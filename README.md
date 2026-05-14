# Schulbefragung

Datenschutzkonforme, selbst gehostete Web-App für die jährliche Eltern- und Schülerbefragung.  
Ersatz für Edkimo – betrieben auf dem Schulserver hinter nginx.

---

## 1. Kurzbeschreibung

Teilnehmer (Eltern / Kinder) erhalten einen Zettel mit QR-Code und TAN. Sie öffnen die App, beantworten den Fragebogen und senden ab. Die Schulleitung kann über das Backend Befragungen anlegen, TANs generieren, den Rücklauf verfolgen und nach Abschluss eine Auswertung mit Diagrammen herunterladen.

**Anonymitätsgarantie:** Es gibt keine technische Verbindung zwischen einer TAN und den abgegebenen Antworten. Details unter [§ Datenschutz-Architektur](#13-datenschutz-architektur).

---

## 2. Voraussetzungen

- Ubuntu 22.04 oder neuer
- Python 3.11+
- nginx
- (optional) Certbot für Let's-Encrypt-Zertifikat

```bash
sudo apt install python3.11 python3.11-venv python3-pip nginx certbot python3-certbot-nginx
```

Für PDF-Erzeugung wird **weasyprint** benötigt:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0
```

---

## 3. Installation

```bash
# Ins Installationsverzeichnis klonen
sudo mkdir -p /opt/schulbefragung
sudo chown $USER /opt/schulbefragung
git clone <repository-url> /opt/schulbefragung
cd /opt/schulbefragung

# Virtuelle Umgebung und Abhängigkeiten
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Konfiguration
cp .env.example .env
nano .env  # SECRET_KEY, INITIAL_ADMIN_PASSWORD, SCHOOL_DOMAIN anpassen

# Datenbankordner anlegen
mkdir -p data/backups
```

---

## 4. Erstes Admin-Konto anlegen

Entweder über die `.env`-Variable `INITIAL_ADMIN_PASSWORD` (Konto wird beim ersten Start automatisch angelegt):

```ini
INITIAL_ADMIN_PASSWORD=mein-sicheres-passwort
```

Oder manuell:

```bash
cd /opt/schulbefragung
.venv/bin/python -m app.cli create-admin
```

Beim ersten Login wird ein Passwortänderung erzwungen.

---

## 5. systemd-Unit installieren

```bash
sudo cp deploy/schulbefragung.service /etc/systemd/system/
# Ggf. WorkingDirectory und User in der Unit-Datei anpassen
sudo systemctl daemon-reload
sudo systemctl enable schulbefragung
sudo systemctl start schulbefragung
sudo systemctl status schulbefragung
```

---

## 6. nginx-Konfiguration

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/schulbefragung
# Domain in der Datei anpassen (server_name)
sudo ln -s /etc/nginx/sites-available/schulbefragung /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 7. Let's-Encrypt-Zertifikat einrichten

```bash
sudo certbot --nginx -d befragung.meine-schule.de
# Certbot aktualisiert die nginx-Konfiguration automatisch
```

Automatische Erneuerung wird von Certbot per Cronjob erledigt.

---

## 8. Backup-Cronjob einrichten

Tägliches Backup der Datenbank, Aufbewahrung 30 Tage:

```bash
sudo crontab -e
```

Folgende Zeile hinzufügen:

```cron
0 2 * * * /bin/bash -c 'cp /opt/schulbefragung/data/db.sqlite /opt/schulbefragung/data/backups/db-$(date +\%Y\%m\%d).sqlite && find /opt/schulbefragung/data/backups -name "db-*.sqlite" -mtime +30 -delete'
```

---

## 9. Erste Befragung anlegen

1. Im Browser `/admin/login` aufrufen und einloggen.
2. **„Neue Befragung"** klicken.
3. Titel, Typ (Eltern / Kinder), Fragebogen, Start- und Enddatum eingeben.
4. In der Detailansicht: Klasse hinzufügen (z.B. `4a`).
5. TANs generieren (Anzahl = Schüler-/Elternzahl + Reserve).
6. **„Druck-PDF"** herunterladen → ausdrucken → Zettel ausschneiden und verteilen.
7. Nach Abschluss: Befragung schließen → Auswertung abrufen.

---

## 10. Fragebogen anpassen

Fragebögen liegen als JSON-Dateien im Ordner `surveys/`. Jede Datei folgt diesem Schema:

```json
{
  "id": "kinder_kl4",
  "version": 1,
  "title": "...",
  "scale": { "options": [...] },
  "sections": [
    {
      "id": "unterricht",
      "title": "Der Unterricht",
      "questions": [
        {"id": "k01", "type": "scale", "text": "..."},
        {"id": "k02", "type": "single_choice", "options": [...], "text": "..."},
        {"id": "k03", "type": "text", "optional": true, "text": "..."}
      ]
    }
  ]
}
```

**Fragetypen:** `scale` (4-stufig), `single_choice` (eigene Optionen), `text` (Freitext), `conditional` (bedingt, mit `show_if`).

**Neue Frage hinzufügen:** Zeile im passenden Abschnitt ergänzen, eindeutige `id` vergeben, App neu starten.

**Neue Sprache hinzufügen (Phase 2):**
1. `locales/ar.json` anlegen (Schlüssel aus `de.json` übernehmen, Texte übersetzen).
2. `text`-Felder in der Fragebogen-JSON zu `{"de": "...", "ar": "..."}` konvertieren.
3. In `app/i18n.py` den Sprachumschalter aktivieren.

---

## 11. Update

```bash
cd /opt/schulbefragung
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart schulbefragung
```

---

## 12. Fehlersuche

**App startet nicht:**
```bash
sudo journalctl -u schulbefragung -n 50
```

**Datenbank gesperrt:**  
Sicherstellen, dass nur eine uvicorn-Instanz läuft:
```bash
sudo systemctl status schulbefragung
```

**PDF wird nicht erzeugt:**  
Prüfen ob weasyprint-Abhängigkeiten installiert sind:
```bash
.venv/bin/python -c "from weasyprint import HTML; print('OK')"
```
Falls nicht: `sudo apt install libpango-1.0-0 libcairo2`

**TAN ungültig / nicht gefunden:**  
Sicherstellen, dass die Befragung den Status `active` hat und `ends_at` in der Zukunft liegt.

---

## 13. Datenschutz-Architektur

Diese Dokumentation richtet sich an die Schulkonferenz und interessierte Eltern.

### Kernprinzip: Trennung TAN ↔ Antworten

Die Datenbank enthält zwei voneinander unabhängige Tabellen:

| Tabelle | Enthält |
|---------|---------|
| `tans` | TAN-Code, Klasse, Status (unbenutzt/benutzt), Zeitpunkt der Einlösung |
| `responses` | Klasse, Zeitstempel (gerundet), Antworten |

**Es gibt keine technische Verbindung (Fremdschlüssel) zwischen diesen Tabellen.** Sobald eine TAN eingelöst wurde, ist nur noch bekannt, *dass* sie eingelöst wurde – nicht welche Antworten dazu gehören.

### Technische Umsetzung

1. **Keine FK zwischen `tans` und `responses`** – von einer Antwort kann nicht auf die TAN zurückgeschlossen werden.
2. **TAN niemals in der URL** – QR-Codes verwenden URL-Fragmente (`#TAN`), die nicht an den Server gesendet und nicht in Server-Logs gespeichert werden.
3. **Atomare Transaktion**: Beim Absenden werden in einer einzigen Datenbanktransaktion (a) die TAN als „benutzt" markiert und (b) ein neuer, unverknüpfter Antwortdatensatz angelegt.
4. **Zeitstempel gerundet**: Das `submitted_at`-Feld wird auf die volle Stunde gerundet, um eine Zuordnung über Zeitstempel zu erschweren (z.B. „das letzte Kind, das den Bogen eingereicht hat").
5. **Zwischenspeicher nur im Browser**: Das „Speichern und später fortsetzen" schreibt ausschließlich in den `localStorage` des Browsers – keine serverseitigen Zwischenstände.
6. **CSV-Export ohne TANs**: Der Rohdaten-Export enthält nur Felder aus der `responses`-Tabelle.

Diese Maßnahmen wurden mit Blick auf die DSGVO und das Schulkonferenz-Votum umgesetzt.
