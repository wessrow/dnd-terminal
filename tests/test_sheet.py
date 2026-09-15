"""Tests for domain/sheet.py across several different classes/races - the point
is proving genericity (nothing keyed off a specific class/race name), not just
re-testing the one Half-Orc Warlock this app happened to be built against."""

from domain import sheet

from .fixtures import (
    barbarian_character,
    base_character,
    class_entry,
    fighter_character,
    granted_spell,
    limited_use_action,
    multiclass_warlock_sorcerer_character,
    wizard_character,
)


# -- ability_scores: flat "bonus" modifiers, not just bonusStats ---------- #

def test_ability_scores_folds_in_flat_bonus_modifiers():
    data = wizard_character()
    scores = sheet.ability_scores(data)
    assert scores[4] == 17  # INT 16 base + 1 racial bonus modifier
    assert scores[1] == 8  # untouched abilities pass through unchanged


def test_ability_scores_defaults_to_base_stats_with_no_modifiers():
    data = base_character()
    scores = sheet.ability_scores(data)
    assert all(score == 10 for score in scores.values())


def test_ability_scores_override_wins_over_base_and_bonus():
    data = base_character(overrideStats=[{"id": 1, "value": 20}] + [{"id": i, "value": None} for i in range(2, 7)])
    assert sheet.ability_scores(data)[1] == 20


# -- hit points: Constitution modifier applied per level ------------------ #

def test_hit_points_adds_con_modifier_per_level_for_any_class():
    data = barbarian_character()  # CON 16 -> +3 mod, level 5
    data["baseHitPoints"] = 44  # hit-die contribution only, per D&D Beyond's API
    current, max_hp, temp = sheet.hit_points(data)
    assert max_hp == 44 + 3 * 5
    assert current == max_hp
    assert temp == 0


# -- Pact Magic detection: by feature name, not by class name ------------- #

def test_pact_magic_detected_by_feature_name_not_class_name():
    data = wizard_character()
    assert sheet.pact_magic_slots(data) is None  # a Wizard has no Pact Magic feature


def test_pact_magic_present_for_any_class_with_the_feature():
    data = multiclass_warlock_sorcerer_character()
    used, available = sheet.pact_magic_slots(data)
    assert (used, available) == (0, 2)  # Warlock level 3 -> 2 slots at level 2 (PACT_MAGIC_SLOTS[3])


def test_class_with_pact_magic_feature_under_a_different_name_still_detected():
    """A homebrew/reflavored class should work identically - detection is purely
    the classFeatures name, never the class's own name."""
    data = base_character(
        classes=[class_entry("Eldritch Adept", 3, class_features=["Pact Magic"],
                              spell_rules={"levelSpellSlots": [[0] * 9, [1] + [0] * 8, [2] + [0] * 8, [0, 2] + [0] * 7]})],
        pactMagic=[{"level": 1, "used": 1}],
    )
    used, available = sheet.pact_magic_slots(data)
    assert (used, available) == (1, 2)


# -- Regular spell slots: summed across every non-Pact-Magic class -------- #

def test_spell_slots_empty_for_a_non_caster():
    data = barbarian_character()
    assert sheet.spell_slots(data) == []
    assert sheet.pact_magic_slots(data) is None


def test_spell_slots_for_a_single_full_caster():
    data = wizard_character()
    slots = {level: (used, available) for level, used, available in sheet.spell_slots(data)}
    assert slots[1] == (0, 4)
    assert slots[2] == (0, 3)
    assert slots[3] == (0, 2)


def test_multiclass_keeps_pact_magic_and_regular_slots_separate():
    data = multiclass_warlock_sorcerer_character()
    pact_used, pact_available = sheet.pact_magic_slots(data)
    regular = {level: (used, available) for level, used, available in sheet.spell_slots(data)}
    assert (pact_used, pact_available) == (0, 2)
    assert regular == {1: (0, 3)}  # only the Sorcerer's slots, Warlock excluded


# -- Class/race/feat resources: generic actions[...].limitedUse ----------- #

def test_class_resources_finds_a_class_action_regardless_of_class():
    data = barbarian_character()
    resources = sheet.class_resources(data)
    assert len(resources) == 1
    assert resources[0]["name"] == "Rage"
    assert resources[0]["available"] == 3
    assert resources[0]["reset_type"] == "Long Rest"


def test_class_resources_reads_short_rest_reset_type():
    data = fighter_character()
    by_name = {r["name"]: r for r in sheet.class_resources(data)}
    assert by_name["Second Wind"]["reset_type"] == "Short Rest"
    assert by_name["Action Surge"]["reset_type"] == "Short Rest"


def test_class_resources_excludes_pact_magic_itself():
    data = base_character(
        classes=[class_entry("Warlock", 1, class_features=["Pact Magic"])],
        actions={"class": [limited_use_action("Pact Magic", max_uses=1)], "race": [], "background": [], "feat": [], "item": []},
    )
    assert sheet.class_resources(data) == []


def test_class_resources_reads_racial_actions_too():
    data = base_character(
        actions={"race": [limited_use_action("Relentless Endurance", max_uses=1, reset_type=2)],
                 "class": [], "background": [], "feat": [], "item": []},
    )
    resources = sheet.class_resources(data)
    assert len(resources) == 1
    assert resources[0]["name"] == "Relentless Endurance"


# -- Saving throws / skills: proficiency from modifiers, not a fixed list - #

def test_saving_throw_proficiency_generic_per_class():
    data = barbarian_character()
    saves = {s["ability"]: s for s in sheet.saving_throws(data)}
    assert saves["STR"]["proficient"] is True
    assert saves["CON"]["proficient"] is True
    assert saves["DEX"]["proficient"] is False


def test_skill_proficiency_from_scattered_modifiers():
    data = wizard_character()
    skills = {s["name"]: s for s in sheet.skills(data)}
    assert skills["Arcana"]["proficient"] is True
    assert skills["Athletics"]["proficient"] is False


# -- known_spells: dedup + structured limited-use data --------------------- #

def test_known_spells_includes_class_and_feat_granted_spells():
    data = wizard_character()
    names = {s["name"] for s in sheet.known_spells(data)}
    assert {"Fireball", "Mage Armor", "Light"} <= names


def test_known_spells_marks_source_correctly():
    data = wizard_character()
    by_name = {s["name"]: s for s in sheet.known_spells(data)}
    assert by_name["Fireball"]["source"] == "Class"
    assert by_name["Light"]["source"] == "Feat"


def test_known_spells_captures_free_cast_limited_use():
    data = base_character(
        spells={"feat": [granted_spell("Disguise Self", 1, limited_use={"maxUses": 1, "numberUsed": 0, "resetType": 2})],
                "race": [], "background": [], "class": [], "item": []},
    )
    spell = sheet.known_spells(data)[0]
    assert spell["free_cast"] is True
    assert spell["max_uses"] == 1
    assert spell["reset_type"] == "Long Rest"


def test_known_spells_dedupes_a_spell_listed_twice_for_two_casting_modes():
    data = base_character(
        spells={
            "feat": [
                granted_spell("Invisibility", 2, limited_use={"maxUses": 1, "numberUsed": 0, "resetType": 2}),
                granted_spell("Invisibility", 2, uses_spell_slot=True),
            ],
            "race": [], "background": [], "class": [], "item": [],
        },
    )
    spells = sheet.known_spells(data)
    assert len(spells) == 1
    assert spells[0]["free_cast"] is True
    assert spells[0]["slot_cast"] is True
