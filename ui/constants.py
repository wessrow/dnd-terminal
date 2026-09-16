"""Shared constants for tab navigation, kept separate from app.py/commands.py so
neither has to import the other just to see these."""

TAB_IDS = [
    "tab-skills", "tab-attacks", "tab-spells", "tab-familiar",
    "tab-resources", "tab-inventory", "tab-conditions",
]

TAB_LABELS = {
    "tab-skills": "Skills",
    "tab-attacks": "Attacks",
    "tab-spells": "Spells",
    "tab-familiar": "Familiar",
    "tab-resources": "Resources",
    "tab-inventory": "Inventory",
    "tab-conditions": "Conditions",
}

# Every tab's primary table should grab focus when you switch to them, Skills
# included - a table that never gets focus can't be scrolled with the keyboard.
TAB_PRIMARY_WIDGET = {
    "tab-skills": "#skills",
    "tab-attacks": "#attacks",
    "tab-spells": "#spells",
    "tab-familiar": "#familiar-features",
    "tab-resources": "#resources",
    "tab-inventory": "#inventory",
    "tab-conditions": "#conditions",
}

# Every tab's table is searchable with "/", including the read-only ones.
SEARCHABLE_TABS = {
    "tab-skills": "#skills",
    "tab-attacks": "#attacks",
    "tab-spells": "#spells",
    "tab-familiar": "#familiar-features",
    "tab-resources": "#resources",
    "tab-inventory": "#inventory",
    "tab-conditions": "#conditions",
}

# Tabs that are hidden entirely for a character who can't use them at all -
# a pure martial has nothing to show under Spells, a character with no way to
# cast Find Familiar has nothing to show under Familiar - rather than a
# permanently empty pane. Value is the DndSheetApp attribute name that gates
# visibility (see DndSheetApp._sync_conditional_tabs / _visible_tab_ids).
CONDITIONAL_TABS = {
    "tab-spells": "is_spellcaster",
    "tab-familiar": "has_familiar",
}
