# Changelog

Alle signifikanten Änderungen an diesem Projekt werden hier dokumentiert.

## [1.9.2] - 2026-03-01

### ✨ Neu
- **Datenbank Backup**: Administratoren können nun direkt über das Dashboard eine Sicherungskopie der `app.db` herunterladen. Dies dient zur lokalen Sicherung und zur Vorbeugung von Datenverlust bei Docker-Updates.

## [1.9.1] - 2026-03-01

### 🛠️ Behobene Fehler (Fixes)
- **Auto-Updater Docker Fix**: Der Auto-Updater behält beim Entpacken des ZIP-Archivs nun die ausführbaren Datei-Rechte (`chmod +x`) für `docker-entrypoint.sh` bei. Dies verhindert Abstürze beim Docker-Neustart (`permission denied`).

## [1.9.0] - 2026-03-01

### ✨ Neu
- **Geburtstags-Bot**: Gruppenmitglieder können ihren Geburtstag über `/gb DD MM` oder `/geburtstag DD.MM.` eintragen. Der Bot gratuliert automatisch zur konfigurierten Zeit (z.B. um 00:01). Inklusive Dashboard-Integration zur Verwaltung der Geburtstage, Texte und Uhrzeiten.

## [1.8.13] - 2026-02-28

### 🛠️ Behobene Fehler (Fixes)
- **Dashboard**: Jinja2 Template-Syntax-Fehler beim Aufruf des Profanity-Filters behoben (`endblock`).

## [1.8.11] - 2026-02-28

### ✨ Neu
- **Beleidigungsmanagement (Profanity Filter)**: Eine neue Blacklist für verbotene Wörter inklusive Google-Profanity Imports und automatischer Verwarnung.

## [1.0.0] - 2026-02-24

### ✨ Neu
- **Automatisches Software-Update**: Hintergrund-Task (APScheduler) prüft alle 6 Stunden auf neue Releases.
- **Auto-Installation**: Dashboard kann Updates jetzt selbstständig herunterladen und installieren (inkl. Windows-Auto-Restart Loop).
- **MySQL Migration**: Vollständige Unterstützung für MariaDB/MySQL inklusive Migrations-Skript (`migrate_to_mysql.py`).
- **Live-Moderation v2**: Komplett überarbeitetes Dashboard zur Echtzeit-Überwachung von Gruppen.

### 🛠️ Behobene Fehler (Fixes)
- **Conflict Error**: Automatischer Cleanup von PID-Dateien und Geister-Prozessen bei Bot-Start.
- **SQL Syntax**: Kompatibilitätsprobleme mit `EXTRACT(DOW)` unter MariaDB behoben.
- **UTF-8 Encoding**: Abstürze auf Windows-Systemen durch Unicode-Fehler in den Logs behoben.
- **Token Migration**: Fehlerhafte Token-Zuweisung nach DB-Migration korrigiert.

### ⚙️ Geändert
- **Startup**: `devserver.ps1` nutzt nun eine Endlosschleife, um nach Updates automatisch neu zu starten.
- **Shared Utils**: Zentralisiertes Environment-Loading für alle Bot-Subprozesse verbessert.

---
*Status: Stable Release*
