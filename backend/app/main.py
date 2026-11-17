import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import router as api_router
from app.core.config import settings
from app.db.base import engine
from app.web.share import router as share_router

logger = logging.getLogger("fixtr")

if not settings.DEBUG and settings.EMAIL_BACKEND == "console":
    logger.warning("EMAIL_BACKEND is 'console': password reset emails are only logged, not sent")
if not settings.DEBUG and not settings.PUBLIC_BASE_URL:
    logger.warning("PUBLIC_BASE_URL is not set: share links use whatever host the request came in on")

# Interactive API docs only in debug; production doesn't advertise its schema
docs_kwargs = {} if settings.DEBUG else {"docs_url": None, "redoc_url": None, "openapi_url": None}

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, **docs_kwargs)

# Auth uses bearer tokens, not cookies, so credentials are never needed cross-origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(share_router)  # /c/{code} share pages


@app.get("/health")
def health():
    """For load balancers and uptime checks: 200 only when the database answers too."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Health check: database unreachable")
        return JSONResponse(status_code=503, content={"status": "error", "database": "unreachable"})
    return {"status": "ok", "database": "ok"}
