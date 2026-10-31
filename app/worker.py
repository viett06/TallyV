"""Durable PostgreSQL job queue; one worker, leases, bounded retries, idempotent jobs."""

import logging
import signal
import time
from datetime import timedelta

from app.core.errors import AppError, MailboxReauthenticationRequired
from app.core.i18n import message
from app.core.time import utcnow
from app.crud import cases as case_crud
from app.crud import jobs as job_crud
from app.crud import outlook as outlook_crud
from app.crud.emails import get_email
from app.crud.jobs import enqueue
from app.db.session import SessionLocal
from app.services import mailbox
from app.services.analysis import analyze
from app.services.imports import process_email

logger = logging.getLogger("tallyv.worker")
running = True


def run_one():
    with SessionLocal() as db:
        job = job_crud.claim_next(db)
        if job is None:
            return False
        job_id = job.id
        db.commit()
    try:
        with SessionLocal() as db:
            job = job_crud.get_job(db, job_id)
            if job.kind == "SYNC":
                payload = dict(job.payload)
                if payload.get("mode") == "rescan":
                    result = mailbox.synchronize_mailbox(
                        db, restart=not payload.get("started_at"), lookback_days=payload["lookback_days"]
                    )
                else:
                    result = mailbox.synchronize_mailbox(db)
                summary = payload.get("summary", {})
                payload["summary"] = {
                    key: summary.get(key, 0) + result.get(key, 0) for key in ("scanned", "matched", "new", "existing")
                }
                payload.setdefault("started_at", utcnow().isoformat())
                if not result.get("has_more"):
                    payload["completed_at"] = utcnow().isoformat()
                job.payload = payload
                if result.get("has_more"):
                    job.status, job.attempts, job.locked_at, job.error = "PENDING", 0, None, None
                    job.available_at = utcnow()
                    db.commit()
                    return True
            elif job.kind == "DEMO":
                from app.demo.generate import run

                run(**job.payload)
                enqueue(db, "SYNC", "mailbox-sync", {})
            elif job.kind == "IMPORT_EMAIL":
                process_email(db, job.payload["email_id"])
            elif job.kind == "ANALYZE":
                analyze(db, job.payload["version_id"])
            else:
                raise ValueError("Unknown job kind")
            job.status, job.error, job.locked_at = "DONE", None, None
            db.commit()
    except Exception as error:
        # Log IDs and exception classes only; no email or evidence content.
        logger.warning("job_id=%s error_type=%s", job_id, type(error).__name__)
        with SessionLocal() as db:
            job = job_crud.get_job(db, job_id)
            job.status = "FAILED" if job.attempts >= job.max_attempts else "PENDING"
            job.error = (
                error.detail
                if isinstance(error, AppError) and isinstance(error.detail, str)
                else message("jobs.processing_failed", value0=type(error).__name__)
            )
            if job.kind == "SYNC" and isinstance(error, MailboxReauthenticationRequired):
                connection = outlook_crud.get_connection(db, for_update=True)
                if connection and connection.status == "CONNECTED":
                    connection.status = "REAUTH_REQUIRED"
                job.status = "FAILED"
            job.available_at = utcnow() + timedelta(seconds=getattr(error, "retry_after", 2**job.attempts))
            job.locked_at = None
            if job.kind == "IMPORT_EMAIL":
                email = get_email(db, job.payload["email_id"])
                if email:
                    email.status, email.error = "FAILED", job.error
            elif job.kind == "ANALYZE":
                result = case_crud.get_analysis(db, job.payload["version_id"])
                if result:
                    result.status = "FAILED" if job.status == "FAILED" else "PENDING"
                    result.error = job.error
            db.commit()
    return True


def main():
    global running
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    def stop(*_):
        global running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Enforce a single scheduler/worker instance for the MVP.
    with SessionLocal() as lock:
        if not job_crud.acquire_worker_lock(lock):
            raise SystemExit("A demo worker is already running")
        last_sync = 0
        while running:
            interval = mailbox.poll_interval()
            if interval and time.monotonic() - last_sync > interval:
                with SessionLocal() as db:
                    if mailbox.ready(db):
                        enqueue(db, "SYNC", "mailbox-sync", {}, respect_backoff=True)
                        db.commit()
                last_sync = time.monotonic()
            if not run_one():
                time.sleep(0.5)


if __name__ == "__main__":
    main()
