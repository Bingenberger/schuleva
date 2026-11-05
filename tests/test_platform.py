"""Plattformbetrieb: expliziter Migrationsschritt, Readiness, Fragebögen im Datenvolume, Konfiguration."""
import importlib
import json
import sqlite3
import sys

import pytest

LEGACY = """
CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('schulleitung')), must_change_password INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL);
CREATE TABLE surveys (id INTEGER PRIMARY KEY, title TEXT NOT NULL,
  survey_type TEXT NOT NULL CHECK(survey_type IN ('eltern_kl4', 'kinder_kl4')), questionnaire_id TEXT NOT NULL,
  starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('draft','active','closed')),
  created_at TEXT NOT NULL);
CREATE TABLE classes (id INTEGER PRIMARY KEY, survey_id INTEGER NOT NULL REFERENCES surveys(id) ON DELETE CASCADE,
  name TEXT NOT NULL, UNIQUE(survey_id, name));
CREATE TABLE tans (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, class_id INTEGER NOT NULL REFERENCES classes(id),
  survey_id INTEGER NOT NULL REFERENCES surveys(id), used_at TEXT, created_at TEXT NOT NULL);
CREATE TABLE responses (id INTEGER PRIMARY KEY, survey_id INTEGER NOT NULL REFERENCES surveys(id),
  class_name TEXT NOT NULL, submitted_at TEXT NOT NULL, payload_json TEXT NOT NULL);
INSERT INTO users VALUES (1, 'sl', 'x', 'schulleitung', 0, '2025-01-01');
INSERT INTO surveys VALUES (1, 'Elternbefragung 2025', 'eltern_kl4', 'eltern_kl4', '2025-01-01', '2025-02-01', 'closed', '2025-01-01');
INSERT INTO classes VALUES (1, 1, '4a');
INSERT INTO responses VALUES (1, 1, '4a', '2025-01-10T10:00:00+00:00', '{"q1": 4}');
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("SURVEYS_DIR", str(tmp_path / "surveys"))
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    monkeypatch.setenv("BASE_URL", "https://befragung.schule.example")
    monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        sys.modules.pop(name)
    return tmp_path


def client():
    from fastapi.testclient import TestClient
    return TestClient(importlib.import_module("app.main").app)


def test_not_ready_and_no_schema_before_migration(env):
    c = client()
    assert c.get("/health/live").status_code == 200
    assert c.get("/health/ready").status_code == 503
    assert not (env / "db.sqlite").exists()


def test_fresh_migration_seeds_surveys_and_is_repeatable(env):
    from app import migrate
    assert "angelegt" in migrate.migrate()
    assert {p.stem for p in (env / "surveys").glob("*.json")} >= {"eltern_kl4", "kinder_kl4"}
    assert oct((env / "db.sqlite").stat().st_mode & 0o777) == "0o600"
    assert client().get("/health/ready").status_code == 200
    assert "aktuell" in migrate.migrate()


def test_legacy_database_is_adopted_without_data_loss(env):
    conn = sqlite3.connect(env / "db.sqlite")
    conn.executescript(LEGACY)
    conn.close()
    (env / "surveys").mkdir()
    (env / "surveys" / "eltern_kl4.json").write_text(json.dumps({"id": "eltern_kl4", "title": "eigene Fassung"}))
    from app import migrate
    assert "übernommen" in migrate.migrate()
    conn = sqlite3.connect(env / "db.sqlite")
    assert conn.execute("SELECT payload_json FROM responses").fetchone()[0] == '{"q1": 4}'
    assert "lehrer" in conn.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()[0]
    conn.execute("INSERT INTO users VALUES (2,'lk','x','lehrer',1,'2025')")
    assert json.loads((env / "surveys" / "eltern_kl4.json").read_text())["title"] == "eigene Fassung"


def test_newer_schema_is_refused(env):
    conn = sqlite3.connect(env / "db.sqlite")
    conn.executescript("CREATE TABLE schema_version (version INTEGER PRIMARY KEY); INSERT INTO schema_version VALUES (2);")
    conn.close()
    from app import migrate
    with pytest.raises(migrate.MigrationError):
        migrate.migrate()


@pytest.mark.parametrize("value", ["", "kurz", "CHANGE-ME-IN-PRODUCTION-secret-key-placeholder"])
def test_secret_key_is_required(env, monkeypatch, value):
    monkeypatch.setenv("SECRET_KEY", value)
    with pytest.raises(RuntimeError):
        client()


def test_secure_cookie_and_tan_url_follow_base_url(env):
    from app import migrate
    migrate.migrate()
    from app.services import pdf_tans
    assert pdf_tans.SCHOOL_DOMAIN == "befragung.schule.example"
    cookies = client().get("/admin/login").headers.get_list("set-cookie")
    assert cookies and all("secure" in c.lower() for c in cookies)


def test_proxy_trust_only_for_explicit_addresses(env, monkeypatch):
    from app import serve
    monkeypatch.setenv("PROXY_IPS", "10.231.12.2")
    assert serve.options()["forwarded_allow_ips"] == "10.231.12.2" and serve.options()["proxy_headers"]
    monkeypatch.setenv("PROXY_IPS", "")
    assert serve.options()["proxy_headers"] is False
    monkeypatch.setenv("PROXY_IPS", "*")
    with pytest.raises(ValueError):
        serve.options()
    assert serve.options.__module__ == "app.serve" and serve.options is not None


def test_questionnaire_editor_writes_into_surveys_dir(env):
    from app import migrate
    from app.routes import admin
    migrate.migrate()
    assert admin.SURVEYS_DIR == env / "surveys"
