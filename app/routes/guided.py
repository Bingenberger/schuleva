"""Guided survey mode – teacher control panel + student WebSocket."""
from __future__ import annotations
import io
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

import qrcode
from fastapi import APIRouter, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.auth import generate_csrf_token, get_current_user, require_login, validate_csrf
from app.db import get_db
from app.services.evaluation import evaluate_survey
from app.i18n import t
from app.services.guided import GuidedSession, StudentConn, create_session, get_session

router = APIRouter()
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
SURVEYS_DIR = Path(__file__).parent.parent.parent / "surveys"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["t"] = t


# ── Admin: Start session ───────────────────────────────────────────────────────

@router.post("/admin/survey/{survey_id}/guided/start")
async def guided_start(
    request: Request,
    survey_id: int,
    class_name: str = Form(...),
    csrf_token: str = Form(...),
):
    require_login(request)
    validate_csrf(request, csrf_token)

    conn = get_db()
    try:
        survey = conn.execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone()
        if survey is None:
            raise HTTPException(404)
        cls = conn.execute(
            "SELECT id FROM classes WHERE survey_id = ? AND name = ?", (survey_id, class_name)
        ).fetchone()
        if cls is None:
            raise HTTPException(404, "Klasse nicht gefunden")
    finally:
        conn.close()

    q_path = SURVEYS_DIR / f"{survey['questionnaire_id']}.json"
    if not q_path.exists():
        raise HTTPException(404, "Fragebogen nicht gefunden")
    questionnaire = json.loads(q_path.read_text(encoding="utf-8"))

    session = create_session(survey_id, class_name, questionnaire)
    return RedirectResponse(f"/admin/guided/{session.session_id}", status_code=303)


# ── Admin: Teacher control panel ──────────────────────────────────────────────

@router.get("/admin/guided/{session_id}", response_class=HTMLResponse)
async def guided_control(request: Request, session_id: str):
    user = require_login(request)
    session = get_session(session_id)
    if session is None:
        raise HTTPException(404, "Sitzung nicht gefunden oder abgelaufen (max. 4 Stunden)")
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(request, "admin/guided_control.html", {
        "session": session,
        "user": user,
        "csrf": csrf,
    })


