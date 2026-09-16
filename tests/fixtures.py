"""Minimal, hand-built D&D Beyond character JSON fixtures for a handful of
different classes/races, so domain/sheet.py and domain/combat.py get exercised
against more than just the one Half-Orc Warlock this app was developed against.

There's no official mock dataset for D&D Beyond's unofficial API, so these are
built by hand from the real schema this project reverse-engineered (see
CLAUDE.md's "D&D Beyond API" section) - only the keys sheet.py/combat.py actually
read are populated; everything else is a minimal-but-valid placeholder.

Standard 5e spell slot progressions, hardcoded here as plain data (NOT read by
the app - these represent what a real class's spellRules.levelSpellSlots table
looks like, for building realistic fixtures only).
"""

FULL_CASTER_SLOTS = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],  # level 0 (unused - characters start at 1)
    [2, 0, 0, 0, 0, 0, 0, 0, 0],  # 1
    [3, 0, 0, 0, 0, 0, 0, 0, 0],  # 2
    [4, 2, 0, 0, 0, 0, 0, 0, 0],  # 3
    [4, 3, 0, 0, 0, 0, 0, 0, 0],  # 4
    [4, 3, 2, 0, 0, 0, 0, 0, 0],  # 5
]

HALF_CASTER_SLOTS = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],  # 0
    [0, 0, 0, 0, 0, 0, 0, 0, 0],  # 1 (half-casters get no slots at level 1)
    [2, 0, 0, 0, 0, 0, 0, 0, 0],  # 2
    [3, 0, 0, 0, 0, 0, 0, 0, 0],  # 3
    [3, 0, 0, 0, 0, 0, 0, 0, 0],  # 4
    [4, 2, 0, 0, 0, 0, 0, 0, 0],  # 5
]

PACT_MAGIC_SLOTS = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],  # 0
    [1, 0, 0, 0, 0, 0, 0, 0, 0],  # 1
    [2, 0, 0, 0, 0, 0, 0, 0, 0],  # 2
    [0, 2, 0, 0, 0, 0, 0, 0, 0],  # 3
    [0, 2, 0, 0, 0, 0, 0, 0, 0],  # 4
    [0, 0, 2, 0, 0, 0, 0, 0, 0],  # 5
]


def base_character(**overrides) -> dict:
    """A minimal-but-valid character with 10 in every ability, no class, no
    features - the empty skeleton every fixture below starts from."""
    base = {
        "name": "Test Character",
        "stats": [{"id": i, "name": None, "value": 10} for i in range(1, 7)],
        "bonusStats": [{"id": i, "name": None, "value": None} for i in range(1, 7)],
        "overrideStats": [{"id": i, "name": None, "value": None} for i in range(1, 7)],
        "modifiers": {"race": [], "class": [], "background": [], "feat": [], "item": [], "condition": []},
        "baseHitPoints": 10,
        "bonusHitPoints": None,
        "overrideHitPoints": None,
        "removedHitPoints": 0,
        "temporaryHitPoints": 0,
        "inventory": [],
        "classes": [],
        "race": {"fullName": "Human", "weightSpeeds": {"normal": {"walk": 30}}},
        "background": {"definition": {"name": "Folk Hero"}},
        "alignmentId": 5,
        "inspiration": False,
        "deathSaves": {"successCount": 0, "failCount": 0, "isStabilized": False},
        "pactMagic": [],
        "spellSlots": [],
        "classSpells": [],
        "spells": {"race": [], "class": [], "background": [], "feat": [], "item": []},
        "actions": {"race": [], "class": [], "background": [], "feat": [], "item": []},
        "currencies": {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0},
    }
    base.update(overrides)
    return base


def ability_score_bonus_modifier(ability_subtype: str, value: int, source: str = "race") -> dict:
    """A flat ability-score-increase modifier, e.g. from a racial trait or
    half-feat - see CLAUDE.md, these do NOT show up in bonusStats."""
    return {"type": "bonus", "subType": f"{ability_subtype}-score", "value": value, "friendlySubtypeName": ""}


def proficiency_modifier(subtype: str, kind: str = "proficiency") -> dict:
    """A skill/save proficiency modifier (kind: proficiency/expertise/half-proficiency)."""
    return {"type": kind, "subType": subtype, "value": None}


def class_feature(name: str) -> dict:
    return {"name": name}


def feature_action(name: str, description: str) -> dict:
    """A plain (non-limited-use) named action, e.g. an invocation - what
    sheet.familiar_special_forms reads its [monsters] tags from."""
    return {"name": name, "description": description}


def limited_use_action(name: str, max_uses: int, used: int = 0, reset_type: int = 2, description: str = "") -> dict:
    """A named action with a limitedUse block - the generic shape behind Rage,
    Second Wind, Bardic Inspiration, Relentless Endurance, Magical Cunning, etc."""
    return {
        "name": name,
        "description": description,
        "limitedUse": {"maxUses": max_uses, "numberUsed": used, "resetType": reset_type},
    }


