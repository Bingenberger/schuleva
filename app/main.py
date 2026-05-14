from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.db import init_db
from app.routes.public import router as public_router
from app.routes.admin import router as admin_router
from app.routes.export import router as export_router
from app.routes.guided import router as guided_router

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE-ME-IN-PRODUCTION-secret-key-placeholder")

app = FastAPI(title="Schulbefragung", docs_url=None, redoc_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="session",
    max_age=8 * 3600,
    https_only=False,  # set True in production (behind nginx with HTTPS)
    same_site="strict",
)

STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(public_router)
app.include_router(admin_router)
app.include_router(export_router)
app.include_router(guided_router)


@app.on_event("startup")
async def startup() -> None:
    init_db()
    _ensure_initial_admin()


def _ensure_initial_admin() -> None:
    from app.db import get_db
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()

    if count == 0:
        password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
        if password:
            from app.auth import create_admin_user
            create_admin_user("admin", password)
            print("Admin-Benutzer 'admin' wurde angelegt. Bitte Passwort beim ersten Login ändern.")
        else:
            print(
                "Kein INITIAL_ADMIN_PASSWORD gesetzt. "
                "Bitte 'python -m app.cli create-admin' ausführen."
            )
