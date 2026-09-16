import asyncio

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Input, OptionList, ProgressBar, Static, TabbedContent, Tabs
from textual.widgets.option_list import Option

from clients import ddb_client
from domain import familiar, sheet
from domain.combat import CombatTracker
from storage import state_store
from ui import formatting, icons
from ui.commands import list_commands, match_commands
from ui.constants import CONDITIONAL_TABS, SEARCHABLE_TABS, TAB_IDS, TAB_PRIMARY_WIDGET
from ui.screens import CharacterSelectScreen
from ui.tabs import AttacksTab, ConditionsTab, FamiliarTab, InventoryTab, ResourcesTab, SkillsTab, SpellsTab
from ui.widgets import PromptBar, ReferenceTable, VimDataTable

# Widgets whose .loading spinner should show while the character fetch is in flight.
LOADING_WIDGETS = (
    "#identity", "#abilities", "#saves", "#hp-line", "#hp-bar",
    "#combat-rest", "#skills", "#attacks", "#spells", "#resources", "#inventory",
)

PROMPT_PLACEHOLDERS = {
    "search": f"{icons.SEARCH}  Search this pane...",
    "damage": f"{icons.DAMAGE}  Damage amount...",
    "heal": f"{icons.HEAL}  Heal amount...",
    "temp": f"{icons.SHIELD}  Temporary HP amount...",
    "familiar-damage": f"{icons.DAMAGE}  Familiar damage amount...",
    "familiar-heal": f"{icons.HEAL}  Familiar heal amount...",
    "command": f"{icons.COMMAND}  Command...",
}

MAX_NOTIFICATIONS = 5


