from __future__ import annotations
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import get_db
from app.i18n import t
from app.models import TanCheckRequest, SubmitRequest
from app.services.tan import validate_tan, redeem_tan

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["t"] = t

SURVEYS_DIR = Path(__file__).parent.parent.parent / "surveys"

# Rate limiting: {ip: [timestamps]}
_rate_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 60
RATE_WINDOW = 60


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    window_start = now - RATE_WINDOW
    _rate_store[ip] = [t for t in _rate_store[ip] if t > window_start]
    if len(_rate_store[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Zu viele Anfragen. Bitte warten.")
    _rate_store[ip].append(now)


def _load_questionnaire(questionnaire_id: str) -> dict[str, Any]:
    path = SURVEYS_DIR / f"{questionnaire_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fragebogen {questionnaire_id} nicht gefunden")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    dsgvo = os.getenv("DSGVO_HINWEIS", "")
    return templates.TemplateResponse(request, "public/index.html", {"dsgvo": dsgvo})


@router.get("/start", response_class=HTMLResponse)
async def start(request: Request):
    """QR-Code landing page — reads TAN from URL fragment via JS."""
    return templates.TemplateResponse(request, "public/start.html")


@router.get("/befragung", response_class=HTMLResponse)
async def befragung_page(request: Request):
    return templates.TemplateResponse(request, "public/befragung.html")


@router.get("/danke", response_class=HTMLResponse)
async def danke(request: Request):
    return templates.TemplateResponse(request, "public/danke.html")


@router.post("/api/tan/check")
async def tan_check(request: Request, body: TanCheckRequest):
    ip = _get_client_ip(request)
    _check_rate_limit(ip)

    tan_code = body.tan.strip().upper()
    meta = validate_tan(tan_code)
    if meta is None:
        return JSONResponse({"valid": False, "error": "TAN ungültig oder bereits verwendet."})

    try:
        questionnaire = _load_questionnaire(meta["questionnaire_id"])
    except FileNotFoundError:
        return JSONResponse({"valid": False, "error": "Fragebogen nicht gefunden."})

    return JSONResponse({
        "valid": True,
        "survey_id": meta["survey_id"],
        "class_name": meta["class_name"],
        "survey_title": meta["title"],
        "questionnaire": questionnaire,
    })


@router.post("/api/submit")
async def submit(request: Request, body: SubmitRequest):
    ip = _get_client_ip(request)
    _check_rate_limit(ip)

    tan_code = body.tan.strip().upper()

    result = redeem_tan(tan_code)
    if result is None:
        return JSONResponse(
            {"ok": False, "error": "TAN ungültig, bereits verwendet oder Befragung nicht aktiv."},
            status_code=409,
        )

    # Round timestamp to the hour for anonymity (see §4)
    now = datetime.now(timezone.utc)
    rounded = now.replace(minute=0, second=0, microsecond=0)
    submitted_at = rounded.isoformat()

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO responses (survey_id, class_name, submitted_at, payload_json) VALUES (?, ?, ?, ?)",
            (
                result["survey_id"],
                result["class_name"],
                submitted_at,
                json.dumps(body.answers, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse({"ok": True})
