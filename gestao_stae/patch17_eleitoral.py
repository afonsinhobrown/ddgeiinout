import sqlite3
from app import DB_PATH, get_pg_connection

def create_eleitoral_tables():
    print("Iniciando migração de Gestão de Material Eleitoral...")
    
    # --- SQLITE DDL ---
    sqlite_ddl = """
    CREATE TABLE IF NOT EXISTS eleitoral_provincia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL UNIQUE,
        nome TEXT NOT NULL UNIQUE,
        activo INTEGER NOT NULL DEFAULT 1,
        criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS eleitoral_pais_diaspora (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_iso TEXT,
        nome TEXT NOT NULL UNIQUE,
        continente TEXT,
        activo INTEGER NOT NULL DEFAULT 1,
        criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS eleitoral_local_armazenamento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL,
        provincia_id INTEGER,
        pais_diaspora_id INTEGER,
        nome TEXT NOT NULL,
        observacoes TEXT,
        activo INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (provincia_id) REFERENCES eleitoral_provincia(id),
        FOREIGN KEY (pais_diaspora_id) REFERENCES eleitoral_pais_diaspora(id)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_categoria_material (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS eleitoral_tipo_material (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        categoria_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        variante TEXT,
        unidade_medida TEXT NOT NULL DEFAULT 'Unidade',
        controla_estado INTEGER NOT NULL DEFAULT 1,
        activo INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (categoria_id) REFERENCES eleitoral_categoria_material(id)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_processo_eleitoral (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        tipo TEXT NOT NULL,
        ano INTEGER NOT NULL,
        data_inicio DATE,
        data_fim DATE,
        estado TEXT NOT NULL DEFAULT 'PLANEADO',
        observacoes TEXT,
        criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS eleitoral_material_sobrante (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        processo_id INTEGER NOT NULL,
        local_id INTEGER NOT NULL,
        tipo_material_id INTEGER NOT NULL,
        quantidade_total REAL NOT NULL DEFAULT 0,
        quantidade_bom REAL NOT NULL DEFAULT 0,
        quantidade_mau REAL NOT NULL DEFAULT 0,
        origem TEXT NOT NULL DEFAULT 'REGISTO_DIRECTO',
        processo_origem_id INTEGER,
        observacoes TEXT,
        utilizador_id INTEGER,
        criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        actualizado_em DATETIME,
        FOREIGN KEY (processo_id) REFERENCES eleitoral_processo_eleitoral(id),
        FOREIGN KEY (local_id) REFERENCES eleitoral_local_armazenamento(id),
        FOREIGN KEY (tipo_material_id) REFERENCES eleitoral_tipo_material(id),
        FOREIGN KEY (processo_origem_id) REFERENCES eleitoral_processo_eleitoral(id),
        UNIQUE (processo_id, local_id, tipo_material_id)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_transferencia_sobrantes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        processo_origem_id INTEGER NOT NULL,
        processo_destino_id INTEGER NOT NULL,
        data_transferencia DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        utilizador_id INTEGER,
        observacoes TEXT,
        FOREIGN KEY (processo_origem_id) REFERENCES eleitoral_processo_eleitoral(id),
        FOREIGN KEY (processo_destino_id) REFERENCES eleitoral_processo_eleitoral(id)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_transferencia_sobrantes_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transferencia_id INTEGER NOT NULL,
        local_id INTEGER NOT NULL,
        tipo_material_id INTEGER NOT NULL,
        quantidade_total REAL NOT NULL,
        quantidade_bom REAL NOT NULL,
        quantidade_mau REAL NOT NULL,
        FOREIGN KEY (transferencia_id) REFERENCES eleitoral_transferencia_sobrantes(id),
        FOREIGN KEY (local_id) REFERENCES eleitoral_local_armazenamento(id),
        FOREIGN KEY (tipo_material_id) REFERENCES eleitoral_tipo_material(id)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_importacao_material (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        processo_id INTEGER NOT NULL,
        nome_ficheiro TEXT NOT NULL,
        data_importacao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        utilizador_id INTEGER,
        total_linhas INTEGER NOT NULL DEFAULT 0,
        total_sucesso INTEGER NOT NULL DEFAULT 0,
        total_erro INTEGER NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'EM_PROCESSAMENTO',
        FOREIGN KEY (processo_id) REFERENCES eleitoral_processo_eleitoral(id)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_importacao_material_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        importacao_id INTEGER NOT NULL,
        numero_linha INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        mensagem TEXT NOT NULL,
        FOREIGN KEY (importacao_id) REFERENCES eleitoral_importacao_material(id)
    );
    """

    # --- POSTGRES DDL ---
    pg_ddl = """
    CREATE TABLE IF NOT EXISTS eleitoral_provincia (
        id SERIAL PRIMARY KEY,
        codigo VARCHAR(10) NOT NULL UNIQUE,
        nome VARCHAR(60) NOT NULL UNIQUE,
        activo SMALLINT NOT NULL DEFAULT 1,
        criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS eleitoral_pais_diaspora (
        id SERIAL PRIMARY KEY,
        codigo_iso VARCHAR(3),
        nome VARCHAR(60) NOT NULL UNIQUE,
        continente VARCHAR(30),
        activo SMALLINT NOT NULL DEFAULT 1,
        criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS eleitoral_local_armazenamento (
        id SERIAL PRIMARY KEY,
        tipo VARCHAR(20) NOT NULL,
        provincia_id INTEGER REFERENCES eleitoral_provincia(id),
        pais_diaspora_id INTEGER REFERENCES eleitoral_pais_diaspora(id),
        nome VARCHAR(120) NOT NULL,
        observacoes VARCHAR(255),
        activo SMALLINT NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS eleitoral_categoria_material (
        id SERIAL PRIMARY KEY,
        nome VARCHAR(60) NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS eleitoral_tipo_material (
        id SERIAL PRIMARY KEY,
        categoria_id INTEGER NOT NULL REFERENCES eleitoral_categoria_material(id),
        nome VARCHAR(100) NOT NULL,
        variante VARCHAR(60),
        unidade_medida VARCHAR(20) NOT NULL DEFAULT 'Unidade',
        controla_estado SMALLINT NOT NULL DEFAULT 1,
        activo SMALLINT NOT NULL DEFAULT 1,
        CONSTRAINT uq_eleitoral_tipo_material UNIQUE (nome, variante)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_processo_eleitoral (
        id SERIAL PRIMARY KEY,
        nome VARCHAR(150) NOT NULL,
        tipo VARCHAR(60) NOT NULL,
        ano SMALLINT NOT NULL,
        data_inicio DATE,
        data_fim DATE,
        estado VARCHAR(20) NOT NULL DEFAULT 'PLANEADO',
        observacoes VARCHAR(255),
        criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS eleitoral_material_sobrante (
        id BIGSERIAL PRIMARY KEY,
        processo_id INTEGER NOT NULL REFERENCES eleitoral_processo_eleitoral(id),
        local_id INTEGER NOT NULL REFERENCES eleitoral_local_armazenamento(id),
        tipo_material_id INTEGER NOT NULL REFERENCES eleitoral_tipo_material(id),
        quantidade_total DECIMAL(12,2) NOT NULL DEFAULT 0,
        quantidade_bom DECIMAL(12,2) NOT NULL DEFAULT 0,
        quantidade_mau DECIMAL(12,2) NOT NULL DEFAULT 0,
        origem VARCHAR(50) NOT NULL DEFAULT 'REGISTO_DIRECTO',
        processo_origem_id INTEGER REFERENCES eleitoral_processo_eleitoral(id),
        observacoes VARCHAR(255),
        utilizador_id INTEGER,
        criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        actualizado_em TIMESTAMP,
        CONSTRAINT uq_eleitoral_ms_linha UNIQUE (processo_id, local_id, tipo_material_id)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_transferencia_sobrantes (
        id SERIAL PRIMARY KEY,
        processo_origem_id INTEGER NOT NULL REFERENCES eleitoral_processo_eleitoral(id),
        processo_destino_id INTEGER NOT NULL REFERENCES eleitoral_processo_eleitoral(id),
        data_transferencia TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        utilizador_id INTEGER,
        observacoes VARCHAR(255)
    );

    CREATE TABLE IF NOT EXISTS eleitoral_transferencia_sobrantes_item (
        id BIGSERIAL PRIMARY KEY,
        transferencia_id INTEGER NOT NULL REFERENCES eleitoral_transferencia_sobrantes(id),
        local_id INTEGER NOT NULL REFERENCES eleitoral_local_armazenamento(id),
        tipo_material_id INTEGER NOT NULL REFERENCES eleitoral_tipo_material(id),
        quantidade_total DECIMAL(12,2) NOT NULL,
        quantidade_bom DECIMAL(12,2) NOT NULL,
        quantidade_mau DECIMAL(12,2) NOT NULL
    );

    CREATE TABLE IF NOT EXISTS eleitoral_importacao_material (
        id SERIAL PRIMARY KEY,
        processo_id INTEGER NOT NULL REFERENCES eleitoral_processo_eleitoral(id),
        nome_ficheiro VARCHAR(255) NOT NULL,
        data_importacao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        utilizador_id INTEGER,
        total_linhas INTEGER NOT NULL DEFAULT 0,
        total_sucesso INTEGER NOT NULL DEFAULT 0,
        total_erro INTEGER NOT NULL DEFAULT 0,
        estado VARCHAR(30) NOT NULL DEFAULT 'EM_PROCESSAMENTO'
    );

    CREATE TABLE IF NOT EXISTS eleitoral_importacao_material_log (
        id BIGSERIAL PRIMARY KEY,
        importacao_id INTEGER NOT NULL REFERENCES eleitoral_importacao_material(id),
        numero_linha INTEGER NOT NULL,
        tipo VARCHAR(10) NOT NULL,
        mensagem VARCHAR(255) NOT NULL
    );
    """

    # --- SEED DATA ---
    seed_data = {
        'provincia': [
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('CMPT','Cidade de Maputo') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('MPT','Maputo') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('GZA','Gaza') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('INH','Inhambane') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('SOF','Sofala') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('MAN','Manica') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('TET','Tete') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('ZAM','Zambézia') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('NAM','Nampula') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('CDL','Cabo Delgado') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_provincia (codigo, nome) VALUES ('NIA','Niassa') ON CONFLICT DO NOTHING;"
        ],
        'pais': [
            "INSERT INTO eleitoral_pais_diaspora (codigo_iso, nome, continente) VALUES ('ZAF','África do Sul','África') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_pais_diaspora (codigo_iso, nome, continente) VALUES ('SWZ','Eswatini','África') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_pais_diaspora (codigo_iso, nome, continente) VALUES ('ZWE','Zimbabwe','África') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_pais_diaspora (codigo_iso, nome, continente) VALUES ('MWI','Malawi','África') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_pais_diaspora (codigo_iso, nome, continente) VALUES ('ZMB','Zâmbia','África') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_pais_diaspora (codigo_iso, nome, continente) VALUES ('TZA','Tanzânia','África') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_pais_diaspora (codigo_iso, nome, continente) VALUES ('KEN','Quénia','África') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_pais_diaspora (codigo_iso, nome, continente) VALUES ('PRT','Portugal','Europa') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_pais_diaspora (codigo_iso, nome, continente) VALUES ('DEU','Alemanha','Europa') ON CONFLICT DO NOTHING;"
        ],
        'categoria': [
            "INSERT INTO eleitoral_categoria_material (nome) VALUES ('Equipamento Electrónico') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_categoria_material (nome) VALUES ('Equipamento de Identificação/Impressão') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_categoria_material (nome) VALUES ('Consumível') ON CONFLICT DO NOTHING;",
            "INSERT INTO eleitoral_categoria_material (nome) VALUES ('Mobiliário e Acessório') ON CONFLICT DO NOTHING;"
        ]
    }
    
    # Adaptação para SQLite (ON CONFLICT DO NOTHING -> INSERT OR IGNORE)
    sqlite_seed_data = {}
    for key, queries in seed_data.items():
        sqlite_seed_data[key] = [q.replace('ON CONFLICT DO NOTHING', '').replace('INSERT INTO', 'INSERT OR IGNORE INTO') for q in queries]

    # --- APPLY SQLITE ---
    try:
        s_conn = sqlite3.connect(DB_PATH)
        s_c = s_conn.cursor()
        
        # Create tables
        for statement in sqlite_ddl.split(';'):
            if statement.strip():
                s_c.execute(statement)
                
        # Insert base catalogs
        for queries in sqlite_seed_data.values():
            for query in queries:
                try:
                    s_c.execute(query)
                except sqlite3.IntegrityError:
                    pass # Already exists
        
        s_conn.commit()
        print("SQLITE: Tabelas eleitorais criadas e catálogos preenchidos.")
        s_conn.close()
    except Exception as e:
        print(f"Erro ao aplicar patch no SQLite: {e}")

    # --- APPLY POSTGRES ---
    try:
        pg_conn = get_pg_connection()
        if pg_conn:
            pg_c = pg_conn.cursor()
            
            for statement in pg_ddl.split(';'):
                if statement.strip():
                    pg_c.execute(statement)
            
            for queries in seed_data.values():
                for query in queries:
                    try:
                        pg_c.execute(query)
                    except Exception as pg_e:
                        print(f"Postgres Insert Error (ignored): {pg_e}")
                        pg_conn.rollback()
                        continue
            
            pg_conn.commit()
            print("POSTGRES: Tabelas eleitorais criadas e catálogos preenchidos.")
            pg_conn.close()
        else:
            print("POSTGRES: Conexão não disponível, saltando DB remota.")
    except Exception as e:
        print(f"Erro ao aplicar patch no Postgres: {e}")

if __name__ == '__main__':
    create_eleitoral_tables()
