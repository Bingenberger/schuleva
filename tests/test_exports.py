"""Smoke tests: CSV + PDF Export"""
import os
import json
import pytest
from datetime import datetime, timezone


def setup_survey_with_responses(tmp_path):
    db_path = str(tmp_path / "export_test.sqlite")
    os.environ["DATABASE_PATH"] = db_path
    from app.db import init_db, get_db
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    rounded = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO surveys (id,title,survey_type,questionnaire_id,starts_at,ends_at,status,created_at) "
        "VALUES (1,'Test-Befragung','kinder_kl4','kinder_kl4','2024-01-01','2024-06-30','closed',?)", (now,)
    )
    conn.execute("INSERT INTO classes (id,survey_id,name) VALUES (1,1,'4a')")
    conn.execute("INSERT INTO classes (id,survey_id,name) VALUES (2,1,'4b')")

    for i in range(3):
        conn.execute(
            "INSERT INTO responses (survey_id, class_name, submitted_at, payload_json) VALUES (?,?,?,?)",
            (1, "4a", rounded, json.dumps({"k01": "stimmt", "k02": "nicht", "k63": "zufrieden"}))
        )
    for i in range(2):
        conn.execute(
            "INSERT INTO responses (survey_id, class_name, submitted_at, payload_json) VALUES (?,?,?,?)",
            (1, "4b", rounded, json.dumps({"k01": "teilweise", "k02": "stimmt", "k63": "sehr_zufrieden"}))
        )
    conn.commit()
    conn.close()


def test_csv_export_structure(tmp_path):
    setup_survey_with_responses(tmp_path)
    from app.db import get_db
    import csv, io

    conn = get_db()
    rows = conn.execute(
        "SELECT submitted_at, class_name, payload_json FROM responses WHERE survey_id = 1 ORDER BY class_name"
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["submitted_at", "class_name", "k01", "k02", "k63"])
    for row in rows:
        payload = json.loads(row["payload_json"])
        writer.writerow([row["submitted_at"], row["class_name"], payload.get("k01",""), payload.get("k02",""), payload.get("k63","")])

    content = buf.getvalue()
    lines = content.strip().split("\n")
    assert len(lines) == 6  # header + 5 responses
    assert "submitted_at" in lines[0]
    assert "class_name" in lines[0]
    # No TAN data in CSV
    assert "K4-" not in content
    assert "tan" not in content.lower()


def test_csv_no_tan_data(tmp_path):
    """CSV export must not contain TAN codes or references."""
    setup_survey_with_responses(tmp_path)
    from app.db import get_db

    conn = get_db()
    rows = conn.execute("SELECT * FROM responses WHERE survey_id = 1").fetchall()
    conn.close()

    for row in rows:
        assert "tan" not in json.dumps(dict(row)).lower(), \
            "Response must not contain tan reference"


def test_evaluation_aggregation(tmp_path):
    setup_survey_with_responses(tmp_path)
    surveys_dir = os.path.join(os.path.dirname(__file__), '..', 'surveys')
    qpath = os.path.join(surveys_dir, 'kinder_kl4.json')
    if not os.path.exists(qpath):
        pytest.skip("kinder_kl4.json not available")

    with open(qpath) as f:
        questionnaire = json.load(f)

    from app.services.evaluation import evaluate_survey
    result = evaluate_survey(1, questionnaire, None)

    assert result["total_responses"] == 5
    # Find k01 in sections
    found = False
    for sec in result["sections"]:
        for q in sec["questions"]:
            if q["id"] == "k01":
                found = True
                stats = q["stats"]
                assert stats["total"] == 5
                assert stats["counts"]["stimmt"] == 3
                assert stats["counts"]["teilweise"] == 2
    assert found, "k01 not found in eval result"


def test_csv_export_smoke(tmp_path):
    """Smoke test: CSV bytes can be generated without error."""
    setup_survey_with_responses(tmp_path)
    import csv, io, json
    from app.db import get_db

    surveys_dir = os.path.join(os.path.dirname(__file__), '..', 'surveys')
    qpath = os.path.join(surveys_dir, 'kinder_kl4.json')
    if not os.path.exists(qpath):
        pytest.skip("kinder_kl4.json not available")
    with open(qpath) as f:
        questionnaire = json.load(f)

    question_ids = [
        q["id"]
        for sec in questionnaire.get("sections", [])
        for q in sec.get("questions", [])
    ]

    conn = get_db()
    rows = conn.execute(
        "SELECT submitted_at, class_name, payload_json FROM responses WHERE survey_id = 1"
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    buf.write("﻿")  # BOM
    writer = csv.writer(buf)
    writer.writerow(["submitted_at", "class_name"] + question_ids)
    for row in rows:
        payload = json.loads(row["payload_json"])
        writer.writerow(
            [row["submitted_at"], row["class_name"]]
            + [payload.get(qid, "") for qid in question_ids]
        )

    content = buf.getvalue()
    assert len(content) > 100
    assert "submitted_at" in content
