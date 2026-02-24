# 🤖 Unified Bot System v2.0.0

Zentrale Verwaltungsoberfläche für mehrere Telegram-Bots mit Live-Moderation, MySQL-Modul, automatischem Software-Update-System und professionellem Web-Installer.

## 🚀 Kern-Features

- **✨ Web-Installation Wizard**: Kinderleichte Einrichtung über den Browser (keine manuellen Config-Dateien!).
- **🛡️ Live-Moderations-Dashboard**: Überwachung und Moderation von Telegram-Gruppen in Echtzeit.
- **🔄 Auto-Update-System**: Automatische Erkennung und Installation von Software-Updates direkt von GitHub.
- **🐳 Docker Support**: Native Unterstützung für Linux-Deployment via Docker Compose.
- **🗄️ MySQL & SQLite**: Unterstützung für lokale und remote Datenbanken mit integriertem Verschlüsselungs-Support.
- **🎮 Multi-Bot Steuerung**: Zentrale Steuerung für ID-Finder, Quiz-Bot, Umfrage-Bot, TikTok-Monitor und mehr.

## 🚀 Schnellstart (Setup)

### Option A: Klassische Installation (Windows/Linux)
1. **Repository klonen/kopieren**.
2. **Umgebung einrichten**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Starten**:
   ```bash
   python main.py  # Oder unter Windows: .\devserver.ps1
   ```
4. **Setup**: Öffne `http://127.0.0.1:9002` im Browser. Er wird dich automatisch zum **Installationsassistenten** leiten.

### Option B: Docker (Empfohlen für Linux/Cloud)
1. **Docker Compose starten**:
   ```bash
   docker-compose up -d
   ```
2. **Konfigurieren**: Gehe auf `http://deine-ip:9002` und folge den Anweisungen des Web-Installers.

## 🔐 Sicherheit & Login
- Das Admin-Passwort wird während der Installation festgelegt.
- **Anforderungen**: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.
- Passwörter werden sicher mit modernem Hashing gespeichert.

## 🔄 Software Updates
Das System prüft alle 6 Stunden auf GitHub nach neuen Versionen. 
- **Auto-Update**: Kann im Dashboard aktiviert werden, um Updates vollautomatisch im Hintergrund zu installieren.
- **Manuell**: Über die Sidebar/Dashboard im Bereich "System Settings".

## 📁 Projektstruktur
- `/bots`: Quellcode der einzelnen Telegram-Bots.
- `/web_dashboard`: Flask-App für die Verwaltungsoberfläche.
- `/data`: Lokale Datenspeicher (Logs, JSON-Daten).
- `/instance`: Enthält die Sperrdatei `installed.lock` und lokale Datenbanken.

---
*Entwickelt für maximale Portabilität und Benutzerfreundlichkeit.*
