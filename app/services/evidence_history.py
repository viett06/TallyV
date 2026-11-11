"""Retrieve permitted historical views, then verify spatial correspondence locally."""

import logging
import re
import unicodedata
from heapq import heappush, heappushpop, nlargest

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import cases as case_crud
from app.crud.jobs import enqueue
from app.models import (
    Attachment,
    AttendanceCase,
    CaseVersion,
    Email,
    EvidenceFile,
    EvidenceReference,
    EvidenceViewpoint,
)
from app.services.storage import read_bytes

logger = logging.getLogger(__name__)


def _evidence_scope(*columns, include_proposed: bool = False):
    active = AttendanceCase.active_version_id == CaseVersion.id
    eligible = or_(active, CaseVersion.status == "PROPOSED") if include_proposed else active
    return (
        select(*columns)
        .select_from(EvidenceFile)
        .join(CaseVersion, CaseVersion.id == EvidenceFile.version_id)
        .join(AttendanceCase, AttendanceCase.id == CaseVersion.case_id)
        .outerjoin(Attachment, Attachment.id == CaseVersion.attachment_id)
        .outerjoin(Email, Email.id == Attachment.email_id)
        .where(AttendanceCase.deleted_at.is_(None), eligible)
    )


def _source():
    return case(
        (AttendanceCase.manual_source.is_not(None), AttendanceCase.manual_source),
        (Email.source_id.startswith("outlook:"), "outlook"),
        else_="mailpit",
    )


def active_evidence(db: Session, evidence_id: int, *, confirmed_only: bool = False) -> EvidenceFile | None:
    query = _evidence_scope(EvidenceFile).where(EvidenceFile.id == evidence_id)
    if confirmed_only:
        query = query.where(AttendanceCase.hr_status == "CONFIRMED")
    return db.scalar(query)


def compare(db: Session, evidence: EvidenceFile, content: bytes) -> dict:
    try:
        with db.begin_nested():
            return _compare(db, evidence, content)
    except Exception as error:
        logger.warning("Evidence history unavailable for evidence %s (%s)", evidence.id, type(error).__name__)
        return {"status": "UNAVAILABLE"}


def enqueue_confirmed(db: Session, version_id: int) -> None:
    if settings.evidence_history_enabled and case_crud.evidence_count(db, version_id):
        enqueue(db, "INDEX_EVIDENCE", f"evidence-history:{version_id}", {"version_id": version_id})


def index_confirmed_version(db: Session, version_id: int) -> None:
    if not settings.evidence_history_enabled:
        return
    version = case_crud.get_version(db, version_id)
    attendance = case_crud.get_for_update(db, version.case_id) if version else None
    if not attendance or attendance.hr_status != "CONFIRMED" or attendance.active_version_id != version_id:
        return
    for evidence in case_crud.list_evidence(db, version_id):
        reference = db.get(EvidenceReference, evidence.id)
        if not reference or not reference.excluded:
            index_reference(db, evidence, read_bytes(evidence.path))


def index_reference(db: Session, evidence: EvidenceFile, content: bytes) -> dict:
    result = _compare(db, evidence, content, index=True)
    if result["status"] == "UNAVAILABLE":
        raise RuntimeError("Reference comparison unavailable")
    return result


def _compare(db: Session, evidence: EvidenceFile, content: bytes, *, index: bool = False) -> dict:
    from app.services import evidence_image_features as features

    scope = _evidence_scope(AttendanceCase.id, _source(), include_proposed=not index).where(
        EvidenceFile.id == evidence.id
    )
    if index:
        scope = scope.where(AttendanceCase.hr_status == "CONFIRMED")
    row = db.execute(scope).first()
    if row is None:
        return {"status": "OUT_OF_SCOPE"}
    case_id, source = row
    existing = db.get(EvidenceReference, evidence.id)
    if existing and existing.excluded:
        return {"status": "OUT_OF_SCOPE"}

    image = features.open_image(content)
    fingerprint = features.fingerprint(image)
    background = features.background(image, evidence.extracted)
    reference_query = (
        _evidence_scope(
            EvidenceReference.evidence_id,
            EvidenceReference.viewpoint_id,
            EvidenceReference.fingerprint,
            EvidenceReference.embedding,
            EvidenceFile.sha256,
        )
        .join(EvidenceReference, EvidenceReference.evidence_id == EvidenceFile.id)
        .where(
            EvidenceFile.id != evidence.id if index else AttendanceCase.id != case_id,
            AttendanceCase.hr_status == "CONFIRMED",
            _source() == source,
            EvidenceReference.excluded.is_(False),
            or_(EvidenceReference.model == features.FEATURE_VERSION, EvidenceFile.sha256 == evidence.sha256),
        )
    )
    vector = None
    if background is not None:
        vector = existing.embedding if not index and existing and existing.model == features.FEATURE_VERSION else None
        if vector is None:
            vector = features.embedding(background[0])

    candidates = db.execute(reference_query.execution_options(yield_per=128))
    nearest: dict[int, list] = {}
    near_duplicate_id = None
    for evidence_id, viewpoint_id, old_fingerprint, old_embedding, sha in candidates:
        if sha == evidence.sha256:
            candidates.close()
            return _reuse(evidence_id, "EXACT")
        if near_duplicate_id is None and features.near_duplicate(fingerprint, old_fingerprint):
            near_duplicate_id = evidence_id
        if vector is None or old_embedding is None or viewpoint_id is None:
            continue
        similarity = sum(a * b for a, b in zip(vector, old_embedding, strict=True))
        if similarity < 0.50:
            continue
        sample = (min(1.0, similarity), evidence_id, viewpoint_id)
        group_samples = nearest.setdefault(viewpoint_id, [])
        if len(group_samples) < 3:
            heappush(group_samples, sample)
        else:
            heappushpop(group_samples, sample)
    if near_duplicate_id is not None:
        return _reuse(near_duplicate_id, "NEAR")
    ranked_rows = nlargest(16, (sample for group in nearest.values() for sample in group))

    result, matched_id = {"status": "INSUFFICIENT_BACKGROUND"}, None
    if vector is not None:
        result, matched_id = _verify_candidates(db, evidence, background, ranked_rows)
    if not index:
        if matched_id:
            result["viewpoint_id"] = matched_id
        return result
    if result["status"] == "UNAVAILABLE":
        return result

    group_id = existing.viewpoint_id if existing else None
    current_group = db.get(EvidenceViewpoint, group_id) if group_id else None
    if matched_id and (not current_group or current_group.location_evidence_id != evidence.id):
        group_id = matched_id
    if vector is not None and not group_id:
        group = EvidenceViewpoint()
        db.add(group)
        db.flush()
        group_id = group.id
    if existing is None:
        existing = EvidenceReference(evidence_id=evidence.id)
        db.add(existing)
    existing.model = features.FEATURE_VERSION
    existing.fingerprint = fingerprint
    existing.embedding = vector
    existing.viewpoint_id = group_id
    if group_id:
        result["viewpoint_id"] = group_id
    return result


