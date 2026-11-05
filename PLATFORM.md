# Schulbefragung (schuleva): Containervertrag

Python 3.12.12/amd64, FastAPI 0.115.0, Uvicorn 0.30.6, WeasyPrint 70.0 und
matplotlib 3.9.2 aus Hash-Lockfiles (`requirements.lock`); Basisimage mit Digest.
Läuft schreibgeschützt als UID/GID 10001 ohne Capabilities. Beschreibbar sind
`/data` und `/tmp` (Caches von matplotlib und fontconfig).

## Eigenständiger Start

```sh
python3 -c "import secrets; print(secrets.token_hex(32))" > .session-key && chmod 600 .session-key
export SCHULEVA_SECRET_FILE="$PWD/.session-key"
docker compose build
docker compose run --rm app python -m app.migrate
docker compose run --rm app python -m app.cli create-admin    # persönliches Schulleitungskonto
docker compose up -d --no-build
```

## Konfiguration

| Variable | Bedeutung |
| --- | --- |
| `SECRET_KEY` / `SECRET_KEY_FILE` | Pflicht, mindestens 32 Zeichen; Platzhalter werden abgewiesen |
| `BASE_URL` | öffentliche Adresse; `https://` schaltet Secure-Cookies ein; Host erscheint auf den TAN-Zetteln (`SCHOOL_DOMAIN` überschreibt) |
| `PROXY_IPS` | IP-Adressen des Reverse-Proxys; nur deren `X-Forwarded-For` zählt (Brute-Force-Sperre je Client statt je Proxy) |
| `DATABASE_PATH`, `SURVEYS_DIR` | im Container `/data/db.sqlite` und `/data/surveys` |
| `INITIAL_ADMIN_PASSWORD` | nur nativer Altbetrieb; die Plattform setzt es nicht |

## Schema und Migration

Kein Schemaaufbau beim Start. `python -m app.migrate` sperrt, führt die bekannten,
idempotenten Schritte aus (Rolle `lehrer`, `anon_names`, `share_grants`) und trägt
Stand 1 in `schema_version` ein; ein neuerer Stand wird abgewiesen. Mitgelieferte
Fragebögen werden nach `SURVEYS_DIR` kopiert, wenn dort keiner gleichen Namens liegt;
im Browser bearbeitete Fragebögen bleiben unverändert.

- `/health/live`: Prozess antwortet.
- `/health/ready`: Stand 1, alle Tabellen, Fragebogenverzeichnis vorhanden; sonst 503.

## Betrieb

Ein Worker, weil der geführte Modus seine Sitzungen im Speicher hält (WebSocket).
Keine Zugriffsprotokolle: Bei einer anonymen Befragung sollen keine IP-Adressen
mit Zeitpunkten gespeichert werden. Die TAN steht weiterhin nur im URL-Fragment.
