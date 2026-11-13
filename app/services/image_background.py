"""In-process async orchestration. No broker or ProcessingJob dependency."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore

from sqlalchemy.orm import sessionmaker

from app.core.i18n import message
from app.core.time import utcnow
from app.crud import cases as cases_crud
from app.models import EvidencePrivacy
from app.schema.evidence_privacy import ImageBatch
from app.services import evidence_privacy

logger = logging.getLogger(__name__)
_image_slots = BoundedSemaphore(2)
_import_background = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-background")


def _preprocess(sessions, version_id):
    with _image_slots, sessions() as db:
        evidence_privacy.preprocess_version(db, version_id)
        db.commit()


def _inputs(sessions, batch):
    with sessions() as db:
        payloads = evidence_privacy.assessment_inputs(db, batch)
        db.commit()
        return payloads


def _assess(sessions, payload):
    from app.services.analysis import analyze

    with sessions() as db:
        analyze(db, payload["version_id"], privacy_payload=payload)
        db.commit()


def _failed(sessions, request, error_type, *, preprocessing=False, analyze=False):
    with sessions() as db:
        version = cases_crud.get_version(db, request.version_id)
        if not version:
            return
        case = cases_crud.get_for_update(db, version.case_id)
        if not case or case.deleted_at:
            return
        if preprocessing:
            for item in cases_crud.list_evidence(db, version.id):
                record = db.get(EvidencePrivacy, item.id)
                if record is None:
                    record = EvidencePrivacy(evidence_id=item.id)
                    db.add(record)
                record.status, record.reason = "ERROR", "PREPROCESSING_FAILED"
                record.source_sha256, record.config_revision = item.sha256, "0" * 64
                record.profile_id = record.kind = record.sanitized_path = record.sanitized_sha256 = None
                record.metrics, record.processed_at = {"error_type": error_type}, utcnow()
        result = cases_crud.get_analysis(db, version.id)
        if analyze and result and result.extracted.get("privacy_request_id") == request.privacy_request_id:
            result.status, result.assessment = "FAILED", "MISSING"
            result.error = message("privacy.background_failed", value0=error_type)
        db.commit()


async def run_batch(batch: ImageBatch, sessions):
    """Finish all PII work before any assessment. Each thread owns its DB session."""
    failed = False
    for request in batch.requests:
        try:
            await asyncio.to_thread(_preprocess, sessions, request.version_id)
        except Exception as error:
            failed = True
            logger.warning("image_preprocessing version_id=%s error_type=%s", request.version_id, type(error).__name__)
            await asyncio.to_thread(
                _failed, sessions, request, type(error).__name__, preprocessing=True, analyze=batch.analyze
            )
    if not batch.analyze:
        return
    if failed:
        for request in batch.requests:
            await asyncio.to_thread(_failed, sessions, request, "PreprocessingFailed", analyze=True)
        return  # A failed prerequisite blocks the entire batch from VLM.
    try:
        payloads = await asyncio.to_thread(_inputs, sessions, batch)
    except Exception as error:
        for request in batch.requests:
            await asyncio.to_thread(_failed, sessions, request, type(error).__name__, analyze=True)
        return
    requests = {request.version_id: request for request in batch.requests}
    for payload in payloads:
        try:
            await asyncio.to_thread(_assess, sessions, payload)
        except Exception as error:
            logger.warning("image_assessment version_id=%s error_type=%s", payload["version_id"], type(error).__name__)
            await asyncio.to_thread(
                _failed, sessions, requests[payload["version_id"]], type(error).__name__, analyze=True
            )


def _run_import(batch, sessions):
    asyncio.run(run_batch(batch, sessions))


def defer(db, batch: ImageBatch, background_tasks=None):
    """API: native FastAPI BackgroundTasks; sync importer: bounded background runner."""
    sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    if background_tasks is not None:
        background_tasks.add_task(run_batch, batch, sessions)
        return None
    # Email import still runs in the existing sync worker. Only the image work is
    # submitted here: asyncio orchestration runs in the background without a queue.
    future = _import_background.submit(_run_import, batch, sessions)

    def finished(done):
        if done.exception():
            logger.warning("image_background error_type=%s", type(done.exception()).__name__)

    future.add_done_callback(finished)
    return future
