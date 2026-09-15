"""Tests for domain/combat.py's CombatTracker - the local HP/spell-slot/resource
overlay - across several different classes, not just the app's original Warlock."""

from domain.combat import CombatTracker
from storage import state_store

from .fixtures import (
    barbarian_character,
    base_character,
    fighter_character,
    granted_spell,
    multiclass_warlock_sorcerer_character,
    wizard_character,
)


def tracker(character_data: dict) -> CombatTracker:
    return CombatTracker(character_data, state_store.default_state())


# -- HP -------------------------------------------------------------------- #

def test_damage_eats_temp_hp_before_current_hp():
    t = tracker(wizard_character())
    t.apply_temp_hp(5)
    current, max_hp = t.apply_damage(8)
    assert t.state["temp_hp"] == 0
    assert current == max_hp - 3  # 8 damage - 5 temp = 3 into current HP


def test_heal_never_exceeds_max_hp():
    t = tracker(wizard_character())
    t.apply_damage(5)
    current, max_hp = t.apply_heal(999)
    assert current == max_hp


def test_temp_hp_does_not_stack_takes_higher_value():
    t = tracker(wizard_character())
    t.apply_temp_hp(5)
    t.apply_temp_hp(3)
    assert t.state["temp_hp"] == 5
    t.apply_temp_hp(10)
    assert t.state["temp_hp"] == 10


# -- Pact Magic vs regular slots stay independent for any character -------- #

def test_use_pact_slot_noop_for_a_class_without_pact_magic():
    t = tracker(wizard_character())
    t.use_pact_slot()  # must not raise even though this Wizard has no Pact Magic
    assert t.effective_pact_magic() is None


def test_multiclass_using_pact_slot_does_not_touch_regular_slots():
    t = tracker(multiclass_warlock_sorcerer_character())
    t.use_pact_slot()
    pact_used, _ = t.effective_pact_magic()
    regular = dict((lvl, used) for lvl, used, _ in t.effective_spell_slots())
    assert pact_used == 1
    assert regular[1] == 0


# -- cast_spell: charge first, then fall back to a slot -------------------- #

def _spell_by_name(character_data: dict, name: str) -> dict:
    from domain import sheet
    return next(s for s in sheet.known_spells(character_data) if s["name"] == name)


def test_cantrip_never_spends_anything():
    data = wizard_character()
    t = tracker(data)
    spell = _spell_by_name(data, "Light")
    message = t.cast_spell(spell)
    assert "no slot needed" in message


def test_class_spell_spends_a_regular_slot_for_a_non_warlock():
    data = wizard_character()
    t = tracker(data)
    spell = _spell_by_name(data, "Mage Armor")  # level 1
    t.cast_spell(spell)
    used_by_level = dict((lvl, used) for lvl, used, _ in t.effective_spell_slots())
    assert used_by_level[1] == 1


def test_free_cast_spell_uses_its_own_charge_before_a_slot():
    data = base_character(
        spells={"feat": [granted_spell("Detect Magic", 1, limited_use={"maxUses": 1, "numberUsed": 0, "resetType": 2})],
                "race": [], "background": [], "class": [], "item": []},
    )
    t = tracker(data)
    spell = _spell_by_name(data, "Detect Magic")
    message = t.cast_spell(spell)
    assert "free use" in message
    assert t.can_cast(spell) is False  # exhausted, and this spell has no slot fallback


def test_free_cast_spell_falls_back_to_a_slot_once_exhausted():
    data = wizard_character()
    data["spells"]["feat"] = [
        granted_spell("Invisibility", 2, limited_use={"maxUses": 1, "numberUsed": 1, "resetType": 2}, uses_spell_slot=True),
    ]
    t = tracker(data)
    spell = _spell_by_name(data, "Invisibility")
    assert t.effective_spell_charge(spell) == (1, 1)  # already exhausted per fixture
    message = t.cast_spell(spell)
    assert "slot used" in message
    used_by_level = dict((lvl, used) for lvl, used, _ in t.effective_spell_slots())
    assert used_by_level[2] == 1