def class_entry(name: str, level: int, class_features: list[str] = (), spell_rules: dict | None = None,
                 can_cast_spells: bool | None = None, subclass_can_cast_spells: bool = False) -> dict:
    """`can_cast_spells` defaults to True whenever spell_rules is given (the
    common case - a real caster). Pass `can_cast_spells=False` explicitly to
    model real D&D Beyond behavior for non-caster subclasses: a Fighter's
    *class* definition always carries a populated spellRules table (the
    Eldritch Knight progression) even when the character picked a non-casting
    subclass like Champion - `canCastSpells` (class or subclass) is the actual
    gate, not whether spellRules happens to be present. See sheet.spell_slots."""
    if can_cast_spells is None:
        can_cast_spells = spell_rules is not None
    return {
        "level": level,
        "definition": {
            "name": name,
            "classFeatures": [class_feature(f) for f in class_features],
            "spellRules": spell_rules,
            "canCastSpells": can_cast_spells,
        },
        "subclassDefinition": {"canCastSpells": subclass_can_cast_spells},
    }


def spell_rules(level_slots: list[list[int]]) -> dict:
    return {"levelSpellSlots": level_slots}


def class_spell(name: str, level: int, school: str = "Evocation", description: str = "") -> dict:
    return {"definition": {"name": name, "level": level, "school": school, "description": description}}


def granted_spell(name: str, level: int, school: str = "Illusion", description: str = "",
                   limited_use: dict | None = None, uses_spell_slot: bool = False, component_id: int = 1) -> dict:
    """A feat/race/class-feature-granted spell entry (data['spells']['feat'/'race'/'class']).
    component_id identifies which feature granted it - D&D Beyond repeats the same
    componentId across a grant's multiple casting-mode entries (dedupe key), but
    two independent features granting a same-named spell get different ids."""
    entry = {
        "definition": {"name": name, "level": level, "school": school, "description": description},
        "usesSpellSlot": uses_spell_slot,
        "componentId": component_id,
    }
    if limited_use:
        entry["limitedUse"] = limited_use
    return entry


def sense_modifier(name: str, range_ft: int) -> dict:
    """A special sense (Darkvision, Blindsight, etc.) - a `type: "set-base"` modifier."""
    return {"type": "set-base", "subType": name, "friendlySubtypeName": name.title(), "value": range_ft}


# -- Concrete fixtures --------------------------------------------------- #

def wizard_character() -> dict:
    """A level 5 single-class Wizard: standard full-caster slots, no Pact Magic,
    a feat-granted cantrip with no limited use, and a racial ability bonus."""
    return base_character(
        stats=[
            {"id": 1, "value": 8}, {"id": 2, "value": 14}, {"id": 3, "value": 12},
            {"id": 4, "value": 16}, {"id": 5, "value": 10}, {"id": 6, "value": 10},
        ],
        modifiers={
            "race": [ability_score_bonus_modifier("intelligence", 1)],
            "class": [
                proficiency_modifier("intelligence-saving-throws"),
                proficiency_modifier("wisdom-saving-throws"),
                proficiency_modifier("arcana"),
            ],
            "background": [], "feat": [], "item": [], "condition": [],
        },
        classes=[
            class_entry("Wizard", 5, class_features=["Spellcasting", "Arcane Recovery"],
                        spell_rules=spell_rules(FULL_CASTER_SLOTS)),
        ],
        spellSlots=[{"level": i, "used": 0} for i in range(1, 4)],
        classSpells=[{"characterClassId": 1, "spells": [
            class_spell("Fireball", 3, "Evocation"),
            class_spell("Mage Armor", 1, "Abjuration"),
        ]}],
        spells={"feat": [granted_spell("Light", 0, "Evocation")], "race": [], "background": [], "class": [], "item": []},
    )


def barbarian_character() -> dict:
    """A level 5 single-class Barbarian: no spellcasting at all, Rage as a
    Long-Rest resource. Exercises "no caster" paths (pact_magic_slots and
    spell_slots must both come back empty) and a non-Warlock class resource."""
    return base_character(
        stats=[
            {"id": 1, "value": 18}, {"id": 2, "value": 14}, {"id": 3, "value": 16},
            {"id": 4, "value": 8}, {"id": 5, "value": 10}, {"id": 6, "value": 8},
        ],
        modifiers={
            "race": [], "background": [], "feat": [], "item": [], "condition": [],
            "class": [
                proficiency_modifier("strength-saving-throws"),
                proficiency_modifier("constitution-saving-throws"),
                proficiency_modifier("athletics"),
            ],
        },
        classes=[
            class_entry("Barbarian", 5, class_features=["Rage", "Extra Attack", "Fast Movement"]),
        ],
        actions={
            "class": [limited_use_action("Rage", max_uses=3, used=0, reset_type=2,
                                          description="Bonus action to enter a battle fury.")],
            "race": [], "background": [], "feat": [], "item": [],
        },
    )


