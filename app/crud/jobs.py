"""Durable queue storage: idempotent enqueue, claim, lease and worker lock."""

from datetime import timedelta

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import ProcessingJob


def enqueue(db: Session, kind: str, key: str, payload: dict, *, respect_backoff: bool = False) -> ProcessingJob:
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.key == key))
    if job is None:
        job = ProcessingJob(kind=kind, key=key, payload=payload)
        db.add(job)
    elif job.status in {"FAILED", "DONE"}:
        if respect_backoff and job.status == "FAILED" and job.available_at > utcnow():
            return job
        job.status, job.attempts, job.error = "PENDING", 0, None
        job.payload = payload
        job.available_at = utcnow()
    return job


def get_job(db: Session, job_id: int) -> ProcessingJob | None:
    return db.get(ProcessingJob, job_id)


def get_by_key(db: Session, key: str) -> ProcessingJob | None:
    return db.scalar(select(ProcessingJob).where(ProcessingJob.key == key))


def list_jobs(db: Session) -> list[ProcessingJob]:
    return list(db.scalars(select(ProcessingJob).order_by(ProcessingJob.id.desc()).limit(100)))


def claim_next(db: Session) -> ProcessingJob | None:
    now = utcnow()
    job = db.scalar(
        select(ProcessingJob)
        .where(
            or_(
                (ProcessingJob.status == "PENDING") & (ProcessingJob.available_at <= now),
                (ProcessingJob.status == "RUNNING") & (ProcessingJob.locked_at < now - timedelta(minutes=5)),
            )
        )
        .order_by(ProcessingJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job:
        job.status, job.locked_at = "RUNNING", now
        job.attempts += 1
    return job


def acquire_worker_lock(db: Session) -> bool:
    return bool(db.scalar(text("SELECT pg_try_advisory_lock(744019)")))
