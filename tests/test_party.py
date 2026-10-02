import pytest

from app import DndSheetApp
from clients import ddb_client
from domain import party
from textual.widgets import Static

from .fixtures import base_character, fighter_character, wizard_character
from .test_app import _make_app


def _campaign(own_id, *others):
    return {"name": "Stormwreck", "characters": [
        {"characterId": i, "characterName": f"PC{i}", "username": f"u{i}"} for i in (own_id, *others)
    ]}


def test_no_campaign_means_no_members():
    assert party.party_members(base_character()) == []
    assert party.party_members(base_character(campaign=None)) == []


def test_alone_in_campaign_means_no_members():
    assert party.party_members(base_character(id=1, campaign=_campaign(1))) == []


def test_members_exclude_self_and_dupes():
    data = base_character(id=1, campaign=_campaign(1, 2, 3, 2))
    assert [m["id"] for m in party.party_members(data)] == ["2", "3"]


@pytest.mark.asyncio
async def test_party_panel_hidden_without_campaign(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, wizard_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.query_one("#party-sidebar").display is False


@pytest.mark.asyncio
async def test_party_panel_shows_members_and_tolerates_private(monkeypatch, tmp_path):
    me = wizard_character()
    me["id"], me["campaign"] = 1, _campaign(1, 2, 3)
    app = _make_app(monkeypatch, tmp_path, me)

    def fetch(character_id):
        if character_id == "3":
            raise ddb_client.CharacterFetchError("private")
        return fighter_character() if character_id == "2" else me

    monkeypatch.setattr(ddb_client, "fetch_character", fetch)
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.query_one("#party-sidebar").display is True
        text = str(app.query_one("#party-list", Static).render())
        assert "Fighter" in text and "PC3" in text and "not public" in text