def fighter_character() -> dict:
    """A level 5 single-class Fighter (Champion subclass, no casting): Second Wind
    as a Short-Rest resource - the generic resource path's other reset type
    (Rage/Warlock above are both Long Rest). Also models a real D&D Beyond
    quirk: Fighter's class definition carries a populated spellRules table (the
    Eldritch Knight progression) even for a non-casting subclass like this one -
    can_cast_spells=False is what should suppress it, not the absence of
    spellRules (see sheet.spell_slots / test_spell_slots_ignores_a_non_caster_..)."""
    return base_character(
        stats=[
            {"id": 1, "value": 16}, {"id": 2, "value": 14}, {"id": 3, "value": 14},
            {"id": 4, "value": 10}, {"id": 5, "value": 12}, {"id": 6, "value": 8},
        ],
        classes=[
            class_entry("Fighter", 5, class_features=["Second Wind", "Action Surge", "Extra Attack"],
                        spell_rules=spell_rules([[0] * 9] * 3 + [[2, 0, 0, 0, 0, 0, 0, 0, 0]] * 3),
                        can_cast_spells=False),
        ],
        actions={
            "class": [
                limited_use_action("Second Wind", max_uses=1, used=0, reset_type=1,
                                    description="Bonus action to regain hit points."),
                limited_use_action("Action Surge", max_uses=1, used=0, reset_type=1),
            ],
            "race": [], "background": [], "feat": [], "item": [],
        },
    )


def warlock_familiar_character() -> dict:
    """A level 5 Warlock with the Pact of the Chain invocation: Find Familiar
    granted via spells.class (the invocation's free-cast grant, same shape as
    a real character's), plus the invocation's own action carrying its
    expanded familiar-form list as [monsters] bbcode tags in its description -
    the exact format confirmed against a real character's D&D Beyond JSON
    (see CLAUDE.md). Exercises sheet.has_familiar/familiar_forms end to end."""
    return base_character(
        stats=[
            {"id": 1, "value": 8}, {"id": 2, "value": 12}, {"id": 3, "value": 14},
            {"id": 4, "value": 10}, {"id": 5, "value": 10}, {"id": 6, "value": 16},
        ],
        classes=[
            class_entry("Warlock", 5, class_features=["Pact Magic"], spell_rules=spell_rules(PACT_MAGIC_SLOTS)),
        ],
        pactMagic=[{"level": 1, "used": 0}, {"level": 2, "used": 0}],
        spells={
            "class": [
                granted_spell(
                    "Find Familiar", 1, "Conjuration", component_id=99,
                    description=(
                        "You gain the service of a familiar, a spirit that takes an animal form you choose: "
                        "Bat, Cat, Frog, Hawk, Lizard, Octopus, Owl, Rat, Raven, Spider, or Weasel."
                    ),
                ),
            ],
            "feat": [], "race": [], "background": [], "item": [],
        },
        actions={
            "class": [
                feature_action(
                    "Pact of the Chain: Attack",
                    "You learn the Find Familiar spell. When you cast the spell, you choose one of the normal "
                    "forms for your familiar or one of the following special forms: [monsters]Imp[/monsters], "
                    "[monsters]Pseudodragon[/monsters], [monsters]Quasit[/monsters], [monsters]Sprite[/monsters].",
                ),
            ],
            "race": [], "background": [], "feat": [], "item": [],
        },
    )


def multiclass_warlock_sorcerer_character() -> dict:
    """A level 3 Warlock / level 2 Sorcerer multiclass: Pact Magic AND regular
    spell slots must both come back populated and *separately* tracked - the
    scenario that would break if Pact Magic detection were name-based and only
    checked the character's "primary" class."""
    return base_character(
        stats=[
            {"id": 1, "value": 8}, {"id": 2, "value": 12}, {"id": 3, "value": 14},
            {"id": 4, "value": 10}, {"id": 5, "value": 10}, {"id": 6, "value": 16},
        ],
        classes=[
            class_entry("Warlock", 3, class_features=["Pact Magic"], spell_rules=spell_rules(PACT_MAGIC_SLOTS)),
            class_entry("Sorcerer", 2, class_features=["Font of Magic"], spell_rules=spell_rules(FULL_CASTER_SLOTS)),
        ],
        pactMagic=[{"level": 1, "used": 0}, {"level": 2, "used": 0}],
        spellSlots=[{"level": 1, "used": 0}],
    )
