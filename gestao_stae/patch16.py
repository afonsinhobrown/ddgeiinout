import sqlite3
from app import DB_PATH, get_pg_connection

def fix_database_movimentos():
    s_conn = sqlite3.connect(DB_PATH)
    s_c = s_conn.cursor()
    
    # Check if there are null sectors in movimentos
    s_c.execute("UPDATE movimentos SET setor_origem_id = 1, setor_destino_id = 1 WHERE setor_origem_id IS NULL AND setor_destino_id IS NULL")
    s_conn.commit()
    s_conn.close()
    
    # Also update Postgres
    pg_conn = get_pg_connection()
    if pg_conn:
        pg_c = pg_conn.cursor()
        pg_c.execute("UPDATE movimentos SET setor_origem_id = 1, setor_destino_id = 1 WHERE setor_origem_id IS NULL AND setor_destino_id IS NULL")
        pg_conn.commit()
        pg_conn.close()
        
    print("Database data fixed. All unassigned movimentos now have origin and destination as sector 1.")

if __name__ == '__main__':
    fix_database_movimentos()
