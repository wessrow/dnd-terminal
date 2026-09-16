"""Local tracking for a summoned familiar (Find Familiar, granted via a Pact
of the Chain invocation or any other source - see sheet.has_familiar).

Reference stat blocks (AC, HP, traits, actions) come from Open5e's SRD
dataset (clients.open5e_client.fetch_monster) - reference *text*, same
reasoning as Conditions. Which form is currently summoned, and that
familiar's current HP, are tracked locally instead - the same "local overlay
on top of a read-only baseline" pattern domain.combat.CombatTracker uses for
the player character's own HP, just for a second, independently-tracked
creature.
"""

from .sheet import ability_modifier

_ABILITY_FIELDS = [
    ("STR", "strength"), ("DEX", "dexterity"), ("CON", "constitution"),
    ("INT", "intelligence"), ("WIS", "wisdom"), ("CHA", "charisma"),
]

# Open5e monster field -> the label shown for that group of entries in the
# Familiar tab's feature table. Every one of these is either null or a list
# of {name, desc} on a real Open5e monster record - same shape regardless of
# which field it's in, so they're normalized into one flat list here.
_FEATURE_FIELDS = [
    ("special_abilities", "Trait"),
    ("actions", "Action"),
    ("bonus_actions", "Bonus Action"),
    ("reactions", "Reaction"),
    ("legendary_actions", "Legendary Action"),
]


def summarize_monster(raw: dict) -> dict:
    """Normalizes an Open5e monster record into the shape the Familiar tab
    renders: formatted speed/size/type lines, ability scores with modifiers
    already computed, and every trait/action/bonus action/reaction/legendary
    action flattened into one list tagged with which kind it is."""
    speed_parts = [
        f"{ft} ft." if kind == "walk" else f"{kind} {ft} ft."
        for kind, ft in (raw.get("speed") or {}).items()
    ]
    abilities = [
        {"ability": abbr, "score": raw[field], "modifier": ability_modifier(raw[field])}
        for abbr, field in _ABILITY_FIELDS
    ]
    features = [
        {"name": entry["name"], "kind": kind, "description": entry.get("desc", "")}
        for field, kind in _FEATURE_FIELDS
        for entry in (raw.get(field) or [])
    ]
    size_type = f"{raw['size']} {raw['type']}"
    if raw.get("subtype"):
        size_type += f" ({raw['subtype']})"

    return {
        "name": raw["name"],
        "size_type": size_type,
        "alignment": raw.get("alignment") or "",
        "armor_class": raw["armor_class"],
        "armor_desc": raw.get("armor_desc") or "",
        "max_hp": raw["hit_points"],
        "hit_dice": raw.get("hit_dice") or "",
        "speed": ", ".join(speed_parts) or "0 ft.",
        "abilities": abilities,
        "senses": raw.get("senses") or "-",
        "languages": raw.get("languages") or "-",
        "challenge_rating": raw.get("challenge_rating") or "-",
        "damage_resistances": raw.get("damage_resistances") or "",
        "damage_immunities": raw.get("damage_immunities") or "",
        "condition_immunities": raw.get("condition_immunities") or "",
        "features": features,
    }


class FamiliarTracker:
    """Local current-HP overlay for whichever familiar form is currently
    summoned. `monster` is the summarize_monster() result for that form (or
    None if no form is summoned yet, or its stat block isn't in the SRD
    dataset) - `state["familiar_hp"]` only ever holds a *local* override,
    same `None`-means-"defer to baseline" convention as CombatTracker's
    `current_hp`/`temp_hp`.
    """

    def __init__(self, monster: dict | None, state: dict):
        self.monster = monster
        self.state = state

    def effective_hp(self) -> tuple[int, int] | None:
        """Returns (current, max), or None if there's no stat block to track
        HP against (no familiar summoned, or an unrecognized 2024-only form)."""
        if not self.monster:
            return None
        max_hp = self.monster["max_hp"]
        current = self.state["familiar_hp"]
        return (max_hp if current is None else current), max_hp

    def apply_damage(self, amount: int) -> tuple[int, int] | None:
        """Returns (current, max) after damage, or None if there's nothing to
        track. Dropping to 0 HP despawns the familiar immediately - per the
        actual Find Familiar rules text ("When the familiar drops to 0 Hit
        Points, it disappears. It reappears after you cast this spell
        again."), not a house rule - so this also clears `familiar_form`/
        `familiar_hp` via dismiss(), the same as the player explicitly
        dismissing it. Callers can tell this happened because
        `state["familiar_form"]` is None afterward."""
        effective = self.effective_hp()
        if not effective:
            return None
        current, max_hp = effective
        current = max(0, current - amount)
        if current == 0:
            self.dismiss()
        else:
            self.state["familiar_hp"] = current
        return current, max_hp

    def apply_heal(self, amount: int) -> tuple[int, int] | None:
        effective = self.effective_hp()
        if not effective:
            return None
        current, max_hp = effective
        current = min(max_hp, current + amount)
        self.state["familiar_hp"] = current
        return current, max_hp

    def summon(self, form: str) -> None:
        self.state["familiar_form"] = form
        self.state["familiar_hp"] = None  # a freshly-summoned familiar starts at full HP

    def dismiss(self) -> None:
        self.state["familiar_form"] = None
        self.state["familiar_hp"] = None
