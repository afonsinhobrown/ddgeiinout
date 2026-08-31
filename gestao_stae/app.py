import os
import sqlite3
import decimal
sqlite3.register_adapter(decimal.Decimal, float)
import webbrowser
from datetime import datetime
from threading import Timer
import threading
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_file, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import hashlib
import io
import psycopg2
import socket
from PIL import Image

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'documentos')
if not os.path.exists(UPLOAD_FOLDER):
    try: os.makedirs(UPLOAD_FOLDER)
    except Exception: pass

def imagem_para_pdf(f, nome_base):
    """Converte imagem anexada para PDF e devolve o nome do ficheiro criado (ou None)."""
    try:
        img = Image.open(f)
        img = img.convert('RGB')
        from reportlab.pdfgen import canvas as _canvas
        from reportlab.lib.pagesizes import A4 as _A4
        nome = f"{nome_base}.pdf"
        caminho = os.path.join(UPLOAD_FOLDER, nome)
        w_px, h_px = img.size
        c = _canvas.Canvas(caminho, pagesize=_A4)
        c.drawImage(ImageReader(img), 0, 0, width=_A4[0], height=_A4[1], preserveAspectRatio=True, anchor='c')
        c.save()
        return nome
    except Exception as e:
        print(f"[-] Erro ao converter imagem para PDF: {e}")
        return None

def generate_guia(tipo, cursor):
    # Try to get MACHINE_ID from environment, fallback to hostname hash
    mid = os.environ.get("MACHINE_ID")
    if not mid:
        try:
            hostname = socket.gethostname() or "default"
        except Exception:
            hostname = "default"
        mid = hashlib.md5(hostname.encode()).hexdigest().upper()[:4]
    else:
        mid = mid.strip().upper()[:4]
        
    count = len(cursor.execute('SELECT id FROM movimentos').fetchall()) + 1
    return f"{tipo}-{datetime.now().year}-{mid}-{count:04d}"

# ---------------------------------------------------------
# HYBRID DATABASE WRAPPER FOR SEAMLESS CLOUD/LOCAL DEPLOYMENT
# ---------------------------------------------------------
from flask import has_request_context, request

def is_cloud_mode():
    # 1. Verifica variáveis de ambiente
    if (os.environ.get('CLOUD_MODE') == 'true' or
        os.environ.get('VERCEL') == '1' or
        os.environ.get('RENDER') == 'true' or
        os.environ.get('ORIGEM_CADASTRO') == 'nuvem'):
        return True
    
    # 2. Verifica a URL ativa (Fallback à prova de bala)
    if has_request_context():
        if 'vercel.app' in request.host:
            return True
            
    return False

class PGCursorWrapper:
    def __init__(self, pg_cursor):
        self.pg_cursor = pg_cursor
    def execute(self, query, params=None):
        # Translate query placeholders from ? to %s and column names from setor_id to setor_id
        translated_query = query.replace('?', '%s').replace('setor_id', 'setor_id')
        if params is not None:
            self.pg_cursor.execute(translated_query, params)
        else:
            self.pg_cursor.execute(translated_query)
        return self
    def executemany(self, query, seq_of_params):
        translated_query = query.replace('?', '%s').replace('setor_id', 'setor_id')
        self.pg_cursor.executemany(translated_query, seq_of_params)
        return self
    def fetchone(self):
        return self.pg_cursor.fetchone()
    def fetchall(self):
        return self.pg_cursor.fetchall()
    @property
    def description(self):
        return self.pg_cursor.description
    def close(self):
        self.pg_cursor.close()
    def __enter__(self):
        self.pg_cursor.__enter__()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.pg_cursor.__exit__(exc_type, exc_val, exc_tb)

class PGConnectionWrapper:
    def __init__(self, pg_conn):
        self.pg_conn = pg_conn
    def cursor(self):
        return PGCursorWrapper(self.pg_conn.cursor())
    def commit(self):
        self.pg_conn.commit()
    def rollback(self):
        self.pg_conn.rollback()
    def close(self):
        self.pg_conn.close()
    def __enter__(self):
        self.pg_conn.__enter__()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.pg_conn.__exit__(exc_type, exc_val, exc_tb)

_original_sqlite_connect = sqlite3.connect

def smart_connect(database, *args, **kwargs):
    if is_cloud_mode():
        pg_url = os.environ.get('DATABASE_URL') or os.environ.get('PG_URL') or "postgresql://neondb_owner:npg_3BsxjEU4NCki@ep-withered-truth-asbeszuu-pooler.c-4.eu-central-1.aws.neon.tech/equipamento?sslmode=require&channel_binding=require"
        pg_conn = psycopg2.connect(pg_url)
        return PGConnectionWrapper(pg_conn)
    else:
        return _original_sqlite_connect(database, *args, **kwargs)

sqlite3.connect = smart_connect

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'stae_secret_key_2026'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'stae.db')

