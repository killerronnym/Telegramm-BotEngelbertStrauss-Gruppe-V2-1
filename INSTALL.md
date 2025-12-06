# Installationsanleitung für den Telegram Bot Control Panel

Diese Anleitung führt dich durch die Schritte zur Einrichtung und zum Starten der Flask-Webanwendung und der integrierten Telegram-Bots.

## Voraussetzungen

*   **Python 3.11+**: Die Anwendung basiert auf Python.
*   **Git**: Zum Klonen des Repositorys.
*   **Telegram Bots**: Du benötigst zwei separate Telegram Bots, die du bei [@BotFather](https://t.me/BotFather) erstellen musst:
    *   Einen Bot für die **Einladungs- und Profilverwaltung** (für `invite_bot.py`). Notiere dir den **Bot Token** und mache diesen Bot zum Administrator deiner Gruppe, damit er Einladungslinks erstellen und Beitrittsanfragen verwalten kann.
    *   Einen Bot für den **Outfit-Wettbewerb** (für `outfit_bot.py`). Notiere dir den **Bot Token** und füge diesen Bot ebenfalls zu deiner Gruppe hinzu.
*   **Telegram Gruppen Chat ID**: Du benötigst die Chat ID deiner Haupt-Telegram-Gruppe. Diese beginnt oft mit `-100` gefolgt von vielen Ziffern (z.B. `-1001234567890`).

## Einrichtung des Projekts

1.  **Repository klonen:**
    ```bash
    git clone [DEIN_REPO_URL_HIER]
    cd telegramm-bot-es # Oder den Namen deines geklonten Ordners
    ```

2.  **Virtuelle Umgebung erstellen und aktivieren:**
    Es wird dringend empfohlen, eine virtuelle Umgebung zu verwenden.
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Abhängigkeiten installieren:**
    ```bash
    pip install -r requirements.txt
    ```

## Konfiguration über die Web-Oberfläche

Die Konfiguration der Bots erfolgt bequem über die Flask-Weboberfläche. Die Einstellungen werden in JSON-Dateien im Projektverzeichnis gespeichert.

### 1. Flask-Anwendung starten

Starte die Flask-Anwendung. Dies versucht auch, die Bots im Hintergrund zu starten (sofern sie aktiviert sind).

```bash
./devserver.sh
```

*   Die Anwendung sollte unter `http://localhost:8080` erreichbar sein.
*   **Wichtiger Hinweis:** Die Flask-Anwendung läuft jetzt mit `use_reloader=False`, um Konflikte mit den Telegram-Bots zu vermeiden. Das bedeutet, dass Änderungen am Code einen **manuellen Neustart** des `./devserver.sh`-Skripts erfordern, damit sie wirksam werden.
*   Beachte die Terminal-Ausgabe auf Fehler.

### 2. Standard-Konfigurationsdateien initialisieren (falls nicht vorhanden)

Beim ersten Start oder wenn `bot_settings_config.json` leer ist, werden Standardwerte erstellt. Du musst diese mit deinen tatsächlichen Bot-Informationen aktualisieren.

### 3. Einladungs-Bot konfigurieren

Navigiere im Browser zu den Einstellungen des Einladungs-Bots: `http://localhost:8080/bot-settings`

*   **"Bot aktivieren"**: Aktiviere diesen Haken.
*   **"Bot Token"**: Gib hier den **Bot Token deines EINLADUNGS-BOTS** ein (vom BotFather).
*   **"Haupt-Chat ID der Gruppe (für Einladungslinks)"**: Gib hier die Chat ID deiner Haupt-Telegram-Gruppe ein (z.B. `-1001234567890`).
*   **"Gültigkeit des Einladungslinks (Minuten)"**: Lege die gewünschte Gültigkeitsdauer fest.
*   **"Steckbrief für bestehende Mitglieder erneut posten"**: Aktiviere diesen Haken, wenn der Steckbrief eines Nutzers, der bereits Mitglied der Gruppe ist und das Formular erneut ausfüllt, wieder in der Gruppe gepostet werden soll. Ist dies aktiviert, erhält der Benutzer keinen neuen Einladungslink, sondern eine Bestätigung, dass der Steckbrief gepostet wurde.
*   Klicke auf **"Einstellungen speichern"**.
*   Nach dem Speichern: Überprüfe den "Invite-Bot Status" und klicke ggf. auf **"Bot starten"**. Überprüfe die Logs auf dieser Seite auf Fehlermeldungen.

### 4. Outfit-Bot konfigurieren

Navigiere im Browser zum Dashboard des Outfit-Bots: `http://localhost:8080/outfit-bot/dashboard`

*   **"Bot Token"**: Gib hier den **Bot Token deines OUTFIT-BOTS** ein (vom BotFather).
*   **"Chat ID"**: Gib hier ebenfalls die Chat ID deiner Telegram-Gruppe ein.
*   Konfiguriere `POST_TIME`, `WINNER_TIME` und `AUTO_POST_ENABLED` nach deinen Wünschen.
*   **"Admin User IDs"**: Gib die Telegram User IDs der Administratoren an, die Admin-Befehle nutzen dürfen (kommagetrennt).
*   Klicke auf **"Outfit-Bot Konfiguration speichern!"**.
*   Nach dem Speichern: Überprüfe den "Outfit-Bot Status" und klicke ggf. auf **"Bot starten"**. Überprüfe die Logs auf dieser Seite auf Fehlermeldungen.

## Wichtige Hinweise

*   **Einzige Bot-Instanz**: Stelle IMMER sicher, dass nur eine Instanz jedes Bots läuft. Starte die Bots ausschließlich über die Flask-Webanwendung, nachdem diese gestartet wurde. Manuelles Starten der `invite_bot.py` oder `outfit_bot.py` aus dem Terminal, während die Flask-App läuft, führt zu Konflikten mit der Telegram API (`Conflict: terminated by other getUpdates request`).
*   **Bot Tokens**: Verwende für den Einladungs-Bot und den Outfit-Bot **zwei unterschiedliche Bot Tokens**.
*   **Flask-App beenden**: Um die Flask-App und damit beide Bots sauber zu beenden, drücke `Strg + C` im Terminal, in dem `devserver.sh` läuft.
