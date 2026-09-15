import asyncio

import requests
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    OptionList,
    ProgressBar,
    Static,
    TabbedContent,
    TabPane,
    Tabs,
)
from textual.widgets.option_list import Option

from clients import ddb_client, open5e_client
from domain import sheet
from domain.combat import CombatTracker
from storage import state_store
from ui import formatting, icons
from ui.commands import list_commands, match_commands
from ui.constants import SEARCHABLE_TABS, TAB_IDS, TAB_LABELS, TAB_PRIMARY_WIDGET
from ui.screens import CharacterSelectScreen
from ui.widgets import PromptBar, ReferenceTable, VimDataTable

# Widgets whose .loading spinner should show while the character fetch is in flight.
LOADING_WIDGETS = (
    "#identity", "#abilities", "#saves", "#hp-line", "#hp-bar",
    "#combat-rest", "#skills", "#spells", "#resources", "#inventory",
)

PROMPT_PLACEHOLDERS = {
    "search": f"{icons.SEARCH}  Search this pane...",
    "damage": f"{icons.DAMAGE}  Damage amount...",
    "heal": f"{icons.HEAL}  Heal amount...",
    "temp": f"{icons.SHIELD}  Temporary HP amount...",
    "command": f"{icons.COMMAND}  Command...",
}

MAX_NOTIFICATIONS = 5


