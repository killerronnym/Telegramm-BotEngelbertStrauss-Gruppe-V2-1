# Telegram Bot Control Panel

Ein robustes Flask-basiertes Web-Panel zur zentralisierten Verwaltung von zwei spezialisierten Telegram-Bots: einem Einladungs-Bot für die Nutzerregistrierung und einem Outfit-Wettbewerb-Bot. Dieses System ermöglicht eine einfache Konfiguration, Überwachung und Steuerung beider Bots über eine intuitive Web-Oberfläche.

## Funktionen

*   **Zentrale Web-Oberfläche (Flask)**: Ein responsives Admin-Panel zur Verwaltung aller Bot-Einstellungen und zur Überwachung ihres Status.
*   **Einladungs-Bot (`invite_bot.py`)**:
    *   **Geführte Registrierung**: Nutzer füllen einen Steckbrief über eine Konversation im Bot aus.
    *   **Automatische Einladungen**: Generiert individuelle Einladungslinks zur Gruppe.
    *   **Verbessertes Profil-Posting**: Postet automatisch den Steckbrief des Nutzers beim Beitritt in die Gruppe. Für *bestehende Mitglieder* kann über die Web-Oberfläche konfiguriert werden, ob der Steckbrief erneut gepostet wird (ohne erneuten Einladungslink).
    *   **Robuste MarkdownV2-Formatierung**: Alle vom Bot gesendeten Nachrichten sind nun vollständig kompatibel mit Telegrams MarkdownV2, wodurch Fehler bei der Textformatierung behoben wurden.
    *   **Web-Konfiguration**: Aktivieren/Deaktivieren, Bot Token, Haupt-Chat ID der Gruppe, Gültigkeitsdauer der Einladungslinks, **und die Option zum erneuten Posten von Profilen für bestehende Mitglieder** über das Web-Panel konfigurierbar.
    *   **Status & Logs**: Echtzeit-Statusanzeige und Log-Ausgabe des Bots im Web-Panel.
*   **Outfit-Wettbewerb Bot (`outfit_bot.py`)**:
    *   **Tägliche Wettbewerbe**: Verwaltet das "Outfit des Tages" mit Fotoeinreichungen und Abstimmung.
    *   **Automatische Posts & Gewinner**: Sendet tägliche Aufforderungen und ermittelt Gewinner.
    *   **Web-Konfiguration**: Bot Token, Chat ID, Zeiten für Posts und Gewinner, Admin User IDs über das Web-Panel konfigurierbar.
    *   **Status & Logs**: Echtzeit-Statusanzeige und Log-Ausgabe des Bots im Web-Panel.
*   **Hintergrundprozesse**: Beide Bots laufen als unabhängige Hintergrundprozesse, gesteuert durch die Flask-Anwendung. Konflikte durch Mehrfachstarts wurden behoben.
*   **Konfigurations-Persistenz**: Alle Bot-Einstellungen werden in JSON-Dateien gespeichert, um sie über Neustarts hinweg zu erhalten.
*   **Dunkles Design**: Eine angenehme, augenschonende Oberfläche für die Admin-Panels.

## Erste Schritte

Für eine detaillierte Installations- und Konfigurationsanleitung, einschließlich der Einrichtung von Telegram Bots und der benötigten Tokens/IDs, siehe die [INSTALL.md](INSTALL.md) Datei.

**Kurzanleitung:**

1.  Klonen Sie das Repository.
2.  Erstellen und aktivieren Sie eine Python-virtuelle Umgebung.
3.  Installieren Sie die Abhängigkeiten: `pip install -r requirements.txt`.
4.  Starten Sie die Flask-Anwendung: `./devserver.sh`.
    *   *Hinweis:* Um Konflikte mit Telegrams API zu vermeiden, startet die Flask-Anwendung jetzt ohne automatischen Reloader. Manuelle Änderungen erfordern einen Neustart des Servers.
5.  Konfigurieren Sie beide Bots über die Web-Oberfläche unter `http://localhost:8080/bot-settings` (für den Einladungs-Bot) und `http://localhost:8080/outfit-bot/dashboard` (für den Outfit-Bot).

## Projektstruktur
