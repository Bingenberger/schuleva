from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import settings
from app.db import schema_ready
from app.routes.public import router as public_router
from app.routes.admin import router as admin_router
from app.routes.export import router as export_router
from app.routes.guided import router as guided_router

app = FastAPI(title="Schulbefragung", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key(),
    session_cookie="session",
    max_age=8 * 3600,
    https_only=settings.SECURE_COOKIES,  # Secure-Cookie, sobald BASE_URL https ist
    same_site="strict",
)

STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(public_router)
app.include_router(admin_router)
app.include_router(export_router)
app.include_router(guided_router)


# Kein Schemaaufbau beim Start: python -m app.migrate ist der explizite Schritt.
@app.get("/health/live", include_in_schema=False)
def health_live() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/health/ready", include_in_schema=False)
def health_ready() -> JSONResponse:
    ready = schema_ready() and settings.SURVEYS_DIR.is_dir()
    return JSONResponse({"status": "ready" if ready else "not-ready"}, status_code=200 if ready else 503)
