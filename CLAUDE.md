# D&D Terminal

A personal terminal UI (Textual) for viewing a D&D Beyond character sheet and
tracking combat state (HP, spell slots, conditions) during a session. Single
character-focused, single user, no server component.

## Running it

```
uv run app.py          # the TUI
uv run fetch_test.py   # quick CLI smoke test of the D&D Beyond fetch, no TUI
uv run pytest          # automated tests (tests/) - no network, no real .state/
```

Requires a **Nerd Font** in the terminal (icons throughout the UI use Font Awesome
codepoints from `ui/icons.py`) - they render as boxes otherwise.

## Architecture

```
app.py              entry point + DndSheetApp (composes the layout, wires events)
fetch_test.py        CLI smoke test, no TUI

clients/             talks to the outside world - nothing else does
  ddb_client.py       D&D Beyond character fetch (unofficial API, read-only)
  open5e_client.py     Open5e SRD conditions fetch

domain/              pure logic - no Textual, no I/O, independently testable
  sheet.py            derives sheet values (ability mods, AC, HP, skills, spells,
                       saves, languages, class resources, proficiency bonus) from
                       raw D&D Beyond JSON - all class/race-agnostic, see below
  combat.py           CombatTracker: local HP / spell-slot / resource / inspiration
                       overlay on top of sheet.py's baseline

storage/
  state_store.py       local JSON persistence under .state/: per-character combat
                        state, the character registry, and app config (theme)

ui/                  Textual-specific
  widgets.py           VimDataTable (hjkl + row cursor, interactive tables),
                        ReferenceTable (non-focusable, read-only tables), PromptBar
                        (non-modal bottom input for search/damage/heal/temp-HP/the
                        inline command palette)
  screens.py           CharacterSelectScreen (the one real modal - picking a
                        character is rare/deliberate enough to warrant it)
  commands.py          list_commands/match_commands: plain functions (not a
                        Textual command.Provider) backing the inline palette
  formatting.py        Rich Text/markup helpers - presentation only, no app state
  icons.py             Nerd Font glyph constants
  constants.py         tab id/label/focus-target maps shared by app.py + commands.py
  app.tcss             all CSS, external to keep app.py free of a giant string
```

Keep this layering when adding features: sheet math goes in `domain/sheet.py`,
anything that mutates tracked-but-not-DDB-owned state goes in
`domain/combat.py`/`storage/state_store.py`, Rich formatting goes in
`ui/formatting.py`. `app.py` should stay glue: fetch → call a pure function → put
the result in a widget. Modules within a package import siblings relatively
(`from . import sheet`); cross-package imports are absolute (`from domain import
sheet`).

**Gotcha carried over from before the reorg**: `state_store.STATE_DIR` is computed
as `Path(__file__).parent.parent / ".state"` specifically so it resolves to the
project root regardless of which package `state_store.py` lives in - don't
"simplify" that to `.parent` or saves silently start writing into `storage/.state/`.

## D&D Beyond API - things that aren't obvious from the JSON

- Endpoint: `https://character-service.dndbeyond.com/character/v5/character/{id}`,
  no auth needed **as long as the character's sharing visibility is set to Public**
  in D&D Beyond's UI. Needs a normal browser `User-Agent` header or it 403s.
- **`baseHitPoints` excludes the Constitution modifier.** D&D Beyond's client adds
  `conMod * total_level` on top. Miss this and HP is wrong by exactly that amount.
- **No AC field at all.** Computed client-side from equipped armor type (light =
  full Dex, medium = Dex capped at +2, heavy = no Dex) + shield + flat
  `armor-class` bonus modifiers. See `sheet.armor_class`.
