import requests

CONDITIONS_URL = "https://api.open5e.com/v1/conditions/"


def fetch_conditions() -> list[dict]:
    """Returns the SRD conditions (name, desc, slug, ...) from the Open5e API."""
    response = requests.get(CONDITIONS_URL, params={"format": "json", "limit": 50}, timeout=10)
    response.raise_for_status()
    return response.json()["results"]
