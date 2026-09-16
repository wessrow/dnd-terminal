"""End-to-end TUI smoke tests across a few different classes - mocks the network
(ddb_client.fetch_character, open5e_client.fetch_conditions) and redirects
state_store's on-disk paths into pytest's tmp_path, so these run fully offline
and never touch a real .state/ directory."""

import pytest

from app import DndSheetApp
from clients import ddb_client, open5e_client
from storage import state_store
from textual.widgets import DataTable, TabbedContent
from ui import icons
from ui.commands import list_commands
from ui.tabs import FamiliarTab, SpellsTab

from .fixtures import (
    barbarian_character,
    fighter_character,
    multiclass_warlock_sorcerer_character,
    warlock_familiar_character,
    wizard_character,
)

FAKE_CONDITIONS = [{"name": "Prone", "slug": "prone", "desc": "You are prone."}]

FAKE_IMP = {
    "name": "Imp", "size": "Tiny", "type": "Fiend", "subtype": "devil", "alignment": "lawful evil",
    "armor_class": 13, "armor_desc": None, "hit_points": 10, "hit_dice": "3d4+3",
    "speed": {"walk": 20, "fly": 40},
    "strength": 6, "dexterity": 17, "constitution": 13, "intelligence": 11, "wisdom": 12, "charisma": 14,
    "senses": "darkvision 120 ft.", "languages": "Infernal, Common", "challenge_rating": "1",
    "damage_resistances": "", "damage_immunities": "", "condition_immunities": "",
    "actions": [{"name": "Sting", "desc": "Melee Weapon Attack: +5 to hit."}],
    "bonus_actions": None, "reactions": None, "legendary_actions": None,
    "special_abilities": [{"name": "Shapechanger", "desc": "The imp can polymorph."}],
}


def _make_app(monkeypatch, tmp_path, character_data: dict) -> DndSheetApp:
    monkeypatch.setattr(ddb_client, "fetch_character", lambda character_id: character_data)
    monkeypatch.setattr(open5e_client, "fetch_conditions", lambda: FAKE_CONDITIONS)
    monkeypatch.setattr(open5e_client, "fetch_monster", lambda name: FAKE_IMP if name == "Imp" else None)
    monkeypatch.setattr(ddb_client, "get_character_id", lambda: "test-id")
    monkeypatch.setattr(state_store, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state_store, "REGISTRY_PATH", tmp_path / "characters.json")
    monkeypatch.setattr(state_store, "CONFIG_PATH", tmp_path / "config.json")
    return DndSheetApp()


