"""Local JSON persistence for things D&D Beyond doesn't track, or where its write
API is unreliable/unauthenticated in this app: active conditions, in-session HP and
spell-slot tracking, and the list of characters you've loaded before.

This is a *local combat tracker* layered on top of D&D Beyond's read-only data. It
deliberately never writes back to D&D Beyond (see clients/ddb_client.py) - "Refresh"
re-pulls the character sheet (level, gear, etc.) but leaves this local overlay
alone; "Long Rest" / "Short Rest" reset the overlay instead.
"""

import copy
import json
from pathlib import Path

# Project root, not this module's own directory (storage/) - state lives at <root>/.state.
PROJECT_ROOT = Path(__file__).parent.parent
STATE_DIR = PROJECT_ROOT / ".state"
REGISTRY_PATH = STATE_DIR / "characters.json"
CONFIG_PATH = STATE_DIR / "config.json"

DEFAULT_STATE = {
    "active_conditions": [],
    "current_hp": None,  # None until initialized from the D&D Beyond baseline
    "temp_hp": None,  # None until initialized from the D&D Beyond baseline (tracked independently of current_hp)
    "pact_magic_used": None,  # None = not yet touched locally, defer to D&D Beyond's value
    "spell_slots_used": {},  # {"3": 1, ...} spell level (str) -> local used-count override
    "inspiration_override": None,  # None = not yet touched locally, defer to D&D Beyond's value
    "resources_used": {},  # {"Rage": 1, ...} resource name -> local used-count override
    "spell_uses": {},  # {"Detect Magic": 1, ...} spell name -> local used-count override (feat/race free casts)
    "familiar_form": None,  # currently-summoned familiar's form name (e.g. "Imp"), or None
    "familiar_hp": None,  # local current HP for that familiar; None = full (the SRD statblock's own max)
}


def _path(character_id: str) -> Path:
    return STATE_DIR / f"{character_id}.json"


def default_state() -> dict:
    """A fresh copy of DEFAULT_STATE - deep, not shallow, since several values
    (resources_used, spell_slots_used, spell_uses) are mutable dicts. A plain
    `dict(DEFAULT_STATE)` copies the top level only, so every "fresh" character
    would share and mutate the *same* nested dict objects - real bug, caught by
    tests/test_app.py's character-switch isolation test actually missing this
    exact case initially."""
    return copy.deepcopy(DEFAULT_STATE)


def load(character_id: str) -> dict:
    path = _path(character_id)
    state = default_state()
    if path.exists():
        state.update(json.loads(path.read_text()))
    return state


def save(character_id: str, state: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    _path(character_id).write_text(json.dumps(state, indent=2))


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"characters": [], "last_used": None}
    return json.loads(REGISTRY_PATH.read_text())


def remember_character(character_id: str, name: str, classes: str = "") -> None:
    """`classes` is a display string like "Warlock 5" or "Fighter 3, Rogue 2"
    (domain.sheet.class_summary) - stored so CharacterSelectScreen can show it
    without re-fetching every character just to populate the picker."""
    registry = load_registry()
    for entry in registry["characters"]:
        if entry["id"] == character_id:
            entry["name"] = name
            entry["classes"] = classes
            break
    else:
        registry["characters"].append({"id": character_id, "name": name, "classes": classes})
    registry["last_used"] = character_id
    STATE_DIR.mkdir(exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


def load_config() -> dict:
    """App-wide preferences (currently just the Textual theme name), separate from
    any one character's state."""
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text())


def save_config(config: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
