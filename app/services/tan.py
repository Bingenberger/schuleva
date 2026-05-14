from __future__ import annotations
import secrets
import sqlite3
from datetime import datetime, timezone

from app.db import get_db

# No visually ambiguous characters
SAFE_CHARS = "ABCDEFGHJKLMNPQRTUVWXYZ23467889"


def _generate_code(prefix: str) -> str:
    part1 = "".join(secrets.choice(SAFE_CHARS) for _ in range(4))
    part2 = "".join(secrets.choice(SAFE_CHARS) for _ in range(4))
    return f"{prefix}-{part1}-{part2}"


def _tan_prefix(survey_type: str) -> str:
    return "E4" if survey_type == "eltern_kl4" else "K4"


def generate_tans(survey_id: int, class_id: int, class_name: str, survey_type: str, count: int) -> list[str]:
    prefix = _tan_prefix(survey_type)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        existing = {
            row[0]
            for row in conn.execute("SELECT code FROM tans WHERE survey_id = ?", (survey_id,))
        }
        new_codes: list[str] = []
        attempts = 0
        while len(new_codes) < count:
            if attempts > count * 100:
                raise RuntimeError("Konnte nicht genug eindeutige TANs generieren")
            code = _generate_code(prefix)
            if code not in existing:
                existing.add(code)
                new_codes.append(code)
            attempts += 1

        conn.executemany(
            "INSERT INTO tans (code, class_id, survey_id, created_at) VALUES (?, ?, ?, ?)",
            [(code, class_id, survey_id, now) for code in new_codes],
        )
        conn.commit()
        return new_codes
    finally:
        conn.close()


def redeem_tan(tan_code: str) -> dict | None:
    """
    Atomically marks TAN as used and returns class_name + survey_id.
    Returns None if TAN is invalid or already used.
    The caller is responsible for inserting the response in the same connection.
    """
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT t.id, t.survey_id, c.name AS class_name, s.status, s.ends_at
            FROM tans t
            JOIN classes c ON c.id = t.class_id
            JOIN surveys s ON s.id = t.survey_id
            WHERE t.code = ? AND t.used_at IS NULL
            """,
            (tan_code,),
        ).fetchone()

        if row is None:
            conn.rollback()
            return None

        if row["status"] != "active":
            conn.rollback()
            return None

        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE tans SET used_at = ? WHERE id = ?",
            (now_iso, row["id"]),
        )
        conn.commit()
        return {
            "survey_id": row["survey_id"],
            "class_name": row["class_name"],
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def validate_tan(tan_code: str) -> dict | None:
    """Check TAN without consuming it. Returns metadata or None."""
    conn = get_db()
    try:
        row = conn.execute(
            """
            SELECT t.survey_id, c.name AS class_name, s.status, s.questionnaire_id, s.ends_at, s.title
            FROM tans t
            JOIN classes c ON c.id = t.class_id
            JOIN surveys s ON s.id = t.survey_id
            WHERE t.code = ? AND t.used_at IS NULL
            """,
            (tan_code,),
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "active":
            return None
        return dict(row)
    finally:
        conn.close()
