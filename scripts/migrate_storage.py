"""Copy DB-referenced local files to S3, verify SHA-256, and retain all source files."""

import argparse
import hashlib
from pathlib import Path

from botocore.exceptions import ClientError
from sqlalchemy import select, text

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Attachment, EvidenceFile
from app.services.storage import LocalStorage, S3Storage, get_s3_storage


def migrate_files(records, source: Path, target: S3Storage, apply: bool = False) -> dict:
    local = LocalStorage(source)
    expected = {}
    for name, sha in records:
        if name in expected and expected[name] != sha:
            raise ValueError("Conflicting hashes for the same stored file")
        expected[name] = sha
    # Preflight the complete source set before uploading anything.
    for name, sha in expected.items():
        if hashlib.sha256(local.read(name)).hexdigest() != sha:
            raise ValueError(f"Local checksum mismatch: {name}")
    copied = existing = 0
    for name, sha in expected.items():
        try:
            remote = target.read(name)
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"NoSuchKey", "404", "NotFound"}:
                raise
            if not apply:
                continue
            target.write(name, local.read(name))
            remote = target.read(name)
            copied += 1
        else:
            existing += 1
        if hashlib.sha256(remote).hexdigest() != sha:
            raise ValueError(f"Remote checksum mismatch: {name}")
    return {"referenced_files": len(expected), "copied": copied, "already_verified": existing, "dry_run": not apply}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=settings.storage_dir)
    parser.add_argument("--apply", action="store_true", help="Upload missing files; default is read-only preflight")
    args = parser.parse_args()
    with SessionLocal() as db:
        if not db.scalar(text("SELECT pg_try_advisory_xact_lock(744019)")):
            raise SystemExit("Stop the worker before migrating storage.")
        records = [
            *db.execute(select(Attachment.path, Attachment.sha256)).all(),
            *db.execute(select(EvidenceFile.path, EvidenceFile.sha256)).all(),
        ]
        print(migrate_files(records, args.source, get_s3_storage(), args.apply))
    print("Database references and local source files preserved. Activate S3 only after successful verification.")


if __name__ == "__main__":
    main()
