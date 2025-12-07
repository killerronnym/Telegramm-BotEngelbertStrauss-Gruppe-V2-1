# Telegramm-Bot-Ökosystem: NexusMod & Co.

Willkommen zu deinem persönlichen Telegramm-Bot-Control-Panel! Dieses Projekt bietet eine zentrale Verwaltungsoberfläche für mehrere spezialisierte Telegram-Bots, darunter der leistungsstarke **NexusMod Bot** (ehemals ID-Finder Bot) für umfassende Moderationsaufgaben, ein Einladungs-Bot und ein Outfit-Wettbewerb-Bot.

## ✨ Hauptfunktionen des NexusMod Bots (ID-Finder & Moderation)

Der NexusMod Bot ist dein ultimatives Werkzeug für die Telegram-Gruppenverwaltung, ausgestattet mit einer Vielzahl an Moderations- und Schutzfunktionen:

*   **Umfassende Moderationswerkzeuge:** Von flexiblen Verwarnungen (`/warn`, `/unwarn`, `/clearwarns`) über präzise Stummschaltungen (`/mute`, `/unmute`, `/mutelist`) bis hin zu effektiven Kick- und Bann-Optionen (`/kick`, `/ban`, `/unban`, `/softban`).
*   **Nachrichten-Moderation:** Lösche einzelne Nachrichten (`/del`) oder bereinige ganze Chat-Verläufe (`/purge`).
*   **Starke Auto-Moderation:**
    *   **Anti-Flood:** Verhindert das Überfluten des Chats mit Nachrichten (`/setflood`).
    *   **CAPS-Lock-Filter:** Löscht Nachrichten mit übermäßig vielen Großbuchstaben (`/setcaps`).
    *   **Link-Kontrolle:** Erlaubt, blockiert oder beschränkt Links auf eine Whitelist (`/setlinks`, `/whitelist`).
    *   **Wortfilter:** Automatische Filterung und Aktion bei unerwünschten Wörtern (`/filter add|remove|list`).
*   **Raid-Modus:** Ein Notfallschalter, der neue Mitglieder automatisch stummschaltet und alle Links blockiert, um die Gruppe bei einem Angriff zu schützen (`/raidmode on|off`).
*   **Flexibles Rollensystem:** Definiere benutzerdefinierte Rollen und weise Moderatoren eingeschränkte Berechtigungen zu (`/role add|remove`, `/roles`).
*   **Zentrale Weboberfläche:** Verwalte alle Einstellungen, starte/stoppe Bots und sieh dir detaillierte Logs über ein intuitives Web-Dashboard an.
*   **Intelligente Log-Verwaltung:** Getrennte Logs für Befehlsausführungen und Systemfehler, optional in ein spezielles Telegram-Topic postbar.
*   **ID-Finder-Funktionalität:** Rufe Chat-IDs und User-IDs direkt im Chat ab (`/ChatID`, `/UserID`).

## 🚀 Installation & Start

Eine detaillierte Installationsanleitung findest du in der [INSTALL.md](INSTALL.md) Datei. Sie führt dich durch die Schritte zum Klonen des Repositorys, zur Installation der Abhängigkeiten und zur Konfiguration der Bots über das Web-Dashboard.

## 🌐 Web-Dashboard Übersicht

Das Web-Dashboard (erreichbar unter `http://localhost:8080/id-finder` nach dem Start) bietet dir eine zentrale Steuerzentrale:

![NexusMod Dashboard Screenshot](path/to/your/screenshot.png)

*   **Statusanzeige:** Sieh auf einen Blick, ob der Bot läuft oder gestoppt ist.
*   **Konfiguration:** Gib Bot-Tokens, Haupt-Gruppen-IDs und optionale Log-Topic-IDs ein.
*   **Steuerung:** Starte, stoppe und speichere die Bot-Konfiguration direkt über Buttons.
*   **Zwei Logbücher:** Überwache Befehlsausführungen und Systemfehler in getrennten, übersichtlichen Log-Fenstern.
*   **Befehls-Dokumentation:** Ein Link führt dich zu einer detaillierten Übersicht aller Bot-Befehle mit Erklärungen.

## 📋 Befehlsübersicht (NexusMod Bot)

Hier ist eine Zusammenfassung der Befehle. Für detaillierte Erklärungen besuche das Web-Dashboard oder die Befehls-Dokumentation.

---

### **Grundlagen & ID**
*   `/ChatID`
    *   *Erklärung:* Sendet eine Nachricht mit der ID der Gruppe und des Topics, in dem der Befehl ausgeführt wird.
*   `/UserID`
    *   *Erklärung:* Zeigt deine persönliche Telegram User-ID an.

### **Globale Bot-Konfiguration (Nur Top-Admins in der Admin-Gruppe)**
*   `/setadmingroup`
    *   *Erklärung:* Setzt den Chat, in dem der Befehl ausgeführt wird, als private Admin-Gruppe für kritische Bot-Einstellungen.
*   `/setmaingroup [gruppen_id]`
    *   *Erklärung:* Legt fest, in welcher Gruppe Moderationsaktionen (Mute, Ban etc.) stattfinden sollen.
