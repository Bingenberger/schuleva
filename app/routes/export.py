from __future__ import annotations
import csv
import io
import json
from pathlib import Path
from typing import Any

from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import RedirectResponse, Response, StreamingResponse

import secrets as _secrets

from app.auth import require_login, require_admin
from app.db import get_db
from app.services.evaluation import evaluate_survey
from app.services.pdf_tans import generate_tan_pdf_bytes
from app.services.pdf_report import generate_report_pdf_bytes

router = APIRouter(prefix="/admin")

SURVEYS_DIR = Path(__file__).parent.parent.parent / "surveys"


def _load_questionnaire(qid: str) -> dict[str, Any]:
    path = SURVEYS_DIR / f"{qid}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_survey_and_questionnaire(survey_id: int) -> tuple[Any, dict[str, Any]]:
    conn = get_db()
    try:
        survey = conn.execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone()
    finally:
        conn.close()
    if survey is None:
        raise HTTPException(404, "Befragung nicht gefunden")
    return survey, _load_questionnaire(survey["questionnaire_id"])


# ── TAN PDF ──────────────────────────────────────────────────────────────────

def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _weasyprint_error(exc: Exception) -> HTTPException:
    msg = str(exc)
    if "pango" in msg.lower() or "cairo" in msg.lower() or "OSError" in type(exc).__name__:
        detail = (
            "PDF-Erzeugung fehlgeschlagen: fehlende Systembibliothek. "
            "Auf dem Server bitte ausführen: "
            "sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0"
        )
    else:
        detail = f"PDF-Erzeugung fehlgeschlagen: {msg}"
    return HTTPException(status_code=500, detail=detail)


@router.get("/survey/{survey_id}/tans.pdf")
async def tans_pdf(request: Request, survey_id: int, class_name: str | None = None):
    require_login(request)
    conn = get_db()
    try:
        survey = conn.execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone()
        if survey is None:
            raise HTTPException(404)

        if class_name:
            cls_rows = conn.execute(
                "SELECT id, name FROM classes WHERE survey_id = ? AND name = ?",
                (survey_id, class_name),
            ).fetchall()
        else:
            cls_rows = conn.execute(
                "SELECT id, name FROM classes WHERE survey_id = ? ORDER BY name",
                (survey_id,),
            ).fetchall()

        class_tans = []
        for cls in cls_rows:
            tans = conn.execute(
                "SELECT code FROM tans WHERE class_id = ? AND used_at IS NULL ORDER BY created_at",
                (cls["id"],),
            ).fetchall()
            if tans:
                class_tans.append({
                    "class_name": cls["name"],
                    "tans": [t["code"] for t in tans],
                })
    finally:
        conn.close()

    if not class_tans:
        raise HTTPException(404, "Keine unbenutzten TANs gefunden")

    try:
        pdf_bytes = generate_tan_pdf_bytes(survey["title"], class_tans)
    except Exception as exc:
        raise _weasyprint_error(exc)
    filename = f"TANs_{survey['title'].replace(' ', '_')}.pdf"
    return _pdf_response(pdf_bytes, filename)


# ── Results PDF ──────────────────────────────────────────────────────────────

@router.get("/survey/{survey_id}/results.pdf")
async def results_pdf(request: Request, survey_id: int, class_name: str | None = None):
    require_login(request)
    survey, questionnaire = _get_survey_and_questionnaire(survey_id)

    eval_result = evaluate_survey(survey_id, questionnaire, class_name)
    filter_label = class_name if class_name else "Schule gesamt"
    period = f"{survey['starts_at'][:10]} – {survey['ends_at'][:10]}"

    try:
        pdf_bytes = generate_report_pdf_bytes(
            survey["title"], period, filter_label, eval_result
        )
    except Exception as exc:
        raise _weasyprint_error(exc)
    filename = f"Auswertung_{survey['title'].replace(' ', '_')}.pdf"
    return _pdf_response(pdf_bytes, filename)


# ── CSV Export ───────────────────────────────────────────────────────────────

