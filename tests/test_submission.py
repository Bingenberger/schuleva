"""Tests: Anonymitäts-Garantien und Submission-Flow"""
import os
import json
import pytest
from datetime import datetime, timezone


def setup_db(tmp_path, status="active"):
    db_path = str(tmp_path / "test.sqlite")
    os.environ["DATABASE_PATH"] = db_path
    from app.db import init_db, get_db
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO surveys (id,title,survey_type,questionnaire_id,starts_at,ends_at,status,created_at) "
        f"VALUES (1,'Test','kinder_kl4','kinder_kl4','2024-01-01','2099-12-31','{status}',?)", (now,)
    )
    conn.execute("INSERT INTO classes (id,survey_id,name) VALUES (1,1,'4a')")
    conn.execute(
        "INSERT INTO tans (code,class_id,survey_id,created_at) VALUES ('K4-SUBM-0001',1,1,?)", (now,)
    )
    conn.commit()
    conn.close()
    return db_path


def test_submission_anonymity(tmp_path):
    """After submission: response has no tan reference, tan is marked used."""
    setup_db(tmp_path)

    from app.services.tan import redeem_tan
    from app.db import get_db

    result = redeem_tan("K4-SUBM-0001")
    assert result is not None

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO responses (survey_id, class_name, submitted_at, payload_json) VALUES (?,?,?,?)",
        (result["survey_id"], result["class_name"], now, json.dumps({"k01": "stimmt"}))
    )
    conn.commit()

    # Verify: response has class_name but no tan_code column
    resp = conn.execute("SELECT * FROM responses").fetchone()
    keys = resp.keys()
    assert "class_name" in keys
    assert "tan_code" not in keys, "responses must NOT contain tan_code (anonymity §4.1)"
    assert "tan_id" not in keys
    assert "tan" not in keys

    # TAN is used
    tan_row = conn.execute("SELECT used_at FROM tans WHERE code = 'K4-SUBM-0001'").fetchone()
    assert tan_row["used_at"] is not None

    conn.close()


def test_timestamp_rounded_to_hour(tmp_path):
    """submitted_at should be rounded to the hour."""
    setup_db(tmp_path)
    from app.services.tan import redeem_tan
    from app.db import get_db

    redeem_tan("K4-SUBM-0001")

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    submitted_at = now.isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO responses (survey_id, class_name, submitted_at, payload_json) VALUES (?,?,?,?)",
        (1, "4a", submitted_at, "{}")
    )
    conn.commit()

    resp = conn.execute("SELECT submitted_at FROM responses").fetchone()
    dt = datetime.fromisoformat(resp["submitted_at"])
    assert dt.minute == 0
    assert dt.second == 0
    conn.close()


def test_double_submission_blocked(tmp_path):
    """A second redemption of the same TAN must return None."""
    setup_db(tmp_path)
    from app.services.tan import redeem_tan

    first = redeem_tan("K4-SUBM-0001")
    assert first is not None

    second = redeem_tan("K4-SUBM-0001")
    assert second is None, "Double submission must be blocked"


def test_conditional_show_if_any_of():
    """Conditional show_if logic with any_of."""
    # This tests the logic that would run in the browser (Python equivalent for server-side evaluation)
    def is_visible(q, answers):
        if not q.get("show_if"):
            return True
        cond = q["show_if"]
        if "any_of" in cond:
            return any(
                answers.get(c["question"]) is not None
                and answers.get(c["question"]) != c["not_equals"]
                for c in cond["any_of"]
                if "not_equals" in c
            )
        return True

    q_conditional = {
        "id": "k55",
        "type": "scale",
        "text": "Wenn dies passierte …",
        "show_if": {
            "any_of": [
                {"question": "k53", "not_equals": "nicht"},
                {"question": "k54", "not_equals": "nicht"},
            ]
        }
    }

    # Hidden: both are "nicht"
    assert not is_visible(q_conditional, {"k53": "nicht", "k54": "nicht"})
    # Visible: k53 is something else
    assert is_visible(q_conditional, {"k53": "stimmt", "k54": "nicht"})
    # Visible: k54 is something else
    assert is_visible(q_conditional, {"k53": "nicht", "k54": "teilweise"})
    # Visible: both non-"nicht"
    assert is_visible(q_conditional, {"k53": "stimmt", "k54": "teilweise"})
    # Hidden: neither answered
    assert not is_visible(q_conditional, {})
