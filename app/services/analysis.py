"""AI-stage consumer: only checked sanitized artifacts; raw storage is never read."""

from app.core.attendance import PUNCH_IN, PUNCH_OUT
from app.core.i18n import message
from app.crud import cases as case_crud
from app.crud import catalog as catalog_crud
from app.models import AnalysisResult
from app.schema.evidence_privacy import AssessmentRequest
from app.services import evidence_privacy, evidence_vision, evidence_vlm
from app.services.assessment_input import RuleSnapshotChanged


def analyze(db, version_id, *, privacy_payload=None):
    version = case_crud.get_version(db, version_id)
    if not version:
        return
    case = case_crud.get_for_update(db, version.case_id)
    if not case or case.deleted_at:
        return
    result = case_crud.get_analysis(db, version_id)
    if result is None:
        result = AnalysisResult(version_id=version_id)
        db.add(result)
    result.extracted = result.extracted or {}
    if privacy_payload is None:
        raise ValueError("VLM requires a completed background preprocessing batch")
    request = AssessmentRequest.model_validate(privacy_payload)
    if request.version_id != version_id or request.privacy_request_id != result.extracted.get("privacy_request_id"):
        return  # Superseded delivery; never overwrite a newer request.
    if result.status in {"COMPLETED", "MANUAL_REVIEW"}:
        return  # Duplicate delivery after a committed result.
    evidence = case_crud.list_evidence(db, version_id)
    try:
        revision = evidence_privacy.profiles().revision
        ready, manual = evidence_privacy.ready_records(db, evidence, revision=revision)
    except (ValueError, OSError):
        raise ValueError("Privacy processing is pending or stale; run preprocessing again") from None
    expected = [
        {"evidence_id": item.id, "artifact": record.sanitized_path, "sha256": record.sanitized_sha256}
        for item, record in ready
    ]
    if request.privacy_revision != revision or [a.model_dump() for a in request.images] != expected:
        raise ValueError("AI request does not match the current privacy manifest")
    result.status, result.error, result.category = "RUNNING", None, "UNKNOWN"
    result.method, result.model = "VLM", None
    result.missing, result.conflicts = [], []
    result.extracted = {
        "privacy_request_id": result.extracted.get("privacy_request_id"),
        "manual_evidence_ids": [item.id for item, _ in manual],
    }
    result.evidence_checks = [
        {"evidence_id": item.id, "status": record.status, "checks": [record.reason]}
        for item, record in [*ready, *manual]
    ]
    result.reason = message("privacy.manual_required")
    for item in evidence:
        # Never recycle historical observations derived from a raw input.
        item.extracted, item.checks = {}, []
    if manual or not evidence:
        result.missing = [message("privacy.manual_required")]
    if not ready or len(ready) > 10:
        result.status, result.assessment = "MANUAL_REVIEW", "MISSING"
        result.missing = [message("privacy.manual_required")]
        db.flush()
        return
    policies = {rule.category: rule.settings for rule in catalog_crud.list_rules(db)}
    try:
        images = [evidence_privacy.load_image(record) for _, record in ready]
        output = evidence_vlm.assess(version.normalized, policies, images)
        current = {rule.category: rule.settings for rule in catalog_crud.list_rules(db, lock_for_analysis=True)}
        if current != policies:
            raise RuleSnapshotChanged("HR rules changed during visual assessment")
        result.category, result.reason, result.model = output.category, output.reason, evidence_vision.model_id()
        result.extracted = {
            **result.extracted,
            "visual_assessment": {
                "category": output.category,
                "reason": output.reason,
                "evidence_assessments": [
                    {
                        **assessment.model_dump(exclude={"evidence_ref"}),
                        "evidence_id": ready[assessment.evidence_ref - 1][0].id,
                    }
                    for assessment in output.evidence_assessments
                ],
            },
            "processed_evidence_ids": [item.id for item, _ in ready],
            "privacy_revision": revision,
            "hr_rule_versions": {category: rule.get("version", "demo-1.0") for category, rule in policies.items()},
            "supporting_evidence_ids": [
                ready[a.evidence_ref - 1][0].id for a in output.evidence_assessments if a.relation == "SUPPORTS"
            ],
        }
        for assessment in output.evidence_assessments:
            item = ready[assessment.evidence_ref - 1][0]
            item.extracted = {"visual_assessment": assessment.model_dump(exclude={"evidence_ref"})}
            if assessment.relation == "CONTRADICTS":
                result.conflicts = [*result.conflicts, message("analysis.visual_contradiction")]
            elif assessment.relation == "INSUFFICIENT":
                result.missing = [*result.missing, message("analysis.visual_insufficient")]
        result.status = "COMPLETED"
    except Exception as error:
        result.status, result.category = "FAILED", "UNKNOWN"
        result.reason, result.error = (
            message("analysis.model_review_required"),
            message("analysis.model_error", value0=type(error).__name__),
        )
        result.missing = [*result.missing, message("analysis.model_failed")]
    policy = policies.get(result.category, {})
    result.rules_version = policy.get("version", "demo-1.0")
    data = version.normalized
    for condition, key in [
        (not data["explanation"], "analysis.missing_explanation"),
        (policy.get("require_shift", True) and not data["shift"], "analysis.missing_shift"),
        (policy.get("require_punch", False) and data["punch"] not in {PUNCH_IN, PUNCH_OUT}, "analysis.missing_punch"),
        (result.category == "UNKNOWN", "analysis.cause_unresolved"),
    ]:
        if condition:
            result.missing = [*result.missing, message(key)]
    result.missing, result.conflicts = sorted(set(result.missing)), sorted(set(result.conflicts))
    result.assessment = "CONFLICT" if result.conflicts else "MISSING" if result.missing else "SUFFICIENT"
    db.flush()
