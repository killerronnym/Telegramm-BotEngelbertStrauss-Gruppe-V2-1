# Installationsanleitung: Telegram Bot Control Panel

Diese Anleitung führt dich durch die Einrichtung des Bot-Ökosystems, inklusive NexusMod (Moderation), Minecraft Status, Einladungs-Bot und Outfit-Bot.

## 📋 Voraussetzungen

*   **Python 3.9+**: Die Basis für alle Bots und das Dashboard.
*   **Git**: Zum Verwalten des Quellcodes.
*   **Telegram Bot(s)**: Erstelle deine Bots über [@BotFather](https://t.me/BotFather).
    *   **Wichtig:** Der Bot benötigt Admin-Rechte in der Gruppe ("Delete Messages", "Ban Users", "Invite Users via Link").
*   **Minecraft Server (Java)**: Für das Monitoring muss der Server Java-basiert sein und Anfragen (TCP-Port 25565 standardmäßig) erlauben.

## 🚀 Einrichtung des Projekts

1.  **Repository klonen:**
    ```bash
    git clone [DEIN_REPO_URL]
    cd telegramm-bot-es
    ```

2.  **Virtuelle Umgebung (Empfohlen):**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Abhängigkeiten installieren:**
    ```bash
    pip install -r requirements.txt
    ```

## 🌐 Dashboard & Konfiguration

Das Dashboard ist die zentrale Steuerzentrale (Port 9002).

### 1. Dashboard starten

```bash
./devserver.sh
# ODER manuell:
python3 app.py
```
Öffne `http://localhost:9002` in deinem Browser.

### 2. Minecraft Status Bot konfigurieren
Navigiere zu `http://localhost:9002/minecraft`:
*   **Interne IP/Port:** Die Adresse, die der Bot nutzt, um den Server zu pingen (z.B. lokale IP im Netzwerk).
*   **Anzeige Host/Port:** Die Adresse, die im Telegram-Chat angezeigt wird (z.B. DuckDNS-Adresse).
*   **Topic-ID:** Falls deine Gruppe ein Forum ist, gib hier die ID des "Minecraft"-Themas ein.
*   **Update-Intervall:** Zeit in Sekunden zwischen den Status-Updates.
*   **Rotation:** Der Bot rotiert die Nachricht alle 23h automatisch (Löschen + Neu-Senden), um Editierfehler zu vermeiden.

### 3. NexusMod (ID-Finder & Moderation) konfigurieren
Navigiere zu `http://localhost:9002/id-finder`:
*   Gib den Bot-Token ein.
*   Setze die **Haupt-Gruppen-ID** (erhältlich via `/chatid` in der Gruppe).
*   **Admin-Gruppe einrichten:** Erstelle eine private Gruppe mit dem Bot und sende dort `/setadmingroup`. Wichtige Moderations-Logs erscheinen nun dort.

### 4. Einladungs-Bot & Datenschutz
Navigiere zu `http://localhost:9002/bot-settings`:
*   Aktiviere den Bot und gib den Token ein.
*   Nutzer können nun `/letsgo` im DM des Bots nutzen.
*   Neu: Nutzer können via `/datenschutz` Informationen zur Datenverarbeitung abrufen.

## 🛡️ Stabilität & Sicherheit

*   **Globaler Lock:** Die Minecraft-Bridge nutzt einen `asyncio.Lock`. Dies verhindert, dass bei langsamen Internetverbindungen oder Timeouts doppelte Nachrichten gepostet werden.
*   **Daten-Registry:** Alle Nutzerdaten werden lokal im Ordner `data/` in JSON/JSONL-Dateien gespeichert. Das System erstellt diesen Ordner beim ersten Start automatisch.
*   **Prozess-Kontrolle:** Starte und stoppe die Bots ausschließlich über das Web-Dashboard, um sicherzustellen, dass keine Instanzen doppelt laufen.

## 🛠️ Fehlerbehebung

*   **Doppelte Nachrichten:** Stelle sicher, dass nur ein Bot-Prozess läuft. Überprüfe dies im Dashboard unter "Bot Status".
*   **Nachricht wird nicht editiert:** Das ist normal, wenn die Nachricht älter als 48h ist. Der Bot erkennt dies automatisch, löscht die alte Nachricht und erstellt eine neue.
*   **Syntaxfehler:** Falls du Code manuell änderst, prüfe ihn mit `python -m py_compile [dateiname.py]`.

---

**Wichtiger Hinweis:** Nach jeder Code-Änderung muss das Dashboard (`devserver.sh`) manuell neu gestartet werden.
