import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '../gestao_stae/stae.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("""
    SELECT t.nome as material, t.variante, s.quantidade_total, s.quantidade_bom, s.quantidade_mau
    FROM eleitoral_material_sobrante s
    JOIN eleitoral_local_armazenamento l ON s.local_id = l.id
    JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
    WHERE l.tipo = 'CENTRAL' OR l.nome LIKE '%CENTRAL%'
""")
rows = c.fetchall()

if rows:
    print(f"Encontrados {len(rows)} registos no STAE Central:")
    for r in rows:
        variante = f" ({r[1]})" if r[1] else ""
        print(f"- {r[0]}{variante}: Total={r[2]}, Bom={r[3]}, Mau={r[4]}")
else:
    print("Nenhum sobrante registado no STAE Central atualmente.")
conn.close()
