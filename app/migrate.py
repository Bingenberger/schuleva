"""Expliziter, gesperrter Schema-Schritt (Stand 1). Aufruf: python -m app.migrate

- legt die Datenbank an oder hebt bestehende Datenbanken mit den bekannten,
  idempotenten Schritten an (Rolle 'lehrer', anon_names, share_grants)
- trägt Stand 1 in schema_version ein; ein neuerer Stand wird abgewiesen
- kopiert mitgelieferte Fragebögen in SURVEYS_DIR, sofern dort noch nicht vorhanden
  (bestehende, im Browser bearbeitete Fragebögen bleiben unverändert)
- legt nur bei gesetztem INITIAL_ADMIN_PASSWORD und leerer Benutzertabelle 'admin' an
  (nativer Altbetrieb); in der Plattform: ./install.sh app-setup schuleva
"""
from __future__ import annotations

import fcntl
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from app import db, settings


class MigrationError(Exception):
    pass


def _version(path: str) -> int:
    if path == ":memory:" or not Path(path).exists():
        return 0
    conn = sqlite3.connect(path)
    try:
        has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
        return (conn.execute("SELECT max(version) FROM schema_version").fetchone()[0] or 0) if has else 0
    finally:
        conn.close()


def seed_surveys() -> list[str]:
    settings.SURVEYS_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    if settings.SURVEYS_DIR.resolve() == settings.BUNDLED_SURVEYS.resolve():
        return copied
    for source in sorted(settings.BUNDLED_SURVEYS.glob("*.json")):
        target = settings.SURVEYS_DIR / source.name
        if not target.exists():
            shutil.copyfile(source, target)
            copied.append(source.stem)
    return copied


def migrate() -> str:
    path = db._db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".migrate.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = _version(path)
        if before > db.SCHEMA_VERSION:
            raise MigrationError(f"Datenbank hat neueren Stand {before}")
        existed = Path(path).exists()
        db.init_db()
        conn = db.get_db()
        try:
            conn.execute("DELETE FROM schema_version WHERE version <> ?", (db.SCHEMA_VERSION,))
            conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (db.SCHEMA_VERSION,))
            conn.commit()
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise MigrationError("Integritätsprüfung fehlgeschlagen")
        finally:
            conn.close()
        os.chmod(path, 0o600)
        copied = seed_surveys()
        _initial_admin()
    if not db.schema_ready():
        raise MigrationError("Schema-Prüfung nach der Migration fehlgeschlagen")
    state = "aktuell" if before == db.SCHEMA_VERSION else ("übernommen" if existed else "angelegt")
    return f"Schema {db.SCHEMA_VERSION} {state}" + (f"; Fragebögen ergänzt: {', '.join(copied)}" if copied else "")


def _initial_admin() -> None:
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if not password:
        return
    conn = db.get_db()
    try:
        empty = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    finally:
        conn.close()
    if empty:
        from app.auth import create_admin_user
        create_admin_user("admin", password)
        print("Admin-Benutzer 'admin' angelegt; das Passwort muss beim ersten Login geändert werden.")


if __name__ == "__main__":
    try:
        print(migrate())
    except MigrationError as exc:
        sys.exit(f"Migration abgebrochen: {exc}")
