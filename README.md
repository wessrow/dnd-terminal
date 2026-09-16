# D&D Terminal

A personal terminal UI (built with [Textual](https://github.com/Textualize/textual))
for viewing a D&D Beyond character sheet and tracking combat state - HP, spell
slots, class resources, conditions, inspiration - during a session. Single
character-focused, single user, no server component. Everything you'd track
with pencil marks on a printed sheet, kept in a terminal instead.

![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue)

## Why

D&D Beyond's character sheet is the source of truth for who your character
*is*, but it's clunky to update live at the table for things that change every
round (current HP, which spell slots are spent, whether Rage is up). This app
reads your character from D&D Beyond and layers fast, local, vim-flavored
combat tracking on top - without ever writing back to D&D Beyond.

## Features

- Full character sheet: abilities, saves, skills, AC, HP, attacks, spells,
  class resources, senses, languages - derived generically from D&D Beyond's
  raw JSON, so it works for any class/race/feat combination, not just the one
  it was built against
- Local combat tracking: damage/heal/temp HP, spell slot usage (including Pact
  Magic), class resource usage (Rage, Ki, Channel Divinity, etc.), Heroic
  Inspiration - all overlaid on top of D&D Beyond's baseline and persisted
  locally between sessions
- Familiar tracking (Find Familiar / Pact of the Chain) with monster stat
  blocks pulled from [Open5e](https://open5e.com/)
- SRD condition reference, also from Open5e
- Vim-style keybindings and an inline command palette - no mouse required
- Multiple characters, switchable without restarting

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- A **Nerd Font** in your terminal - the UI uses Font Awesome glyphs
  throughout (see `ui/icons.py`); without one, icons render as boxes
- A D&D Beyond character with its sharing visibility set to **Public**
  (Options → Sharing on the character's D&D Beyond page) - this app reads the
  same unofficial API D&D Beyond's own site uses, which requires public
  visibility instead of a login

## Setup

```bash
git clone <this-repo>
cd dnd-terminal
uv sync
```

Optionally, create a `.env` file with your character's ID so it loads
automatically on first run:

```
DND_CHARACTER_ID=12345678
```

The character ID is the numeric ID in your D&D Beyond character URL
(`https://www.dndbeyond.com/characters/12345678`). If you skip this, or want
to track more than one character, use the in-app character picker (`:` →
"Switch character") - characters you add that way are remembered locally
between runs.

## Running it

```bash
uv run app.py          # the TUI
uv run fetch_test.py   # quick CLI smoke test of the D&D Beyond fetch, no TUI
uv run pytest          # automated tests - no network, no real .state/
```

## Keybindings

Vim-flavored and intentionally small - anything beyond a single-key action
goes through the command palette instead of growing this list.

| Key     | Action                                                        |
|---------|----------------------------------------------------------------|
| `h j k l` (or arrows) | Move within the focused table                    |
| `[` / `]` | Previous / next tab (auto-focuses that tab's table)          |
| `/`     | Search the active tab's table, jumps to first match             |
| `r`     | Refresh character data from D&D Beyond                          |
| `:`     | Command palette                                                 |
| `q`     | Quit                                                             |

The command palette (`:`) covers everything else: rest (short/long), damage /
heal / temp-HP, spending spell slots or class resources, toggling
inspiration, switching characters, jumping to a tab, changing the theme, and
a DANGER reset-to-baseline command.

## How combat tracking works

D&D Beyond's read API works without authentication as long as the character
is Public, but *writing* back (HP, spell slots, conditions) requires the
character owner's own login session, and several of those write endpoints
(spell slots, Pact Magic, death saves, currency) are already deprecated on
D&D Beyond's end regardless. So this app doesn't write to D&D Beyond at all:

- `r` (refresh) re-pulls the character sheet - level, gear, known spells -
  from D&D Beyond, and deliberately leaves your local combat state alone.
- HP, spell-slot usage, class-resource usage, and inspiration are tracked
  entirely locally (`.state/`), seeded from D&D Beyond's data the first time
  each is touched.
- "Short Rest" / "Long Rest" reset the local overlay; they don't touch the
  network.

See `CLAUDE.md` for the full writeup, including why several D&D Beyond fields
(HP, AC, spell slots, proficiencies, weapon attacks, familiars, ...) aren't
where you'd expect them in the raw JSON.

## Project layout

```
app.py              entry point + DndSheetApp (composes the layout, wires events)
fetch_test.py        CLI smoke test, no TUI

clients/             talks to the outside world - nothing else does
  ddb_client.py       D&D Beyond character fetch (unofficial API, read-only)
  open5e_client.py     Open5e SRD conditions + monster stat block fetch

domain/              pure logic - no Textual, no I/O, independently testable
  sheet.py            derives sheet values from raw D&D Beyond JSON
  combat.py           CombatTracker: local HP / spell-slot / resource /
                       inspiration overlay on top of sheet.py's baseline
  familiar.py         familiar summarization + local HP overlay, same split
                       as combat.py but against Open5e instead of D&D Beyond

storage/
  state_store.py       local JSON persistence under .state/: combat state,
                        character registry, app config

ui/                  Textual-specific
  widgets.py           custom table + prompt-bar widgets
  screens.py           the one real modal (character selection)
  commands.py          command palette definitions
  formatting.py        Rich text formatting helpers
  icons.py             Nerd Font glyph constants
  app.tcss             all CSS
```

See `CLAUDE.md` for the detailed architecture notes, D&D Beyond API gotchas,
and testing approach.

## Testing

```bash
uv run pytest
```

Automated tests cover `domain/sheet.py` and `domain/combat.py` against
several classes (Wizard, Barbarian, Fighter, a Warlock/Sorcerer multiclass),
plus a few full-app smoke tests that mock the network and redirect state
storage into a temp directory - the suite never touches the real `.state/`
directory or a live server.

## Status

Personal project, built against - and tested with - real D&D Beyond
characters. Not affiliated with D&D Beyond or Wizards of the Coast.
