"""The Skills tab: a single read-only reference table. No interactive
behavior beyond being focusable/scrollable/searchable (Enter is a no-op on a
ReferenceTable - there's nothing to "select" here)."""

from textual.widgets import DataTable, TabPane

from domain import sheet

from .. import formatting, icons
from ..widgets import ReferenceTable


class SkillsTab(TabPane):
    def __init__(self):
        super().__init__(f"{icons.SKILLS} Skills", id="tab-skills")

    def compose(self):
        yield ReferenceTable(id="skills")

    def on_mount(self) -> None:
        self.query_one("#skills", DataTable).add_columns("Skill", "Ability", "Mod", "")

    def populate(self, data: dict) -> None:
        table = self.query_one("#skills", DataTable)
        table.clear()
        for skill in sheet.skills(data):
            table.add_row(
                skill["name"],
                skill["ability"],
                sheet.format_modifier(skill["modifier"]),
                formatting.proficiency_marker(skill["proficient"], skill["expertise"]),
            )
