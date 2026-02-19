# 🚀 Neue Projekte

*   [ ] **Web-Oberfläche zur Telegram-Moderation:** Eine neue Seite im Dashboard erstellen, um Telegram-Gruppen zu moderieren.
    *   [ ] Anzeige aller Gruppen und deren Topics.
    *   [ ] Anzeige aller Nachrichten (inkl. Bilder und Usernamen) pro Topic.
    *   [ ] Funktion zum Löschen von Nachrichten.
    *   [ ] Option, beim Löschen eine Verwarnung an den User zu senden.
    *   [ ] Option, Nachrichten kommentarlos zu löschen.

# 🎯 Offene Aufgaben

*   [ ] **Test-Suite erstellen:** Automatisierte Tests für die Kernfunktionen der Bots entwickeln, um zukünftige Änderungen abzusichern. (Langfristiges Ziel)

---

## ✨ Verbesserungspotenzial

### Allgemein
*   [ ] **Datenbank statt JSON:** Langfristig die Datenhaltung von JSON-Dateien auf eine robustere Lösung wie SQLite oder eine kleine Datenbank umstellen, um die Leistung und Zuverlässigkeit zu erhöhen.

---

## ✅ Fertiggestellte Aufgaben

*   [x] **Robuste Fehlerbehandlung in `track_activity`:** Sichergestellt, dass bei Fehlern im globalen Activity-Log (`activity_log.jsonl`) die Verarbeitung abbricht, um Inkonsistenzen zu vermeiden, und dass Fehler beim User-Registry-Update nicht das gesamte Logging blockieren. (In `bots/id_finder_bot/id_finder_bot.py` implementiert)
*   [x] **Asynchrone Dateizugriffe:** Die synchronen Dateizugriffe (`load_json`, `save_json`, `_append_jsonl`) in `bots/id_finder_bot/id_finder_bot.py` in asynchrone Operationen umgewandelt (`run_in_executor`), um das Blockieren des Bots zu verhindern.
*   [x] **Bot-Startprozess optimieren:** Überprüfen, ob alle Bots korrekt und ohne Verzögerungen starten. (Erledigt: Startprozess robuster gemacht und Prozessabfrage im Dashboard optimiert)
*   [x] **API-Endpunkte prüfen:** Alle externen API-Abfragen (z.g. Minecraft-Server-Status) auf Robustheit und korrekte Fehlerbehandlung testen. (Erledigt: `minecraft_bridge.py` gehärtet und `mcstatus` als Dependency hinzugefügt)
*   [x] **Funktionalität aller Bots testen & fixen:** Jeden Bot einzeln auf seine Kernfunktionen geprüft, Fehler behoben und Robustheit erhöht.
    *   [x] **Invite Bot:** Conversation-Logik gefixt, Markdown-Escaping, Join-Request-Handler korrigiert.
    *   [x] **Outfit Bot:** Threading-Probleme behoben, Pfade absolut gesetzt, Duell-Logik stabilisiert.
    *   [x] **Quiz Bot:** Persistenz für `last_sent_date` eingebaut, API-Limits validiert.
    *   [x] **Umfrage Bot:** Persistenz für `last_sent_date` eingebaut, API-Limits validiert.
*   [x] **Web-Dashboard Stabilität:** Prüfen, ob das Dashboard auch bei vielen Anfragen stabil läuft und keine Sessions verliert. (Erledigt: Prozess-Abfrage optimiert, Session-Key ausgelagert)
*   [x] **Logging verbessern:** Detailliertere Log-Ausgaben implementieren, um Fehler schneller identifizieren zu können.
    *   [x] **Zentrale Logging-Konfiguration:** Eine zentrale Konfiguration für das Logging einrichten, die das Log-Level, das Ausgabeformat und die Rotationsstrategie für alle Module festlegt.
*   [x] **Code-Refactoring:** Den Code auf Lesbarkeit, Wartbarkeit und Performance optimieren. (Alte Skripte im `archive`-Ordner wurden entfernt.)
*   [x] **Dokumentation erweitern:** Die `README.md` und andere Dokumentationsdateien aktualisieren, um alle neuen Funktionen und Änderungen zu beschreiben.
*   [x] **Benachrichtigungen bei Fehlern:** Ein System einrichten, das den Admin (z.B. per Telegram-Nachricht) informiert, wenn ein kritischer Fehler auftritt. (Implementiert als Dashboard-Ansicht für Kritische Logs)
*   [x] **Optimierte Broadcast-Engine:** Die Broadcast-Engine so umbauen, dass sie nicht alle 10 Sekunden alle Nachrichten prüft, sondern gezielt den nächsten Sendezeitpunkt mit `job_queue.run_once()` ansteuert.
*   [x] **Datenredundanz prüfen:** Überprüfen, ob die in `activity_log.jsonl` und der `user_messages`-History gespeicherten Daten zusammengefasst oder besser structured werden können. (Anmerkung zur aktuellen Strategie hinzugefügt)
*   [x] **Spezifischere Fehlerbehandlung:** Allgemeine `try...except`-Blöcke durch spezifische Fehlerbehandlung ersetzen und detaillierte Fehlermeldungen loggen.
*   [x] **Effizienteres Log-Handling:** Das Einlesen von Log-Dateien optimieren, um den Speicherverbrauch bei großen Dateien zu reduzieren (z.B. durch zeilenweises Lesen oder Buffering).
*   [x] **Code-Duplizierung reduzieren:** Wiederholte Code-Blöcke in den Flask-Routen (z.B. für die Bot-Verwaltung) identifizieren und in wiederverwendbare Funktionen auslagern.
*   [x] **Caching für Konfigurationsdateien:** Eine Caching-Strategie für häufig gelesene JSON-Dateien implementieren, um die Anzahl der Festplattenzugriffe zu minimieren und die Performance zu verbessern.
*   [x] **Datum und Uhrzeit:** ❔ Quiz Bot & 📊 Umfrage Bot Datum und Uhrzeit Funktionalitäten (z.B. flexiblere Zeitsteuerung, Zeitstempel in Nachrichten).
