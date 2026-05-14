"""Tests: TAN-Generierung und -Einlösung"""
import os
import pytest

os.environ.setdefault("DATABASE_PATH", ":memory:")

# We need a proper in-memory db for each test
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch


def make_in_memory_db():
    from app.db import SCHEMA
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def test_tan_format():
    from app.services.tan import _generate_code, SAFE_CHARS
    for _ in range(100):
        code = _generate_code("K4")
        parts = code.split("-")
        assert len(parts) == 3, f"Expected 3 parts, got: {code}"
        assert parts[0] == "K4"
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        # No ambiguous chars
        for ch in parts[1] + parts[2]:
            assert ch in SAFE_CHARS, f"Ambiguous char {ch!r} in TAN {code}"


def test_safe_chars_no_ambiguous():
    from app.services.tan import SAFE_CHARS
    for bad in ("0", "O", "1", "I", "l", "5", "S"):
        assert bad not in SAFE_CHARS, f"{bad!r} should not be in SAFE_CHARS"


def test_tan_uniqueness_within_survey():
    from app.services.tan import _generate_code, SAFE_CHARS
    codes = {_generate_code("K4") for _ in range(500)}
    # With ~31^8 possibilities, collisions in 500 draws are astronomically unlikely
    assert len(codes) == 500


def test_tan_prefix_eltern():
    from app.services.tan import _tan_prefix
    assert _tan_prefix("eltern_kl4") == "E4"


def test_tan_prefix_kinder():
    from app.services.tan import _tan_prefix
    assert _tan_prefix("kinder_kl4") == "K4"


def test_redeem_tan_marks_used(tmp_path):
    """Atomically redeeming a TAN sets used_at; second redeem returns None."""
    db_path = str(tmp_path / "test.sqlite")
    os.environ["DATABASE_PATH"] = db_path

    from app.db import init_db, get_db
    init_db()

    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO surveys (id,title,survey_type,questionnaire_id,starts_at,ends_at,status,created_at) "
        "VALUES (1,'Test','kinder_kl4','kinder_kl4','2024-01-01','2099-12-31','active',?)", (now,)
    )
    conn.execute(
        "INSERT INTO classes (id,survey_id,name) VALUES (1,1,'4a')"
    )
    conn.execute(
        "INSERT INTO tans (code,class_id,survey_id,created_at) VALUES ('K4-TEST-0001',1,1,?)", (now,)
    )
    conn.commit()
    conn.close()

    from app.services.tan import redeem_tan
    result = redeem_tan("K4-TEST-0001")
    assert result is not None
    assert result["class_name"] == "4a"
    assert result["survey_id"] == 1

    # Second attempt must fail
    result2 = redeem_tan("K4-TEST-0001")
    assert result2 is None


def test_no_fk_between_tans_and_responses(tmp_path):
    """responses table must NOT have a foreign key reference to tans."""
    db_path = str(tmp_path / "fk_test.sqlite")
    os.environ["DATABASE_PATH"] = db_path

    from app.db import init_db, get_db
    init_db()

    conn = get_db()
    # Get schema for responses table
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='responses'"
    ).fetchall()
    conn.close()

    schema = rows[0]["sql"].lower() if rows else ""
    # Must not contain reference to tans
    assert "tans" not in schema, \
        "responses table must not reference tans (anonymity requirement §4.1)"


def test_validate_tan_returns_none_for_used(tmp_path):
    db_path = str(tmp_path / "validate.sqlite")
    os.environ["DATABASE_PATH"] = db_path

    from app.db import init_db, get_db
    init_db()

    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO surveys (id,title,survey_type,questionnaire_id,starts_at,ends_at,status,created_at) "
        "VALUES (1,'Test','kinder_kl4','kinder_kl4','2024-01-01','2099-12-31','active',?)", (now,)
    )
    conn.execute("INSERT INTO classes (id,survey_id,name) VALUES (1,1,'4a')")
    conn.execute(
        "INSERT INTO tans (code,class_id,survey_id,used_at,created_at) VALUES ('K4-USED-0001',1,1,?,?)",
        (now, now)
    )
    conn.commit()
    conn.close()

    from app.services.tan import validate_tan
    assert validate_tan("K4-USED-0001") is None


def test_validate_tan_returns_none_for_closed_survey(tmp_path):
    db_path = str(tmp_path / "closed.sqlite")
    os.environ["DATABASE_PATH"] = db_path

    from app.db import init_db, get_db
    init_db()

    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO surveys (id,title,survey_type,questionnaire_id,starts_at,ends_at,status,created_at) "
        "VALUES (1,'Test','kinder_kl4','kinder_kl4','2024-01-01','2099-12-31','closed',?)", (now,)
    )
    conn.execute("INSERT INTO classes (id,survey_id,name) VALUES (1,1,'4a')")
    conn.execute(
        "INSERT INTO tans (code,class_id,survey_id,created_at) VALUES ('K4-CLOS-0001',1,1,?)", (now,)
    )
    conn.commit()
    conn.close()

    from app.services.tan import validate_tan
    assert validate_tan("K4-CLOS-0001") is None
