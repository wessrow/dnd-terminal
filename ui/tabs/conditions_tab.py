"""The Conditions tab: SRD condition reference text from Open5e, with active/
inactive toggled and tracked locally in app.state (D&D Beyond has no concept
of "currently active conditions" in its read API). Conditions are the same
for every character, so this loads once at startup, independent of whichever
character is loaded - not re-fetched on character switch/refresh."""

import asyncio

import requests
from textual.widgets import DataTable, Static, TabPane

from clients import open5e_client
from storage import state_store

from .. import formatting, icons
from ..widgets import VimDataTable


class ConditionsTab(TabPane):
    def __init__(self):
        super().__init__(f"{icons.CONDITIONS} Conditions", id="tab-conditions")
        self.conditions_by_slug: dict[str, dict] = {}
        self._name_col = None
        self._active_col = None

    def compose(self):
        yield VimDataTable(id="conditions")
        yield Static(id="active-effects")
        yield Static(id="condition-detail", classes="detail")

    def on_mount(self) -> None:
        columns = self.query_one("#conditions", DataTable).add_columns("Condition", "Active")
        self._name_col, self._active_col = columns

    async def load(self) -> None:
        table = self.query_one("#conditions", DataTable)
        detail = self.query_one("#condition-detail", Static)
        table.loading = True
        try:
            conditions = await asyncio.to_thread(open5e_client.fetch_conditions)
        except requests.RequestException as exc:
            table.loading = False
            detail.update(f"[bold red]Failed to load conditions from Open5e: {exc}[/bold red]")
            return

        conditions = sorted(conditions, key=lambda c: c["name"])
        self.conditions_by_slug = {c["slug"]: c for c in conditions}
        active_conditions = self.app.state["active_conditions"]
        table.clear()
        for condition in conditions:
            is_active = condition["slug"] in active_conditions
            table.add_row(
                formatting.condition_name_cell(condition["name"], is_active),
                formatting.active_marker(is_active),
                key=condition["slug"],
            )
        table.loading = False

        if conditions:
            detail.update(conditions[0]["desc"])
        self.render_active_effects()
        if self.app.character_data:
            self.app.render_combat_panel()

    def refresh_data(self) -> None:
        """Refreshes every row's active styling from app.state - unlike the
        row-selected toggle handler, this is for bulk changes (e.g. resetting
        to baseline) where there's no single row/cursor to preserve."""
        table = self.query_one("#conditions", DataTable)
        active_conditions = self.app.state["active_conditions"]
        for slug, condition in self.conditions_by_slug.items():
            is_active = slug in active_conditions
            table.update_cell(
                slug, self._name_col, formatting.condition_name_cell(condition["name"], is_active),
                update_width=True,
            )
            table.update_cell(slug, self._active_col, formatting.active_marker(is_active), update_width=True)
        self.render_active_effects()

    def render_active_effects(self) -> None:
        panel = self.query_one("#active-effects", Static)
        active = [
            self.conditions_by_slug[slug]
            for slug in self.app.state["active_conditions"]
            if slug in self.conditions_by_slug
        ]
        if not active:
            panel.update("[dim]No active conditions.[/dim]")
            return
        blocks = [f"[bold red]{c['name']}[/bold red]\n{c['desc']}" for c in active]
        panel.update("\n\n".join(blocks))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if key in self.conditions_by_slug:
            self.query_one("#condition-detail", Static).update(self.conditions_by_slug[key]["desc"])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        active = self.app.state["active_conditions"]
        if key in active:
            active.remove(key)
        else:
            active.append(key)
        state_store.save(self.app.character_id, self.app.state)

        is_active = key in active
        event.data_table.update_cell(
            event.row_key, self._name_col,
            formatting.condition_name_cell(self.conditions_by_slug[key]["name"], is_active),
            update_width=True,
        )
        event.data_table.update_cell(event.row_key, self._active_col, formatting.active_marker(is_active), update_width=True)
        self.render_active_effects()
        self.app.render_combat_panel()
