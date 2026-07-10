import sqlite3

def sync_sqlite_to_pg():
    from app import DB_PATH, get_pg_connection
    conn_pg = get_pg_connection()
    if not conn_pg:
        print("PG nao disponivel")
        return
        
    conn_sl = sqlite3.connect(DB_PATH)
    c_sl = conn_sl.cursor()
    c_pg = conn_pg.cursor()
    
    # Processos
    c_sl.execute("SELECT id, nome, tipo, ano, estado FROM eleitoral_processo_eleitoral")
    processos = c_sl.fetchall()
    for row in processos:
        c_pg.execute("""
            INSERT INTO eleitoral_processo_eleitoral (id, nome, tipo, ano, estado) 
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET estado=EXCLUDED.estado
        """, row)
        
    # Tipo de Material
    c_sl.execute("SELECT id, categoria_id, nome, variante, unidade_medida, controla_estado FROM eleitoral_tipo_material")
    for row in c_sl.fetchall():
        c_pg.execute("""
            INSERT INTO eleitoral_tipo_material (id, categoria_id, nome, variante, unidade_medida, controla_estado) 
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, row)
        
    # Categorias
    c_sl.execute("SELECT id, nome FROM eleitoral_categoria_material")
    for row in c_sl.fetchall():
        c_pg.execute("""
            INSERT INTO eleitoral_categoria_material (id, nome) 
            VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
        """, row)

    # Sobrantes
    c_pg.execute("TRUNCATE TABLE eleitoral_material_sobrante CASCADE")
    c_sl.execute("SELECT processo_id, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau, origem, utilizador_id FROM eleitoral_material_sobrante")
    sobrantes = c_sl.fetchall()
    for row in sobrantes:
        c_pg.execute("""
            INSERT INTO eleitoral_material_sobrante 
            (processo_id, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau, origem, utilizador_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, row)
        
    conn_pg.commit()
    conn_pg.close()
    conn_sl.close()
    print("Sincronizacao para PG concluida!")

if __name__ == "__main__":
    sync_sqlite_to_pg()
