import sys

from clients import ddb_client
from domain import sheet
from storage import state_store


def print_summary(data: dict) -> None:
    level = sheet.total_level(data)
    current_hp, max_hp, _ = sheet.hit_points(data)

    print(f"{data['name']} - Level {level} {data['race']['fullName']}")
    print(f"Class: {sheet.class_summary(data)}")
    print(f"HP: {current_hp}/{max_hp}")
    print("Ability Scores:")
    scores = sheet.ability_scores(data)
    for ability_id, name in sheet.ABILITY_ABBR.items():
        print(f"  {name}: {scores[ability_id]}")


def main() -> None:
    character_id = ddb_client.get_character_id() or state_store.load_registry()["last_used"]
    if not character_id:
        sys.exit("No character ID configured. Set DND_CHARACTER_ID in .env, or run app.py once to pick one.")
    data = ddb_client.fetch_character_or_exit(character_id)
    print_summary(data)


if __name__ == "__main__":
    main()
