"""Derived character-sheet values computed from the raw D&D Beyond JSON.

The raw API mirrors D&D Beyond's internal data model closely, so most
"obvious" sheet values (ability modifiers, proficiency bonus, HP, AC, skills,
spell slot totals) aren't stored directly and have to be computed the same
way the D&D Beyond web client computes them.
"""

import html
import re

ABILITY_NAMES = {1: "Strength", 2: "Dexterity", 3: "Constitution", 4: "Intelligence", 5: "Wisdom", 6: "Charisma"}
ABILITY_ABBR = {1: "STR", 2: "DEX", 3: "CON", 4: "INT", 5: "WIS", 6: "CHA"}

ALIGNMENTS = {
    1: "Lawful Good", 2: "Neutral Good", 3: "Chaotic Good",
    4: "Lawful Neutral", 5: "True Neutral", 6: "Chaotic Neutral",
    7: "Lawful Evil", 8: "Neutral Evil", 9: "Chaotic Evil",
}

# skill name -> (D&D Beyond modifier subType slug, ability id)
SKILLS = {
    "Acrobatics": ("acrobatics", 2),
    "Animal Handling": ("animal-handling", 5),
    "Arcana": ("arcana", 4),
    "Athletics": ("athletics", 1),
    "Deception": ("deception", 6),
    "History": ("history", 4),
    "Insight": ("insight", 5),
    "Intimidation": ("intimidation", 6),
    "Investigation": ("investigation", 4),
    "Medicine": ("medicine", 5),
    "Nature": ("nature", 4),
    "Perception": ("perception", 5),
    "Performance": ("performance", 6),
    "Persuasion": ("persuasion", 6),
    "Religion": ("religion", 4),
    "Sleight of Hand": ("sleight-of-hand", 2),
    "Stealth": ("stealth", 2),
    "Survival": ("survival", 5),
}

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("</p>", "\n\n").replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()


def total_level(data: dict) -> int:
    return sum(c["level"] for c in data["classes"])


def proficiency_bonus(data: dict) -> int:
    return 2 + (total_level(data) - 1) // 4


def ability_scores(data: dict) -> dict[int, int]:
    """Ability id -> final score, folding in bonus/override stats plus flat
    ability-score modifiers from race/feats. 2024-rules half-feats and some racial
    traits (this character's +2 STR/+1 CON from race, +1 CHA from a feat) show up
    as `type: "bonus"` modifiers with subType `"<ability>-score"`, not in the
    dedicated bonusStats array - miss these and both the score and everything
    derived from it (saves, skills, HP, AC) read low.
    """
    base = {s["id"]: s["value"] for s in data["stats"]}
    bonus = {s["id"]: s["value"] for s in data["bonusStats"] if s["value"]}
    override = {s["id"]: s["value"] for s in data["overrideStats"] if s["value"]}

    score_subtype_to_id = {f"{name.lower()}-score": ability_id for ability_id, name in ABILITY_NAMES.items()}
    modifier_bonus: dict[int, int] = {}
    for mod_list in data["modifiers"].values():
        for m in (mod_list or []):
            if m.get("type") != "bonus":
                continue
            ability_id = score_subtype_to_id.get(m.get("subType"))
            if ability_id is not None and m.get("value"):
                modifier_bonus[ability_id] = modifier_bonus.get(ability_id, 0) + m["value"]

    scores = {}
    for ability_id, base_value in base.items():
        if ability_id in override:
            scores[ability_id] = override[ability_id]
        else:
            scores[ability_id] = base_value + bonus.get(ability_id, 0) + modifier_bonus.get(ability_id, 0)
    return scores


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def format_modifier(modifier: int) -> str:
    return f"+{modifier}" if modifier >= 0 else str(modifier)


def hit_points(data: dict) -> tuple[int, int, int]:
    """Returns (current, max, temporary).

    `baseHitPoints` from the API is just the hit-die contribution - it does NOT
    include the Constitution modifier the D&D Beyond client adds on top (conMod
    per character level), so that has to be applied here too.
    """
    con_mod = ability_modifier(ability_scores(data)[3])
    base_total = data["baseHitPoints"] + con_mod * total_level(data)
    max_hp = data["overrideHitPoints"] or (base_total + (data["bonusHitPoints"] or 0))
    current = max_hp - data["removedHitPoints"]
    temp = data["temporaryHitPoints"] or 0
    return current, max_hp, temp


