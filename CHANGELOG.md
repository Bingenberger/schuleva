# Changelog

## [0.1.0] – 2026-05-11

### Neu
- Vollständige Phase-1-Implementierung gemäß Pflichtenheft
- Öffentliche Teilnehmerseiten: TAN-Eingabe, QR-Start, Fragebogen, Danke-Seite
- TAN-Flow mit URL-Fragment-Technik (kein Server-Logging der TAN)
- Anonymitäts-Architektur: keine FK zwischen `tans` und `responses`, Zeitstempel auf Stunden gerundet
- Admin-Backend: Befragungen anlegen, Klassen verwalten, TANs generieren, Live-Statistik
- Druckbogen-PDF mit QR-Codes (weasyprint)
- Auswertungs-PDF mit matplotlib-Diagrammen
- CSV-Rohdaten-Export (UTF-8 mit BOM, Excel-kompatibel)
- Brute-Force-Schutz (5 Fehlversuche / 15 Min pro IP)
- Rate-Limiting auf TAN-Check und Submit (60 Req/Min/IP)
- CSRF-Schutz für alle POST-Routen
- Session-Cookie (HTTP-only, SameSite=Strict)
- Passwortänderung beim ersten Login erzwungen
- Mehrsprachigkeits-Architektur vorbereitet (locales/de.json)
- systemd-Unit und nginx-Beispielkonfiguration
- 17 Unit-Tests (TAN-Generierung, Anonymitätsgarantien, Auswertung, CSV-Export)
