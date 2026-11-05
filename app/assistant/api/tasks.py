from fastapi import APIRouter, Query

from app.api.deps import DBSession, HRUser
from app.assistant.crud import tasks as queries
from app.assistant.schema.tasks import ResumeTask, RetireRule, TaskReview
from app.assistant.services import tasks

router = APIRouter()


@router.get("/conversations/{conversation_id}/runs/{run_id}/dataset")
def dataset(
    conversation_id: str,
    run_id: str,
    db: DBSession,
    user: HRUser,
    reference: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return tasks.dataset_view(db, conversation_id, run_id, user, reference, offset, limit)


@router.get("/conversations/{conversation_id}/runs/{run_id}/classifications")
def classifications(
    conversation_id: str,
    run_id: str,
    db: DBSession,
    user: HRUser,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return tasks.classifications(db, conversation_id, run_id, user, offset, limit)


@router.post("/conversations/{conversation_id}/runs/{run_id}/revise", status_code=202)
def revise(conversation_id: str, run_id: str, body: ResumeTask, db: DBSession, user: HRUser):
    return tasks.revise(db, conversation_id, run_id, user, body)


@router.post("/conversations/{conversation_id}/runs/{run_id}/cancel")
def cancel(conversation_id: str, run_id: str, db: DBSession, user: HRUser):
    return tasks.cancel(db, conversation_id, run_id, user)


@router.post("/conversations/{conversation_id}/runs/{run_id}/review")
def review(conversation_id: str, run_id: str, body: TaskReview, db: DBSession, user: HRUser):
    return tasks.review(db, conversation_id, run_id, user, body)


@router.get("/rules")
def rules(db: DBSession, user: HRUser):
    return [tasks.rule_view(rule) for rule in queries.rules(db, user.id)]


@router.post("/rules/{rule_id}/retire")
def retire(rule_id: str, body: RetireRule, db: DBSession, user: HRUser):
    return tasks.retire_rule(db, rule_id, user, body.version)
