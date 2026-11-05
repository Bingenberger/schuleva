"""Startet Uvicorn für den Betrieb: ein Worker (geführter Modus hält Sitzungen im Speicher),
Forwarded-Header nur vom konfigurierten Proxy, keine Zugriffsprotokolle (anonyme Befragung)."""
from __future__ import annotations

import uvicorn

from app import settings


def options() -> dict:
    ips = settings.proxy_ips()
    return {"host": "0.0.0.0", "port": 8000, "workers": 1, "proxy_headers": bool(ips),
            "forwarded_allow_ips": ips or "", "access_log": False, "server_header": False,
            "timeout_graceful_shutdown": 20}


def main() -> None:
    settings.secret_key()  # fail fast before binding
    uvicorn.run("app.main:app", **options())


if __name__ == "__main__":
    main()
