"""CLI-Hilfsskript: python -m app.cli create-admin"""
from __future__ import annotations
import sys
import getpass
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


def create_admin() -> None:
    from app.db import init_db, get_db
    from app.auth import create_admin_user

    init_db()

    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()

    if count > 0:
        print("Es existieren bereits Benutzer. Neuen Admin anlegen? (j/N) ", end="")
        if input().strip().lower() != "j":
            sys.exit(0)

    username = input("Benutzername [admin]: ").strip() or "admin"
    while True:
        password = getpass.getpass("Passwort (min. 10 Zeichen): ")
        if len(password) < 10:
            print("Passwort zu kurz.")
            continue
        confirm = getpass.getpass("Passwort bestätigen: ")
        if password != confirm:
            print("Passwörter stimmen nicht überein.")
            continue
        break

    create_admin_user(username, password)
    print(f"Benutzer '{username}' angelegt.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Verwendung: python -m app.cli create-admin")
        sys.exit(1)
    if sys.argv[1] == "create-admin":
        create_admin()
    else:
        print(f"Unbekannter Befehl: {sys.argv[1]}")
        sys.exit(1)
