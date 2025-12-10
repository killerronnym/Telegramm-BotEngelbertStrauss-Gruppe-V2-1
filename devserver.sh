#!/bin/bash
# Start script pointing to the root app.py (proxy)
source .venv/bin/activate
export FLASK_APP=app.py
export FLASK_ENV=development
python app.py