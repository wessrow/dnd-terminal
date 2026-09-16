"""The Familiar tab: whichever Find Familiar form is currently summoned (see
domain.sheet.has_familiar/familiar_forms), its SRD stat block from Open5e, and
its locally-tracked HP (domain.familiar.FamiliarTracker)."""

import asyncio

import requests
from textual.widgets import DataTable, ProgressBar, Static, TabPane

from clients import open5e_client
from domain import familiar

from .. import formatting, icons
from ..widgets import VimDataTable


class FamiliarTab(TabPane):
    def __init__(self):
        super().__init__(f"{icons.FAMILIAR} Familiar", id="tab-familiar")
        self.monster: dict | None = None  # domain.familiar.summarize_monster() of the summoned form
        self.features_by_key: dict[str, dict] = {}

    def compose(self):
        yield Static(id="familiar-header")
        yield ProgressBar(id="familiar-hp-bar", show_percentage=False, show_eta=False)
        yield VimDataTable(id="familiar-features")
        yield Static(id="familiar-feature-detail", classes="detail")

    def on_mount(self) -> None:
        self.query_one("#familiar-features", DataTable).add_columns("Feature", "Kind")

    def _clear(self, message: str) -> None:
        self.query_one("#familiar-header", Static).update(message)
        self.query_one("#familiar-hp-bar", ProgressBar).update(total=1, progress=0)
        self.query_one("#familiar-features", DataTable).clear()
        self.features_by_key.clear()
        self.query_one("#familiar-feature-detail", Static).update("")

    async def load(self, form: str | None) -> None:
        """Fetches the currently-summoned familiar's SRD stat block from
        Open5e, if any form is summoned - separate from the main character
        fetch since it depends on local state (which form, if any) rather
        than D&D Beyond data, and shouldn't block the rest of the sheet."""
        self.monster = None
        if not form:
            self._clear("[dim]No familiar summoned. Use the command palette to summon one.[/dim]")
            return

        table = self.query_one("#familiar-features", DataTable)
        table.loading = True
        try:
            raw = await asyncio.to_thread(open5e_client.fetch_monster, form)
        except requests.RequestException as exc:
            table.loading = False
            self.query_one("#familiar-header", Static).update(
                f"[bold red]Failed to load {form}'s stat block: {exc}[/bold red]"
            )
            return
        table.loading = False

        if raw is None:
            self._clear(
                f"[bold]{form}[/bold]\n[dim]No SRD stat block available for this form "
                "(likely a 2024-only monster not yet in the SRD dataset).[/dim]"
            )
            return

        self.monster = familiar.summarize_monster(raw)
        self.refresh_data()

    def refresh_data(self) -> None:
        """Renders the currently-cached monster summary plus its
        locally-tracked HP - called after load() fetches a stat block, and
        after any local HP change (damage/heal) so it never needs to re-fetch
        Open5e just to reflect a HP change."""
        monster = self.monster
        if not monster:
            return
        current, max_hp = familiar.FamiliarTracker(monster, self.app.state).effective_hp()
        self.query_one("#familiar-header", Static).update(formatting.familiar_header(monster, current, max_hp))
        self.query_one("#familiar-hp-bar", ProgressBar).update(total=max_hp, progress=max(current, 0))

        table = self.query_one("#familiar-features", DataTable)
        table.clear()
        self.features_by_key.clear()
        for i, feature in enumerate(monster["features"]):
            key = str(i)
            self.features_by_key[key] = feature
            table.add_row(feature["name"], feature["kind"], key=key)
        detail = self.query_one("#familiar-feature-detail", Static)
        if monster["features"]:
            first = next(iter(self.features_by_key.values()))
            detail.update(formatting.familiar_feature_detail(first))
        else:
            detail.update("")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if key in self.features_by_key:
            self.query_one("#familiar-feature-detail", Static).update(
                formatting.familiar_feature_detail(self.features_by_key[key])
            )
