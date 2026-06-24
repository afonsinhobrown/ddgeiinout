import os
import sys

# Enable cloud mode
os.environ["CLOUD_MODE"] = "true"

# Add path to import app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import app
import sqlite3

try:
    print("Testing smart_connect in Cloud Mode...")
    # This should connect to PostgreSQL via smart_connect
    conn = sqlite3.connect('any_dummy_path_doesnt_matter')
    print(f"Connection class: {conn.__class__.__name__}")
    
    c = conn.cursor()
    print(f"Cursor class: {c.__class__.__name__}")
    
    # Test executing a query with sqlite ? placeholders and setor_id column name
    # We will query users since it exists in our PG db.
    print("\nExecuting query on users...")
    c.execute("SELECT id, username, perfil, nome_completo FROM users LIMIT 1")
    row = c.fetchone()
    print(f"Result row: {row}")
    
    # Test method chaining (common in app.py)
    print("\nTesting method chaining: c.execute(...).fetchall()...")
    rows = c.execute("SELECT id FROM users LIMIT 2").fetchall()
    print(f"Chained result rows: {rows}")
    
    # Test query with column mapping: select from funcionarios using setor_id
    print("\nTesting column mapping (setor_id -> sector_id) on funcionarios...")
    c.execute("SELECT id, nome, cargo, setor_id FROM funcionarios LIMIT 1")
    func_row = c.fetchone()
    print(f"Funcionarios row (mapped successfully!): {func_row}")
    
    conn.close()
    print("\nAll tests passed successfully!")
    
except Exception as e:
    import traceback
    print(f"\nERROR: {e}")
    traceback.print_exc()
