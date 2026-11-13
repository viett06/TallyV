from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse

from app.api.deps import DBSession, Filters, HRUser
from app.services import exports, files

router = APIRouter(tags=["Evidence & exports"])


@router.get("/evidence/{evidence_id}")
def evidence(evidence_id: int, db: DBSession, user: HRUser):
    return Response(
        files.evidence_content(db, evidence_id), media_type="image/png", headers={"Cache-Control": "private, no-store"}
    )


@router.get("/attachments/{attachment_id}")
def attachment(attachment_id: int, db: DBSession, user: HRUser):
    return Response(
        files.attachment_content(db, attachment_id),
        headers={
            "Content-Disposition": f'attachment; filename="attachment-{attachment_id}.xlsx"',
            "Cache-Control": "private, no-store",
        },
        media_type="application/octet-stream",
    )


@router.get("/evidence/{evidence_id}/sanitized")
def sanitized(evidence_id: int, db: DBSession, user: HRUser):
    return Response(
        files.sanitized_content(db, evidence_id), media_type="image/png", headers={"Cache-Control": "private, no-store"}
    )


@router.get("/export")
def export(db: DBSession, selection: Filters, user: HRUser):
    return StreamingResponse(
        exports.create_workbook(db, selection),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="tallyv-synthetic.xlsx"'},
    )
