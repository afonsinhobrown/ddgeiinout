import traceback
import sys
import os

# Set environment variables if needed
os.environ["ORIGEM_CADASTRO"] = "local"

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app import sync_lookup_table, sync_users, sync_funcionarios, sync_movimentos, sync_inventario_local, init_pg_db
except Exception as e:
    print("Error importing from app.py:")
    traceback.print_exc()
    sys.exit(1)

print("Initializing PG DB if possible...")
try:
    init_pg_db()
except Exception as e:
    print(f"Failed to init PG DB: {e}")

funcs = [
    ("sync_lookup_table sectores", lambda: sync_lookup_table("setores")),
    ("sync_lookup_table marcas", lambda: sync_lookup_table("marcas")),
    ("sync_lookup_table tipos_equipamento", lambda: sync_lookup_table("tipos_equipamento")),
    ("sync_lookup_table motivos", lambda: sync_lookup_table("motivos")),
    ("sync_lookup_table fornecedores", lambda: sync_lookup_table("fornecedores")),
    ("sync_lookup_table instituicoes", lambda: sync_lookup_table("instituicoes")),
    ("sync_users", sync_users),
    ("sync_funcionarios", sync_funcionarios),
    ("sync_movimentos", sync_movimentos),
    ("sync_inventario_local", sync_inventario_local)
]

for name, func in funcs:
    print(f"\nRunning {name}...")
    try:
        res = func()
        print(f"Finished {name} with result: {res}")
    except Exception as e:
        print(f"EXCEPTION in {name}: {e}")
        traceback.print_exc()
