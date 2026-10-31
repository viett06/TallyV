"""Vietnamese presentation messages, addressed by English semantic keys."""

import json
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parents[1] / "locales" / "vi.json"
MESSAGES: dict[str, str] = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def message(key: str, **values: object) -> str:
    template = MESSAGES[key]
    return template.format(**values) if values else template
