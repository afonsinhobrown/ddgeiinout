import sqlite3
import os

DB_PATH = 'stae.db'
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    print("TRIGGERS:")
    for row in c.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'").fetchall():
        print(f"Trigger Name: {row[0]}")
        print(f"SQL:\n{row[1]}\n" + "-"*40)
    conn.close()
else:
    print("Database file not found.")
