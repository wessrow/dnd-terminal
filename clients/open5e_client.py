import requests

CONDITIONS_URL = "https://api.open5e.com/v1/conditions/"
MONSTERS_URL = "https://api.open5e.com/v1/monsters/"

# The 2024 rules renamed a couple of 2014-SRD monsters; Open5e mirrors the
# SRD text (still under its old name) and doesn't expose a "current name"
# alias anywhere - no generic signal distinguishes this, so it's hardcoded as
# a last resort (see CLAUDE.md), not a guess: confirmed by name against a
# real character's Pact of the Chain familiar-form list ("Venomous Snake")
# having no Open5e match under that name, only under "Poisonous Snake".
MONSTER_NAME_ALIASES = {"venomous snake": "poisonous snake"}


def fetch_conditions() -> list[dict]:
    """Returns the SRD conditions (name, desc, slug, ...) from the Open5e API."""
    response = requests.get(CONDITIONS_URL, params={"format": "json", "limit": 50}, timeout=10)
    response.raise_for_status()
    return response.json()["results"]


def fetch_monster(name: str) -> dict | None:
    """Looks up an SRD monster stat block by exact name (case-insensitive) -
    used for familiar/summon reference stat blocks. Returns None if Open5e's
    SRD dataset doesn't have this creature - notably true for a few 2024-only
    monsters (e.g. Sphinx of Wonder, Slaad Tadpole) that aren't in the 5.1 SRD
    Open5e mirrors; callers should treat that as "no reference stat block
    available", not an error. Filtered to `wotc-srd` specifically since
    Open5e also carries same-named monsters from third-party content
    (Tome of Beasts, etc.) under the same `name` filter.
    """
    canonical = MONSTER_NAME_ALIASES.get(name.lower(), name)
    response = requests.get(MONSTERS_URL, params={"format": "json", "name": canonical, "limit": 20}, timeout=10)
    response.raise_for_status()
    for result in response.json()["results"]:
        if result.get("document__slug") == "wotc-srd":
            return result
    return None
