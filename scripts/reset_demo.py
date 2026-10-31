"""Explicitly destructive reset, limited to the configured local demo."""

import argparse
import shutil

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.demo.catalog import seed


def reset(confirmed):
    if confirmed != "RESET-SYNTHETIC-DEMO":
        raise SystemExit("Reset refused: use --confirm RESET-SYNTHETIC-DEMO. Stop the worker first.")
    with SessionLocal() as db:
        # A running worker holds this advisory lock: never reset underneath processing.
        if not db.scalar(text("SELECT pg_try_advisory_xact_lock(744019)")):
            raise SystemExit("Stop the worker before resetting demo data.")
        db.execute(
            text(
                "TRUNCATE analysis_results, evidence_files, audit_logs, case_versions, attendance_cases, import_batches, attachments, emails, processing_jobs RESTART IDENTITY CASCADE"
            )
        )
        db.commit()
        seed(db)
    # All file paths are UUID-owned artifacts within this application's storage root.
    root = settings.storage_dir.resolve()
    for path in root.iterdir() if root.exists() else []:
        if path.is_file() and (len(path.stem) == 32 or path.parent.name == "demo"):
            path.unlink()
    demo = root / "demo"
    if demo.is_dir():
        shutil.rmtree(demo)
    with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
        response = client.delete(settings.mailpit_url + "/api/v1/messages")
        response.raise_for_status()
    print("Synthetic cases, files, jobs and local Mailpit messages reset. Catalogue and HR account preserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deletes only this local synthetic demo. Stop the worker first.")
    parser.add_argument("--confirm", required=True)
    reset(parser.parse_args().confirm)
