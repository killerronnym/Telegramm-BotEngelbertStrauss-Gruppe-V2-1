# Installationsanleitung für das Telegram Bot Control Panel

Diese Anleitung führt dich durch die Schritte zur Einrichtung und zum Starten der Flask-Webanwendung und der integrierten Telegram-Bots.

## Voraussetzungen

*   **Python 3.11+**: Die Anwendung basiert auf Python.
*   **Git**: Zum Klonen des Repositorys.
*   **Telegram Bot**: Du benötigst mindestens einen Telegram Bot, den du bei [@BotFather](https://t.me/BotFather) erstellen musst. Für die volle Funktionalität (ID-Finder, Einladungs-Bot, Outfit-Bot) könnten bis zu drei separate Bots erforderlich sein, oder du nutzt einen Bot für mehrere Zwecke.
    *   Notiere dir den **Bot Token** und mache diesen Bot zum Administrator deiner Gruppe(n), damit er Nachrichten löschen, Mitglieder bannen/einschränken und Einladungslinks erstellen kann.
*   **Telegram Gruppen Chat ID**: Du benötigst die Chat ID deiner Haupt-Telegram-Gruppe. Diese beginnt oft mit `-100` gefolgt von vielen Ziffern (z.B. `-1001234567890`). Nutze den `/ChatID` Befehl des ID-Finder Bots, um diese zu erhalten.

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

### 2. ID-Finder & Moderations-Bot (NexusMod Bot) konfigurieren

Navigiere im Browser zum ID-Finder Dashboard: `http://localhost:8080/id-finder`

*   **Bot Token**: Gib hier den **Bot Token deines NexusMod Bots** ein.
*   **Haupt-Gruppen-ID**: Gib hier die Chat ID deiner Haupt-Telegram-Gruppe ein (z.B. `-1001234567890`).
*   **Log-Topic-ID (Optional)**: Gib hier die Topic-ID ein, falls Bot-Bestätigungen und Logs in ein spezifisches Topic innerhalb deiner Hauptgruppe gesendet werden sollen. Lass es leer, wenn der Bot direkt im Kontext antworten soll.
*   Klicke auf **"Nur Speichern"**.
*   Nach dem Speichern: Klicke auf **"Start"**, um den Bot zu starten. Überprüfe die Logs auf dieser Seite auf Fehlermeldungen.

### 3. Admin-Gruppe des NexusMod Bots einrichten (WICHTIG!)

Nachdem der NexusMod Bot gestartet ist:

1.  **Erstelle eine neue PRIVATE Telegram-Gruppe** (nur für dich und den Bot).
2.  Füge deinen **NexusMod Bot** zu dieser Gruppe hinzu und mache ihn zum **Administrator**.
3.  Sende in dieser **privaten Admin-Gruppe** den Befehl: `/setadmingroup`
    *   Der Bot wird bestätigen, dass dieser Chat als Admin-Gruppe festgelegt wurde. Von nun an können wichtige Bot-Konfigurationen und Rollen-Management-Befehle nur hier ausgeführt werden.

### 4. Weitere Bots konfigurieren (Einladungs-Bot, Outfit-Bot)

Navigiere zu den Dashboards der anderen Bots über die Hauptseite (`http://localhost:8080/`). Dort findest du die jeweiligen Einstellungsseiten und kannst sie wie gewohnt konfigurieren.

*   **Einladungs-Bot (`/bot-settings`):**
    *   **"Bot aktivieren"**: Aktiviere diesen Haken.
    *   **"Bot Token"**: Gib hier den **Bot Token deines EINLADUNGS-BOTS** ein.
    *   **"Haupt-Chat ID der Gruppe"**: Gib hier die Chat ID deiner Haupt-Telegram-Gruppe ein.
    *   **"Topic-ID (Optional)"**: ID des Themas für Steckbriefe.
    *   **"Gültigkeit des Einladungslinks (Minuten)"**: Lege die Dauer fest.
    *   **"Steckbrief für bestehende Mitglieder erneut posten"**: Haken setzen, wenn gewünscht.
*   **Outfit-Bot (`/outfit-bot/dashboard`):**
    *   **"Bot Token"**: Gib hier den **Bot Token deines OUTFIT-BOTS** ein.
    *   **"Gruppen-Chat-ID"**: Gib hier die Chat ID deiner Haupt-Telegram-Gruppe ein.
    *   **"Topic ID (Optional)"**: ID des Themas für Outfit-Posts.
    *   Konfiguriere `Automatische Posts`, `Start-Uhrzeit`, `Gewinner-Uhrzeit` nach deinen Wünschen.
    *   **"Admin User IDs"**: Gib die Telegram User IDs der Administratoren an, die Admin-Befehle nutzen dürfen (kommagetrennt).

Speichere die Einstellungen auf den jeweiligen Seiten und starte die Bots bei Bedarf.

## Wichtige Hinweise

*   **Telegram Bot Administratorrechte**: Stelle sicher, dass die Bots in den relevanten Gruppen die notwendigen Admin-Rechte besitzen (Nachrichten löschen, Mitglieder bannen/einschränken, etc.).
*   **Einzige Bot-Instanz**: Starte die Bots IMMER ausschließlich über die Flask-Webanwendung. Manuelles Starten der Bot-Skripte aus dem Terminal führt zu Konflikten.
*   **Bot Tokens**: Verwende für jeden Bot (falls du mehrere nutzt) **unterschiedliche Bot Tokens**.
*   **Flask-App beenden**: Um die Flask-App und damit alle Bots sauber zu beenden, drücke `Strg + C` im Terminal, in dem `devserver.sh` läuft.
