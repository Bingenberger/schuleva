from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

from app.auth import (
    authenticate_user, get_current_user, require_login, require_admin,
    generate_csrf_token, validate_csrf, change_password,
    is_locked_out, record_failed, clear_attempts,
    create_user, delete_user,
)
from app.db import get_db
from app.i18n import t
from app.services.tan import generate_tans
from app.services.evaluation import evaluate_survey

router = APIRouter(prefix="/admin")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["t"] = t

SURVEYS_DIR = Path(__file__).parent.parent.parent / "surveys"


def _available_questionnaires() -> list[str]:
    return [p.stem for p in SURVEYS_DIR.glob("*.json")]


def _load_questionnaire(qid: str) -> dict[str, Any]:
    path = SURVEYS_DIR / f"{qid}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Login ────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if get_current_user(request):
        return RedirectResponse("/admin/", status_code=303)
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(request, "admin/login.html", {"csrf": csrf, "error": None})


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    ip = _get_client_ip(request)

    if is_locked_out(ip):
        csrf = generate_csrf_token(request)
        return templates.TemplateResponse(
            request, "admin/login.html",
            {"csrf": csrf, "error": "Zu viele Fehlversuche. Bitte 15 Minuten warten."},
            status_code=429,
        )

    user = authenticate_user(username, password)
    if user is None:
        record_failed(ip)
        csrf = generate_csrf_token(request)
        return templates.TemplateResponse(
            request, "admin/login.html",
            {"csrf": csrf, "error": "Benutzername oder Passwort falsch."},
            status_code=401,
        )

    clear_attempts(ip)
    request.session["user_id"] = user.id

    if user.must_change_password:
        return RedirectResponse("/admin/change-password", status_code=303)
    return RedirectResponse("/admin/", status_code=303)


@router.post("/logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/change-password", response_class=HTMLResponse)
async def change_pw_form(request: Request):
    user = require_login(request)
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(
        request, "admin/change_password.html",
        {"csrf": csrf, "error": None, "user": user},
    )


@router.post("/change-password")
async def change_pw_post(
    request: Request,
    new_password: str = Form(...),
    new_password2: str = Form(...),
    csrf_token: str = Form(...),
):
    user = require_login(request)
    validate_csrf(request, csrf_token)
    csrf = generate_csrf_token(request)

    if new_password != new_password2:
        return templates.TemplateResponse(
            request, "admin/change_password.html",
            {"csrf": csrf, "error": "Passwörter stimmen nicht überein.", "user": user},
        )
    if len(new_password) < 10:
        return templates.TemplateResponse(
            request, "admin/change_password.html",
            {"csrf": csrf, "error": "Passwort muss mindestens 10 Zeichen haben.", "user": user},
        )

    change_password(user.id, new_password)
    return RedirectResponse("/admin/", status_code=303)


# ── Survey overview ──────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def admin_overview(request: Request):
    user = require_login(request)
    conn = get_db()
    try:
        surveys = conn.execute(
            "SELECT * FROM surveys ORDER BY created_at DESC"
        ).fetchall()
        survey_stats = []
        for s in surveys:
            total_tans = conn.execute(
                "SELECT COUNT(*) FROM tans WHERE survey_id = ?", (s["id"],)
            ).fetchone()[0]
            used_tans = conn.execute(
                "SELECT COUNT(*) FROM tans WHERE survey_id = ? AND used_at IS NOT NULL", (s["id"],)
            ).fetchone()[0]
            responses = conn.execute(
                "SELECT COUNT(*) FROM responses WHERE survey_id = ?", (s["id"],)
            ).fetchone()[0]
            survey_stats.append({
                **dict(s),
                "total_tans": total_tans,
                "used_tans": used_tans,
                "responses": responses,
            })
    finally:
        conn.close()

    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(
        request, "admin/overview.html",
        {"surveys": survey_stats, "user": user, "csrf": csrf},
    )


# ── New survey ───────────────────────────────────────────────────────────────

@router.get("/survey/new", response_class=HTMLResponse)
async def survey_new_form(request: Request):
    user = require_login(request)
    csrf = generate_csrf_token(request)
    questionnaires = _available_questionnaires()
    return templates.TemplateResponse(
        request, "admin/survey_new.html",
        {"csrf": csrf, "questionnaires": questionnaires, "user": user, "error": None},
    )