@pytest.mark.asyncio
async def test_wizard_shows_regular_slots_and_no_pact_magic(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, wizard_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        combat_text = str(app.query_one("#combat-rest").render())
        assert "Pact Magic" not in combat_text
        assert "Level 1" in combat_text

        spells = app.query_one("#spells", DataTable)
        names = {app.query_one(SpellsTab).spells_by_key[str(i)]["name"] for i in range(spells.row_count)}
        assert "Fireball" in names


@pytest.mark.asyncio
async def test_barbarian_has_no_spells_but_has_a_rage_resource(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, barbarian_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert app.query_one("#spells", DataTable).row_count == 0

        resources = app.query_one("#resources", DataTable)
        assert resources.row_count == 1
        assert resources.get_row_at(0)[0] == "Rage"

        # using it from the table (not the command palette) works the same way
        resources.focus()
        resources.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        assert resources.get_row_at(0)[1] == "2/3"


@pytest.mark.asyncio
async def test_going_to_skills_tab_focuses_it_so_it_can_be_scrolled(monkeypatch, tmp_path):
    """Regression guard: Skills used to have no entry in TAB_PRIMARY_WIDGET (its
    table was can_focus=False, "nothing to select"), so switching to it from the
    command palette left focus on nothing - and a non-focusable table can't be
    scrolled with the keyboard even when its rows overflow the screen."""
    app = _make_app(monkeypatch, tmp_path, wizard_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        app.goto_tab("tab-spells")
        await pilot.pause()
        app.goto_tab("tab-skills")
        await pilot.pause()

        skills = app.query_one("#skills", DataTable)
        assert app.focused is skills
        assert skills.can_focus


@pytest.mark.asyncio
async def test_spells_tab_is_hidden_for_a_pure_martial(monkeypatch, tmp_path):
    """A Fighter/Rogue/Monk-style character with no spellcasting at all gets no
    Spells tab, rather than an always-empty pane - see sheet.is_spellcaster."""
    app = _make_app(monkeypatch, tmp_path, fighter_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        tabs = app.query_one(TabbedContent)
        assert tabs.get_tab("tab-spells").has_class("-hidden")
        assert "Go to Spells tab" not in [text for text, _ in list_commands(app)]

        # cycling with ] must skip straight past the hidden tab
        app.action_next_tab()
        await pilot.pause()
        assert tabs.active != "tab-spells"


@pytest.mark.asyncio
async def test_spells_tab_reappears_when_switching_to_a_caster(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, fighter_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        tabs = app.query_one(TabbedContent)
        assert tabs.get_tab("tab-spells").has_class("-hidden")

        monkeypatch.setattr(ddb_client, "fetch_character", lambda character_id: wizard_character())
        app.on_character_chosen("other-test-id")
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert not tabs.get_tab("tab-spells").has_class("-hidden")


@pytest.mark.asyncio
async def test_familiar_tab_hidden_without_find_familiar(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, fighter_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        tabs = app.query_one(TabbedContent)
        assert tabs.get_tab("tab-familiar").has_class("-hidden")
        assert "Go to Familiar tab" not in [text for text, _ in list_commands(app)]


@pytest.mark.asyncio
async def test_familiar_tab_shown_for_pact_of_the_chain_warlock(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, warlock_familiar_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        tabs = app.query_one(TabbedContent)
        assert not tabs.get_tab("tab-familiar").has_class("-hidden")
        commands = [text for text, _ in list_commands(app)]
        assert f"{icons.FAMILIAR}  Summon Familiar: Imp" in commands
        assert f"{icons.FAMILIAR}  Summon Familiar: Bat" in commands


@pytest.mark.asyncio
async def test_summoning_a_familiar_loads_its_stat_block_and_tracks_hp(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, warlock_familiar_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        app.summon_familiar("Imp")
        await app.workers.wait_for_complete()
        await pilot.pause()

        header_text = str(app.query_one("#familiar-header").render())
        assert "Imp" in header_text
        assert "10" in header_text  # full HP shown

        app.apply_familiar_damage(4)
        await pilot.pause()
        header_text = str(app.query_one("#familiar-header").render())
        assert "6/10" in header_text

        app.dismiss_familiar()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.query_one(FamiliarTab).monster is None


@pytest.mark.asyncio
async def test_familiar_despawns_and_notifies_when_dropped_to_zero_hp(monkeypatch, tmp_path):
    """RAW: a familiar disappears the moment it drops to 0 HP - this must
    clear the tracked form (not just clamp at 0/10) and tell the player,
    distinctly from an ordinary damage notification."""
    app = _make_app(monkeypatch, tmp_path, warlock_familiar_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        app.summon_familiar("Imp")
        await app.workers.wait_for_complete()
        await pilot.pause()

        app.apply_familiar_damage(100)  # Imp has 10 HP - well past lethal
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert app.state["familiar_form"] is None
        assert app.state["familiar_hp"] is None
        assert app.query_one(FamiliarTab).monster is None
        header_text = str(app.query_one("#familiar-header").render())
        assert "No familiar summoned" in header_text

        despawn_notifications = [n for n in app._notifications if "disappeared" in n.message]
        assert len(despawn_notifications) == 1
        assert despawn_notifications[0].severity == "warning"


@pytest.mark.asyncio
async def test_multiclass_shows_both_pact_magic_and_regular_slots(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, multiclass_warlock_sorcerer_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        combat_text = str(app.query_one("#combat-rest").render())
        assert "Pact Magic" in combat_text
        assert "Level 1" in combat_text


@pytest.mark.asyncio
async def test_single_class_identity_does_not_repeat_the_level_line(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, wizard_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        identity_text = str(app.query_one("#identity").render())
        assert "Level 5 Human Wizard" in identity_text
        assert identity_text.count("Level 5") == 1


@pytest.mark.asyncio
async def test_multiclass_identity_shows_the_class_breakdown_separately(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, multiclass_warlock_sorcerer_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        identity_text = str(app.query_one("#identity").render())
        assert "Level 5 Human" in identity_text
        assert "Warlock 3" in identity_text and "Sorcerer 2" in identity_text


@pytest.mark.asyncio
async def test_reset_command_clears_local_tracking_end_to_end(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, barbarian_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        app.apply_damage(10)
        app.use_resource("Rage")
        assert app.combat.effective_hp()[0] < app.combat.effective_hp()[1]

        app.reset_to_ddb_baseline()
        await pilot.pause()

        current, max_hp, _ = app.combat.effective_hp()
        assert current == max_hp
        resources = app.query_one("#resources", DataTable)
        assert resources.get_row_at(0)[1] == "3/3"


@pytest.mark.asyncio
async def test_switching_characters_does_not_leak_state_between_them(monkeypatch, tmp_path):
    """Regression guard: a fresh CombatTracker/state must be loaded per character,
    not carried over from whichever was loaded before."""
    app = _make_app(monkeypatch, tmp_path, barbarian_character())
    async with app.run_test(size=(170, 50)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.apply_damage(5)
        assert app.combat.effective_hp()[0] < app.combat.effective_hp()[1]

        monkeypatch.setattr(ddb_client, "fetch_character", lambda character_id: wizard_character())
        app.on_character_chosen("other-test-id")
        await app.workers.wait_for_complete()
        await pilot.pause()

        current, max_hp, _ = app.combat.effective_hp()
        assert current == max_hp  # fresh character, full HP, no leftover damage
