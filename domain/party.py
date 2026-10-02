"""Campaign party data: who else is in this character's D&D Beyond campaign,
and a compact summary of each of them. Pure logic - fetching each member's own
sheet happens in the app layer (clients.ddb_client)."""

from . import sheet


def campaign_name(data: dict) -> str | None:
    campaign = data.get("campaign")
    return campaign.get("name") if isinstance(campaign, dict) else None


def party_members(data: dict) -> list[dict]:
    """The *other* characters in this character's campaign, as
    `{"id": str, "name": str, "username": str}`. Empty when the character isn't
    in a campaign or is alone in it. `campaign` is null/absent for a character
    outside any campaign."""
    campaign = data.get("campaign")
    if not isinstance(campaign, dict):
        return []
    own_id = str(data.get("id", ""))
    members, seen = [], set()
    for entry in campaign.get("characters") or []:
        member_id = str(entry.get("characterId", ""))
        if not member_id or member_id == own_id or member_id in seen:
            continue
        seen.add(member_id)
        members.append({
            "id": member_id,
            "name": entry.get("characterName") or "Unknown",
            "username": entry.get("username") or "",
        })
    return members


def summarize_member(data: dict) -> dict:
    """Glanceable stats for one party member's fetched sheet."""
    current, max_hp, temp = sheet.hit_points(data)
    return {
        "name": data["name"],
        "classes": sheet.class_summary(data),
        "level": sheet.total_level(data),
        "hp": current,
        "max_hp": max_hp,
        "temp_hp": temp,
        "ac": sheet.armor_class(data),
        "passive_perception": sheet.passive_perception(data),
        "speed": sheet.speed(data),
    }
