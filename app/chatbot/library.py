"""List published documents and return literal keyword matches on their PDF pages."""

import re
import unicodedata
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chatbot.models import PolicyDocument, PolicyPage

DocumentType = Literal["handbook", "regulation", "dispatch", "procedure", "form", "other"]
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
PAGE_SIZE = 12


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _matches(value: str, terms: list[str]) -> list[tuple[int, int]]:
    words = list(_WORD.finditer(value))
    tokens = [_fold(word.group()) for word in words]
    return [
        (words[index].start(), words[index + len(terms) - 1].end())
        for index in range(len(tokens) - len(terms) + 1)
        if tokens[index : index + len(terms)] == terms
    ]


def _snippets(value: str, matches: list[tuple[int, int]]) -> list[list[tuple[str, bool]]]:
    snippets = []
    cursor = 0
    while cursor < len(matches) and len(snippets) < 3:
        start, stop = matches[cursor]
        left = max(0, start - 76)
        right = min(len(value), stop + 105)
        segments = []
        if left:
            segments.append(("… ", False))
        end = left
        while cursor < len(matches) and matches[cursor][1] <= right:
            begin, stop = matches[cursor]
            if begin < end:
                cursor += 1
                continue
            segments.extend(((value[end:begin], False), (value[begin:stop], True)))
            end = stop
            cursor += 1
        segments.append((value[end:right] + (" …" if right < len(value) else ""), False))
        snippets.append(segments)
    return snippets


def _view(document: PolicyDocument) -> dict:
    return {
        "id": document.id,
        "title": document.title or document.filename.removesuffix(".pdf"),
        "filename": document.filename,
        "issuer": document.issuer,
        "document_type": document.document_type,
        "page_count": document.page_count,
        "url": f"/api/chatbot/employee/documents/{document.id}/pdf",
    }


def browse(
    db: Session, *, keyword: str, document_type: DocumentType | None, document_id: int | None, page: int
) -> dict:
    statement = select(PolicyDocument).where(PolicyDocument.published.is_(True)).order_by(PolicyDocument.id.desc())
    all_documents = list(db.scalars(statement))
    documents = [
        document
        for document in all_documents
        if (document_type is None or document.document_type == document_type)
        and (document_id is None or document.id == document_id)
    ]
    result = {
        "catalog": [_view(document) for document in all_documents],
        "documents": [_view(document) for document in documents],
        "hits": [],
        "total_hits": 0,
        "page": page,
        "page_size": PAGE_SIZE,
    }
    terms = [_fold(word.group()) for word in _WORD.finditer(unicodedata.normalize("NFC", keyword))]
    if not terms or not documents:
        return result

    views = {document.id: _view(document) for document in documents}
    pages = db.execute(
        select(PolicyPage.document_id, PolicyPage.page_number, PolicyPage.text)
        .where(PolicyPage.document_id.in_(views))
        .order_by(PolicyPage.document_id.desc(), PolicyPage.page_number)
        .execution_options(yield_per=50)
    )
    first = (page - 1) * PAGE_SIZE
    for doc_id, page_number, raw_text in pages:
        value = " ".join(unicodedata.normalize("NFC", raw_text).split())
        matches = _matches(value, terms)
        if not matches:
            continue
        index = result["total_hits"]
        result["total_hits"] += 1
        if first <= index < first + PAGE_SIZE:
            view = views[doc_id]
            result["hits"].append(
                {
                    "document": view,
                    "page_number": page_number,
                    "match_count": len(matches),
                    "snippets": _snippets(value, matches),
                    "url": f"{view['url']}#page={page_number}",
                }
            )
    return result
