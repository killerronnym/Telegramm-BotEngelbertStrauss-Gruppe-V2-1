# 🤖 Unified Bot System v1.0.0

Zentrale Verwaltungsoberfläche für mehrere Telegram-Bots mit Live-Moderation, MySQL-Modul und automatischem Software-Update-System.

## 🚀 Kern-Features

- **🛡️ Live-Moderations-Dashboard**: Überwachung und Moderation von Telegram-Gruppen in Echtzeit über den Browser.
- **🔄 Auto-Update-System**: Automatische Erkennung und Installation von Software-Updates direkt von GitHub.
- **🗄️ MySQL-Integration**: Skalierbare Datenspeicher-Lösung (statt SQLite) für hohe Performance und Zuverlässigkeit.
- **🎮 Multi-Bot Steuerung**: Zentrale Steuerung für ID-Finder, Quiz-Bot, Umfrage-Bot, TikTok-Monitor, Minecraft-Status und mehr.
- **🔐 Sicherheit**: Rollenbasierte Benutzerverwaltung mit sicherem Passwort-Hashing (Flask-Login).

## 🛠️ Installation & Setup (Windows)

### 1. Repository vorbereiten
```powershell
# In das Projektverzeichnis wechseln
cd "Bot T"
```

### 2. Python Umgebung einrichten
Stelle sicher, dass Python 3.10+ installiert ist.
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Konfiguration (`.env`)
Erstelle eine `.env` Datei im Hauptverzeichnis basierend auf der `.env.example`:
```ini
DATABASE_URL=mysql+pymysql://user:password@localhost/db_name
SECRET_KEY=dein_geheimes_passwort
```

### 4. Datenbank Migration
Falls du von einer alten Version (SQLite) kommst, nutze das Migrations-Skript:
```powershell
python migrate_to_mysql.py
```

## 🏃 Starten des Systems

Starte einfach das PowerShell-Skript im Hauptverzeichnis:
```powershell
.\devserver.ps1
```
Das Dashboard ist danach erreichbar unter: `http://127.0.0.1:9002`

## 🔄 Software Updates

Das System verfügt über ein integriertes Update-Modul:
- **Manuell**: Klicke in der Update-Kachel auf "Nach Updates scannen".
- **Automatisch**: Aktiviere den "Auto-Update" Schalter. Der Server prüft alle 6 Stunden im Hintergrund auf neue Versionen und installiert diese bei Bedarf vollautomatisch (inkl. Neustart).

## 📁 Projektstruktur
- `/bots`: Quellcode der einzelnen Telegram-Bots.
- `/web_dashboard`: Flask-App für die Verwaltungsoberfläche.
- `/data`: Lokale Datenspeicher (Logs, temporäre Dateien).
- `shared_bot_utils.py`: Gemeinsame Funktionen & DB-Zugriff für alle Bots.

---
*Entwickelt für Stabilität und einfache Handhabung.*
