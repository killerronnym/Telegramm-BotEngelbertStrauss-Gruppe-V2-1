# Telegramm-Bot-Ökosystem: NexusMod & Co.

Willkommen zu deinem persönlichen Telegramm-Bot-Control-Panel! Dieses Projekt bietet eine zentrale Verwaltungsoberfläche für mehrere spezialisierte Telegram-Bots, darunter der leistungsstarke **NexusMod Bot** (ehemals ID-Finder Bot), der **Minecraft Status Bot**, ein **Einladungs-Bot** und ein **Outfit-Wettbewerb-Bot**.

## ✨ Neuheiten & Highlights (Aktuelles Update)

In den letzten Updates wurden signifikante Verbesserungen an der Stabilität, Sicherheit und Benutzererfahrung vorgenommen:

*   **🔐 Sicheres Login-System:**
    *   **Benutzer-Authentifizierung:** Zugriff auf das Dashboard ist nur noch mit gültigen Zugangsdaten möglich.
    *   **Passwort-Hashing:** Passwörter werden sicher mit modernsten Algorithmen (PBKDF2/scrypt) verschlüsselt gespeichert.
    *   **Session-Management:** Sichere Sitzungsverwaltung verhindert unbefugten Zugriff.
    *   **Dark Mode Login:** Ein augenfreundliches, komplett dunkles Login-Interface.
*   **👥 Erweiterte Benutzerverwaltung:**
    *   **Rollenbasiert:** Unterscheidung zwischen **Admins** (voller Zugriff) und **Usern** (eingeschränkter Zugriff).
    *   **Zentrale Steuerung:** Direkt auf dem Dashboard können neue Benutzer angelegt, bearbeitet oder gelöscht werden.
    *   **Profil-Bearbeitung:** Benutzernamen, Passwörter und Rollen können jederzeit über ein intuitives Modal-Fenster geändert werden.
*   **🎨 Modernisiertes Dashboard-Design:**
    *   **Kachel-Interface:** Alle Funktionen sind über übersichtliche Kacheln erreichbar.
    *   **Navbar-Frei:** Die obere Navigationsleiste wurde entfernt, um mehr Platz für die Bot-Steuerung zu schaffen.
    *   **Status-Infos:** Der aktuell angemeldete Benutzer und seine Rolle werden dezent auf der Startseite angezeigt.
*   **🛡️ Minecraft Status Pro:** 
    *   **Anti-Duplikat-System:** Ein globaler `asyncio.Lock` verhindert doppelt gesendete Nachrichten bei Telegram-Timeouts.
    *   **Intelligente Rotation:** Status-Nachrichten werden alle 23 Stunden automatisch gelöscht und neu erstellt, um die 48h-Editiergrenze von Telegram sicher zu umgehen.
    *   **Cleanup-First:** Wenn eine Nachricht nicht mehr editiert werden kann, wird sie konsequent gelöscht, bevor eine neue erstellt wird. Nur eine Nachricht bleibt im Chat!
    *   **Robustes Logging:** Detailliertes Fehler-Logging inkl. Exception-Klassen für maximale Transparenz.
*   **📊 Analytics Dashboard:**
    *   **Recently Active Users:** Eine neue Tabelle im Dashboard zeigt die zuletzt aktiven Nutzer mit Zeitstempel und Avatar an.
    *   **Echtzeit-KPIs:** Verbesserte Berechnung von Nachrichtenvolumen, aktiven Nutzern und Top-Contributoren.
    *   **Daten-Registry:** Automatisierte Erfassung von Nutzern beim Beitritt oder Schreiben, um vollständige Statistiken zu gewährleisten.

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

Das Dashboard (Standard-Port 9002) bietet die volle Kontrolle:

1.  **Start/Stop:** Alle Bots können einzeln gestartet und gestoppt werden.
2.  **Live-Logs:** Einblick in die Bot-Aktivitäten direkt im Browser.
3.  **Konfiguration:** Änderungen an Token, IDs und Timern werden sofort übernommen.
4.  **Benutzerverwaltung:** Nur für Admins zugänglich, um den Zugriff auf das System zu regeln.

---
*Entwickelt für maximale Kontrolle und Transparenz in deiner Telegram-Community.*
