"""The Attacks tab: every weapon/feature attack the character can currently
make (see domain.sheet.attacks). Purely derived from D&D Beyond data - no
CombatTracker involvement, unlike most other tabs."""

from textual.widgets import DataTable, Static, TabPane

from domain import sheet

from .. import formatting, icons
from ..widgets import VimDataTable


class AttacksTab(TabPane):
    def __init__(self):
        super().__init__(f"{icons.ATTACKS} Attacks", id="tab-attacks")
        self.attacks_by_key: dict[str, dict] = {}
        self._data: dict | None = None

    def compose(self):
        yield VimDataTable(id="attacks")
        yield Static(id="attack-detail", classes="detail")

    def on_mount(self) -> None:
        self.query_one("#attacks", DataTable).add_columns("Attack", "Type", "To Hit", "Damage", "Range", "Source")

    def refresh_data(self) -> None:
        """Redraw from local state (e.g. Rage toggled) without a re-fetch."""
        if self._data is not None:
            self.populate(self._data)

    def populate(self, data: dict) -> None:
        self._data = data
        combat = getattr(self.app, "combat", None)
        rage_bonus = combat.rage_damage_bonus() if combat else 0
        table = self.query_one("#attacks", DataTable)
        table.clear()
        self.attacks_by_key.clear()
        for i, attack in enumerate(sheet.attacks(data, rage_bonus)):
            key = str(i)
            self.attacks_by_key[key] = attack
            table.add_row(
                attack["name"],
                attack["attack_type"],
                formatting.attack_to_hit_cell(attack["to_hit"], attack["proficient"]),
                f"{attack['damage']} {attack['damage_type']}".strip(),
                attack["range"],
                attack["source"],
                key=key,
            )
        detail = self.query_one("#attack-detail", Static)
        if self.attacks_by_key:
            detail.update(formatting.attack_detail(self.attacks_by_key["0"]))
        else:
            detail.update("[dim]No weapon or feature attacks for this character.[/dim]")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if key in self.attacks_by_key:
            self.query_one("#attack-detail", Static).update(formatting.attack_detail(self.attacks_by_key[key]))