*   `/antispam on|off`
    *   *Erklärung:* Aktiviert oder deaktiviert alle automatischen Moderationsfunktionen wie Flood-Control, Link-Filter etc.
*   `/raidmode on|off`
    *   *Erklärung:* Ein Notfallmodus. Wenn aktiviert, werden neue Mitglieder sofort stummgeschaltet und alle Nachrichten mit Links blockiert.

### **Verwarnungssystem**
*   `/warn @user [grund]`
    *   *Erklärung:* Verwarnt einen Benutzer. Kann als Antwort auf eine Nachricht oder durch Angabe der User-ID erfolgen.
*   `/warnings @user`
    *   *Erklärung:* Zeigt alle aktiven Verwarnungen für einen bestimmten Benutzer an.
*   `/unwarn @user [anzahl]`
    *   *Erklärung:* Entfernt eine (oder die angegebene Anzahl) der letzten Verwarnungen eines Benutzers.
*   `/clearwarns @user`
    *   *Erklärung:* Setzt den Verwarnungszähler eines Benutzers komplett auf Null zurück.
*   `/setwarnlimit [zahl]` (Nur Top-Admin)
    *   *Erklärung:* Legt fest, nach wie vielen Verwarnungen eine automatische Aktion erfolgen soll.
*   `/setwarnaction [aktion]` (Nur Top-Admin)
    *   *Erklärung:* Definiert die Aktion (mute, kick, ban, none), die bei Erreichen des Warn-Limits ausgeführt wird.

### **Stummschaltung, Kick & Ban**
*   `/mute @user [dauer] [grund]`
    *   *Erklärung:* Schaltet einen Benutzer stumm. Dauer ist optional (z.B. 30m, 5h, 7d). Ohne Dauer ist der Mute permanent.
*   `/unmute @user`
    *   *Erklärung:* Erlaubt einem stummgeschalteten Benutzer wieder zu schreiben.
*   `/mutelist`
    *   *Erklärung:* Zeigt alle aktuell stummgeschalteten Benutzer, Grund und verbleibende Dauer an.
*   `/kick @user [grund]`
    *   *Erklärung:* Entfernt einen Benutzer aus der Gruppe. Er kann aber sofort wieder beitreten.
*   `/ban @user [dauer] [grund]`
    *   *Erklärung:* Verbannt einen Benutzer aus der Gruppe. Dauer ist optional.
*   `/unban [user_id]`
    *   *Erklärung:* Hebt eine permanente Verbannung auf. Die User-ID muss angegeben werden.
*   `/softban @user`
    *   *Erklärung:* Bannt und entbannt einen Benutzer sofort wieder. Löscht dabei alle Nachrichten des Benutzers aus dem Chat.

### **Nachrichten-Moderation**
*   `/del` (als Reply)
    *   *Erklärung:* Muss als Antwort auf eine Nachricht gesendet werden. Löscht die beantwortete Nachricht und den Befehl selbst.
*   `/purge [anzahl]` (als Reply)
    *   *Erklärung:* Muss als Antwort auf eine Nachricht gesendet werden. Löscht die letzten X Nachrichten ab der beantworteten. Standard ist 10.

### **Auto-Moderation (Nur Top-Admins in der Admin-Gruppe)**
*   `/setflood [nachrichten]/[sekunden]s`
    *   *Erklärung:* Legt fest, wie viele Nachrichten ein User in X Sekunden senden darf, bevor sie gelöscht werden. Beispiel: `5/10s`.
*   `/setcaps [prozent]`
    *   *Erklärung:* Legt den maximal erlaubten Prozentsatz an Großbuchstaben in einer Nachricht fest (z.B. `70`).
*   `/setlinks [allow|block|whitelist]`
    *   *Erklärung:* Erlaubt Links (allow), blockiert sie für alle (block) oder erlaubt sie nur für gewhitelistete User (whitelist).
*   `/whitelist add|remove [user_id]`
    *   *Erklärung:* Fügt einen Benutzer zur Link-Whitelist hinzu oder entfernt ihn.
*   `/filter add|remove|list "wort"`
    *   *Erklärung:* Fügt ein Wort zur Blacklist hinzu (Nachrichten werden gelöscht), entfernt es oder listet alle Filter. Das Wort muss in Anführungszeichen stehen.

### **Rollen-Management (Nur Top-Admins in der Admin-Gruppe)**
*   `/role add [user_id] [rolle]`
    *   *Erklärung:* Gibt einem Benutzer eine vordefinierte Rolle (z.B. 'mod'), die ihm Zugriff auf bestimmte Befehle gewährt.
*   `/role remove [user_id]`
    *   *Erklärung:* Entfernt die zugewiesene Rolle von einem Benutzer.
*   `/roles`
    *   *Erklärung:* Zeigt alle Benutzer an, denen aktuell eine Rolle zugewiesen ist.

---

## 🤝 Beitrag & Entwicklung

Dieses Projekt ist für die private Nutzung gedacht. Änderungen und Erweiterungen können über das integrierte Code-Panel vorgenommen werden.
