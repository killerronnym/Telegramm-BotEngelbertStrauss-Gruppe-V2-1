import sqlite3
import os

db_path = 'instance/app.db'
if not os.path.exists(db_path):
    print(f"Error: Database {db_path} not found.")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute('ALTER TABLE birthday ADD COLUMN year INTEGER')
    conn.commit()
    print("Column 'year' added to 'birthday' table successfully.")
except sqlite3.OperationalError as e:
    if "duplicate column name: year" in str(e):
        print("Column 'year' already exists in 'birthday' table.")
    else:
        print(f"Error executing ALTER TABLE: {e}")

conn.close()