@router.get("/survey/{survey_id}/export.csv")
async def export_csv(request: Request, survey_id: int, class_name: str | None = None):
    require_login(request)
    survey, questionnaire = _get_survey_and_questionnaire(survey_id)

    conn = get_db()
    try:
        if class_name:
            rows = conn.execute(
                "SELECT submitted_at, class_name, payload_json FROM responses WHERE survey_id = ? AND class_name = ? ORDER BY submitted_at",
                (survey_id, class_name),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT submitted_at, class_name, payload_json FROM responses WHERE survey_id = ? ORDER BY class_name, submitted_at",
                (survey_id,),
            ).fetchall()
    finally:
        conn.close()

    # Collect all question IDs in order
    question_ids: list[str] = []
    for section in questionnaire.get("sections", []):
        for q in section.get("questions", []):
            question_ids.append(q["id"])

    buf = io.StringIO()
    # UTF-8 with BOM for Excel compatibility
    buf.write("﻿")
    writer = csv.writer(buf, dialect="excel")
    writer.writerow(["submitted_at", "class_name"] + question_ids)

    for row in rows:
        payload = json.loads(row["payload_json"])
        writer.writerow(
            [row["submitted_at"], row["class_name"]]
            + [payload.get(qid, "") for qid in question_ids]
        )

    filename = f"Rohdaten_{survey['title'].replace(' ', '_')}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── TAN CSV ───────────────────────────────────────────────────────────────────

@router.get("/survey/{survey_id}/tans.csv")
async def tans_csv(request: Request, survey_id: int, class_name: str | None = None):
    require_login(request)
    conn = get_db()
    try:
        survey = conn.execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone()
        if survey is None:
            raise HTTPException(404)
        if class_name:
            rows = conn.execute(
                "SELECT t.code, c.name AS class_name, t.used_at, t.created_at"
                " FROM tans t JOIN classes c ON c.id = t.class_id"
                " WHERE t.survey_id = ? AND c.name = ? ORDER BY c.name, t.created_at",
                (survey_id, class_name),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT t.code, c.name AS class_name, t.used_at, t.created_at"
                " FROM tans t JOIN classes c ON c.id = t.class_id"
                " WHERE t.survey_id = ? ORDER BY c.name, t.created_at",
                (survey_id,),
            ).fetchall()
    finally:
        conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf, dialect="excel")
    writer.writerow(["TAN", "Klasse", "Verwendet", "Datum"])
    for r in rows:
        writer.writerow([
            r["code"],
            r["class_name"],
            "Ja" if r["used_at"] else "Nein",
            r["used_at"][:10] if r["used_at"] else "",
        ])

    filename = f"TANs_{survey['title'].replace(' ', '_')}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Share grants (public results links) ──────────────────────────────────────

@router.post("/survey/{survey_id}/share/grant")
async def share_grant_create(
    request: Request,
    survey_id: int,
    scope: str = Form(...),
    csrf_token: str = Form(...),
    redirect_to: str = Form("results"),
):
    from app.auth import validate_csrf
    require_admin(request)
    validate_csrf(request, csrf_token)

    conn = get_db()
    try:
        survey = conn.execute("SELECT id FROM surveys WHERE id = ?", (survey_id,)).fetchone()
        if survey is None:
            raise HTTPException(404)
        existing = conn.execute(
            "SELECT id FROM share_grants WHERE survey_id = ? AND scope = ?",
            (survey_id, scope),
        ).fetchone()
        if existing is None:
            token = _secrets.token_urlsafe(24)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO share_grants (survey_id, scope, token, created_at) VALUES (?,?,?,?)",
                (survey_id, scope, token, now),
            )
            conn.commit()
    finally:
        conn.close()

    target = "results" if redirect_to == "results" else "detail"
    if target == "results":
        return RedirectResponse(f"/admin/survey/{survey_id}/results", status_code=303)
    return RedirectResponse(f"/admin/survey/{survey_id}", status_code=303)


@router.post("/survey/{survey_id}/share/revoke/{grant_id}")
async def share_grant_revoke(
    request: Request,
    survey_id: int,
    grant_id: int,
    csrf_token: str = Form(...),
    redirect_to: str = Form("results"),
):
    from app.auth import validate_csrf
    require_admin(request)
    validate_csrf(request, csrf_token)

    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM share_grants WHERE id = ? AND survey_id = ?",
            (grant_id, survey_id),
        )
        conn.commit()
    finally:
        conn.close()

    if redirect_to == "detail":
        return RedirectResponse(f"/admin/survey/{survey_id}", status_code=303)
    return RedirectResponse(f"/admin/survey/{survey_id}/results", status_code=303)