def test_can_cast_false_when_out_of_slots_and_charges():
    data = base_character(
        spells={"feat": [granted_spell("Disguise Self", 1, limited_use={"maxUses": 1, "numberUsed": 1, "resetType": 2})],
                "race": [], "background": [], "class": [], "item": []},
    )
    t = tracker(data)
    spell = _spell_by_name(data, "Disguise Self")
    assert t.can_cast(spell) is False  # no charge left, no slot_cast fallback, no class spell slots either


# -- Class resources: generic use/restore, any class -------------------- #

def test_use_resource_decrements_and_reports_success():
    t = tracker(barbarian_character())
    assert t.use_resource("Rage") is True
    used, available = next((r["used"], r["available"]) for r in t.effective_resources() if r["name"] == "Rage")
    assert (used, available) == (1, 3)


def test_use_resource_fails_once_exhausted():
    t = tracker(fighter_character())  # Second Wind has 1 max use
    assert t.use_resource("Second Wind") is True
    assert t.use_resource("Second Wind") is False


def test_restore_resource_never_goes_below_zero():
    t = tracker(barbarian_character())
    t.restore_resource("Rage")
    used, _ = next((r["used"], r["available"]) for r in t.effective_resources() if r["name"] == "Rage")
    assert used == 0


def test_unknown_resource_name_is_a_safe_noop():
    t = tracker(barbarian_character())
    assert t.use_resource("Not A Real Resource") is False
    t.restore_resource("Not A Real Resource")  # must not raise


def test_two_fresh_trackers_do_not_share_mutable_state():
    """Regression guard: state_store.default_state() must deep-copy - a plain
    dict(DEFAULT_STATE) shallow-copies nested dicts (resources_used etc.), so two
    "fresh" characters would silently share and corrupt each other's usage counts."""
    a = tracker(barbarian_character())
    b = tracker(barbarian_character())
    a.use_resource("Rage")
    used_a, _ = next((r["used"], r["available"]) for r in a.effective_resources() if r["name"] == "Rage")
    used_b, _ = next((r["used"], r["available"]) for r in b.effective_resources() if r["name"] == "Rage")
    assert used_a == 1
    assert used_b == 0


# -- Rests: reset type actually matters, for any class -------------------- #

def test_long_rest_restores_everything_regardless_of_reset_type():
    t = tracker(fighter_character())
    t.use_resource("Second Wind")
    t.use_resource("Action Surge")
    t.apply_damage(5)
    t.long_rest()
    current, max_hp = t.effective_hp()[:2]
    assert current == max_hp
    assert all(r["used"] == 0 for r in t.effective_resources())


def test_short_rest_only_restores_short_rest_resources():
    t = tracker(fighter_character())
    t.use_resource("Second Wind")  # Short Rest
    restored = t.short_rest()
    assert restored is True
    used, _ = next((r["used"], r["available"]) for r in t.effective_resources() if r["name"] == "Second Wind")
    assert used == 0


def test_short_rest_does_not_touch_long_rest_only_resources():
    t = tracker(barbarian_character())  # Rage is Long Rest only
    t.use_resource("Rage")
    restored = t.short_rest()
    used, _ = next((r["used"], r["available"]) for r in t.effective_resources() if r["name"] == "Rage")
    assert used == 1  # untouched by a short rest
    assert restored is False  # nothing this character has resets on a short rest


def test_short_rest_restores_pact_magic_for_any_class_that_has_it():
    t = tracker(multiclass_warlock_sorcerer_character())
    t.use_pact_slot()
    assert t.short_rest() is True
    pact_used, _ = t.effective_pact_magic()
    assert pact_used == 0


# -- Heroic Inspiration ------------------------------------------------ #

def test_inspiration_mirrors_ddb_value_until_toggled():
    data = wizard_character()
    data["inspiration"] = True
    t = tracker(data)
    assert t.effective_inspiration() is True
    t.toggle_inspiration()
    assert t.effective_inspiration() is False
