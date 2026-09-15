import os
import sys

import requests
from dotenv import load_dotenv

CHARACTER_SERVICE_URL = "https://character-service.dndbeyond.com/character/v5/character/{id}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}


class CharacterFetchError(Exception):
    pass


def get_character_id() -> str | None:
    """Character ID from .env, if set. Returns None otherwise - callers should
    fall back to the locally-remembered character registry (see state_store.py)."""
    load_dotenv()
    return os.environ.get("DND_CHARACTER_ID")


def fetch_character(character_id: str) -> dict:
    response = requests.get(
        CHARACTER_SERVICE_URL.format(id=character_id),
        headers=_HEADERS,
        timeout=10,
    )
    payload = response.json()

    if response.status_code != 200 or not payload.get("success"):
        server_message = payload.get("data", {}).get("serverMessage", "unknown error")
        raise CharacterFetchError(
            f"Failed to fetch character {character_id}: {server_message}\n"
            "Check that the character's sharing visibility is set to Public "
            "in D&D Beyond (Character Sheet -> Options -> Privacy)."
        )

    return payload["data"]


def fetch_character_or_exit(character_id: str) -> dict:
    try:
        return fetch_character(character_id)
    except CharacterFetchError as exc:
        sys.exit(str(exc))
