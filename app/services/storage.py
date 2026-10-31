import hashlib
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


def store_bytes(content: bytes, suffix: str) -> tuple[str, str]:
    root = settings.storage_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4().hex}{suffix}"
    target = root / name
    target.write_bytes(content)
    return name, hashlib.sha256(content).hexdigest()


def stored_path(name: str) -> Path:
    root = settings.storage_dir.resolve()
    target = (root / name).resolve()
    if target.parent != root:
        raise ValueError("Invalid stored file path")
    return target
