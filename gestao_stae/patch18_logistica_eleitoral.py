import sqlite3
from app import DB_PATH, get_pg_connection

def apply_patch18():
    print("Aplicando Patch 18: Gestão de Eventos e Logística Activa...")
    
    # --- SQLITE ---
    conn_sqlite = sqlite3.connect(DB_PATH)
    c = conn_sqlite.cursor()
    
    # Adicionar parent_id a eleitoral_local_armazenamento (ignorar erro se existir)
    try:
        c.execute("ALTER TABLE eleitoral_local_armazenamento ADD COLUMN parent_id INTEGER REFERENCES eleitoral_local_armazenamento(id)")
    except sqlite3.OperationalError:
        pass # Coluna já existe
        
    sqlite_ddl = """
    CREATE TABLE IF NOT EXISTS eleitoral_evento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        processo_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        nome TEXT NOT NULL,
        data_inicio DATE,
        data_fim DATE,
        estado TEXT NOT NULL DEFAULT 'PLANEADO',
        FOREIGN KEY (processo_id) REFERENCES eleitoral_processo_eleitoral(id)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_movimento_material (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        processo_id INTEGER NOT NULL,
        evento_id INTEGER,
        local_origem_id INTEGER NOT NULL,
        local_destino_id INTEGER NOT NULL,
        estado TEXT NOT NULL DEFAULT 'PENDENTE',
        data_envio DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        data_recepcao DATETIME,
        utilizador_envio_id INTEGER,
        utilizador_recepcao_id INTEGER,
        observacoes_envio TEXT,
        observacoes_recepcao TEXT,
        FOREIGN KEY (processo_id) REFERENCES eleitoral_processo_eleitoral(id),
        FOREIGN KEY (evento_id) REFERENCES eleitoral_evento(id),
        FOREIGN KEY (local_origem_id) REFERENCES eleitoral_local_armazenamento(id),
        FOREIGN KEY (local_destino_id) REFERENCES eleitoral_local_armazenamento(id)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_movimento_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        movimento_id INTEGER NOT NULL,
        tipo_material_id INTEGER NOT NULL,
        quantidade_bom REAL NOT NULL DEFAULT 0,
        quantidade_mau REAL NOT NULL DEFAULT 0,
        FOREIGN KEY (movimento_id) REFERENCES eleitoral_movimento_material(id),
        FOREIGN KEY (tipo_material_id) REFERENCES eleitoral_tipo_material(id)
    );
    """
    c.executescript(sqlite_ddl)
    conn_sqlite.commit()
    conn_sqlite.close()
    
    # --- POSTGRES ---
    pg_conn = get_pg_connection()
    if pg_conn:
        pc = pg_conn.cursor()
        
        try:
            pc.execute("ALTER TABLE eleitoral_local_armazenamento ADD COLUMN parent_id INTEGER REFERENCES eleitoral_local_armazenamento(id)")
        except Exception:
            pg_conn.rollback() # Coluna já existe ou erro
        else:
            pg_conn.commit()

        pg_ddl = """
        CREATE TABLE IF NOT EXISTS eleitoral_evento (
            id SERIAL PRIMARY KEY,
            processo_id INTEGER NOT NULL REFERENCES eleitoral_processo_eleitoral(id),
            tipo VARCHAR(50) NOT NULL,
            nome VARCHAR(150) NOT NULL,
            data_inicio DATE,
            data_fim DATE,
            estado VARCHAR(20) NOT NULL DEFAULT 'PLANEADO'
        );

        CREATE TABLE IF NOT EXISTS eleitoral_movimento_material (
            id SERIAL PRIMARY KEY,
            processo_id INTEGER NOT NULL REFERENCES eleitoral_processo_eleitoral(id),
            evento_id INTEGER REFERENCES eleitoral_evento(id),
            local_origem_id INTEGER NOT NULL REFERENCES eleitoral_local_armazenamento(id),
            local_destino_id INTEGER NOT NULL REFERENCES eleitoral_local_armazenamento(id),
            estado VARCHAR(20) NOT NULL DEFAULT 'PENDENTE',
            data_envio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            data_recepcao TIMESTAMP,
            utilizador_envio_id INTEGER,
            utilizador_recepcao_id INTEGER,
            observacoes_envio VARCHAR(255),
            observacoes_recepcao VARCHAR(255)
        );

        CREATE TABLE IF NOT EXISTS eleitoral_movimento_item (
            id BIGSERIAL PRIMARY KEY,
            movimento_id INTEGER NOT NULL REFERENCES eleitoral_movimento_material(id),
            tipo_material_id INTEGER NOT NULL REFERENCES eleitoral_tipo_material(id),
            quantidade_bom DECIMAL(12,2) NOT NULL DEFAULT 0,
            quantidade_mau DECIMAL(12,2) NOT NULL DEFAULT 0
        );
        """
        pc.execute(pg_ddl)
        pg_conn.commit()
        pg_conn.close()
        print("[+] Patch 18 PostgreSQL aplicado.")
    else:
        print("[-] Banco PostgreSQL não detectado. Apenas SQLite.")

if __name__ == "__main__":
    apply_patch18()
    print("Patch 18 concluído.")
