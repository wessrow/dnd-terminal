"""The Resources tab: limited-use class/race/feat resources (Rage, Second
Wind, Channel Divinity, ...), read live from app.combat since usage is
locally tracked, not part of the raw D&D Beyond data."""

from textual.widgets import DataTable, Static, TabPane

from .. import formatting, icons
from ..widgets import VimDataTable


class ResourcesTab(TabPane):
    def __init__(self):
        super().__init__(f"{icons.RESOURCES} Resources", id="tab-resources")
        self.resources_by_name: dict[str, dict] = {}

    def compose(self):
        yield VimDataTable(id="resources")
        yield Static(id="resource-detail", classes="detail")

    def on_mount(self) -> None:
        self.query_one("#resources", DataTable).add_columns("Resource", "Uses", "Reset")

    def refresh_data(self) -> None:
        table = self.query_one("#resources", DataTable)
        table.clear()
        self.resources_by_name.clear()
        for res in self.app.combat.effective_resources():
            self.resources_by_name[res["name"]] = res
            table.add_row(
                res["name"],
                f"{res['available'] - res['used']}/{res['available']}",
                res["reset_type"],
                key=res["name"],
            )
        detail = self.query_one("#resource-detail", Static)
        if self.resources_by_name:
            detail.update(formatting.resource_detail(next(iter(self.resources_by_name.values()))))
        else:
            detail.update("[dim]No tracked resources for this character.[/dim]")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if key in self.resources_by_name:
            self.query_one("#resource-detail", Static).update(formatting.resource_detail(self.resources_by_name[key]))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        if key in self.resources_by_name:
            self.app.use_resource(key)