@router.get("/admin/guided/{session_id}/qr.png")
async def guided_qr(request: Request, session_id: str):
    require_login(request)
    session = get_session(session_id)
    if session is None:
        raise HTTPException(404)

    origin = str(request.base_url).rstrip("/")
    student_url = f"{origin}/guided/{session_id}"

    qr = qrcode.QRCode(box_size=8, border=3)
    qr.add_data(student_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


# ── Public: Student page ──────────────────────────────────────────────────────

@router.get("/guided/{session_id}", response_class=HTMLResponse)
async def guided_student_page(request: Request, session_id: str):
    session = get_session(session_id)
    if session is None or session.phase == "ended":
        return templates.TemplateResponse(request, "guided_ended.html", {})
    is_kinder = session.questionnaire.get("id", "").startswith("kinder")
    return templates.TemplateResponse(request, "guided_student.html", {
        "session_id": session_id,
        "survey_title": session.questionnaire.get("title", "Befragung"),
        "is_kinder": is_kinder,
    })


# ── WebSocket: Teacher ────────────────────────────────────────────────────────

@router.websocket("/ws/guided/{session_id}/teacher")
async def teacher_ws_endpoint(ws: WebSocket, session_id: str):
    if not ws.session.get("user_id"):
        await ws.close(code=4001)
        return

    session = get_session(session_id)
    if session is None:
        await ws.close(code=4004)
        return

    await ws.accept()
    session.teacher_ws = ws
    await _send_teacher(session, _teacher_state(session))

    try:
        while True:
            msg = await ws.receive_json()
            await _handle_teacher_msg(session, msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if session.teacher_ws is ws:
            session.teacher_ws = None


# ── WebSocket: Student ────────────────────────────────────────────────────────

@router.websocket("/ws/guided/{session_id}/student")
async def student_ws_endpoint(ws: WebSocket, session_id: str):
    session = get_session(session_id)
    if session is None or session.phase == "ended":
        await ws.close(code=4004)
        return

    await ws.accept()
    student_id = secrets.token_hex(8)
    session.students[student_id] = StudentConn(ws=ws)

    await _notify_teacher(session, {"type": "student_count", "count": len(session.students)})
    await _send_student_state(session, student_id)

    try:
        while True:
            msg = await ws.receive_json()
            await _handle_student_msg(session, student_id, msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        session.students.pop(student_id, None)
        await _notify_teacher(session, {"type": "student_count", "count": len(session.students)})


# ── Teacher message handler ───────────────────────────────────────────────────

async def _handle_teacher_msg(session: GuidedSession, msg: dict) -> None:
    kind = msg.get("type")

    if kind == "start" and session.phase == "lobby":
        session.phase = "survey"
        session.q_idx = 0
        session.unlocked = False
        _reset_answered(session)
        await _broadcast_students(session, _question_msg(session))
        await _send_teacher(session, _teacher_state(session))

    elif kind == "unlock" and session.phase == "survey" and not session.unlocked:
        session.unlocked = True
        await _broadcast_students(session, {"type": "answers_unlocked"})
        await _send_teacher(session, _teacher_state(session))

    elif kind == "next" and session.phase == "survey":
        nxt = session.q_idx + 1
        if nxt >= len(session.questions):
            await _end_session(session)
        else:
            session.q_idx = nxt
            session.unlocked = False
            _reset_answered(session)
            await _broadcast_students(session, _question_msg(session))
            await _send_teacher(session, _teacher_state(session))

    elif kind == "prev" and session.phase == "survey" and session.q_idx > 0:
        session.q_idx -= 1
        session.unlocked = False
        _reset_answered(session)
        await _broadcast_students(session, _question_msg(session))
        await _send_teacher(session, _teacher_state(session))

    elif kind == "end":
        await _end_session(session)


# ── Student message handler ───────────────────────────────────────────────────

async def _handle_student_msg(
    session: GuidedSession, student_id: str, msg: dict
) -> None:
    if msg.get("type") != "answer":
        return
    if not session.unlocked or session.phase != "survey":
        return

    student = session.students.get(student_id)
    if student is None or student.answered_current:
        return

    q = session.questions[session.q_idx]
    q_id = msg.get("q_id", "")
    value = msg.get("value", "")
    if q_id != q["id"] or not value:
        return

    student.answers[q_id] = value
    student.answered_current = True

    answered = sum(1 for s in session.students.values() if s.answered_current)
    await _notify_teacher(session, {
        "type": "answer_progress",
        "answered": answered,
        "total": len(session.students),
    })
    try:
        await student.ws.send_json({"type": "answer_received", "q_id": q_id})
    except Exception:
        pass


# ── End session & save ────────────────────────────────────────────────────────

async def _end_session(session: GuidedSession) -> None:
    session.phase = "ended"

    saved = 0
    db = get_db()
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
    try:
        for student in session.students.values():
            if student.answers:
                db.execute(
                    "INSERT INTO responses (survey_id, class_name, submitted_at, payload_json)"
                    " VALUES (?, ?, ?, ?)",
                    (session.survey_id, session.class_name, now, json.dumps(student.answers)),
                )
                saved += 1
        db.commit()
    finally:
        db.close()

    await _broadcast_students(session, {"type": "session_ended"})
    await _send_teacher(session, {"type": "session_ended", "saved": saved})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_answered(session: GuidedSession) -> None:
    for s in session.students.values():
        s.answered_current = False


def _teacher_state(session: GuidedSession) -> dict:
    q = session.questions[session.q_idx] if session.questions else None
    answered = sum(1 for s in session.students.values() if s.answered_current)
    return {
        "type": "state",
        "phase": session.phase,
        "q_idx": session.q_idx,
        "total": len(session.questions),
        "question": q,
        "scale": session.scale,
        "unlocked": session.unlocked,
        "student_count": len(session.students),
        "answered": answered,
    }


def _question_msg(session: GuidedSession) -> dict:
    q = session.questions[session.q_idx]
    return {
        "type": "question",
        "q_idx": session.q_idx,
        "total": len(session.questions),
        "question": q,
        "scale": session.scale,
        "unlocked": False,
    }


async def _send_student_state(session: GuidedSession, student_id: str) -> None:
    student = session.students.get(student_id)
    if student is None:
        return
    if session.phase == "lobby":
        msg: dict = {"type": "waiting"}
    elif session.phase == "survey":
        q = session.questions[session.q_idx]
        msg = {
            "type": "question",
            "q_idx": session.q_idx,
            "total": len(session.questions),
            "question": q,
            "scale": session.scale,
            "unlocked": session.unlocked and not student.answered_current,
            "already_answered": student.answered_current,
        }
    else:
        msg = {"type": "session_ended"}
    try:
        await student.ws.send_json(msg)
    except Exception:
        pass


async def _broadcast_students(session: GuidedSession, msg: dict) -> None:
    dead: list[str] = []
    for sid, student in list(session.students.items()):
        try:
            await student.ws.send_json(msg)
        except Exception:
            dead.append(sid)
    for sid in dead:
        session.students.pop(sid, None)


async def _notify_teacher(session: GuidedSession, msg: dict) -> None:
    if session.teacher_ws:
        try:
            await session.teacher_ws.send_json(msg)
        except Exception:
            session.teacher_ws = None


async def _send_teacher(session: GuidedSession, msg: dict) -> None:
    await _notify_teacher(session, msg)


# ── Public results presentation ───────────────────────────────────────────────

@router.get("/ergebnisse/{token}", response_class=HTMLResponse)
async def public_results(request: Request, token: str, class_name: str | None = None):
    conn = get_db()
    try:
        grant = conn.execute(
            "SELECT * FROM share_grants WHERE token = ?", (token,)
        ).fetchone()
        if grant is None:
            raise HTTPException(404, "Dieser Link ist ungültig oder wurde deaktiviert.")
        survey = conn.execute(
            "SELECT * FROM surveys WHERE id = ?", (grant["survey_id"],)
        ).fetchone()
        if survey is None:
            raise HTTPException(404)

        if grant["scope"] == "all":
            classes = conn.execute(
                "SELECT name FROM classes WHERE survey_id = ? ORDER BY name", (survey["id"],)
            ).fetchall()
            class_names = [c["name"] for c in classes]
            active_class = class_name
        else:
            class_names = [grant["scope"]]
            active_class = grant["scope"]
    finally:
        conn.close()

    q_path = SURVEYS_DIR / f"{survey['questionnaire_id']}.json"
    if not q_path.exists():
        raise HTTPException(404)
    questionnaire = json.loads(q_path.read_text(encoding="utf-8"))

    eval_result = evaluate_survey(survey["id"], questionnaire, active_class)

    if grant["scope"] == "all":
        filter_label = class_name if class_name else "Schule gesamt"
    else:
        filter_label = f"Klasse {grant['scope']}"

    return templates.TemplateResponse(request, "ergebnisse.html", {
        "survey": dict(survey),
        "eval_result": eval_result,
        "questionnaire": questionnaire,
        "class_names": class_names if grant["scope"] == "all" else [],
        "selected_class": active_class if grant["scope"] == "all" else None,
        "filter_label": filter_label,
        "grant_scope": grant["scope"],
        "token": token,
    })
