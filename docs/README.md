# Telegramm-Bot-Ökosystem: NexusMod & Co.

Willkommen zu deinem persönlichen Telegramm-Bot-Control-Panel! Dieses Projekt bietet eine zentrale Verwaltungsoberfläche für mehrere spezialisierte Telegram-Bots, darunter der leistungsstarke **NexusMod Bot** (ehemals ID-Finder Bot), der **Minecraft Status Bot**, ein **Einladungs-Bot** und ein **Outfit-Wettbewerb-Bot**.

## ✨ Neuheiten & Highlights (Aktuelles Update)

In den letzten Updates wurden signifikante Verbesserungen an der Stabilität und Funktionalität vorgenommen:

*   **🛡️ Minecraft Status Pro:** 
    *   **Anti-Duplikat-System:** Ein globaler `asyncio.Lock` verhindert doppelt gesendete Nachrichten bei Telegram-Timeouts.
    *   **Intelligente Rotation:** Status-Nachrichten werden alle 23 Stunden automatisch gelöscht und neu erstellt, um die 48h-Editiergrenze von Telegram sicher zu umgehen.
    *   **Cleanup-First:** Wenn eine Nachricht nicht mehr editiert werden kann, wird sie konsequent gelöscht, bevor eine neue erstellt wird. Nur eine Nachricht bleibt im Chat!
    *   **Robustes Logging:** Detailliertes Fehler-Logging inkl. Exception-Klassen für maximale Transparenz.
*   **📊 Analytics Dashboard:**
    *   **Recently Active Users:** Eine neue Tabelle im Dashboard zeigt die zuletzt aktiven Nutzer mit Zeitstempel und Avatar an.
    *   **Echtzeit-KPIs:** Verbesserte Berechnung von Nachrichtenvolumen, aktiven Nutzern und Top-Contributoren.
    *   **Daten-Registry:** Automatisierte Erfassung von Nutzern beim Beitritt oder Schreiben, um vollständige Statistiken zu gewährleisten.
*   **🤝 Einladungs-Bot Plus:**
    *   **Transparenter Datenschutz:** Neuer Befehl `/datenschutz` klärt Nutzer über die Verarbeitung ihrer Daten während des Steckbrief-Prozesses auf.
    *   **Mitglieder-Sync:** Verbesserte Erkennung bestehender Mitglieder zur Vermeidung doppelter Anmeldungen.

## ⛏️ Minecraft Status Bot Features

*   **Live-Monitoring:** Überwacht Java-Minecraft-Server in Echtzeit (Spieleranzahl, MOTD, Version, Latenz).
*   **Vollautomatisches Dashboard:** Verwaltung aller IP-Daten, Ports und Topic-IDs direkt über das Web-UI.
*   **Auto-Cleanup:** Der `/player` Befehl löscht seine eigene Antwort automatisch nach X Sekunden (einstellbar).
*   **Präzise Anzeige:** Nutzt spezialisierte IP-Felder für interne Abfragen vs. öffentliche Anzeige im Chat.

## 🛡️ NexusMod Bot (Moderation & ID-Finder)

Der NexusMod Bot bleibt dein zentrales Werkzeug für die Gruppenmoderation:

*   **Moderations-Suite:** `/warn`, `/mute`, `/kick`, `/ban` mit flexiblen Zeitangaben (m/h/d).
*   **Chat-Tools:** `/del`, `/purge` (Massenlöschung), `/pin`, `/unpin`.
*   **Automatisierung:** `/lock` (Sperrung von Links, Medien oder Stickern), Anti-Flood-Schutz und Wortfilter.
*   **Identifikation:** Schnelle Abfrage von IDs mit `/id`, `/chatid`, `/userid` oder `/topicid`.

## 🌐 Zentrales Web-Dashboard

Das Dashboard (Port 9002) bietet die volle Kontrolle:

*   **Service-Steuerung:** Starte oder stoppe jeden Bot einzeln mit nur einem Klick.
*   **Konfigurations-Editor:** Bearbeite Bot-Token und Gruppen-IDs bequem über Formulare.
*   **Echtzeit-Logs:** Überwache alle Systemvorgänge und Befehlsausführungen direkt im Browser.
*   **User-Management:** Verwalte Administratoren und deren Berechtigungen global für alle Bots.

## 🚀 Installation & Betrieb

1.  **Voraussetzungen:** Python 3.9+ und die Abhängigkeiten aus `requirements.txt`.
2.  **Start:** Führe `app.py` im Hauptverzeichnis aus, um das Dashboard zu starten.
3.  **Konfiguration:** Navigiere im Browser zur Dashboard-IP und konfiguriere deine Bots.
4.  **Datenschutz:** Alle Daten werden lokal im Ordner `data/` gespeichert (JSON/JSONL-Format).

---

## 📋 Wichtige Befehlsübersicht (Auszug)

| Bereich | Befehl | Funktion |
| :--- | :--- | :--- |
| **Moderation** | `/warn @user` | Gibt eine Verwarnung (Limit konfigurierbar) |
| | `/mute @user 1h` | Schaltet Nutzer für 1 Stunde stumm |
| **Minecraft** | `/player` | Zeigt Liste der aktuell eingeloggten Spieler |
| **Invite** | `/letsgo` | Startet den Anmeldeprozess für neue Mitglieder |
| | `/datenschutz`| Zeigt Informationen zur Datenverarbeitung an |
| **ID-Tools** | `/id` | Zeigt alle relevanten IDs der aktuellen Nachricht |

---

## 🤝 Beitrag & Entwicklung

Das Projekt ist für die private Nutzung optimiert. Änderungen können direkt über das integrierte Code-Panel des Control-Panels vorgenommen und sofort getestet werden.
