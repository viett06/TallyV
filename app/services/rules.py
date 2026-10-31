from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.i18n import message
from app.core.time import utcnow
from app.crud import cases as case_crud
from app.crud import catalog as catalog_crud
from app.models import AuditLog, User
from app.schema.rules import RuleUpdateRequest


def update_rule(db: Session, category: str, body: RuleUpdateRequest, user: User) -> dict:
    rule = catalog_crud.get_rule(db, category, for_update=True)
    if not rule:
        raise AppError(404, message("rules.not_found"))
    before = rule.settings
    rule.settings = {**body.model_dump(), "version": "demo-" + utcnow().strftime("%Y%m%d%H%M%S")}
    for case in case_crud.list_for_update(db):
        analysis = case_crud.get_analysis(db, case.active_version_id)
        if analysis.category == category:
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
