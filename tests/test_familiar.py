"""Tests for domain/familiar.py: Open5e monster-record normalization and the
local HP overlay for a summoned familiar."""

from domain import familiar
from storage.state_store import default_state

RAW_IMP = {
    "name": "Imp",
    "size": "Tiny",
    "type": "Fiend",
    "subtype": "devil",
    "alignment": "lawful evil",
    "armor_class": 13,
    "armor_desc": None,
    "hit_points": 10,
    "hit_dice": "3d4+3",
    "speed": {"walk": 20, "fly": 40},
    "strength": 6, "dexterity": 17, "constitution": 13,
    "intelligence": 11, "wisdom": 12, "charisma": 14,
    "senses": "darkvision 120 ft., passive Perception 11",
    "languages": "Infernal, Common",
    "challenge_rating": "1",
    "damage_resistances": "cold",
    "damage_immunities": "fire, poison",
    "condition_immunities": "poisoned",
    "actions": [{"name": "Sting", "desc": "Melee Weapon Attack: +5 to hit."}],
    "bonus_actions": None,
    "reactions": None,
    "legendary_actions": None,
    "special_abilities": [{"name": "Shapechanger", "desc": "The imp can polymorph."}],
}


def test_summarize_monster_normalizes_speed_and_abilities():
    summary = familiar.summarize_monster(RAW_IMP)
    assert summary["name"] == "Imp"
    assert summary["size_type"] == "Tiny Fiend (devil)"
    assert summary["speed"] == "20 ft., fly 40 ft."
    dex = next(a for a in summary["abilities"] if a["ability"] == "DEX")
    assert dex == {"ability": "DEX", "score": 17, "modifier": 3}


def test_summarize_monster_flattens_every_feature_kind():
    summary = familiar.summarize_monster(RAW_IMP)
    kinds = {f["name"]: f["kind"] for f in summary["features"]}
    assert kinds == {"Shapechanger": "Trait", "Sting": "Action"}


def test_summarize_monster_handles_null_feature_lists():
    """bonus_actions/reactions/legendary_actions are null (not []) on most
    monsters - must not blow up flattening them."""
    summary = familiar.summarize_monster(RAW_IMP)
    assert all(f["kind"] != "Reaction" for f in summary["features"])


def test_familiar_tracker_effective_hp_defaults_to_max():
    monster = familiar.summarize_monster(RAW_IMP)
    tracker = familiar.FamiliarTracker(monster, default_state())
    assert tracker.effective_hp() == (10, 10)


def test_familiar_tracker_no_monster_means_no_hp_to_track():
    tracker = familiar.FamiliarTracker(None, default_state())
    assert tracker.effective_hp() is None
    assert tracker.apply_damage(5) is None
    assert tracker.apply_heal(5) is None


def test_familiar_tracker_damage_and_heal_clamp_to_bounds():
    monster = familiar.summarize_monster(RAW_IMP)
    state = default_state()
    tracker = familiar.FamiliarTracker(monster, state)

    assert tracker.apply_damage(4) == (6, 10)
    assert tracker.apply_damage(100) == (0, 10)  # clamped at 0, not negative
    assert tracker.apply_heal(3) == (3, 10)
    assert tracker.apply_heal(100) == (10, 10)  # clamped at max, not overhealed


def test_familiar_tracker_summon_resets_local_hp_to_full():
    state = default_state()
    state["familiar_hp"] = 2  # damaged from a previous familiar
    familiar.FamiliarTracker(None, state).summon("Sprite")
    assert state["familiar_form"] == "Sprite"
    assert state["familiar_hp"] is None  # a fresh summon starts at full HP


def test_familiar_tracker_dismiss_clears_form_and_hp():
    state = default_state()
    state["familiar_form"] = "Imp"
    state["familiar_hp"] = 4
    familiar.FamiliarTracker(None, state).dismiss()
    assert state["familiar_form"] is None
    assert state["familiar_hp"] is None
