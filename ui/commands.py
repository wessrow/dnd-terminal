"""Command list for the inline, nvim-style command palette (see PromptBar in
widgets.py and DndSheetApp.open_command_prompt in app.py). Plain functions rather
than a Textual `command.Provider` - the palette is rendered ourselves as a bottom
input + results list instead of using Textual's built-in floating palette."""

import re

from textual.fuzzy import Matcher

from domain import sheet

from . import icons
from .constants import CONDITIONAL_TABS, TAB_IDS, TAB_LABELS

_DYNAMIC_PATTERNS = [
    (re.compile(r"^(damage|dmg|hurt)\s+(\d+)$", re.IGNORECASE),
     lambda app, n: (f"{icons.DAMAGE}  Apply {n} damage", lambda: app.apply_damage(n))),
    (re.compile(r"^(heal|hp)\s+(\d+)$", re.IGNORECASE),
     lambda app, n: (f"{icons.HEAL}  Heal {n} HP", lambda: app.apply_heal(n))),
    (re.compile(r"^(temp|temphp)\s+(\d+)$", re.IGNORECASE),
     lambda app, n: (f"{icons.SHIELD}  Add {n} temporary HP", lambda: app.apply_temp_hp(n))),
]


def list_commands(app) -> list[tuple[str, callable]]:
    """[(display_text, callback), ...] for every command, in a sensible default order."""
    commands = [
        (f"{icons.REFRESH}  Refresh from D&D Beyond", app.action_refresh),
        (f"{icons.CHARACTER}  Switch Character", app.open_character_select),
        (f"{icons.DAMAGE}  Damage...", app.open_damage_input),
        (f"{icons.HEAL}  Heal...", app.open_heal_input),
        (f"{icons.SHIELD}  Temporary HP...", app.open_temp_hp_input),
        (f"{icons.LONG_REST}  Long Rest", app.do_long_rest),
        (f"{icons.SHORT_REST}  Short Rest", app.do_short_rest),
        (f"{icons.INSPIRATION}  Toggle Heroic Inspiration", app.toggle_inspiration),
    ]
    if app.character_data is not None:
        if sheet.pact_magic_slots(app.character_data):
            commands.append((f"{icons.SPELLS}  Use Pact Magic Slot", app.use_pact_slot))
            commands.append((f"{icons.SPELLS}  Restore Pact Magic Slot", app.restore_pact_slot))
        for level, _, _ in sheet.spell_slots(app.character_data):
            commands.append((f"{icons.SPELLS}  Use Level {level} Spell Slot", lambda lvl=level: app.use_spell_slot(lvl)))
            commands.append((f"{icons.SPELLS}  Restore Level {level} Spell Slot", lambda lvl=level: app.restore_spell_slot(lvl)))
        for res in sheet.class_resources(app.character_data):
            name = res["name"]
            commands.append((f"{icons.RESOURCES}  Use {name}", lambda n=name: app.use_resource(n)))
            commands.append((f"{icons.RESOURCES}  Restore {name}", lambda n=name: app.restore_resource(n)))
    if app.has_familiar:
        for form in app.familiar_forms_available:
            commands.append((f"{icons.FAMILIAR}  Summon Familiar: {form}", lambda f=form: app.summon_familiar(f)))
        if app.state.get("familiar_form"):
            commands.append((f"{icons.FAMILIAR}  Dismiss Familiar", app.dismiss_familiar))
            commands.append((f"{icons.DAMAGE}  Damage Familiar...", app.open_familiar_damage_input))
            commands.append((f"{icons.HEAL}  Heal Familiar...", app.open_familiar_heal_input))
    for tab_id in TAB_IDS:
        gate = CONDITIONAL_TABS.get(tab_id)
        if gate and not getattr(app, gate):
            continue  # hidden tab (see DndSheetApp._sync_conditional_tabs) - nothing to jump to
        commands.append((f"Go to {TAB_LABELS[tab_id]} tab", lambda t=tab_id: app.goto_tab(t)))
    for theme_name in app.available_themes:
        commands.append((f"{icons.THEME}  Theme: {theme_name}", lambda t=theme_name: setattr(app, "theme", t)))
    commands.append(
        (f"{icons.DANGER}  DANGER: reset ALL local tracking to D&D Beyond", app.reset_to_ddb_baseline)
    )
    return commands


def match_commands(app, query: str) -> list[tuple[str, callable]]:
    """[(display_text, callback), ...] for the query, best match first. Recognizes
    typed amounts (e.g. "damage 8") as a single top hit, same as before."""
    query = query.strip()
    for pattern, build in _DYNAMIC_PATTERNS:
        m = pattern.match(query)
        if m:
            return [build(app, int(m.group(2)))]

    commands = list_commands(app)
    if not query:
        return commands

    matcher = Matcher(query)
    scored = [(matcher.match(text), text, cb) for text, cb in commands]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda s: s[0], reverse=True)
    return [(text, cb) for _, text, cb in scored]
