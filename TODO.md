# Projekt TODO & Analyse

Dieses Dokument listet den Status der Umstrukturierung und Optimierung des Projekts auf.

## ✅ Erledigte Aufgaben

### 🔴 Kritische Sicherheitsprobleme behoben
- [x] **Hardcodierter `secret_key`:** `SECRET_KEY` wird nun aus Umgebungsvariablen geladen (`web_dashboard/app/config.py`).
- [x] **Deaktivierte Login-Funktion:** Login wurde repariert und nutzt nun `Flask-Login` mit einer SQLite-Datenbank.
- [x] **Tokens & Secrets:** Alle Bots (`invite_bot`, `outfit_bot`) laden ihre Tokens nun primär aus Umgebungsvariablen oder der Datenbank.

### 🟡 Code-Qualität & Refactoring
- [x] **Modularisierung:** Die monolithische `app.py` wurde in Blueprints (`web_dashboard/app/routes/`) aufgeteilt.
- [x] **Datenbank-Integration:** Einführung von SQLite und SQLAlchemy (`models.py`). JSON-Dateien werden schrittweise abgelöst.
- [x] **Shared Utils:** Erstellung von `shared_bot_utils.py` zur gemeinsamen Nutzung von DB-Funktionen durch die Bots.
- [x] **Bot-Anpassung:** `invite_bot.py` und `outfit_bot.py` wurden auf die neue Struktur migriert.

### 🔵 Distribution & Setup
- [x] **Setup-Skripte:** `scripts/setup.sh` und `scripts/init_db.py` erstellt.
- [x] **Requirements:** `requirements.txt` aktualisiert (inkl. `flask-sqlalchemy`, `flask-login`, `python-dotenv`).

## 📝 Offene Punkte / Nächste Schritte

### 🟠 UI/UX & Frontend
- [ ] **Templates anpassen:** Die HTML-Templates (z.B. `bot_settings.html`) müssen noch so angepasst werden, dass sie die Konfiguration aus der Datenbank lesen und schreiben, statt Platzhalter zu verwenden. Aktuell sind viele Routen in `dashboard.py` noch Stubs.
- [x] Implement Puppy-Alter Dedicated Tab (v1.5.3)
    - [x] Add "Puppy-Alter" tab to `bot_settings.html`
    - [x] Create specialized route in `dashboard.py`
    - [x] Integrate into bot conversation in `invite_bot.py`
- [x] Debug Internal Server Error on /bot-settings (v1.5.1/v1.5.2)
- [x] Implement Puppy Age Enhancement
    - [x] Create Puppy Age field in Invite Bot config
    - [x] Add "Skip" button for optional fields in `invite_bot.py`
- [x] Implement Custom Slash Commands
    - [x] Add "Custom Commands" tab to `bot_settings.html`
    - [x] Create backend routes for custom command management in `dashboard.py`
    - [x] Implement dynamic command handling in `invite_bot.py`
- [ ] **Live-Moderation:** Die `live_moderation` Route liefert aktuell leere Daten. Hier muss die Logik implementiert werden, um Nachrichten aus der Datenbank oder den Log-Dateien zu lesen.

### 🟡 Weitere Bots migrieren
- [ ] **Quiz Bot:** Muss noch auf `shared_bot_utils` umgestellt werden.
- [ ] **Umfrage Bot:** Muss noch auf `shared_bot_utils` umgestellt werden.
- [ ] **ID Finder Bot:** Muss noch auf `shared_bot_utils` umgestellt werden.
- [ ] **Minecraft Bridge:** Muss noch geprüft und angepasst werden.

### 🔵 Dokumentation
- [ ] **README aktualisieren:** Die Dokumentation sollte die neue Architektur und die Setup-Schritte widerspiegeln.
