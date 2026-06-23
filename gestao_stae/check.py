import sqlite3
conn = sqlite3.connect('staeavancado.db')
c = conn.cursor()
tables = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
for t in tables:
    cols = [row[1] for row in c.execute(f"PRAGMA table_info({t})").fetchall()]
    count = c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    print(f"Table {t} ({count} rows): {cols}")
conn.close()

