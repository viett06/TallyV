"""Application storage adapter for the standalone offline image preprocessor."""

from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from tallyv_image_preprocessing import ProfileSet, SanitizedImage, process

from app.core.config import settings
from app.core.time import utcnow
from app.crud import cases as cases_crud
from app.models import Attachment, CaseVersion, EvidenceFile, EvidencePrivacy
from app.schema.evidence_privacy import ImageBatch
from app.services.storage import read_bytes, store_bytes


def profiles() -> ProfileSet:
    return ProfileSet.model_validate_json(settings.evidence_privacy_profiles_path.read_bytes())


def plan_batch(db: Session, version_ids: list[int], *, analyze: bool = False) -> ImageBatch:
    requests = []
    for version_id in sorted(set(version_ids)):
        request_id = uuid4().hex
        if analyze:
            result = cases_crud.get_analysis(db, version_id)
            result.status, result.error = "WAITING_PRIVACY", None
            result.extracted = {"privacy_request_id": request_id}
        requests.append({"schema_version": 1, "version_id": version_id, "privacy_request_id": request_id})
    return ImageBatch(requests=requests, analyze=analyze)


def plan_import(db: Session, email_id: int) -> ImageBatch | None:
    version_ids = list(
        db.scalars(
            select(CaseVersion.id).join(Attachment).join(EvidenceFile).where(Attachment.email_id == email_id).distinct()
        )
    )
    return plan_batch(db, version_ids) if version_ids else None


def _current(record, item, revision):
    return bool(
        record
        and record.source_sha256 == item.sha256
        and record.config_revision == revision
        and record.status in {"READY", "MANUAL_REVIEW"}
    )


def preprocess_version(db: Session, version_id: int):
    version = cases_crud.get_version(db, version_id)
    if not version:
        return
    case = cases_crud.get_for_update(db, version.case_id)
    if not case or case.deleted_at:
        return
    config = profiles()  # Invalid configuration fails the job, never releases images.
    evidence = cases_crud.list_evidence(db, version_id)
    for item in evidence:
        record = db.get(EvidencePrivacy, item.id)
        if _current(record, item, config.revision):
            continue
        if record is None:
            record = EvidencePrivacy(evidence_id=item.id)
            db.add(record)
        record.status = "PENDING"
        record.source_sha256, record.config_revision = item.sha256, config.revision
        record.profile_id = record.kind = record.sanitized_path = record.sanitized_sha256 = None
        content = read_bytes(item.path)
        if sha256(content).hexdigest() != item.sha256:
            record.status, record.reason, record.metrics = "MANUAL_REVIEW", "SOURCE_CHECKSUM_MISMATCH", {}
        else:
            outcome = process(content, config)
            record.status, record.reason, record.metrics = outcome.status, outcome.reason, outcome.metrics
            if outcome.image:
                path, digest = store_bytes(outcome.image.content, ".png")
                record.sanitized_path, record.sanitized_sha256 = path, digest
                record.profile_id, record.kind = outcome.image.profile_id, outcome.image.kind
        record.processed_at = utcnow()
    db.flush()


def assessment_inputs(db: Session, batch: ImageBatch) -> list[dict]:
    """Validate the entire preprocessing pass before releasing any VLM call."""
    revision = profiles().revision
    completed = []
    for request in batch.requests:
        version_id = request.version_id
        version = cases_crud.get_version(db, version_id)
        case = cases_crud.get_for_update(db, version.case_id) if version else None
        result = cases_crud.get_analysis(db, version_id)
        if (
            not case
            or case.deleted_at
            or not result
            or result.extracted.get("privacy_request_id") != request.privacy_request_id
        ):
            continue
        if result.status in {"COMPLETED", "MANUAL_REVIEW"}:
            continue
        evidence = cases_crud.list_evidence(db, version_id)
        ready, _ = ready_records(db, evidence, revision=revision)
        manifest = [
            {"evidence_id": item.id, "artifact": record.sanitized_path, "sha256": record.sanitized_sha256}
            for item, record in ready
        ]
        completed.append(
            {
                "schema_version": 1,
                "version_id": version_id,
                "privacy_request_id": request.privacy_request_id,
                "privacy_revision": revision,
                "images": manifest,
            }
        )
    for payload in completed:
        cases_crud.get_analysis(db, payload["version_id"]).status = "PENDING"
    return completed


def ready_records(db: Session, evidence, *, revision=None):
    revision = revision or profiles().revision
    ready, manual = [], []
    for item in evidence:
        record = db.get(EvidencePrivacy, item.id)
        if not _current(record, item, revision):
            raise ValueError("Privacy preprocessing is pending or stale")
        (ready if record.status == "READY" else manual).append((item, record))
    return ready, manual


def load_image(record: EvidencePrivacy) -> SanitizedImage:
    if record.status != "READY" or not record.sanitized_path or not record.sanitized_sha256:
        raise ValueError("Only processed images may enter AI inference")
    if record.kind not in {"FACEID", "DEVICE_ERROR"}:
        raise ValueError("Unsupported evidence kind")
    try:
        content = read_bytes(record.sanitized_path)
    except Exception:
        record.status, record.reason = "INVALID", "ARTIFACT_UNAVAILABLE"
        raise ValueError("Sanitized artifact unavailable") from None
    if sha256(content).hexdigest() != record.sanitized_sha256:
        record.status, record.reason = "INVALID", "ARTIFACT_CHECKSUM_MISMATCH"
        raise ValueError("Sanitized artifact checksum mismatch")
    return SanitizedImage(content, record.sanitized_sha256, record.profile_id, record.kind)


def public_status(db: Session, evidence_id: int):
    record = db.get(EvidencePrivacy, evidence_id)
    if not record:
        return {"status": "PENDING", "reason": "NOT_PROCESSED", "vlm_allowed": False}
    item = db.get(EvidenceFile, evidence_id)
    try:
        current = _current(record, item, profiles().revision)
    except (OSError, ValueError):
        current = False
    # The caller already checked evidence ownership; artifact locations stay private.
    failed = record.status in {"INVALID", "ERROR"}
    status = record.status if current else "MANUAL_REVIEW" if failed else "PENDING"
    return {
        "status": status,
        "reason": record.reason if current or failed else "STALE_CONFIGURATION",
        "kind": record.kind,
        "profile_id": record.profile_id,
        "metrics": record.metrics,
        "vlm_allowed": status == "READY",
        "processed_at": record.processed_at.isoformat(),
        "preview_url": f"/api/evidence/{evidence_id}/sanitized" if status == "READY" else None,
    }