def _reuse(evidence_id: int, kind: str) -> dict:
    return {"status": "POSSIBLE_REUSE", "reference_evidence_id": evidence_id, "duplicate_kind": kind}


def _verify_candidates(db: Session, evidence: EvidenceFile, background, ranked_rows: list) -> tuple[dict, int | None]:
    from app.services import evidence_image_features as features

    strongest = {}
    checked = 0
    signage = _signage(evidence.extracted)
    for similarity, evidence_id, viewpoint_id in ranked_rows:
        reference = active_evidence(db, evidence_id, confirmed_only=True)
        if reference is None:
            continue
        try:
            other = features.background(features.open_image(read_bytes(reference.path)), reference.extracted)
        except Exception as error:
            logger.warning("Cannot compare evidence reference %s (%s)", evidence_id, type(error).__name__)
            continue
        checked += 1
        geometry = features.geometry(background, other) if other is not None else None
        if geometry:
            match = {
                **geometry,
                "reference_evidence_id": evidence_id,
                "viewpoint_id": viewpoint_id,
                "cosine": round(similarity, 4),
                "shared_signage": bool(signage & _signage(reference.extracted)),
            }
            if viewpoint_id not in strongest or _match_order(match) > _match_order(strongest[viewpoint_id]):
                strongest[viewpoint_id] = match
    matches = sorted(strongest.values(), key=_match_order, reverse=True)
    strong = [match for match in matches if match["strength"] == "STRONG"]
    if len(strong) == 1:
        best = strong[0]
        group = db.get(EvidenceViewpoint, best["viewpoint_id"])
        result = {"status": "KNOWN_VIEW" if _location_active(db, group) else "KNOWN_VIEW_UNLOCATED", "matches": matches}
        if result["status"] == "KNOWN_VIEW":
            result["location"] = group.location
            result["location_basis"] = group.location_basis
            result["location_reference_evidence_id"] = group.location_evidence_id
        return result, best["viewpoint_id"]
    if len(matches) > 1:
        return {"status": "AMBIGUOUS", "matches": matches}, None
    if matches:
        return {"status": "PARTIAL", "matches": matches}, None
    if ranked_rows and not checked:
        return {"status": "UNAVAILABLE"}, None
    return {"status": "NO_MATCH" if ranked_rows else "NO_REFERENCE"}, None


def _signage(extracted: dict) -> set[str]:
    signs = set()
    for region in extracted.get("ocr_regions", []):
        folded = unicodedata.normalize("NFKD", region["text"].casefold().replace("đ", "d"))
        label = " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in folded if not unicodedata.combining(c))))
        if re.fullmatch(r"(?:vinmec(?: [a-z0-9]+){0,5}|(?:sanh|phong|khoa|co so|benh vien)(?: [a-z0-9]+){1,5})", label):
            signs.add(label)
    return signs


def _match_order(match):
    return (match["strength"] == "STRONG", match["feature_count"], len(match["regions"]), match["cosine"])


def _location_active(db: Session, group: EvidenceViewpoint | None) -> bool:
    if not group or not group.location or not group.location_basis or not group.location_evidence_id:
        return False
    anchor = db.get(EvidenceReference, group.location_evidence_id)
    return bool(
        anchor
        and not anchor.excluded
        and anchor.viewpoint_id == group.id
        and active_evidence(db, anchor.evidence_id, confirmed_only=True)
    )
