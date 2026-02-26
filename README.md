# 🤖 Bot Engine V2 - Engelbert Strauss Gruppe

Ein leistungsstarker Telegram-Bot mit Dashboard zur Verwaltung von Einladungen, ID-Suche, Quiz und Umfragen. Optimiert für Windows und Linux (Docker).

---

## 🚀 Übersicht der Features

### 🧩 Verfügbare Bot Module
- **Invite Bot:** Automatisierte Bewerbungen mit Steckbrief und Admin-Whitelist-Funktion, inklusive intelligenter Erkennung von Social-Media-Links.
- **ID-Finder Bot:** Gruppen-Moderation (Kick, Ban, Mute, Warnungen) und Nutzer-Identifizierung.
- **Quiz Bot:** Planbare Quiz-Runden in der Telegram-Gruppe.
- **Umfrage Bot:** Automatisierte und wiederkehrende Umfragen.
- **TikTok Monitor:** Benachrichtigung in Telegram, sobald hinterlegte User auf TikTok live gehen.

### 💻 Modernes Web-Dashboard
Die gesamte Konfiguration erfolgt bequem über ein passwortgeschütztes Web-Interface auf Port `9002`.
- **Bot-Steuerung:** Alle Module können zentral gestartet, gestoppt und konfiguriert werden.
- **Analytics:** Echtzeit-Statistiken, Live-Protokolle und Nutzer-Rankings.
- **Auto-Update:** Automatische Aktualisierung des Systems direkt über GitHub.

### 🛠️ Technische Stabilität
- **Robuste Datenbank-Verbindungen:** Unterstützung für sichere MySQL Verbindungen via `.env` (Sonderzeichen in Passwörtern werden nativ unterstützt).
- **Bulletproof Process Locking:** Ein Datei-basierter Lock (`main_bot.lock`) verhindert Conflict-409 Fehler durch doppelt laufende Instanzen.
- **Persistence:** Zustände (Conversation State) bleiben auch nach einem Bot-Neustart erhalten.

---

## 📂 Projektstruktur & Sicherheit
Das System nutzt eine aufgeräumte Ordnerstruktur zur sicheren Trennung von Code und Daten.

```text
📦 Telegramm-BotEngelbertStrauss-Gruppe-V2-1
 ┣ 📂 bots/            # Die Kernlogik der einzelnen Bot-Module
 ┣ 📂 data/            # Vorlagen für Quiz-Fragen und Umfragen
 ┣ 📂 instance/        # [ISOLIERT] Deine SQLite Datenbank und gespeicherten Konfigurationen (.json)
 ┣ 📂 logs/            # [ISOLIERT] Alle Bot-Logfiles (.log) und Prozess-Sperren (.pid / .lock)
 ┣ 📂 scripts/         # Optionale Hilfsskripte (z.B. für Datenbank-Fixes)
 ┣ 📂 web_dashboard/   # Das Backend und Frontend des Flask Web-Dashboards
 ┣ 📜 docker-compose.yml
 ┣ 📜 Dockerfile
 ┗ 📜 .env             # (Muss angelegt werden) Beinhaltet sensible Zugangsdaten
```

Alle sensiblen Logs und lokalen Datenbanken sind vom Git-Tracking ausgeschlossen, damit keine echten Konfigurationen ungewollt auf GitHub landen.

---

## 🐳 Installation (Docker / Synology)

Diese Methode wird für Server und NAS (z.B. Synology) dringend empfohlen.

1. **Voraussetzungen:** Docker und Docker-Compose installiert.
2. **Repository klonen** oder das ZIP-Archiv entpacken.
3. **Konfiguration:** Kopiere die Datei `.env.example` und markiere sie in `.env` um.
   Trage deine Daten ein. **Für externe MySQL/MariaDB Server nutze die stabilen Environment-Variablen:**
   ```env
   DB_DRIVER=mysql+pymysql
   DB_USER=dein_db_username
   DB_PASSWORD=dein_sicheres_passwort_mit_sonderzeichen
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_NAME=bot_engine_db
   
   TELEGRAM_BOT_TOKEN=dein_bot_token
   ```
4. **Starten:**
   ```bash
   docker-compose up -d --build
   ```
5. **Dashboard:** Aufrufen über `http://<server-ip>:9002`.

> [!IMPORTANT]
> **Automatik-Betrieb im Docker:** Das System startet im Container **automatisch** das Web-Dashboard sowie den Master-Bot (ID-Finder). Du musst das Bot-Script im Container nicht manuell antippen.

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
5. **Starten des Dashboards (Flask Server):**
   ```powershell
   python web_dashboard/wsgi.py
   ```
   *Alternativ für Produktionsleistung unter Windows: `python run_waitress.py`*
   
   Das Dashboard ist nun unter `http://localhost:5000` (bzw. `9002` bei Waitress) erreichbar.
6. **Starten des Master-Bots:**
   Der Bot kann direkt aus dem Dashboard heraus gestartet werden ("Start"-Button).

---

## 🔄 Updates
- **Automatisch:** Aktiviere in den Dashboard-Systemeinstellungen die Option "Auto-Update".
- **Manuell (Dashboard):** Klicke auf "Nach Updates suchen" und dann auf "Update jetzt installieren".
- **Docker-Konsole:** 
  ```bash
  docker-compose pull && docker-compose up -d
  ```

---

**Entwickelt für die Engelbert Strauss Gruppe.**  
Bei Fragen zum System: `@didinils` | `@pup_Rinno_cgn` auf Telegram.
