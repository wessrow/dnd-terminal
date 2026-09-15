"""Local combat-tracking overlay: HP and spell-slot state layered on top of D&D
Beyond's read-only character data. Pure logic, no Textual dependency, so it's
testable on its own - the App just owns a CombatTracker per loaded character and
calls state_store.save()/re-renders after each mutation.

D&D Beyond's write API for HP/spell-slots is either unauthenticated-only (read) or
broken for these specific fields (see the write-endpoint research in CLAUDE.md), so
this tracker never talks to the network - it only reads `character_data` as a
baseline and stores deltas in `state` (the dict persisted via state_store).
"""

from . import sheet


class CombatTracker:
    def __init__(self, character_data: dict, state: dict):
        self.character_data = character_data
        self.state = state

    # -- HP ------------------------------------------------------------ #

    def effective_hp(self) -> tuple[int, int, int]:
        """(current, max, temp). Mirrors D&D Beyond's own current HP/temp HP until
        each is first locally touched, so a plain refresh never shows stale tracker
        data. current_hp and temp_hp are tracked independently - e.g. adding temp
        HP before ever taking damage must not fall back to D&D Beyond's (likely 0)
        temp HP on the next read just because current_hp is still untouched."""
        current_baseline, max_hp, temp_baseline = sheet.hit_points(self.character_data)
        current = current_baseline if self.state["current_hp"] is None else min(self.state["current_hp"], max_hp)
        temp = temp_baseline if self.state["temp_hp"] is None else self.state["temp_hp"]
        return current, max_hp, temp

    def apply_damage(self, amount: int) -> tuple[int, int]:
        """Damage eats temporary HP first, then current HP. Returns (current, max)."""
        current, max_hp, temp = self.effective_hp()
        remaining = amount
        if temp > 0:
            absorbed = min(temp, remaining)
            temp -= absorbed
            remaining -= absorbed
        current = max(0, current - remaining)
        self.state["current_hp"] = current
        self.state["temp_hp"] = temp
        return current, max_hp

    def apply_heal(self, amount: int) -> tuple[int, int]:
        """Returns (current, max)."""
        current, max_hp, _ = self.effective_hp()
        current = min(max_hp, current + amount)
        self.state["current_hp"] = current
        return current, max_hp

    def apply_temp_hp(self, amount: int) -> int:
        """Temporary HP doesn't stack - takes the higher value. Returns the new total."""
        _, _, temp = self.effective_hp()
        self.state["temp_hp"] = max(temp, amount)
        return self.state["temp_hp"]

    # -- Heroic Inspiration ------------------------------------------------ #

    def effective_inspiration(self) -> bool:
        """Mirrors D&D Beyond's `inspiration` flag until toggled locally (that write
        endpoint is one of the few that actually still works, but needs the login
        auth this app doesn't have - see CLAUDE.md)."""
        override = self.state["inspiration_override"]
        if override is None:
            return bool(self.character_data["inspiration"])
        return override

    def toggle_inspiration(self) -> bool:
        """Returns the new value."""
        self.state["inspiration_override"] = not self.effective_inspiration()
        return self.state["inspiration_override"]

    # -- Spell slots / Pact Magic ---------------------------------------- #

    def effective_pact_magic(self) -> tuple[int, int] | None:
        """(used, available), or None if this character has no Pact Magic."""
        pact = sheet.pact_magic_slots(self.character_data)
        if not pact:
            return None
        ddb_used, available = pact
        used = self.state["pact_magic_used"]
        return min(available, ddb_used if used is None else used), available

    def effective_spell_slots(self) -> list[tuple[int, int, int]]:
        """[(level, used, available), ...] for regular (non-Pact-Magic) slots."""
        result = []
        for level, ddb_used, available in sheet.spell_slots(self.character_data):
            used = self.state["spell_slots_used"].get(str(level))
            result.append((level, min(available, ddb_used if used is None else used), available))
        return result

    def use_pact_slot(self) -> None:
        pact = self.effective_pact_magic()
        if not pact:
            return
        used, available = pact
        self.state["pact_magic_used"] = min(available, used + 1)

    def restore_pact_slot(self) -> None:
        pact = self.effective_pact_magic()
        if not pact:
            return
        used, _ = pact
        self.state["pact_magic_used"] = max(0, used - 1)

    def use_spell_slot(self, level: int) -> None:
        slots = {lvl: (used, available) for lvl, used, available in self.effective_spell_slots()}
        if level not in slots:
            return
        used, available = slots[level]
        self.state["spell_slots_used"][str(level)] = min(available, used + 1)

    def restore_spell_slot(self, level: int) -> None:
        slots = {lvl: (used, available) for lvl, used, available in self.effective_spell_slots()}
        if level not in slots:
            return
        used, _ = slots[level]
        self.state["spell_slots_used"][str(level)] = max(0, used - 1)

    def effective_spell_charge(self, spell: dict) -> tuple[int, int] | None:
        """(used, available) for a feat/race/feature-granted spell's own
        free-cast-per-rest allowance (e.g. Magic Initiate's 1/long rest), or None
        if this spell doesn't have one (a Class spell, or an at-will cantrip).
        Tracked by `charge_key`, not `name` - two different features can grant a
        same-named spell as two independent charges (see sheet.known_spells)."""
        if not spell["free_cast"] or not spell["max_uses"]:
            return None
        used = self.state["spell_uses"].get(spell["charge_key"], spell["used_baseline"])
        return min(used, spell["max_uses"]), spell["max_uses"]

    def _use_a_slot(self, spell: dict) -> str | None:
        """Spends a Pact Magic or regular slot for `spell`'s level, if one's free.
        Returns the outcome message on success, None if no slot was available."""
        pact = self.effective_pact_magic()
        if pact:
            used, available = pact
            if used < available:
                self.use_pact_slot()
                return f"Cast {spell['name']} - Pact Magic slot used"
            return None

        for level, used, available in sorted(self.effective_spell_slots()):
            if level >= spell["level"] and used < available:
                self.use_spell_slot(level)
                return f"Cast {spell['name']} - Level {level} slot used"
        return None

    def can_cast(self, spell: dict) -> bool:
        """Whether `spell` could actually be cast right now - cantrips always can;
        others need either a free charge left or an available slot of the right
        level. Mirrors cast_spell's logic without spending anything, for the UI to
        gray out spells that can't currently be cast."""
        if spell["level"] == 0:
            return True
        charge = self.effective_spell_charge(spell)
        if charge and charge[0] < charge[1]:
            return True
        if spell["source"] != "Class" and not spell["slot_cast"]:
            return False
        pact = self.effective_pact_magic()
        if pact:
            return pact[0] < pact[1]
        return any(used < available for level, used, available in self.effective_spell_slots() if level >= spell["level"])

    def cast_spell(self, spell: dict) -> str:
        """Spends a charge or slot for casting `spell`, if any is available. Returns
        a human-readable outcome message for the caller to display."""
        if spell["level"] == 0:
            return f"{spell['name']} is a cantrip - no slot needed"

        charge = self.effective_spell_charge(spell)
        if charge:
            used, available = charge
            if used < available:
                self.state["spell_uses"][spell["charge_key"]] = used + 1
                remaining = available - used - 1
                return f"Cast {spell['name']} - {remaining}/{available} free use(s) left"
            if not spell["slot_cast"]:
                return f"No uses of {spell['name']} left (resets on {spell['reset_type']})"
            # exhausted its free charge, but it can also be cast with a real slot

        if spell["source"] != "Class" and not spell["slot_cast"]:
            return f"{spell['name']} isn't slot-tracked (granted by {spell['source'].lower()})"

        message = self._use_a_slot(spell)
        return message or f"No spell slots left for {spell['name']}!"

    # -- Class/race/feat resources (Rage, Ki, Bardic Inspiration, etc.) ---- #

    def effective_resources(self) -> list[dict]:
        """One dict per limited-use resource this character has, whatever class
        or race it comes from - see sheet.class_resources for how these are found."""
        result = []
        for res in sheet.class_resources(self.character_data):
            used = self.state["resources_used"].get(res["name"], res["used"])
            result.append({**res, "used": min(used, res["available"])})
        return result

    def use_resource(self, name: str) -> bool:
        """Returns whether a use was actually spent (False if already at 0 left)."""
        resources = {r["name"]: r for r in self.effective_resources()}
        if name not in resources:
            return False
        r = resources[name]
        if r["used"] >= r["available"]:
            return False
        self.state["resources_used"][name] = r["used"] + 1
        return True

    def restore_resource(self, name: str) -> None:
        resources = {r["name"]: r for r in self.effective_resources()}
        if name not in resources:
            return
        self.state["resources_used"][name] = max(0, resources[name]["used"] - 1)

    # -- Rests ------------------------------------------------------------ #

    def long_rest(self) -> None:
        _, max_hp, _ = sheet.hit_points(self.character_data)
        self.state["current_hp"] = max_hp
        self.state["temp_hp"] = 0
        self.state["pact_magic_used"] = 0
        self.state["spell_slots_used"] = {str(lvl): 0 for lvl, _, _ in sheet.spell_slots(self.character_data)}
        for res in sheet.class_resources(self.character_data):
            self.state["resources_used"][res["name"]] = 0
        for spell in sheet.known_spells(self.character_data):
            if spell["free_cast"]:
                self.state["spell_uses"][spell["charge_key"]] = 0

    def short_rest(self) -> bool:
        """Returns whether there was anything to restore."""
        restored = False
        if sheet.pact_magic_slots(self.character_data):
            self.state["pact_magic_used"] = 0
            restored = True
        for res in sheet.class_resources(self.character_data):
            if res["reset_type"] == "Short Rest":
                self.state["resources_used"][res["name"]] = 0
                restored = True
        for spell in sheet.known_spells(self.character_data):
            if spell["free_cast"] and spell["reset_type"] == "Short Rest":
                self.state["spell_uses"][spell["charge_key"]] = 0
                restored = True
        return restored

    # -- Reset everything back to D&D Beyond's own data ------------------- #

    def reset_to_baseline(self) -> None:
        """Wipes every local override, so the next read of anything falls all the
        way back to whatever D&D Beyond's own data says - the "undo everything
        this session tracked locally" escape hatch. Deliberately does not touch
        `character_data` itself (that's always D&D Beyond's, never local)."""
        self.state["active_conditions"] = []
        self.state["current_hp"] = None
        self.state["temp_hp"] = None
        self.state["pact_magic_used"] = None
        self.state["spell_slots_used"] = {}
        self.state["inspiration_override"] = None
        self.state["resources_used"] = {}
        self.state["spell_uses"] = {}
