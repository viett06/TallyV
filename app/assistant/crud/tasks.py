"""Persistence queries for task receipts and owner-scoped business rules."""

from sqlalchemy import select

from app.assistant.models import BusinessRule, TaskStep


def steps(db, run_id):
    return list(
        db.scalars(select(TaskStep).where(TaskStep.run_id == run_id).order_by(TaskStep.updated_at, TaskStep.id))
    )


def step(db, run_id, step_id):
    return db.scalar(select(TaskStep).where(TaskStep.run_id == run_id, TaskStep.step_id == step_id))


def rules(db, user_id, *, active=True):
    query = select(BusinessRule).where(BusinessRule.user_id == user_id)
    if active:
        query = query.where(BusinessRule.status == "ACTIVE")
    return list(db.scalars(query.order_by(BusinessRule.created_at, BusinessRule.id)))


def rule(db, rule_id, user_id):
    return db.scalar(
        select(BusinessRule).where(BusinessRule.id == rule_id, BusinessRule.user_id == user_id).with_for_update()
    )
