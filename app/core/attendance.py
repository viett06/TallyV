"""Versioned workbook conventions and classifier vocabulary are data, not code."""

import json
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
CHARACTER_SUBSTITUTIONS: dict[str, str] = TEMPLATE["character_substitutions"]