def armor_class(data: dict) -> int:
    """Computes AC from equipped armor/shield plus Dex, the way D&D Beyond's client does.

    Covers the common case (unarmored, or wearing one armor + optional shield) plus
    flat AC bonuses from feats/items/race. Does NOT special-case class features like
    Unarmored Defense (Barbarian/Monk) since the raw API doesn't flag those distinctly
    from other class features - fine for classes without them, but a caster with
    Unarmored Defense would show low.
    """
    dex_mod = ability_modifier(ability_scores(data)[2])

    equipped_armor = None
    shield_bonus = 0
    for item in data["inventory"]:
        if not item.get("equipped") or item["definition"].get("armorClass") is None:
            continue
        definition = item["definition"]
        if "shield" in (definition.get("type") or "").lower():
            shield_bonus += definition["armorClass"]
        else:
            equipped_armor = definition

    if equipped_armor is None:
        base_ac = 10 + dex_mod
    else:
        armor_type = (equipped_armor.get("type") or "").lower()
        if "light" in armor_type:
            base_ac = equipped_armor["armorClass"] + dex_mod
        elif "medium" in armor_type:
            base_ac = equipped_armor["armorClass"] + min(dex_mod, 2)
        else:
            base_ac = equipped_armor["armorClass"]

    flat_bonus = sum(
        m.get("value") or 0
        for mod_list in data["modifiers"].values()
        for m in (mod_list or [])
        if m.get("type") == "bonus" and m.get("subType") == "armor-class"
    )

    return base_ac + shield_bonus + flat_bonus


def class_summary(data: dict) -> str:
    return ", ".join(f"{c['definition']['name']} {c['level']}" for c in data["classes"])


def alignment_name(data: dict) -> str:
    return ALIGNMENTS.get(data.get("alignmentId"), "Unknown")


def speed(data: dict) -> int:
    return data["race"]["weightSpeeds"]["normal"]["walk"]


def initiative(data: dict) -> int:
    scores = ability_scores(data)
    return ability_modifier(scores[2])


def languages(data: dict) -> list[str]:
    """Languages aren't a dedicated field - they're `type: "language"` modifiers
    scattered across race/class/background/feat/item, named via friendlySubtypeName."""
    names = {
        m["friendlySubtypeName"]
        for mod_list in data["modifiers"].values()
        for m in (mod_list or [])
        if m.get("type") == "language" and m.get("friendlySubtypeName")
    }
    return sorted(names)


def _proficiency_multiplier(data: dict, subtype: str) -> float:
    """Highest proficiency tier granted for a given modifier subType slug.

    0 = none, 0.5 = half proficiency (e.g. Jack of All Trades), 1 = proficient,
    2 = expertise. Modifiers can come from race/class/background/feat/item, and a
    character can be granted the same proficiency from more than one source.
    """
    best = 0.0
    for mod_list in data["modifiers"].values():
        for m in (mod_list or []):
            if m.get("subType") != subtype:
                continue
            if m["type"] == "expertise":
                best = max(best, 2.0)
            elif m["type"] == "proficiency":
                best = max(best, 1.0)
            elif m["type"] == "half-proficiency":
                best = max(best, 0.5)
    return best


def skills(data: dict) -> list[dict]:
    """Returns one dict per skill: name, ability, modifier, proficient, expertise."""
    scores = ability_scores(data)
    prof_bonus = proficiency_bonus(data)
    results = []
    for name, (slug, ability_id) in SKILLS.items():
        multiplier = _proficiency_multiplier(data, slug)
        modifier = ability_modifier(scores[ability_id]) + int(prof_bonus * multiplier)
        results.append(
            {
                "name": name,
                "ability": ABILITY_ABBR[ability_id],
                "modifier": modifier,
                "proficient": multiplier >= 1.0,
                "expertise": multiplier >= 2.0,
            }
        )
    return results


def passive_perception(data: dict) -> int:
    perception = next(s for s in skills(data) if s["name"] == "Perception")
    return 10 + perception["modifier"]


def saving_throws(data: dict) -> list[dict]:
    """Returns one dict per ability: ability, modifier, proficient."""
    scores = ability_scores(data)
    prof_bonus = proficiency_bonus(data)
    results = []
    for ability_id, name in ABILITY_NAMES.items():
        slug = f"{name.lower()}-saving-throws"
        proficient = _proficiency_multiplier(data, slug) >= 1.0
        modifier = ability_modifier(scores[ability_id]) + (prof_bonus if proficient else 0)
        results.append({"ability": ABILITY_ABBR[ability_id], "modifier": modifier, "proficient": proficient})
    return results


def _has_pact_magic(cls: dict) -> bool:
    """Whether this class grants the Pact Magic feature - the actual rules signal
    for "this class's slots work like Warlock slots", rather than hardcoding the
    class name. D&D Beyond doesn't expose a "castingType" flag anywhere, but every
    class's own classFeatures list names its features, and Pact Magic is one of
    them for whichever class has it (core Warlock, or any homebrew/reflavored class
    built the same way) - so this works without needing any external dataset.
    """
    features = cls["definition"].get("classFeatures") or []
    return any(f.get("name") == "Pact Magic" for f in features)


def pact_magic_slots(data: dict) -> tuple[int, int] | None:
    """Returns (used, available), or None if this character has no Pact Magic class."""
    for cls in data["classes"]:
        if not _has_pact_magic(cls):
            continue
        level_slots = cls["definition"]["spellRules"]["levelSpellSlots"][cls["level"]]
        available = sum(count for count in level_slots if count)
        used = sum(slot["used"] for slot in data["pactMagic"])
        return used, available
    return None


