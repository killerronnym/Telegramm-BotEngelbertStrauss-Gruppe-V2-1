#!/bin/bash
set -e

echo "--- Starting Bot Engine v2 Entrypoint ---"

# Navigieren zum App-Verzeichnis
cd /app

# Prüfen auf neue Abhängigkeiten
if [ -f "requirements.txt" ]; then
    echo "Checking for dependency updates..."
    pip install --no-cache-dir -r requirements.txt
fi

# Datenbank-Migrationen oder andere Vorbereitungen könnten hier stehen
# python manage.py db upgrade

echo "Starting Gunicorn Flask server..."
# Gunicorn im Vordergrund starten
exec gunicorn --bind 0.0.0.0:9002 --workers 4 --timeout 120 "web_dashboard.app:create_app()"
