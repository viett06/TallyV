from urllib.parse import quote

from fastapi import APIRouter, Query, Response

from app.api.deps import DBSession, HRUser
from app.assistant.schema.chat import ArtifactEdit, ArtifactView, ReviewRequest
from app.assistant.services import artifacts as service

router = APIRouter()


def file_response(result):
    content, name, media_type = result
    return Response(
        content, media_type=media_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"}
    )


@router.get("/attachments/{attachment_id}/download")
def source_download(attachment_id: str, db: DBSession, user: HRUser):
    return file_response(service.source_download(db, attachment_id, user))


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactView)
def edit(artifact_id: str, body: ArtifactEdit, db: DBSession, user: HRUser):
    return service.edit(db, artifact_id, user, body)


@router.post("/artifacts/{artifact_id}/review", response_model=ArtifactView)
def review(artifact_id: str, body: ReviewRequest, db: DBSession, user: HRUser):
    return service.review(db, artifact_id, user, body)


@router.get("/artifacts/{artifact_id}/download")
def download(artifact_id: str, db: DBSession, user: HRUser, kind: str = "docx"):
    return file_response(service.download(db, artifact_id, user, kind))


@router.get("/artifacts/{artifact_id}/preview")
def preview(
    artifact_id: str,
    db: DBSession,
    user: HRUser,
    sheet: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    return service.preview(db, artifact_id, user, sheet, offset, limit)


@router.get("/runs/{run_id}/download")
def run_download(run_id: str, db: DBSession, user: HRUser, kind: str = "zip"):
    return file_response(service.run_download(db, run_id, user, kind))
