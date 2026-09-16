"""One module per main-tab TabPane - each owns its own widgets' compose/
populate/render and any event handling purely local to that tab (nothing
beyond its own table/detail panel). Cross-cutting concerns (the CombatTracker,
local state, the sidebar combat panel) stay app.py's job - a tab reaches
`self.app.<thing>` for those rather than duplicating them; see CLAUDE.md."""

from .attacks_tab import AttacksTab
from .conditions_tab import ConditionsTab
from .familiar_tab import FamiliarTab
from .inventory_tab import InventoryTab
from .resources_tab import ResourcesTab
from .skills_tab import SkillsTab
from .spells_tab import SpellsTab

__all__ = [
    "AttacksTab",
    "ConditionsTab",
    "FamiliarTab",
    "InventoryTab",
    "ResourcesTab",
    "SkillsTab",
    "SpellsTab",
]
