# Schulbefragung

Datenschutzkonforme, selbst gehostete Web-App für die jährliche Eltern- und Schülerbefragung an Grundschulen.

---

## Inhalt

1. [Für die Schule: Funktionsübersicht](#1-für-die-schule-funktionsübersicht)
2. [Rollen und Berechtigungen](#2-rollen-und-berechtigungen)
3. [Befragungsworkflows](#3-befragungsworkflows)
4. [Datenschutz-Architektur](#4-datenschutz-architektur)
5. [Technische Übersicht](#5-technische-übersicht)
6. [Installationsanleitung](#6-installationsanleitung)
7. [Lokale Entwicklungsumgebung](#7-lokale-entwicklungsumgebung)
8. [Fragebögen pflegen](#8-fragebögen-pflegen)
9. [Update](#9-update)
10. [Fehlersuche](#10-fehlersuche)

---

## 1. Für die Schule: Funktionsübersicht

### Was die App leistet

Die App ermöglicht anonyme Befragungen von Eltern und Schülerinnen und Schülern – vollständig auf dem eigenen Schulserver betrieben, ohne Weitergabe von Daten an Dritte.

### Teilnehmerseite (Eltern / Kinder)

- **TAN-basierter Einstieg:** Jede teilnehmende Familie erhält einen Zettel mit QR-Code und individueller TAN. Der QR-Code führt direkt zur Befragung; die TAN stellt sicher, dass jede Person nur einmal teilnimmt.
- **Fragebogen:** Mehrteilig mit Skala-, Auswahl- und Freitextfragen. Für Kinderbefragungen wird eine gut lesbare Grundschrift-Schrift verwendet.
- **Zwischenspeichern:** Antworten werden im Browser zwischengespeichert – die Seite kann geschlossen und später weitergeführt werden.
- **Geführter Modus (Klassenzimmer):** Schülerinnen und Schüler verbinden sich über einen QR-Code mit dem eigenen Gerät. Die Lehrkraft steuert das Tempo: eine Frage nach der anderen wird freigegeben und sichtbar gemacht.

### Schulleitung / Verwaltung

- **Befragungen anlegen:** Titel, Typ (Eltern oder Kinder), Fragebogen, Start- und Enddatum.
- **Klassen verwalten:** Beliebig viele Klassen pro Befragung.
- **TANs generieren und drucken:** PDF mit abschneidbaren Zetteln (QR-Code + TAN) sowie CSV-Export für den Seriendruck.
- **Live-Rücklauf:** Anzahl eingereichter Antworten in Echtzeit, aufgeteilt nach Klasse.
- **Befragung abschließen und auswerten:** Balkendiagramme je Frage, filterbar nach Klasse oder Schulgesamtheit.
- **Exportformate:** Auswertungs-PDF (mit Diagrammen) und Rohdaten-CSV (Excel-kompatibel).
- **Ergebnisse freigeben:** Öffentliche Freigabelinks pro Klasse oder für die ganze Schule – ohne Login einsehbar, gezielt deaktivierbar.
- **Präsentationsmodus:** Die freigegebene Ergebnisseite bietet neben der Listenansicht einen Folienmodus, bei dem jede Frage als einzelne „Slide" erscheint (Tastatursteuerung, Vollbild).
- **Fragebogen-Editor:** Fragebögen können direkt im Browser bearbeitet werden (formularbasierter Editor mit JSON-Ansicht für Fortgeschrittene).
- **Befragungen löschen:** Inklusive aller Antworten und TANs.

---

## 2. Rollen und Berechtigungen

| Funktion | Schulleitung | Lehrer |
|---|---|---|
| Befragungen anlegen / schließen / löschen | ✓ | – |
| Klassen und TANs verwalten | ✓ | – |
| Geführten Modus starten | ✓ | ✓ |
| Auswertung einsehen | ✓ | ✓ |
| Exporte herunterladen | ✓ | ✓ |
| Freigabelinks verwalten | ✓ | – |
| Fragebögen bearbeiten | ✓ | – |
| Benutzerverwaltung | ✓ | – |

Lehrerkonten werden von der Schulleitung im Bereich **Admin → Benutzer** angelegt.

---

## 3. Befragungsworkflows

### 3.1 TAN-basierte Befragung (Standardweg)

1. **Befragung anlegen:** `/admin/` → „Neue Befragung" → Formular ausfüllen.
2. **Klasse hinzufügen:** In der Detailansicht Klassenname eintragen (z.B. `4a`).
3. **TANs generieren:** Anzahl = Schüler-/Elternzahl + ca. 10 % Reserve.
4. **PDF drucken:** „PDF" herunterladen, ausdrucken, Zettel ausschneiden und verteilen.
5. **Befragung aktiv halten:** Läuft bis zum Enddatum automatisch.
6. **Abschließen:** „Befragung schließen" → Auswertung öffnen.

### 3.2 Geführter Modus (Klassenzimmer, ohne TANs)

Geeignet für Kinderbefragungen unter Aufsicht einer Lehrkraft.

1. In der Detailansicht auf **„▶ Geführter Modus"** neben der Klasse klicken.
2. Das Lehrer-Kontrollpanel öffnet sich mit QR-Code und Sitzungscode.
3. Schülerinnen und Schüler scannen den QR-Code mit ihrem Gerät.
4. Sobald alle verbunden sind: **„Befragung starten"**.
5. Fragen einzeln mit **„Freischalten"** sichtbar machen.
6. Warten, bis alle geantwortet haben (Fortschrittsanzeige), dann **„Weiter"**.
7. Am Ende: **„Sitzung beenden"** – Antworten werden gespeichert.

Die Sitzung läuft maximal 4 Stunden. Wird die Seite neu geladen, verbindet sich der Browser automatisch wieder.

### 3.3 Ergebnisse freigeben

1. Auswertung öffnen: `/admin/survey/{id}/results`.
2. Abschnitt **„Freigabelinks"** in der Detailansicht:
   - Beliebig viele Links erstellen – je für „Schule gesamt" oder eine einzelne Klasse.
   - Jeder Link ist unabhängig deaktivierbar.
3. Link per E-Mail oder Schulwebsite teilen.
4. Empfänger sehen die Ergebnisse **ohne Login** – klassengefiltert oder mit Klassenauswahl, je nach freigegebenem Umfang.
5. Auf der Ergebnisseite: Umschalten zwischen **Listenansicht** und **Präsentationsmodus** (eine Frage pro Folie, Pfeiltasten / Leertaste / Vollbild).

---

## 4. Datenschutz-Architektur

*Dieser Abschnitt richtet sich an Schulkonferenz, Datenschutzbeauftragte und interessierte Eltern.*

### Kernprinzip: Trennung TAN ↔ Antworten

Die Datenbank enthält zwei voneinander vollständig unabhängige Tabellen:

| Tabelle | Inhalt |
|---|---|
| `tans` | TAN-Code, Klasse, ob verwendet, Zeitpunkt der Einlösung |
| `responses` | Klasse, Zeitstempel (gerundet), Antworten |

**Es gibt keinen Fremdschlüssel und keine andere technische Verbindung zwischen diesen Tabellen.** Nach Einlösung einer TAN ist nur noch bekannt, *dass* sie eingelöst wurde – nicht, welche Antworten dazu gehören.

### Maßnahmen im Detail

1. **Keine Verknüpfung TAN → Antwort** – von einem Antwortdatensatz kann nicht auf die TAN zurückgeschlossen werden.
2. **TAN nie in der URL** – QR-Codes übergeben die TAN als URL-Fragment (`#TAN`). Fragmente werden nicht an den Server gesendet und erscheinen nicht in Server-Logs.
3. **Atomare Transaktion** – TAN-Markierung als „benutzt" und Speichern der Antworten erfolgen in einer einzigen Datenbanktransaktion, ohne verknüpfende Daten.
4. **Zeitstempel gerundet** – `submitted_at` wird auf die volle Stunde gerundet, um eine Re-Identifizierung über den Zeitpunkt zu erschweren.
5. **Zwischenspeicher nur im Browser** – angefangene Antworten liegen im `localStorage` des Browsers, nicht auf dem Server.
6. **CSV-Export ohne TANs** – der Rohdaten-Export enthält ausschließlich Felder aus der `responses`-Tabelle.
7. **Geführter Modus anonym** – Schülerinnen und Schüler verbinden sich ohne Namen; der Server vergibt eine temporäre Zufalls-ID nur für die Dauer der Sitzung.

---

## 5. Technische Übersicht

### Stack

| Komponente | Technologie |
|---|---|
| Web-Framework | FastAPI 0.115 + Uvicorn |
| Datenbank | SQLite 3 (WAL-Modus) |
| Templates | Jinja2 |
| Echtzeit (Geführter Modus) | WebSocket (FastAPI nativ) |
| PDF-Erzeugung | WeasyPrint 62 |
| Diagramme | matplotlib 3.9 |
| QR-Codes | qrcode[pil] |
| Authentifizierung | Session-Cookie (itsdangerous), bcrypt |
| Laufzeitumgebung | Python 3.11+ |

### Verzeichnisstruktur

```
schulbefragung/
├── app/
│   ├── main.py             # App-Einstiegspunkt, Middleware, Startup
│   ├── db.py               # Datenbankschema, Migrations-Helper
│   ├── auth.py             # Login, CSRF, Brute-Force-Schutz
│   ├── models.py           # User-Datenklasse
│   ├── i18n.py             # Übersetzungsfunktion t()
│   ├── cli.py              # Kommandozeilen-Hilfsskript
│   ├── routes/
│   │   ├── public.py       # Teilnehmerseiten (TAN, Fragebogen, Danke)
│   │   ├── admin.py        # Backend (Login, Übersicht, Detail, Auswertung)
│   │   ├── export.py       # PDF, CSV, Freigabelinks
│   │   └── guided.py       # Geführter Modus (WebSocket) + öffentl. Ergebnisse
│   ├── services/
│   │   ├── tan.py          # TAN-Generierung
│   │   ├── evaluation.py   # Auswertungslogik
│   │   ├── guided.py       # In-Memory-Sitzungsverwaltung
│   │   ├── pdf_tans.py     # Druckbogen-PDF
│   │   └── pdf_report.py   # Auswertungs-PDF
│   └── templates/          # Jinja2-Templates
├── static/                 # CSS, Schriften
├── surveys/                # Fragebogen-JSON-Dateien
├── locales/                # Übersetzungsdateien (de.json)
├── deploy/                 # nginx- und systemd-Vorlagen
├── tests/                  # pytest-Tests
├── data/                   # Datenbank (wird automatisch angelegt)
└── requirements.txt
```

### Umgebungsvariablen (`.env`)

| Variable | Pflicht | Beschreibung |
|---|---|---|
| `SECRET_KEY` | **Ja** | Zufälliger Schlüssel für Session-Signaturen (min. 32 Zeichen) |
| `INITIAL_ADMIN_PASSWORD` | Empfohlen | Passwort für den ersten Admin-Account (`admin`); nur beim ersten Start wirksam |
| `DATABASE_PATH` | Nein | Pfad zur SQLite-Datei (Standard: `data/db.sqlite`) |

Sicherer `SECRET_KEY` erzeugen:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 6. Installationsanleitung

### 6.1 Systemvoraussetzungen

- Ubuntu 22.04 LTS oder neuer (oder vergleichbare Debian-basierte Distribution)
- Python 3.11 oder neuer
- nginx
- Certbot (für HTTPS)

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip nginx certbot python3-certbot-nginx
```

Für die PDF-Erzeugung werden native Bibliotheken benötigt:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0
```

### 6.2 App installieren

```bash
# Installationsverzeichnis anlegen
sudo mkdir -p /opt/schulbefragung
sudo chown $USER /opt/schulbefragung

# Quellcode einspielen (z.B. per git oder scp)
git clone <repository-url> /opt/schulbefragung
cd /opt/schulbefragung

# Virtuelle Python-Umgebung anlegen
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Datenordner anlegen
mkdir -p data/backups
```

### 6.3 Konfiguration

Konfigurationsdatei anlegen:

```bash
cat > /opt/schulbefragung/.env << 'EOF'
SECRET_KEY=HIER-EINEN-ZUFALLSSCHLUESSEL-EINTRAGEN
INITIAL_ADMIN_PASSWORD=HIER-EIN-SICHERES-PASSWORT-EINTRAGEN
DATABASE_PATH=data/db.sqlite
EOF
chmod 600 /opt/schulbefragung/.env
```

Den `SECRET_KEY` mit folgendem Befehl generieren:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 6.4 Admin-Konto

Das erste Admin-Konto (`admin`) wird beim ersten Start der App automatisch angelegt, wenn `INITIAL_ADMIN_PASSWORD` in der `.env` gesetzt ist. Beim ersten Login wird eine Passwortänderung erzwungen.

Alternativ kann das Konto manuell erstellt werden:

```bash
cd /opt/schulbefragung
.venv/bin/python -m app.cli create-admin
```

### 6.5 systemd-Service einrichten

```bash
# Service-Datei installieren
sudo cp deploy/schulbefragung.service /etc/systemd/system/

# Bei Bedarf Pfade in der Service-Datei anpassen:
sudo nano /etc/systemd/system/schulbefragung.service

# Service aktivieren und starten
sudo systemctl daemon-reload
sudo systemctl enable schulbefragung
sudo systemctl start schulbefragung

# Status prüfen
sudo systemctl status schulbefragung
```

Die App lauscht standardmäßig auf `127.0.0.1:8000` und ist nur über nginx von außen erreichbar.

### 6.6 nginx-Konfiguration

```bash
# Vorlage kopieren und Domain anpassen
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/schulbefragung
sudo nano /etc/nginx/sites-available/schulbefragung
# → server_name auf die eigene Domain setzen (z.B. befragung.meine-schule.de)

# Konfiguration aktivieren
sudo ln -s /etc/nginx/sites-available/schulbefragung /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 6.7 HTTPS mit Let's Encrypt einrichten

```bash
sudo certbot --nginx -d befragung.meine-schule.de
```

Certbot passt die nginx-Konfiguration automatisch an und richtet die automatische Erneuerung ein.

Erneuerung testen:

```bash
sudo certbot renew --dry-run
```

### 6.8 Im lokalen Netzwerk betreiben (ohne öffentliche Domain)

Soll die App nur im Schul-LAN erreichbar sein (z.B. für den geführten Modus im Klassenzimmer), kann Uvicorn direkt ohne nginx gestartet werden:

```bash
cd /opt/schulbefragung
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Die App ist dann unter `http://<IP-des-Servers>:8000` erreichbar. Die IP-Adresse des Servers ermitteln:

```bash
hostname -I
```

### 6.9 Backup-Cronjob einrichten

Tägliches Backup der Datenbank, automatische Bereinigung nach 30 Tagen:

```bash
sudo crontab -e
```

Folgende Zeile hinzufügen:

```
0 2 * * * bash -c 'cp /opt/schulbefragung/data/db.sqlite /opt/schulbefragung/data/backups/db-$(date +\%Y\%m\%d).sqlite && find /opt/schulbefragung/data/backups -name "db-*.sqlite" -mtime +30 -delete'
```

---

## 7. Lokale Entwicklungsumgebung

```bash
# Repository klonen
git clone <repository-url>
cd schulbefragung

# Virtuelle Umgebung
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# App starten (mit Auto-Reload)
uvicorn app.main:app --reload

# Tests ausführen
pytest
```

Die App ist dann unter `http://localhost:8000` erreichbar. Beim ersten Start wird ohne `.env` ein Hinweis ausgegeben; das Admin-Konto muss dann über das CLI angelegt werden:

```bash
python -m app.cli create-admin
```

---

## 8. Fragebögen pflegen

Fragebögen liegen als JSON-Dateien im Ordner `surveys/`. Die mitgelieferten Dateien `eltern_kl4.json` und `kinder_kl4.json` dienen als Ausgangspunkt.

Fragebögen können entweder direkt als Datei bearbeitet oder über den **Fragebogen-Editor** im Admin-Backend (`/admin/questionnaires`) verwaltet werden. Der Editor bietet eine formularbasierte Oberfläche sowie einen JSON-Direkteditor für Fortgeschrittene.

### Dateistruktur

```json
{
  "id": "eltern_kl4",
  "version": 1,
  "title": "Elternbefragung Klasse 4",
  "scale": {
    "options": [
      {"value": "1", "label": "trifft voll zu"},
      {"value": "2", "label": "trifft eher zu"},
      {"value": "3", "label": "trifft eher nicht zu"},
      {"value": "4", "label": "trifft nicht zu"}
    ]
  },
  "sections": [
    {
      "id": "unterricht",
      "title": "Unterricht",
      "questions": [...]
    }
  ]
}
```

### Fragetypen

| Typ | Beschreibung |
|---|---|
| `scale` | Skalafrage – nutzt die global definierten `scale.options` |
| `single_choice` | Einzelauswahl mit eigenen Optionen (Feld `options`) |
| `text` | Freitexteingabe (wird in der Auswertung als Liste angezeigt) |
| `conditional` | Wie `single_choice`, aber mit `show_if`-Bedingung für abhängige Folgefragen |

### Beispielfragen

```json
{"id": "u01", "type": "scale",
 "text": "Mein Kind fühlt sich in der Klasse wohl."},

{"id": "u02", "type": "single_choice",
 "text": "Wie oft erhält Ihr Kind Hausaufgaben?",
 "options": [
   {"value": "taeglich", "label": "täglich"},
   {"value": "manchmal", "label": "manchmal"},
   {"value": "nie",      "label": "nie"}
 ]},

{"id": "u03", "type": "text", "optional": true,
 "text": "Was möchten Sie uns noch mitteilen?"},

{"id": "u04", "type": "conditional",
 "text": "Wie zufrieden sind Sie mit der Betreuung?",
 "show_if": {"question_id": "u02", "value": "nie"},
 "options": [
   {"value": "sehr",   "label": "sehr zufrieden"},
   {"value": "wenig",  "label": "wenig zufrieden"}
 ]}
```

Nach dem Bearbeiten von JSON-Dateien muss die App neu gestartet werden:

```bash
sudo systemctl restart schulbefragung
```

---

## 9. Update

```bash
cd /opt/schulbefragung

# Neue Version einspielen
git pull

# Abhängigkeiten aktualisieren
.venv/bin/pip install -r requirements.txt

# App neu starten
sudo systemctl restart schulbefragung
```

Das Datenbankschema wird beim Start automatisch migriert – manuelle SQL-Eingriffe sind nicht erforderlich.

---

## 10. Fehlersuche

**App startet nicht**

```bash
sudo journalctl -u schulbefragung -n 100 --no-pager
```

**Datenbank gesperrt / mehrere Instanzen**

```bash
sudo systemctl status schulbefragung
# Sicherstellen, dass nur eine Instanz läuft
sudo systemctl restart schulbefragung
```

**PDF wird nicht erzeugt**

```bash
.venv/bin/python -c "from weasyprint import HTML; print('OK')"
```

Schlägt dies fehl:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0
```

**TAN ungültig**

- Befragung hat Status `active`?  `/admin/survey/{id}`
- Liegt `ends_at` in der Zukunft?
- TAN noch nicht verwendet? (Jede TAN ist Einwegcode)

**Geführter Modus – Schülerinnen und Schüler können nicht verbinden**

- App mit `--host 0.0.0.0` starten oder über nginx erreichbar machen.
- Alle Geräte im selben Netzwerk?
- WebSocket-Verbindungen durch nginx durchgeleitet? (`proxy_read_timeout` mind. 60 s, besser 300 s für lange Sitzungen)

**Session läuft unerwartet ab**

Session-Lifetime beträgt 8 Stunden. Bei Bedarf in `app/main.py` den Parameter `max_age` anpassen.

---

*Betrieben auf dem Schulserver – keine Daten verlassen das Schulnetz.*
