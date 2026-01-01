
import os
import sys

# Add dashboard to path to import app
sys.path.append(os.path.join(os.getcwd(), 'dashboard'))

from app import build_group_activity

res = build_group_activity(days=30)
leaderboard = res.get('leaderboard', [])

for entry in leaderboard:
    if entry.get('user_id') == '7386906637' or entry.get('username') == 'didinils':
        print(f"DEBUG: Found Nils: {entry}")

# Check Rinno too
for entry in leaderboard:
    if entry.get('user_id') == '5544098336':
        print(f"DEBUG: Found Rinno: {entry}")