class DndSheetApp(App):
    TITLE = "D&D Terminal"
    CSS_PATH = "ui/app.tcss"
    ENABLE_COMMAND_PALETTE = False  # replaced by our own nvim-style PromptBar palette

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
        Binding("]", "next_tab", "Next tab"),
        Binding("[", "prev_tab", "Prev tab"),
        Binding("/", "search", "Search"),
        Binding(":", "open_command_prompt", "Commands"),
    ]

    def __init__(self):
        super().__init__()
        config = state_store.load_config()
        if theme := config.get("theme"):
            self.theme = theme

        self.character_id: str | None = ddb_client.get_character_id() or state_store.load_registry()["last_used"]
        self.character_data: dict | None = None
        self.state: dict = state_store.load(self.character_id) if self.character_id else state_store.default_state()
        self.combat: CombatTracker | None = None
        self.conditions_by_slug: dict[str, dict] = {}
        self.spells_by_key: dict[str, dict] = {}
        self.items_by_key: dict[str, dict] = {}
        self.resources_by_name: dict[str, dict] = {}
        self._condition_name_col = None
        self._condition_active_col = None
        self._spell_name_col = None
        self._spell_notes_col = None
        self._prompt_mode: str | None = None
        self._command_matches: list[tuple[str, callable]] = []

    def watch_theme(self, theme_name: str) -> None:
        state_store.save_config({**state_store.load_config(), "theme": theme_name})

    def _on_notify(self, event) -> None:
        """Cap stacked toasts at MAX_NOTIFICATIONS, dropping the oldest first -
        Textual has no built-in limit and they'd otherwise pile up indefinitely."""
        super()._on_notify(event)
        while len(self._notifications) > MAX_NOTIFICATIONS:
            self._unnotify(next(iter(self._notifications)), refresh=False)
        self._refresh_notifications()

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with VerticalScroll(id="sidebar"):
                with Vertical(id="identity-panel", classes="panel"):
                    yield Static(id="identity")
                with Vertical(id="abilities-panel", classes="panel"):
                    yield ReferenceTable(id="abilities")
                with Vertical(id="saves-panel", classes="panel"):
                    yield ReferenceTable(id="saves")
                with Vertical(id="combat-panel", classes="panel"):
                    yield Static(id="hp-line")
                    yield ProgressBar(id="hp-bar", show_percentage=False, show_eta=False)
                    yield Static(id="combat-rest")
            with TabbedContent(id="main-tabs"):
                with TabPane(f"{icons.SKILLS} Skills", id="tab-skills"):
                    yield ReferenceTable(id="skills")
                with TabPane(f"{icons.SPELLS} Spells", id="tab-spells"):
                    yield VimDataTable(id="spells")
                    yield Static(id="spell-detail", classes="detail")
                with TabPane(f"{icons.RESOURCES} Resources", id="tab-resources"):
                    yield VimDataTable(id="resources")
                    yield Static(id="resource-detail", classes="detail")
                with TabPane(f"{icons.INVENTORY} Inventory", id="tab-inventory"):
                    yield VimDataTable(id="inventory")
                    yield Static(id="item-detail", classes="detail")
                with TabPane(f"{icons.CONDITIONS} Conditions", id="tab-conditions"):
                    yield VimDataTable(id="conditions")
                    yield Static(id="active-effects")
                    yield Static(id="condition-detail", classes="detail")
        command_list = OptionList(id="command-list")
        command_list.can_focus = False  # see PromptBar's docstring re: AUTO_FOCUS
        with Vertical(id="palette"):
            yield command_list
            yield PromptBar(id="prompt-bar")
        yield Footer()

    def on_mount(self) -> None:
        for scroll in self.query(VerticalScroll):
            scroll.can_focus = False
        for tabs in self.query(Tabs):
            tabs.can_focus = False

        self.query_one("#identity-panel").border_title = f"{icons.CHARACTER} Character"
        self.query_one("#abilities-panel").border_title = f"{icons.ABILITIES} Ability Scores"
        self.query_one("#saves-panel").border_title = f"{icons.SAVES} Saving Throws"
        self.query_one("#combat-panel").border_title = f"{icons.COMBAT} Combat"

        self.query_one("#abilities", DataTable).add_columns("Ability", "Score", "Mod")
        self.query_one("#saves", DataTable).add_columns("Save", "Mod", "")
        self.query_one("#skills", DataTable).add_columns("Skill", "Ability", "Mod", "")
        spell_columns = self.query_one("#spells", DataTable).add_columns("Spell", "Level", "School", "Source", "Notes")
        self._spell_name_col, _, _, _, self._spell_notes_col = spell_columns
        self.query_one("#resources", DataTable).add_columns("Resource", "Uses", "Reset")
        self.query_one("#inventory", DataTable).add_columns("Item", "Qty", "Equipped", "Weight")
        columns = self.query_one("#conditions", DataTable).add_columns("Condition", "Active")
        self._condition_name_col, self._condition_active_col = columns

        if self.character_id is None:
            self.open_character_select()
        else:
            self.start_loading()

    def on_character_chosen(self, character_id: str | None) -> None:
        if character_id is None:
            return
        self.character_id = character_id
        self.state = state_store.load(character_id)
        self.start_loading()

    def open_character_select(self) -> None:
        self.push_screen(CharacterSelectScreen(state_store.load_registry()["characters"]), self.on_character_chosen)

    # ------------------------------------------------------------------ #
    # Loading (async, so the UI paints immediately and shows spinners)
    # ------------------------------------------------------------------ #

    def start_loading(self) -> None:
        self.run_worker(self.load_character(), exclusive=True, group="character")
        self.run_worker(self.load_conditions(), exclusive=True, group="conditions")

    async def load_character(self) -> None:
        for widget_id in LOADING_WIDGETS:
            self.query_one(widget_id).loading = True
        try:
            data = await asyncio.to_thread(ddb_client.fetch_character, self.character_id)
        except ddb_client.CharacterFetchError as exc:
            for widget_id in LOADING_WIDGETS:
                self.query_one(widget_id).loading = False
            self.query_one("#identity", Static).update(f"[bold red]{exc}[/bold red]")
            return
        self.character_data = data
        self.combat = CombatTracker(data, self.state)
        state_store.remember_character(self.character_id, data["name"])
        self.populate(data)
        for widget_id in LOADING_WIDGETS:
            self.query_one(widget_id).loading = False

    async def load_conditions(self) -> None:
        table = self.query_one("#conditions", DataTable)
        detail = self.query_one("#condition-detail", Static)
        table.loading = True
        try:
            conditions = await asyncio.to_thread(open5e_client.fetch_conditions)
        except requests.RequestException as exc:
            table.loading = False
            detail.update(f"[bold red]Failed to load conditions from Open5e: {exc}[/bold red]")
            return

        conditions = sorted(conditions, key=lambda c: c["name"])
        self.conditions_by_slug = {c["slug"]: c for c in conditions}
        table.clear()
        for condition in conditions:
            is_active = condition["slug"] in self.state["active_conditions"]
            table.add_row(
                formatting.condition_name_cell(condition["name"], is_active),
                formatting.active_marker(is_active),
                key=condition["slug"],
            )
        table.loading = False

        if conditions:
            detail.update(conditions[0]["desc"])
        self.render_active_effects()
        if self.character_data:
            self.render_combat_panel()

    def action_refresh(self) -> None:
        if self.character_id is None:
            self.open_character_select()
            return
        self.run_worker(self.load_character(), exclusive=True, group="character")

    # ------------------------------------------------------------------ #
    # PromptBar: one non-modal input line used for search, damage, heal, and
    # temp-HP - none of these hide the sheet the way a full modal screen would.
    # ------------------------------------------------------------------ #

    def open_prompt(self, mode: str) -> None:
        self._prompt_mode = mode
        bar = self.query_one("#prompt-bar", PromptBar)
        bar.placeholder = PROMPT_PLACEHOLDERS[mode]
        bar.value = ""
        bar.add_class("visible")
        bar.can_focus = True
        bar.focus()
        if mode == "command":
            self._refresh_command_matches("")
            self.query_one("#command-list", OptionList).add_class("visible")

    def close_prompt(self) -> None:
        bar = self.query_one("#prompt-bar", PromptBar)
        bar.remove_class("visible")
        bar.value = ""
        bar.can_focus = False
        self._prompt_mode = None
        self._command_matches = []
        command_list = self.query_one("#command-list", OptionList)
        command_list.remove_class("visible")
        command_list.clear_options()
        widget_selector = TAB_PRIMARY_WIDGET.get(self.query_one(TabbedContent).active)
        if widget_selector:
            self.query_one(widget_selector).focus()

    def action_search(self) -> None:
        tab_id = self.query_one(TabbedContent).active
        if tab_id in SEARCHABLE_TABS:
            self.open_prompt("search")

    def action_open_command_prompt(self) -> None:
        self.open_prompt("command")

    def open_damage_input(self) -> None:
        self.open_prompt("damage")

    def open_heal_input(self) -> None:
        self.open_prompt("heal")

    def open_temp_hp_input(self) -> None:
        self.open_prompt("temp")

    def _refresh_command_matches(self, query: str) -> None:
        self._command_matches = match_commands(self, query)
        command_list = self.query_one("#command-list", OptionList)
        command_list.clear_options()
        for i, (text, _) in enumerate(self._command_matches):
            command_list.add_option(Option(text, id=str(i)))
        if self._command_matches:
            command_list.highlighted = 0

    def on_prompt_bar_cancelled(self, event: PromptBar.Cancelled) -> None:
        self.close_prompt()

    def on_prompt_bar_navigate(self, event: PromptBar.Navigate) -> None:
        if self._prompt_mode != "command":
            return
        command_list = self.query_one("#command-list", OptionList)
        if event.direction == "up":
            command_list.action_cursor_up()
        else:
            command_list.action_cursor_down()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "prompt-bar" and self._prompt_mode == "command":
            self._refresh_command_matches(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "prompt-bar":
            return
        mode, value = self._prompt_mode, event.value.strip()

        if mode == "command":
            command_list = self.query_one("#command-list", OptionList)
            index = command_list.highlighted
            matches = self._command_matches
            self.close_prompt()
            if index is not None and index < len(matches):
                matches[index][1]()
            return

        self.close_prompt()
        if not value:
            return

        if mode == "search":
            self._jump_to_match(value)
            return

        try:
            amount = int(value)
        except ValueError:
            self.notify("Enter a whole number", severity="error")
            return
        if mode == "damage":
            self.apply_damage(amount)
        elif mode == "heal":
            self.apply_heal(amount)
        elif mode == "temp":
            self.apply_temp_hp(amount)

    def _jump_to_match(self, query: str) -> None:
        tab_id = self.query_one(TabbedContent).active
        selector = SEARCHABLE_TABS.get(tab_id)
        if not selector:
            return
        table = self.query_one(selector, DataTable)
        needle = query.lower()
        for row_index in range(table.row_count):
            row = table.get_row_at(row_index)
            if any(needle in str(cell).lower() for cell in row):
                table.move_cursor(row=row_index)
                if table.can_focus:
                    table.focus()
                return
        self.notify(f'No match for "{query}"', severity="warning")

    # ------------------------------------------------------------------ #
    # Populate from D&D Beyond data
    # ------------------------------------------------------------------ #

    def populate(self, data: dict) -> None:
        self.title = data["name"]
        level = sheet.total_level(data)
        languages = ", ".join(sheet.languages(data)) or "-"
        classes = data["classes"]
        if len(classes) == 1:
            # single-class: fold the class name into the level line instead of a
            # separate "Warlock 5" line that just repeats the level shown above it
            class_line = f"Level {level} {data['race']['fullName']} {classes[0]['definition']['name']}"
        else:
            class_line = f"Level {level} {data['race']['fullName']}\n{sheet.class_summary(data)}"
        self.query_one("#identity", Static).update(
            f"[bold]{data['name']}[/bold]\n"
            f"{class_line}\n"
            f"Background: {data['background']['definition']['name']}\n"
            f"Alignment: {sheet.alignment_name(data)}\n"
            f"Languages: {languages}"
        )

        abilities = self.query_one("#abilities", DataTable)
        abilities.clear()
        scores = sheet.ability_scores(data)
        for ability_id, name in sheet.ABILITY_ABBR.items():
            score = scores[ability_id]
            modifier = sheet.ability_modifier(score)
            abilities.add_row(name, str(score), sheet.format_modifier(modifier))

        saves = self.query_one("#saves", DataTable)
        saves.clear()
        for save in sheet.saving_throws(data):
            saves.add_row(
                save["ability"],
                sheet.format_modifier(save["modifier"]),
                formatting.proficiency_marker(save["proficient"], False),
            )

        self.render_combat_panel()

        skills_table = self.query_one("#skills", DataTable)
        skills_table.clear()
        for skill in sheet.skills(data):
            skills_table.add_row(
                skill["name"],
                skill["ability"],
                sheet.format_modifier(skill["modifier"]),
                formatting.proficiency_marker(skill["proficient"], skill["expertise"]),
            )
        self.spells_by_key.clear()
        for i, spell in enumerate(sheet.known_spells(data)):
            self.spells_by_key[str(i)] = spell
        self.render_spells(rebuild=True)

        self.render_resources()

        inventory = self.query_one("#inventory", DataTable)
        inventory.clear()
        self.items_by_key.clear()
        for i, item in enumerate(sheet.inventory_items(data)):
            key = str(i)
            self.items_by_key[key] = item
            inventory.add_row(
                item["name"],
                str(item["quantity"]),
                "Yes" if item["equipped"] else "",
                f"{item['weight']} lb",
                key=key,
            )
        if self.items_by_key:
            self.query_one("#item-detail", Static).update(formatting.item_detail(self.items_by_key["0"]))

    # ------------------------------------------------------------------ #
    # Local combat-tracking overlay: thin wrappers around CombatTracker that
    # persist state and refresh the UI after each mutation (see domain/combat.py).
    # ------------------------------------------------------------------ #

    def apply_damage(self, amount: int) -> None:
        if not self.combat:
            return
        current, max_hp = self.combat.apply_damage(amount)
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.notify(f"{icons.DAMAGE} Took {amount} damage - {current}/{max_hp} HP")

    def apply_heal(self, amount: int) -> None:
        if not self.combat:
            return
        current, max_hp, _ = self.combat.effective_hp()
        if current >= max_hp:
            self.notify(f"{icons.HEAL} HP Full ({max_hp}/{max_hp})")
            return
        current, max_hp = self.combat.apply_heal(amount)
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.notify(f"{icons.HEAL} Healed {amount} - {current}/{max_hp} HP")

    def apply_temp_hp(self, amount: int) -> None:
        if not self.combat:
            return
        new_temp = self.combat.apply_temp_hp(amount)
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.notify(f"{icons.SHIELD} Temporary HP set to {new_temp}")

    def toggle_inspiration(self) -> None:
        if not self.combat:
            return
        new_value = self.combat.toggle_inspiration()
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.notify(f"{icons.INSPIRATION} Heroic Inspiration: {'Yes' if new_value else 'No'}")

    def use_pact_slot(self) -> None:
        self.combat.use_pact_slot()
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.render_spells()

    def restore_pact_slot(self) -> None:
        self.combat.restore_pact_slot()
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.render_spells()

    def use_resource(self, name: str) -> None:
        if not self.combat:
            return
        if self.combat.use_resource(name):
            state_store.save(self.character_id, self.state)
            self.render_resources()
            self.notify(f"{icons.RESOURCES} Used {name}")
        else:
            self.notify(f"No uses of {name} left!", severity="warning")

    def restore_resource(self, name: str) -> None:
        if not self.combat:
            return
        self.combat.restore_resource(name)
        state_store.save(self.character_id, self.state)
        self.render_resources()

    def use_spell_slot(self, level: int) -> None:
        self.combat.use_spell_slot(level)
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.render_spells()

    def restore_spell_slot(self, level: int) -> None:
        self.combat.restore_spell_slot(level)
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.render_spells()

    def cast_spell(self, spell: dict) -> None:
        message = self.combat.cast_spell(spell)
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.render_spells()
        if message.startswith("No "):
            self.notify(message, severity="warning")
        elif message.startswith("Cast "):
            self.notify(f"{icons.SPELLS} {message}")
        else:
            self.notify(message)

    def do_long_rest(self) -> None:
        if not self.combat:
            return
        self.combat.long_rest()
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.render_resources()
        self.render_spells()
        self.notify(f"{icons.LONG_REST} Long rest complete - HP, spell slots, and resources restored (tracked locally)")

    def do_short_rest(self) -> None:
        if not self.combat:
            return
        if self.combat.short_rest():
            state_store.save(self.character_id, self.state)
            self.render_combat_panel()
            self.render_resources()
            self.render_spells()
            self.notify(f"{icons.SHORT_REST} Short rest complete - resources restored (tracked locally)")
        else:
            self.notify("Nothing to restore on a short rest for this character.")

    def reset_to_ddb_baseline(self) -> None:
        """The "undo everything I've tracked locally this session" button - wipes
        HP/spell-slot/resource/condition overrides so every value falls back to
        whatever D&D Beyond's own data says. Does not touch D&D Beyond itself."""
        if not self.combat:
            return
        self.combat.reset_to_baseline()
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.render_resources()
        self.render_spells()
        self.render_conditions()
        self.notify(f"{icons.DANGER} Reset - all local tracking cleared, back to D&D Beyond's own data", severity="warning")

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def render_combat_panel(self) -> None:
        if not self.character_data:
            return
        data = self.character_data
        current_hp, max_hp, temp_hp = self.combat.effective_hp()

        hp_line = f"{icons.HEART} HP: {current_hp}/{max_hp}" + (f" (+{temp_hp} temp)" if temp_hp else "")
        self.query_one("#hp-line", Static).update(hp_line)
        self.query_one("#hp-bar", ProgressBar).update(total=max_hp, progress=max(current_hp, 0))

        sections = []

        death_saves = data["deathSaves"]
        if current_hp <= 0:
            sections.append(
                f"{icons.DEATH} Death Saves: {death_saves['successCount']} succ / {death_saves['failCount']} fail"
            )

        # Every line here gets a leading icon and pairs up related stats on one
        # row, rather than a long list of single unrelated icon+label lines.
        sections.append(
            f"{icons.SHIELD} AC {sheet.armor_class(data)}"
            f"   {icons.PROFICIENCY} Prof {sheet.format_modifier(sheet.proficiency_bonus(data))}\n"
            f"{icons.INITIATIVE} Init {sheet.format_modifier(sheet.initiative(data))}"
            f"   {icons.SPEED} Speed {sheet.speed(data)} ft"
        )

        sense_lines = [
            f"{icons.EYE} Passive Perception {sheet.passive_skill(data, 'Perception')}",
            f"{icons.EYE} Passive Investigation {sheet.passive_skill(data, 'Investigation')}",
            f"{icons.EYE} Passive Insight {sheet.passive_skill(data, 'Insight')}",
        ]
        sense_lines.extend(f"{icons.EYE} {s['name']} {s['range']} ft" for s in sheet.senses(data))
        sections.append("\n".join(sense_lines))

        active_conditions = [
            self.conditions_by_slug[slug]["name"]
            for slug in self.state["active_conditions"]
            if slug in self.conditions_by_slug
        ]
        conditions_line = f"[bold red]{', '.join(active_conditions)}[/bold red]" if active_conditions else "None"
        inspiration = self.combat.effective_inspiration()
        sections.append(
            f"{icons.INSPIRATION} Inspiration: {'Yes' if inspiration else 'No'}\n"
            f"{icons.CONDITIONS} Conditions: {conditions_line}"
        )

        sections.append(self._spellcasting_summary())
        sections.append(f"{icons.GOLD} {sheet.currency_summary(data)}")

        self.query_one("#combat-rest", Static).update("\n\n".join(sections))

    def render_conditions(self) -> None:
        """Refreshes every row's active styling from self.state - unlike the
        row-selected toggle handler, this is for bulk changes (e.g. resetting to
        baseline) where there's no single row/cursor to preserve."""
        table = self.query_one("#conditions", DataTable)
        for slug, condition in self.conditions_by_slug.items():
            is_active = slug in self.state["active_conditions"]
            table.update_cell(
                slug, self._condition_name_col, formatting.condition_name_cell(condition["name"], is_active),
                update_width=True,
            )
            table.update_cell(slug, self._condition_active_col, formatting.active_marker(is_active), update_width=True)
        self.render_active_effects()

    def render_active_effects(self) -> None:
        panel = self.query_one("#active-effects", Static)
        active = [
            self.conditions_by_slug[slug]
            for slug in self.state["active_conditions"]
            if slug in self.conditions_by_slug
        ]
        if not active:
            panel.update("[dim]No active conditions.[/dim]")
            return
        blocks = [f"[bold red]{c['name']}[/bold red]\n{c['desc']}" for c in active]
        panel.update("\n\n".join(blocks))

    def render_spells(self, rebuild: bool = False) -> None:
        """Refreshes the Spells table's usability styling (dimmed name + live "X/Y
        left" notes). `rebuild=True` also rebuilds the rows from scratch (initial
        load); otherwise it updates cells in place so the cursor position survives
        casting a spell."""
        table = self.query_one("#spells", DataTable)
        if rebuild:
            table.clear()
            for key, spell in self.spells_by_key.items():
                charge = self.combat.effective_spell_charge(spell)
                table.add_row(
                    formatting.spell_name_cell(spell["name"], self.combat.can_cast(spell)),
                    sheet.format_spell_level(spell["level"]),
                    spell["school"],
                    spell["source"],
                    formatting.spell_notes(spell, charge),
                    key=key,
                )
            if self.spells_by_key:
                first_spell = next(iter(self.spells_by_key.values()))
                charge = self.combat.effective_spell_charge(first_spell)
                self.query_one("#spell-detail", Static).update(formatting.spell_detail(first_spell, charge))
        else:
            for key, spell in self.spells_by_key.items():
                charge = self.combat.effective_spell_charge(spell)
                table.update_cell(
                    key, self._spell_name_col,
                    formatting.spell_name_cell(spell["name"], self.combat.can_cast(spell)),
                    update_width=True,
                )
                table.update_cell(key, self._spell_notes_col, formatting.spell_notes(spell, charge), update_width=True)

    def render_resources(self) -> None:
        table = self.query_one("#resources", DataTable)
        table.clear()
        self.resources_by_name.clear()
        for res in self.combat.effective_resources():
            self.resources_by_name[res["name"]] = res
            table.add_row(
                res["name"],
                f"{res['available'] - res['used']}/{res['available']}",
                res["reset_type"],
                key=res["name"],
            )
        if self.resources_by_name:
            first = next(iter(self.resources_by_name.values()))
            self.query_one("#resource-detail", Static).update(formatting.resource_detail(first))
        else:
            self.query_one("#resource-detail", Static).update("[dim]No tracked resources for this character.[/dim]")

    def _spellcasting_summary(self) -> str:
        lines = [f"{icons.SPELLS} Spellcasting:"]
        pact = self.combat.effective_pact_magic()
        if pact:
            used, available = pact
            lines.append(f"  Pact Magic: {available - used}/{available}")
        for level, used, available in self.combat.effective_spell_slots():
            lines.append(f"  Level {level}: {available - used}/{available}")
        if len(lines) == 1:
            lines.append("  (none)")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Tab navigation
    # ------------------------------------------------------------------ #

    def goto_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id
        widget_selector = TAB_PRIMARY_WIDGET.get(tab_id)
        if widget_selector:
            self.query_one(widget_selector).focus()

    def action_next_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        idx = TAB_IDS.index(tabs.active)
        self.goto_tab(TAB_IDS[(idx + 1) % len(TAB_IDS)])

    def action_prev_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        idx = TAB_IDS.index(tabs.active)
        self.goto_tab(TAB_IDS[(idx - 1) % len(TAB_IDS)])

    # ------------------------------------------------------------------ #
    # Table events
    # ------------------------------------------------------------------ #

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        table_id = event.data_table.id
        key = event.row_key.value
        if table_id == "spells" and key in self.spells_by_key:
            spell = self.spells_by_key[key]
            charge = self.combat.effective_spell_charge(spell) if self.combat else None
            self.query_one("#spell-detail", Static).update(formatting.spell_detail(spell, charge))
        elif table_id == "inventory" and key in self.items_by_key:
            self.query_one("#item-detail", Static).update(formatting.item_detail(self.items_by_key[key]))
        elif table_id == "conditions" and key in self.conditions_by_slug:
            self.query_one("#condition-detail", Static).update(self.conditions_by_slug[key]["desc"])
        elif table_id == "resources" and key in self.resources_by_name:
            self.query_one("#resource-detail", Static).update(formatting.resource_detail(self.resources_by_name[key]))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id
        key = event.row_key.value

        if table_id == "conditions":
            active = self.state["active_conditions"]
            if key in active:
                active.remove(key)
            else:
                active.append(key)
            state_store.save(self.character_id, self.state)

            is_active = key in active
            event.data_table.update_cell(
                event.row_key, self._condition_name_col,
                formatting.condition_name_cell(self.conditions_by_slug[key]["name"], is_active),
                update_width=True,
            )
            event.data_table.update_cell(
                event.row_key, self._condition_active_col, formatting.active_marker(is_active), update_width=True
            )
            self.render_active_effects()
            self.render_combat_panel()

        elif table_id == "spells" and key in self.spells_by_key:
            self.cast_spell(self.spells_by_key[key])

        elif table_id == "resources" and key in self.resources_by_name:
            self.use_resource(key)


if __name__ == "__main__":
    DndSheetApp().run()
