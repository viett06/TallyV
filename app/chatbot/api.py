from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import DBSession, HRUser
from app.chatbot.config import MAX_PDF_BYTES
from app.chatbot.employee_api import EmployeeUser
from app.chatbot.employee_api import router as employee_router
from app.chatbot.ingestion import ingest_pdf
from app.chatbot.library import DocumentType
from app.chatbot.models import PolicyDocument
from app.core.errors import AppError

documents = APIRouter()


class DocumentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    page_count: int
    ocr_page_count: int
    chunk_count: int
    published: bool


class UploadResult(BaseModel):
    document: DocumentView
    created: bool


@documents.get("", response_model=list[DocumentView])
def list_documents(db: DBSession, user: HRUser):
    return list(db.scalars(select(PolicyDocument).order_by(PolicyDocument.id.desc())))


@documents.post("", response_model=UploadResult)
def upload_document(
    file: UploadFile,
    db: DBSession,
    user: HRUser,
    title: Annotated[str | None, Form(max_length=255)] = None,
    issuer: Annotated[str | None, Form(max_length=160)] = None,
    document_type: Annotated[DocumentType, Form()] = "other",
):
    document, created = ingest_pdf(
        db,
        file.filename or "",
        file.file.read(MAX_PDF_BYTES + 1),
        title=title,
        issuer=issuer,
        document_type=document_type,
    )
    return {"document": document, "created": created}


class PublicationRequest(BaseModel):
    published: bool


@documents.patch("/{document_id}", response_model=DocumentView)
def change_publication(document_id: int, body: PublicationRequest, db: DBSession, user: HRUser):
    document = db.get(PolicyDocument, document_id)
    if document is None:
        raise AppError(404, "Không tìm thấy tài liệu.")
    document.published = body.published
    db.commit()
    return document


def _pdf_response(document: PolicyDocument) -> Response:
    return Response(
        document.pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(document.filename, safe='')}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@documents.get("/{document_id}/pdf")
def original_document(document_id: int, db: DBSession, user: HRUser):
    document = db.get(PolicyDocument, document_id)
    if document is None:
        raise AppError(404, "Không tìm thấy tài liệu.")
    return _pdf_response(document)


@employee_router.get("/documents/{document_id}/pdf")
def published_document(document_id: int, db: DBSession, user: EmployeeUser):
    document = db.get(PolicyDocument, document_id)
    if document is None or not document.published:
        raise AppError(404, "Không tìm thấy tài liệu.")
    return _pdf_response(document)


router = APIRouter(prefix="/chatbot", tags=["Chatbot"])
router.include_router(documents, prefix="/documents")
router.include_router(employee_router)

# Keep existing PDF citations and upload clients working during the move.
legacy_router = APIRouter()
legacy_router.include_router(documents, prefix="/policy-documents", include_in_schema=False)
