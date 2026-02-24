# Changelog

Alle signifikanten Änderungen an diesem Projekt werden hier dokumentiert.

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
