# 🤖 Engelbert Strauss Bot - V2.1 (V1.11.4)

Ein leistungsstarker, modularer Telegram-Bot mit integriertem Web-Dashboard zur Verwaltung von Gruppen, Umfragen, Gewinnspielen und mehr.

## 🚀 Features & Plugins

Das System besteht aus einem Master-Bot, der verschiedene spezialisierte Plugins lädt:

| Plugin | Beschreibung |
| :--- | :--- |
| **ID Finder** | Loggt Benutzeraktivitäten, IDs und verwaltet Verwarnungen/Strafen. |
| **Invite Bot** | Erstellt "Steckbriefe" und verwaltet Beitrittsanfragen für geschlossene Gruppen. |
| **Outfit Bot** | Täglicher "Outfit des Tages" Wettbewerb mit Abstimmung und Gewinnerkürung. |
| **Quiz Bot** | Automatisiertes Senden von Quizfragen nach Zeitplan oder manuell. |
| **Umfrage Bot** | Erstellt regelmäßige Gruppenumfragen zur Community-Interaktion. |
| **Birthday Bot** | Registriert Geburtstage und gratuliert Mitgliedern automatisch. |
| **TikTok Bot** | Überwacht TikTok-Kanäle und sendet Benachrichtigungen bei neuen Videos/Lives. |
| **Profanity Filter** | Automatisches Löschen von Schimpfwörtern und Verwarnung der Benutzer. |
| **Auto Responder** | Reagiert automatisch auf bestimmte Schlüsselwörter in Nachrichten. |
| **Report Bot** | Ermöglicht Mitgliedern das Melden von Nachrichten an Administratoren. |
| **Event Bot** | Verwaltung und Ankündigung von Gruppen-Events. |

## 🛠 Installation (Docker)

Die empfohlene Installationsmethode ist via **Docker Compose**.

### Voraussetzungen
- Docker & Docker Compose installiert.
- Ein Telegram Bot Token (von [@BotFather](https://t.me/BotFather)).

### Schritte
1. **Repository klonen**:
   ```bash
   git clone https://github.com/killerronnym/Telegramm-BotEngelbertStrauss-Gruppe-V2-1.git
   cd Telegramm-BotEngelbertStrauss-Gruppe-V2-1
   ```

2. **Konfiguration**:
   Kopiere die `.env.example` Datei nach `.env` und trage deinen Bot-Token und deine Datenbank-URL ein:
   ```bash
   cp .env.example .env
   ```

3. **Starten**:
   ```bash
   docker-compose up -d
   ```
   Der Bot startet nun automatisch, und das Dashboard ist unter `http://localhost:9003` erreichbar.

## 📁 Ordnerstruktur

- `bots/`: Enthält den Master-Bot und alle Plugin-Module.
- `web_dashboard/`: Das Flask-basierte Admin-Panel.
- `instance/`: Lokale Datenbank und Persistenz-Dateien.
- `logs/`: System- und Bot-Logs.
- `scripts/`: Wartungs- und Setup-Utilitys.

## 📦 Abhängigkeiten

Die wichtigsten Bibliotheken sind:
- `python-telegram-bot`: Für die Bot-Interaktion.
- `Flask`: Für das Web-Dashboard.
- `SQLAlchemy`: Datenbank-Abstraktion.
- `APScheduler`: Für zeitgesteuerte Aufgaben (Quiz, Geburtstage).

---
Entwickelt von **killerronnym** für die Engelbert Strauss Gruppe.
