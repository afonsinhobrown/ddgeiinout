import sqlite3

def populate_local_armazenamento():
    from app import DB_PATH, get_pg_connection
    conn_sl = sqlite3.connect(DB_PATH)
    conn_pg = get_pg_connection()
    c_sl = conn_sl.cursor()
    c_pg = conn_pg.cursor()
    
    # For SQLite
    queries_sl = [
        "INSERT OR IGNORE INTO eleitoral_local_armazenamento (tipo, provincia_id, nome) SELECT 'PROVINCIA', id, nome FROM eleitoral_provincia",
        "INSERT OR IGNORE INTO eleitoral_local_armazenamento (tipo, pais_diaspora_id, nome) SELECT 'PAIS_DIASPORA', id, nome FROM eleitoral_pais_diaspora",
        "INSERT OR IGNORE INTO eleitoral_local_armazenamento (tipo, nome, observacoes) VALUES ('CENTRAL', 'STAE Central', 'Departamento')"
    ]
    
    # For Postgres
    queries_pg = [
        "INSERT INTO eleitoral_local_armazenamento (tipo, provincia_id, nome) SELECT 'PROVINCIA', id, nome FROM eleitoral_provincia ON CONFLICT DO NOTHING",
        "INSERT INTO eleitoral_local_armazenamento (tipo, pais_diaspora_id, nome) SELECT 'PAIS_DIASPORA', id, nome FROM eleitoral_pais_diaspora ON CONFLICT DO NOTHING",
        "INSERT INTO eleitoral_local_armazenamento (tipo, nome, observacoes) VALUES ('CENTRAL', 'STAE Central', 'Departamento') ON CONFLICT DO NOTHING"
    ]
    
    for q in queries_sl:
        try:
            c_sl.execute(q)
        except Exception as e:
            print("SQLite erro:", e)
            
    if conn_pg:
        for q in queries_pg:
            try:
                c_pg.execute(q)
            except Exception as e:
                print("PG erro:", e)
                
    conn_sl.commit()
    if conn_pg: conn_pg.commit()
    
    conn_sl.close()
    if conn_pg: conn_pg.close()
    
    print("Locais de armazenamento criados.")

if __name__ == '__main__':
    populate_local_armazenamento()