class DndSheetApp(App):
    """Composes the layout out of ui/tabs/*'s per-tab widgets and wires
    top-level events. Owns: the sidebar (identity/abilities/saves/combat
    panel), the CombatTracker and everything that mutates it (damage/heal/
    rest/spell-slot/resource/familiar actions - all cross-cutting, since a
    single rest can touch HP, Resources, and Spells at once), the command
    palette/PromptBar, and tab navigation. Each tab in ui/tabs/ owns its own
    widgets' compose/populate/render and whatever event handling is purely
    local to it - see ui/tabs/__init__.py.
    """

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
        self.familiar_forms_available: list[str] = []
        self.is_spellcaster: bool = True  # updated per-character in populate()
        self.has_familiar: bool = True  # updated per-character in populate()
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
                yield SkillsTab()
                yield AttacksTab()
                yield SpellsTab()
                yield FamiliarTab()
                yield ResourcesTab()
                yield InventoryTab()
                yield ConditionsTab()
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
        self.run_worker(self.query_one(ConditionsTab).load(), exclusive=True, group="conditions")

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
        state_store.remember_character(self.character_id, data["name"], sheet.class_summary(data))
        self.populate(data)
        for widget_id in LOADING_WIDGETS:
            self.query_one(widget_id).loading = False
        self.run_worker(
            self.query_one(FamiliarTab).load(self.state.get("familiar_form")), exclusive=True, group="familiar"
        )

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
        elif mode == "familiar-damage":
            self.apply_familiar_damage(amount)
        elif mode == "familiar-heal":
            self.apply_familiar_heal(amount)

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

        self.query_one(SkillsTab).populate(data)
        self.query_one(AttacksTab).populate(data)
        self.query_one(SpellsTab).populate(data)
        self.query_one(InventoryTab).populate(data)

        self.is_spellcaster = sheet.is_spellcaster(data)
        self.has_familiar = sheet.has_familiar(data)
        self.familiar_forms_available = sheet.familiar_forms(data)
        self._sync_conditional_tabs()

        self.query_one(ResourcesTab).refresh_data()

    # ------------------------------------------------------------------ #
    # Local combat-tracking overlay: thin wrappers around CombatTracker that
    # persist state and refresh the UI after each mutation (see domain/combat.py).
    # These stay app-level (rather than living on whichever tab triggered them)
    # because a single mutation often has to refresh several tabs plus the
    # sidebar combat panel at once - e.g. a rest touches HP, Resources, AND
    # Spells - which only app.py has a reference to all of.
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
        self.query_one(SpellsTab).refresh_data()

    def restore_pact_slot(self) -> None:
        self.combat.restore_pact_slot()
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.query_one(SpellsTab).refresh_data()

    def use_resource(self, name: str) -> None:
        if not self.combat:
            return
        if self.combat.use_resource(name):
            state_store.save(self.character_id, self.state)
            self.query_one(ResourcesTab).refresh_data()
            self.notify(f"{icons.RESOURCES} Used {name}")
        else:
            self.notify(f"No uses of {name} left!", severity="warning")

    def restore_resource(self, name: str) -> None:
        if not self.combat:
            return
        self.combat.restore_resource(name)
        state_store.save(self.character_id, self.state)
        self.query_one(ResourcesTab).refresh_data()

    def use_spell_slot(self, level: int) -> None:
        self.combat.use_spell_slot(level)
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.query_one(SpellsTab).refresh_data()

    def restore_spell_slot(self, level: int) -> None:
        self.combat.restore_spell_slot(level)
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.query_one(SpellsTab).refresh_data()

    def cast_spell(self, spell: dict) -> None:
        message = self.combat.cast_spell(spell)
        state_store.save(self.character_id, self.state)
        self.render_combat_panel()
        self.query_one(SpellsTab).refresh_data()
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
        self.query_one(ResourcesTab).refresh_data()
        self.query_one(SpellsTab).refresh_data()
        self.notify(f"{icons.LONG_REST} Long rest complete - HP, spell slots, and resources restored (tracked locally)")

    def do_short_rest(self) -> None:
        if not self.combat:
            return
        if self.combat.short_rest():
            state_store.save(self.character_id, self.state)
            self.render_combat_panel()
            self.query_one(ResourcesTab).refresh_data()
            self.query_one(SpellsTab).refresh_data()
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
        self.query_one(ResourcesTab).refresh_data()
        self.query_one(SpellsTab).refresh_data()
        self.query_one(ConditionsTab).refresh_data()
        self.notify(f"{icons.DANGER} Reset - all local tracking cleared, back to D&D Beyond's own data", severity="warning")

    def summon_familiar(self, form: str) -> None:
        familiar.FamiliarTracker(None, self.state).summon(form)
        state_store.save(self.character_id, self.state)
        self.notify(f"{icons.FAMILIAR} Summoned {form}")
        self.run_worker(self.query_one(FamiliarTab).load(form), exclusive=True, group="familiar")

    def dismiss_familiar(self) -> None:
        form = self.state.get("familiar_form")
        familiar.FamiliarTracker(None, self.state).dismiss()
        state_store.save(self.character_id, self.state)
        self.notify(f"{icons.FAMILIAR} Dismissed {form or 'familiar'}")
        self.run_worker(self.query_one(FamiliarTab).load(None), exclusive=True, group="familiar")

    def open_familiar_damage_input(self) -> None:
        self.open_prompt("familiar-damage")

    def open_familiar_heal_input(self) -> None:
        self.open_prompt("familiar-heal")

    def apply_familiar_damage(self, amount: int) -> None:
        tab = self.query_one(FamiliarTab)
        form = self.state.get("familiar_form")
        result = familiar.FamiliarTracker(tab.monster, self.state).apply_damage(amount)
        if result is None:
            self.notify("No familiar HP to track (none summoned, or no stat block found).", severity="warning")
            return
        state_store.save(self.character_id, self.state)
        current, max_hp = result
        if self.state.get("familiar_form") is None:
            # apply_damage() already despawned it (dropped to 0 HP) - reload
            # the tab (form=None) rather than refresh_data(), since the tab's
            # cached monster is now stale and would otherwise still render
            # against it.
            self.run_worker(tab.load(None), exclusive=True, group="familiar")
            self.notify(
                f"{icons.DEATH} {form} dropped to 0 HP and disappeared! Re-cast Find Familiar to summon it again.",
                severity="warning",
            )
        else:
            tab.refresh_data()
            self.notify(f"{icons.DAMAGE} Familiar took {amount} damage - {current}/{max_hp} HP")

    def apply_familiar_heal(self, amount: int) -> None:
        tab = self.query_one(FamiliarTab)
        tracker = familiar.FamiliarTracker(tab.monster, self.state)
        effective = tracker.effective_hp()
        if effective is None:
            self.notify("No familiar HP to track (none summoned, or no stat block found).", severity="warning")
            return
        current, max_hp = effective
        if current >= max_hp:
            self.notify(f"{icons.HEAL} Familiar HP Full ({max_hp}/{max_hp})")
            return
        current, max_hp = tracker.apply_heal(amount)
        state_store.save(self.character_id, self.state)
        tab.refresh_data()
        self.notify(f"{icons.HEAL} Familiar healed {amount} - {current}/{max_hp} HP")

    # ------------------------------------------------------------------ #
    # Sidebar rendering (identity/abilities/saves are populate()-only; the
    # combat panel also changes on every HP/rest/condition/inspiration action)
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

        conditions_by_slug = self.query_one(ConditionsTab).conditions_by_slug
        active_conditions = [
            conditions_by_slug[slug]["name"]
            for slug in self.state["active_conditions"]
            if slug in conditions_by_slug
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

    def _visible_tab_ids(self) -> list[str]:
        """TAB_IDS minus any tab CONDITIONAL_TABS gates off for this character
        (no Spells for a pure martial, no Familiar with no way to cast Find
        Familiar) - hidden rather than left as a permanently empty pane."""
        return [t for t in TAB_IDS if t not in CONDITIONAL_TABS or getattr(self, CONDITIONAL_TABS[t])]

    def _sync_conditional_tabs(self) -> None:
        tabs = self.query_one(TabbedContent)
        for tab_id, attr in CONDITIONAL_TABS.items():
            if getattr(self, attr):
                tabs.show_tab(tab_id)
            else:
                tabs.hide_tab(tab_id)
        # Textual's Tabs.hide() relocates `active` off a hidden tab via a
        # posted TabActivated message, processed on a later refresh - not
        # synchronously. Hiding two tabs in the same tick (Spells + Familiar
        # together, for a pure martial) can leave `active` resolving onto
        # whichever tab got hidden second once those messages finally land,
        # since each hide_tab() call's own relocation logic was computed
        # before the other's had applied. Deferred to after Textual's own
        # refresh/message processing so this reliably sees (and can correct)
        # the real settled value instead of a stale one - confirmed by
        # testing that fixing this synchronously, before OR after the loop,
        # does not work. See CLAUDE.md.
        self.call_after_refresh(self._fix_active_tab_if_hidden)

    def _fix_active_tab_if_hidden(self) -> None:
        tabs = self.query_one(TabbedContent)
        visible = self._visible_tab_ids()
        if tabs.active not in visible and visible:
            self.goto_tab(visible[0])

    def action_next_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        visible = self._visible_tab_ids()
        idx = visible.index(tabs.active)
        self.goto_tab(visible[(idx + 1) % len(visible)])

    def action_prev_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        visible = self._visible_tab_ids()
        idx = visible.index(tabs.active)
        self.goto_tab(visible[(idx - 1) % len(visible)])


if __name__ == "__main__":
    DndSheetApp().run()
