"""Import local sample PDFs with the same ingestion as the HR upload page."""

import argparse
from pathlib import Path

from app.chatbot.config import MAX_PDF_BYTES
from app.chatbot.ingestion import ingest_pdf
from app.core.errors import AppError
from app.db.session import SessionLocal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--force-ocr", action="store_true", help="Run OCR even on pages with embedded text.")
    args = parser.parse_args()
    failed = False
    for path in args.files:
        try:
            with path.open("rb") as pdf, SessionLocal() as db:
                document, created = ingest_pdf(db, path.name, pdf.read(MAX_PDF_BYTES + 1), force_ocr=args.force_ocr)
                status = "imported" if created else "already present"
                print(
                    f"{path.name}: {status}, id={document.id}, {document.page_count} pages, "
                    f"{document.ocr_page_count} OCR pages, {document.chunk_count} chunks",
                    flush=True,
                )
        except (AppError, OSError) as exc:
            print(f"{path.name}: {exc}", flush=True)
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
