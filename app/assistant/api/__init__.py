from fastapi import APIRouter

from app.api.deps import HRUser
from app.assistant.api import artifacts, conversations, tasks
from app.assistant.config import settings

router = APIRouter(prefix="/assistant", tags=["Assistant"])
router.include_router(conversations.router)
router.include_router(artifacts.router)
router.include_router(tasks.router)


@router.get("/capabilities")
def capabilities(user: HRUser):
    return {
        "processing_mode": settings.processing_mode,
        "model": settings.ollama_model if settings.processing_mode == "LOCAL_LLM" else None,
        "template_formats": ["docx", "txt", "xlsx"],
        "data_formats": ["xlsx", "csv", "txt", "docx", "pdf"],
        "limits": {"upload_mb": 15, "rows": 200, "pdf_pages": 20},
        "ocr": False,
        "email_sending": False,
        "data_tasks": True,
        "orchestrator": "Microsoft Agent Framework",
        "data_limits": {"rows": settings.max_data_rows, "steps": settings.max_steps, "files": 6},
        "code_execution": False,
        "formula_recalculation": False,
    }
