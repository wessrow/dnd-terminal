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
    try:
        response = requests.get(
            CHARACTER_SERVICE_URL.format(id=character_id),
            headers=_HEADERS,
            timeout=10,
        )
    except requests.RequestException as exc:
        raise CharacterFetchError(f"Could not reach D&D Beyond to fetch character {character_id}: {exc}") from exc

    # Error responses (404 especially) aren't guaranteed to be JSON, or to
    # carry the usual {"data": {"serverMessage": ...}} shape.
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        payload = {}

    if response.status_code == 404:
        raise CharacterFetchError(
            f"Character {character_id} not found (404). Check the ID - and note "
            "that premade/sample characters aren't served by this API."
        )

    if response.status_code != 200 or not payload.get("success"):
        data = payload.get("data")
        server_message = (
            data.get("serverMessage") if isinstance(data, dict) else None
        ) or payload.get("message") or f"HTTP {response.status_code}"
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
