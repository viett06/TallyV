"""FastAPI composition root; workflows live in app.services."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.core.config import ROOT
from app.core.errors import AppError
from app.core.middleware import local_security


def create_app() -> FastAPI:
    application = FastAPI(title="TallyV - Attendance review", docs_url=None, redoc_url=None, openapi_url=None)
    application.middleware("http")(local_security)

    @application.exception_handler(AppError)
    async def application_error(request: Request, error: AppError):
        return JSONResponse({"detail": error.detail}, status_code=error.status_code)

    application.include_router(router)
    frontend = ROOT / "frontend" / "dist"
    if frontend.is_dir():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return application


app = create_app()
