"""Modal screens. Character selection is the one interaction rare/deliberate enough
to warrant a full modal - quick in-flow inputs (search, damage/heal/temp HP) use the
non-modal PromptBar instead (see widgets.py) so they don't cover the sheet."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from . import icons
from .widgets import VimDataTable


class CharacterSelectScreen(ModalScreen[str | None]):
    """Pick a previously-used character or type a new D&D Beyond character ID."""

    DEFAULT_CSS = """
    CharacterSelectScreen {
        align: center middle;
    }
    #dialog {
        width: 78;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    #dialog Static.title {
        text-style: bold;
        margin-bottom: 1;
    }
    #dialog VimDataTable {
        height: auto;
        max-height: 10;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "dismiss_none", "Cancel", show=False)]

    def __init__(self, characters: list[dict]):
        super().__init__()
        self.characters = characters

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"{icons.CHARACTER}  Select a Character", classes="title")
            if self.characters:
                table = VimDataTable(id="character-list")
                table.add_columns("Name", "Class", "Character ID")
                for entry in self.characters:
                    table.add_row(entry["name"], entry.get("classes") or "-", entry["id"], key=entry["id"])
                yield table
            yield Input(placeholder="...or paste a D&D Beyond character ID and press Enter", id="character-input")

    def on_mount(self) -> None:
        if self.characters:
            self.query_one("#character-list", VimDataTable).focus()
        else:
            self.query_one("#character-input", Input).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.dismiss(event.row_key.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if value:
            self.dismiss(value)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
