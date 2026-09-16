"""Rich-markup/Text formatting helpers - pure presentation, no app state."""

from rich.text import Text

from domain import sheet

from . import icons


def active_marker(is_active: bool) -> Text:
    return Text(f"{icons.ACTIVE} Active", style="bold green") if is_active else Text("")


def condition_name_cell(name: str, is_active: bool) -> Text:
    """Active conditions get colored so they stand out in the list - easy to forget
    otherwise."""
    return Text(name, style="bold red") if is_active else Text(name)


def proficiency_marker(proficient: bool, expertise: bool) -> Text:
    if expertise:
        return Text(icons.SKILL_PROFICIENT * 2, style="bold gold3")
    if proficient:
        return Text(icons.SKILL_PROFICIENT, style="bold green")
    return Text("")


def spell_notes(spell: dict, charge: tuple[int, int] | None) -> str:
    """Live "X/Y left (Long Rest)"-style notes for a spell - computed from current
    tracker state rather than a static string, so it doesn't go stale the moment
    the spell is actually used.

    "or slot" only makes sense as a fallback *alongside* a free charge (e.g.
    Invisibility: "0/1 left (Long Rest), or slot") - a spell that is ONLY ever
    cast with a slot (a Fiend patron's Fireball, or any regular Class spell)
    gets no note at all, same as a normal Class spell, rather than a lone
    dangling "or slot" with nothing for the "or" to refer to.
    """
    if not charge:
        return ""
    used, available = charge
    note = f"{available - used}/{available} left ({spell['reset_type']})"
    if spell["slot_cast"]:
        note += ", or slot"
    return note


def spell_name_cell(name: str, usable: bool) -> Text:
    """Spells with no charge/slot left to cast them are dimmed - "clearly unusable"
    rather than looking identical to everything else in the list."""
    return Text(name) if usable else Text(name, style="dim")


def spell_detail(spell: dict, charge: tuple[int, int] | None) -> str:
    header = f"[bold]{spell['name']}[/bold] - {sheet.format_spell_level(spell['level'])} {spell['school']}"
    notes = spell_notes(spell, charge)
    if notes:
        header += f" ({notes})"
    return f"{header}\n\n{spell['description'] or '(no description)'}"


def item_detail(item: dict) -> str:
    cost = f"{item['cost']} gp" if item["cost"] else "-"
    header = f"[bold]{item['name']}[/bold]  |  Weight: {item['weight']} lb  |  Cost: {cost}"
    return f"{header}\n\n{item['description'] or '(no description)'}"


def attack_to_hit_cell(to_hit: int, proficient: bool) -> Text:
    """Dims a not-proficient attack's to-hit, same idea as spell_name_cell
    graying out an uncastable spell - a quick "this one's worse" signal."""
    text = sheet.format_modifier(to_hit)
    return Text(text) if proficient else Text(text, style="dim")


def attack_detail(attack: dict) -> str:
    header = (
        f"[bold]{attack['name']}[/bold]  |  {attack['attack_type']}  |  "
        f"To Hit: {sheet.format_modifier(attack['to_hit'])}  |  "
        f"Damage: {attack['damage']} {attack['damage_type']}  |  Range: {attack['range']}"
    )
    return f"{header}\n\n{attack['notes'] or '(no notes)'}"


def resource_detail(resource: dict) -> str:
    remaining = resource["available"] - resource["used"]
    header = f"[bold]{resource['name']}[/bold]  |  {remaining}/{resource['available']} left  |  Resets: {resource['reset_type']}"
    return f"{header}\n\n{resource['description'] or '(no description)'}"
