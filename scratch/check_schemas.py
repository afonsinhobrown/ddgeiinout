import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '../gestao_stae/stae.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()

print(c.execute("SELECT sql FROM sqlite_master WHERE name='eleitoral_movimento_material'").fetchone()[0])
print("-----")
print(c.execute("SELECT sql FROM sqlite_master WHERE name='eleitoral_movimento_item'").fetchone()[0])

conn.close()
