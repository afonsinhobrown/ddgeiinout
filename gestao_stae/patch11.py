import re
import os

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update check_db_integrity
old_integrity = '''def check_db_integrity(c):
    try:
        c.execute("PRAGMA table_info(movimentos)")
        cols = [row[1] for row in c.fetchall()]
        if 'entregue_por' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN entregue_por TEXT")
        if 'recebido_por' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN recebido_por TEXT")
        if 'agente_protecao' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN agente_protecao TEXT")
        if 'fornecedor' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN fornecedor TEXT")
        if 'quantidade' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN quantidade TEXT")'''

new_integrity = '''def check_db_integrity(c):
    try:
        c.execute("PRAGMA table_info(movimentos)")
        cols = [row[1] for row in c.fetchall()]
        if 'entregue_por' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN entregue_por TEXT")
        if 'recebido_por' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN recebido_por TEXT")
        if 'agente_protecao' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN agente_protecao TEXT")
        if 'fornecedor' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN fornecedor TEXT")
        if 'quantidade' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN quantidade TEXT")
        if 'setor_origem_id' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN setor_origem_id INTEGER")
        if 'setor_destino_id' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN setor_destino_id INTEGER")
        
        c.execute("PRAGMA table_info(users)")
        u_cols = [row[1] for row in c.fetchall()]
        if 'setor_id' not in u_cols: 
            c.execute("ALTER TABLE users ADD COLUMN setor_id INTEGER")
            c.execute("UPDATE users SET setor_id = 1 WHERE perfil != 'admin' AND setor_id IS NULL")'''

if old_integrity in content:
    content = content.replace(old_integrity, new_integrity)
    print("Updated check_db_integrity")
else:
    print("Failed to find check_db_integrity")

# 2. Add dependencies to requirements.txt and executar.bat
with open('requirements.txt', 'r', encoding='utf-8') as f:
    reqs = f.read()
if 'openpyxl' not in reqs:
    with open('requirements.txt', 'a', encoding='utf-8') as f:
        f.write('\nopenpyxl')
    print("Updated requirements.txt")

with open('executar.bat', 'r', encoding='utf-8') as f:
    bat = f.read()
if 'openpyxl' not in bat:
    bat = bat.replace('pip install flask reportlab', 'pip install flask reportlab openpyxl')
    with open('executar.bat', 'w', encoding='utf-8') as f:
        f.write(bat)
    print("Updated executar.bat")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Patch 11 executed.")