@router.post("/survey")
async def survey_create(
    request: Request,
    title: str = Form(...),
    survey_type: str = Form(...),
    questionnaire_id: str = Form(...),
    starts_at: str = Form(...),
    ends_at: str = Form(...),
    csrf_token: str = Form(...),
):
    user = require_login(request)
    validate_csrf(request, csrf_token)

    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO surveys (title, survey_type, questionnaire_id, starts_at, ends_at, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?)""",
            (title, survey_type, questionnaire_id, starts_at, ends_at, _now()),
        )
        survey_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse(f"/admin/survey/{survey_id}", status_code=303)


# ── Survey detail ────────────────────────────────────────────────────────────

@router.get("/survey/{survey_id}", response_class=HTMLResponse)
async def survey_detail(request: Request, survey_id: int):
    user = require_login(request)
    conn = get_db()
    try:
        survey = conn.execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone()
        if survey is None:
            raise HTTPException(404, "Befragung nicht gefunden")

        classes = conn.execute(
            "SELECT * FROM classes WHERE survey_id = ? ORDER BY name", (survey_id,)
        ).fetchall()

        class_stats = []
        for cls in classes:
            total = conn.execute(
                "SELECT COUNT(*) FROM tans WHERE class_id = ?", (cls["id"],)
            ).fetchone()[0]
            used = conn.execute(
                "SELECT COUNT(*) FROM tans WHERE class_id = ? AND used_at IS NOT NULL", (cls["id"],)
            ).fetchone()[0]
            resp = conn.execute(
                "SELECT COUNT(*) FROM responses WHERE survey_id = ? AND class_name = ?",
                (survey_id, cls["name"]),
            ).fetchone()[0]
            class_stats.append({
                "id": cls["id"],
                "name": cls["name"],
                "total_tans": total,
                "used_tans": used,
                "responses": resp,
            })
        grants = [dict(g) for g in conn.execute(
            "SELECT * FROM share_grants WHERE survey_id = ? ORDER BY created_at",
            (survey_id,),
        ).fetchall()]
    finally:
        conn.close()

    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(
        request, "admin/survey_detail.html",
        {
            "survey": dict(survey),
            "class_stats": class_stats,
            "grants": grants,
            "user": user,
            "csrf": csrf,
        },
    )


@router.post("/survey/{survey_id}/classes")
async def add_class(
    request: Request,
    survey_id: int,
    class_name: str = Form(...),
    csrf_token: str = Form(...),
):
    require_login(request)
    validate_csrf(request, csrf_token)

    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO classes (survey_id, name) VALUES (?, ?)",
            (survey_id, class_name.strip()),
        )
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse(f"/admin/survey/{survey_id}", status_code=303)


@router.post("/survey/{survey_id}/tans")
async def generate_tans_route(
    request: Request,
    survey_id: int,
    class_name: str = Form(...),
    count: int = Form(...),
    csrf_token: str = Form(...),
):
    require_login(request)
    validate_csrf(request, csrf_token)

    conn = get_db()
    try:
        survey = conn.execute("SELECT survey_type FROM surveys WHERE id = ?", (survey_id,)).fetchone()
        cls = conn.execute(
            "SELECT id FROM classes WHERE survey_id = ? AND name = ?",
            (survey_id, class_name),
        ).fetchone()
    finally:
        conn.close()

    if survey is None or cls is None:
        raise HTTPException(404, "Befragung oder Klasse nicht gefunden")

    generate_tans(survey_id, cls["id"], class_name, survey["survey_type"], count)
    return RedirectResponse(f"/admin/survey/{survey_id}", status_code=303)


@router.post("/survey/{survey_id}/close")
async def close_survey(
    request: Request,
    survey_id: int,
    csrf_token: str = Form(...),
):
    require_admin(request)
    validate_csrf(request, csrf_token)

    conn = get_db()
    try:
        conn.execute(
            "UPDATE surveys SET status = 'closed' WHERE id = ?", (survey_id,)
        )
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse(f"/admin/survey/{survey_id}", status_code=303)


@router.post("/survey/{survey_id}/delete")
async def delete_survey(
    request: Request,
    survey_id: int,
    csrf_token: str = Form(...),
):
    require_admin(request)
    validate_csrf(request, csrf_token)

    conn = get_db()
    try:
        # tans and responses have no ON DELETE CASCADE → delete manually first
        conn.execute("DELETE FROM tans WHERE survey_id = ?", (survey_id,))
        conn.execute("DELETE FROM responses WHERE survey_id = ?", (survey_id,))
        # CASCADE handles: classes, share_grants
        conn.execute("DELETE FROM surveys WHERE id = ?", (survey_id,))
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse("/admin/", status_code=303)


# ── User management ───────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request):
    user = require_admin(request)
    conn = get_db()
    try:
        users = conn.execute(
            "SELECT id, username, role, must_change_password, created_at FROM users ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(request, "admin/users.html", {
        "users": [dict(u) for u in users],
        "user": user,
        "csrf": csrf,
    })


@router.post("/users/create")
async def user_create(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    csrf_token: str = Form(...),
):
    user = require_admin(request)
    validate_csrf(request, csrf_token)
    csrf = generate_csrf_token(request)

    errors = []
    if len(username) < 3:
        errors.append("Benutzername muss mindestens 3 Zeichen haben")
    if len(password) < 10:
        errors.append("Passwort muss mindestens 10 Zeichen haben")
    if role not in ("schulleitung", "lehrer"):
        errors.append("Ungültige Rolle")

    if not errors:
        conn = get_db()
        try:
            exists = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
        finally:
            conn.close()
        if exists:
            errors.append(f'Benutzername "{username}" ist bereits vergeben')

    if errors:
        conn = get_db()
        try:
            users = conn.execute(
                "SELECT id, username, role, must_change_password, created_at FROM users ORDER BY created_at"
            ).fetchall()
        finally:
            conn.close()
        return templates.TemplateResponse(request, "admin/users.html", {
            "users": [dict(u) for u in users],
            "user": user,
            "csrf": csrf,
            "errors": errors,
            "form": {"username": username, "role": role},
        })

    create_user(username, password, role)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/delete")
async def user_delete(
    request: Request,
    user_id: int,
    csrf_token: str = Form(...),
):
    current = require_admin(request)
    validate_csrf(request, csrf_token)
    if current.id == user_id:
        raise HTTPException(400, "Eigenen Account kann man nicht löschen")
    conn = get_db()
    try:
        target = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise HTTPException(404)
        # Prevent deleting last admin
        if target["role"] == "schulleitung":
            admin_count = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'schulleitung'"
            ).fetchone()[0]
            if admin_count <= 1:
                raise HTTPException(400, "Das letzte Schulleitung-Konto kann nicht gelöscht werden")
    finally:
        conn.close()
    delete_user(user_id)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/reset-password")
async def user_reset_password(
    request: Request,
    user_id: int,
    new_password: str = Form(...),
    csrf_token: str = Form(...),
):
    require_admin(request)
    validate_csrf(request, csrf_token)
    if len(new_password) < 10:
        raise HTTPException(400, "Passwort muss mindestens 10 Zeichen haben")
    change_password(user_id, new_password)
    # Force password change on next login
    conn = get_db()
    try:
        conn.execute("UPDATE users SET must_change_password = 1 WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse("/admin/users", status_code=303)


# ── Results ──────────────────────────────────────────────────────────────────

@router.get("/survey/{survey_id}/results", response_class=HTMLResponse)
async def results_view(request: Request, survey_id: int, class_name: str | None = None):
    user = require_login(request)
    conn = get_db()
    try:
        survey = conn.execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone()
        if survey is None:
            raise HTTPException(404)
        classes = conn.execute(
            "SELECT name FROM classes WHERE survey_id = ? ORDER BY name", (survey_id,)
        ).fetchall()
        class_names = [c["name"] for c in classes]
        grants = [dict(g) for g in conn.execute(
            "SELECT * FROM share_grants WHERE survey_id = ? ORDER BY created_at",
            (survey_id,),
        ).fetchall()]
    finally:
        conn.close()

    questionnaire = _load_questionnaire(survey["questionnaire_id"])
    eval_result = evaluate_survey(survey_id, questionnaire, class_name)

    filter_label = class_name if class_name else "Schule gesamt"
    csrf = generate_csrf_token(request)

    return templates.TemplateResponse(
        request, "admin/results.html",
        {
            "survey": dict(survey),
            "eval_result": eval_result,
            "questionnaire": questionnaire,
            "class_names": class_names,
            "selected_class": class_name,
            "filter_label": filter_label,
            "grants": grants,
            "user": user,
            "csrf": csrf,
        },
    )


# ── Questionnaire management ──────────────────────────────────────────────────

def _validate_qid(qid: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9_]+$', qid))


def _validate_questionnaire(data: dict) -> list[str]:
    errors: list[str] = []
    for field in ("id", "title", "sections"):
        if field not in data:
            errors.append(f"Pflichtfeld '{field}' fehlt")
    if errors:
        return errors
    if not isinstance(data["sections"], list) or len(data["sections"]) == 0:
        errors.append("'sections' muss eine nicht-leere Liste sein")
        return errors
    for i, sec in enumerate(data["sections"], 1):
        for f in ("id", "title", "questions"):
            if f not in sec:
                errors.append(f"Abschnitt {i}: Feld '{f}' fehlt")
        if "questions" in sec:
            if not isinstance(sec["questions"], list):
                errors.append(f"Abschnitt {i}: 'questions' muss eine Liste sein")
            else:
                for j, q in enumerate(sec["questions"], 1):
                    for f in ("id", "type", "text"):
                        if f not in q:
                            errors.append(f"Abschnitt {i}, Frage {j}: Feld '{f}' fehlt")
    return errors


def _questionnaire_usage(qid: str) -> int:
    conn = get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM surveys WHERE questionnaire_id = ?", (qid,)
        ).fetchone()[0]
    finally:
        conn.close()


@router.get("/questionnaires", response_class=HTMLResponse)
async def questionnaires_list(request: Request):
    user = require_login(request)
    csrf = generate_csrf_token(request)
    conn = get_db()
    try:
        items = []
        for p in sorted(SURVEYS_DIR.glob("*.json")):
            qid = p.stem
            usage = conn.execute(
                "SELECT COUNT(*) FROM surveys WHERE questionnaire_id = ?", (qid,)
            ).fetchone()[0]
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                title = data.get("title", qid)
                n_sections = len(data.get("sections", []))
                n_questions = sum(len(s.get("questions", [])) for s in data.get("sections", []))
            except Exception:
                title = f"{qid} (ungültig)"
                n_sections = n_questions = 0
            items.append({
                "id": qid,
                "title": title,
                "n_sections": n_sections,
                "n_questions": n_questions,
                "usage": usage,
            })
    finally:
        conn.close()
    return templates.TemplateResponse(request, "admin/questionnaires.html", {
        "items": items, "user": user, "csrf": csrf,
    })


@router.get("/questionnaire/new", response_class=HTMLResponse)
async def questionnaire_new_get(request: Request):
    user = require_login(request)
    csrf = generate_csrf_token(request)
    blank = {
        "id": "neuer_fragebogen",
        "version": 1,
        "title": "Neuer Fragebogen",
        "intro": "",
        "scale": {
            "id": "4stufig",
            "options": [
                {"value": "trifft_zu",  "label": "Trifft zu"},
                {"value": "teilweise",  "label": "Trifft teilweise zu"},
                {"value": "eher_nicht", "label": "Trifft eher nicht zu"},
                {"value": "nicht",      "label": "Trifft nicht zu"}
            ]
        },
        "sections": [
            {
                "id": "abschnitt1",
                "title": "Abschnitt 1",
                "questions": [
                    {"id": "q01", "type": "scale", "text": "Beispielfrage"}
                ]
            }
        ]
    }
    return templates.TemplateResponse(request, "admin/questionnaire_edit.html", {
        "qid": None,
        "title": "Neuen Fragebogen anlegen",
        "content": json.dumps(blank, indent=2, ensure_ascii=False),
        "usage": 0,
        "user": user, "csrf": csrf, "errors": [],
    })


@router.post("/questionnaire/new")
async def questionnaire_new_post(
    request: Request,
    content: str = Form(...),
    csrf_token: str = Form(...),
):
    user = require_login(request)
    validate_csrf(request, csrf_token)

    def _err(errors):
        csrf = generate_csrf_token(request)
        return templates.TemplateResponse(request, "admin/questionnaire_edit.html", {
            "qid": None, "title": "Neuen Fragebogen anlegen",
            "content": content, "usage": 0,
            "user": user, "csrf": csrf, "errors": errors,
        })

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return _err([f"JSON-Fehler: {e}"])

    errors = _validate_questionnaire(data)
    qid = str(data.get("id", "")).strip()
    if not _validate_qid(qid):
        errors.append("Feld 'id' darf nur Buchstaben, Zahlen und Unterstriche enthalten")
    elif (SURVEYS_DIR / f"{qid}.json").exists():
        errors.append(f"Ein Fragebogen mit der ID '{qid}' existiert bereits")
    if errors:
        return _err(errors)

    (SURVEYS_DIR / f"{qid}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return RedirectResponse("/admin/questionnaires", status_code=303)


@router.get("/questionnaire/{qid}/edit", response_class=HTMLResponse)
async def questionnaire_edit_get(request: Request, qid: str):
    user = require_login(request)
    if not _validate_qid(qid):
        raise HTTPException(400, "Ungültige Fragebogen-ID")
    path = SURVEYS_DIR / f"{qid}.json"
    if not path.exists():
        raise HTTPException(404, "Fragebogen nicht gefunden")
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(request, "admin/questionnaire_edit.html", {
        "qid": qid,
        "title": f"Fragebogen bearbeiten: {qid}",
        "content": path.read_text(encoding="utf-8"),
        "usage": _questionnaire_usage(qid),
        "user": user, "csrf": csrf, "errors": [],
    })


@router.post("/questionnaire/{qid}/edit")
async def questionnaire_edit_post(
    request: Request,
    qid: str,
    content: str = Form(...),
    csrf_token: str = Form(...),
):
    user = require_login(request)
    validate_csrf(request, csrf_token)
    if not _validate_qid(qid):
        raise HTTPException(400, "Ungültige Fragebogen-ID")
    path = SURVEYS_DIR / f"{qid}.json"
    if not path.exists():
        raise HTTPException(404, "Fragebogen nicht gefunden")

    usage = _questionnaire_usage(qid)

    def _err(errors):
        csrf = generate_csrf_token(request)
        return templates.TemplateResponse(request, "admin/questionnaire_edit.html", {
            "qid": qid, "title": f"Fragebogen bearbeiten: {qid}",
            "content": content, "usage": usage,
            "user": user, "csrf": csrf, "errors": errors,
        })

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return _err([f"JSON-Fehler: {e}"])

    errors = _validate_questionnaire(data)
    if str(data.get("id", "")).strip() != qid:
        errors.append(
            f"Die ID darf beim Bearbeiten nicht geändert werden "
            f"(erwartet: '{qid}'). Nutze 'Duplizieren', um eine Kopie mit neuer ID anzulegen."
        )
    if errors:
        return _err(errors)

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return RedirectResponse("/admin/questionnaires", status_code=303)


@router.get("/questionnaire/{qid}/download")
async def questionnaire_download(request: Request, qid: str):
    require_login(request)
    if not _validate_qid(qid):
        raise HTTPException(400, "Ungültige Fragebogen-ID")
    path = SURVEYS_DIR / f"{qid}.json"
    if not path.exists():
        raise HTTPException(404, "Fragebogen nicht gefunden")
    return FileResponse(
        str(path),
        media_type="application/json",
        filename=f"{qid}.json",
    )


@router.post("/questionnaire/{qid}/duplicate")
async def questionnaire_duplicate(
    request: Request,
    qid: str,
    new_id: str = Form(...),
    csrf_token: str = Form(...),
):
    require_login(request)
    validate_csrf(request, csrf_token)
    if not _validate_qid(qid):
        raise HTTPException(400, "Ungültige Fragebogen-ID")
    src = SURVEYS_DIR / f"{qid}.json"
    if not src.exists():
        raise HTTPException(404, "Fragebogen nicht gefunden")

    new_id = new_id.strip()
    if not _validate_qid(new_id):
        raise HTTPException(400, "Neue ID ungültig – nur Buchstaben, Zahlen und Unterstriche erlaubt")
    dst = SURVEYS_DIR / f"{new_id}.json"
    if dst.exists():
        raise HTTPException(409, f"Fragebogen '{new_id}' existiert bereits")

    data = json.loads(src.read_text(encoding="utf-8"))
    data["id"] = new_id
    dst.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return RedirectResponse(f"/admin/questionnaire/{new_id}/edit", status_code=303)


@router.post("/questionnaire/{qid}/delete")
async def questionnaire_delete(
    request: Request,
    qid: str,
    csrf_token: str = Form(...),
):
    require_login(request)
    validate_csrf(request, csrf_token)
    if not _validate_qid(qid):
        raise HTTPException(400, "Ungültige Fragebogen-ID")
    path = SURVEYS_DIR / f"{qid}.json"
    if not path.exists():
        raise HTTPException(404, "Fragebogen nicht gefunden")
    usage = _questionnaire_usage(qid)
    if usage > 0:
        raise HTTPException(
            409, f"Fragebogen wird von {usage} Befragung(en) verwendet und kann nicht gelöscht werden"
        )
    path.unlink()
    return RedirectResponse("/admin/questionnaires", status_code=303)
