"""Shared constants for tab navigation, kept separate from app.py/commands.py so
neither has to import the other just to see these."""

TAB_IDS = ["tab-skills", "tab-spells", "tab-resources", "tab-inventory", "tab-conditions"]

TAB_LABELS = {
    "tab-skills": "Skills",
    "tab-spells": "Spells",
    "tab-resources": "Resources",
    "tab-inventory": "Inventory",
    "tab-conditions": "Conditions",
}

# Every tab's primary table should grab focus when you switch to them, Skills
# included - a table that never gets focus can't be scrolled with the keyboard.
TAB_PRIMARY_WIDGET = {
    "tab-skills": "#skills",
    "tab-spells": "#spells",
    "tab-resources": "#resources",
    "tab-inventory": "#inventory",
    "tab-conditions": "#conditions",
}

# Every tab's table is searchable with "/", including the read-only ones.
SEARCHABLE_TABS = {
    "tab-skills": "#skills",
    "tab-spells": "#spells",
    "tab-resources": "#resources",
    "tab-inventory": "#inventory",
    "tab-conditions": "#conditions",
}
