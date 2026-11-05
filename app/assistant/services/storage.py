"""Adapt document storage to TallyV's configured private local/S3 storage."""

import hashlib

from app.core.errors import AppError
from app.services import storage


def store_bytes(content):
    return storage.store_bytes(content, ".bin")


def read_bytes(key, expected_hash=None):
    content = storage.read_bytes(key)
    if expected_hash and hashlib.sha256(content).hexdigest() != expected_hash:
        raise AppError(503, "Checksum file không khớp. Vui lòng kiểm tra kho lưu trữ.")
    return content
