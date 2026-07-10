import sqlite3
import os
db_path = os.path.join(os.path.dirname(__file__), '../gestao_stae/stae.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT sql FROM sqlite_master WHERE name='eleitoral_local_armazenamento'")
print(c.fetchone()[0])
c.execute("PRAGMA table_info(eleitoral_local_armazenamento)")
print(c.fetchall())
conn.close()
