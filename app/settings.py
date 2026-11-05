"""Zentrale Laufzeitkonfiguration aus der Umgebung (Plattform-Container und nativer Betrieb)."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
BUNDLED_SURVEYS = ROOT / "surveys"
# Fragebögen werden im Browser bearbeitet; im Container liegen sie im Datenvolume.
SURVEYS_DIR = Path(os.getenv("SURVEYS_DIR") or BUNDLED_SURVEYS)
BASE_URL = os.getenv("BASE_URL", "").strip().rstrip("/")
SECURE_COOKIES = BASE_URL.startswith("https://")
PLACEHOLDERS = {"CHANGE-ME-IN-PRODUCTION-secret-key-placeholder", "hier-einen-langen-zufaelligen-string-eintragen"}


def _value(name: str) -> str:
    direct = os.getenv(name, "").strip()
    path = os.getenv(name + "_FILE", "").strip()
    if direct and path:
        raise RuntimeError(f"{name} und {name}_FILE nicht gleichzeitig setzen")
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return direct


def secret_key() -> str:
    key = _value("SECRET_KEY")
    if len(key) < 32 or key in PLACEHOLDERS:
        raise RuntimeError("SECRET_KEY (oder SECRET_KEY_FILE) mit mindestens 32 zufälligen Zeichen setzen")
    return key


def school_domain() -> str:
    """Adresse auf den TAN-Zetteln: SCHOOL_DOMAIN, sonst der Host aus BASE_URL."""
    return os.getenv("SCHOOL_DOMAIN", "").strip() or urlsplit(BASE_URL).netloc or "befragung.meine-schule.de"


def public_scheme() -> str:
    return urlsplit(BASE_URL).scheme or "https"


def proxy_ips() -> str:
    """Komma-getrennte IP-Adressen des Reverse-Proxys; nur deren X-Forwarded-For zählt."""
    import ipaddress
    items = [item.strip() for item in os.getenv("PROXY_IPS", "").split(",") if item.strip()]
    for item in items:
        ipaddress.ip_address(item)  # nur explizite Adressen, keine Netze oder '*'
    return ",".join(items)
