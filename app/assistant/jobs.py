"""Assistant lifecycle hooks called by the shared TallyV worker."""

from app.assistant.crud import conversations
from app.assistant.errors import InputError
from app.assistant.models import Message
from app.assistant.services.workflow import ask, process


def start(db, job):
    run = conversations.run(db, job.payload["run_id"])
    if run.status not in {"COMPLETED", "CANCELLED", "NEEDS_INPUT"}:
        run.status = "RUNNING"


def execute(db, job):
    run = conversations.run(db, job.payload["run_id"])
    if run.kind == "DATA_TASK":
        from app.assistant.services.tasks import advance

        return advance(db, job)
    try:
        with db.begin_nested():
            process(db, run)
    except InputError as error:
        run = conversations.run(db, job.payload["run_id"])
        ask(db, run, error.detail)
    return True


def failed(db, job):
    run = conversations.run(db, job.payload["run_id"])
    if run.status == "CANCELLED":
        job.status = "DONE"
        return
    run.status = "FAILED" if job.status == "FAILED" else "QUEUED"
    run.summary = job.error
    if job.status == "FAILED":
        db.add(
            Message(
                conversation_id=run.conversation_id,
                role="assistant",
                content=job.error,
                details={"run_id": run.id, "kind": "error"},
            )
        )
