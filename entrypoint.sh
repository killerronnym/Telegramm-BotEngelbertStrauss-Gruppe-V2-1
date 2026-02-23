#!/bin/bash
set -e

# Initialisiere die Datenbank, falls nötig
echo "Initialisiere Datenbank..."
python scripts/init_db.py

# Starte das Web-Dashboard im Hintergrund
echo "Starte Web-Dashboard..."
python web_dashboard/app.py &

# Warte kurz, damit das Dashboard hochfahren kann
sleep 5

# Starte die Bots (hier beispielhaft, muss an deine Logik angepasst werden)
# Wir nutzen hier parallel startende Prozesse
echo "Starte Bots..."

# ID Finder Bot
if [ -f "bots/id_finder_bot/id_finder_bot.py" ]; then
    echo "Starte ID Finder Bot..."
    python bots/id_finder_bot/id_finder_bot.py &
fi

# Invite Bot
if [ -f "bots/invite_bot/invite_bot.py" ]; then
    echo "Starte Invite Bot..."
    python bots/invite_bot/invite_bot.py &
fi

# Outfit Bot
if [ -f "bots/outfit_bot/outfit_bot.py" ]; then
    echo "Starte Outfit Bot..."
    python bots/outfit_bot/outfit_bot.py &
fi

# Quiz Bot
if [ -f "bots/quiz_bot/quiz_bot.py" ]; then
    echo "Starte Quiz Bot..."
    python bots/quiz_bot/quiz_bot.py &
fi

# TikTok Bot
if [ -f "bots/tiktok_bot/tiktok_bot.py" ]; then
    echo "Starte TikTok Bot..."
    python bots/tiktok_bot/tiktok_bot.py &
fi

# Umfrage Bot
if [ -f "bots/umfrage_bot/umfrage_bot.py" ]; then
    echo "Starte Umfrage Bot..."
    python bots/umfrage_bot/umfrage_bot.py &
fi

# Halte den Container am Leben, solange Prozesse laufen
wait
