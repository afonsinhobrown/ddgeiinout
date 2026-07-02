import os
import sys
sys.path.insert(0, os.path.abspath('gestao_stae'))
import sqlite3
import psycopg2

SYNC_CONFIG = {
    'users': ['username'],
    'setores': ['nome'],
    'funcionarios': ['nome'],
    'movimentos': ['guia'],
    'marcas': ['nome'],
    'tipos_equipamento': ['nome'],
    'motivos': ['nome'],
    'fornecedores': ['nome'],
    'instituicoes': ['nome'],
    'inventario_local': ['equipamento', 'marca', 'numero_serie']
}

def get_table_columns(cursor, table_name, is_pg=False):
    if is_pg:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table_name,))
        return [row[0] for row in cursor.fetchall() if row[0] != 'id']
    else:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor.fetchall() if row[1] != 'id']

def normalize_pg_schema(pg_c):
    # Rename sector_id to setor_id in Postgres if it exists
    try:
        pg_c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'funcionarios' AND column_name = 'sector_id'")
        if pg_c.fetchone():
            pg_c.execute("ALTER TABLE funcionarios RENAME COLUMN sector_id TO setor_id")
            print("Renamed sector_id to setor_id in Postgres.")
    except Exception as e:
        print("Error normalizing schema:", e)

def sync_schema_dynamic(s_c, pg_c, table_name):
    s_cols = get_table_columns(s_c, table_name, is_pg=False)
    pg_cols = get_table_columns(pg_c, table_name, is_pg=True)
    
    # ADD to Postgres what is missing
    for col in s_cols:
        if col not in pg_cols:
            print(f"Adding column {col} to PG table {table_name}")
            try:
                pg_c.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} VARCHAR")
            except Exception as e:
                print(f"Error adding {col} to PG: {e}")
                
    # ADD to SQLite what is missing
    for col in pg_cols:
        if col not in s_cols:
            print(f"Adding column {col} to SQLite table {table_name}")
            try:
                s_c.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} TEXT")
            except Exception as e:
                print(f"Error adding {col} to SQLite: {e}")

def get_common_columns(s_c, pg_c, table_name):
    s_cols = get_table_columns(s_c, table_name, is_pg=False)
    pg_cols = get_table_columns(pg_c, table_name, is_pg=True)
    return [c for c in s_cols if c in pg_cols]

def get_records_dict(cursor, table_name, columns, unique_keys, is_pg=False):
    cols_str = ", ".join(columns)
    if is_pg:
        cursor.execute(f"SELECT {cols_str} FROM {table_name}")
    else:
        cursor.execute(f"SELECT {cols_str} FROM {table_name}")
        
    records = cursor.fetchall()
    res = {}
    for r in records:
        d = dict(zip(columns, r))
        # Build composite key
        key = tuple(str(d.get(k, '')) for k in unique_keys)
        res[key] = d
    return res

def sync_table_dynamic(s_conn, pg_conn, table_name, unique_keys):
    s_c = s_conn.cursor()
    pg_c = pg_conn.cursor()
    
    sync_schema_dynamic(s_c, pg_c, table_name)
    columns = get_common_columns(s_c, pg_c, table_name)
    
    if 'last_modified' not in columns or 'origem_registo' not in columns:
        print(f"Table {table_name} missing sync columns.")
        return
        
    s_records = get_records_dict(s_c, table_name, columns, unique_keys, is_pg=False)
    pg_records = get_records_dict(pg_c, table_name, columns, unique_keys, is_pg=True)
    
    # From SQLite to PG
    for key, s_rec in s_records.items():
        if key not in pg_records:
            cols = list(s_rec.keys())
            vals = list(s_rec.values())
            placeholders = ", ".join(["%s"] * len(cols))
            cols_str = ", ".join(cols)
            pg_c.execute(f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})", vals)
        elif str(s_rec.get('last_modified', '')) > str(pg_records[key].get('last_modified', '')):
            cols = list(s_rec.keys())
            vals = list(s_rec.values())
            set_str = ", ".join([f"{c}=%s" for c in cols])
            where_str = " AND ".join([f"{k}=%s" for k in unique_keys])
            where_vals = [s_rec[k] for k in unique_keys]
            pg_c.execute(f"UPDATE {table_name} SET {set_str} WHERE {where_str}", vals + where_vals)
            
    # From PG to SQLite
    for key, pg_rec in pg_records.items():
        if key not in s_records:
            cols = list(pg_rec.keys())
            vals = list(pg_rec.values())
            placeholders = ", ".join(["?"] * len(cols))
            cols_str = ", ".join(cols)
            s_c.execute(f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})", vals)
        elif str(pg_rec.get('last_modified', '')) > str(s_records[key].get('last_modified', '')):
            cols = list(pg_rec.keys())
            vals = list(pg_rec.values())
            set_str = ", ".join([f"{c}=?" for c in cols])
            where_str = " AND ".join([f"{k}=?" for k in unique_keys])
            where_vals = [pg_rec[k] for k in unique_keys]
            s_c.execute(f"UPDATE {table_name} SET {set_str} WHERE {where_str}", vals + where_vals)

if __name__ == "__main__":
    from app import get_pg_connection, DB_PATH
    pg_conn = get_pg_connection()
    s_conn = sqlite3.connect(DB_PATH)
    normalize_pg_schema(pg_conn.cursor())
    pg_conn.commit()
    
    for table, keys in SYNC_CONFIG.items():
        print(f"Syncing {table}...")
        sync_table_dynamic(s_conn, pg_conn, table, keys)
        
    pg_conn.commit()
    s_conn.commit()
    pg_conn.close()
    s_conn.close()
    print("Done!")
