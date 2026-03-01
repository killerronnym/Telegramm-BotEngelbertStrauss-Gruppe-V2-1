# 🤖 Bot Engine V2 - Engelbert Strauss Gruppe (v1.9.5)

Ein leistungsstarker Telegram-Bot mit einem modernen Web-Dashboard zur Verwaltung von Einladungen, ID-Suche, Moderation, Quiz, Umfragen und KI-Chat-Integration. Optimiert für Windows und Linux (Docker/Synology).

---

## 📸 Screenshots vom Dashboard

Hier ein kleiner Einblick in das moderne Web-Dashboard:

### Dashboard Startseite
![Dashboard Übersicht](assets/dashboard_home.png)
*Echtzeit-Statistiken, Live-Protokolle und schnelle System-Steuerung auf einen Blick.*

### Live-Moderation & Bot-Steuerung
![Live Moderation](assets/dashboard_moderation.png)
*Zentrale Steuerung aller Module und detaillierte Live-Moderation (Kick, Ban, Mute, Warnungen).*

*(Hinweis: Erstelle am besten im Projektordner einen Ordner `assets/` und speichere dort deine Screenshots unter den Namen `dashboard_home.png` und `dashboard_moderation.png` ab, um sie direkt auf GitHub im README anzeigen zu lassen!)*

---

## 🚀 Übersicht der Features

### 🧩 Verfügbare Bot Module
- **Invite Bot:** Automatisierte Bewerbungen mit Steckbrief, Admin-Whitelist-Funktion und intelligenter Erkennung von Social-Media-Links.
- **ID-Finder Bot:** Gruppen-Moderation (Kick, Ban, Mute, Warnungen), Nutzer-Identifizierung und das neue **Live-Moderation v2** Interface.
- **Beleidigungsfilter:** Eine anpassbare Blacklist (inkl. Google-Profanity-Import), die Nachrichten automatisch löscht und den Nutzer verwarnt.
- **KI-Chat-Monitoring:** Intelligente Überwachung und Beantwortung von Chat-Nachrichten durch integrierte KI-Modelle.
- **Quiz Bot:** Planbare Quiz-Runden in der Telegram-Gruppe.
- **Geburtstags Bot:** Automatisierte Gratulationen für Gruppenmitglieder mit konfigurierbaren Texten und Uhrzeiten über das Web-Dashboard.
- **Umfrage Bot:** Automatisierte und wiederkehrende Umfragen.
- **TikTok Monitor:** Benachrichtigung in Telegram, sobald hinterlegte User auf TikTok live gehen.

### 💻 Modernes Web-Dashboard (Port `9002`)
Die gesamte Konfiguration erfolgt bequem über ein passwortgeschütztes Web-Interface.
- **Bot-Steuerung:** Alle Module (Haupt-Bot, TikTok-Bot, etc.) können zentral über das Dashboard gestartet und gestoppt werden.
- **Analytics:** Echtzeit-Statistiken, Live-Protokolle und Nutzer-Rankings.
- **Setup-Wizard:** Geführte Ersteinrichtung im Web-Browser bei frischen Installationen inkl. Token-Verwaltung.

### ⚙️ System & Stabilität
- **Auto-Update System:** Integrierter Updater (APScheduler), der auf neue Releases prüft und diese automatisch herunterladen/installieren kann (inkl. Windows Auto-Restart Loop).
- **Robuste Datenbank:** Native Unterstützung für MariaDB/MySQL (`.env` Konfiguration) und SQLite, inklusive Migrations-Skript (`migrate_to_mysql.py`).
- **Bulletproof Process Locking:** Dateibasierte Locks für alle Prozesse verhindern zuverlässig Konflikt-Fehler bei doppelt laufenden Instanzen.
- **Docker-Optimiert:** Startet Webserver und Bot effizient parallel im Container und lädt Tokens priorisiert aus den Environment Variables.

---

## 📂 Projektstruktur & Sicherheit
Das System nutzt eine aufgeräumte Ordnerstruktur zur sicheren Trennung von Code und Daten.

```text
📦 Telegramm-BotEngelbertStrauss-Gruppe-V2-1
 ┣ 📂 assets/          # Bilder für dieses README (Screenshots)
 ┣ 📂 bots/            # Die Kernlogik der einzelnen Bot-Module
 ┣ 📂 data/            # Vorlagen für Quiz-Fragen und Umfragen
 ┣ 📂 instance/        # [ISOLIERT] Deine SQLite Datenbank und Konfigurationen
 ┣ 📂 logs/            # [ISOLIERT] Alle Bot-Logfiles (.log) und Prozess-Sperren
 ┣ 📂 scripts/         # Optionale Hilfsskripte (z.B. Datenbank-Migration)
 ┣ 📂 web_dashboard/   # Dashboard-Backend (Flask) und Frontend
 ┣ 📜 docker-compose.yml
 ┣ 📜 Dockerfile
 ┗ 📜 .env             # (Wird beim Setup erstellt) Beinhaltet sensible Zugänge
```
Alle sensiblen Logs und Datenbanken sind vom Git-Tracking durch `.gitignore` ausgeschlossen.

---

## 🐳 Installation (Docker / Synology NAS)

Diese Methode wird für Server und NAS dringend empfohlen.

1. **Repository klonen** oder das ZIP-Archiv entpacken.
2. **Konfiguration:**
   Starte den Container und folge dem Setup-Wizard im Browser oder nutze die `.env`-Datei für externe Datenbanken:
   ```env
   DB_DRIVER=mysql+pymysql
   DB_USER=dein_db_username
   DB_PASSWORD=dein_passwort
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_NAME=bot_engine_db
   
   TELEGRAM_BOT_TOKEN=dein_bot_token
   ```
3. **Starten:**
   ```bash
   docker-compose up -d --build
   ```
4. **Dashboard:** Aufrufen über `http://<server-ip>:9002`. Docker startet jetzt Web Dashboard und Master-Bot parallel!

---

## 🛠️ Installation (Windows / Lokal)

1. **Voraussetzungen:** [Python 3.11+](https://www.python.org/) installiert.
2. **Repository klonen:**
   ```cmd
   git clone https://github.com/killerronnym/Telegramm-BotEngelbertStrauss-Gruppe-V2-1.git
   cd Telegramm-BotEngelbertStrauss-Gruppe-V2-1
   ```
3. **Virtuelle Umgebung erstellen:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
4. **Abhängigkeiten installieren:**
   ```powershell
   pip install -r requirements.txt
   ```
5. **Starten des Dashboards (Waitress Server):**
   ```powershell
   python run_waitress.py
   ```
   *(Das Dashboard ist nun unter `http://localhost:9002` erreichbar. Bei Neuinstallation öffnet sich automatisch der Wizard).*
6. **Starten der Bots:** Direkt über die Weboberfläche!

---

## 🔄 Updates
- **Automatisch:** Über das Dashboard kann das Auto-Update konfiguriert werden.
- **Manuell (Dashboard):** Klicke auf "Nach Updates suchen" und auf "Update jetzt installieren".
- **Docker-Konsole:** 
  ```bash
  docker-compose pull && docker-compose up -d
  ```

---

**Entwickelt für die Engelbert Strauss Gruppe.**  
Bei Fragen zum System: `@didinils` | `@pup_Rinno_cgn` auf Telegram.
