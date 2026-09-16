"""The Inventory tab: equipment/gear, purely derived from D&D Beyond data -
no CombatTracker involvement."""

from textual.widgets import DataTable, Static, TabPane

from domain import sheet

from .. import formatting, icons
from ..widgets import VimDataTable


class InventoryTab(TabPane):
    def __init__(self):
        super().__init__(f"{icons.INVENTORY} Inventory", id="tab-inventory")
        self.items_by_key: dict[str, dict] = {}

    def compose(self):
        yield VimDataTable(id="inventory")
        yield Static(id="item-detail", classes="detail")

    def on_mount(self) -> None:
        self.query_one("#inventory", DataTable).add_columns("Item", "Qty", "Equipped", "Weight")

    def populate(self, data: dict) -> None:
        table = self.query_one("#inventory", DataTable)
        table.clear()
        self.items_by_key.clear()
        for i, item in enumerate(sheet.inventory_items(data)):
            key = str(i)
            self.items_by_key[key] = item
            table.add_row(
                item["name"],
                str(item["quantity"]),
                "Yes" if item["equipped"] else "",
                f"{item['weight']} lb",
                key=key,
            )
        if self.items_by_key:
            self.query_one("#item-detail", Static).update(formatting.item_detail(self.items_by_key["0"]))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if key in self.items_by_key:
            self.query_one("#item-detail", Static).update(formatting.item_detail(self.items_by_key[key]))
