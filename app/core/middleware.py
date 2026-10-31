import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.i18n import message


class OAuthAccessLogFilter(logging.Filter):
    """Authorization codes must not enter development server access logs."""

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            path = record.args[2]
            if isinstance(path, str) and path.startswith("/api/outlook/callback"):
                record.args = (*record.args[:2], path.split("?", 1)[0], *record.args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(OAuthAccessLogFilter())


async def local_security(request: Request, call_next):
    is_oauth_response = request.method == "POST" and request.url.path == "/api/outlook/callback"
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not is_oauth_response:
        origin = request.headers.get("origin")
        if origin and origin not in settings.allowed_origins.split(","):
            return JSONResponse({"detail": message("security.origin_denied")}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": message("security.cross_site_denied")}, status_code=403)
    try:
        response = await call_next(request)
    except Exception as error:
        logging.getLogger("tallyv.api").error("request_failed error_type=%s", type(error).__name__)
        response = JSONResponse({"detail": message("errors.internal_error")}, status_code=500)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response