def check_and_auto_migrate():
    if not os.path.exists(DB_PATH): return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sectores'")
        has_sectores = c.fetchone()
    except:
        has_sectores = False
    conn.close()
    
    if has_sectores:
        print("[*] Formato de base de dados antigo detetado em stae.db. A iniciar migração automática...")
        try:
            import shutil
            # Create a backup of the old stae.db
            shutil.copy(DB_PATH, os.path.join(BASE_DIR, 'stae_antigo.db'))
            
            # Connect to old database to extract data
            conn_old = sqlite3.connect(os.path.join(BASE_DIR, 'stae_antigo.db'))
            old = conn_old.cursor()
            
            old.execute("SELECT id, username, password, perfil FROM users")
            users = old.fetchall()
            
            old.execute("SELECT id, nome FROM sectores")
            setores = old.fetchall()
            
            old.execute("SELECT id, nome, cargo, setor_id FROM funcionarios")
            funcionarios = old.fetchall()
            
            old.execute("SELECT id, numero_guia, tipo, equipamento_id, quantidade, origem_destino, motivo, data_movimento, status, relatorio_reparacao, tecnico_responsavel, funcionario_entrega_id FROM movimentos")
            movimentos = old.fetchall()
            
            old.execute("SELECT id, numero_serie, marca, tipo FROM equipamentos")
            equip_rows = old.fetchall()
            equip_map = {r[0]: (r[1], r[2], r[3]) for r in equip_rows}
            
            conn_old.close()
            
            # Delete the old file
            os.remove(DB_PATH)
            
            # Create the new database and new tables
            conn_new = sqlite3.connect(DB_PATH)
            new = conn_new.cursor()
            
            new.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, perfil TEXT, nome_completo TEXT)''')
            new.execute('''CREATE TABLE IF NOT EXISTS setores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
            new.execute('''CREATE TABLE IF NOT EXISTS funcionarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, cargo TEXT, setor_id INTEGER, FOREIGN KEY (setor_id) REFERENCES setores(id))''')
            new.execute('''CREATE TABLE IF NOT EXISTS movimentos (id INTEGER PRIMARY KEY AUTOINCREMENT, guia TEXT UNIQUE, tipo TEXT, equipamento TEXT, origem_destino TEXT, motivo TEXT, data TEXT, status TEXT, tecnico TEXT, relatorio TEXT, funcionario_id INTEGER, numero_serie TEXT, marca TEXT, entregue_por TEXT, recebido_por TEXT, agente_protecao TEXT, fornecedor TEXT, quantidade TEXT)''')
            new.execute('''CREATE TABLE IF NOT EXISTS marcas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
            new.execute('''CREATE TABLE IF NOT EXISTS tipos_equipamento (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
            new.execute('''CREATE TABLE IF NOT EXISTS motivos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
            new.execute('''CREATE TABLE IF NOT EXISTS fornecedores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
            new.execute('''CREATE TABLE IF NOT EXISTS instituicoes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
            
            # Pre-populate defaults
            for m in ['Alocação', 'Transferência', 'Reparação', 'Avaria', 'Substituição', 'Outro']:
                new.execute('INSERT OR IGNORE INTO motivos (nome) VALUES (?)', (m,))
            for f in ['N/A', 'NCR', 'Sistec']:
                new.execute('INSERT OR IGNORE INTO fornecedores (nome) VALUES (?)', (f,))
            for t in ['Desktop', 'Laptop', 'Monitor', 'Impressora', 'Mesa', 'Cadeira', 'Scanner', 'Outro']:
                new.execute('INSERT OR IGNORE INTO tipos_equipamento (nome) VALUES (?)', (t,))
            for mc in ['HP', 'Dell', 'Lenovo', 'Epson', 'Canon', 'Brother', 'Apple', 'Outra']:
                new.execute('INSERT OR IGNORE INTO marcas (nome) VALUES (?)', (mc,))
                
            # Migrate Users
            for u in users:
                new.execute("INSERT OR IGNORE INTO users (id, username, password, perfil, nome_completo) VALUES (?,?,?,?,?)", (u[0], u[1], u[2], u[3], u[1]))
                
            # Migrate Setores
            for s in setores:
                new.execute("INSERT OR IGNORE INTO setores (id, nome) VALUES (?,?)", (s[0], s[1]))
                
            # Migrate Funcionários
            for f in funcionarios:
                new.execute("INSERT OR IGNORE INTO funcionarios (id, nome, cargo, setor_id) VALUES (?,?,?,?)", (f[0], f[1], f[2], f[3]))
                
            # Migrate Movimentos
            for m in movimentos:
                eq_id = m[3]
                ns, marca, equip_tipo = equip_map.get(eq_id, (f"SN-{m[0]}", "", "Desconhecido"))
                new.execute('''INSERT OR IGNORE INTO movimentos 
                    (id, guia, tipo, equipamento, origem_destino, motivo, data, status, tecnico, relatorio, funcionario_id, numero_serie, marca, fornecedor, quantidade) 
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
                    (m[0], m[1], m[2], equip_tipo, m[5], m[6], m[7], m[8], m[10], m[9], m[11], ns, marca, 'N/A', m[4]))
            
            conn_new.commit()
            conn_new.close()
            print("[+] Migração automática concluída com sucesso!")
        except Exception as e:
            print(f"[-] Erro na migração automática: {e}")
            if os.path.exists(os.path.join(BASE_DIR, 'stae_antigo.db')):
                shutil.copy(os.path.join(BASE_DIR, 'stae_antigo.db'), DB_PATH)

def check_db_integrity(c):
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
        if 'codigo_barras' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN codigo_barras TEXT")
        if 'documento_pdf' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN documento_pdf TEXT")
        if 'provincia_origem_id' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN provincia_origem_id INTEGER")
        if 'provincia_destino_id' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN provincia_destino_id INTEGER")
        if 'local_origem' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN local_origem TEXT")
        if 'local_destino' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN local_destino TEXT")
        if 'estado_rastreio' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN estado_rastreio TEXT")
        if 'confirmado_destino' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN confirmado_destino TEXT")
        if 'departamento_responsavel_id' not in cols: c.execute("ALTER TABLE movimentos ADD COLUMN departamento_responsavel_id INTEGER")
        
        c.execute("PRAGMA table_info(inventario_local)")
        inv_cols = [row[1] for row in c.fetchall()]
        if 'codigo_barras' not in inv_cols: c.execute("ALTER TABLE inventario_local ADD COLUMN codigo_barras TEXT")
        if 'documento_pdf' not in inv_cols: c.execute("ALTER TABLE inventario_local ADD COLUMN documento_pdf TEXT")
        if 'provincia_id' not in inv_cols: c.execute("ALTER TABLE inventario_local ADD COLUMN provincia_id INTEGER")
        if 'local_uso' not in inv_cols: c.execute("ALTER TABLE inventario_local ADD COLUMN local_uso TEXT")
        if 'estado' not in inv_cols: c.execute("ALTER TABLE inventario_local ADD COLUMN estado TEXT")
        if 'guia_origem' not in inv_cols: c.execute("ALTER TABLE inventario_local ADD COLUMN guia_origem TEXT")
        
        c.execute("PRAGMA table_info(users)")
        u_cols = [row[1] for row in c.fetchall()]
        if 'setor_id' not in u_cols: 
            c.execute("ALTER TABLE users ADD COLUMN setor_id INTEGER")
        # Associar usuarios sem local ao DDGEI por defeito
        c.execute("SELECT id FROM setores WHERE nome LIKE '%DDGEI%' OR nome LIKE '%DELIMITA%' LIMIT 1")
        ddgei_row = c.fetchone()
        ddgei_id = ddgei_row[0] if ddgei_row else 3
        c.execute("UPDATE users SET setor_id = ? WHERE setor_id IS NULL", (ddgei_id,))
        if 'provincia_id' not in u_cols: c.execute("ALTER TABLE users ADD COLUMN provincia_id INTEGER")
        if 'permissoes_estado' not in u_cols: c.execute("ALTER TABLE users ADD COLUMN permissoes_estado TEXT")
        if 'locais_acesso' not in u_cols: c.execute("ALTER TABLE users ADD COLUMN locais_acesso TEXT")
        
        try:
            migrar_schema_eleitoral(c, False)
        except Exception as ex:
            print(f"[-] Erro na migração do schema eleitoral (SQLite): {ex}")
        
        tables = ['users', 'setores', 'funcionarios', 'movimentos', 'marcas', 'tipos_equipamento', 'motivos', 'fornecedores', 'instituicoes', 'inventario_local', 'eleitoral_provincia', 'eleitoral_pais_diaspora', 'eleitoral_local_armazenamento', 'eleitoral_categoria_material', 'eleitoral_tipo_material', 'eleitoral_processo_eleitoral', 'eleitoral_material_sobrante', 'eleitoral_evento', 'eleitoral_movimento_material', 'eleitoral_movimento_historico', 'equipamento_rastreio', 'equipamento_estado_historico']
        for t in tables:
            try:
                c.execute(f"PRAGMA table_info({t})")
                t_cols = [row[1] for row in c.fetchall()]
                if 'last_modified' not in t_cols:
                    c.execute(f"ALTER TABLE {t} ADD COLUMN last_modified TEXT DEFAULT '2026-06-24T00:00:00'")
                if 'origem_registo' not in t_cols:
                    c.execute(f"ALTER TABLE {t} ADD COLUMN origem_registo TEXT DEFAULT 'local'")
            except Exception as ex:
                print(f"[-] Erro ao verificar coluna last_modified na tabela {t}: {ex}")
        c.execute("UPDATE inventario_local SET status='Disponível' WHERE status='Disponvel'")
        c.execute("UPDATE inventario_local SET status='Indisponível' WHERE status='Indisponvel'")
    except Exception as e:
        print(f"[-] Erro na verificação de integridade: {e}")

def migrar_schema_eleitoral(c, is_pg):
    """Cria/manuteni tabelas auxiliares do módulo eleitoral (histórico de movimento e hierarquia de locais)."""
    if is_pg:
        c.execute('''CREATE TABLE IF NOT EXISTS eleitoral_movimento_historico (
            id SERIAL PRIMARY KEY,
            movimento_id INTEGER,
            estado VARCHAR,
            observacoes VARCHAR,
            data VARCHAR,
            utilizador_id INTEGER,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute("ALTER TABLE eleitoral_local_armazenamento ADD COLUMN IF NOT EXISTS tem_filhos INTEGER DEFAULT 0")
        c.execute("ALTER TABLE eleitoral_importacao_material ADD COLUMN IF NOT EXISTS caminho_ficheiro VARCHAR")
        c.execute("ALTER TABLE eleitoral_importacao_material ADD COLUMN IF NOT EXISTS modo VARCHAR DEFAULT 'adicionar'")
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS eleitoral_movimento_historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movimento_id INTEGER,
            estado TEXT,
            observacoes TEXT,
            data TEXT,
            utilizador_id INTEGER
        )''')
        c.execute("PRAGMA table_info(eleitoral_local_armazenamento)")
        la_cols = [row[1] for row in c.fetchall()]
        if 'tem_filhos' not in la_cols:
            c.execute("ALTER TABLE eleitoral_local_armazenamento ADD COLUMN tem_filhos INTEGER DEFAULT 0")
        c.execute("PRAGMA table_info(eleitoral_importacao_material)")
        imp_cols = [row[1] for row in c.fetchall()]
        if 'caminho_ficheiro' not in imp_cols:
            c.execute("ALTER TABLE eleitoral_importacao_material ADD COLUMN caminho_ficheiro TEXT")
        if 'modo' not in imp_cols:
            c.execute("ALTER TABLE eleitoral_importacao_material ADD COLUMN modo TEXT DEFAULT 'adicionar'")

def create_triggers(c):
    origem_padrao = os.environ.get("ORIGEM_CADASTRO") or "local"
    tables = ['users', 'setores', 'funcionarios', 'movimentos', 'marcas', 'tipos_equipamento', 'motivos', 'fornecedores', 'instituicoes', 'inventario_local', 'eleitoral_provincia', 'eleitoral_pais_diaspora', 'eleitoral_local_armazenamento', 'eleitoral_categoria_material', 'eleitoral_tipo_material', 'eleitoral_processo_eleitoral', 'eleitoral_material_sobrante', 'eleitoral_evento', 'eleitoral_movimento_material', 'eleitoral_movimento_historico', 'equipamento_rastreio', 'equipamento_estado_historico']
    for t in tables:
        c.execute(f'''
            CREATE TRIGGER IF NOT EXISTS tr_insert_{t}
            AFTER INSERT ON {t}
            BEGIN
                UPDATE {t} SET 
                    last_modified = datetime('now'),
                    origem_registo = COALESCE(new.origem_registo, '{origem_padrao}')
                WHERE id = new.id;
            END;
        ''')
        c.execute(f'''
            CREATE TRIGGER IF NOT EXISTS tr_update_{t}
            AFTER UPDATE ON {t}
            FOR EACH ROW
            WHEN new.last_modified IS NULL OR new.last_modified = old.last_modified OR new.last_modified = '2026-06-24T00:00:00'
            BEGIN
                UPDATE {t} SET last_modified = datetime('now') WHERE id = old.id;
            END;
        ''')

def init_db():
    if is_cloud_mode():
        init_pg_db()
        return
    check_and_auto_migrate()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, perfil TEXT, nome_completo TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS setores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS funcionarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, cargo TEXT, setor_id INTEGER, FOREIGN KEY (setor_id) REFERENCES setores(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS movimentos (id INTEGER PRIMARY KEY AUTOINCREMENT, guia TEXT UNIQUE, tipo TEXT, equipamento TEXT, origem_destino TEXT, motivo TEXT, data TEXT, status TEXT, tecnico TEXT, relatorio TEXT, funcionario_id INTEGER, numero_serie TEXT, marca TEXT, entregue_por TEXT, recebido_por TEXT, agente_protecao TEXT, fornecedor TEXT, quantidade TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS marcas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tipos_equipamento (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS motivos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS fornecedores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS instituicoes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventario_local (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipamento TEXT,
        marca TEXT,
        numero_serie TEXT,
        quantidade INTEGER DEFAULT 1,
        status TEXT DEFAULT 'Disponível',
        data_registo TEXT,
        observacoes TEXT,
        codigo_barras TEXT,
        documento_pdf TEXT,
        provincia_id INTEGER,
        local_uso TEXT,
        estado TEXT,
        guia_origem TEXT,
        setor_id TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS equipamento_rastreio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guia TEXT,
        equipamento TEXT,
        marca TEXT,
        numero_serie TEXT,
        estado TEXT,
        local_atual TEXT,
        observacoes TEXT,
        data TEXT,
        utilizador TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS equipamento_estado_historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guia TEXT,
        equipamento TEXT,
        numero_serie TEXT,
        estado TEXT,
        observacoes TEXT,
        data TEXT,
        utilizador TEXT
    )''')
    check_db_integrity(c)
    
    try: c.execute("ALTER TABLE users ADD COLUMN nome_completo TEXT")
    except: pass
    
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        for u, p, perf in [("admin", "admin123", "admin"), ("tecnico", "tecnico123", "tecnico"), ("protecao", "protecao123", "protecao")]:
            c.execute("INSERT INTO users (username, password, perfil, nome_completo) VALUES (?,?,?,?)", (u, generate_password_hash(p), perf, u))
            
    # Populate default lookup values if empty
    c.execute("SELECT COUNT(*) FROM motivos")
    if c.fetchone()[0] == 0:
        for m in ['Alocação', 'Transferência', 'Reparação', 'Avaria', 'Substituição', 'Outro']:
            c.execute('INSERT OR IGNORE INTO motivos (nome) VALUES (?)', (m,))
            
    c.execute("SELECT COUNT(*) FROM fornecedores")
    if c.fetchone()[0] == 0:
        for f in ['N/A', 'NCR', 'Sistec']:
            c.execute('INSERT OR IGNORE INTO fornecedores (nome) VALUES (?)', (f,))
            
    c.execute("SELECT COUNT(*) FROM tipos_equipamento")
    if c.fetchone()[0] == 0:
        for t in ['Desktop', 'Laptop', 'Monitor', 'Impressora', 'Mesa', 'Cadeira', 'Scanner', 'Outro']:
            c.execute('INSERT OR IGNORE INTO tipos_equipamento (nome) VALUES (?)', (t,))
            
    c.execute("SELECT COUNT(*) FROM marcas")
    if c.fetchone()[0] == 0:
        for mc in ['HP', 'Dell', 'Lenovo', 'Epson', 'Canon', 'Brother', 'Apple', 'Outra']:
            c.execute('INSERT OR IGNORE INTO marcas (nome) VALUES (?)', (mc,))
            
    create_triggers(c)
    conn.commit()
    conn.close()
    
    threading.Thread(target=run_startup_sync).start()

COMMON_HEAD = '''
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20100%20100'%3E%3Ctext%20y='.9em'%20font-size='90'%3E%F0%9F%93%A6%3C/text%3E%3C/svg%3E">
    <style>
        :root { --primary: #1e293b; --accent: #10b981; --bg: #f8fafc; --border: #e2e8f0; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: #1e293b; }
        .nav { background: var(--primary); color: white; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
        .container { max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }
        .card { background: white; border-radius: 1rem; padding: 1.5rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid var(--border); margin-bottom: 2rem; }
        .btn { padding: 0.6rem 1.2rem; border-radius: 0.5rem; border: none; cursor: pointer; font-weight: 600; text-decoration: none; transition: all 0.2s; }
        .btn-green { background: var(--accent); color: white; }
        .btn-blue { background: #3b82f6; color: white; }
        .btn-outline { background: white; border: 1px solid var(--border); color: #64748b; }
        .btn-danger { background: #ef4444; color: white; }
        table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
        th { text-align: left; background: #f8fafc; padding: 1rem; border-bottom: 2px solid #f1f5f9; font-size: 0.75rem; text-transform: uppercase; color: #64748b; }
        td { padding: 1rem; border-bottom: 1px solid #f1f5f9; font-size: 0.9rem; }
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
        input, select, textarea { width: 100%; padding: 0.75rem; border: 1px solid var(--border); border-radius: 0.5rem; margin-top: 0.5rem; }
        .hidden { display: none; }
    </style>
    <script>
        function syncManual() {
            if(!confirm("Deseja forçar a sincronização com a Nuvem agora?")) return;
            fetch('/api/sync', {method: 'POST'})
            .then(res => res.json())
            .then(data => {
                if(data.success) {
                    alert("Sincronização concluída com sucesso!");
                    window.location.reload();
                } else {
                    alert("Erro na sincronização: " + data.error);
                }
            })
            .catch(e => alert("Erro ao contactar servidor de sincronização."));
        }
    </script>
'''

LOGIN_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>Login - STAE</title></head>
<body style="display:flex; justify-content:center; align-items:center; height:100vh; background:#f1f5f9">
    <div class="card" style="width:100%; max-width:400px; text-align:center">
        <h2>STAE - GESTÃO DE EQUIPAMENTOS</h2>
        <p style="color:#64748b; margin-bottom:2rem">Faça login para continuar</p>
        {% if error %}<div style="color:#ef4444; margin-bottom:1rem">{{error}}</div>{% endif %}
        <form method="POST" action="/login">
            <input type="text" name="username" placeholder="Usuário" required style="text-align:center">
            <input type="password" name="password" placeholder="Palavra-passe" required style="text-align:center">
            <button type="submit" class="btn btn-blue" style="width:100%; margin-top:1rem">Entrar</button>
        </form>
    </div>
</body></html>'''

RELATORIOS_TEMPLATE = """<!DOCTYPE html><html lang="pt"><head>""" + COMMON_HEAD + """<title>Dashboard STAE - Relatórios</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
    .tabs { display:flex; gap:0.5rem; margin-bottom:1.5rem; flex-wrap:wrap; }
    .tab { padding:0.6rem 1.2rem; border-radius:0.5rem; border:1px solid var(--border); cursor:pointer; background:white; color:#475569; font-weight:600; text-decoration:none; }
    .tab.active { background:#3b82f6; color:white; border-color:#3b82f6; }
    .toolbar { display:flex; gap:0.75rem; flex-wrap:wrap; align-items:flex-end; margin-bottom:1.5rem; }
    .toolbar > div { flex:1; min-width:140px; }
    .toolbar label { font-size:0.75rem; color:#64748b; font-weight:600; }
    .table-wrap { overflow-x:auto; }
    .table-wrap table td, .table-wrap table th { white-space:nowrap; }
</style>
</head>
<body>
    <div class="nav">
        <strong>STAE RELATÓRIOS E ESTATÍSTICAS</strong>
        <div style="display:flex; align-items:center; gap:1rem;">
            <button onclick="syncManual()" class="btn btn-outline" style="background:transparent; color:white; border:1px solid rgba(255,255,255,0.3); padding:0.3rem 0.6rem; font-size:0.8rem">🔄 Sincronizar</button>
            <a href="/" class="btn btn-outline" style="background:white; color:#0f172a;">⬅️ Voltar ao Início</a>
            <a href="/relatorios/export/excel?tab={{ tab }}&setor_id={{ setor_ids|join(',') }}&marca={{ marcas_list|join(',') }}&tipo_equipamento={{ tipos_eq_list|join(',') }}&status={{ status_list|join(',') }}&mov_tipo={{ mov_tipo|join(',') }}&data_inicio={{ data_inicio }}&data_fim={{ data_fim }}" class="btn btn-green">📊 Exportar Excel</a>
            <a href="/relatorios/export/pdf?tab={{ tab }}&setor_id={{ setor_ids|join(',') }}&marca={{ marcas_list|join(',') }}&tipo_equipamento={{ tipos_eq_list|join(',') }}&status={{ status_list|join(',') }}&mov_tipo={{ mov_tipo|join(',') }}&data_inicio={{ data_inicio }}&data_fim={{ data_fim }}" class="btn btn-blue">📄 Exportar PDF</a>
        </div>
    </div>
    <div class="container">
        <div class="card" style="margin-top:1rem">
            <h3 style="margin-bottom:1rem">Relatório de Dados</h3>
            <div class="tabs">
                <a href="/relatorios?tab=inventario" class="tab {% if tab == 'inventario' %}active{% endif %}">📦 Inventário</a>
                <a href="/relatorios?tab=entradas_saidas" class="tab {% if tab == 'entradas_saidas' %}active{% endif %}">↔️ Entradas / Saídas</a>
                <a href="/relatorios?tab=movimentos" class="tab {% if tab == 'movimentos' %}active{% endif %}">🚚 Movimentos</a>
            </div>
            <form method="GET" action="/relatorios" class="toolbar">
                <input type="hidden" name="tab" value="{{ tab }}">
                <div>
                    <label>Setor (Ctrl+clique p/ vários)</label>
                    <select name="setor_id" multiple size="3" style="margin-top:0.2rem;">
                        {% for s in setores %}<option value="{{ s.id }}" {% if s.id|string in setor_ids %}selected{% endif %}>{{ s.nome }}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label>Marca (Ctrl+clique p/ vários)</label>
                    <select name="marca" multiple size="3" style="margin-top:0.2rem;">
                        {% for m in marcas %}<option value="{{ m.nome }}" {% if m.nome in marcas_list %}selected{% endif %}>{{ m.nome }}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label>Tipo de Equipamento (Ctrl+clique p/ vários)</label>
                    <select name="tipo_equipamento" multiple size="3" style="margin-top:0.2rem;">
                        {% for t in tipos_eq %}<option value="{{ t.nome }}" {% if t.nome in tipos_eq_list %}selected{% endif %}>{{ t.nome }}</option>{% endfor %}
                    </select>
                </div>
                {% if tab in ('entradas_saidas', 'movimentos') %}
                <div>
                    <label>De</label>
                    <input type="date" name="data_inicio" value="{{ data_inicio }}" style="margin-top:0.2rem;">
                </div>
                <div>
                    <label>Até</label>
                    <input type="date" name="data_fim" value="{{ data_fim }}" style="margin-top:0.2rem;">
                </div>
                {% endif %}
                {% if tab == 'inventario' or tab == 'movimentos' %}
                <div>
                    <label>Status/Estado (Ctrl+clique p/ vários)</label>
                    <select name="status" multiple size="3" style="margin-top:0.2rem;">
                        <option value="Disponível" {% if 'Disponível' in status_list %}selected{% endif %}>Disponível</option>
                        <option value="Indisponível" {% if 'Indisponível' in status_list %}selected{% endif %}>Indisponível</option>
                        <option value="Pendente" {% if 'Pendente' in status_list %}selected{% endif %}>Pendente</option>
                        <option value="Em estoque" {% if 'Em estoque' in status_list %}selected{% endif %}>Em estoque</option>
                        <option value="Entregue" {% if 'Entregue' in status_list %}selected{% endif %}>Entregue</option>
                    </select>
                </div>
                {% endif %}
                {% if tab == 'movimentos' %}
                <div>
                    <label>Tipo de Movimento (Ctrl+clique p/ vários)</label>
                    <select name="mov_tipo" multiple size="3" style="margin-top:0.2rem;">
                        <option value="ENTRADA" {% if 'ENTRADA' in mov_tipo %}selected{% endif %}>Entrada</option>
                        <option value="SAIDA" {% if 'SAIDA' in mov_tipo %}selected{% endif %}>Saída</option>
                        <option value="TRANSFERENCIA" {% if 'TRANSFERENCIA' in mov_tipo %}selected{% endif %}>Transferência</option>
                    </select>
                </div>
                {% endif %}
                <div style="flex:0 0 auto;">
                    <button type="submit" class="btn btn-blue">Filtrar</button>
                </div>
            </form>
            <div class="table-wrap">
                <table>
                    <thead>
                        {% if tab == 'inventario' %}
                        <tr>
                            <th>ID</th><th>Equipamento</th><th>Marca</th><th>Nº Série</th><th>Qtd</th><th>Estado</th><th>Data Registo</th><th>Setor</th><th>Observações</th>
                        </tr>
                        {% else %}
                        <tr>
                            <th>Guia</th><th>Tipo</th><th>Equipamento</th><th>Marca</th><th>Nº Série</th><th>Origem/Destino</th><th>Qtd</th><th>Data</th><th>Status</th><th>Técnico</th><th>Motivo</th>
                        </tr>
                        {% endif %}
                    </thead>
                    <tbody>
                        {% for it in items %}
                        {% if tab == 'inventario' %}
                        <tr>
                            <td>{{ it.id }}</td>
                            <td>{{ it.equipamento }}</td>
                            <td>{{ it.marca }}</td>
                            <td>{{ it.numero_serie }}</td>
                            <td>{{ it.quantidade }}</td>
                            <td>{{ it.status }}</td>
                            <td>{{ it.data_registo }}</td>
                            <td>{{ it.setor_nome or '-' }}</td>
                            <td>{{ it.observacoes or '-' }}</td>
                        </tr>
                        {% else %}
                        <tr>
                            <td>{{ it.guia }}</td>
                            <td>{{ it.tipo }}</td>
                            <td>{{ it.equipamento }}</td>
                            <td>{{ it.marca }}</td>
                            <td>{{ it.numero_serie }}</td>
                            <td>{{ it.origem_destino }}</td>
                            <td>{{ it.quantidade }}</td>
                            <td>{{ it.data }}</td>
                            <td>{{ it.status }}</td>
                            <td>{{ it.tecnico }}</td>
                            <td>{{ it.motivo }}</td>
                        </tr>
                        {% endif %}
                        {% else %}
                        <tr><td colspan="11" style="text-align:center; color:#64748b;">Nenhum registo encontrado com os filtros seleccionados.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div style="margin-top:2rem; display:grid; grid-template-columns:1fr 1fr; gap:2rem;">
            <div class="card">
                <h3 style="text-align:center">Movimentos por Tipo de Equipamento</h3>
                <canvas id="chartEquip"></canvas>
            </div>
            <div class="card">
                <h3 style="text-align:center">Entradas por Setor/Origem</h3>
                <canvas id="chartSetor"></canvas>
            </div>
        </div>
        <div class="card" style="margin-top:2rem">
            <h3 style="text-align:center">Resumo de Movimentos por Marca</h3>
            <canvas id="chartMarca"></canvas>
        </div>
    </div>
    <script>
        const dataEquip = {{ stat_equip | safe }};
        new Chart(document.getElementById('chartEquip'), {
            type: 'bar',
            data: {
                labels: dataEquip.map(d => d.equipamento),
                datasets: [
                    {label: 'Entradas', data: dataEquip.map(d => d.entradas), backgroundColor: '#10b981'},
                    {label: 'Saídas', data: dataEquip.map(d => d.saidas), backgroundColor: '#3b82f6'}
                ]
            }
        });

        const dataSetor = {{ stat_setor | safe }};
        new Chart(document.getElementById('chartSetor'), {
            type: 'doughnut',
            data: {
                labels: dataSetor.map(d => d.origem),
                datasets: [{
                    data: dataSetor.map(d => d.total),
                    backgroundColor: ['#f43f5e', '#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#64748b']
                }]
            }
        });

        const dataMarca = {{ stat_marca | safe }};
        new Chart(document.getElementById('chartMarca'), {
            type: 'bar',
            data: {
                labels: dataMarca.map(d => d.marca),
                datasets: [
                    {label: 'Entradas', data: dataMarca.map(d => d.entradas), backgroundColor: '#10b981'},
                    {label: 'Saídas', data: dataMarca.map(d => d.saidas), backgroundColor: '#3b82f6'}
                ]
            }
        });
    </script>
</body></html>"""

MAIN_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>STAE Gestão</title></head>
<body>
    <div class="nav">
        <strong>STAE GESTÃO</strong>
        <div style="display:flex; align-items:center; gap:1rem;"><button onclick="syncManual()" class="btn btn-outline" style="background:transparent; color:white; border:1px solid rgba(255,255,255,0.3); padding:0.3rem 0.6rem; font-size:0.8rem">🔄 Sincronizar</button> <span>👤 {{session.nome}} ({{session.perfil}})</span> | <a href="/logout" style="color:white">Sair</a></div>
    </div>
    <div class="container">
        {% if msg %}<div style="background:#dcfce3; color:#166534; padding:1rem; border-radius:0.5rem; margin-bottom:1rem;">{{msg}}</div>{% endif %}
        
        
        <!-- PENDENTES_BLOCK_ADDED -->
        {% if pendentes %}
        <div class="card" style="border: 2px solid #f59e0b; background: #fffbeb;">
            <h3 style="color:#d97706; margin-bottom:1rem;">⚠️ Equipamentos Pendentes de Receção ({{pendentes|length}})</h3>
            <table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
                <tr style="background:#fef3c7; text-align:left; color:#b45309;">
                    <th style="padding:0.5rem">GUIA</th>
                    <th style="padding:0.5rem">EQUIPAMENTO</th>
                    <th style="padding:0.5rem">ORIGEM</th>
                    <th style="padding:0.5rem">QTD</th>
                    <th style="padding:0.5rem">AÇÃO</th>
                </tr>
                {% for p in pendentes %}
                <tr style="border-bottom:1px solid #fde68a;">
                    <td style="padding:0.5rem"><strong>{{p.guia}}</strong></td>
                    <td style="padding:0.5rem">{{p.equipamento}} ({{p.marca}}) S/N: {{p.numero_serie}}</td>
                    <td style="padding:0.5rem">{{p.origem_destino}}</td>
                    <td style="padding:0.5rem">{{p.quantidade}}</td>
                    <td style="padding:0.5rem; display:flex; gap:0.5rem;">
                        <form method="POST" action="/confirmar_recepcao/{{p.guia}}" style="display:inline;"><button class="btn btn-green" style="padding:0.3rem 0.6rem; font-size:0.8rem">✅ Confirmar</button></form>
                        <form method="POST" action="/rejeitar_recepcao/{{p.guia}}" style="display:inline;"><button class="btn btn-danger" style="padding:0.3rem 0.6rem; font-size:0.8rem">❌ Rejeitar</button></form>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
        {% endif %}
    <div style="display:flex; gap:1rem; margin-bottom:2rem; justify-content:center; flex-wrap:wrap">
            <button onclick="show('ent')" class="btn btn-green">📥 Entrada</button>
            <button onclick="show('sai')" class="btn btn-blue">📤 Saída</button>
            <a href="/inventario" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a">📦 Inventário</a>
            <a href="/movimentos" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a">📋 Todos os Movimentos</a>
            <button onclick="abrirBuscaBarcode()" class="btn btn-outline" style="background:#f1f5f9; color:#0f172a">🔍 Buscar por Código de Barras</button>
            {% if session.perfil == 'admin' %}
            <a href="/relatorios" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a"> 📊 Dashboard de Relatórios</a>
            <a href="/cadastros" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a"> ⚙️ Configurações</a>
            <a href="/eleitoral" class="btn btn-outline" style="background:#0369a1; color:white; font-weight:bold"> 🗳️ Gestão Eleitoral</a>
            {% endif %}
            <button id="syncBtn" onclick="syncCloud()" class="btn btn-outline" style="margin-left:auto; font-weight:bold; background:#10b981; color:white; border:none; cursor:pointer; display:flex; align-items:center; gap:0.5rem; padding:0.5rem 1rem; border-radius:0.5rem; transition: all 0.3s;">
                🔄 Sincronizar Nuvem
            </button>
            <button onclick="showReparacaoModal()" class="btn btn-outline" style="font-weight:bold; background:white; border:1px solid #cbd5e1; color:#1e293b; cursor:pointer; display:flex; align-items:center; gap:0.5rem; padding:0.5rem 1rem; border-radius:0.5rem;">
                🔧 EM REPARAÇÃO: {{ em_reparacao }}
            </button>
        </div>

        <div id="ent" class="card hidden">
            <h3>Nova Entrada</h3>
            <div style="background:#f0f9ff; border:1px solid #bae6fd; border-radius:0.5rem; padding:0.8rem 1rem; margin-bottom:1rem; display:flex; align-items:center; gap:0.8rem;">
                <input type="checkbox" id="modo_inventario" name="modo_inventario" value="1" onchange="toggleModoInventario()" style="width:18px; height:18px; cursor:pointer;">
                <label for="modo_inventario" style="cursor:pointer; font-weight:600; color:#0369a1; margin:0;">📦 Modo Inventário</label>
                <span style="font-size:0.82rem; color:#64748b;">Ative para registar material directamente no inventário de um local (sem origem obrigatória)</span>
            </div>
            <form method="POST" action="/registrar_entrada" enctype="multipart/form-data">
                <input type="hidden" name="modo_inventario" id="modo_inventario_hidden" value="">
                <div id="inv_destino_row" style="display:none; background:#f0fdf4; border:1px solid #86efac; border-radius:0.5rem; padding:0.8rem 1rem; margin-bottom:1rem;">
                    <label style="font-weight:600; color:#166534;">📍 Local de Destino (Inventário) *</label>
                    <select name="destino_inventario" id="destino_inventario" style="margin-top:0.4rem; width:100%; padding:0.5rem;">
                        <option value="">-- Selecione o local onde o material será registado --</option>
                        {% for s in setores %}<option value="{{s.id}}" {% if s.id == session.setor_id %}selected{% endif %}>{{s.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div class="form-grid">
                    <div><label>Equipamento (Tipo)</label>
                        <select name="equipamento" required>
                            <option value="">-- Selecione --</option>
                            {% for t in tipos %}<option value="{{t.nome}}">{{t.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div><label>Marca</label>
                        <select name="marca" required>
                            <option value="">-- Selecione --</option>
                            {% for m in marcas %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div><label>S/N / Nº Série</label><input name="numero_serie" required placeholder="Ex: 1234 ou N/A"></div>
                    <div><label id="ent_origem_label">Origem</label>
                        <select name="origem" id="ent_origem_select">
                            <option value="">-- Selecione --</option>
                            <optgroup label="Setores Internos">
                                {% for s in setores %}<option value="SETOR_{{s.id}}">{{s.nome}}</option>{% endfor %}
                            </optgroup>
                            <optgroup label="Instituições Externas">
                                {% for i in instituicoes %}<option value="Externo - {{i.nome}}">{{i.nome}}</option>{% endfor %}
                            </optgroup>
                        </select>
                    </div>
                    <div><label>Fornecedor</label>
                        <select name="fornecedor" required>
                            <option value="N/A">N/A</option>
                            {% for f in fornecedores %}
                                {% if f.nome != 'N/A' %}<option value="{{f.nome}}">{{f.nome}}</option>{% endif %}
                            {% endfor %}
                        </select>
                    </div>
                    <div><label>Quantidade</label><input name="quantidade" type="number" min="1" value="1" required></div>
                    <div>
                        <label>Código de Barras (opcional - scan)</label>
                        <input name="codigo_barras" placeholder="Escanear ou digitar código de barras...">
                    </div>
                    <div>
                        <label>Documento do Equipamento (imagem → PDF)</label>
                        <input type="file" name="documento" accept=".jpg,.jpeg,.png,.bmp,.webp,.tif,.tiff,.pdf">
                    </div>
                    <div style="grid-column: span 2;">
                        <label>Motivo</label>
                        <select name="motivo" required>
                            <option value="">-- Selecione --</option>
                            {% for m in motivos %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div style="grid-column: span 2; display:flex; gap:1rem;">
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Entregue por (Funcionário)</label>
                            <select name="entregue_por" id="ent_entregue" required></select>
                        </div>
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Recebido por (Funcionário)</label>
                            <select name="recebido_por" id="ent_recebido" required></select>
                        </div>
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Agente de Protecção</label>
                            <select name="agente_protecao" id="ent_protecao"></select>
                        </div>
                    </div>
                    <div style="grid-column: span 2;">
                        <label>Departamento Responsável (aparece na guia)</label>
                        <select name="departamento_responsavel_id" required>
                            {% for s in setores %}<option value="{{s.id}}" {% if s.id == session.setor_id %}selected{% endif %}>{{s.nome}}</option>{% endfor %}
                        </select>
                    </div>
                </div>
                <button type="submit" class="btn btn-green" style="margin-top:1.5rem; width:100%">CONFIRMAR ENTRADA</button>
            </form>
        </div>

        <div id="sai" class="card hidden">
            <h3>Nova Saída</h3>
            <form method="POST" action="/registrar_saida">
                <div style="background: #f8fafc; padding: 1rem; border-radius: 0.5rem; border: 1px dashed var(--border); margin-bottom: 1.5rem;">
                    <label style="font-weight: bold; color: #1e293b; display: block; margin-bottom: 0.5rem;">📦 Retirar do Inventário Local (Opcional)</label>
                    <select id="sai_selecao_inventario" onchange="preencherSaidaDoInventario(this.value)" style="margin-top: 0;">
                        <option value="">-- Escolha um item do inventário para preenchimento automático --</option>
                        {% for item in inv_items %}
                        <option value='{{ item|tojson }}'>{{ item.equipamento }} {{ item.marca }} (S/N: {{ item.numero_serie }}) [Disponível: {{ item.quantidade }}]</option>
                        {% endfor %}
                    </select>
                    <input type="hidden" name="inventario_id" id="sai_inventario_id" value="">
                </div>
                <div class="form-grid">
                    <div><label>Equipamento (Tipo)</label>
                        <select name="equipamento" required>
                            <option value="">-- Selecione --</option>
                            {% for t in tipos %}<option value="{{t.nome}}">{{t.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div><label>Marca</label>
                        <select name="marca" required>
                            <option value="">-- Selecione --</option>
                            {% for m in marcas %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div><label>S/N / Nº Série</label><input name="numero_serie" required placeholder="Ex: 1234 ou N/A"></div>
                    {% if session.perfil == 'admin' %}
                    <div><label>Origem (Local)</label>
                        <select name="origem" required>
                            <option value="">-- Selecione o local de origem --</option>
                            {% for s in setores %}<option value="SETOR_{{s.id}}">{{s.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    {% else %}
                    <div><label>Origem (Local)</label>
                        <input type="text" value="{{ meu_setor_nome or 'DDGEI' }}" readonly style="background:#f1f5f9; color:#475569;">
                        <input type="hidden" name="origem" value="SETOR_{{ meu_setor_id or 3 }}">
                    </div>
                    {% endif %}
                    <div><label>Destino</label>
                        <select name="destino" required>
                            <option value="">-- Selecione --</option>
                            <optgroup label="Setores Internos">
                                {% for s in setores %}<option value="SETOR_{{s.id}}">{{s.nome}}</option>{% endfor %}
                            </optgroup>
                            <optgroup label="Instituições Externas">
                                {% for i in instituicoes %}<option value="Externo - {{i.nome}}">{{i.nome}}</option>{% endfor %}
                            </optgroup>
                        </select>
                    </div>
                    <div><label>Estado de Saída</label>
                        <select name="estado_saida" required>
                            <option value="EM_PREPARACAO">Em preparação</option>
                            <option value="EMPACOTAMENTO">Empacotamento</option>
                            <option value="A_ESPERA_ENVIO">À espera de envio</option>
                            <option value="ENVIADO">Enviado</option>
                            <option value="RECEBIDO">Recebido</option>
                        </select>
                    </div>
                    <div><label>Fornecedor</label>
                        <select name="fornecedor" required>
                            <option value="N/A">N/A</option>
                            {% for f in fornecedores %}
                                {% if f.nome != 'N/A' %}<option value="{{f.nome}}">{{f.nome}}</option>{% endif %}
                            {% endfor %}
                        </select>
                    </div>
                    <div><label>Quantidade</label><input name="quantidade" type="number" min="1" value="1" required></div>
                    <div style="grid-column: span 2;">
                        <label>Motivo</label>
                        <select name="motivo" required>
                            <option value="">-- Selecione --</option>
                            {% for m in motivos %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div style="grid-column: span 2; display:flex; gap:1rem;">
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Entregue por (Funcionário)</label>
                            <select name="entregue_por" id="sai_entregue" required></select>
                        </div>
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Recebido por (Funcionário)</label>
                            <select name="recebido_por" id="sai_recebido" required></select>
                        </div>
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Agente de Protecção</label>
                            <select name="agente_protecao" id="sai_protecao"></select>
                        </div>
                    </div>
                    <div style="grid-column: span 2;">
                        <label>Departamento Responsável (aparece na guia)</label>
                        <select name="departamento_responsavel_id" required>
                            {% for s in setores %}<option value="{{s.id}}" {% if s.id == session.setor_id %}selected{% endif %}>{{s.nome}}</option>{% endfor %}
                        </select>
                    </div>
                </div>
                <button type="submit" class="btn btn-blue" style="margin-top:1.5rem; width:100%">GERAR GUIA</button>
            </form>
        </div>

        <div class="card">
            <h3>Histórico Recente</h3>
            <input type="text" id="searchInput" onkeyup="searchTable()" placeholder="Pesquisar guia, equipamento, origem..." style="width:100%; padding:0.8rem; margin-top:1rem; border:1px solid #cbd5e1; border-radius:4px; margin-bottom:1rem">
            <table id="mainTable" style="width:100%; border-collapse:collapse; margin-top:1rem; font-size:0.9rem">
                <tr style="background:#f1f5f9; text-align:left; color:#64748b; font-size:0.8rem">
                    <th style="padding:1rem">GUIA</th><th style="padding:1rem">EQUIPAMENTO</th>
                    <th style="padding:1rem">S/N</th><th style="padding:1rem">ORIGEM</th><th style="padding:1rem">DESTINO</th>
                    <th style="padding:1rem">ESTADO</th><th style="padding:1rem">DATA</th><th style="padding:1rem">ACÇÕES</th>
                </tr>
                {% for m in movimentos %}
                <tr style="border-bottom:1px solid var(--border)">
                    <td style="padding:1rem"><strong>{{m.guia[:8]}}</strong><br>{{m.guia[8:]}}</td>
                    <td style="padding:1rem">{{m.equipamento}}<br><small style="color:#64748b">({{m.marca}})</small></td>
                    <td style="padding:1rem">{{m.numero_serie}}</td>
                    <td style="padding:1rem">{% if m.tipo == 'ENTRADA' %}{{ m.origem_destino or m.setor_origem_nome or 'Inventário Directo' }}{% else %}{{ m.setor_origem_nome or m.local_origem or m.origem_destino or '-' }}{% endif %}</td>
                    <td style="padding:1rem">{% if m.tipo == 'SAIDA' %}{{ m.origem_destino or m.setor_destino_nome or m.local_destino or '-' }}{% else %}{{ m.setor_destino_nome or m.local_destino or 'Inventário Directo' }}{% endif %}</td>
                    <td style="padding:1rem">{{ (m.estado_rastreio or m.status or '').replace('_',' ') }}</td>
                    <td style="padding:1rem">{{m.data[:10]}}<br><small style="color:#64748b">{{m.data[11:]}}</small></td>
                    <td style="padding:1rem">
                        <button onclick="toggleDetails('det_{{loop.index}}')" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-right:0.3rem;">Detalhes</button>
                        <button onclick="mudarEstadoMov('{{m.guia}}','{{m.estado_rastreio or m.status or ''}}')" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-right:0.3rem;">Estado</button>
                        <a href="/ver_guia/{{m.guia}}" target="_blank" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-right:0.3rem">PDF</a>
                        {% if m.tipo == 'ENTRADA' and m.status and 'repara' in m.status|lower %}
                        <button onclick="abrirSaidaReparacao('{{m.guia}}')" class="btn btn-green" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-right:0.3rem">Saída</button>
                        {% endif %}
                        <a href="/edit_movimento_form/{{m.guia}}" class="btn btn-blue" style="padding:0.3rem 0.6rem; font-size:0.8rem">Editar</a>
                    </td>
                </tr>
                <tr id="det_{{loop.index}}" class="hidden" style="background:#f8fafc;">
                    <td colspan="7" style="padding:1rem; border-bottom:1px solid var(--border)">
                        <div style="display:flex; gap:2rem; font-size:0.85rem; color:#475569; flex-wrap:wrap">
                            <div><strong>Motivo:</strong> {{m.motivo or '-'}}</div>
                            <div><strong>Técnico do Sistema:</strong> {{m.tecnico or '-'}}</div>
                            <div><strong>Fornecedor:</strong> {{m.fornecedor or '-'}}</div>
                            <div><strong>Quantidade:</strong> {{m.quantidade or '-'}}</div>
                            <div><strong>Entregue Por:</strong> {{m.entregue_nome or '-'}}</div>
                            <div><strong>Recebido Por:</strong> {{m.recebido_nome or '-'}}</div>
                            <div><strong>Agente de Protecção:</strong> {{m.protecao_nome or '-'}}</div>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
    <script>
        function preencherSaidaDoInventario(jsonStr) {
            if (!jsonStr) {
                document.getElementById('sai_inventario_id').value = '';
                return;
            }
            const item = JSON.parse(jsonStr);
            document.getElementById('sai_inventario_id').value = item.id;
            
            const fSai = document.getElementById('sai');
            const selEquip = fSai.querySelector('select[name="equipamento"]');
            const selMarca = fSai.querySelector('select[name="marca"]');
            const inpSN = fSai.querySelector('input[name="numero_serie"]');
            const inpQtd = fSai.querySelector('input[name="quantidade"]');
            
            let hasEquip = false;
            for(let i=0; i<selEquip.options.length; i++) {
                if(selEquip.options[i].value === item.equipamento) {
                    selEquip.selectedIndex = i;
                    hasEquip = true;
                    break;
                }
            }
            if(!hasEquip) {
                const opt = new Option(item.equipamento, item.equipamento);
                selEquip.add(opt);
                selEquip.value = item.equipamento;
            }
            
            let hasMarca = false;
            for(let i=0; i<selMarca.options.length; i++) {
                if(selMarca.options[i].value === item.marca) {
                    selMarca.selectedIndex = i;
                    hasMarca = true;
                    break;
                }
            }
            if(!hasMarca) {
                const opt = new Option(item.marca, item.marca);
                selMarca.add(opt);
                selMarca.value = item.marca;
            }
            
            inpSN.value = item.numero_serie;
            inpQtd.max = item.quantidade;
            inpQtd.value = 1;
        }

        function syncCloud() {
            const btn = document.getElementById('syncBtn');
            const originalText = btn.innerHTML;
            btn.innerHTML = '🔄 Sincronizando...';
            btn.disabled = true;
            btn.style.background = '#64748b';
            
            fetch('/api/sync', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        btn.innerHTML = '✅ Sincronizado!';
                        btn.style.background = '#10b981';
                        alert('Sincronização com a nuvem concluída com sucesso!');
                        window.location.reload();
                    } else {
                        btn.innerHTML = '❌ Erro';
                        btn.style.background = '#ef4444';
                        alert('Erro ao sincronizar com a nuvem: ' + (data.error || 'Conexão falhou'));
                        setTimeout(() => {
                            btn.innerHTML = originalText;
                            btn.disabled = false;
                            btn.style.background = '#10b981';
                        }, 3000);
                    }
                })
                .catch(err => {
                    btn.innerHTML = '❌ Erro';
                    btn.style.background = '#ef4444';
                    alert('Erro de rede ao tentar conectar com a nuvem.');
                    setTimeout(() => {
                        btn.innerHTML = originalText;
                        btn.disabled = false;
                        btn.style.background = '#10b981';
                    }, 3000);
                });
        }

        function show(id){
            document.getElementById('ent').classList.add('hidden');
            document.getElementById('sai').classList.add('hidden');
            document.getElementById(id).classList.remove('hidden');
            if(id === 'sai' || id === 'ent') loadFuncs(id);
        }
        function loadFuncs(type){
            const pfx = type === 'ent' ? 'ent' : 'sai';
            const selE = document.getElementById(pfx + '_entregue');
            const selR = document.getElementById(pfx + '_recebido');
            const selP = document.getElementById(pfx + '_protecao');
            
            selE.innerHTML = '<option value="">-- Selecione quem entregou --</option>';
            selR.innerHTML = '<option value="">-- Selecione quem recebeu --</option>';
            selP.innerHTML = '<option value="">-- Opcional --</option>';
            
            fetch('/api/funcionarios').then(r=>r.json()).then(data=>{
                data.forEach(f => {
                    const opt = `<option value="${f.id}">${f.nome} (${f.setor})</option>`;
                    selE.innerHTML += opt;
                    selR.innerHTML += opt;
                });
            });
            
            fetch('/api/usuarios_protecao').then(r=>r.json()).then(data=>{
                data.forEach(u => {
                    const opt = `<option value="${u.nome}">${u.nome} (${u.info})</option>`;
                    selP.innerHTML += opt;
                });
            });
        }
        function toggleDetails(id){
            const el = document.getElementById(id);
            if(el.classList.contains('hidden')) el.classList.remove('hidden');
            else el.classList.add('hidden');
        }
        function searchTable() {
            var input, filter, table, tr, td, i, txtValue;
            input = document.getElementById("searchInput");
            filter = input.value.toUpperCase();
            table = document.getElementById("mainTable");
            tr = table.getElementsByTagName("tr");
            for (i = 1; i < tr.length; i+=2) {
                if(tr[i].className.includes("hidden")) continue;
                td = tr[i].innerText;
                if (td) {
                    if (td.toUpperCase().indexOf(filter) > -1) {
                        tr[i].style.display = "";
                    } else {
                        tr[i].style.display = "none";
                        if(tr[i+1]) tr[i+1].classList.add("hidden");
                    }
                }
            }
        }
        function toggleModoInventario() {
            const on = document.getElementById('modo_inventario').checked;
            document.getElementById('modo_inventario_hidden').value = on ? '1' : '';
            const destRow = document.getElementById('inv_destino_row');
            const origemSel = document.getElementById('ent_origem_select');
            const origemLabel = document.getElementById('ent_origem_label');
            if (on) {
                destRow.style.display = 'block';
                origemSel.removeAttribute('required');
                origemLabel.innerHTML = 'Origem <small style="color:#94a3b8">(opcional em inventário)</small>';
            } else {
                destRow.style.display = 'none';
                document.getElementById('destino_inventario').value = '';
                origemSel.setAttribute('required', 'required');
                origemLabel.innerHTML = 'Origem';
            }
        }
        function showReparacaoModal() {
            document.getElementById('reparacaoModal').style.display = 'flex';
            loadReparacoes();
        }
        function closeReparacaoModal() {
            document.getElementById('reparacaoModal').style.display = 'none';
            window.location.reload();
        }
        function loadReparacoes() {
            const tbody = document.getElementById('reparacaoTableBody');
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:2rem;">Carregando...</td></tr>';
            fetch('/api/equipamentos_reparacao')
                .then(r => r.json())
                .then(data => {
                    if(data.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:2rem; color:#64748b;">Nenhum equipamento em reparação no momento.</td></tr>';
                        return;
                    }
                    tbody.innerHTML = '';
                    data.forEach(item => {
                        const tr = document.createElement('tr');
                        tr.style.borderBottom = '1px solid var(--border)';
                        tr.innerHTML = `
                            <td style="padding:0.75rem"><strong>${item.guia}</strong></td>
                            <td style="padding:0.75rem">${item.equipamento}<br><small style="color:#64748b">${item.marca}</small></td>
                            <td style="padding:0.75rem">${item.numero_serie}</td>
                            <td style="padding:0.75rem">${item.origem_destino}</td>
                            <td style="padding:0.75rem"><span style="background:#fef3c7; color:#d97706; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">${item.status}</span></td>
                            <td style="padding:0.75rem; display:flex; gap:0.5rem; align-items:center;">
                                <select onchange="updateReparacaoStatus('${item.guia}', this.value)" style="padding:0.3rem 0.5rem; font-size:0.85rem; margin-top:0; flex:1;">
                                    <option value="Aguardando reparação" ${item.status==='Aguardando reparação'?'selected':''}>Aguardando reparação</option>
                                    <option value="Reparado e Entregue">Reparado e Entregue</option>
                                    <option value="Em estoque" ${item.status==='Em estoque'?'selected':''}>Em estoque</option>
                                    <option value="Entregue">Entregue</option>
                                </select>
                                <button onclick="document.getElementById('reparacaoModal').style.display = 'none'; abrirSaidaReparacao('${item.guia}', 'Reparado e Entregue')" class="btn btn-green" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-top:0;">Saída</button>
                            </td>
                        `;
                        tbody.appendChild(tr);
                    });
                });
        }
        function updateReparacaoStatus(guia, newStatus) {
            if (newStatus === 'Reparado e Entregue' || newStatus === 'Entregue') {
                document.getElementById('reparacaoModal').style.display = 'none';
                abrirSaidaReparacao(guia, newStatus);
            } else {
                fetch(`/api/update_status/${guia}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: newStatus })
                })
                .then(r => r.json())
                .then(res => {
                    if(res.success) {
                        loadReparacoes();
                    } else {
                        alert('Erro ao atualizar o status do equipamento.');
                    }
                });
            }
        }
        function abrirSaidaReparacao(guia, statusFinal) {
            document.getElementById('saidaReparacaoForm').action = `/registrar_saida_reparacao/${guia}`;
            document.getElementById('sr_guia_original').value = guia;
            
            if (statusFinal) {
                document.getElementById('sr_novo_status').value = statusFinal;
            } else {
                document.getElementById('sr_novo_status').value = 'Reparado e Entregue';
            }
            
            document.getElementById('saidaReparacaoModal').style.display = 'flex';
            
            const selE = document.getElementById('sr_entregue');
            const selR = document.getElementById('sr_recebido');
            const selP = document.getElementById('sr_protecao');
            
            selE.innerHTML = '<option value="">-- Selecione quem entregou --</option>';
            selR.innerHTML = '<option value="">-- Selecione quem recebeu --</option>';
            selP.innerHTML = '<option value="">-- Opcional --</option>';
            
            fetch('/api/funcionarios').then(r=>r.json()).then(data=>{
                data.forEach(f => {
                    const opt = `<option value="${f.id}">${f.nome} (${f.setor})</option>`;
                    selE.innerHTML += opt;
                    selR.innerHTML += opt;
                });
            });
            
            fetch('/api/usuarios_protecao').then(r=>r.json()).then(data=>{
                data.forEach(u => {
                    const opt = `<option value="${u.nome}">${u.nome} (${u.info})</option>`;
                    selP.innerHTML += opt;
                });
            });
            
            fetch(`/api/movimento_info/${guia}`)
                .then(r => r.json())
                .then(mov => {
                    document.getElementById('sr_destino').value = mov.origem_destino || '';
                    document.getElementById('sr_equipamento').value = mov.equipamento || '';
                    document.getElementById('sr_marca').value = mov.marca || '';
                    document.getElementById('sr_numero_serie').value = mov.numero_serie || '';
                    document.getElementById('sr_quantidade').value = mov.quantidade || '1';
                    document.getElementById('sr_motivo').value = mov.motivo || '';
                    document.getElementById('sr_fornecedor').value = mov.fornecedor || 'N/A';
                });
        }
        function fecharSaidaReparacao() {
            document.getElementById('saidaReparacaoModal').style.display = 'none';
            window.location.reload();
        }
        function mudarEstadoMov(guia, estadoAtual) {
            document.getElementById('me_guia').value = guia;
            document.getElementById('me_atual').value = estadoAtual;
            document.getElementById('me_estado').value = estadoAtual;
            document.getElementById('me_local').value = '';
            document.getElementById('me_obs').value = '';
            document.getElementById('movEstadoModal').style.display = 'flex';
        }
        function guardarEstadoMov(event) {
            event.preventDefault();
            const guia = document.getElementById('me_guia').value;
            const estado = document.getElementById('me_estado').value;
            const local = document.getElementById('me_local').value;
            const obs = document.getElementById('me_obs').value;
            fetch('/api/movimento/estado', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ guia: guia, estado: estado, local: local, obs: obs })
            })
            .then(r => r.json())
            .then(res => {
                if(res.success) {
                    document.getElementById('movEstadoModal').style.display = 'none';
                    window.location.reload();
                } else {
                    alert(res.error || 'Erro ao atualizar o estado do movimento.');
                }
            })
            .catch(() => alert('Erro de ligação. Tente novamente.'));
        }
    </script>
    <div id="reparacaoModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:800px; max-width:95%; max-height:90vh; overflow-y:auto; position:relative;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem;">
                <h2>🔧 Equipamentos em Reparação</h2>
                <button type="button" class="btn btn-outline" onclick="closeReparacaoModal()" style="padding:0.4rem 0.8rem;">Fechar</button>
            </div>
            <div id="reparacaoList">
                <table style="width:100%; border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f1f5f9; text-align:left; color:#64748b; font-size:0.8rem">
                            <th style="padding:0.75rem">GUIA</th>
                            <th style="padding:0.75rem">EQUIPAMENTO</th>
                            <th style="padding:0.75rem">S/N</th>
                            <th style="padding:0.75rem">ORIGEM</th>
                            <th style="padding:0.75rem">STATUS ATUAL</th>
                            <th style="padding:0.75rem">ALTERAR STATUS</th>
                        </tr>
                    </thead>
                    <tbody id="reparacaoTableBody">
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <!-- Modal de Saída de Equipamento sob Reparação -->
    <div id="saidaReparacaoModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1010; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:800px; max-width:95%; max-height:90vh; overflow-y:auto;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem;">
                <h2>📤 Registrar Saída (Reparação/Entrega)</h2>
                <button type="button" class="btn btn-outline" onclick="fecharSaidaReparacao()" style="padding:0.4rem 0.8rem;">Fechar</button>
            </div>
            <form id="saidaReparacaoForm" method="POST" action="">
                <div class="form-grid">
                    <div>
                        <label>Guia de Entrada Original</label>
                        <input type="text" id="sr_guia_original" readonly style="background:#f1f5f9; font-weight:bold; color:#475569;">
                    </div>
                    <div>
                        <label>Status Final do Equipamento Original</label>
                        <select name="novo_status" id="sr_novo_status" required>
                            <option value="Reparado e Entregue">Reparado e Entregue</option>
                            <option value="Entregue">Entregue</option>
                        </select>
                    </div>
                    <div>
                        <label>Departamento Responsável (aparece na guia)</label>
                        <select name="departamento_responsavel_id" required>
                            {% for s in setores %}<option value="{{s.id}}" {% if s.id == session.setor_id %}selected{% endif %}>{{s.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label>Destino (Origem da Entrada)</label>
                        <input type="text" name="destino" id="sr_destino" required style="font-weight:600;">
                    </div>
                    <div>
                        <label>Equipamento (Tipo)</label>
                        <input type="text" name="equipamento" id="sr_equipamento" required style="font-weight:600;">
                    </div>
                    <div>
                        <label>Marca</label>
                        <input type="text" name="marca" id="sr_marca" required style="font-weight:600;">
                    </div>
                    <div>
                        <label>S/N / Nº Série</label>
                        <input type="text" name="numero_serie" id="sr_numero_serie" required style="font-weight:600;">
                    </div>
                    <div>
                        <label>Quantidade</label>
                        <input type="text" name="quantidade" id="sr_quantidade" required style="font-weight:600;">
                    </div>
                    <div>
                        <label>Motivo</label>
                        <input type="text" name="motivo" id="sr_motivo" style="font-weight:600;">
                    </div>
                    <div>
                        <label>Fornecedor</label>
                        <input type="text" name="fornecedor" id="sr_fornecedor" style="font-weight:600;">
                    </div>
                    <div style="grid-column: span 2; border-top: 1px solid var(--border); margin-top: 1rem; padding-top: 1rem;">
                        <h4 style="margin-bottom:0.5rem; color:#1e293b;">Responsáveis pelo Movimento de Saída</h4>
                    </div>
                    <div>
                        <label style="font-size:0.9rem; color:#64748b">Entregue por (Funcionário)</label>
                        <select name="entregue_por" id="sr_entregue" required></select>
                    </div>
                    <div>
                        <label style="font-size:0.9rem; color:#64748b">Recebido por (Funcionário)</label>
                        <select name="recebido_por" id="sr_recebido" required></select>
                    </div>
                    <div style="grid-column: span 2;">
                        <label style="font-size:0.9rem; color:#64748b">Agente de Protecção</label>
                        <select name="agente_protecao" id="sr_protecao"></select>
                    </div>
                </div>
                <button type="submit" class="btn btn-blue" style="margin-top:2rem; width:100%; padding:0.8rem; font-size:1.05rem; font-weight:bold;">CONFIRMAR SAÍDA E GERAR GUIA</button>
            </form>
        </div>
    </div>

    <!-- Modal de Alteração de Estado do Movimento -->
    <div id="movEstadoModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1020; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:480px; max-width:95%;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
                <h3>🚚 Alterar Estado do Movimento</h3>
                <button type="button" class="btn btn-outline" onclick="document.getElementById('movEstadoModal').style.display='none'" style="padding:0.4rem 0.8rem;">Fechar</button>
            </div>
            <form onsubmit="guardarEstadoMov(event)">
                <div>
                    <label>Guia</label>
                    <input type="text" id="me_guia" readonly style="background:#f1f5f9; font-weight:bold; color:#475569;">
                </div>
                <div>
                    <label>Estado Atual</label>
                    <input type="text" id="me_atual" readonly style="background:#f1f5f9; color:#475569;">
                </div>
                <div>
                    <label>Novo Estado</label>
                    <select id="me_estado" required>
                        <option value="EM_PREPARACAO">Em Preparação</option>
                        <option value="EMPACOTAMENTO">Empacotamento</option>
                        <option value="A_ESPERA_ENVIO">À espera de envio</option>
                        <option value="ENVIADO">Enviado</option>
                        <option value="RECEBIDO">Recebido</option>
                    </select>
                </div>
                <div>
                    <label>Local (Opcional)</label>
                    <input type="text" id="me_local" placeholder="Localização atual">
                </div>
                <div>
                    <label>Observações (Opcional)</label>
                    <textarea id="me_obs" rows="2" placeholder="Observações..."></textarea>
                </div>
                <button type="submit" class="btn btn-blue" style="margin-top:1.5rem; width:100%; padding:0.8rem;">SALVAR ESTADO</button>
            </form>
        </div>
    </div>

    <!-- Modal de Busca por Código de Barras -->
    <div id="barcodeModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1030; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:600px; max-width:95%; max-height:90vh; overflow-y:auto;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
                <h3>🔍 Buscar Equipamento por Código de Barras</h3>
                <button type="button" class="btn btn-outline" onclick="document.getElementById('barcodeModal').style.display='none'" style="padding:0.4rem 0.8rem;">Fechar</button>
            </div>
            <div style="display:flex; gap:0.5rem; margin-bottom:1rem;">
                <input type="text" id="barcodeInput" placeholder="Escanear ou digitar o código de barras..." style="flex:1; padding:0.7rem; border:1px solid #cbd5e1; border-radius:4px;" autofocus>
                <button class="btn btn-blue" onclick="buscarBarcode()" style="padding:0.7rem 1.2rem;">Buscar</button>
            </div>
            <div id="barcode_result"></div>
        </div>
    </div>

    <script>
        function abrirBuscaBarcode() {
            document.getElementById('barcodeModal').style.display = 'flex';
            var inp = document.getElementById('barcodeInput');
            inp.value = '';
            inp.focus();
        }
        function buscarBarcode() {
            var codigo = document.getElementById('barcodeInput').value.trim();
            if (!codigo) { alert('Digite ou escaneie um código de barras.'); return; }
            var box = document.getElementById('barcode_result');
            box.innerHTML = '<div style="color:#64748b;">A pesquisar...</div>';
            fetch('/api/buscar_barcode?codigo=' + encodeURIComponent(codigo))
                .then(function(r){ return r.json().then(function(j){ return {ok:r.ok, j:j}; }); })
                .then(function(res){
                    if (!res.ok) { box.innerHTML = '<div style="color:#dc2626; background:#fee2e2; padding:1rem; border-radius:0.5rem;">' + (res.j.error || 'Equipamento não encontrado.') + '</div>'; return; }
                    var it = res.j.item, t = res.j.tipo;
                    var guia = it.guia || ('INV-' + it.id);
                    var html = '<div style="border:1px solid var(--border); border-radius:0.5rem; padding:1rem;">';
                    html += '<h4 style="margin-top:0;">' + (it.equipamento||'') + (it.marca ? ' (' + it.marca + ')' : '') + '</h4>';
                    html += '<div style="display:grid; grid-template-columns:1fr 1fr; gap:0.5rem 1rem; font-size:0.9rem; margin-top:0.75rem;">';
                    html += '<div><strong>S/N:</strong> ' + (it.numero_serie||'-') + '</div>';
                    html += '<div><strong>Qtd:</strong> ' + (it.quantidade||'-') + '</div>';
                    html += '<div><strong>Tipo:</strong> ' + t + '</div>';
                    html += '<div><strong>Status:</strong> ' + (it.status||'-') + '</div>';
                    html += '<div><strong>Estado:</strong> ' + ((it.estado||it.estado_rastreio||'-').replace(/_/g,' ')) + '</div>';
                    html += '<div><strong>Guia:</strong> ' + guia + '</div>';
                    html += '</div>';
                    html += '<div style="margin-top:1rem;"><button class="btn btn-outline" onclick="buscarBarcodeRastreio(\\'' + guia + '\\')">📦 Ver Rastreio</button></div>';
                    html += '<div id="barcode_rastreio" style="margin-top:0.75rem;"></div>';
                    html += '</div>';
                    box.innerHTML = html;
                })
                .catch(function(e){ box.innerHTML = '<div style="color:#dc2626;">Erro de ligação.</div>'; });
        }
        function buscarBarcodeRastreio(guia) {
            var br = document.getElementById('barcode_rastreio');
            br.innerHTML = '<div style="color:#64748b;">A carregar histórico...</div>';
            fetch('/api/rastreio/' + encodeURIComponent(guia))
                .then(function(r){ return r.json(); })
                .then(function(rows){
                    if (!rows || rows.length === 0) { br.innerHTML = '<div style="color:#64748b;">Sem histórico registado.</div>'; return; }
                    var html = '<div style="border-top:1px solid var(--border); padding-top:0.75rem;"><strong>Histórico / Rastreio:</strong></div>';
                    rows.forEach(function(ev){
                        html += '<div style="border-left:3px solid #3b82f6; padding:0.5rem 0.75rem; background:#f8fafc; border-radius:0 0.375rem 0.375rem 0; margin-top:0.5rem;">';
                        html += '<div style="display:flex; justify-content:space-between;"><strong style="text-transform:capitalize;">' + (ev.estado||'').replace(/_/g,' ') + '</strong><span style="font-size:0.75rem; color:#64748b;">' + (ev.data||'') + '</span></div>';
                        html += (ev.local_atual ? '<div style="font-size:0.85rem; color:#475569;">📍 ' + ev.local_atual + '</div>' : '');
                        html += (ev.observacoes ? '<div style="font-size:0.8rem; color:#64748b;">' + ev.observacoes + '</div>' : '');
                        html += '<div style="font-size:0.75rem; color:#94a3b8;">por: ' + (ev.utilizador||'-') + '</div></div>';
                    });
                    br.innerHTML = html;
                })
                .catch(function(){ br.innerHTML = '<div style="color:#dc2626;">Erro ao carregar rastreio.</div>'; });
        }
        document.getElementById('barcodeInput').addEventListener('keydown', function(e){ if (e.key === 'Enter') { buscarBarcode(); } });
    </script>
</body></html>'''

CADASTROS_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>Configurações - STAE</title>
<style>
    .card table td { border-bottom: 1px solid #f1f5f9; padding: 0.5rem 0; }
</style>
</head>
<body>
    <div class="nav"><strong>STAE GESTÃO - CONFIGURAÇÕES</strong><div style="display:flex; align-items:center; gap:1rem;"><button onclick="syncManual()" class="btn btn-outline" style="background:transparent; color:white; border:1px solid rgba(255,255,255,0.3); padding:0.3rem 0.6rem; font-size:0.8rem">🔄 Sincronizar</button><a href="/" style="color:white">⬅️ Voltar ao Início</a></div></div>
    <div class="container">
        {% if msg %}<div style="background:#dcfce3; color:#166534; padding:1rem; border-radius:0.5rem; margin-bottom:1rem;">{{msg}}</div>{% endif %}
        
        <div class="card">
            <h3>🔒 Alterar a minha palavra-passe</h3>
            <p style="color:#64748b; font-size:0.9rem; margin-bottom:1rem;">Utilize esta secção para alterar a sua própria palavra-passe de acesso ao sistema.</p>
            <form method="POST" action="/alterar_senha" style="display:flex; gap:1rem; flex-wrap:wrap; align-items:flex-end;">
                <div style="flex:1; min-width:180px;">
                    <label>Palavra-passe atual</label>
                    <input type="password" name="senha_atual" required>
                </div>
                <div style="flex:1; min-width:180px;">
                    <label>Nova palavra-passe</label>
                    <input type="password" name="nova_senha" required>
                </div>
                <div style="flex:1; min-width:180px;">
                    <label>Confirmar nova palavra-passe</label>
                    <input type="password" name="nova_senha2" required>
                </div>
                <button class="btn btn-blue">Alterar Palavra-passe</button>
            </form>
        </div>
        
        <div class="form-grid" style="grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 1.5rem;">
            <!-- Setores -->
            <div class="card">
                <h3>Adicionar Setor</h3>
                <form method="POST" action="/add_setor">
                    <input name="nome" placeholder="Nome do Setor" required>
                    <button class="btn btn-blue" style="margin-top:1rem; width:100%">Salvar Setor</button>
                </form>
                <h4 style="margin-top:2rem">Setores Existentes</h4>
                <table style="margin-top:0.5rem">
                    {% for s in setores %}
                    <tr>
                        <td style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                            <span style="font-weight: 500;">{{s.nome}}</span>
                            <div style="display:flex; gap:0.25rem; align-items:center;">
                                <button onclick="openEdit('/edit_setor/{{s.id}}', 'Editar Setor', [{label:'Nome do Setor', name:'nome', type:'text', value:'{{s.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                                <form method="POST" action="/delete_setor/{{s.id}}" style="display:inline;" onsubmit="return confirm('Tem certeza que deseja remover este setor?');">
                                    <button class="btn btn-danger" style="padding:0.2rem 0.5rem; font-size:0.8rem">Remover</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <!-- Funcionários -->
            <div class="card">
                <h3>Adicionar Funcionário</h3>
                <form method="POST" action="/add_funcionario">
                    <input name="nome" placeholder="Nome do Funcionário" required>
                    <input name="cargo" placeholder="Cargo">
                    <select name="setor_id" required>
                        <option value="">Selecione o Setor</option>
                        {% for s in setores %}<option value="{{s.id}}">{{s.nome}}</option>{% endfor %}
                    </select>
                    <button class="btn btn-green" style="margin-top:1rem; width:100%">Salvar Funcionário</button>
                </form>
                <h4 style="margin-top:2rem">Funcionários Cadastrados</h4>
                <table style="margin-top:0.5rem">
                    {% for f in funcionarios %}
                    <tr>
                        <td style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                            <div>
                                <span style="font-weight: 500;">{{f.nome}}</span><br>
                                <small style="color:#64748b;">{{f.cargo or '-'}}</small>
                            </div>
                            <div style="display:flex; gap:0.25rem; align-items:center;">
                                <button onclick="openEdit('/edit_funcionario/{{f.id}}', 'Editar Funcionário', [{label:'Nome', name:'nome', type:'text', value:'{{f.nome}}', required:true}, {label:'Cargo', name:'cargo', type:'text', value:'{{f.cargo or ""}}', required:false}, {label:'Setor', name:'setor_id', type:'select', value:'{{f.setor_id}}', options:[{% for s in setores %}{value:'{{s.id}}',text:'{{s.nome}}'},{% endfor %}]}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                                <form method="POST" action="/delete_funcionario/{{f.id}}" style="display:inline;" onsubmit="return confirm('Tem certeza que deseja remover este funcionário?');">
                                    <button class="btn btn-danger" style="padding:0.2rem 0.5rem; font-size:0.8rem">Remover</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <!-- Usuários -->
            <div class="card">
                <h3>Adicionar Usuário</h3>
                <form method="POST" action="/add_user">
                    <input name="nome_completo" placeholder="Nome Completo" required>
                    <input name="username" placeholder="Nome de Utilizador" required>
                    <input name="password" placeholder="Palavra-passe" required type="password">
                    <select name="perfil" required>
                        <option value="">Selecione o Perfil</option>
                        <option value="admin">Administrador</option>
                        <option value="tecnico">Técnico</option>
                        <option value="protecao">Protecção</option>
                    </select>
                    <select name="setor_id">
                        <option value="">Selecione o Setor (Opcional)</option>
                        {% for s in setores %}<option value="{{s.id}}">{{s.nome}}</option>{% endfor %}
                    </select>
                    <div style="margin-top:0.75rem; font-size:0.85rem; color:#64748b;">
                        <strong>Locais do Inventário que este utilizador pode aceder</strong><br>
                        <small>Selecione os locais. Se não selecionar nenhum, terá acesso apenas ao seu setor. O Administrador vê sempre tudo.</small>
                    </div>
                    <div style="display:flex; flex-wrap:wrap; gap:0.5rem; margin-top:0.5rem; max-height:110px; overflow-y:auto; border:1px solid var(--border); border-radius:0.5rem; padding:0.5rem;">
                        {% for s in setores %}
                        <label style="display:flex; align-items:center; gap:0.3rem; font-size:0.85rem;"><input type="checkbox" name="locais_acesso" value="{{s.id}}" {% if not s_locals or s.id in s_locals %}checked{% endif %}> {{s.nome}}</label>
                        {% endfor %}
                    </div>
                    <select name="eleitoral_local_id">
                        <option value="">Selecione o Local Eleitoral (Opcional - STAE)</option>
                        {% for l in eleitoral_locais %}<option value="{{l.id}}">{{l.tipo}} - {{l.nome}}</option>{% endfor %}
                    </select>
                    <div style="margin-top:0.75rem; font-size:0.85rem; color:#64748b;">
                        <strong>Permissões de Estados de Saída</strong><br>
                        <small>Estados que este usuário pode marcar (vazio = regra por setor: origem marca envio, destino marca recebido).</small>
                    </div>
                    <div style="display:flex; flex-wrap:wrap; gap:0.5rem; margin-top:0.5rem;">
                        <label style="display:flex; align-items:center; gap:0.3rem; font-size:0.85rem;"><input type="checkbox" name="permissoes_estado" value="EM_PREPARACAO"> Preparação</label>
                        <label style="display:flex; align-items:center; gap:0.3rem; font-size:0.85rem;"><input type="checkbox" name="permissoes_estado" value="EMPACOTAMENTO"> Empacotamento</label>
                        <label style="display:flex; align-items:center; gap:0.3rem; font-size:0.85rem;"><input type="checkbox" name="permissoes_estado" value="A_ESPERA_ENVIO"> À espera de envio</label>
                        <label style="display:flex; align-items:center; gap:0.3rem; font-size:0.85rem;"><input type="checkbox" name="permissoes_estado" value="ENVIADO"> Enviado</label>
                        <label style="display:flex; align-items:center; gap:0.3rem; font-size:0.85rem;"><input type="checkbox" name="permissoes_estado" value="RECEBIDO"> Recebido</label>
                    </div>
                    <button class="btn" style="background:#1e293b; color:white; margin-top:1rem; width:100%">Salvar Usuário</button>
                </form>
                <h4 style="margin-top:2rem">Usuários do Sistema</h4>
                <table style="margin-top:0.5rem">
                    {% for u in users_list %}
                    <tr>
                        <td style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                            <div>
                                <span style="font-weight: 600;">{{u.nome_completo}}</span><br>
                                <small style="color:#64748b;">{{u.username}} ({{u.perfil}}){% if u.permissoes_estado %} · Estados: {{u.permissoes_estado|replace('_',' ')}}
                                {% else %} · Estados: por setor{% endif %}</small>
                            </div>
                            <div style="display:flex; gap:0.25rem; align-items:center;">
                                <button onclick="openEdit('/edit_user/{{u.id}}', 'Editar Usuário', [{label:'Nome Completo', name:'nome_completo', type:'text', value:'{{u.nome_completo}}', required:true}, {label:'Username', name:'username', type:'text', value:'{{u.username}}', required:true}, {label:'Perfil', name:'perfil', type:'select', value:'{{u.perfil}}', options:[{value:'admin',text:'Administrador'},{value:'tecnico',text:'Técnico'},{value:'protecao',text:'Protecção'}]}, {label:'Setor', name:'setor_id', type:'select', value:'{{u.setor_id or ""}}', options:[{value:'',text:'Nenhum'}, {% for s in setores %}{value:'{{s.id}}',text:'{{s.nome}}'},{% endfor %}]}, {label:'Local Eleitoral', name:'eleitoral_local_id', type:'select', value:'{{u.eleitoral_local_id or ""}}', options:[{value:'',text:'Nenhum'}, {% for l in eleitoral_locais %}{value:'{{l.id}}',text:'{{l.tipo}} - {{l.nome}}'},{% endfor %}]}, {label:'Locais do Inventário a que pode aceder', name:'locais_acesso', type:'checkboxes', value:'{{u.locais_acesso or ""}}', options:[{% for s in setores %}{value:'{{s.id}}',text:'{{s.nome}}'},{% endfor %}]}, {label:'Permissões de Estados de Saída', name:'permissoes_estado', type:'checkboxes', value:'{{u.permissoes_estado or ""}}', options:[{value:'EM_PREPARACAO',text:'Preparação'},{value:'EMPACOTAMENTO',text:'Empacotamento'},{value:'A_ESPERA_ENVIO',text:'À espera de envio'},{value:'ENVIADO',text:'Enviado'},{value:'RECEBIDO',text:'Recebido'}]}, {label:'Nova Senha (Opcional)', name:'password', type:'password', value:'', required:false}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                                <form method="POST" action="/delete_user/{{u.id}}" style="display:inline;" onsubmit="return confirm('Tem certeza que deseja remover este usuário?');">
                                    <button class="btn btn-danger" style="padding:0.2rem 0.5rem; font-size:0.8rem">Remover</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <!-- Marcas -->
            <div class="card">
                <h3>Adicionar Marca</h3>
                <form method="POST" action="/add_marca">
                    <input name="nome" placeholder="Ex: HP, Dell, Apple" required>
                    <button class="btn btn-blue" style="margin-top:1rem; width:100%">Salvar Marca</button>
                </form>
                <h4 style="margin-top:2rem">Marcas Cadastradas</h4>
                <table style="margin-top:0.5rem">
                    {% for m in marcas %}
                    <tr>
                        <td style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                            <span style="font-weight: 500;">{{m.nome}}</span>
                            <div style="display:flex; gap:0.25rem; align-items:center;">
                                <button onclick="openEdit('/edit_marca/{{m.id}}', 'Editar Marca', [{label:'Nome da Marca', name:'nome', type:'text', value:'{{m.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                                <form method="POST" action="/delete_marca/{{m.id}}" style="display:inline;" onsubmit="return confirm('Tem certeza que deseja remover esta marca?');">
                                    <button class="btn btn-danger" style="padding:0.2rem 0.5rem; font-size:0.8rem">Remover</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <!-- Tipos de Equipamento -->
            <div class="card">
                <h3>Adicionar Tipo de Equip.</h3>
                <form method="POST" action="/add_tipo">
                    <input name="nome" placeholder="Ex: Desktop, Monitor" required>
                    <button class="btn btn-green" style="margin-top:1rem; width:100%">Salvar Tipo</button>
                </form>
                <h4 style="margin-top:2rem">Tipos Cadastrados</h4>
                <table style="margin-top:0.5rem">
                    {% for t in tipos %}
                    <tr>
                        <td style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                            <span style="font-weight: 500;">{{t.nome}}</span>
                            <div style="display:flex; gap:0.25rem; align-items:center;">
                                <button onclick="openEdit('/edit_tipo/{{t.id}}', 'Editar Tipo', [{label:'Nome do Tipo', name:'nome', type:'text', value:'{{t.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                                <form method="POST" action="/delete_tipo/{{t.id}}" style="display:inline;" onsubmit="return confirm('Tem certeza que deseja remover este tipo de equipamento?');">
                                    <button class="btn btn-danger" style="padding:0.2rem 0.5rem; font-size:0.8rem">Remover</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <!-- Motivos -->
            <div class="card">
                <h3>Adicionar Motivo</h3>
                <form method="POST" action="/add_motivo">
                    <input name="nome" placeholder="Ex: Alocação, Avaria" required>
                    <button class="btn btn-blue" style="margin-top:1rem; width:100%">Salvar Motivo</button>
                </form>
                <h4 style="margin-top:2rem">Motivos Cadastrados</h4>
                <table style="margin-top:0.5rem">
                    {% for m in motivos %}
                    <tr>
                        <td style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                            <span style="font-weight: 500;">{{m.nome}}</span>
                            <div style="display:flex; gap:0.25rem; align-items:center;">
                                <button onclick="openEdit('/edit_motivo/{{m.id}}', 'Editar Motivo', [{label:'Nome do Motivo', name:'nome', type:'text', value:'{{m.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                                <form method="POST" action="/delete_motivo/{{m.id}}" style="display:inline;" onsubmit="return confirm('Tem certeza que deseja remover este motivo?');">
                                    <button class="btn btn-danger" style="padding:0.2rem 0.5rem; font-size:0.8rem">Remover</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <!-- Fornecedores -->
            <div class="card">
                <h3>Adicionar Fornecedor</h3>
                <form method="POST" action="/add_fornecedor">
                    <input name="nome" placeholder="Ex: NCR Angola" required>
                    <button class="btn btn-blue" style="margin-top:1rem; width:100%">Salvar Fornecedor</button>
                </form>
                <h4 style="margin-top:2rem">Fornecedores</h4>
                <table style="margin-top:0.5rem">
                    {% for f in fornecedores %}
                    <tr>
                        <td style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                            <span style="font-weight: 500;">{{f.nome}}</span>
                            <div style="display:flex; gap:0.25rem; align-items:center;">
                                <button onclick="openEdit('/edit_fornecedor/{{f.id}}', 'Editar Fornecedor', [{label:'Nome', name:'nome', type:'text', value:'{{f.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                                <form method="POST" action="/delete_fornecedor/{{f.id}}" style="display:inline;" onsubmit="return confirm('Tem certeza que deseja remover este fornecedor?');">
                                    <button class="btn btn-danger" style="padding:0.2rem 0.5rem; font-size:0.8rem">Remover</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <!-- Instituições Externas -->
            <div class="card">
                <h3>Adicionar Instituição Ext.</h3>
                <form method="POST" action="/add_instituicao">
                    <input name="nome" placeholder="Ex: Ministério X" required>
                    <button class="btn btn-green" style="margin-top:1rem; width:100%">Salvar Instituição</button>
                </form>
                <h4 style="margin-top:2rem">Instituições Externas</h4>
                <table style="margin-top:0.5rem">
                    {% for i in instituicoes %}
                    <tr>
                        <td style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                            <span style="font-weight: 500;">{{i.nome}}</span>
                            <div style="display:flex; gap:0.25rem; align-items:center;">
                                <button onclick="openEdit('/edit_instituicao/{{i.id}}', 'Editar Instituição', [{label:'Nome', name:'nome', type:'text', value:'{{i.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                                <form method="POST" action="/delete_instituicao/{{i.id}}" style="display:inline;" onsubmit="return confirm('Tem certeza que deseja remover esta instituição?');">
                                    <button class="btn btn-danger" style="padding:0.2rem 0.5rem; font-size:0.8rem">Remover</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>
    </div>

    <!-- Modals de Edição -->
    <div id="editModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:460px; max-width:95%; max-height:92vh; overflow-y:auto;">
            <h3 id="editTitle">Editar</h3>
            <form id="editForm" method="POST" action="">
                <div id="editFields" style="display:flex; flex-direction:column; gap:1rem; margin-bottom:1rem; max-height:60vh; overflow-y:auto; padding-right:0.5rem;"></div>
                <div style="display:flex; gap:1rem;">
                    <button type="button" class="btn btn-outline" style="flex:1" onclick="document.getElementById('editModal').style.display='none'">Cancelar</button>
                    <button type="submit" class="btn btn-blue" style="flex:1">Salvar</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        function openEdit(action, title, fields) {
            document.getElementById('editForm').action = action;
            document.getElementById('editTitle').innerText = title;
            const container = document.getElementById('editFields');
            container.innerHTML = '';
            fields.forEach(f => {
                if(f.type === 'select') {
                    let html = `<label>${f.label}</label><select name="${f.name}" required>`;
                    f.options.forEach(o => {
                        html += `<option value="${o.value}" ${o.value==f.value?'selected':''}>${o.text}</option>`;
                    });
                    html += `</select>`;
                    container.innerHTML += html;
                } else if(f.type === 'checkboxes') {
                    let html = `<label>${f.label}</label>`;
                    const current = String(f.value || '').split(',').map(s=>s.trim()).filter(Boolean);
                    const marcarVazios = (f.name === 'locais_acesso') ? 'checked' : '';
                    f.options.forEach(o => {
                        const checked = current.includes(o.value) ? 'checked' : (current.length === 0 ? marcarVazios : '');
                        html += `<label style="display:flex; align-items:center; gap:0.3rem; font-size:0.85rem;"><input type="checkbox" name="${f.name}" value="${o.value}" ${checked}> ${o.text}</label>`;
                    });
                    const nota = (f.name === 'locais_acesso')
                        ? 'Vazio = apenas o próprio setor. Administrador vê sempre tudo.'
                        : 'Vazio = regra por setor (origem marca envio, destino marca recebido).';
                    html += `<small style="color:#64748b;">` + nota + `</small>`;
                    container.innerHTML += html;
                } else {
                    container.innerHTML += `<label>${f.label}</label><input type="${f.type}" name="${f.name}" value="${f.value}" ${f.required?'required':''} placeholder="${f.placeholder||''}">`;
                }
            });
            document.getElementById('editModal').style.display = 'flex';
        }
    </script>
</body></html>
'''

INVENTARIO_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>{{ titulo_pagina }}</title>
<style>
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
    .stat-card { background: white; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .stat-number { font-size: 2rem; font-weight: bold; color: var(--primary); margin-top: 0.5rem; }
    .card table td { border-bottom: 1px solid #f1f5f9; padding: 0.75rem 0.5rem; }
    
    .pagination-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 1.5rem;
        padding-top: 1rem;
        border-top: 1px solid var(--border);
    }
    .pagination-btn {
        background: white;
        border: 1px solid var(--border);
        padding: 0.4rem 0.8rem;
        border-radius: 0.375rem;
        cursor: pointer;
        font-weight: 600;
        transition: all 0.2s;
    }
    .pagination-btn:hover:not(:disabled) {
        background: #f8fafc;
        border-color: #cbd5e1;
    }
    .pagination-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
</style>
</head>
<body>
    <div class="nav">
        <strong>STAE GESTÃO - {{ titulo_pagina }}</strong>
        <div>
            <button id="syncBtn" onclick="syncCloud()" class="btn btn-outline" style="background:#10b981; color:white; border:none; margin-right:1rem; padding: 0.4rem 0.8rem; font-weight:bold; cursor:pointer; transition: all 0.3s;">🔄 Sincronizar Nuvem</button>
            <a href="/" class="btn btn-outline" style="background:white; color:#0f172a; margin-right:1.5rem; padding: 0.4rem 0.8rem;">⬅️ Voltar ao Início</a>
            <span>👤 {{session.username}}</span>
        </div>
    </div>
    <div class="container">
        {% if msg %}<div style="background:#dcfce3; color:#166534; padding:1rem; border-radius:0.5rem; margin-bottom:1rem;">{{msg}}</div>{% endif %}
        
        <div class="card" style="margin-bottom: 2rem;">
            <form method="GET" action="/inventario" style="display:flex; flex-wrap:wrap; gap:1rem; align-items:flex-end;">
                <div style="flex:1; min-width:250px;">
                    <label style="font-weight:600; font-size:0.85rem; color:#475569;">Local (Setor) — visualize um ou vários</label>
                    <select name="filtro_setor" multiple size="6" style="width:100%; margin-top:0.25rem;">
                        {% for s in setores_filtro %}
                        <option value="{{ s.id }}" {% if s.id in filtro_ativo_ids %}selected{% endif %}>{{ s.nome }}</option>
                        {% endfor %}
                    </select>
                    <div style="font-size:0.75rem; color:#64748b; margin-top:0.25rem;">Segure Ctrl (ou Cmd) para escolher vários locais.</div>
                </div>
                <div style="display:flex; gap:0.5rem;">
                    <button class="btn btn-blue" style="margin-top:0;">Filtrar</button>
                    <a href="/inventario" class="btn btn-outline" style="margin-top:0; background:white;">Limpar</a>
                </div>
            </form>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div style="color: #64748b; font-weight: 600;">Total de Itens</div>
                <div class="stat-number">{{ stats.total }}</div>
            </div>
            <div class="stat-card">
                <div style="color: #10b981; font-weight: 600;">Disponíveis</div>
                <div class="stat-number" style="color: #10b981;">{{ stats.disponiveis }}</div>
            </div>
            <div class="stat-card">
                <div style="color: #3b82f6; font-weight: 600;">Em Uso</div>
                <div class="stat-number" style="color: #3b82f6;">{{ stats.em_uso }}</div>
            </div>
            <div class="stat-card">
                <div style="color: #ef4444; font-weight: 600;">Avariados</div>
                <div class="stat-number" style="color: #ef4444;">{{ stats.danificados }}</div>
            </div>
        </div>

        <!-- Pending Confirmation Panel -->
        {% if pending_items %}
        <div class="card" style="margin-bottom: 2rem; border: 2px solid #fed7aa; background: #fffbeb;">
            <h3 style="color: #ea580c; display: flex; align-items: center; gap: 0.5rem;">📥 Equipamentos Pendentes de Receção</h3>
            <div style="overflow-x: auto; margin-top: 1rem;">
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #ffedd5; text-align: left; color: #ea580c; font-size: 0.8rem">
                            <th style="padding: 0.75rem">EQUIPAMENTO</th>
                            <th style="padding: 0.75rem">MARCA</th>
                            <th style="padding: 0.75rem">S/N</th>
                            <th style="padding: 0.75rem">QUANTIDADE</th>
                            <th style="padding: 0.75rem">GUIA DE ORIGEM</th>
                            <th style="padding: 0.75rem">SETOR DE ORIGEM</th>
                            <th style="padding: 0.75rem; text-align: right;">AÇÕES</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for p_item in pending_items %}
                        <tr style="border-bottom: 1px solid #fed7aa">
                            <td style="padding: 0.75rem; font-weight: 600;">{{ p_item.equipamento }}</td>
                            <td style="padding: 0.75rem">{{ p_item.marca }}</td>
                            <td style="padding: 0.75rem; font-family: monospace;">{{ p_item.numero_serie }}</td>
                            <td style="padding: 0.75rem; font-weight: bold; text-align: center;">{{ p_item.quantidade }}</td>
                            <td style="padding: 0.75rem; font-weight: bold; color: #475569;">{{ p_item.guia_origem or '-' }}</td>
                            <td style="padding: 0.75rem; color: #64748b;">{{ p_item.setor_nome or 'Desconhecido' }}</td>
                            <td style="padding: 0.75rem; text-align: right;">
                                <form method="POST" action="/inventario/confirmar_rececao/{{ p_item.id }}" style="display:inline;">
                                    <button class="btn btn-green" style="margin-top:0; padding: 0.3rem 0.8rem; font-weight: bold; font-size: 0.8rem;">Confirmar Receção</button>
                                </form>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}

        <!-- Provincial Pending Confirmation Panel -->
        {% if provincias_pendentes %}
        <div class="card" style="margin-bottom: 2rem; border: 2px solid #bfdbfe; background: #eff6ff;">
            <h3 style="color: #1d4ed8; display: flex; align-items: center; gap: 0.5rem;">🚚 Receção Pendente entre Províncias</h3>
            <div style="overflow-x: auto; margin-top: 1rem;">
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #dbeafe; text-align: left; color: #1d4ed8; font-size: 0.8rem">
                            <th style="padding: 0.75rem">EQUIPAMENTO</th>
                            <th style="padding: 0.75rem">MARCA</th>
                            <th style="padding: 0.75rem">S/N</th>
                            <th style="padding: 0.75rem">QUANTIDADE</th>
                            <th style="padding: 0.75rem">PROVÍNCIA DESTINO</th>
                            <th style="padding: 0.75rem">ESTADO</th>
                            <th style="padding: 0.75rem">GUIA</th>
                            <th style="padding: 0.75rem; text-align: right;">AÇÕES</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for pp in provincias_pendentes %}
                        <tr style="border-bottom: 1px solid #bfdbfe">
                            <td style="padding: 0.75rem; font-weight: 600;">{{ pp.equipamento }}</td>
                            <td style="padding: 0.75rem">{{ pp.marca }}</td>
                            <td style="padding: 0.75rem; font-family: monospace;">{{ pp.numero_serie }}</td>
                            <td style="padding: 0.75rem; font-weight: bold; text-align: center;">{{ pp.quantidade }}</td>
                            <td style="padding: 0.75rem; color: #1e40af;">{{ pp.provincia_destino_nome or '-' }}</td>
                            <td style="padding: 0.75rem; font-size: 0.8rem;">{{ (pp.estado or 'EM_PREPARACAO')|replace('_',' ') }}</td>
                            <td style="padding: 0.75rem; font-family: monospace;">{{ pp.guia_origem or '-' }}</td>
                            <td style="padding: 0.75rem; text-align: right;">
                                <form method="POST" action="/confirmar_recepcao_provincia/{{ pp.id }}" style="display:inline;">
                                    <button class="btn btn-green" style="margin-top:0; padding: 0.3rem 0.8rem; font-weight: bold; font-size: 0.8rem;">Confirmar Receção</button>
                                </form>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}

        <!-- Movement between Provinces card -->
        <div class="card" style="margin-bottom: 2rem;">
            <h3 style="margin-bottom: 0.25rem;">🚚 Movimentar Equipamento entre Províncias</h3>
            <form method="POST" action="/movimentar_provincia" style="margin-top: 1rem; display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem;">
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Província de Origem</label>
                    <select name="provincia_origem_id" required style="margin-top: 0.25rem;">
                        <option value="">-- Selecione --</option>
                        {% for p in provincias %}<option value="{{p.id}}">{{p.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Província de Destino</label>
                    <select name="provincia_destino_id" required style="margin-top: 0.25rem;">
                        <option value="">-- Selecione --</option>
                        {% for p in provincias %}<option value="{{p.id}}">{{p.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Local de Origem</label>
                    <input name="local_origem" placeholder="Ex: Armazém Central" style="margin-top: 0.25rem;">
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Local de Destino</label>
                    <input name="local_destino" placeholder="Ex: Delegação Provincial" style="margin-top: 0.25rem;">
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Equipamento</label>
                    <input name="equipamento" placeholder="Tipo de equipamento" required style="margin-top: 0.25rem;">
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Marca</label>
                    <input name="marca" placeholder="Marca" style="margin-top: 0.25rem;">
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Número de Série</label>
                    <input name="numero_serie" placeholder="S/N" style="margin-top: 0.25rem;">
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Quantidade</label>
                    <input name="quantidade" type="number" min="1" value="1" style="margin-top: 0.25rem;">
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Código de Barras (opcional)</label>
                    <input name="codigo_barras" placeholder="Código de barras" style="margin-top: 0.25rem;">
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Estado Inicial de Envio</label>
                    <select name="estado" style="margin-top: 0.25rem;">
                        {% for e in estados_intermedios %}<option value="{{e}}" {% if e == 'EM_PREPARACAO' %}selected{% endif %}>{{e.replace('_',' ')}}</option>{% endfor %}
                    </select>
                </div>
                <div style="grid-column: span 2;">
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Motivo</label>
                    <input name="motivo" placeholder="Motivo da movimentação" style="margin-top: 0.25rem;">
                </div>
                <div style="grid-column: span 4; display: flex; justify-content: flex-end;">
                    <button class="btn btn-blue" style="margin-top:0; padding: 0.6rem 1.5rem; font-weight: bold;">Enviar para Província</button>
                </div>
            </form>
        </div>

        <div style="display: grid; grid-template-columns: 350px 1fr; gap: 1.5rem; align-items: start;">
            <div class="card">
                <h3>Cadastrar Equipamento</h3>
                <form method="POST" action="/inventario/add" enctype="multipart/form-data" style="margin-top: 1rem; display: flex; flex-direction: column; gap: 1rem;">
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Tipo de Equipamento</label>
                        <select name="equipamento" required style="margin-top: 0.25rem;">
                            <option value="">-- Selecione --</option>
                            {% for t in tipos %}<option value="{{t.nome}}">{{t.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Marca</label>
                        <select name="marca" required style="margin-top: 0.25rem;">
                            <option value="">-- Selecione --</option>
                            {% for m in marcas %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Número de Série (S/N)</label>
                        <input name="numero_serie" placeholder="Ex: SN-12345 ou N/A" required style="margin-top: 0.25rem;">
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Código de Barras (opcional - scan)</label>
                        <input name="codigo_barras" id="cadastro_codigo_barras" placeholder="Escanear ou digitar código de barras..." style="margin-top: 0.25rem;">
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Quantidade</label>
                        <input name="quantidade" type="number" min="1" value="1" required style="margin-top: 0.25rem;">
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Setor Pertencente</label>
                        <select name="setor_id" required style="margin-top: 0.25rem;">
                            <option value="">-- Selecione o Setor --</option>
                            {% for s in setores %}<option value="{{s.id}}" {% if session.setor_id == s.id %}selected{% endif %}>{{s.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Província (opcional)</label>
                        <select name="provincia_id" style="margin-top: 0.25rem;">
                            <option value="">-- Selecione a Província --</option>
                            {% for p in provincias %}<option value="{{p.id}}">{{p.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Local de Uso / Armazenamento</label>
                        <input name="local_uso" placeholder="Ex: Armazém Central, Sala 2, ..." style="margin-top: 0.25rem;">
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Estado Intermédio (opcional)</label>
                        <select name="estado" style="margin-top: 0.25rem;">
                            {% for e in estados_intermedios %}<option value="{{e}}" {% if e == 'EM_ESTOQUE' %}selected{% endif %}>{{e.replace('_',' ')}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Documento do Equipamento (imagem → PDF)</label>
                        <input type="file" name="documento" accept=".jpg,.jpeg,.png,.bmp,.webp,.tif,.tiff,.pdf" style="margin-top: 0.25rem;">
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Status Inicial</label>
                        <select name="status" required style="margin-top: 0.25rem;">
                            <option value="Disponível">Disponível</option>
                            <option value="Em uso">Em uso</option>
                            <option value="Danificado">Danificado</option>
                            <option value="Avariado">Avariado</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Observações</label>
                        <textarea name="observacoes" rows="3" placeholder="Localização, detalhes físicos..." style="margin-top: 0.25rem;"></textarea>
                    </div>
                    <button class="btn btn-blue" style="margin-top:0.5rem; width:100%">Salvar no Inventário</button>
                </form>
            </div>

            <div class="card">
                <h3>Equipamentos em Stock</h3>
                
                <!-- Bulk Actions -->
                <div style="display:flex; justify-content: space-between; align-items:center; margin-top: 1rem; margin-bottom: 1rem; gap: 0.5rem; flex-wrap: wrap;">
                    <div style="display:flex; gap: 0.5rem;">
                        <button onclick="abrirTransferenciaMultiplos()" class="btn btn-blue" style="margin-top:0; font-size: 0.85rem;">📁 Transferir Selecionados</button>
                        <button onclick="apagarSelecionados()" class="btn btn-danger" style="margin-top:0; font-size: 0.85rem;">🗑️ Apagar Selecionados</button>
                    </div>
                    {% if session.perfil == 'admin' %}
                    <form method="POST" action="/inventario/delete_all" onsubmit="return confirm('ATENÇÃO: Isto irá apagar TODOS os equipamentos do inventário permanentemente. Continuar?');">
                        <button class="btn btn-danger" style="margin-top:0; background:#dc2626; font-size: 0.85rem;">⚠️ Apagar Todo o Inventário</button>
                    </form>
                    {% endif %}
                </div>

                <input type="text" id="invSearchInput" onkeyup="searchInvTable()" placeholder="Pesquisar por equipamento, marca ou S/N..." style="width:100%; padding:0.8rem; border:1px solid #cbd5e1; border-radius:4px; margin-bottom:1rem">
                
                <table id="invTable" style="width:100%; border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f1f5f9; text-align:left; color:#64748b; font-size:0.8rem">
                            <th style="padding:0.75rem; width: 30px;"><input type="checkbox" id="selectAllCheckbox" onclick="toggleSelectAll(this)"></th>
                            <th style="padding:0.75rem">EQUIPAMENTO</th>
                            <th style="padding:0.75rem">MARCA</th>
                            <th style="padding:0.75rem">S/N</th>
                            <th style="padding:0.75rem">QUANTIDADE</th>
                            <th style="padding:0.75rem">SETOR</th>
                            <th style="padding:0.75rem">PROVÍNCIA</th>
                            <th style="padding:0.75rem">ESTADO</th>
                            <th style="padding:0.75rem">STATUS</th>
                            <th style="padding:0.75rem">DOC</th>
                            <th style="padding:0.75rem; text-align: right;">ACÇÕES</th>
                        </tr>
                    </thead>
                    <tbody id="invTableBody">
                        <!-- Filled by JS -->
                    </tbody>
                </table>

                <div class="pagination-nav">
                    <button id="btnPrevPage" onclick="changePage(-1)" class="pagination-btn">⬅️ Anterior</button>
                    <span id="pageIndicator" style="font-weight: 600; color: #475569; font-size: 0.9rem;">Página 1 de 1</span>
                    <button id="btnNextPage" onclick="changePage(1)" class="pagination-btn">Próximo ➡️</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Modal de Edição de Inventário -->
    <div id="editInvModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:450px; max-width:90%;">
            <h3>Editar Item do Inventário</h3>
            <form id="editInvForm" method="POST" action="" style="margin-top: 1.5rem; display: flex; flex-direction: column; gap: 1rem;">
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Tipo de Equipamento</label>
                    <select name="equipamento" id="ei_equipamento" required>
                        {% for t in tipos %}<option value="{{t.nome}}">{{t.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Marca</label>
                    <select name="marca" id="ei_marca" required>
                        {% for m in marcas %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Número de Série (S/N)</label>
                    <input name="numero_serie" id="ei_numero_serie" required>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Quantidade em Stock</label>
                    <input name="quantidade" id="ei_quantidade" type="number" min="0" required>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Setor Pertencente</label>
                    <select name="setor_id" id="ei_setor_id" required>
                        {% for s in setores %}<option value="{{s.id}}">{{s.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Status</label>
                    <select name="status" id="ei_status" required>
                        <option value="Disponível">Disponível</option>
                        <option value="Em uso">Em uso</option>
                        <option value="Danificado">Danificado</option>
                        <option value="Avariado">Avariado</option>
                    </select>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Observações</label>
                    <textarea name="observacoes" id="ei_observacoes" rows="3"></textarea>
                </div>
                <div style="display:flex; gap:1rem; margin-top:0.5rem;">
                    <button type="button" class="btn btn-outline" style="flex:1" onclick="document.getElementById('editInvModal').style.display='none'">Cancelar</button>
                    <button type="submit" class="btn btn-blue" style="flex:1">Salvar Alterações</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal de Saída Rápida a partir do Inventário -->
    <div id="saidaRapidaInvModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1010; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:750px; max-width:95%; max-height:90vh; overflow-y:auto;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem;">
                <h2>📤 Registrar Saída (Item do Inventário Local)</h2>
                <button type="button" class="btn btn-outline" onclick="fecharSaidaRapidaInv()" style="padding:0.4rem 0.8rem;">Fechar</button>
            </div>
            <form id="saidaRapidaInvForm" method="POST" action="">
                <input type="hidden" name="inventario_id" id="sri_inventario_id">
                <div class="form-grid">
                    <div>
                        <label>Departamento Responsável (aparece na guia)</label>
                        <select name="departamento_responsavel_id" required>
                            {% for s in setores %}<option value="{{s.id}}" {% if s.id == session.setor_id %}selected{% endif %}>{{s.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label>Destino</label>
                        <select name="destino" required>
                            <option value="">-- Selecione o Destino --</option>
                            <optgroup label="Setores Internos">
                                {% for s in setores %}<option value="SETOR_{{s.id}}">{{s.nome}}</option>{% endfor %}
                            </optgroup>
                            <optgroup label="Instituições Externas">
                                {% for i in instituicoes %}<option value="Externo - {{i.nome}}">{{i.nome}}</option>{% endfor %}
                            </optgroup>
                        </select>
                    </div>
                    <div>
                        <label>Equipamento</label>
                        <input type="text" name="equipamento" id="sri_equipamento" readonly style="background:#f1f5f9; color:#475569;">
                    </div>
                    <div>
                        <label>Marca</label>
                        <input type="text" name="marca" id="sri_marca" readonly style="background:#f1f5f9; color:#475569;">
                    </div>
                    <div>
                        <label>Número de Série (S/N)</label>
                        <input type="text" name="numero_serie" id="sri_numero_serie" readonly style="background:#f1f5f9; color:#475569;">
                    </div>
                    <div>
                        <label>Quantidade Disponível</label>
                        <input type="text" id="sri_qtd_disponivel" readonly style="background:#f1f5f9; font-weight:bold; color:#475569;">
                    </div>
                    <div>
                        <label>Quantidade a Retirar</label>
                        <input type="number" name="quantidade" id="sri_quantidade" min="1" value="1" required>
                    </div>
                    <div>
                        <label>Motivo</label>
                        <select name="motivo" required>
                            <option value="">-- Selecione --</option>
                            {% for m in motivos %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div style="grid-column: span 2; border-top: 1px solid var(--border); margin-top: 1rem; padding-top: 1rem;">
                        <h4 style="margin-bottom:0.5rem; color:#1e293b;">Responsáveis pela Saída</h4>
                    </div>
                    <div>
                        <label style="font-size:0.9rem; color:#64748b">Entregue por (Funcionário)</label>
                        <select name="entregue_por" id="sri_entregue" required></select>
                    </div>
                    <div>
                        <label style="font-size:0.9rem; color:#64748b">Recebido por (Funcionário)</label>
                        <select name="recebido_por" id="sri_recebido" required></select>
                    </div>
                    <div style="grid-column: span 2;">
                        <label style="font-size:0.9rem; color:#64748b">Agente de Protecção</label>
                        <select name="agente_protecao" id="sri_protecao"></select>
                    </div>
                </div>
                <button type="submit" class="btn btn-blue" style="margin-top:2rem; width:100%; padding:0.8rem; font-size:1.05rem; font-weight:bold;">CONFIRMAR SAÍDA E GERAR GUIA</button>
            </form>
        </div>
    </div>

    <!-- Modal de Transferência de Múltiplos Itens -->
    <div id="transferModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:500px; max-width:90%;">
            <h3>📁 Transferir Equipamentos para Setor</h3>
            <form id="transferForm" onsubmit="submeterTransferencia(event)" style="margin-top:1.5rem; display:flex; flex-direction:column; gap:1rem;">
                <div>
                    <label style="font-weight:600; font-size:0.85rem; color:#475569;">Setor de Destino</label>
                    <select id="trans_setor_destino_id" required>
                        <option value="">-- Selecione o Setor --</option>
                        {% for s in setores %}<option value="{{s.id}}">{{s.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div id="trans_items_container" style="max-height: 200px; overflow-y: auto; border: 1px solid var(--border); padding: 0.5rem; border-radius: 4px; display:flex; flex-direction:column; gap:0.5rem;">
                    <!-- Quantidades inputs dynamically loaded -->
                </div>
                <div style="display:flex; gap:1rem;">
                    <div>
                        <label style="font-weight:600; font-size:0.85rem; color:#475569;">Entregue por (Resp.)</label>
                        <input type="text" id="trans_entregue_por" required style="padding:0.4rem;">
                    </div>
                    <div>
                        <label style="font-weight:600; font-size:0.85rem; color:#475569;">Recebido por (Resp.)</label>
                        <input type="text" id="trans_recebido_por" required style="padding:0.4rem;">
                    </div>
                </div>
                <div>
                    <label style="font-weight:600; font-size:0.85rem; color:#475569;">Motivo da Transferência</label>
                    <input type="text" id="trans_motivo" required placeholder="Ex: Necessidade de serviço" style="padding:0.4rem;">
                </div>
                <div style="display:flex; gap:1rem; margin-top:0.5rem;">
                    <button type="button" class="btn btn-outline" style="flex:1" onclick="fecharTransferModal()">Cancelar</button>
                    <button type="submit" class="btn btn-blue" style="flex:1">Confirmar Transferência</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal de Estado Intermédio -->
    <div id="estadoModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1020; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:450px; max-width:90%;">
            <h3>🔄 Mudar Estado do Equipamento</h3>
            <div style="margin-top:1.5rem; display:flex; flex-direction:column; gap:1rem;">
                <div>
                    <label style="font-weight:600; font-size:0.85rem; color:#475569;">Equipamento (Guia)</label>
                    <input type="text" id="ee_guia" readonly style="background:#f1f5f9; color:#475569;">
                </div>
                <div>
                    <label style="font-weight:600; font-size:0.85rem; color:#475569;">Novo Estado Intermédio</label>
                    <select id="ee_estado">
                        {% for e in estados_intermedios %}<option value="{{e}}">{{e.replace('_',' ')}}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label style="font-weight:600; font-size:0.85rem; color:#475569;">Local Atual</label>
                    <input type="text" id="ee_local" placeholder="Ex: Embalagem, Transporte, Armazém..." style="margin-top:0.25rem;">
                </div>
                <div>
                    <label style="font-weight:600; font-size:0.85rem; color:#475569;">Observações (opcional)</label>
                    <input type="text" id="ee_obs" placeholder="Detalhes..." style="margin-top:0.25rem;">
                </div>
                <div style="display:flex; gap:1rem; margin-top:0.5rem;">
                    <button type="button" class="btn btn-outline" style="flex:1" onclick="document.getElementById('estadoModal').style.display='none'">Cancelar</button>
                    <button type="button" class="btn btn-blue" style="flex:1" onclick="guardarEstado()">Guardar Estado</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Modal de Rastreio -->
    <div id="rastreioModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1020; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:600px; max-width:95%; max-height:90vh; overflow-y:auto;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
                <h3>📦 Histórico / Rastreio do Equipamento</h3>
                <button type="button" class="btn btn-outline" onclick="document.getElementById('rastreioModal').style.display='none'" style="padding:0.4rem 0.8rem;">Fechar</button>
            </div>
            <div id="rastreio_content" style="display:flex; flex-direction:column; gap:0.75rem;">
            </div>
        </div>
    </div>

    <script>
        const allItems = {{ items|tojson }};
        let filteredItems = [...allItems];
        let currentPage = 1;
        const pageSize = 10;
        const selectedIds = new Set();

        function searchInvTable() {
            const query = document.getElementById("invSearchInput").value.toUpperCase();
            filteredItems = allItems.filter(item => {
                const text = `${item.equipamento} ${item.marca} ${item.numero_serie} ${item.status} ${item.setor_nome || ''}`.toUpperCase();
                return text.indexOf(query) > -1;
            });
            currentPage = 1;
            renderTable();
        }

        function renderTable() {
            const tbody = document.getElementById("invTableBody");
            tbody.innerHTML = "";
            
            const startIdx = (currentPage - 1) * pageSize;
            const endIdx = startIdx + pageSize;
            const pageItems = filteredItems.slice(startIdx, endIdx);
            
            if (pageItems.length === 0) {
                tbody.innerHTML = `<tr><td colspan="11" style="padding:1.5rem; text-align:center; color:#64748b;">Nenhum equipamento correspondente encontrado.</td></tr>`;
            } else {
                pageItems.forEach(item => {
                    let statusSpan = '';
                    if (item.status === 'Disponível') {
                        statusSpan = `<span style="background:#dcfce3; color:#166534; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">${item.status}</span>`;
                    } else if (item.status === 'Em uso') {
                        statusSpan = `<span style="background:#dbeafe; color:#1e40af; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">${item.status}</span>`;
                    } else {
                        statusSpan = `<span style="background:#fee2e2; color:#991b1b; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">${item.status}</span>`;
                    }
                    
                    const estadoLabel = (item.estado || 'EM_ESTOQUE').replace(/_/g, ' ');
                    const estadoSpan = `<span style="background:#e2e8f0; color:#334155; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.75rem; font-weight:600;">${estadoLabel}</span>`;
                    
                    const isChecked = selectedIds.has(item.id) ? 'checked' : '';
                    const actionSaida = (item.quantidade > 0 && item.status === 'Disponível') 
                        ? `<button onclick="abrirSaidaRapidaInventario(${item.id})" class="btn btn-green" style="padding:0.25rem 0.5rem; font-size:0.75rem; margin-top:0;">Saída</button>` 
                        : '';
                    const docLink = item.documento_pdf 
                        ? `<a href="/documentos/${item.documento_pdf}" target="_blank" title="Ver documento" style="text-decoration:none;">📄</a>` 
                        : '-';
                    const guiaExib = item.guia_origem || ('INV-' + item.id);
                        
                    const tr = document.createElement("tr");
                    tr.style.borderBottom = "1px solid var(--border)";
                    tr.innerHTML = `
                        <td style="padding:0.75rem;"><input type="checkbox" class="row-checkbox" value="${item.id}" data-qty="${item.quantidade}" ${isChecked} onclick="toggleSelectRow(this, ${item.id})"></td>
                        <td style="padding:0.75rem; font-weight: 600;">${item.equipamento}</td>
                        <td style="padding:0.75rem">${item.marca}</td>
                        <td style="padding:0.75rem; font-family: monospace;">${item.numero_serie}</td>
                        <td style="padding:0.75rem; text-align: center; font-weight: bold;">${item.quantidade}</td>
                        <td style="padding:0.75rem; color:#475569;">${item.setor_nome || '-'}</td>
                        <td style="padding:0.75rem; color:#1e40af;">${item.provincia_nome || '-'}</td>
                        <td style="padding:0.75rem">${estadoSpan}</td>
                        <td style="padding:0.75rem">${statusSpan}</td>
                        <td style="padding:0.75rem; text-align:center;">${docLink}</td>
                        <td style="padding:0.75rem; text-align: right; display:flex; gap:0.25rem; justify-content: flex-end; align-items: center; flex-wrap: wrap;">
                            ${actionSaida}
                            <button onclick="abrirEstadoModal(${item.id}, '${guiaExib}')" class="btn btn-outline" style="padding:0.25rem 0.5rem; font-size:0.75rem; margin-top:0;" title="Mudar estado intermédio">Estado</button>
                            <button onclick="verRastreio(${item.id}, 'inventario')" class="btn btn-outline" style="padding:0.25rem 0.5rem; font-size:0.75rem; margin-top:0;" title="Ver histórico/rastreio">Rastreio</button>
                            <button onclick="editarItemInventario(${item.id})" class="btn btn-outline" style="padding:0.25rem 0.5rem; font-size:0.75rem; margin-top:0;">Editar</button>
                            <form method="POST" action="/inventario/delete/${item.id}" style="display:inline;" onsubmit="return confirm('Deseja remover este item do inventário?');">
                                <button class="btn btn-danger" style="padding:0.25rem 0.5rem; font-size:0.75rem; margin-top:0;">Remover</button>
                            </form>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
            
            // Update indicator and buttons state
            const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
            document.getElementById("pageIndicator").innerText = `Página ${currentPage} de ${totalPages}`;
            document.getElementById("btnPrevPage").disabled = (currentPage === 1);
            document.getElementById("btnNextPage").disabled = (currentPage === totalPages);
        }

        function changePage(direction) {
            currentPage += direction;
            renderTable();
        }

        function toggleSelectAll(masterCheckbox) {
            const boxes = document.querySelectorAll(".row-checkbox");
            boxes.forEach(cb => {
                cb.checked = masterCheckbox.checked;
                const id = parseInt(cb.value);
                if (masterCheckbox.checked) {
                    selectedIds.add(id);
                } else {
                    selectedIds.delete(id);
                }
            });
        }

        function toggleSelectRow(checkbox, id) {
            if (checkbox.checked) {
                selectedIds.add(id);
            } else {
                selectedIds.delete(id);
            }
        }

        function apagarSelecionados() {
            if (selectedIds.size === 0) {
                alert("Nenhum item selecionado.");
                return;
            }
            if (!confirm(`Deseja realmente remover os ${selectedIds.size} itens selecionados?`)) return;
            
            fetch("/inventario/delete_multiple", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ ids: Array.from(selectedIds) })
            })
            .then(r => r.json())
            .then(res => {
                if (res.success) {
                    window.location.reload();
                } else {
                    alert("Erro ao remover: " + res.error);
                }
            });
        }

        function abrirTransferenciaMultiplos() {
            if (selectedIds.size === 0) {
                alert("Selecione pelo menos um equipamento.");
                return;
            }
            
            const container = document.getElementById("trans_items_container");
            container.innerHTML = "";
            
            selectedIds.forEach(id => {
                const item = allItems.find(x => x.id === id);
                if (item) {
                    const rowDiv = document.createElement("div");
                    rowDiv.style.display = "flex";
                    rowDiv.style.justifyContent = "space-between";
                    rowDiv.style.alignItems = "center";
                    rowDiv.style.padding = "0.25rem 0";
                    rowDiv.innerHTML = `
                        <span style="font-size:0.85rem; font-weight:600;">${item.equipamento} (${item.marca} - SN: ${item.numero_serie})</span>
                        <div style="display:flex; align-items:center; gap:0.5rem;">
                            <span style="font-size:0.75rem; color:#64748b;">(Qtd disp: ${item.quantidade})</span>
                            <input type="number" class="trans-qty" data-id="${item.id}" min="1" max="${item.quantidade}" value="1" style="width:60px; padding:0.2rem;">
                        </div>
                    `;
                    container.appendChild(rowDiv);
                }
            });
            
            document.getElementById("transferModal").style.display = "flex";
        }

        function fecharTransferModal() {
            document.getElementById("transferModal").style.display = "none";
        }

        function submeterTransferencia(e) {
            e.preventDefault();
            const sectorDestId = document.getElementById("trans_setor_destino_id").value;
            const entregue = document.getElementById("trans_entregue_por").value;
            const recebido = document.getElementById("trans_recebido_por").value;
            const motivo = document.getElementById("trans_motivo").value;
            
            const qtyInputs = document.querySelectorAll(".trans-qty");
            const quantities = {};
            for (let input of qtyInputs) {
                const id = input.getAttribute("data-id");
                const qtyVal = parseInt(input.value);
                const maxVal = parseInt(input.getAttribute("max"));
                if (qtyVal > maxVal) {
                    alert("A quantidade para transferir não pode exceder a quantidade disponível.");
                    return;
                }
                quantities[id] = qtyVal;
            }
            
            fetch("/inventario/movimentar_multiplos", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ids: Array.from(selectedIds),
                    quantities: quantities,
                    setor_destino_id: sectorDestId,
                    entregue_por: entregue,
                    recebido_por: recebido,
                    motivo: motivo
                })
            })
            .then(r => r.json())
            .then(res => {
                if (res.success) {
                    window.location.reload();
                } else {
                    alert("Erro na transferência: " + res.error);
                }
            });
        }

        function editarItemInventario(id) {
            const item = allItems.find(x => x.id === id);
            if (!item) return;
            document.getElementById('editInvForm').action = `/inventario/edit/${item.id}`;
            document.getElementById('ei_equipamento').value = item.equipamento;
            document.getElementById('ei_marca').value = item.marca;
            document.getElementById('ei_numero_serie').value = item.numero_serie;
            document.getElementById('ei_quantidade').value = item.quantidade;
            document.getElementById('ei_setor_id').value = item.setor_id || '';
            document.getElementById('ei_status').value = item.status;
            document.getElementById('ei_observacoes').value = item.observacoes || '';
            document.getElementById('editInvModal').style.display = 'flex';
        }

        function abrirSaidaRapidaInventario(id) {
            fetch(`/api/inventario_info/${id}`)
                .then(r => r.json())
                .then(item => {
                    document.getElementById('saidaRapidaInvForm').action = `/registrar_saida_inventario/${item.id}`;
                    document.getElementById('sri_inventario_id').value = item.id;
                    document.getElementById('sri_equipamento').value = item.equipamento;
                    document.getElementById('sri_marca').value = item.marca;
                    document.getElementById('sri_numero_serie').value = item.numero_serie;
                    document.getElementById('sri_qtd_disponivel').value = item.quantidade;
                    document.getElementById('sri_quantidade').max = item.quantidade;
                    document.getElementById('sri_quantidade').value = 1;

                    const selE = document.getElementById('sri_entregue');
                    const selR = document.getElementById('sri_recebido');
                    const selP = document.getElementById('sri_protecao');
                    
                    selE.innerHTML = '<option value="">-- Selecione quem entregou --</option>';
                    selR.innerHTML = '<option value="">-- Selecione quem recebeu --</option>';
                    selP.innerHTML = '<option value="">-- Opcional --</option>';
                    
                    fetch('/api/funcionarios').then(r=>r.json()).then(data=>{
                        data.forEach(f => {
                            const opt = `<option value="${f.id}">${f.nome} (${f.setor})</option>`;
                            selE.innerHTML += opt;
                            selR.innerHTML += opt;
                        });
                    });
                    
                    fetch('/api/usuarios_protecao').then(r=>r.json()).then(data=>{
                        data.forEach(u => {
                            const opt = `<option value="${u.nome}">${u.nome} (${u.info})</option>`;
                            selP.innerHTML += opt;
                        });
                    });

                    document.getElementById('saidaRapidaInvModal').style.display = 'flex';
                });
        }

        function fecharSaidaRapidaInv() {
            document.getElementById('saidaRapidaInvModal').style.display = 'none';
        }

        // Initial table load
        renderTable();

        // ---- Estado intermédio ----
        let estadoCurrentId = null;
        let estadoCurrentTipo = null;

        function abrirEstadoModal(id, guia) {
            estadoCurrentId = id;
            estadoCurrentTipo = 'inventario';
            document.getElementById('ee_guia').value = guia || ('INV-' + id);
            document.getElementById('ee_local').value = '';
            document.getElementById('ee_obs').value = '';
            document.getElementById('estadoModal').style.display = 'flex';
        }

        function guardarEstado() {
            const estado = document.getElementById('ee_estado').value;
            const local = document.getElementById('ee_local').value;
            const obs = document.getElementById('ee_obs').value;
            if (!estado) { alert('Selecione um estado.'); return; }
            fetch('/api/inventario/estado', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: estadoCurrentId, estado: estado, local_atual: local, obs: obs })
            })
            .then(r => r.json())
            .then(res => {
                if (res.success) {
                    document.getElementById('estadoModal').style.display = 'none';
                    window.location.reload();
                } else {
                    alert('Erro: ' + (res.error || 'Ocorreu um erro.'));
                }
            });
        }

        // ---- Rastreio ----
        function verRastreio(id, tipo) {
            const guia = (tipo === 'inventario') ? ('INV-' + id) : id;
            const item = allItems.find(x => x.id === id);
            const guiaReal = (item && item.guia_origem) ? item.guia_origem : guia;
            document.getElementById('rastreio_content').innerHTML = '<div style="color:#64748b;">A carregar histórico...</div>';
            document.getElementById('rastreioModal').style.display = 'flex';
            fetch(`/api/rastreio/${encodeURIComponent(guiaReal)}`)
                .then(r => r.json())
                .then(rows => {
                    const box = document.getElementById('rastreio_content');
                    if (!rows || rows.length === 0) {
                        box.innerHTML = '<div style="color:#64748b; text-align:center; padding:1rem;">Sem histórico registado para esta guia.</div>';
                        return;
                    }
                    let html = '';
                    rows.forEach(ev => {
                        html += `<div style="border-left: 3px solid #3b82f6; padding: 0.5rem 0.75rem; background: #f8fafc; border-radius: 0 0.375rem 0.375rem 0;">
                            <div style="display:flex; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                                <strong style="color:#1e293b; text-transform:capitalize;">${(ev.estado||'').replace(/_/g,' ')}</strong>
                                <span style="font-size:0.75rem; color:#64748b;">${ev.data || ''}</span>
                            </div>
                            <div style="font-size:0.85rem; color:#475569; margin-top:0.25rem;">${ev.local_atual ? '📍 ' + ev.local_atual : ''}</div>
                            ${ev.observacoes ? '<div style="font-size:0.8rem; color:#64748b; margin-top:0.25rem;">' + ev.observacoes + '</div>' : ''}
                            <div style="font-size:0.75rem; color:#94a3b8; margin-top:0.25rem;">por: ${ev.utilizador || '-'}</div>
                        </div>`;
                    });
                    box.innerHTML = html;
                })
                .catch(err => {
                    document.getElementById('rastreio_content').innerHTML = '<div style="color:#dc2626;">Erro ao carregar rastreio.</div>';
                });
        }
    </script>
</body></html>'''

@app.before_request
def auth():
    if request.path.startswith('/static'): return
    if request.path == '/login': return
    if 'username' not in session: return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error_msg = ""
    if request.method == 'POST':
        u = request.form.get('username', '').strip()
        p = request.form.get('password', '')
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT id, perfil, nome_completo, setor_id, eleitoral_local_id, password FROM users WHERE username=?", (u,))
            res = c.fetchone()
            valid = False
            if res:
                locais_acesso = ''
                try:
                    c.execute("SELECT locais_acesso FROM users WHERE id=?", (res[0],))
                    la = c.fetchone()
                    if la and la[0]:
                        locais_acesso = la[0]
                except Exception:
                    pass
                stored = res[5]
                if stored and ':' in stored and not stored.startswith('md5'):
                    valid = check_password_hash(stored, p)
                elif stored:
                    valid = hashlib.md5(p.encode()).hexdigest() == stored
                    if valid:
                        c.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(p), res[0]))
                        conn.commit()
            conn.close()
            if valid:
                session['username'] = u
                session['user_id'] = res[0]
                session['perfil'] = res[1]
                session['nome_completo'] = res[2] or u
                session['setor_id'] = res[3]
                session['eleitoral_local_id'] = res[4]
                session['locais_acesso'] = locais_acesso
                return redirect(url_for('index'))
            else:
                error_msg = f"<p style='color:red;'>Credenciais inválidas! BD: {'Nuvem' if is_cloud_mode() else 'Local'}<br>User digitado: '{u}'</p>"
        except Exception as e:
            error_msg = f"<p style='color:red;'>Erro BD: {str(e)}</p>"
    
    template = LOGIN_TEMPLATE
    if error_msg:
        template = template.replace('Faça login para continuar', error_msg)
    return render_template_string(template)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.before_request
def check_permissions():
    if request.endpoint in ('login', 'static', 'api_sync') or request.endpoint is None:
        return
        
    if 'username' not in session:
        return redirect(url_for('login'))
        
    admin_only_endpoints = [
        'cadastros', 'add_motivo', 'add_fornecedor', 'add_instituicao', 
        'add_marca', 'add_tipo', 'add_setor', 'add_funcionario', 'add_user',
        'edit_user', 'delete_user',
        'relatorios', 'relatorios_export', 'eliminar_movimento'
    ]
    
    if request.endpoint in admin_only_endpoints:
        if session.get('perfil') != 'admin':
            return "Erro: Acesso negado. Apenas administradores t&ecirc;m permiss&atilde;o para aceder a esta p&aacute;gina.", 403


def get_locais_acesso():
    """Devolve a lista de locais de inventário (setor_id) a que o utilizador
    pode aceder. Admin/None = todos os locais."""
    if session.get('perfil') == 'admin':
        return None
    raw = session.get('locais_acesso', '')
    if not raw:
        sid = session.get('setor_id')
        return [sid] if sid else []
    return [int(x) for x in raw.split(',') if x.strip().isdigit()]


MOVIMENTOS_TEMPLATE = """<!DOCTYPE html><html lang="pt"><head>""" + COMMON_HEAD + """<title>Todos os Movimentos - STAE</title>
<script>
    function searchTable() {
        var input = document.getElementById("searchInput");
        var filter = input.value.toUpperCase();
        var trs = document.querySelectorAll("#mainTable tr.mov-row");
        for (var i = 0; i < trs.length; i++) {
            var txtValue = trs[i].textContent || trs[i].innerText;
            if (txtValue.toUpperCase().indexOf(filter) > -1) {
                trs[i].style.display = "";
            } else {
                trs[i].style.display = "none";
                var det = document.getElementById("det_" + trs[i].dataset.index);
                if (det) det.style.display = "none";
            }
        }
    }
    function toggleDetails(id) {
        var el = document.getElementById(id);
        if (el.style.display === 'none' || el.classList.contains('hidden')) {
            el.style.display = 'table-row';
            el.classList.remove('hidden');
        } else {
            el.style.display = 'none';
        }
    }
</script>
</head>
<body>
    <div class="nav">
        <strong>STAE GESTÃO - TODOS OS MOVIMENTOS</strong>
        <div>
            <a href="/" class="btn btn-outline" style="background:white; color:#0f172a; margin-right:1rem">🏠 Voltar ao Início</a>
            <span>👤 {{session.username}}</span>
        </div>
    </div>
    <div class="container">
        <div class="card">
            <h3 style="margin-bottom:1rem">Registo Completo de Movimentos</h3>
            <input type="text" id="searchInput" onkeyup="searchTable()" placeholder="Pesquisar guia, equipamento, origem/destino, status..." style="width:100%; padding:0.8rem; border:1px solid #cbd5e1; border-radius:4px; margin-bottom:1rem">
            
            <table id="mainTable" style="width:100%; border-collapse:collapse; margin-top:1rem; font-size:0.9rem">
                <tr style="background:#f1f5f9; text-align:left; color:#64748b; font-size:0.8rem">
                    <th style="padding:1rem">GUIA</th>
                    <th style="padding:1rem">EQUIPAMENTO</th>
                    <th style="padding:1rem">S/N</th>
                    <th style="padding:1rem">ORIGEM</th>
                    <th style="padding:1rem">DESTINO</th>
                    <th style="padding:1rem">STATUS</th>
                    <th style="padding:1rem">DATA</th>
                    <th style="padding:1rem">ACÇÕES</th>
                </tr>
                {% for m in movimentos %}
                <tr class="mov-row" data-index="{{loop.index}}" style="border-bottom:1px solid var(--border)">
                    <td style="padding:1rem"><strong>{{m.guia[:8]}}</strong><br>{{m.guia[8:]}}</td>
                    <td style="padding:1rem">{{m.equipamento}}<br><small style="color:#64748b">({{m.marca}})</small></td>
                    <td style="padding:1rem">{{m.numero_serie}}</td>
                    <td style="padding:1rem">{% if m.tipo == 'ENTRADA' %}{{ m.origem_destino or m.setor_origem_nome or 'Inventário Directo' }}{% else %}{{ m.setor_origem_nome or m.local_origem or m.origem_destino or '-' }}{% endif %}</td>
                    <td style="padding:1rem">{% if m.tipo == 'SAIDA' %}{{ m.origem_destino or m.setor_destino_nome or m.local_destino or '-' }}{% else %}{{ m.setor_destino_nome or m.local_destino or 'Inventário Directo' }}{% endif %}</td>
                    <td style="padding:1rem">
                        {% if m.status == 'PENDENTE_RECEPCAO' %}
                            <span style="background:#fef3c7; color:#d97706; padding:0.2rem 0.5rem; border-radius:0.3rem; font-size:0.8rem; font-weight:bold;">Pendente Confirmação</span>
                        {% elif m.status == 'RECEBIDO' %}
                            <span style="background:#dcfce3; color:#166534; padding:0.2rem 0.5rem; border-radius:0.3rem; font-size:0.8rem; font-weight:bold;">Recebido</span>
                        {% elif m.status == 'REJEITADO' %}
                            <span style="background:#fee2e2; color:#b91c1c; padding:0.2rem 0.5rem; border-radius:0.3rem; font-size:0.8rem; font-weight:bold;">Rejeitado</span>
                        {% else %}
                            {{m.status}}
                        {% endif %}
                    </td>
                    <td style="padding:1rem">{{m.data[:10]}}<br><small style="color:#64748b">{{m.data[11:]}}</small></td>
                    <td style="padding:1rem; display:flex; gap:0.3rem; flex-wrap:wrap; align-items:center;">
                        <button onclick="toggleDetails('det_{{loop.index}}')" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem;">Detalhes</button>
                        <a href="/ver_guia/{{m.guia}}" target="_blank" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem;">PDF</a>
                        {% if m.status == 'PENDENTE_RECEPCAO' %}
                            {% if is_admin or m.setor_destino_id == meu_setor %}
                                <form method="POST" action="/confirmar_recepcao/{{m.guia}}" style="display:inline;"><button class="btn btn-green" style="padding:0.3rem 0.6rem; font-size:0.8rem;">✅ Confirmar</button></form>
                                <form method="POST" action="/rejeitar_recepcao/{{m.guia}}" style="display:inline;"><button class="btn btn-danger" style="padding:0.3rem 0.6rem; font-size:0.8rem;">❌ Rejeitar</button></form>
                            {% endif %}
                        {% endif %}
                    </td>
                </tr>
                <tr id="det_{{loop.index}}" class="hidden" style="background:#f8fafc; display:none;">
                    <td colspan="8" style="padding:1rem; border-bottom:1px solid var(--border)">
                        <div style="display:flex; gap:2rem; font-size:0.85rem; color:#475569; flex-wrap:wrap">
                            <div><strong>Motivo:</strong> {{m.motivo or '-'}}</div>
                            <div><strong>Técnico do Sistema:</strong> {{m.tecnico or '-'}}</div>
                            <div><strong>Fornecedor:</strong> {{m.fornecedor or '-'}}</div>
                            <div><strong>Quantidade:</strong> {{m.quantidade or '-'}}</div>
                            <div><strong>Entregue Por:</strong> {{m.entregue_nome or '-'}}</div>
                            <div><strong>Recebido Por:</strong> {{m.recebido_nome or '-'}}</div>
                            <div><strong>Agente de Protecção:</strong> {{m.protecao_nome or '-'}}</div>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
</body></html>"""


@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    msg = request.args.get('msg')
    
    setor_id = session.get('setor_id')
    is_admin = session.get('perfil') == 'admin'
    
    if is_admin:
        c.execute("SELECT * FROM movimentos ORDER BY id DESC LIMIT 50")
    else:
        locais = get_locais_acesso() or [0]
        ph = ','.join('?' * len(locais))
        c.execute(f"SELECT * FROM movimentos WHERE setor_origem_id IN ({ph}) OR setor_destino_id IN ({ph}) ORDER BY id DESC LIMIT 50", locais + locais)
    
    cols = [d[0] for d in c.description]
    movimentos = [dict(zip(cols, r)) for r in c.fetchall()]
    
    c.execute("SELECT id, nome FROM funcionarios")
    func_map = {str(r[0]): r[1] for r in c.fetchall()}
    c.execute("SELECT id, nome FROM setores")
    setor_map = {int(r[0]): r[1] for r in c.fetchall()}
    
    for m in movimentos:
        m['entregue_nome'] = func_map.get(str(m.get('entregue_por')), m.get('entregue_por') or '-')
        m['recebido_nome'] = func_map.get(str(m.get('recebido_por')), m.get('recebido_por') or '-')
        m['protecao_nome'] = func_map.get(str(m.get('agente_protecao')), m.get('agente_protecao') or '-')
        so = m.get('setor_origem_id')
        sd = m.get('setor_destino_id')
        m['setor_origem_nome'] = setor_map.get(int(so), '') if so else ''
        m['setor_destino_nome'] = setor_map.get(int(sd), '') if sd else ''
        
    # Fetch pending receptions
    pendentes = []
    if not is_admin and setor_id:
        c.execute("SELECT * FROM movimentos WHERE setor_destino_id=? AND status='PENDENTE_RECEPCAO' ORDER BY id DESC", (setor_id,))
        if c.description:
            p_cols = [d[0] for d in c.description]
            pendentes = [dict(zip(p_cols, r)) for r in c.fetchall()]
    elif is_admin:
        c.execute("SELECT * FROM movimentos WHERE status='PENDENTE_RECEPCAO' ORDER BY id DESC")
        if c.description:
            p_cols = [d[0] for d in c.description]
            pendentes = [dict(zip(p_cols, r)) for r in c.fetchall()]
            
    if is_admin:
        c.execute("SELECT id, equipamento, marca, numero_serie, quantidade FROM inventario_local WHERE status!='Pendente' ORDER BY equipamento")
    else:
        locais = get_locais_acesso() or [0]
        ph = ','.join('?' * len(locais))
        c.execute(f"SELECT id, equipamento, marca, numero_serie, quantidade FROM inventario_local WHERE setor_id IN ({ph}) AND status!='Pendente' ORDER BY equipamento", locais)
    inv_items = []
    if c.description:
        inv_cols = [d[0] for d in c.description]
        inv_items = [dict(zip(inv_cols, r)) for r in c.fetchall()]
        
    c.execute("SELECT id, nome FROM setores")
    setores = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM marcas")
    marcas = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM tipos_equipamento")
    tipos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM motivos")
    motivos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM fornecedores")
    fornecedores = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM instituicoes")
    instituicoes = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    
    # Nome do setor do usuario (para mostrar origem automatica)
    meu_setor_nome = 'DDGEI'
    if setor_id:
        for s in setores:
            if s['id'] == setor_id:
                meu_setor_nome = s['nome']
                break
    
    c.execute("SELECT COUNT(*) FROM movimentos WHERE tipo='ENTRADA' AND status LIKE '%repara%'")
    row_count = c.fetchone()
    em_reparacao = row_count[0] if row_count else 0
    
    conn.close()
    return render_template_string(MAIN_TEMPLATE, msg=msg, username=session['username'], perfil=session.get('perfil'), movimentos=movimentos, pendentes=pendentes, inv_items=inv_items, setores=setores, marcas=marcas, tipos=tipos, motivos=motivos, fornecedores=fornecedores, instituicoes=instituicoes, em_reparacao=em_reparacao, meu_setor_id=setor_id, meu_setor_nome=meu_setor_nome)


@app.route('/movimentos')
def movimentos():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    setor_id = session.get('setor_id')
    is_admin = session.get('perfil') == 'admin'
    
    if is_admin:
        c.execute("SELECT * FROM movimentos ORDER BY id DESC")
    else:
        locais = get_locais_acesso() or [0]
        ph = ','.join('?' * len(locais))
        c.execute(f"SELECT * FROM movimentos WHERE setor_origem_id IN ({ph}) OR setor_destino_id IN ({ph}) ORDER BY id DESC", locais + locais)
        
    cols = [d[0] for d in c.description]
    movs = [dict(zip(cols, r)) for r in c.fetchall()]
    
    c.execute("SELECT id, nome FROM funcionarios")
    func_map = {str(r[0]): r[1] for r in c.fetchall()}
    
    c.execute("SELECT id, nome FROM setores")
    setor_map = {int(r[0]): r[1] for r in c.fetchall()}
    
    for m in movs:
        m['entregue_nome'] = func_map.get(str(m.get('entregue_por')), m.get('entregue_por') or '-')
        m['recebido_nome'] = func_map.get(str(m.get('recebido_por')), m.get('recebido_por') or '-')
        m['protecao_nome'] = func_map.get(str(m.get('agente_protecao')), m.get('agente_protecao') or '-')
        so = m.get('setor_origem_id')
        sd = m.get('setor_destino_id')
        m['setor_origem_nome'] = setor_map.get(int(so), '') if so else ''
        m['setor_destino_nome'] = setor_map.get(int(sd), '') if sd else ''
        
    conn.close()
    return render_template_string(MOVIMENTOS_TEMPLATE, movimentos=movs, meu_setor=setor_id, is_admin=is_admin)

@app.route('/api/funcionarios')
def api_funcionarios():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT f.id, f.nome, s.nome FROM funcionarios f LEFT JOIN setores s ON f.setor_id = s.id")
    data = [{'id':r[0], 'nome':r[1], 'setor':r[2] or ''} for r in c.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/api/usuarios_protecao')
def api_usuarios_protecao():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Load users with profile 'protecao'
    c.execute("SELECT id, nome_completo, username FROM users WHERE perfil='protecao'")
    users = [{'nome': r[1] or r[2], 'info': f"Utilizador ({r[2]})"} for r in c.fetchall()]
    
    # Load employees in a sector that contains 'prote'
    try:
        c.execute("SELECT f.nome, s.nome FROM funcionarios f JOIN setores s ON f.setor_id = s.id WHERE s.nome LIKE '%prote%'")
        employees = [{'nome': r[0], 'info': f"Funcionário ({r[1]})"} for r in c.fetchall()]
    except:
        employees = []
        
    data = users + employees
    conn.close()
    return jsonify(data)

@app.route('/api/equipamentos_reparacao')
def api_equipamentos_reparacao():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT m.guia, m.equipamento, m.marca, m.numero_serie, m.origem_destino, m.data, m.status FROM movimentos m WHERE m.tipo='ENTRADA' AND m.status LIKE '%repara%' ORDER BY m.id DESC")
    rows = c.fetchall()
    data = [{'guia': r[0], 'equipamento': r[1], 'marca': r[2], 'numero_serie': r[3], 'origem_destino': r[4], 'data': r[5], 'status': r[6]} for r in rows]
    conn.close()
    return jsonify(data)

@app.route('/documentos/<path:nome>')
def servir_documento(nome):
    if 'username' not in session: return redirect(url_for('login'))
    nome = os.path.basename(nome)
    caminho = os.path.join(UPLOAD_FOLDER, nome)
    if not os.path.exists(caminho):
        return "Documento não encontrado", 404
    return send_file(caminho, mimetype='application/pdf')

@app.route('/api/buscar_barcode')
def api_buscar_barcode():
    if 'username' not in session: return jsonify({'error': 'Não logado'}), 401
    codigo = request.args.get('codigo', '').strip()
    if not codigo:
        return jsonify({'error': 'Código de barras vazio'}), 400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, i.codigo_barras, i.local_uso, i.estado, s.nome as setor_nome 
                 FROM inventario_local i LEFT JOIN setores s ON i.setor_id = s.id 
                 WHERE i.codigo_barras = ?''', (codigo,))
    cols = [d[0] for d in c.description]
    row = c.fetchone()
    if row:
        conn.close()
        return jsonify({'tipo': 'inventario', 'item': dict(zip(cols, row))})
    c.execute("SELECT guia, tipo, equipamento, marca, numero_serie, quantidade, status, origem_destino, data, estado_rastreio, documento_pdf FROM movimentos WHERE codigo_barras = ? ORDER BY id DESC", (codigo,))
    cols2 = [d[0] for d in c.description]
    row2 = c.fetchone()
    conn.close()
    if row2:
        return jsonify({'tipo': 'movimento', 'item': dict(zip(cols2, row2))})
    return jsonify({'error': 'Nenhum equipamento encontrado com esse código de barras'}), 404

@app.route('/api/movimento/estado', methods=['POST'])
def api_movimento_estado():
    if 'username' not in session: return jsonify({'error': 'Não logado'}), 401
    data = request.get_json() or {}
    guia = data.get('guia')
    estado = data.get('estado')
    obs = data.get('obs', '')
    if not guia or not estado:
        return jsonify({'error': 'Guia e estado são obrigatórios'}), 400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Controlo de permissoes: admin pode qualquer estado; os demais usam as permissoes configuradas
    # pelo admin no cadastro do usuario (permissoes_estado). Se vazio, regra por setor:
    # origem marca preparacao/empacotamento/espera/envio; destino marca recebido.
    c.execute("SELECT setor_origem_id, setor_destino_id FROM movimentos WHERE guia=?", (guia,))
    mov = c.fetchone()
    if not mov:
        conn.close()
        return jsonify({'error': 'Movimento nao encontrado'}), 404
    setor_origem_id, setor_destino_id = mov
    meu_setor = session.get('setor_id')
    is_admin = session.get('perfil') == 'admin'
    estados_origem = ['EM_PREPARACAO', 'EMPACOTAMENTO', 'A_ESPERA_ENVIO', 'ENVIADO']
    estados_destino = ['RECEBIDO']
    c.execute("SELECT permissoes_estado FROM users WHERE id=?", (session.get('user_id'),))
    up = c.fetchone()
    user_perm = []
    if up and up[0]:
        user_perm = [s.strip() for s in up[0].split(',') if s.strip()]
    permitido = False
    if is_admin:
        permitido = True
    elif user_perm:
        permitido = estado in user_perm
    else:
        if estado in estados_origem and setor_origem_id == meu_setor:
            permitido = True
        elif estado in estados_destino and setor_destino_id == meu_setor:
            permitido = True
    if not permitido:
        conn.close()
        return jsonify({'error': 'Sem permissao para alterar este estado'}), 403
    c.execute("UPDATE movimentos SET estado_rastreio=? WHERE guia=?", (estado, guia))
    c.execute('''INSERT INTO equipamento_rastreio (guia, equipamento, numero_serie, estado, local_atual, observacoes, data, utilizador) 
                 SELECT ?, equipamento, numero_serie, ?, ?, ?, ?, ? FROM movimentos WHERE guia=?''',
              (guia, estado, data.get('local') or data.get('local_atual', ''), obs, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get('nome_completo', session.get('username', '')), guia))
    try:
        c.execute('''INSERT INTO equipamento_estado_historico (guia, equipamento, numero_serie, estado, observacoes, data, utilizador) 
                     SELECT ?, equipamento, numero_serie, ?, ?, ?, ? FROM movimentos WHERE guia=?''',
                  (guia, estado, obs, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get('nome_completo', session.get('username', '')), guia))
    except Exception:
        pass
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'estado': estado})

@app.route('/api/inventario/estado', methods=['POST'])
def api_inventario_estado():
    if 'username' not in session: return jsonify({'error': 'Não logado'}), 401
    data = request.get_json() or {}
    item_id = data.get('id')
    estado = data.get('estado')
    if not item_id or not estado:
        return jsonify({'error': 'ID e estado são obrigatórios'}), 400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE inventario_local SET estado=? WHERE id=?", (estado, item_id))
    c.execute('''INSERT INTO equipamento_rastreio (guia, equipamento, numero_serie, estado, local_atual, observacoes, data, utilizador) 
                 SELECT COALESCE(guia_origem, 'INV-' || ?), equipamento, numero_serie, ?, ?, ?, ?, ? FROM inventario_local WHERE id=?''',
              (item_id, estado, data.get('local_atual', ''), data.get('obs', ''), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get('nome_completo', session.get('username', '')), item_id))
    try:
        c.execute('''INSERT INTO equipamento_estado_historico (guia, equipamento, numero_serie, estado, observacoes, data, utilizador) 
                     SELECT COALESCE(guia_origem, 'INV-' || ?), equipamento, numero_serie, ?, ?, ?, ? FROM inventario_local WHERE id=?''',
                  (item_id, estado, data.get('obs', ''), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get('nome_completo', session.get('username', '')), item_id))
    except Exception:
        pass
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'estado': estado})


@app.route('/movimentar_provincia', methods=['POST'])
def movimentar_provincia():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    prov_origem_id = request.form.get('provincia_origem_id')
    prov_destino_id = request.form.get('provincia_destino_id')
    prov_origem = int(prov_origem_id) if prov_origem_id else None
    prov_destino = int(prov_destino_id) if prov_destino_id else None
    if not prov_origem or not prov_destino:
        conn.close()
        flash("Erro: selecione a província de origem e de destino.")
        return redirect(url_for('inventario'))
    if prov_origem == prov_destino:
        conn.close()
        flash("Erro: a província de origem e de destino devem ser diferentes.")
        return redirect(url_for('inventario'))

    def nome_prov(idp):
        try:
            r = c.execute("SELECT nome FROM eleitoral_provincia WHERE id=?", (idp,)).fetchone()
            return r[0] if r else f"Província {idp}"
        except Exception:
            return f"Província {idp}"

    nome_origem = nome_prov(prov_origem)
    nome_destino = nome_prov(prov_destino)

    equipamento = request.form.get('equipamento', '')
    marca = request.form.get('marca', '')
    numero_serie = request.form.get('numero_serie', '')
    quantidade = int(request.form.get('quantidade', 1) or 1)
    motivo = request.form.get('motivo', '')
    inv_id = request.form.get('inventario_id')
    codigo_barras = request.form.get('codigo_barras', '').strip()
    guia = f"TRANSF-{datetime.now().year}-{len(c.execute('SELECT id FROM movimentos').fetchall())+1:04d}"
    estado = request.form.get('estado', 'EM_PREPARACAO') or 'EM_PREPARACAO'

    # valida stock e decrementa na origem se vier do inventário
    if inv_id:
        c.execute("SELECT quantidade FROM inventario_local WHERE id=?", (inv_id,))
        r = c.fetchone()
        if r and int(r[0]) >= quantidade:
            novo = int(r[0]) - quantidade
            ns = 'Disponível' if novo > 0 else 'Indisponível'
            c.execute("UPDATE inventario_local SET quantidade=?, status=?, estado=? WHERE id=?", (novo, ns, estado, inv_id))
        else:
            conn.close()
            flash("Erro: quantidade excede o stock disponível na origem.")
            return redirect(url_for('inventario'))

    c.execute('''INSERT INTO movimentos (guia, tipo, equipamento, origem_destino, motivo, data, status, tecnico, numero_serie, marca, quantidade, setor_origem_id, setor_destino_id, provincia_origem_id, provincia_destino_id, local_origem, local_destino, estado_rastreio, codigo_barras, documento_pdf) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (guia, "TRANSFERENCIA", equipamento, f"{nome_origem} -> {nome_destino}", motivo, datetime.now().strftime("%Y-%m-%d"), "PENDENTE_RECEPCAO", session.get('nome_completo', session.get('username', 'tecnico')), numero_serie, marca, str(quantidade), None, None, prov_origem, prov_destino, request.form.get('local_origem', ''), request.form.get('local_destino', ''), estado, codigo_barras, None))

    # regista no inventário do destino como pendente (não disponível até confirmar)
    c.execute("SELECT id, quantidade FROM inventario_local WHERE provincia_id=? AND equipamento=? AND numero_serie=? AND marca=?", (prov_destino, equipamento, numero_serie, marca))
    inv_dest = c.fetchone()
    if inv_dest:
        c.execute("UPDATE inventario_local SET quantidade=quantidade+?, status='Pendente', estado=?, guia_origem=? WHERE id=?", (quantidade, estado, guia, inv_dest[0]))
    else:
        c.execute("INSERT INTO inventario_local (equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, provincia_id, estado, guia_origem, codigo_barras, local_uso) VALUES (?,?,?,?,'Pendente',?,?,?,?,?,?,?)",
                  (equipamento, marca, numero_serie, quantidade, datetime.now().strftime("%Y-%m-%d"), request.form.get('local_destino', ''), prov_destino, estado, guia, codigo_barras, request.form.get('local_destino', '')))

    # histórico de rastreio
    c.execute('''INSERT INTO equipamento_rastreio (guia, equipamento, numero_serie, estado, local_atual, observacoes, data, utilizador) VALUES (?,?,?,?,?,?,?,?)''',
              (guia, equipamento, numero_serie, estado, request.form.get('local_origem', ''), f"Enviado de {nome_origem} para {nome_destino}. Motivo: {motivo}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get('nome_completo', session.get('username', ''))))
    # histórico de estados intermédios
    try:
        c.execute('''INSERT INTO equipamento_estado_historico (guia, equipamento, numero_serie, estado, observacoes, data, utilizador) VALUES (?,?,?,?,?,?,?)''',
                  (guia, equipamento, numero_serie, estado, f"Enviado de {nome_origem} para {nome_destino}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get('nome_completo', session.get('username', ''))))
    except Exception:
        pass
    conn.commit()
    conn.close()
    flash("Equipamento movimentado entre províncias! Aguarda confirmação no destino.")
    return redirect(url_for('inventario'))


@app.route('/confirmar_recepcao_provincia/<int:item_id>', methods=['POST'])
def confirmar_recepcao_provincia(item_id):
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT equipamento, marca, numero_serie, quantidade, provincia_id, estado, guia_origem FROM inventario_local WHERE id=? AND status='Pendente'", (item_id,))
    inv = c.fetchone()
    if inv:
        equipamento, marca, numero_serie, quantidade, provincia_id, estado, guia = inv
        c.execute("SELECT id, quantidade FROM inventario_local WHERE provincia_id=? AND equipamento=? AND numero_serie=? AND marca=? AND id != ?", (provincia_id, equipamento, numero_serie, marca, item_id))
        existing = c.fetchone()
        if existing:
            c.execute("UPDATE inventario_local SET quantidade=quantidade+?, status='Disponível', estado='EM_ESTOQUE' WHERE id=?", (quantidade, existing[0]))
            c.execute("DELETE FROM inventario_local WHERE id=?", (item_id,))
        else:
            c.execute("UPDATE inventario_local SET status='Disponível', estado='EM_ESTOQUE', guia_origem=NULL WHERE id=?", (item_id,))
        if guia:
            c.execute("UPDATE movimentos SET status='RECEBIDO', estado_rastreio='RECEBIDO', confirmado_destino=? WHERE guia=?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), guia))
            c.execute('''INSERT INTO equipamento_rastreio (guia, equipamento, numero_serie, estado, local_atual, observacoes, data, utilizador) VALUES (?,?,?,?,?,?,?,?)''',
                      (guia, equipamento, numero_serie, 'RECEBIDO', 'Destino', 'Receção confirmada no destino. Quantidade atualizada.', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get('nome_completo', session.get('username', ''))))
            try:
                c.execute('''INSERT INTO equipamento_estado_historico (guia, equipamento, numero_serie, estado, observacoes, data, utilizador) VALUES (?,?,?,?,?,?,?)''',
                          (guia, equipamento, numero_serie, 'RECEBIDO', 'Receção confirmada no destino', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get('nome_completo', session.get('username', ''))))
            except Exception:
                pass
        conn.commit()
        flash("Receção confirmada no destino! Quantidade atualizada.")
    conn.close()
    return redirect(url_for('inventario'))


@app.route('/api/rastreio/<guia>')
def api_rastreio(guia):
    if 'username' not in session: return jsonify({'error': 'Não logado'}), 401
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, guia, equipamento, numero_serie, estado, local_atual, observacoes, data, utilizador FROM equipamento_rastreio WHERE guia=? ORDER BY id ASC", (guia,))
    cols = [d[0] for d in c.description]
    rows = [dict(zip(cols, r)) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route('/api/update_status/<guia>', methods=['POST'])
def api_update_status(guia):
    status = request.json.get('status')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE movimentos SET status=? WHERE guia=?", (status, guia))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/movimento_info/<guia>')
def api_movimento_info(guia):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM movimentos WHERE guia=?", (guia,))
    cols = [d[0] for d in c.description]
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Movimento não encontrado'}), 404
    return jsonify(dict(zip(cols, row)))

@app.route('/registrar_entrada', methods=['POST'])
def registrar_entrada():
    entregue_por = request.form.get('entregue_por', '').strip()
    recebido_por = request.form.get('recebido_por', '').strip()
    if not entregue_por or not recebido_por:
        flash("Erro: É obrigatório indicar quem entregou e quem recebeu (funcionários).")
        return redirect(url_for('index'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    guia = f"ENT-{datetime.now().year}-{len(c.execute('SELECT id FROM movimentos').fetchall())+1:04d}"
    
    modo_inventario = request.form.get('modo_inventario') == '1'
    origem_raw = request.form.get('origem', '').strip()
    
    if modo_inventario:
        destino_inv = request.form.get('destino_inventario', '').strip()
        if not destino_inv:
            flash("Erro: Em modo inventário é obrigatório indicar o local de destino.")
            conn.close()
            return redirect(url_for('index'))
        setor_destino_id = int(destino_inv)
        setor_origem_id = None
        if origem_raw.startswith("SETOR_"):
            setor_origem_id = int(origem_raw.split("_")[1])
        origem_destino = origem_raw if origem_raw else "Inventário Directo"
    else:
        setor_destino_id = session.get('setor_id')
        setor_origem_id = None
        origem_destino = origem_raw
        if not origem_destino:
            flash("Erro: É obrigatório indicar a origem do equipamento.")
            conn.close()
            return redirect(url_for('index'))
    
    codigo_barras = request.form.get('codigo_barras', '').strip()
    documento_pdf = None
    if 'documento' in request.files:
        f = request.files['documento']
        if f and f.filename:
            ext = os.path.splitext(f.filename)[1].lower()
            nome_base = f"ENT_DOC_{guia}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'):
                documento_pdf = imagem_para_pdf(f, nome_base)
            elif ext == '.pdf':
                nome = f"{nome_base}.pdf"
                caminho = os.path.join(UPLOAD_FOLDER, nome)
                f.save(caminho)
                documento_pdf = nome
    
    numero_serie = request.form.get('numero_serie', '').strip()
    motivo_entrada = request.form.get('motivo', '')
    if 'repara' in motivo_entrada.lower() and (not numero_serie or numero_serie.upper() in ('N/A', 'NA', 'N/D', '-')):
        numero_serie = guia
        flash("Atenção: equipamento sem número de série. Foi registado o nº da guia de entrada como identificador.")
    departamento_raw = request.form.get('departamento_responsavel_id', '').strip()
    try:
        departamento_responsavel_id = int(departamento_raw) if departamento_raw else (session.get('setor_id') or setor_destino_id)
    except (TypeError, ValueError):
        departamento_responsavel_id = session.get('setor_id') or setor_destino_id
    c.execute('''INSERT INTO movimentos (guia, tipo, equipamento, origem_destino, motivo, data, status, funcionario_id, numero_serie, marca, entregue_por, recebido_por, tecnico, agente_protecao, fornecedor, quantidade, setor_origem_id, setor_destino_id, codigo_barras, documento_pdf, estado_rastreio, departamento_responsavel_id) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
              (guia, "ENTRADA", request.form['equipamento'], origem_destino, motivo_entrada, datetime.now().strftime("%Y-%m-%d"), "Em estoque", None, numero_serie, request.form.get('marca',''), entregue_por, recebido_por, session.get('nome_completo', session.get('username', 'tecnico')), request.form.get('agente_protecao',''), request.form.get('fornecedor', 'N/A'), request.form.get('quantidade', '1'), setor_origem_id, setor_destino_id, codigo_barras, documento_pdf, 'EM_ESTOQUE', departamento_responsavel_id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/registrar_saida', methods=['POST'])
def registrar_saida():
    if 'username' not in session: return redirect(url_for('login'))
    entregue_por = request.form.get('entregue_por', '').strip()
    recebido_por = request.form.get('recebido_por', '').strip()
    if not entregue_por or not recebido_por:
        flash("Erro: É obrigatório indicar quem entregou e quem recebeu (funcionários).")
        return redirect(url_for('index'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    destino_raw = request.form['destino']
    setor_destino_id = None
    origem_destino = destino_raw
    if destino_raw.startswith("SETOR_"):
        setor_destino_id = int(destino_raw.split("_")[1])
        c.execute("SELECT nome FROM setores WHERE id=?", (setor_destino_id,))
        row = c.fetchone()
        origem_destino = "Interno - " + row[0] if row else destino_raw
    elif destino_raw.startswith("EXTERNO_"):
        origem_destino = "Externo - " + destino_raw.split("_", 1)[1]
        
    # Origem: admin pode selecionar; nao-admin usa o setor do usuario
    origem_raw = request.form.get('origem', '')
    setor_origem_id = None
    if origem_raw.startswith("SETOR_"):
        setor_origem_id = int(origem_raw.split("_")[1])
    else:
        setor_origem_id = session.get('setor_id')
    # Estado de saida
    estado_saida = request.form.get('estado_saida', 'EM_PREPARACAO')
    qty_to_remove = int(request.form.get('quantidade', 1))
    
    inv_id = request.form.get('inventario_id')
    if inv_id:
        try:
            c.execute("SELECT quantidade FROM inventario_local WHERE id=?", (inv_id,))
            row = c.fetchone()
            if row:
                current_qty = int(row[0])
                if current_qty < qty_to_remove:
                    flash("Erro: Quantidade excede o disponvel em stock!")
                    conn.close()
                    return redirect(url_for('index'))
                new_qty = current_qty - qty_to_remove
                new_status = 'Disponível' if new_qty > 0 else 'Indisponível'
                c.execute("UPDATE inventario_local SET quantidade=?, status=? WHERE id=?", (new_qty, new_status, inv_id))
        except Exception as e:
            print(f"Erro ao atualizar inventrio: {e}")
            
    guia = f"SAI-{datetime.now().year}-{len(c.execute('SELECT id FROM movimentos').fetchall())+1:04d}"
    status_movimento = "PENDENTE_RECEPCAO" if setor_destino_id else "Entregue"
    
    departamento_raw = request.form.get('departamento_responsavel_id', '').strip()
    try:
        departamento_responsavel_id = int(departamento_raw) if departamento_raw else (session.get('setor_id') or setor_origem_id)
    except (TypeError, ValueError):
        departamento_responsavel_id = session.get('setor_id') or setor_origem_id
    
    c.execute('''INSERT INTO movimentos (guia, tipo, equipamento, origem_destino, motivo, data, status, funcionario_id, numero_serie, marca, entregue_por, recebido_por, tecnico, agente_protecao, fornecedor, quantidade, setor_origem_id, setor_destino_id, estado_rastreio, departamento_responsavel_id) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
              (guia, "SAIDA", request.form['equipamento'], origem_destino, request.form.get('motivo',''), datetime.now().strftime("%Y-%m-%d"), status_movimento, None, request.form['numero_serie'], request.form.get('marca',''), entregue_por, recebido_por, session.get('nome_completo', session.get('username', 'tecnico')), request.form.get('agente_protecao',''), request.form.get('fornecedor', 'N/A'), str(qty_to_remove), setor_origem_id, setor_destino_id, estado_saida, departamento_responsavel_id))
    conn.commit()
    conn.close()
    flash("Saída registada com sucesso!")
    return redirect(url_for('index'))

@app.route('/registrar_saida_reparacao/<original_guia>', methods=['POST'])
def registrar_saida_reparacao(original_guia):
    if 'username' not in session: return redirect(url_for('login'))
    entregue_por = request.form.get('entregue_por', '').strip()
    recebido_por = request.form.get('recebido_por', '').strip()
    if not entregue_por or not recebido_por:
        flash("Erro: É obrigatório indicar quem entregou e quem recebeu (funcionários).")
        return redirect(url_for('index'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT id FROM movimentos WHERE guia=?", (original_guia,))
    original = c.fetchone()
    if not original:
        conn.close()
        return "Movimento original não encontrado", 404
    
    c.execute("SELECT numero_serie FROM movimentos WHERE guia=?", (original_guia,))
    row_sn = c.fetchone()
    numero_serie_original = row_sn[0] if row_sn else ''
    # A guia de saída é uma variante da guia de entrada (guia de entrada mantém-se como identificador)
    guia_saida = f"{original_guia}-SAI"
    
    equipamento = request.form.get('equipamento')
    marca = request.form.get('marca')
    numero_serie = request.form.get('numero_serie')
    if numero_serie_original == original_guia:
        numero_serie = numero_serie_original
    destino = request.form.get('destino')
    motivo = request.form.get('motivo', '')
    fornecedor = request.form.get('fornecedor', 'N/A')
    quantidade = request.form.get('quantidade', '1')
    if quantidade in (None, '', 'None') or str(quantidade).strip() == '':
        quantidade_txt = '1'
    else:
        try:
            quantidade_txt = str(int(quantidade))
        except (ValueError, TypeError):
            quantidade_txt = '1'
    
    agente_protecao = request.form.get('agente_protecao', '')

    dep_repar_raw = request.form.get('departamento_responsavel_id', '').strip()
    try:
        dep_repar = int(dep_repar_raw) if dep_repar_raw else (session.get('setor_id'))
    except (TypeError, ValueError):
        dep_repar = session.get('setor_id')
    
    c.execute('''INSERT INTO movimentos (guia, tipo, equipamento, origem_destino, motivo, data, status, funcionario_id, numero_serie, marca, entregue_por, recebido_por, tecnico, agente_protecao, fornecedor, quantidade, setor_origem_id, setor_destino_id, estado_rastreio, departamento_responsavel_id) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
              (guia_saida, "SAIDA", equipamento, destino, motivo, datetime.now().strftime("%Y-%m-%d"), "Entregue", None, numero_serie, marca, entregue_por, recebido_por, session.get('nome_completo', session.get('username', 'tecnico')), agente_protecao, fornecedor, quantidade_txt, session.get('setor_id'), None, 'EM_ESTOQUE', dep_repar))
              
    novo_status = request.form.get('novo_status', 'Reparado e Entregue')
    c.execute("UPDATE movimentos SET status=? WHERE guia=?", (novo_status, original_guia))
    
    conn.commit()
    conn.close()
    return redirect(url_for('index', msg=f"Saída registada com sucesso! Guia de Saída: {guia_saida}"))

@app.route('/cadastros')
def cadastros():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, nome FROM setores")
    setores = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome, cargo, setor_id FROM funcionarios")
    funcs = [{'id':r[0], 'nome':r[1], 'cargo':r[2], 'setor_id':r[3]} for r in c.fetchall()]
    c.execute("SELECT id, username, perfil, nome_completo, setor_id, eleitoral_local_id, permissoes_estado, locais_acesso FROM users")
    users_data = [{'id':r[0], 'username':r[1], 'perfil':r[2], 'nome_completo':r[3] or r[1], 'setor_id':r[4], 'eleitoral_local_id': r[5], 'permissoes_estado': r[6] or '', 'locais_acesso': r[7] or ''} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM marcas")
    marcas = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM tipos_equipamento")
    tipos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM motivos")
    motivos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM fornecedores")
    fornecedores = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM instituicoes")
    instituicoes = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    
    # Eleitoral locais
    c.execute("SELECT id, tipo, nome FROM eleitoral_local_armazenamento WHERE activo=1")
    eleitoral_locais = [{'id':r[0], 'tipo':r[1], 'nome':r[2]} for r in c.fetchall()]
    
    conn.close()
    return render_template_string(CADASTROS_TEMPLATE, setores=setores, funcionarios=funcs, users_list=users_data, marcas=marcas, tipos=tipos, motivos=motivos, fornecedores=fornecedores, instituicoes=instituicoes, eleitoral_locais=eleitoral_locais, msg=request.args.get('msg'))



@app.route('/add_motivo', methods=['POST'])
def add_motivo():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO motivos (nome) VALUES (?)", (request.form['nome'],))
        conn.commit()
    except: pass
    conn.close()
    return redirect(url_for('cadastros', msg="Motivo adicionado com sucesso!"))

@app.route('/edit_motivo/<int:id>', methods=['POST'])
def edit_motivo(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE motivos SET nome=? WHERE id=?", (request.form['nome'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Motivo atualizado!"))


@app.route('/add_fornecedor', methods=['POST'])
def add_fornecedor():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try: c.execute("INSERT INTO fornecedores (nome) VALUES (?)", (request.form['nome'],)); conn.commit()
    except: pass
    conn.close()
    return redirect(url_for('cadastros', msg="Fornecedor adicionado!"))

@app.route('/add_instituicao', methods=['POST'])
def add_instituicao():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try: c.execute("INSERT INTO instituicoes (nome) VALUES (?)", (request.form['nome'],)); conn.commit()
    except: pass
    conn.close()
    return redirect(url_for('cadastros', msg="Instituição adicionada!"))

@app.route('/edit_fornecedor/<int:id>', methods=['POST'])
def edit_fornecedor(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE fornecedores SET nome=? WHERE id=?", (request.form['nome'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Fornecedor atualizado!"))

@app.route('/edit_instituicao/<int:id>', methods=['POST'])
def edit_instituicao(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE instituicoes SET nome=? WHERE id=?", (request.form['nome'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Instituição atualizada!"))

@app.route('/add_marca', methods=['POST'])
def add_marca():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO marcas (nome) VALUES (?)", (request.form['nome'],))
        conn.commit()
    except: pass
    conn.close()
    return redirect(url_for('cadastros', msg="Marca adicionada com sucesso!"))

@app.route('/add_tipo', methods=['POST'])
def add_tipo():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO tipos_equipamento (nome) VALUES (?)", (request.form['nome'],))
        conn.commit()
    except: pass
    conn.close()
    return redirect(url_for('cadastros', msg="Tipo adicionado com sucesso!"))

@app.route('/add_setor', methods=['POST'])
def add_setor():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO setores (nome) VALUES (?)", (request.form['nome'],))
        conn.commit()
    except: pass
    conn.close()
    return redirect(url_for('cadastros', msg="Setor adicionado com sucesso!"))

@app.route('/add_funcionario', methods=['POST'])
def add_funcionario():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO funcionarios (nome, cargo, setor_id) VALUES (?,?,?)", (request.form['nome'], request.form['cargo'], request.form['setor_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Funcionário adicionado com sucesso!"))

@app.route('/add_user', methods=['POST'])
def add_user():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        setor_val = request.form.get('setor_id')
        setor_val = int(setor_val) if (setor_val and setor_val != '' and setor_val != 'None') else None
        eleitoral_local_val = request.form.get('eleitoral_local_id')
        eleitoral_local_val = int(eleitoral_local_val) if (eleitoral_local_val and eleitoral_local_val != '' and eleitoral_local_val != 'None') else None
        permissoes = ','.join(request.form.getlist('permissoes_estado'))
        locais = ','.join(request.form.getlist('locais_acesso'))
        c.execute("INSERT INTO users (username, password, perfil, nome_completo, setor_id, eleitoral_local_id, permissoes_estado, locais_acesso) VALUES (?,?,?,?,?,?,?,?)", (request.form['username'], generate_password_hash(request.form['password']), request.form['perfil'], request.form.get('nome_completo'), setor_val, eleitoral_local_val, permissoes, locais))
        conn.commit()
        msg = "Usuário adicionado com sucesso!"
    except:
        msg = "Erro: Este utilizador já existe!"
    conn.close()
    return redirect(url_for('cadastros', msg=msg))

@app.route('/edit_setor/<int:id>', methods=['POST'])
def edit_setor(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE setores SET nome=? WHERE id=?", (request.form['nome'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Setor atualizado!"))

@app.route('/edit_funcionario/<int:id>', methods=['POST'])
def edit_funcionario(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE funcionarios SET nome=?, cargo=?, setor_id=? WHERE id=?", (request.form['nome'], request.form['cargo'], request.form['setor_id'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Funcionário atualizado!"))

@app.route('/edit_user/<int:id>', methods=['POST'])
def edit_user(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    nome_completo = request.form.get('nome_completo')
    username = request.form.get('username')
    perfil = request.form.get('perfil')
    pwd = request.form.get('password')
    setor_id = request.form.get('setor_id')
    setor_val = int(setor_id) if (setor_id and setor_id != '' and setor_id != 'None') else None
    eleitoral_local_id = request.form.get('eleitoral_local_id')
    eleitoral_local_val = int(eleitoral_local_id) if (eleitoral_local_id and eleitoral_local_id != '' and eleitoral_local_id != 'None') else None
    permissoes = ','.join(request.form.getlist('permissoes_estado'))
    locais = ','.join(request.form.getlist('locais_acesso'))
    if pwd:
        hashed = generate_password_hash(pwd)
        c.execute("UPDATE users SET nome_completo=?, username=?, perfil=?, password=?, setor_id=?, eleitoral_local_id=?, permissoes_estado=?, locais_acesso=? WHERE id=?", (nome_completo, username, perfil, hashed, setor_val, eleitoral_local_val, permissoes, locais, id))
    else:
        c.execute("UPDATE users SET nome_completo=?, username=?, perfil=?, setor_id=?, eleitoral_local_id=?, permissoes_estado=?, locais_acesso=? WHERE id=?", (nome_completo, username, perfil, setor_val, eleitoral_local_val, permissoes, locais, id))
    
    # Check if we are updating our own profile, and if so, update the session
    c.execute("SELECT username FROM users WHERE id=?", (id,))
    res = c.fetchone()
    if res and res[0] == session.get('username'):
        session['nome'] = nome_completo or username
        session['perfil'] = perfil
        session['username'] = username
        session['setor_id'] = setor_val
        session['locais_acesso'] = locais
        
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Utilizador atualizado!"))

@app.route('/alterar_senha', methods=['POST'])
def alterar_senha():
    if 'username' not in session: return redirect(url_for('login'))
    senha_atual = request.form.get('senha_atual', '')
    nova = request.form.get('nova_senha', '')
    nova2 = request.form.get('nova_senha2', '')
    if nova != nova2:
        flash("Erro: as novas palavras-passe não coincidem.")
        return redirect(url_for('cadastros'))
    if len(nova) < 4:
        flash("Erro: a nova palavra-passe deve ter pelo menos 4 caracteres.")
        return redirect(url_for('cadastros'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username=?", (session['username'],))
    row = c.fetchone()
    if not row:
        conn.close()
        flash("Erro: utilizador não encontrado.")
        return redirect(url_for('cadastros'))
    stored = row[0]
    valid = False
    if stored and ':' in stored and not stored.startswith('md5'):
        valid = check_password_hash(stored, senha_atual)
    elif stored:
        valid = hashlib.md5(senha_atual.encode()).hexdigest() == stored
    if not valid:
        conn.close()
        flash("Erro: palavra-passe atual incorreta.")
        return redirect(url_for('cadastros'))
    c.execute("UPDATE users SET password=? WHERE username=?", (generate_password_hash(nova), session['username']))
    conn.commit()
    conn.close()
    flash("Palavra-passe alterada com sucesso!")
    return redirect(url_for('cadastros'))


@app.route('/edit_marca/<int:id>', methods=['POST'])
def edit_marca(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE marcas SET nome=? WHERE id=?", (request.form['nome'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Marca atualizada!"))

@app.route('/delete_marca/<int:id>', methods=['POST'])
def delete_marca(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM marcas WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Marca removida!"))

@app.route('/edit_tipo/<int:id>', methods=['POST'])
def edit_tipo(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE tipos_equipamento SET nome=? WHERE id=?", (request.form['nome'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Tipo de equipamento atualizado!"))

@app.route('/delete_tipo/<int:id>', methods=['POST'])
def delete_tipo(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM tipos_equipamento WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Tipo de equipamento removido!"))

@app.route('/delete_setor/<int:id>', methods=['POST'])
def delete_setor(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM setores WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Setor removido!"))

@app.route('/delete_funcionario/<int:id>', methods=['POST'])
def delete_funcionario(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM funcionarios WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Funcionário removido!"))

@app.route('/delete_user/<int:id>', methods=['POST'])
def delete_user(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Usuário removido!"))

@app.route('/delete_motivo/<int:id>', methods=['POST'])
def delete_motivo(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM motivos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Motivo removido!"))

@app.route('/delete_fornecedor/<int:id>', methods=['POST'])
def delete_fornecedor(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM fornecedores WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Fornecedor removido!"))

@app.route('/delete_instituicao/<int:id>', methods=['POST'])
def delete_instituicao(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM instituicoes WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Instituição removida!"))



@app.route('/edit_movimento_form/<guia>')
def edit_movimento_form(guia):
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM movimentos WHERE guia=?", (guia,))
    cols = [d[0] for d in c.description]
    row = c.fetchone()
    if not row: return "Not found"
    mov = dict(zip(cols, row))
    
    c.execute("SELECT nome FROM tipos_equipamento"); tipos = [r[0] for r in c.fetchall()]
    c.execute("SELECT nome FROM marcas"); marcas = [r[0] for r in c.fetchall()]
    c.execute("SELECT nome FROM motivos"); motivos = [r[0] for r in c.fetchall()]
    c.execute("SELECT nome FROM fornecedores"); fornecedores = [r[0] for r in c.fetchall()]
    c.execute("SELECT nome FROM instituicoes"); insts = [r[0] for r in c.fetchall()]
    c.execute("SELECT nome FROM setores"); sets = [r[0] for r in c.fetchall()]
    conn.close()

    # Equipamento options
    curr_equip = mov.get('equipamento', '')
    if curr_equip and curr_equip not in tipos:
        tipos.append(curr_equip)
    equip_options = ""
    for t in tipos:
        selected = "selected" if t == curr_equip else ""
        equip_options += f'<option value="{t}" {selected}>{t}</option>'

    # Marca options
    curr_marca = mov.get('marca', '')
    if curr_marca and curr_marca not in marcas:
        marcas.append(curr_marca)
    marca_options = ""
    for m in marcas:
        selected = "selected" if m == curr_marca else ""
        marca_options += f'<option value="{m}" {selected}>{m}</option>'

    # Motivo options
    curr_motivo = mov.get('motivo', '')
    if curr_motivo and curr_motivo not in motivos:
        motivos.append(curr_motivo)
    motivo_options = ""
    for m in motivos:
        selected = "selected" if m == curr_motivo else ""
        motivo_options += f'<option value="{m}" {selected}>{m}</option>'

    # Fornecedor options
    curr_forn = mov.get('fornecedor', '')
    if curr_forn and curr_forn not in fornecedores:
        fornecedores.append(curr_forn)
    fornecedor_options = ""
    for f in fornecedores:
        selected = "selected" if f == curr_forn else ""
        fornecedor_options += f'<option value="{f}" {selected}>{f}</option>'

    # Origem/Destino options
    curr_od = mov.get('origem_destino', '')
    od_in_lists = False
    for s in sets:
        if f"Interno - {s}" == curr_od: od_in_lists = True
    for i in insts:
        if f"Externo - {i}" == curr_od: od_in_lists = True
        
    origem_destino_options = ""
    if curr_od and not od_in_lists:
        origem_destino_options += f'<option value="{curr_od}" selected>{curr_od}</option>'
        
    origem_destino_options += '<optgroup label="Setores Internos">'
    for s in sets:
        val = f"Interno - {s}"
        selected = "selected" if val == curr_od else ""
        origem_destino_options += f'<option value="{val}" {selected}>{s}</option>'
    origem_destino_options += '</optgroup>'
    
    origem_destino_options += '<optgroup label="Instituições Externas">'
    for i in insts:
        val = f"Externo - {i}"
        selected = "selected" if val == curr_od else ""
        origem_destino_options += f'<option value="{val}" {selected}>{i}</option>'
    origem_destino_options += '</optgroup>'

    # Prepare status selection options
    curr_status = mov.get('status', '')
    status_options = ""
    for st in ["Em estoque", "Aguardando reparação", "Reparado e Entregue", "Entregue"]:
        selected = "selected" if st == curr_status else ""
        status_options += f'<option value="{st}" {selected}>{st}</option>'
    # If custom status is set, add it
    if curr_status and curr_status not in ["Em estoque", "Aguardando reparação", "Reparado e Entregue", "Entregue"]:
        status_options += f'<option value="{curr_status}" selected>{curr_status}</option>'

    # Tipo options
    curr_tipo = mov.get('tipo', '')
    tipo_options = f'<option value="ENTRADA" {"selected" if curr_tipo=="ENTRADA" else ""}>ENTRADA</option>'
    tipo_options += f'<option value="SAIDA" {"selected" if curr_tipo=="SAIDA" else ""}>SAÍDA</option>'

    html = f"""<!DOCTYPE html><html lang="pt"><head>{COMMON_HEAD}
    <title>Editar Movimento</title>
    <style>
        .form-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
        label {{ font-weight: 600; color: #475569; display: block; margin-top: 0.5rem; }}
        @media (max-width: 600px) {{
            .form-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
    </head><body>
    <div class="nav"><strong>Editar Movimento: {guia}</strong><a href="/" class="btn btn-outline" style="background:white; color:#0f172a;">Voltar</a></div>
    <div class="container">
        <div class="card" style="max-width:800px; margin:0 auto;">
            <form method="POST" action="/edit_movimento/{guia}">
                <div class="form-grid">
                    <div>
                        <label>Tipo de Movimento</label>
                        <select name="tipo" required>{tipo_options}</select>
                    </div>
                    <div>
                        <label>Data</label>
                        <input type="date" name="data" value="{mov.get('data', '')}" required>
                    </div>
                    <div>
                        <label>Equipamento</label>
                        <select name="equipamento" required>{equip_options}</select>
                    </div>
                    <div>
                        <label>Marca</label>
                        <select name="marca" required>{marca_options}</select>
                    </div>
                    <div>
                        <label>Número de Série (S/N)</label>
                        <input name="numero_serie" value="{mov.get('numero_serie', '')}" required>
                    </div>
                    <div>
                        <label>Quantidade</label>
                        <input name="quantidade" value="{mov.get('quantidade', '')}" required>
                    </div>
                    <div>
                        <label>Origem / Destino</label>
                        <select name="origem_destino" required>{origem_destino_options}</select>
                    </div>
                    <div>
                        <label>Motivo</label>
                        <select name="motivo" required>{motivo_options}</select>
                    </div>
                    <div>
                        <label>Fornecedor</label>
                        <select name="fornecedor" required>{fornecedor_options}</select>
                    </div>
                    <div>
                        <label>Status</label>
                        <select name="status" required>{status_options}</select>
                    </div>
                    <div>
                        <label>Entregue Por</label>
                        <input name="entregue_por" value="{mov.get('entregue_por') or ''}">
                    </div>
                    <div>
                        <label>Recebido Por</label>
                        <input name="recebido_por" value="{mov.get('recebido_por') or ''}">
                    </div>
                    <div>
                        <label>Técnico Responsável</label>
                        <input name="tecnico" value="{mov.get('tecnico') or ''}">
                    </div>
                    <div>
                        <label>Agente de Proteção</label>
                        <input name="agente_protecao" value="{mov.get('agente_protecao') or ''}">
                    </div>
                </div>
                <button class="btn btn-blue" style="width:100%; margin-top:2rem; padding:0.8rem; font-size:1rem;">Salvar Alterações</button>
            </form>
        </div>
    </div>
    </body></html>"""
    return html


@app.route('/edit_movimento/<guia>', methods=['POST'])
def edit_movimento(guia):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''UPDATE movimentos SET 
                 tipo=?, data=?, equipamento=?, marca=?, numero_serie=?, 
                 quantidade=?, origem_destino=?, motivo=?, fornecedor=?, 
                 status=?, entregue_por=?, recebido_por=?, tecnico=?, agente_protecao=?
                 WHERE guia=?''', 
              (request.form.get('tipo'), request.form.get('data'), request.form.get('equipamento'),
               request.form.get('marca'), request.form.get('numero_serie'), request.form.get('quantidade'),
               request.form.get('origem_destino'), request.form.get('motivo'), request.form.get('fornecedor'),
               request.form.get('status'), request.form.get('entregue_por'), request.form.get('recebido_por'),
               request.form.get('tecnico'), request.form.get('agente_protecao'), guia))
    conn.commit()
    conn.close()
    return redirect(url_for('index', msg="Movimento atualizado!"))

@app.route('/ver_guia/<guia>')
def ver_guia(guia):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT m.*, f.nome FROM movimentos m LEFT JOIN funcionarios f ON m.funcionario_id = f.id WHERE m.guia = ?", (guia,))
    cols = [desc[0] for desc in c.description]
    row = c.fetchone()
    c.execute("SELECT id, nome FROM funcionarios")
    func_map = {str(r[0]): r[1] for r in c.fetchall()}
    
    if not row: return "Guia não encontrada", 404
    r = dict(zip(cols, row))
    
    c.execute("SELECT id, nome FROM setores")
    setor_map = {int(s[0]): s[1] for s in c.fetchall()}
    conn.close()

    # Nome canónico por TEXTO do setor (os ids de setor divergem entre local e nuvem,
    # por isso mapeamos por palavras-chave do nome, que é estável).
    def nome_canonico_setor(nome_cru):
        if not nome_cru:
            return None
        n = str(nome_cru).upper().replace('Ç', 'C').replace('Ã', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
        def contem(*palavras):
            return all(p in n for p in palavras)
        if contem('DELIMITA') or contem('GEO') and contem('INFORMATICA'):
            return "Departamento de Delimitação Geográfica, Estatística e Informática"
        if 'PATRIMONIO' in n:
            return "Departamento de Património e Aprovisionamento"
        if 'RECURSOS HUMANOS' in n:
            return "Departamento de Recursos Humanos"
        if 'FINANC' in n:
            return "Departamento das Finanças"
        if 'AQUISI' in n:
            return "Departamento das Aquisições"
        if 'TRANSPORTES' in n and 'REPART' in n:
            return "Repartição dos Transportes"
        if 'TRANSPORTE' in n:
            return "Departamento dos Transportes"
        if 'PROTEC' in n:
            return "Departamento de Protecção"
        if 'RECENSEAMENTO' in n or 'SUFRAGIO' in n:
            return "Departamento de Recenseamento e Sufrágio"
        if 'OPERACOES ELEITORAIS' in n or n == 'DOOE':
            return "Direcção de Organização e Operações Eleitorais (DOOE)"
        if 'UGEA' in n:
            return "Unidade Gestora Executora de Aquisições"
        if 'GABINETE' in n and 'JURIDICO' in n:
            return "Gabinete Jurídico"
        if 'GABINETE' in n:
            return "Gabinete de Comunicação e Imagem"
        if 'SECRETARIA' in n:
            return "Secretaria Geral"
        return None

    def resolver_nome(dep_id):
        if not dep_id:
            return None
        try:
            dep_id = int(dep_id)
        except (TypeError, ValueError):
            return None
        if dep_id in setor_map:
            canon = nome_canonico_setor(setor_map[dep_id])
            if canon:
                return canon
            return setor_map[dep_id].title()
        return None

    def nome_departamento_responsavel():
        nome = resolver_nome(r.get('departamento_responsavel_id'))
        if nome:
            return nome
        # Fallback: departamento do movimento (origem/destino)
        nome = resolver_nome(r.get('setor_origem_id')) or resolver_nome(r.get('setor_destino_id'))
        if nome:
            return nome
        return "Departamento de Delimitação Geográfica, Estatística e Informática"

    dep_responsavel = nome_departamento_responsavel()

    buffer = io.BytesIO()
    c_pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    logo_path = os.path.join(BASE_DIR, 'logo.jpeg')
    if os.path.exists(logo_path):
        try: c_pdf.drawImage(ImageReader(logo_path), width/2 - 40, height - 90, width=80, height=80, preserveAspectRatio=True)
        except: pass

    c_pdf.setFont("Helvetica", 9)
    y = height - 100
    c_pdf.drawCentredString(width/2, y, "REPÚBLICA DE MOÇAMBIQUE")
    c_pdf.drawCentredString(width/2, y-12, "STAE-Secretariado Técnico de Administração Eleitoral")
    c_pdf.drawCentredString(width/2, y-24, "DIREÇÃO DE ORGANIZAÇÃO E OPERAÇÕES ELEITORAIS (DOOE)")
    c_pdf.setFont("Helvetica-Bold", 9.5)
    c_pdf.drawCentredString(width/2, y-36, dep_responsavel.upper())
    
    c_pdf.setFont("Helvetica-Bold", 12)
    c_pdf.drawCentredString(width/2, y-66, "Ficha de Controlo")
    c_pdf.setFont("Helvetica", 11)
    c_pdf.drawCentredString(width/2, y-80, "MOVIMENTO DE EQUIPAMENTO INFORMÁTICO")
    
    c_pdf.setFont("Helvetica", 10)
    is_entrada = (r.get('tipo', '').upper() == "ENTRADA")
    
    if is_entrada:
        origem = r.get('origem_destino', '') or ""
        dest_id = r.get('setor_destino_id')
        destino = setor_map.get(int(dest_id), "") if dest_id else (r.get('local_destino') or "")
        if not destino:
            destino = "Inventário Directo"
        motivo = r.get('motivo', '') or ""
        c_pdf.drawString(50, y-115, "O Equipamento abaixo descrito foi RECEBIDO de (1):")
        c_pdf.drawString(50, y-130, f"{origem}")
        c_pdf.line(50, y-132, 500, y-132)
        
        c_pdf.drawString(50, y-150, f"Para {destino}")
        c_pdf.line(80, y-152, 500, y-152)
    else:
        orig_id = r.get('setor_origem_id')
        origem = setor_map.get(int(orig_id), "") if orig_id else (r.get('local_origem') or "")
        if not origem:
            origem = "STAE - DDGEI"
        destino = r.get('origem_destino', '') or ""
        motivo = r.get('motivo', '') or ""
        c_pdf.drawString(50, y-115, f"O Equipamento abaixo descrito é RETIRADO de (1) {origem}")
        
        c_pdf.drawString(50, y-130, f"Para {destino}")
        c_pdf.line(80, y-132, 500, y-132)
        
    c_pdf.drawString(50, y-170, f"Com Propósito de {motivo}")
    c_pdf.line(145, y-172, 500, y-172)
    
    y_table = y - 200
    c_pdf.setFont("Helvetica", 9)
    c_pdf.drawString(50, y_table, "QTY")
    c_pdf.drawString(100, y_table, "Tipo de Equipamento")
    c_pdf.drawString(240, y_table, "Marca")
    c_pdf.drawString(330, y_table, "S/N")
    c_pdf.drawString(430, y_table, "Estado")
    c_pdf.drawString(425, y_table-10, "(1Bom-2Avariado)")
    
    y_row = y_table - 30
    qty = str(r.get('quantidade') or '1')
    c_pdf.drawString(55, y_row, qty)
    c_pdf.drawString(100, y_row, str(r.get('equipamento', '')))
    c_pdf.drawString(240, y_row, str(r.get('marca', '')))
    c_pdf.drawString(330, y_row, str(r.get('numero_serie', '')))
    c_pdf.drawString(430, y_row, str(r.get('status', '')))
    
    for i in range(10): c_pdf.line(50, y_row - 5 - (i*15), 520, y_row - 5 - (i*15))
    
    # Desenhar X grande sobre as linhas vazias para evitar fraudes
    c_pdf.line(50, y_row - 5, 520, y_row - 140)
    c_pdf.line(50, y_row - 140, 520, y_row - 5)
    
    y_conf = y_row - 180
    c_pdf.setFont("Helvetica-Bold", 11)
    c_pdf.drawCentredString(width/2, y_conf, "CONFIRMAÇÃO")
    
    y_box1 = y_conf - 20
    c_pdf.rect(50, y_box1 - 70, 470, 70)
    
    c_pdf.setFont("Helvetica", 9)
    data_mov = str(r.get('data', ''))[:10]
    
    tec_name = r.get('tecnico') or ""
    ent_id = str(r.get('entregue_por'))
    rec_id = str(r.get('recebido_por'))
    agente_id = str(r.get('agente_protecao'))
    
    entregue = func_map.get(ent_id, r.get('entregue_por')) or tec_name
    if not entregue or entregue == 'None' or str(entregue).strip() == '': entregue = "XXXXXXXXXXXXXXXXXX"
    
    recebido = func_map.get(rec_id, r.get('recebido_por')) or tec_name
    if not recebido or recebido == 'None' or str(recebido).strip() == '': recebido = "XXXXXXXXXXXXXXXXXX"
    
    agente = func_map.get(agente_id, r.get('agente_protecao'))
    
    c_pdf.drawString(60, y_box1 - 15, f"(1)Entreguei: Data  {data_mov}")
    c_pdf.drawString(60, y_box1 - 35, f"Nome {entregue}")
    c_pdf.drawString(60, y_box1 - 55, "Função _________________________")
    
    c_pdf.drawString(300, y_box1 - 15, f"(2)Recebi: Data  {data_mov}")
    c_pdf.drawString(300, y_box1 - 35, f"Nome {recebido}")
    c_pdf.drawString(300, y_box1 - 55, "Função _________________________")
    
    y_visto = y_box1 - 100
    c_pdf.setFont("Helvetica-Bold", 11)
    c_pdf.drawCentredString(width/2, y_visto, "NO STAE VISTO POR")
    
    y_box2 = y_visto - 20
    c_pdf.rect(50, y_box2 - 60, 470, 60)
    
    c_pdf.setFont("Helvetica", 9)
    c_pdf.drawCentredString(150, y_box2 - 15, "Data ____/____/202__")
    c_pdf.drawCentredString(150, y_box2 - 45, "_______________________________")
    c_pdf.drawCentredString(150, y_box2 - 55, f"O Chefe de {dep_responsavel}")
    
    c_pdf.drawCentredString(400, y_box2 - 15, "Data ____/____/202__")
    if agente and agente != 'None' and str(agente).strip() != '':
        c_pdf.drawCentredString(400, y_box2 - 45, agente)
    else:
        c_pdf.drawCentredString(400, y_box2 - 45, "XXXXXXXXXXXXXXXXXXXXXXXXX")
    c_pdf.drawCentredString(400, y_box2 - 55, "Protecção")

    c_pdf.setFont("Helvetica-Oblique", 7)
    c_pdf.drawCentredString(width/2, 20, f"Gerado por STAE Gestão em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Guia: {r.get('guia','')}")

    c_pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=False, download_name=f"Ficha_{r.get('guia','')}.pdf", mimetype='application/pdf')


import json
@app.route('/relatorios')
def relatorios():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('perfil') != 'admin':
        return redirect(url_for('index', msg="Erro: Apenas administradores têm acesso aos relatórios."))
        
    tab = request.args.get('tab', 'inventario')
    setor_ids = [x for x in request.args.getlist('setor_id') if x]
    status_list = [x for x in request.args.getlist('status') if x]
    marcas = [x for x in request.args.getlist('marca') if x]
    tipos_eq = [x for x in request.args.getlist('tipo_equipamento') if x]
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')
    mov_tipo = request.args.getlist('mov_tipo')
    mov_tipo = [x for x in mov_tipo if x]
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Load filter lists
    c.execute("SELECT id, nome FROM setores")
    setores = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM marcas")
    marcas_opcoes = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM tipos_equipamento")
    tipos_eq_opcoes = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    
    items = []

    def pl(n):
        return ','.join('?' * len(n))
    
    if tab == 'inventario':
        query = '''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, 
                          i.data_registo, i.observacoes, s.nome as setor_nome 
                   FROM inventario_local i 
                   LEFT JOIN setores s ON i.setor_id = s.id 
                   WHERE i.status != 'Pendente' '''
        params = []
        if setor_ids:
            query += f" AND i.setor_id IN ({pl(setor_ids)})"
            params.extend(int(x) for x in setor_ids)
        if status_list:
            query += f" AND i.status IN ({pl(status_list)})"
            params.extend(status_list)
        if marcas:
            query += f" AND i.marca IN ({pl(marcas)})"
            params.extend(marcas)
        if tipos_eq:
            query += f" AND i.equipamento IN ({pl(tipos_eq)})"
            params.extend(tipos_eq)
            
        query += " ORDER BY i.id DESC"
        c.execute(query, params)
        cols = [d[0] for d in c.description]
        items = [dict(zip(cols, r)) for r in c.fetchall()]
        
    elif tab == 'entradas_saidas':
        query = '''SELECT m.guia, m.tipo, m.equipamento, m.marca, m.numero_serie, m.origem_destino, 
                          m.quantidade, m.data, m.status, m.tecnico, m.motivo 
                   FROM movimentos m 
                   WHERE m.tipo IN ('ENTRADA', 'SAIDA') '''
        params = []
        if setor_ids:
            ph = pl(setor_ids)
            query += f" AND (m.setor_origem_id IN ({ph}) OR m.setor_destino_id IN ({ph}))"
            params.extend(int(x) for x in setor_ids)
            params.extend(int(x) for x in setor_ids)
        if marcas:
            query += f" AND m.marca IN ({pl(marcas)})"
            params.extend(marcas)
        if tipos_eq:
            query += f" AND m.equipamento IN ({pl(tipos_eq)})"
            params.extend(tipos_eq)
        if data_inicio:
            query += " AND m.data >= ?"
            params.append(data_inicio)
        if data_fim:
            query += " AND m.data <= ?"
            params.append(data_fim)
            
        query += " ORDER BY m.id DESC"
        c.execute(query, params)
        cols = [d[0] for d in c.description]
        items = [dict(zip(cols, r)) for r in c.fetchall()]
        
    elif tab == 'movimentos':
        query = '''SELECT m.guia, m.tipo, m.equipamento, m.marca, m.numero_serie, m.origem_destino, 
                          m.quantidade, m.data, m.status, m.tecnico, m.motivo 
                   FROM movimentos m 
                   WHERE 1=1 '''
        params = []
        if mov_tipo:
            query += f" AND m.tipo IN ({pl(mov_tipo)})"
            params.extend(mov_tipo)
        if status_list:
            query += f" AND m.status IN ({pl(status_list)})"
            params.extend(status_list)
        if setor_ids:
            ph = pl(setor_ids)
            query += f" AND (m.setor_origem_id IN ({ph}) OR m.setor_destino_id IN ({ph}))"
            params.extend(int(x) for x in setor_ids)
            params.extend(int(x) for x in setor_ids)
        if marcas:
            query += f" AND m.marca IN ({pl(marcas)})"
            params.extend(marcas)
        if data_inicio:
            query += " AND m.data >= ?"
            params.append(data_inicio)
        if data_fim:
            query += " AND m.data <= ?"
            params.append(data_fim)
            
        query += " ORDER BY m.id DESC"
        c.execute(query, params)
        cols = [d[0] for d in c.description]
        items = [dict(zip(cols, r)) for r in c.fetchall()]
        
    # Estatísticas para os gráficos
    c.execute('''
        SELECT COALESCE(equipamento, 'N/A') AS equipamento,
               SUM(CASE WHEN tipo='ENTRADA' THEN COALESCE(CAST(quantidade AS INTEGER),1) ELSE 0 END) AS entradas,
               SUM(CASE WHEN tipo IN ('SAIDA','TRANSFERENCIA') THEN COALESCE(CAST(quantidade AS INTEGER),1) ELSE 0 END) AS saidas
        FROM movimentos GROUP BY equipamento ORDER BY equipamento''')
    stat_equip = [dict(zip(['equipamento','entradas','saidas'], r)) for r in c.fetchall()]

    c.execute('''
        SELECT COALESCE(NULLIF(origem_destino,''),'N/A') AS origem,
               COUNT(*) AS total
        FROM movimentos WHERE tipo='ENTRADA' GROUP BY origem ORDER BY total DESC LIMIT 10''')
    stat_setor = [dict(zip(['origem','total'], r)) for r in c.fetchall()]
    if not stat_setor:
        stat_setor = [{'origem': 'Sem dados', 'total': 0}]

    c.execute('''
        SELECT COALESCE(NULLIF(marca,''),'N/A') AS marca,
               SUM(CASE WHEN tipo='ENTRADA' THEN COALESCE(CAST(quantidade AS INTEGER),1) ELSE 0 END) AS entradas,
               SUM(CASE WHEN tipo IN ('SAIDA','TRANSFERENCIA') THEN COALESCE(CAST(quantidade AS INTEGER),1) ELSE 0 END) AS saidas
        FROM movimentos GROUP BY marca ORDER BY marca''')
    stat_marca = [dict(zip(['marca','entradas','saidas'], r)) for r in c.fetchall()]
    if not stat_marca:
        stat_marca = [{'marca': 'Sem dados', 'entradas': 0, 'saidas': 0}]

    conn.close()
    return render_template_string(
        RELATORIOS_TEMPLATE,
        tab=tab,
        items=items,
        setores=setores,
        marcas=marcas_opcoes,
        tipos_eq=tipos_eq_opcoes,
        setor_ids=setor_ids,
        status_list=status_list,
        marcas_list=marcas,
        tipos_eq_list=tipos_eq,
        data_inicio=data_inicio,
        data_fim=data_fim,
        mov_tipo=mov_tipo,
        stat_equip=json.dumps(stat_equip, ensure_ascii=False),
        stat_setor=json.dumps(stat_setor, ensure_ascii=False),
        stat_marca=json.dumps(stat_marca, ensure_ascii=False)
    )

@app.route('/relatorios/export/<format_type>')
def relatorios_export(format_type):
    if 'username' not in session or session.get('perfil') != 'admin':
        return abort(403)
        
    tab = request.args.get('tab', 'inventario')
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')
    setor_ids = [x for x in request.args.get('setor_id', '').split(',') if x]
    status_list = [x for x in request.args.get('status', '').split(',') if x]
    marcas = [x for x in request.args.get('marca', '').split(',') if x]
    tipos_eq = [x for x in request.args.get('tipo_equipamento', '').split(',') if x]
    mov_tipo = [x for x in request.args.get('mov_tipo', '').split(',') if x]
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    headers = []
    rows = []
    title = ""

    def pl(n):
        return ','.join('?' * len(n))
    
    if tab == 'inventario':
        title = "Relatório de Inventário"
        headers = ["ID", "Equipamento", "Marca", "Nº Série", "Qtd", "Estado", "Data Registo", "Observações", "Setor"]
        query = '''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, 
                          i.data_registo, i.observacoes, s.nome as setor_nome 
                   FROM inventario_local i 
                   LEFT JOIN setores s ON i.setor_id = s.id 
                   WHERE i.status != 'Pendente' '''
        params = []
        if setor_ids:
            query += f" AND i.setor_id IN ({pl(setor_ids)})"
            params.extend(int(x) for x in setor_ids)
        if status_list:
            query += f" AND i.status IN ({pl(status_list)})"
            params.extend(status_list)
        if marcas:
            query += f" AND i.marca IN ({pl(marcas)})"
            params.extend(marcas)
        if tipos_eq:
            query += f" AND i.equipamento IN ({pl(tipos_eq)})"
            params.extend(tipos_eq)
        query += " ORDER BY i.id DESC"
        c.execute(query, params)
        rows = c.fetchall()
        
    elif tab == 'entradas_saidas':
        title = "Relatório de Entradas e Saídas"
        headers = ["Guia", "Tipo", "Equipamento", "Marca", "Nº Série", "Origem/Destino", "Qtd", "Data", "Estado", "Técnico", "Motivo"]
        query = '''SELECT m.guia, m.tipo, m.equipamento, m.marca, m.numero_serie, m.origem_destino, 
                          m.quantidade, m.data, m.status, m.tecnico, m.motivo 
                   FROM movimentos m 
                   WHERE m.tipo IN ('ENTRADA', 'SAIDA') '''
        params = []
        if setor_ids:
            ph = pl(setor_ids)
            query += f" AND (m.setor_origem_id IN ({ph}) OR m.setor_destino_id IN ({ph}))"
            params.extend(int(x) for x in setor_ids)
            params.extend(int(x) for x in setor_ids)
        if marcas:
            query += f" AND m.marca IN ({pl(marcas)})"
            params.extend(marcas)
        if tipos_eq:
            query += f" AND m.equipamento IN ({pl(tipos_eq)})"
            params.extend(tipos_eq)
        if data_inicio:
            query += " AND m.data >= ?"
            params.append(data_inicio)
        if data_fim:
            query += " AND m.data <= ?"
            params.append(data_fim)
        query += " ORDER BY m.id DESC"
        c.execute(query, params)
        rows = c.fetchall()
        
    elif tab == 'movimentos':
        title = "Relatório de Movimentações"
        headers = ["Guia", "Tipo", "Equipamento", "Marca", "Nº Série", "Origem/Destino", "Qtd", "Data", "Estado", "Técnico", "Motivo"]
        query = '''SELECT m.guia, m.tipo, m.equipamento, m.marca, m.numero_serie, m.origem_destino, 
                          m.quantidade, m.data, m.status, m.tecnico, m.motivo 
                   FROM movimentos m 
                   WHERE 1=1 '''
        params = []
        if mov_tipo:
            query += f" AND m.tipo IN ({pl(mov_tipo)})"
            params.extend(mov_tipo)
        if status_list:
            query += f" AND m.status IN ({pl(status_list)})"
            params.extend(status_list)
        if setor_ids:
            ph = pl(setor_ids)
            query += f" AND (m.setor_origem_id IN ({ph}) OR m.setor_destino_id IN ({ph}))"
            params.extend(int(x) for x in setor_ids)
            params.extend(int(x) for x in setor_ids)
        if marcas:
            query += f" AND m.marca IN ({pl(marcas)})"
            params.extend(marcas)
        if data_inicio:
            query += " AND m.data >= ?"
            params.append(data_inicio)
        if data_fim:
            query += " AND m.data <= ?"
            params.append(data_fim)
        query += " ORDER BY m.id DESC"
        c.execute(query, params)
        rows = c.fetchall()
        
    conn.close()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if format_type == 'pdf':
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Titulo', parent=styles['Title'], fontSize=16, alignment=1, spaceAfter=6)
        sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=11, alignment=1, spaceAfter=10, textColor=colors.HexColor('#475569'))
        head_style = ParagraphStyle('Hd', parent=styles['Normal'], fontSize=8, fontWeight='bold', textColor=colors.white)

        elementos = []
        elementos.append(Paragraph("REPÚBLICA DE MOÇAMBIQUE", title_style))
        elementos.append(Paragraph("STAE — Secretariado Técnico de Administração Eleitoral", sub_style))
        elementos.append(Paragraph(f"<b>{title}</b>", styles['Heading2']))
        criterios = []
        if setor_ids:
            criterios.append(f"{len(setor_ids)} setor(es)")
        if marcas:
            criterios.append(f"{len(marcas)} marca(s)")
        if tipos_eq:
            criterios.append(f"{len(tipos_eq)} tipo(s) de equipamento")
        if status_list:
            criterios.append(f"{len(status_list)} estado(s)")
        if mov_tipo:
            criterios.append(f"{len(mov_tipo)} tipo(s) de movimento")
        if data_inicio:
            criterios.append(f"desde {data_inicio}")
        if data_fim:
            criterios.append(f"até {data_fim}")
        if criterios:
            elementos.append(Paragraph("Critérios aplicados: " + ", ".join(criterios) + ".", styles['Normal']))
        elementos.append(Spacer(1, 8))

        if rows:
            col_widths = [doc.width / len(headers)] * len(headers)
            data = [[Paragraph(h, head_style) for h in headers]]
            for r in rows:
                data.append([str(v) if v is not None else '' for v in r])
            tab = Table(data, colWidths=col_widths, repeatRows=1)
            tab.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
                ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#cbd5e1')),
                ('FONTSIZE', (0,0), (-1,-1), 7),
                ('TOPPADDING', (0,0), (-1,-1), 3),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            elementos.append(tab)
        else:
            elementos.append(Paragraph("Sem dados para os critérios selecionados.", styles['Normal']))

        doc.build(elementos)
        output.seek(0)
        return send_file(output, download_name=f"relatorio_{timestamp}.pdf", as_attachment=True, mimetype="application/pdf")
    
    if format_type == 'excel':
        import openpyxl
        from openpyxl.styles import PatternFill, Font
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = title if title else "Relatorio"
        
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        
        green_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        green_font = Font(color="166534", bold=True)
        
        red_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        red_font = Font(color="991B1B", bold=True)
        
        yellow_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
        yellow_font = Font(color="D97706", bold=True)
        
        ws.append(headers)
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col)
            cell.fill = header_fill
            cell.font = header_font
            
        for r in rows:
            ws.append([str(val) if val is not None else '' for val in r])
            current_row = ws.max_row
            # Try to color status cells
            for col_idx, col_name in enumerate(headers):
                cell_val = str(r[col_idx]).upper() if r[col_idx] is not None else ""
                cell = ws.cell(row=current_row, column=col_idx + 1)
                
                if "RECEBIDO" in cell_val or "ENTREGUE" in cell_val or "BOM ESTADO" in cell_val or "BOM" == cell_val:
                    cell.fill = green_fill
                    cell.font = green_font
                elif "REJEITADO" in cell_val or "AVARIADO" in cell_val or "MAU ESTADO" in cell_val or "MAU" == cell_val:
                    cell.fill = red_fill
                    cell.font = red_font
                elif "PENDENTE" in cell_val or "EM_TRANSITO" in cell_val or "MANUTENÇÃO" in cell_val:
                    cell.fill = yellow_fill
                    cell.font = yellow_font
                    
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[column].width = adjusted_width

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f"relatorio_{tab}_{timestamp}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    elif format_type == 'pdf':
        # Professional PDF styling using reportlab SimpleDocTemplate in Landscape
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        
        buffer = io.BytesIO()
        # Use landscape A4 to ensure all data columns fit neatly
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        story = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=18,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=15
        )
        sub_style = ParagraphStyle(
            'ReportSub',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            textColor=colors.HexColor('#64748b'),
            spaceAfter=25
        )
        cell_style = ParagraphStyle(
            'CellText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=10
        )
        header_style = ParagraphStyle(
            'HeaderText',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.white
        )
        
        # Title Banner
        story.append(Paragraph(title, title_style))
        story.append(Paragraph(f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Utilizador: {session['username']}", sub_style))
        
        # Prepare table data
        table_data = []
        table_data.append([Paragraph(h, header_style) for h in headers])
        for r in rows:
            table_data.append([Paragraph(str(val) if val is not None else '', cell_style) for val in r])
            
        # Determine column widths automatically (page width is 842 - 60 = 782)
        col_count = len(headers)
        col_width = 782 / col_count
        
        t = Table(table_data, colWidths=[col_width]*col_count)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#3b82f6')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(t)
        
        doc.build(story)
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"relatorio_{tab}_{timestamp}.pdf",
            mimetype='application/pdf'
        )

@app.route('/confirmar_recepcao/<guia>', methods=['POST'])
def confirmar_recepcao(guia):
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT equipamento, marca, numero_serie, quantidade, setor_destino_id FROM movimentos WHERE guia=? AND status='PENDENTE_RECEPCAO'", (guia,))
    mov = c.fetchone()
    if mov:
        equipamento, marca, numero_serie, quantidade, setor_destino_id = mov
        # Controlo de permissoes: so o destino (ou admin) pode confirmar rececao;
        # se o admin restringiu os estados do usuário, também deve ter RECEBIDO.
        if not (session.get('perfil') == 'admin' or session.get('setor_id') == setor_destino_id):
            conn.close()
            flash("Sem permissao para confirmar esta rececao.")
            return redirect(url_for('index'))
        if session.get('perfil') != 'admin':
            c.execute("SELECT permissoes_estado FROM users WHERE id=?", (session.get('user_id'),))
            up = c.fetchone()
            user_perm = []
            if up and up[0]:
                user_perm = [s.strip() for s in up[0].split(',') if s.strip()]
            if user_perm and 'RECEBIDO' not in user_perm:
                conn.close()
                flash("Sem permissao para confirmar esta rececao.")
                return redirect(url_for('index'))
        # Check if already exists in dest
        c.execute("SELECT id, quantidade FROM inventario_local WHERE setor_id=? AND equipamento=? AND numero_serie=? AND marca=?", (setor_destino_id, equipamento, numero_serie, marca))
        inv = c.fetchone()
        qty = int(quantidade) if quantidade and str(quantidade).isdigit() else 1
        if inv:
            c.execute("UPDATE inventario_local SET quantidade=quantidade+?, status='Disponível' WHERE id=?", (qty, inv[0]))
        else:
            c.execute("INSERT INTO inventario_local (equipamento, marca, numero_serie, quantidade, status, data_registo, setor_id) VALUES (?,?,?,?,'Disponível',?,?)",
                      (equipamento, marca, numero_serie, qty, datetime.now().strftime("%Y-%m-%d"), setor_destino_id))
        
        c.execute("UPDATE movimentos SET status='RECEBIDO', estado_rastreio='RECEBIDO', confirmado_destino=? WHERE guia=?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), guia))
        conn.commit()
        flash(f"Recepção confirmada para a guia {guia}!")
    conn.close()
    return redirect(url_for('index'))

@app.route('/rejeitar_recepcao/<guia>', methods=['POST'])
def rejeitar_recepcao(guia):
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT equipamento, marca, numero_serie, quantidade, setor_origem_id FROM movimentos WHERE guia=? AND status='PENDENTE_RECEPCAO'", (guia,))
    mov = c.fetchone()
    if mov:
        equipamento, marca, numero_serie, quantidade, setor_origem_id = mov
        if setor_origem_id:
            c.execute("SELECT id, quantidade FROM inventario_local WHERE setor_id=? AND equipamento=? AND numero_serie=? AND marca=?", (setor_origem_id, equipamento, numero_serie, marca))
            inv = c.fetchone()
            qty = int(quantidade) if quantidade and str(quantidade).isdigit() else 1
            if inv:
                c.execute("UPDATE inventario_local SET quantidade=quantidade+?, status='Disponível' WHERE id=?", (qty, inv[0]))
            else:
                c.execute("INSERT INTO inventario_local (equipamento, marca, numero_serie, quantidade, status, data_registo, setor_id) VALUES (?,?,?,?,'Disponível',?,?)",
                          (equipamento, marca, numero_serie, qty, datetime.now().strftime("%Y-%m-%d"), setor_origem_id))
        c.execute("UPDATE movimentos SET status='REJEITADO' WHERE guia=?", (guia,))
        conn.commit()
        flash(f"Transferência da guia {guia} foi rejeitada e o material devolvido ao inventário de origem.")
    conn.close()
    return redirect(url_for('index'))

@app.route('/inventario')
def inventario():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    setor_id = session.get('setor_id')
    is_admin = session.get('perfil') == 'admin'
    
    # Setores que o utilizador pode visualizar (localização do utilizador)
    if is_admin:
        allowed = None  # o administrador pode aceder a todos os locais
    else:
        locais = get_locais_acesso()
        allowed = list(locais) if locais else ([setor_id] if setor_id else [0])
    
    # Filtro por local (setor): um ou vários, vindo do pedido
    filtro_raw = request.args.get('filtro_setor', '')
    if filtro_raw:
        chosen = [int(x) for x in filtro_raw.split(',') if x.strip().isdigit()]
    elif setor_id is not None:
        chosen = [setor_id]
    else:
        chosen = None
    
    if allowed is not None:
        chosen = [s for s in (chosen or []) if s in allowed] or allowed
    
    where_setor = ""
    params = []
    if chosen:
        ph = ','.join('?' * len(chosen))
        where_setor = f" AND i.setor_id IN ({ph})"
        params = list(chosen)
    
    # Base query for inventory (excluding Pending which is shown in a separate panel)
    c.execute(f'''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, 
                        i.data_registo, i.observacoes, i.setor_id, s.nome as setor_nome,
                        i.codigo_barras, i.estado, i.local_uso, i.provincia_id, p.nome as provincia_nome, i.documento_pdf, i.guia_origem
                 FROM inventario_local i 
                 LEFT JOIN setores s ON i.setor_id = s.id 
                 LEFT JOIN eleitoral_provincia p ON i.provincia_id = p.id
                 WHERE i.status != 'Pendente'{where_setor}
                 ORDER BY i.id DESC''', params)

    cols = [d[0] for d in c.description]
    items = [dict(zip(cols, r)) for r in c.fetchall()]
    
    # Load pending confirmation list (same scope as the inventory view)
    c.execute(f'''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, 
                        i.data_registo, i.observacoes, i.setor_id, s.nome as setor_nome, i.guia_origem,
                        i.codigo_barras, i.estado, i.local_uso, i.provincia_id, p.nome as provincia_nome
                 FROM inventario_local i 
                 LEFT JOIN setores s ON i.setor_id = s.id 
                 LEFT JOIN eleitoral_provincia p ON i.provincia_id = p.id
                 WHERE i.status = 'Pendente'{where_setor}
                 ORDER BY i.id DESC''', params)
    cols_p = [d[0] for d in c.description]
    pending_items = [dict(zip(cols_p, r)) for r in c.fetchall()]

    # Pendentes de transferência ENTRE PROVÍNCIAS (confirmar receção no destino)
    c.execute('''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, i.guia_origem,
                        i.codigo_barras, i.estado, i.local_uso, i.provincia_id, p.nome as provincia_destino_nome
                 FROM inventario_local i 
                 LEFT JOIN eleitoral_provincia p ON i.provincia_id = p.id
                 WHERE i.status = 'Pendente' AND i.provincia_id IS NOT NULL
                 ORDER BY i.id DESC''')
    cols_pp = [d[0] for d in c.description]
    provincias_pendentes = [dict(zip(cols_pp, r)) for r in c.fetchall()]
    
    # Calculate stats selectively based on user scope
    if chosen:
        cond_setor = " AND setor_id IN ({})".format(','.join('?' * len(chosen)))
        stats_params = list(chosen)
    else:
        cond_setor = ""
        stats_params = []
    
    c.execute("SELECT COUNT(*), SUM(quantidade) FROM inventario_local WHERE status != 'Pendente'" + cond_setor, stats_params)
    res = c.fetchone()
    total_qty = res[1] if res else 0
    
    c.execute("SELECT SUM(quantidade) FROM inventario_local WHERE status='Disponível'" + cond_setor, stats_params)
    disponiveis = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(quantidade) FROM inventario_local WHERE status='Em uso'" + cond_setor, stats_params)
    em_uso = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(quantidade) FROM inventario_local WHERE status IN ('Danificado', 'Avariado')" + cond_setor, stats_params)
    danificados = c.fetchone()[0] or 0
    
    stats = {
        'total': total_qty or 0,
        'disponiveis': disponiveis,
        'em_uso': em_uso,
        'danificados': danificados
    }
    
    c.execute("SELECT id, nome FROM setores")
    setores = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    if is_admin:
        setores_filtro = setores
    else:
        setores_filtro = [s for s in setores if s['id'] in (allowed or [])]
    filtro_ativo_ids = chosen or []
    nome_setor = {s['id']: s['nome'] for s in setores}
    if chosen is None:
        filtro_nome = 'STAE (Todos os Locais)'
    elif len(chosen) == 1:
        filtro_nome = nome_setor.get(chosen[0], 'Inventário')
    else:
        filtro_nome = 'STAE ({} Locais)'.format(len(chosen))
    titulo_pagina = 'INVENTÁRIO LOCAL - {}'.format(filtro_nome)
    c.execute("SELECT id, nome FROM marcas")
    marcas = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM tipos_equipamento")
    tipos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM motivos")
    motivos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM fornecedores")
    fornecedores = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM instituicoes")
    instituicoes = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM eleitoral_provincia ORDER BY nome")
    provincias = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    estados_intermedios = [
        'EM_ESTOQUE', 'EM_PREPARACAO', 'EMPACOTAMENTO',
        'A_ESPERA_ENVIO', 'EM_TRANSITO', 'RECEBIDO', 'EM_USO', 'AVARIADO'
    ]
    
    conn.close()
    return render_template_string(INVENTARIO_TEMPLATE, items=items, pending_items=pending_items, provincias_pendentes=provincias_pendentes, stats=stats, setores=setores, setores_filtro=setores_filtro, filtro_ativo_ids=filtro_ativo_ids, titulo_pagina=titulo_pagina, marcas=marcas, tipos=tipos, motivos=motivos, fornecedores=fornecedores, instituicoes=instituicoes, provincias=provincias, estados_intermedios=estados_intermedios, msg=request.args.get('msg'))

@app.route('/inventario/add', methods=['POST'])
def inventario_add():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    setor_id = request.form.get('setor_id')
    setor_val = int(setor_id) if (setor_id and setor_id != '' and setor_id != 'None') else None
    
    codigo_barras = request.form.get('codigo_barras', '').strip()
    provincia_id = request.form.get('provincia_id')
    prov_val = int(provincia_id) if (provincia_id and provincia_id != '' and provincia_id != 'None') else None
    
    documento_pdf = None
    if 'documento' in request.files:
        f = request.files['documento']
        if f and f.filename:
            ext = os.path.splitext(f.filename)[1].lower()
            nome_base = f"INV_DOC_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'):
                documento_pdf = imagem_para_pdf(f, nome_base)
            elif ext == '.pdf':
                nome = f"{nome_base}.pdf"
                caminho = os.path.join(UPLOAD_FOLDER, nome)
                f.save(caminho)
                documento_pdf = nome
    
    c.execute('''INSERT INTO inventario_local (equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, setor_id, codigo_barras, documento_pdf, provincia_id, local_uso, estado) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
              (request.form.get('equipamento'), request.form.get('marca'), request.form.get('numero_serie'), int(request.form.get('quantidade', 1)), request.form.get('status'), datetime.now().strftime("%Y-%m-%d"), request.form.get('observacoes', ''), setor_val, codigo_barras, documento_pdf, prov_val, request.form.get('local_uso', ''), request.form.get('estado', 'EM_ESTOQUE')))
    conn.commit()
    conn.close()
    return redirect(url_for('inventario', msg="Item adicionado ao inventário local!"))

@app.route('/inventario/edit/<int:item_id>', methods=['POST'])
def inventario_edit(item_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    setor_id = request.form.get('setor_id')
    setor_val = int(setor_id) if (setor_id and setor_id != '' and setor_id != 'None') else None
    c.execute('''UPDATE inventario_local SET 
                 equipamento=?, marca=?, numero_serie=?, quantidade=?, status=?, observacoes=?, setor_id=? 
                 WHERE id=?''', 
              (request.form.get('equipamento'), request.form.get('marca'), request.form.get('numero_serie'), int(request.form.get('quantidade', 1)), request.form.get('status'), request.form.get('observacoes', ''), setor_val, item_id))
    conn.commit()
    conn.close()
    return redirect(url_for('inventario', msg="Item do inventário atualizado!"))

@app.route('/inventario/delete/<int:item_id>', methods=['POST'])
def inventario_delete(item_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM inventario_local WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('inventario', msg="Item removido do inventário!"))

@app.route('/inventario/delete_multiple', methods=['POST'])
def inventario_delete_multiple():
    if 'username' not in session: return jsonify({'success': False, 'error': 'Não logado'}), 401
    data = request.get_json() or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'error': 'Nenhum ID fornecido'}), 400
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    placeholders = ','.join('?' for _ in ids)
    c.execute(f"DELETE FROM inventario_local WHERE id IN ({placeholders})", ids)
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/inventario/delete_all', methods=['POST'])
def inventario_delete_all():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM inventario_local")
    conn.commit()
    conn.close()
    return redirect(url_for('inventario', msg="Todo o inventário local foi removido com sucesso!"))

@app.route('/inventario/movimentar_multiplos', methods=['POST'])
def inventario_movimentar_multiplos():
    if 'username' not in session: return jsonify({'success': False, 'error': 'Não logado'}), 401
    data = request.get_json() or {}
    ids = data.get('ids', [])
    quantities = data.get('quantities', {})
    setor_destino_id = data.get('setor_destino_id')
    entregue_por = data.get('entregue_por', '')
    recebido_por = data.get('recebido_por', '')
    motivo = data.get('motivo', '')
    
    if not ids or not setor_destino_id:
        return jsonify({'success': False, 'error': 'Parâmetros incompletos.'}), 400
        
    setor_destino_id = int(setor_destino_id)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get target sector name
    c.execute("SELECT nome FROM setores WHERE id=?", (setor_destino_id,))
    res_dest = c.fetchone()
    dest_name = res_dest[0] if res_dest else f"Setor #{setor_destino_id}"
    
    try:
        # Step 1: Validate quantities first to abort early if there is any error
        for item_id in ids:
            qty_req = int(quantities.get(str(item_id)) or quantities.get(item_id) or 1)
            c.execute("SELECT equipamento, quantidade FROM inventario_local WHERE id=?", (item_id,))
            item = c.fetchone()
            if not item:
                return jsonify({'success': False, 'error': f'Item ID {item_id} não encontrado no inventário.'}), 400
            if item[1] < qty_req:
                return jsonify({'success': False, 'error': f'Quantidade solicitada para {item[0]} ({qty_req}) excede o stock disponível ({item[1]}).'}), 400
        
        # Step 2: Perform the movements
        for item_id in ids:
            qty_req = int(quantities.get(str(item_id)) or quantities.get(item_id) or 1)
            c.execute("SELECT equipamento, marca, numero_serie, quantidade, status, observacoes, setor_id FROM inventario_local WHERE id=?", (item_id,))
            eq_info = c.fetchone()
            equipamento, marca, numero_serie, qty_avail, status, observacoes, setor_origem_id = eq_info
            
            # Subtract stock
            new_qty = qty_avail - qty_req
            if new_qty == 0:
                c.execute("DELETE FROM inventario_local WHERE id=?", (item_id,))
            else:
                c.execute("UPDATE inventario_local SET quantidade=? WHERE id=?", (new_qty, item_id))
            
            # Generate unique guide prefix
            guia_code = generate_guia('TRANSF', c)
            
            # Insert or update pending item in target sector
            c.execute('''SELECT id, quantidade FROM inventario_local 
                         WHERE equipamento=? AND marca=? AND numero_serie=? AND status='Pendente' AND setor_id=? AND guia_origem=?''',
                      (equipamento, marca, numero_serie, setor_destino_id, guia_code))
            exists_pending = c.fetchone()
            if exists_pending:
                c.execute("UPDATE inventario_local SET quantidade=quantidade+? WHERE id=?", (qty_req, exists_pending[0]))
            else:
                c.execute('''INSERT INTO inventario_local (equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, setor_id, guia_origem) 
                             VALUES (?,?,?,?,?,?,?,?,?)''',
                          (equipamento, marca, numero_serie, qty_req, 'Pendente', datetime.now().strftime("%Y-%m-%d"), observacoes, setor_destino_id, guia_code))
            
            # Get origin sector name
            orig_name = "-"
            if setor_origem_id:
                c.execute("SELECT nome FROM setores WHERE id=?", (setor_origem_id,))
                res_orig = c.fetchone()
                orig_name = res_orig[0] if res_orig else f"Setor #{setor_origem_id}"
                
            # Log movement
            origem_destino_str = f"De {orig_name} para {dest_name}"
            c.execute('''INSERT INTO movimentos 
                (guia, tipo, equipamento, origem_destino, motivo, data, status, tecnico, funcionario_id, numero_serie, marca, entregue_por, recebido_por, quantidade, setor_origem_id, setor_destino_id) 
                VALUES (?, 'TRANSFERENCIA', ?, ?, ?, ?, 'Pendente', ?, NULL, ?, ?, ?, ?, ?, ?, ?)''',
                (guia_code, equipamento, origem_destino_str, motivo, datetime.now().strftime("%Y-%m-%d"), session['username'], numero_serie, marca, entregue_por, recebido_por, str(qty_req), setor_origem_id, setor_destino_id))
                
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': f'Erro interno: {e}'}), 500
        
    conn.close()
    return jsonify({'success': True})

@app.route('/inventario/confirmar_rececao/<int:item_id>', methods=['POST'])
def inventario_confirmar_rececao(item_id):
    if 'username' not in session: return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT equipamento, marca, numero_serie, quantidade, status, observacoes, setor_id, guia_origem FROM inventario_local WHERE id=? AND status='Pendente'", (item_id,))
    item = c.fetchone()
    if not item:
        conn.close()
        return redirect(url_for('inventario', msg="Erro: Item pendente não encontrado."))
        
    equipamento, marca, numero_serie, quantidade, status, observacoes, setor_id, guia_origem = item
    
    try:
        # Check if identical available item exists in sector
        c.execute('''SELECT id FROM inventario_local 
                     WHERE equipamento=? AND marca=? AND numero_serie=? AND status='Disponível' AND setor_id=?''',
                  (equipamento, marca, numero_serie, setor_id))
        exists_avail = c.fetchone()
        if exists_avail:
            c.execute("UPDATE inventario_local SET quantidade=quantidade+? WHERE id=?", (quantidade, exists_avail[0]))
            c.execute("DELETE FROM inventario_local WHERE id=?", (item_id,))
        else:
            c.execute("UPDATE inventario_local SET status='Disponível', guia_origem=NULL WHERE id=?", (item_id,))
            
        # Update movement status
        if guia_origem:
            c.execute("UPDATE movimentos SET status='Entregue' WHERE guia=?", (guia_origem,))
            
        conn.commit()
        msg = "Equipamento recebido e adicionado ao inventário disponível!"
    except Exception as e:
        conn.rollback()
        msg = f"Erro ao confirmar receção: {e}"
        
    conn.close()
    return redirect(url_for('inventario', msg=msg))

@app.route('/api/inventario_info/<int:item_id>')
def api_inventario_info(item_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM inventario_local WHERE id=?", (item_id,))
    cols = [d[0] for d in c.description]
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Item não encontrado'}), 404
    return jsonify(dict(zip(cols, row)))

@app.route('/registrar_saida_inventario/<int:item_id>', methods=['POST'])
def registrar_saida_inventario(item_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT * FROM inventario_local WHERE id=?", (item_id,))
    cols = [d[0] for d in c.description]
    row = c.fetchone()
    if not row:
        conn.close()
        return "Item de inventário não encontrado", 404
    item = dict(zip(cols, row))
    
    qty_to_remove = int(request.form.get('quantidade', 1))
    current_qty = int(item['quantidade'])
    
    if qty_to_remove > current_qty:
        conn.close()
        return f"Erro: Quantidade solicitada ({qty_to_remove}) é maior que a disponível ({current_qty}).", 400
        
    new_qty = current_qty - qty_to_remove
    new_status = 'Disponível' if new_qty > 0 else 'Indisponível'
    c.execute("UPDATE inventario_local SET quantidade=?, status=? WHERE id=?", (new_qty, new_status, item_id))
    
    guia_saida = f"SAI-{datetime.now().year}-{len(c.execute('SELECT id FROM movimentos').fetchall())+1:04d}"
    dep_inv_raw = request.form.get('departamento_responsavel_id', '').strip()
    try:
        dep_inv = int(dep_inv_raw) if dep_inv_raw else (session.get('setor_id'))
    except (TypeError, ValueError):
        dep_inv = session.get('setor_id')
    c.execute('''INSERT INTO movimentos (guia, tipo, equipamento, origem_destino, motivo, data, status, funcionario_id, numero_serie, marca, entregue_por, recebido_por, tecnico, agente_protecao, fornecedor, quantidade, departamento_responsavel_id) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
              (guia_saida, "SAIDA", item['equipamento'], request.form.get('destino'), request.form.get('motivo',''), datetime.now().strftime("%Y-%m-%d"), "Entregue", None, item['numero_serie'], item['marca'], request.form.get('entregue_por',''), request.form.get('recebido_por',''), session.get('nome_completo', session.get('username', 'tecnico')), request.form.get('agente_protecao',''), 'N/A', str(qty_to_remove), dep_inv))
              
    conn.commit()
    conn.close()
    return redirect(url_for('inventario', msg=f"Saída registada com sucesso! Guia de Saída: {guia_saida}"))

# ---------------------------------------------------------
# CLOUD SYNCHRONIZATION (OFFLINE-FIRST)
# ---------------------------------------------------------

@app.after_request
def trigger_sync_after_post(response):
    if request.method == 'POST':
        threading.Thread(target=sync_databases).start()
    return response

@app.route('/api/sync', methods=['POST'])
def api_sync():
    success = sync_databases()
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Não foi possível conectar ou sincronizar com o PostgreSQL Cloud'})

PG_URL = os.environ.get('DATABASE_URL') or os.environ.get('PG_URL') or "postgresql://neondb_owner:npg_3BsxjEU4NCki@ep-withered-truth-asbeszuu-pooler.c-4.eu-central-1.aws.neon.tech/equipamento?sslmode=require&channel_binding=require"

def get_pg_connection():
    try:
        conn = psycopg2.connect(PG_URL, connect_timeout=15)
        return conn
    except Exception as e:
        print(f"[-] Erro ao ligar ao PostgreSQL Cloud: {e}")
        return None

def init_pg_db():
    conn = get_pg_connection()
    if not conn:
        print("[-] PostgreSQL Cloud inacessível. Pulando inicialização da nuvem.")
        return
    c = conn.cursor()
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, 
            username VARCHAR UNIQUE, 
            password VARCHAR, 
            perfil VARCHAR, 
            nome_completo VARCHAR,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS setores (
            id SERIAL PRIMARY KEY, 
            nome VARCHAR UNIQUE,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS funcionarios (
            id SERIAL PRIMARY KEY, 
            nome VARCHAR, 
            cargo VARCHAR, 
            setor_id INTEGER,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS movimentos (
            id SERIAL PRIMARY KEY, 
            guia VARCHAR UNIQUE, 
            tipo VARCHAR, 
            equipamento VARCHAR, 
            origem_destino VARCHAR, 
            motivo VARCHAR, 
            data VARCHAR, 
            status VARCHAR, 
            tecnico VARCHAR, 
            relatorio VARCHAR, 
            funcionario_id INTEGER, 
            numero_serie VARCHAR, 
            marca VARCHAR, 
            entregue_por VARCHAR, 
            recebido_por VARCHAR, 
            agente_protecao VARCHAR, 
            fornecedor VARCHAR, 
            quantidade VARCHAR,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS marcas (
            id SERIAL PRIMARY KEY, 
            nome VARCHAR UNIQUE,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS tipos_equipamento (
            id SERIAL PRIMARY KEY, 
            nome VARCHAR UNIQUE,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS motivos (
            id SERIAL PRIMARY KEY, 
            nome VARCHAR UNIQUE,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS fornecedores (
            id SERIAL PRIMARY KEY, 
            nome VARCHAR UNIQUE,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS instituicoes (
            id SERIAL PRIMARY KEY, 
            nome VARCHAR UNIQUE,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS inventario_local (
            id SERIAL PRIMARY KEY, 
            equipamento VARCHAR, 
            marca VARCHAR, 
            numero_serie VARCHAR, 
            quantidade INTEGER DEFAULT 1, 
            status VARCHAR DEFAULT 'Disponível', 
            data_registo VARCHAR, 
            observacoes VARCHAR,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS equipamento_rastreio (
            id SERIAL PRIMARY KEY,
            guia VARCHAR,
            equipamento VARCHAR,
            marca VARCHAR,
            numero_serie VARCHAR,
            estado VARCHAR,
            local_atual VARCHAR,
            observacoes VARCHAR,
            data VARCHAR,
            utilizador VARCHAR,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS equipamento_estado_historico (
            id SERIAL PRIMARY KEY,
            guia VARCHAR,
            equipamento VARCHAR,
            numero_serie VARCHAR,
            estado VARCHAR,
            observacoes VARCHAR,
            data VARCHAR,
            utilizador VARCHAR,
            last_modified VARCHAR DEFAULT '2026-06-24T00:00:00',
            origem_registo VARCHAR DEFAULT 'local'
        )''')
        try:
            migrar_schema_eleitoral(c, True)
        except Exception as ex:
            conn.rollback()
            print(f"[-] Erro na migração do schema eleitoral (PG): {ex}")
        
        # Ensure all columns exist in PostgreSQL (automatic migration)
        tables = ['users', 'setores', 'funcionarios', 'movimentos', 'marcas', 'tipos_equipamento', 'motivos', 'fornecedores', 'instituicoes', 'inventario_local', 'eleitoral_provincia', 'eleitoral_pais_diaspora', 'eleitoral_local_armazenamento', 'eleitoral_categoria_material', 'eleitoral_tipo_material', 'eleitoral_processo_eleitoral', 'eleitoral_material_sobrante', 'eleitoral_evento', 'eleitoral_movimento_material', 'eleitoral_movimento_historico', 'equipamento_rastreio', 'equipamento_estado_historico']
        
        # Create trigger function for PG
        try:
            c.execute('''
                CREATE OR REPLACE FUNCTION update_last_modified_column()
                RETURNS TRIGGER AS $$
                BEGIN
                   NEW.last_modified = to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS');
                   RETURN NEW;
                END;
                $$ language 'plpgsql';
            ''')
        except Exception as ex:
            conn.rollback()
            print(f"[-] Erro ao criar funcao de trigger no PG: {ex}")
            
        for t in tables:
            try:
                c.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS last_modified VARCHAR DEFAULT '2026-06-24T00:00:00'")
            except Exception as ex:
                conn.rollback()
                print(f"[-] Erro ao migrar last_modified no PG para {t}: {ex}")
            try:
                c.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS origem_registo VARCHAR DEFAULT 'local'")
            except Exception as ex:
                conn.rollback()
                print(f"[-] Erro ao migrar origem_registo no PG para {t}: {ex}")
                
            try:
                c.execute(f'''
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'tr_update_last_modified_{t}') THEN
                            CREATE TRIGGER tr_update_last_modified_{t}
                            BEFORE UPDATE ON {t}
                            FOR EACH ROW
                            WHEN (NEW.last_modified IS NULL OR NEW.last_modified = OLD.last_modified)
                            EXECUTE FUNCTION update_last_modified_column();
                        END IF;
                    END
                    $$;
                ''')
            except Exception as ex:
                conn.rollback()
                print(f"[-] Erro ao criar trigger no PG para {t}: {ex}")
                
        try:
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS setor_id INTEGER")
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissoes_estado VARCHAR")
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS locais_acesso VARCHAR")
            c.execute("ALTER TABLE movimentos ADD COLUMN IF NOT EXISTS setor_origem_id INTEGER")
            c.execute("ALTER TABLE movimentos ADD COLUMN IF NOT EXISTS setor_destino_id INTEGER")
            c.execute("ALTER TABLE movimentos ADD COLUMN IF NOT EXISTS departamento_responsavel_id INTEGER")
        except Exception as ex:
            conn.rollback()
            print(f"[-] Erro ao migrar novas colunas de setor no PG: {ex}")
                
        c.execute("UPDATE inventario_local SET status='Disponível' WHERE status='Disponvel'")
        c.execute("UPDATE inventario_local SET status='Indisponível' WHERE status='Indisponvel'")
        conn.commit()
        print("[+] Tabelas inicializadas/verificadas no PostgreSQL Cloud.")
    except Exception as e:
        if conn: conn.rollback()
        print(f"[-] Erro ao inicializar tabelas no PostgreSQL: {e}")
    finally:
        conn.close()

def run_startup_sync():
    init_pg_db()
    sync_databases()

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
    'inventario_local': ['equipamento', 'marca', 'numero_serie'],
    'eleitoral_provincia': ['codigo'],
    'eleitoral_pais_diaspora': ['codigo_iso'],
    'eleitoral_local_armazenamento': ['tipo', 'nome'],
    'eleitoral_categoria_material': ['nome'],
    'eleitoral_tipo_material': ['nome', 'variante'],
    'eleitoral_processo_eleitoral': ['nome', 'ano'],
    'eleitoral_material_sobrante': ['processo_id', 'local_id', 'tipo_material_id'],
    'eleitoral_evento': ['processo_id', 'nome'],
    'eleitoral_movimento_material': ['processo_id', 'local_origem_id', 'local_destino_id', 'data_envio'],
    'equipamento_rastreio': ['guia', 'estado', 'data'],
    'equipamento_estado_historico': ['guia', 'estado', 'data']
}

def get_table_columns(cursor, table_name, is_pg=False):
    if is_pg:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table_name,))
        return [row[0] for row in cursor.fetchall() if row[0] != 'id']
    else:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor.fetchall() if row[1] != 'id']

def normalize_pg_schema(pg_c):
    try:
        pg_c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'funcionarios' AND column_name = 'sector_id'")
        if pg_c.fetchone():
            pg_c.execute("ALTER TABLE funcionarios RENAME COLUMN sector_id TO setor_id")
            print("[+] Renomeada coluna 'sector_id' para 'setor_id' no PostgreSQL.")
    except Exception as e:
        print("[-] Erro ao normalizar esquema no PG:", e)

def sync_schema_dynamic(s_c, pg_c, table_name):
    s_cols = get_table_columns(s_c, table_name, is_pg=False)
    pg_cols = get_table_columns(pg_c, table_name, is_pg=True)
    
    for col in s_cols:
        if col not in pg_cols:
            print(f"[*] Nova coluna detetada localmente: Adicionando '{col}' à tabela '{table_name}' na Nuvem.")
            try:
                pg_c.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} VARCHAR")
            except Exception as e:
                print(f"[-] Erro ao adicionar '{col}' ao PG: {e}")
                
    for col in pg_cols:
        if col not in s_cols:
            print(f"[*] Nova coluna detetada na Nuvem: Adicionando '{col}' à tabela '{table_name}' localmente.")
            try:
                s_c.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} TEXT")
            except Exception as e:
                print(f"[-] Erro ao adicionar '{col}' ao SQLite: {e}")

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
        key = tuple(str(d.get(k, '')) for k in unique_keys)
        res[key] = d
    return res

def sync_table_dynamic(s_conn, pg_conn, table_name, unique_keys):
    s_c = s_conn.cursor()
    pg_c = pg_conn.cursor()
    
    sync_schema_dynamic(s_c, pg_c, table_name)
    columns = get_common_columns(s_c, pg_c, table_name)
    
    if 'last_modified' not in columns or 'origem_registo' not in columns:
        print(f"[-] Sincronização ignorada para '{table_name}': Faltam as colunas de controlo.")
        return
        
    s_records = get_records_dict(s_c, table_name, columns, unique_keys, is_pg=False)
    pg_records = get_records_dict(pg_c, table_name, columns, unique_keys, is_pg=True)
    
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

def sync_databases():
    if is_cloud_mode():
        return True
    
    pg_conn = get_pg_connection()
    if not pg_conn:
        print("[-] Sincronização cancelada: PostgreSQL Cloud inacessível.")
        return False
        
    s_conn = sqlite3.connect(DB_PATH)
    
    print("[*] A iniciar Sincronização Dinâmica Bidirecional...")
    try:
        normalize_pg_schema(pg_conn.cursor())
        pg_conn.commit()
        
        for table_name, unique_keys in SYNC_CONFIG.items():
            sync_table_dynamic(s_conn, pg_conn, table_name, unique_keys)
            
        pg_conn.commit()
        s_conn.commit()
        print("[+] Sincronização Dinâmica Bidirecional concluída com sucesso!")
        return True
    except Exception as e:
        print(f"[-] Erro durante a sincronização: {e}")
        return False
    finally:
        pg_conn.close()
        s_conn.close()

init_db()

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routes_eleitoral import eleitoral_bp
app.register_blueprint(eleitoral_bp)

@app.route('/mapa_mozambique.svg')
def mapa_mozambique():
    caminho = os.path.join(BASE_DIR, 'static', 'mozambique.svg')
    if os.path.exists(caminho):
        return send_file(caminho, mimetype='image/svg+xml')
    return "Mapa não encontrado", 404

if __name__ == '__main__':
    # Executa a sincronização inteligente apenas se estiver em modo local
    if not is_cloud_mode():
        print("[*] Ambiente local detetado. Iniciando sincronização bidirecional...")
        run_startup_sync()
        
    Timer(1.5, lambda: webbrowser.open('http://127.0.0.1:5000')).start()
    app.run(host='127.0.0.1', port=5000, debug=os.environ.get('FLASK_DEBUG', '') == '1')

