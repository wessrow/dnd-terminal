"""The Spells tab. Reads app.combat (the CombatTracker) for live usability -
dimmed names and "X/Y left" notes - since spell charges are locally tracked,
not part of the raw D&D Beyond data this tab is populated from."""

from textual.widgets import DataTable, Static, TabPane

from domain import sheet

from .. import formatting, icons
from ..widgets import VimDataTable


class SpellsTab(TabPane):
    def __init__(self):
        super().__init__(f"{icons.SPELLS} Spells", id="tab-spells")
        self.spells_by_key: dict[str, dict] = {}
        self._name_col = None
        self._notes_col = None

    def compose(self):
        yield VimDataTable(id="spells")
        yield Static(id="spell-detail", classes="detail")

    def on_mount(self) -> None:
        columns = self.query_one("#spells", DataTable).add_columns("Spell", "Level", "School", "Source", "Notes")
        self._name_col, _, _, _, self._notes_col = columns

    def populate(self, data: dict) -> None:
        self.spells_by_key.clear()
        for i, spell in enumerate(sheet.known_spells(data)):
            self.spells_by_key[str(i)] = spell
        self.refresh_data(rebuild=True)

    def refresh_data(self, rebuild: bool = False) -> None:
        """Refreshes usability styling (dimmed name + live "X/Y left" notes).
        `rebuild=True` also rebuilds rows from scratch (initial load/character
        switch); otherwise cells are updated in place so the cursor position
        survives casting a spell."""
        combat = self.app.combat
        table = self.query_one("#spells", DataTable)
        if rebuild:
            table.clear()
            for key, spell in self.spells_by_key.items():
                charge = combat.effective_spell_charge(spell)
                table.add_row(
                    formatting.spell_name_cell(spell["name"], combat.can_cast(spell)),
                    sheet.format_spell_level(spell["level"]),
                    spell["school"],
                    spell["source"],
                    formatting.spell_notes(spell, charge),
                    key=key,
                )
            if self.spells_by_key:
                first_spell = next(iter(self.spells_by_key.values()))
                charge = combat.effective_spell_charge(first_spell)
                self.query_one("#spell-detail", Static).update(formatting.spell_detail(first_spell, charge))
        else:
            for key, spell in self.spells_by_key.items():
                charge = combat.effective_spell_charge(spell)
                table.update_cell(
                    key, self._name_col,
                    formatting.spell_name_cell(spell["name"], combat.can_cast(spell)),
                    update_width=True,
                )
                table.update_cell(key, self._notes_col, formatting.spell_notes(spell, charge), update_width=True)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if key in self.spells_by_key:
            spell = self.spells_by_key[key]
            charge = self.app.combat.effective_spell_charge(spell) if self.app.combat else None
            self.query_one("#spell-detail", Static).update(formatting.spell_detail(spell, charge))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        if key in self.spells_by_key:
            self.app.cast_spell(self.spells_by_key[key])