def spell_slots(data: dict) -> list[tuple[int, int, int]]:
    """Returns [(spell_level, used, available), ...] summed across every class with
    regular (non-Pact-Magic) spell slots - works for single- or multi-classed
    casters of any class, since it reads each class's own spellRules rather than
    special-casing specific class names."""
    totals = [0] * 9
    for cls in data["classes"]:
        if _has_pact_magic(cls):
            continue
        rules = cls["definition"].get("spellRules")
        if not rules:
            continue
        level_slots = rules["levelSpellSlots"][cls["level"]]
        for i, count in enumerate(level_slots):
            totals[i] += count

    used_by_level = {slot["level"]: slot["used"] for slot in data["spellSlots"]}
    return [
        (level, used_by_level.get(level, 0), available)
        for level, available in enumerate(totals, start=1)
        if available
    ]


RESET_TYPES = {1: "Short Rest", 2: "Long Rest"}


def class_resources(data: dict) -> list[dict]:
    """Limited-use resources (Rage, Bardic Inspiration, Channel Divinity, Ki,
    Sorcery Points, Second Wind, racial traits like Relentless Endurance, etc.),
    read generically from data['actions'] rather than hardcoded per class/race -
    any class/race/feat that grants a named action with a `limitedUse` block shows
    up here automatically. Excludes Pact Magic, which is tracked as slots
    (sheet.pact_magic_slots) rather than a named use-counter.
    """
    resources = []
    seen_names = set()
    for category in ("class", "race", "feat"):
        for action in data["actions"].get(category) or []:
            limited_use = action.get("limitedUse")
            name = action.get("name")
            if not limited_use or not limited_use.get("maxUses") or not name:
                continue
            if name in seen_names or name == "Pact Magic":
                continue
            seen_names.add(name)
            resources.append(
                {
                    "name": name,
                    "used": limited_use.get("numberUsed") or 0,
                    "available": limited_use["maxUses"],
                    "reset_type": RESET_TYPES.get(limited_use.get("resetType"), "Unknown"),
                    "description": strip_html(action.get("description") or action.get("snippet")),
                }
            )
    return resources


def format_spell_level(level: int) -> str:
    if level == 0:
        return "Cantrip"
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(level, f"{level}th")


def known_spells(data: dict) -> list[dict]:
    """Returns one dict per spell the character actually has access to: class spells
    plus anything granted by feats/race (e.g. Magic Initiate, Shadow Touched). D&D
    Beyond stores these in separate places, and feat/race grants can list the same
    spell twice (once per casting mode - e.g. "free once per long rest" vs "using a
    spell slot"), so those are deduped by name here.

    Each dict is pure data (no display strings) so the UI layer can compute live
    "X/Y left" text and gray out unusable spells via combat.CombatTracker, rather
    than baking a static "1/long rest" string in here that goes stale the moment
    it's used once.
    """
    spells = []
    for group in data["classSpells"]:
        for sp in group["spells"]:
            d = sp["definition"]
            spells.append(
                {
                    "name": d["name"],
                    "level": d["level"],
                    "school": d.get("school", ""),
                    "source": "Class",
                    "description": strip_html(d.get("description")),
                    "free_cast": False,
                    "slot_cast": False,
                    "max_uses": None,
                    "used_baseline": 0,
                    "reset_type": None,
                }
            )

    granted: dict[str, dict] = {}
    for source, category in (("Feat", "feat"), ("Race", "race")):
        for sp in data["spells"].get(category) or []:
            d = sp["definition"]
            entry = granted.setdefault(
                d["name"],
                {
                    "level": d["level"],
                    "school": d.get("school", ""),
                    "source": source,
                    "description": strip_html(d.get("description")),
                    "free_cast": False,
                    "slot_cast": False,
                    "max_uses": None,
                    "used_baseline": 0,
                    "reset_type": None,
                },
            )
            limited_use = sp.get("limitedUse")
            if limited_use and limited_use.get("maxUses"):
                entry["free_cast"] = True
                entry["max_uses"] = limited_use["maxUses"]
                entry["used_baseline"] = limited_use.get("numberUsed") or 0
                entry["reset_type"] = RESET_TYPES.get(limited_use.get("resetType"), "Unknown")
            if sp.get("usesSpellSlot"):
                entry["slot_cast"] = True

    for name, info in granted.items():
        spells.append({"name": name, **info})

    spells.sort(key=lambda s: (s["level"], s["name"]))
    return spells


def inventory_items(data: dict) -> list[dict]:
    """Returns one dict per inventory item: name, quantity, equipped, weight, cost, description."""
    items = []
    for item in data["inventory"]:
        d = item["definition"]
        items.append(
            {
                "name": d["name"],
                "quantity": item.get("quantity", 0),
                "equipped": item.get("equipped", False),
                "weight": d.get("weight") or 0,
                "cost": d.get("cost"),
                "description": strip_html(d.get("description")),
            }
        )
    return items


def currency_summary(data: dict) -> str:
    currencies = data["currencies"]
    parts = [f"{currencies[code]} {code}" for code in ("pp", "gp", "ep", "sp", "cp") if currencies.get(code)]
    return ", ".join(parts) if parts else "0 gp"
