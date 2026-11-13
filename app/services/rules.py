from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.i18n import MESSAGES, message
from app.core.serialization import model_dict
from app.core.time import utcnow
from app.crud import cases as case_crud
from app.crud import catalog as catalog_crud
from app.models import AuditLog, DemoRule, User
from app.schema.rules import RuleCreateRequest, RuleUpdateRequest


def rule_view(rule: DemoRule) -> dict:
    label = rule.settings.get("label") or MESSAGES.get("category." + rule.category.lower(), rule.category)
    return {
        **model_dict(rule),
        "label": label,
        "settings": {
            key: value for key, value in rule.settings.items() if key not in {"keywords", "require_readable_ocr"}
        },
    }


def create_rule(db: Session, body: RuleCreateRequest, user: User) -> dict:
    rule = DemoRule(
        category="CUSTOM_" + uuid4().hex.upper(),
        settings={**body.model_dump(), "version": "demo-" + utcnow().strftime("%Y%m%d%H%M%S%f")},
    )
    db.add(rule)
    db.flush()
    db.add(
        AuditLog(
            actor=user.username,
            action="RULE_CREATED",
            after=rule.settings,
            reason=message("audit.rule_created", category=rule.category),
        )
    )
    result = rule_view(rule)
    db.commit()
    return result


def update_rule(db: Session, category: str, body: RuleUpdateRequest, user: User) -> dict:
    rule = catalog_crud.get_rule(db, category, for_update=True)
    if not rule:
        raise AppError(404, message("rules.not_found"))
    before = rule.settings
    rule.settings = {
        **before,
        **body.model_dump(exclude_unset=True, exclude_none=True),
        "version": "demo-" + utcnow().strftime("%Y%m%d%H%M%S%f"),
    }
    for case in case_crud.list_for_update(db):
        analysis = case_crud.get_analysis(db, case.active_version_id)
        if analysis and (analysis.category == category or analysis.method == "VLM"):
            previous = case.hr_status
            case.hr_status, case.confirmed_at, case.confirmed_by = "PENDING_REVIEW", None, None
            analysis.status, analysis.assessment = "NOT_STARTED", "NOT_EVALUATED"
            db.add(
                AuditLog(
                    case_id=case.id,
                    actor=user.username,
                    action="RULE_CHANGED",
                    before={"hr_status": previous},
                    after={"hr_status": case.hr_status},
                    reason=message("audit.rule_changed"),
                )
            )
    db.add(
        AuditLog(
            actor=user.username,
            action="RULE_UPDATED",
            before=before,
            after=rule.settings,
            reason=message("audit.rule_updated") + category,
        )
    )
    db.commit()
    return {"ok": True}
