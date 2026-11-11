"""Versioned workbook conventions and classifier vocabulary are data, not code."""

import json
import unicodedata
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "locales" / "attendance.vi.json"
TEMPLATE = json.loads(_TEMPLATE_PATH.read_text(encoding="utf-8"))
SHEET_NAME: str = TEMPLATE["sheet_name"]
EXPORT_SHEET_NAME: str = TEMPLATE["export_sheet_name"]
HEADERS: list[str] = TEMPLATE["headers"]
EXPORT_HEADERS: list[str] = TEMPLATE["export_headers"]
PUNCH_IN: str = TEMPLATE["punch_types"]["check_in"]
PUNCH_OUT: str = TEMPLATE["punch_types"]["check_out"]
PUNCH_NA: str = TEMPLATE["punch_types"]["not_applicable"]
CLASSIFICATION_KEYWORDS: dict[str, list[str]] = TEMPLATE["classification_keywords"]
DEFAULT_RULE_DESCRIPTIONS: dict[str, str] = TEMPLATE["default_rule_descriptions"]
CHARACTER_SUBSTITUTIONS: dict[str, str] = TEMPLATE["character_substitutions"]
HR_DEMO_SHIFTS: dict[str, dict[str, str]] = TEMPLATE["hr_demo_shifts"]


def rule_keywords(category: str, policy: dict) -> list[str]:
    return policy.get("keywords", CLASSIFICATION_KEYWORDS.get(category, []))


def plain(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower().translate(str.maketrans(CHARACTER_SUBSTITUTIONS)))
        if unicodedata.category(c) != "Mn"
    )


def matching_rule_categories(explanation: str, policies: dict[str, dict]) -> list[str]:
    text = " ".join(plain(explanation).split())
    matches = []
    for category, policy in policies.items():
        if category == "UNKNOWN":
            continue
        phrases = [" ".join(plain(word).split()) for word in rule_keywords(category, policy)]
        if any(phrase and phrase in text for phrase in phrases):
            matches.append(category)
    return matches
