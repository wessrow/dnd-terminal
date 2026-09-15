"""Custom DataTable variants, plus PromptBar - the single-line, non-modal input used
for search/damage/heal/temp-HP so those don't cover the screen like a full dialog."""

from textual.binding import Binding
from textual.message import Message
from textual.widgets import DataTable, Input


class VimDataTable(DataTable):
    """A DataTable navigable with hjkl in addition to the arrow keys, with whole-row
    highlighting (so RowHighlighted/RowSelected actually fire - DataTable's default
    "cell" cursor never emits those). Used for tables you interact with: Spells,
    Inventory, Conditions."""

    BINDINGS = [
        Binding("h", "cursor_left", "Left", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("l", "cursor_right", "Right", show=False),
    ]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("cursor_type", "row")
        super().__init__(*args, **kwargs)


class PromptBar(Input, can_focus=False):
    """A single input line that lives permanently in the layout (hidden until
    needed) instead of pushing a modal screen - so search/damage/heal/temp-HP never
    hide the sheet behind them, closer to how the command palette feels.

    can_focus starts False and is only flipped on while visible (app.py's
    open_prompt/close_prompt) - otherwise Textual's default AUTO_FOCUS grabs this
    Input on startup even while hidden, silently swallowing every keypress typed
    anywhere in the app into its (invisible) value.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("up", "navigate('up')", "Up", show=False),
        Binding("down", "navigate('down')", "Down", show=False),
    ]

    class Cancelled(Message):
        pass

    class Navigate(Message):
        def __init__(self, direction: str) -> None:
            super().__init__()
            self.direction = direction

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())

    def action_navigate(self, direction: str) -> None:
        self.post_message(self.Navigate(direction))


class ReferenceTable(VimDataTable):
    """A read-only reference table (Abilities/Saves/Skills): Enter/RowSelected does
    nothing for these (no app.py handler acts on their table ids), but they must
    stay focusable and hjkl-navigable like every other table - Skills in
    particular can have more rows than fit on screen, and a table that can't take
    focus can't be scrolled with the keyboard (bit us for real: "Go to Skills tab"
    left focus on nothing, so hjkl/arrows had no table to scroll)."""