- **Pact Magic / spell slot totals aren't in the obvious field.** The `pactMagic`/
  `spellSlots` arrays only reliably hold `used` (and even that only if the player
  has manually toggled it on the website - it's not kept in sync with actual play).
  The *available* count has to be computed from
  `class.definition.spellRules.levelSpellSlots[characterLevel]`.
- **There's no `castingType`/`isPactMagic` flag anywhere to tell Pact Magic apart
  from regular spell slots generically** - the only way to know a class uses Pact
  Magic is that its own `classFeatures` list contains a feature literally named
  `"Pact Magic"` (`sheet._has_pact_magic`). This is what `pact_magic_slots`/
  `spell_slots` key off instead of the class's name, so it's not special-cased to
  "Warlock" the string - it works for any class (including homebrew/reflavored
  ones) that grants that feature, entirely from data already in the character
  JSON. **No external ruleset dataset needed for this** - the character's own
  feature list is the source of truth. Apply the same principle before adding any
  other "is this class an X" check: look for the matching class feature by name
  first, only fall back to a name/dataset lookup if the JSON truly doesn't say.
- Skill/save proficiency isn't a boolean flag on the skill - it's scattered across
  `modifiers.{race,class,background,feat,item,condition}`, matched by `subType`
  slug (e.g. `"arcana"`, `"wisdom-saving-throws"`) and `type`
  (`proficiency`/`expertise`/`half-proficiency`). See `sheet._proficiency_multiplier`.
- **Ability score increases from feats/racial traits don't show up in
  `bonusStats`/`overrideStats`** (those stay `null` even when the score is
  visibly higher on the website) - they're `type: "bonus"` modifiers with
  `subType: "<ability>-score"` (e.g. `"strength-score"`), same scattered pattern
  as everything else. `sheet.ability_scores` folds these in; this bit us for real
  (STR/CON/CHA all read 1-2 points low, which then made every save/skill/HP/AC
  derived from them wrong too - one root cause, many wrong-looking symptoms).
- **Languages** are the same story: `type: "language"` modifiers scattered the same
  way, named via `friendlySubtypeName`. See `sheet.languages`.
- Feat/race-granted spells (Magic Initiate, Shadow Touched, etc.) live in
  `spells.feat`/`spells.race`, **not** `classSpells`, and the same spell can appear
  twice there (once per casting mode - free 1/long-rest vs. via a real slot).
  Dedupe by name (`sheet.known_spells` does this). The free-cast side has its own
  `limitedUse` block (same shape as class resources, above) - `known_spells`
  carries `free_cast`/`max_uses`/`used_baseline`/`reset_type`/`slot_cast` as plain
  data, and `CombatTracker.cast_spell` spends the free charge first, falling back
  to a real slot only if `slot_cast` is also true (matching the actual 5e rule for
  these feats). The Spells tab dims any spell `CombatTracker.can_cast` says is
  currently uncastable (no charge left and no slot for its level either), and its
  Notes column shows the live "X/Y left (Long Rest)" count instead of a static
  "1/long rest" string that would go stale the moment it's used once.
- **Limited-use class/race/feat resources (Rage, Bardic Inspiration, Channel
  Divinity, Ki, Second Wind, Relentless Endurance, etc.) are all named actions in
  `data['actions'].{class,race,feat}`, each with its own `limitedUse: {maxUses,
  numberUsed, resetType}` when applicable** - same shape no matter which class or
  race grants it. `resetType` is `1` = Short Rest, `2` = Long Rest (undocumented,
  inferred from known Long-Rest examples - no confirmed Short-Rest sample seen yet,
  so double check if one behaves oddly). `sheet.class_resources` reads this
  generically, same "read the character's own self-describing data" approach as
  Pact Magic detection - this is also why no external ruleset dataset (Open5e or
  otherwise) was needed to support resources for arbitrary classes: D&D Beyond's
  own JSON already carries per-character use-counts, which a static SRD dataset
  couldn't provide anyway.

## Never hardcode per class/race/feat - the character JSON always self-describes

This project's scope is **every character D&D Beyond can produce**, not just the
one it was developed against (a Half-Orc Warlock). Every time something looked
class-specific, the fix turned out to be reading a field that was already there
generically, never adding a name-check or an external ruleset dataset:

| Looked class-specific | Was actually generic | See |
|---|---|---|
| "Warlock has Pact Magic" | any class with a `classFeatures` entry named `"Pact Magic"` | `sheet._has_pact_magic` |
| "Barbarian has Rage" | any class/race/feat action in `data['actions']` with a `limitedUse` block | `sheet.class_resources` |
| "Magic Initiate spells are 1/long rest" | the spell's own `limitedUse` block in `spells.feat`/`spells.race` | `sheet.known_spells` |
| "Half-Orc gets +2 STR" | any `type: "bonus"` modifier with `subType: "<ability>-score"` | `sheet.ability_scores` |

**The rule going forward**: before adding any check that names a specific class,
race, or feat, first look for the generic field the character JSON already uses
for that *kind* of thing (a feature name, a `limitedUse` block, a modifier
`subType` pattern). Reach for Open5e/an SRD dataset only for reference *text*
(what does a rule actually say) - never for tracking, since D&D Beyond's own JSON
is the only source that knows a specific character's current state, and a static
dataset can't provide that regardless. If a real one-off case turns up that
truly has no generic signal, hardcode it as a last resort and say so loudly in a
comment - don't reach for it first.

## Why combat tracking is local-only

Investigated writing back to D&D Beyond (HP damage, spell slots, conditions,
currency, inspiration). Findings (via a reverse-engineered client,
`AlexWorland/dndbeyond-mcp`):

- Auth requires the character owner's own `CobaltSession` cookie exchanged for a
  bearer token at `auth-service.dndbeyond.com/v1/cobalt-token` - a real login flow,
  unlike reads which only need Public visibility.
- Even with auth, **the write endpoints for spell slots, Pact Magic, death saves,
  and currency are already deprecated (404)**. Only HP damage, inspiration,
  conditions, and full rests still work, and D&D Beyond has already broken
  endpoints like these once before without notice.

Given that, `domain/combat.py` + `storage/state_store.py` track HP, spell-slot
usage, and Heroic Inspiration entirely locally, seeded from D&D Beyond's read data
the first time they're touched. "Refresh" (`r`) only re-pulls the character sheet
(level, gear, known spells) and deliberately leaves the local combat overlay alone.
"Long Rest"/"Short Rest" reset the overlay instead of hitting the network.

If write auth ever gets built, the integration point is `domain/combat.py` - it's
already isolated from D&D Beyond I/O, so adding a `sync()` that also POSTs would
not touch `app.py`.

## Keybindings

Vim-flavored, kept intentionally small - anything beyond single-key actions goes
through the command palette (`:`) rather than growing the bindings list. No
duplicate bindings for the same action (e.g. there's no `ctrl+p` alongside `:`).

- `hjkl` - move within the focused table (also arrow keys)
- `[` / `]` - previous/next tab (auto-focuses that tab's table)
- `/` - search the active tab's table (typed inline at the bottom, vim-style -
  see PromptBar below), jumps to first match
- `+` / `-` - heal/damage 1 HP (quick single-point adjustments)
- `r` - refresh character data from D&D Beyond
- `:` - command palette (rest, damage/heal/temp-HP prompts, spell slots, toggle
  inspiration, switch character, jump to tab)
- `q` - quit

Only tables you actually act on (Spells, Inventory, Conditions) are part of the tab
focus chain (`Widget(can_focus=False)` via `ui.widgets.ReferenceTable` for the
rest) - Abilities/Saves/Skills are always-visible reference data with nothing to
select, but are still searchable with `/`.

**PromptBar** (`ui/widgets.py`) is why search/damage/heal/temp-HP/the command
palette don't cover the screen like modal versions would: instead of pushing a
`Screen`, it's a single `Input` docked to the bottom of the layout, hidden
(`display: none`) until `app.open_prompt(mode)` shows it - nvim's `:`/`/` command
line, not Textual's floating command palette. `CharacterSelectScreen` is still a
real `ModalScreen` since switching characters is rare/deliberate enough to warrant
one.

**The command palette (`:`) is our own**, not Textual's built-in one
(`ENABLE_COMMAND_PALETTE = False` on `DndSheetApp`, so `ctrl+p` does nothing) -
`ui/commands.py` exposes plain functions (`list_commands`, `match_commands` using
`textual.fuzzy.Matcher`) that `app.py` renders as PromptBar (mode `"command"`) plus
an `OptionList` (`#command-list`) docked just above it. Typing filters live
(`on_input_changed`); `PromptBar` forwards Up/Down as a `Navigate` message so the
list's highlight moves while the `Input` keeps keyboard focus; Enter runs whichever
option is highlighted. Adding a new command means adding one entry to
`list_commands` - no new UI code needed.

Toast notifications (`self.notify(...)`) are capped at `MAX_NOTIFICATIONS` (5),
oldest dropped first, via an `_on_notify` override - Textual has no built-in limit
and they'd otherwise stack indefinitely if you spam actions.

## Testing approach

**Automated** (`tests/`, run via `uv run pytest`): covers `domain/sheet.py` and
`domain/combat.py`'s pure logic against several different classes - Wizard,
Barbarian, Fighter, and a Warlock/Sorcerer multiclass (see `tests/fixtures.py`) -
plus a few full-app smoke tests (`tests/test_app.py`) that mock the network
(`ddb_client.fetch_character`, `open5e_client.fetch_conditions`) and redirect
`state_store`'s paths into pytest's `tmp_path`, so the suite never touches the
real `.state/` directory or an actual server. **Writing this suite found two real
bugs on the first pass** that manual testing against the one real Warlock
character never surfaced, because both only show up in scenarios that
character's *particular* play history hadn't hit yet:

- `CombatTracker.effective_hp()` returned D&D Beyond's baseline `temp_hp` (not
  the locally-tracked one) for as long as `current_hp` was still untouched - so
  adding temporary HP *before ever taking damage or healing* (a completely
  normal thing to do) silently got overwritten/ignored on the next read. Fixed
  by giving `temp_hp` its own independent `None`-sentinel, not gating both
  values on `current_hp` alone.
- `state_store.load()`/`app.py`'s fresh-state path both did `dict(DEFAULT_STATE)`
  - a **shallow** copy. `DEFAULT_STATE["resources_used"]` (and
  `spell_slots_used`, `spell_uses`) are dicts, so every "fresh" character shared
  and mutated the *same* nested dict object; using a resource on one
  never-before-loaded character would silently bleed into the next
  never-before-loaded character in the same run. Fixed with
  `state_store.default_state()` (a `copy.deepcopy`) - always use that, never
  `dict(DEFAULT_STATE)`, anywhere a fresh state dict is needed (including tests).

There's no official mock dataset for D&D Beyond's unofficial API -
`tests/fixtures.py` hand-builds minimal characters directly from the schema this
project reverse-engineered, populating only the keys `sheet.py`/`combat.py`/
`app.py` actually read (`base_character()` is the shared empty skeleton). When
testing a new class/race/feat interaction, add a fixture function there rather
than inlining one-off JSON in the test file, so later tests can reuse it.

**Manual** (no framework, for TUI behavior `tests/test_app.py` doesn't cover
yet): headless Textual runs work well:

```python
async with app.run_test(size=(170, 50)) as pilot:
    await pilot.pause()
    await app.workers.wait_for_complete()  # data loads via async workers - always wait for this
    ...
```

- `app.query_one(...)` only searches the **base** screen - use `app.screen.query_one(...)`
  for widgets inside a pushed modal.
- To visually sanity-check layout: `app.export_screenshot()` → write the SVG →
  `rsvg-convert -o out.png out.svg` → view the PNG. There's no Nerd Font in that
  render path, so icons show as boxes there even when they'd work in a real terminal.
- `DataTable.update_cell(...)` does **not** resize the column unless you pass
  `update_width=True` - forgetting this truncates any cell that grows wider than
  the column's original content (bit us once with the Conditions "Active" marker).
- `DataTable` defaults to `cursor_type="cell"`, which never fires `RowHighlighted`/
  `RowSelected` - every table in this app uses `cursor_type="row"` specifically so
  those events work (see `ui/widgets.py`).
- **When `export_screenshot()`'s SVG encodes text, spaces between words become
  `&#160;` (non-breaking space) entities, not literal spaces.** A plain
  `grep -o "Go to Conditions tab"` (or any multi-word `re.findall` without
  accounting for this) will never match and gives a false "nothing rendered"
  result. Decode entities (`.replace("&#160;", " ")`) or grep single words before
  concluding content is actually missing - this cost real time chasing a phantom
  bug before the *actual* bug (below) was found.
- **Three or more widgets `dock`-ed to the same screen edge breaks rendering of
  the non-last one(s) once their content scrolls** - confirmed as a genuine
  Textual compositor bug (reproduced in a minimal standalone app, independent of
  this project's code): the widget's own `render_line()` output is correct, and
  `.size`/`.region`/`.scroll_y` all report correctly, but the screen's composited
  output for that region is simply blank past a certain scroll offset. Wrapping
  the docked widgets that don't need to be independently dockable into a single
  container - so only *one* thing (plus whatever else, e.g. `Footer`) is actually
  docked to that edge - fixes it completely. This is why `#command-list` and
  `#prompt-bar` live inside a `#palette` `Vertical` that's the thing actually
  docked to the bottom, alongside `Footer` (2 docked-bottom widgets, not 3). If
  you ever add a third bottom-docked element, wrap it into `#palette` too rather
  than docking it independently.
- Relatedly: `#command-list`'s CSS uses a **fixed** `height: 10` rather than
  `height: auto` - a docked `OptionList` with `auto` height that changes its own
  row count via `clear_options()`/`add_option()` has the *same family* of
  repaint bug (confirmed separately: reported size updates, content doesn't
  render) even before the 3-dock issue above. Don't change it back to `auto`.
- **Any focusable `Input` mounted in `compose()`, even one hidden via
  `display: none`, will be auto-focused on startup** by Textual's default
  `AUTO_FOCUS` behavior, silently swallowing every keystroke typed anywhere in the
  app into its invisible value. This is why `PromptBar` is `can_focus=False` by
  default and only flips `can_focus = True` for the moment it's actually shown
  (`app.open_prompt`/`close_prompt`). If a new always-mounted `Input`-like widget
  gets added and keybindings mysteriously stop firing, check this first.
