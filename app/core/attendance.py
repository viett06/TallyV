"""Versioned workbook conventions and attendance vocabulary."""

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
DEFAULT_RULE_DESCRIPTIONS: dict[str, str] = TEMPLATE["default_rule_descriptions"]
HR_DEMO_SHIFTS: dict[str, dict[str, str]] = TEMPLATE["hr_demo_shifts"]
