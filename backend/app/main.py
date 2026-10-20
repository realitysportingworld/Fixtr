from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.router import router as api_router

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


@app.get("/health")
def health():
    return {"status": "ok"}
