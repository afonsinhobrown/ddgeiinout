import os
import sqlite3
import webbrowser
from datetime import datetime
from threading import Timer
import threading
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_file, session, flash
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import hashlib
import io
import psycopg2
import socket

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
def is_cloud_mode():
    return (
        os.environ.get('CLOUD_MODE') == 'true' or
        os.environ.get('VERCEL') == '1' or
        os.environ.get('RENDER') == 'true' or
        os.environ.get('ORIGEM_CADASTRO') == 'nuvem'
    )

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
        
        c.execute("PRAGMA table_info(users)")
        u_cols = [row[1] for row in c.fetchall()]
        if 'setor_id' not in u_cols: 
            c.execute("ALTER TABLE users ADD COLUMN setor_id INTEGER")
            c.execute("UPDATE users SET setor_id = 1 WHERE perfil != 'admin' AND setor_id IS NULL")
        
        tables = ['users', 'setores', 'funcionarios', 'movimentos', 'marcas', 'tipos_equipamento', 'motivos', 'fornecedores', 'instituicoes', 'inventario_local']
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
    except Exception as e:
        print(f"[-] Erro na verificação de integridade: {e}")

def create_triggers(c):
    origem_padrao = os.environ.get("ORIGEM_CADASTRO") or "local"
    tables = ['users', 'setores', 'funcionarios', 'movimentos', 'marcas', 'tipos_equipamento', 'motivos', 'fornecedores', 'instituicoes', 'inventario_local']
    for t in tables:
        c.execute(f'''
            CREATE TRIGGER IF NOT EXISTS tr_insert_{t}
            AFTER INSERT ON {t}
            BEGIN
                UPDATE {t} SET 
                    last_modified = datetime('now', 'localtime'),
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
                UPDATE {t} SET last_modified = datetime('now', 'localtime') WHERE id = old.id;
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
        observacoes TEXT
    )''')
    check_db_integrity(c)
    
    try: c.execute("ALTER TABLE users ADD COLUMN nome_completo TEXT")
    except: pass
    
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        for u, p, perf in [("admin", "admin123", "admin"), ("tecnico", "tecnico123", "tecnico"), ("protecao", "protecao123", "protecao")]:
            c.execute("INSERT INTO users (username, password, perfil, nome_completo) VALUES (?,?,?,?)", (u, hashlib.md5(p.encode()).hexdigest(), perf, u))
            
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
</head>
<body>
    <div class="nav">
        <strong>STAE RELATÓRIOS E ESTATÍSTICAS</strong>
        <div>
            <a href="/" class="btn btn-outline" style="background:white; color:#0f172a; margin-right:1rem">⬅️ Voltar ao Início</a>
            <a href="/relatorio_pdf" target="_blank" class="btn btn-blue">📄 Imprimir Relatório Geral PDF</a>
        </div>
    </div>
    <div class="container">
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:2rem;">
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
        <div>👤 {{session.nome}} ({{session.perfil}}) | <a href="/logout" style="color:white">Sair</a></div>
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
            <a href="/inventario" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a">📦 Inventário DDGEI</a>
            <a href="/movimentos" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a">📋 Todos os Movimentos</a>
            {% if session.perfil == 'admin' %}
            <a href=\"/relatorios\" class=\"btn btn-outline\" style=\"background:#e2e8f0; color:#0f172a\"> 📊 Dashboard de Relatórios</a>
            <a href=\"/cadastros\" class=\"btn btn-outline\" style=\"background:#e2e8f0; color:#0f172a\"> ⚙️ Cadastros</a>
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
            <form method="POST" action="/registrar_entrada">
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
                    <div><label>Origem</label>
                        <select name="origem" required>
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
                </div>
                <button type="submit" class="btn btn-green" style="margin-top:1.5rem; width:100%">CONFIRMAR ENTRADA</button>
            </form>
        </div>

        <div id="sai" class="card hidden">
            <h3>Nova Saída</h3>
            <form method="POST" action="/registrar_saida">
                <div style="background: #f8fafc; padding: 1rem; border-radius: 0.5rem; border: 1px dashed var(--border); margin-bottom: 1.5rem;">
                    <label style="font-weight: bold; color: #1e293b; display: block; margin-bottom: 0.5rem;">📦 Retirar do Inventário Local DDGEI (Opcional)</label>
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
                    <th style="padding:1rem">S/N</th><th style="padding:1rem">ORIGEM/DESTINO</th>
                    <th style="padding:1rem">STATUS</th><th style="padding:1rem">DATA</th><th style="padding:1rem">ACÇÕES</th>
                </tr>
                {% for m in movimentos %}
                <tr style="border-bottom:1px solid var(--border)">
                    <td style="padding:1rem"><strong>{{m.guia[:8]}}</strong><br>{{m.guia[8:]}}</td>
                    <td style="padding:1rem">{{m.equipamento}}<br><small style="color:#64748b">({{m.marca}})</small></td>
                    <td style="padding:1rem">{{m.numero_serie}}</td>
                    <td style="padding:1rem">{{m.origem_destino}}</td>
                    <td style="padding:1rem">{{m.status}}</td>
                    <td style="padding:1rem">{{m.data[:10]}}<br><small style="color:#64748b">{{m.data[11:]}}</small></td>
                    <td style="padding:1rem">
                        <button onclick="toggleDetails('det_{{loop.index}}')" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-right:0.3rem;">Detalhes</button>
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
                        <label>Origem (Leitura Apenas)</label>
                        <input type="text" value="DEPARTAMENTO DE DELIMITAÇÃO GEOGRÁFICA, ESTATÍSTICA E INFORMÁTICA" readonly style="background:#f1f5f9; color:#475569;">
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
</body></html>'''

CADASTROS_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>Cadastros - STAE</title>
<style>
    .card table td { border-bottom: 1px solid #f1f5f9; padding: 0.5rem 0; }
</style>
</head>
<body>
    <div class="nav"><strong>STAE GESTÃO - ADMINISTRAÇÃO</strong><div><a href="/" style="color:white">⬅️ Voltar ao Início</a></div></div>
    <div class="container">
        {% if msg %}<div style="background:#dcfce3; color:#166534; padding:1rem; border-radius:0.5rem; margin-bottom:1rem;">{{msg}}</div>{% endif %}
        
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
                    <button class="btn" style="background:#1e293b; color:white; margin-top:1rem; width:100%">Salvar Usuário</button>
                </form>
                <h4 style="margin-top:2rem">Usuários do Sistema</h4>
                <table style="margin-top:0.5rem">
                    {% for u in users_list %}
                    <tr>
                        <td style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                            <div>
                                <span style="font-weight: 600;">{{u.nome_completo}}</span><br>
                                <small style="color:#64748b;">{{u.username}} ({{u.perfil}})</small>
                            </div>
                            <div style="display:flex; gap:0.25rem; align-items:center;">
                                <button onclick="openEdit('/edit_user/{{u.id}}', 'Editar Usuário', [{label:'Nome Completo', name:'nome_completo', type:'text', value:'{{u.nome_completo}}', required:true}, {label:'Username', name:'username', type:'text', value:'{{u.username}}', required:true}, {label:'Perfil', name:'perfil', type:'select', value:'{{u.perfil}}', options:[{value:'admin',text:'Administrador'},{value:'tecnico',text:'Técnico'},{value:'protecao',text:'Protecção'}]}, {label:'Setor', name:'setor_id', type:'select', value:'{{u.setor_id or ""}}', options:[{value:'',text:'Nenhum'}, {% for s in setores %}{value:'{{s.id}}',text:'{{s.nome}}'},{% endfor %}]}, {label:'Nova Senha (Opcional)', name:'password', type:'password', value:'', required:false}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
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
        <div class="card" style="width:400px; max-width:90%;">
            <h3 id="editTitle">Editar</h3>
            <form id="editForm" method="POST" action="">
                <div id="editFields" style="display:flex; flex-direction:column; gap:1rem; margin-bottom:1rem;"></div>
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
                } else {
                    container.innerHTML += `<label>${f.label}</label><input type="${f.type}" name="${f.name}" value="${f.value}" ${f.required?'required':''} placeholder="${f.placeholder||''}">`;
                }
            });
            document.getElementById('editModal').style.display = 'flex';
        }
    </script>
</body></html>
'''

INVENTARIO_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>Inventário Local - DDGEI</title>
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
        <strong>STAE GESTÃO - INVENTÁRIO LOCAL (DDGEI)</strong>
        <div>
            <button id="syncBtn" onclick="syncCloud()" class="btn btn-outline" style="background:#10b981; color:white; border:none; margin-right:1rem; padding: 0.4rem 0.8rem; font-weight:bold; cursor:pointer; transition: all 0.3s;">🔄 Sincronizar Nuvem</button>
            <a href="/" class="btn btn-outline" style="background:white; color:#0f172a; margin-right:1.5rem; padding: 0.4rem 0.8rem;">⬅️ Voltar ao Início</a>
            <span>👤 {{session.username}}</span>
        </div>
    </div>
    <div class="container">
        {% if msg %}<div style="background:#dcfce3; color:#166534; padding:1rem; border-radius:0.5rem; margin-bottom:1rem;">{{msg}}</div>{% endif %}
        
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

        <div style="display: grid; grid-template-columns: 350px 1fr; gap: 1.5rem; align-items: start;">
            <div class="card">
                <h3>Cadastrar Equipamento</h3>
                <form method="POST" action="/inventario/add" style="margin-top: 1rem; display: flex; flex-direction: column; gap: 1rem;">
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
                            <th style="padding:0.75rem">STATUS</th>
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
                        <label>Origem (Leitura Apenas)</label>
                        <input type="text" value="DEPARTAMENTO DE DELIMITAÇÃO GEOGRÁFICA, ESTATÍSTICA E INFORMÁTICA" readonly style="background:#f1f5f9; color:#475569;">
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
                tbody.innerHTML = `<tr><td colspan="8" style="padding:1.5rem; text-align:center; color:#64748b;">Nenhum equipamento correspondente encontrado.</td></tr>`;
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
                    
                    const isChecked = selectedIds.has(item.id) ? 'checked' : '';
                    const actionSaida = (item.quantidade > 0 && item.status === 'Disponível') 
                        ? `<button onclick="abrirSaidaRapidaInventario(${item.id})" class="btn btn-green" style="padding:0.25rem 0.5rem; font-size:0.75rem; margin-top:0;">Saída</button>` 
                        : '';
                        
                    const tr = document.createElement("tr");
                    tr.style.borderBottom = "1px solid var(--border)";
                    tr.innerHTML = `
                        <td style="padding:0.75rem;"><input type="checkbox" class="row-checkbox" value="${item.id}" data-qty="${item.quantidade}" ${isChecked} onclick="toggleSelectRow(this, ${item.id})"></td>
                        <td style="padding:0.75rem; font-weight: 600;">${item.equipamento}</td>
                        <td style="padding:0.75rem">${item.marca}</td>
                        <td style="padding:0.75rem; font-family: monospace;">${item.numero_serie}</td>
                        <td style="padding:0.75rem; text-align: center; font-weight: bold;">${item.quantidade}</td>
                        <td style="padding:0.75rem; color:#475569;">${item.setor_nome || '-'}</td>
                        <td style="padding:0.75rem">${statusSpan}</td>
                        <td style="padding:0.75rem; text-align: right; display:flex; gap:0.25rem; justify-content: flex-end; align-items: center;">
                            ${actionSaida}
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
    </script>
</body></html>'''

@app.before_request
def auth():
    if request.path.startswith('/static'): return
    if request.path == '/login': return
    if 'username' not in session: return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = hashlib.md5(request.form['password'].encode()).hexdigest()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT perfil, nome_completo, setor_id FROM users WHERE username=? AND password=?", (u, p))
        res = c.fetchone()
        conn.close()
        if res:
            session['username'] = u
            session['perfil'] = res[0]
            session['nome_completo'] = res[1] or u
            session['setor_id'] = res[2]
            return redirect(url_for('index'))
    return render_template_string(LOGIN_TEMPLATE)

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
        'relatorios', 'relatorios_export', 'eliminar_movimento'
    ]
    
    if request.endpoint in admin_only_endpoints:
        if session.get('perfil') != 'admin':
            return "Erro: Acesso negado. Apenas administradores t&ecirc;m permiss&atilde;o para aceder a esta p&aacute;gina.", 403


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
                    <th style="padding:1rem">ORIGEM/DESTINO</th>
                    <th style="padding:1rem">STATUS</th>
                    <th style="padding:1rem">DATA</th>
                    <th style="padding:1rem">ACÇÕES</th>
                </tr>
                {% for m in movimentos %}
                <tr class="mov-row" data-index="{{loop.index}}" style="border-bottom:1px solid var(--border)">
                    <td style="padding:1rem"><strong>{{m.guia[:8]}}</strong><br>{{m.guia[8:]}}</td>
                    <td style="padding:1rem">{{m.equipamento}}<br><small style="color:#64748b">({{m.marca}})</small></td>
                    <td style="padding:1rem">{{m.numero_serie}}</td>
                    <td style="padding:1rem">{{m.origem_destino}}</td>
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
        c.execute("SELECT * FROM movimentos WHERE setor_origem_id=? OR setor_destino_id=? ORDER BY id DESC LIMIT 50", (setor_id, setor_id))
    
    cols = [d[0] for d in c.description]
    movimentos = [dict(zip(cols, r)) for r in c.fetchall()]
    
    c.execute("SELECT id, nome FROM funcionarios")
    func_map = {str(r[0]): r[1] for r in c.fetchall()}
    
    for m in movimentos:
        m['entregue_nome'] = func_map.get(str(m.get('entregue_por')), m.get('entregue_por') or '-')
        m['recebido_nome'] = func_map.get(str(m.get('recebido_por')), m.get('recebido_por') or '-')
        m['protecao_nome'] = func_map.get(str(m.get('agente_protecao')), m.get('agente_protecao') or '-')
        
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
        c.execute("SELECT id, equipamento, marca, numero_serie, quantidade FROM inventario_local WHERE setor_id=? AND status!='Pendente' ORDER BY equipamento", (setor_id,))
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
    
    c.execute("SELECT COUNT(*) FROM movimentos WHERE tipo='ENTRADA' AND status LIKE '%repara%'")
    row_count = c.fetchone()
    em_reparacao = row_count[0] if row_count else 0
    
    conn.close()
    return render_template_string(MAIN_TEMPLATE, msg=msg, username=session['username'], perfil=session.get('perfil'), movimentos=movimentos, pendentes=pendentes, inv_items=inv_items, setores=setores, marcas=marcas, tipos=tipos, motivos=motivos, fornecedores=fornecedores, instituicoes=instituicoes, em_reparacao=em_reparacao)


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
        c.execute("SELECT * FROM movimentos WHERE setor_origem_id=? OR setor_destino_id=? ORDER BY id DESC", (setor_id, setor_id))
        
    cols = [d[0] for d in c.description]
    movs = [dict(zip(cols, r)) for r in c.fetchall()]
    
    c.execute("SELECT id, nome FROM funcionarios")
    func_map = {str(r[0]): r[1] for r in c.fetchall()}
    
    for m in movs:
        m['entregue_nome'] = func_map.get(str(m.get('entregue_por')), m.get('entregue_por') or '-')
        m['recebido_nome'] = func_map.get(str(m.get('recebido_por')), m.get('recebido_por') or '-')
        m['protecao_nome'] = func_map.get(str(m.get('agente_protecao')), m.get('agente_protecao') or '-')
        
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    guia = f"ENT-{datetime.now().year}-{len(c.execute('SELECT id FROM movimentos').fetchall())+1:04d}"
    
    c.execute('''INSERT INTO movimentos (guia, tipo, equipamento, origem_destino, motivo, data, status, funcionario_id, numero_serie, marca, entregue_por, recebido_por, tecnico, agente_protecao, fornecedor, quantidade, setor_origem_id, setor_destino_id) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
              (guia, "ENTRADA", request.form['equipamento'], request.form['origem'], request.form.get('motivo',''), datetime.now().strftime("%Y-%m-%d"), "Em estoque", None, request.form['numero_serie'], request.form.get('marca',''), request.form.get('entregue_por',''), request.form.get('recebido_por',''), session.get('nome_completo', session.get('username', 'tecnico')), request.form.get('agente_protecao',''), request.form.get('fornecedor', 'N/A'), request.form.get('quantidade', '1'), None, session.get('setor_id')))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/registrar_saida', methods=['POST'])
def registrar_saida():
    if 'username' not in session: return redirect(url_for('login'))
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
        
    setor_origem_id = session.get('setor_id')
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
                new_status = 'Disponvel' if new_qty > 0 else 'Indisponvel'
                c.execute("UPDATE inventario_local SET quantidade=?, status=? WHERE id=?", (new_qty, new_status, inv_id))
        except Exception as e:
            print(f"Erro ao atualizar inventrio: {e}")
            
    guia = f"SAI-{datetime.now().year}-{len(c.execute('SELECT id FROM movimentos').fetchall())+1:04d}"
    status_movimento = "PENDENTE_RECEPCAO" if setor_destino_id else "Entregue"
    
    c.execute('''INSERT INTO movimentos (guia, tipo, equipamento, origem_destino, motivo, data, status, funcionario_id, numero_serie, marca, entregue_por, recebido_por, tecnico, agente_protecao, fornecedor, quantidade, setor_origem_id, setor_destino_id) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
              (guia, "SAIDA", request.form['equipamento'], origem_destino, request.form.get('motivo',''), datetime.now().strftime("%Y-%m-%d"), status_movimento, None, request.form['numero_serie'], request.form.get('marca',''), request.form.get('entregue_por',''), request.form.get('recebido_por',''), session.get('nome_completo', session.get('username', 'tecnico')), request.form.get('agente_protecao',''), request.form.get('fornecedor', 'N/A'), str(qty_to_remove), setor_origem_id, setor_destino_id))
    conn.commit()
    conn.close()
    flash("Sada registada com sucesso!")
    return redirect(url_for('index'))

@app.route('/registrar_saida_reparacao/<original_guia>', methods=['POST'])
def registrar_saida_reparacao(original_guia):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT id FROM movimentos WHERE guia=?", (original_guia,))
    original = c.fetchone()
    if not original:
        conn.close()
        return "Movimento original não encontrado", 404
        
    guia_saida = f"SAI-{datetime.now().year}-{len(c.execute('SELECT id FROM movimentos').fetchall())+1:04d}"
    
    equipamento = request.form.get('equipamento')
    marca = request.form.get('marca')
    numero_serie = request.form.get('numero_serie')
    destino = request.form.get('destino')
    motivo = request.form.get('motivo', '')
    fornecedor = request.form.get('fornecedor', 'N/A')
    quantidade = request.form.get('quantidade', '1')
    
    entregue_por = request.form.get('entregue_por', '')
    recebido_por = request.form.get('recebido_por', '')
    agente_protecao = request.form.get('agente_protecao', '')
    
    c.execute('''INSERT INTO movimentos (guia, tipo, equipamento, origem_destino, motivo, data, status, funcionario_id, numero_serie, marca, entregue_por, recebido_por, tecnico, agente_protecao, fornecedor, quantidade) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
              (guia_saida, "SAIDA", equipamento, destino, motivo, datetime.now().strftime("%Y-%m-%d"), "Entregue", None, numero_serie, marca, entregue_por, recebido_por, session.get('nome_completo', session.get('username', 'tecnico')), agente_protecao, fornecedor, quantidade))
              
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
    c.execute("SELECT id, username, perfil, nome_completo, setor_id FROM users")
    users_data = [{'id':r[0], 'username':r[1], 'perfil':r[2], 'nome_completo':r[3] or r[1], 'setor_id':r[4]} for r in c.fetchall()]
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
    conn.close()
    return render_template_string(CADASTROS_TEMPLATE, setores=setores, funcionarios=funcs, users_list=users_data, marcas=marcas, tipos=tipos, motivos=motivos, fornecedores=fornecedores, instituicoes=instituicoes, msg=request.args.get('msg'))



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
    pwd = hashlib.md5(request.form['password'].encode()).hexdigest()
    try:
        setor_val = request.form.get('setor_id')
        setor_val = int(setor_val) if (setor_val and setor_val != '' and setor_val != 'None') else None
        c.execute("INSERT INTO users (username, password, perfil, nome_completo, setor_id) VALUES (?,?,?,?,?)", (request.form['username'], pwd, request.form['perfil'], request.form.get('nome_completo'), setor_val))
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
    if pwd:
        hashed = hashlib.md5(pwd.encode()).hexdigest()
        c.execute("UPDATE users SET nome_completo=?, username=?, perfil=?, password=?, setor_id=? WHERE id=?", (nome_completo, username, perfil, hashed, setor_val, id))
    else:
        c.execute("UPDATE users SET nome_completo=?, username=?, perfil=?, setor_id=? WHERE id=?", (nome_completo, username, perfil, setor_val, id))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Utilizador atualizado!"))


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
    conn.close()
    
    if not row: return "Guia não encontrada", 404
    r = dict(zip(cols, row))
        
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
    c_pdf.drawCentredString(width/2, y-36, "DEPARTAMENTO DE DELIMITAÇÃO GEOGRÁFICA ESTATÍSTICA E INFORMÁTICA")
    
    c_pdf.setFont("Helvetica-Bold", 12)
    c_pdf.drawCentredString(width/2, y-66, "Ficha de Controlo")
    c_pdf.setFont("Helvetica", 11)
    c_pdf.drawCentredString(width/2, y-80, "MOVIMENTO DE EQUIPAMENTO INFORMÁTICO")
    
    c_pdf.setFont("Helvetica", 10)
    is_entrada = (r.get('tipo', '').upper() == "ENTRADA")
    
    if is_entrada:
        origem = r.get('origem_destino', '') or ""
        destino = "STAE - DDGEI"
        motivo = r.get('motivo', '') or ""
        c_pdf.drawString(50, y-115, "O Equipamento abaixo descrito foi RECEBIDO de (1):")
        c_pdf.drawString(50, y-130, f"{origem}")
        c_pdf.line(50, y-132, 500, y-132)
        
        c_pdf.drawString(50, y-150, f"Para STAE - DDGEI")
        c_pdf.line(80, y-152, 500, y-152)
    else:
        origem = "STAE - DDGEI"
        destino = r.get('origem_destino', '') or ""
        motivo = r.get('motivo', '') or ""
        c_pdf.drawString(50, y-115, "O Equipamento abaixo descrito é RETIRADO de (1) STAE - DDGEI")
        
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
    c_pdf.drawCentredString(150, y_box2 - 55, "O Chefe de Departamento de Informática")
    
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
    setor_id = request.args.get('setor_id', '')
    status = request.args.get('status', '')
    marca = request.args.get('marca', '')
    tipo_equipamento = request.args.get('tipo_equipamento', '')
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')
    mov_tipo = request.args.get('mov_tipo', '')
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Load filter lists
    c.execute("SELECT id, nome FROM setores")
    setores = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM marcas")
    marcas = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM tipos_equipamento")
    tipos_eq = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    
    items = []
    
    if tab == 'inventario':
        query = '''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, 
                          i.data_registo, i.observacoes, s.nome as setor_nome 
                   FROM inventario_local i 
                   LEFT JOIN setores s ON i.setor_id = s.id 
                   WHERE i.status != 'Pendente' '''
        params = []
        if setor_id:
            query += " AND i.setor_id = ?"
            params.append(int(setor_id))
        if status:
            query += " AND i.status = ?"
            params.append(status)
        if marca:
            query += " AND i.marca = ?"
            params.append(marca)
        if tipo_equipamento:
            query += " AND i.equipamento = ?"
            params.append(tipo_equipamento)
            
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
        if setor_id:
            query += " AND (m.setor_origem_id = ? OR m.setor_destino_id = ?)"
            params.extend([int(setor_id), int(setor_id)])
        if marca:
            query += " AND m.marca = ?"
            params.append(marca)
        if tipo_equipamento:
            query += " AND m.equipamento = ?"
            params.append(tipo_equipamento)
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
            query += " AND m.tipo = ?"
            params.append(mov_tipo)
        if status:
            query += " AND m.status = ?"
            params.append(status)
        if setor_id:
            query += " AND (m.setor_origem_id = ? OR m.setor_destino_id = ?)"
            params.extend([int(setor_id), int(setor_id)])
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
        
    conn.close()
    return render_template_string(
        RELATORIOS_TEMPLATE,
        tab=tab,
        items=items,
        setores=setores,
        marcas=marcas,
        tipos_eq=tipos_eq,
        selected_setor=setor_id,
        selected_status=status,
        selected_marca=marca,
        selected_tipo_eq=tipo_equipamento,
        data_inicio=data_inicio,
        data_fim=data_fim,
        mov_tipo=mov_tipo
    )

@app.route('/relatorios/export/<format_type>')
def relatorios_export(format_type):
    if 'username' not in session or session.get('perfil') != 'admin':
        return abort(403)
        
    tab = request.args.get('tab', 'inventario')
    setor_id = request.args.get('setor_id', '')
    status = request.args.get('status', '')
    marca = request.args.get('marca', '')
    tipo_equipamento = request.args.get('tipo_equipamento', '')
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')
    mov_tipo = request.args.get('mov_tipo', '')
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    headers = []
    rows = []
    title = ""
    
    if tab == 'inventario':
        title = "Relatório de Inventário"
        headers = ["ID", "Equipamento", "Marca", "Nº Série", "Qtd", "Estado", "Data Registo", "Observações", "Setor"]
        query = '''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, 
                          i.data_registo, i.observacoes, s.nome as setor_nome 
                   FROM inventario_local i 
                   LEFT JOIN setores s ON i.setor_id = s.id 
                   WHERE i.status != 'Pendente' '''
        params = []
        if setor_id:
            query += " AND i.setor_id = ?"
            params.append(int(setor_id))
        if status:
            query += " AND i.status = ?"
            params.append(status)
        if marca:
            query += " AND i.marca = ?"
            params.append(marca)
        if tipo_equipamento:
            query += " AND i.equipamento = ?"
            params.append(tipo_equipamento)
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
        if setor_id:
            query += " AND (m.setor_origem_id = ? OR m.setor_destino_id = ?)"
            params.extend([int(setor_id), int(setor_id)])
        if marca:
            query += " AND m.marca = ?"
            params.append(marca)
        if tipo_equipamento:
            query += " AND m.equipamento = ?"
            params.append(tipo_equipamento)
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
            query += " AND m.tipo = ?"
            params.append(mov_tipo)
        if status:
            query += " AND m.status = ?"
            params.append(status)
        if setor_id:
            query += " AND (m.setor_origem_id = ? OR m.setor_destino_id = ?)"
            params.extend([int(setor_id), int(setor_id)])
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
    
    if format_type == 'excel':
        # Generate UTF-8 BOM CSV for Excel
        output = io.StringIO()
        output.write('ï»¿') # BOM
        import csv
        writer = csv.writer(output, delimiter=';')
        writer.writerow(headers)
        for r in rows:
            # Format row fields as strings
            writer.writerow([str(val) if val is not None else '' for val in r])
            
        mem = io.BytesIO()
        mem.write(output.getvalue().encode('utf-8'))
        mem.seek(0)
        return send_file(
            mem,
            as_attachment=True,
            download_name=f"relatorio_{tab}_{timestamp}.csv",
            mimetype='text/csv'
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
        # Check if already exists in dest
        c.execute("SELECT id, quantidade FROM inventario_local WHERE setor_id=? AND equipamento=? AND numero_serie=? AND marca=?", (setor_destino_id, equipamento, numero_serie, marca))
        inv = c.fetchone()
        qty = int(quantidade) if quantidade and str(quantidade).isdigit() else 1
        if inv:
            c.execute("UPDATE inventario_local SET quantidade=quantidade+?, status='Disponvel' WHERE id=?", (qty, inv[0]))
        else:
            c.execute("INSERT INTO inventario_local (equipamento, marca, numero_serie, quantidade, status, data_registo, setor_id) VALUES (?,?,?,?,'Disponvel',?,?)",
                      (equipamento, marca, numero_serie, qty, datetime.now().strftime("%Y-%m-%d"), setor_destino_id))
        
        c.execute("UPDATE movimentos SET status='RECEBIDO' WHERE guia=?", (guia,))
        conn.commit()
        flash(f"Receo confirmada para a guia {guia}!")
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
                c.execute("UPDATE inventario_local SET quantidade=quantidade+?, status='Disponvel' WHERE id=?", (qty, inv[0]))
            else:
                c.execute("INSERT INTO inventario_local (equipamento, marca, numero_serie, quantidade, status, data_registo, setor_id) VALUES (?,?,?,?,'Disponvel',?,?)",
                          (equipamento, marca, numero_serie, qty, datetime.now().strftime("%Y-%m-%d"), setor_origem_id))
        c.execute("UPDATE movimentos SET status='REJEITADO' WHERE guia=?", (guia,))
        conn.commit()
        flash(f"Transferncia da guia {guia} foi rejeitada e o material devolvido ao inventrio de origem.")
    conn.close()
    return redirect(url_for('index'))

@app.route('/inventario')
def inventario():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    setor_id = session.get('setor_id')
    is_admin = session.get('perfil') == 'admin'
    
    # Base query for inventory (excluding Pending which is shown in a separate panel)
    if is_admin:
        c.execute('''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, 
                            i.data_registo, i.observacoes, i.setor_id, s.nome as setor_nome 
                     FROM inventario_local i 
                     LEFT JOIN setores s ON i.setor_id = s.id 
                     WHERE i.status != 'Pendente'
                     ORDER BY i.id DESC''')
    else:
        c.execute('''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, 
                            i.data_registo, i.observacoes, i.setor_id, s.nome as setor_nome 
                     FROM inventario_local i 
                     LEFT JOIN setores s ON i.setor_id = s.id 
                     WHERE i.setor_id = ? AND i.status != 'Pendente'
                     ORDER BY i.id DESC''', (setor_id,))
                     
    cols = [d[0] for d in c.description]
    items = [dict(zip(cols, r)) for r in c.fetchall()]
    
    # Load pending confirmation list for this sector (only for technicians) or all (admin)
    if is_admin:
        c.execute('''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, 
                            i.data_registo, i.observacoes, i.setor_id, s.nome as setor_nome, '' as guia_origem
                     FROM inventario_local i 
                     LEFT JOIN setores s ON i.setor_id = s.id 
                     WHERE i.status = 'Pendente'
                     ORDER BY i.id DESC''')
    else:
        c.execute('''SELECT i.id, i.equipamento, i.marca, i.numero_serie, i.quantidade, i.status, 
                            i.data_registo, i.observacoes, i.setor_id, s.nome as setor_nome, '' as guia_origem
                     FROM inventario_local i 
                     LEFT JOIN setores s ON i.setor_id = s.id 
                     WHERE i.setor_id = ? AND i.status = 'Pendente'
                     ORDER BY i.id DESC''', (setor_id,))
    cols_p = [d[0] for d in c.description]
    pending_items = [dict(zip(cols_p, r)) for r in c.fetchall()]
    
    # Calculate stats selectively based on user scope
    if is_admin:
        c.execute("SELECT COUNT(*), SUM(quantidade) FROM inventario_local WHERE status != 'Pendente'")
        res = c.fetchone()
        total_qty = res[1] if res else 0
        
        c.execute("SELECT SUM(quantidade) FROM inventario_local WHERE status='Disponível'")
        disponiveis = c.fetchone()[0] or 0
        
        c.execute("SELECT SUM(quantidade) FROM inventario_local WHERE status='Em uso'")
        em_uso = c.fetchone()[0] or 0
        
        c.execute("SELECT SUM(quantidade) FROM inventario_local WHERE status IN ('Danificado', 'Avariado')")
        danificados = c.fetchone()[0] or 0
    else:
        c.execute("SELECT COUNT(*), SUM(quantidade) FROM inventario_local WHERE setor_id=? AND status != 'Pendente'", (setor_id,))
        res = c.fetchone()
        total_qty = res[1] if res else 0
        
        c.execute("SELECT SUM(quantidade) FROM inventario_local WHERE setor_id=? AND status='Disponível'", (setor_id,))
        disponiveis = c.fetchone()[0] or 0
        
        c.execute("SELECT SUM(quantidade) FROM inventario_local WHERE setor_id=? AND status='Em uso'", (setor_id,))
        em_uso = c.fetchone()[0] or 0
        
        c.execute("SELECT SUM(quantidade) FROM inventario_local WHERE setor_id=? AND status IN ('Danificado', 'Avariado')", (setor_id,))
        danificados = c.fetchone()[0] or 0
    
    stats = {
        'total': total_qty or 0,
        'disponiveis': disponiveis,
        'em_uso': em_uso,
        'danificados': danificados
    }
    
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
    
    conn.close()
    return render_template_string(INVENTARIO_TEMPLATE, items=items, pending_items=pending_items, stats=stats, setores=setores, marcas=marcas, tipos=tipos, motivos=motivos, fornecedores=fornecedores, instituicoes=instituicoes, msg=request.args.get('msg'))

@app.route('/inventario/add', methods=['POST'])
def inventario_add():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    setor_id = request.form.get('setor_id')
    setor_val = int(setor_id) if (setor_id and setor_id != '' and setor_id != 'None') else None
    c.execute('''INSERT INTO inventario_local (equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, setor_id) 
                 VALUES (?,?,?,?,?,?,?,?)''', 
              (request.form.get('equipamento'), request.form.get('marca'), request.form.get('numero_serie'), int(request.form.get('quantidade', 1)), request.form.get('status'), datetime.now().strftime("%Y-%m-%d"), request.form.get('observacoes', ''), setor_val))
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
    c.execute('''INSERT INTO movimentos (guia, tipo, equipamento, origem_destino, motivo, data, status, funcionario_id, numero_serie, marca, entregue_por, recebido_por, tecnico, agente_protecao, fornecedor, quantidade) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
              (guia_saida, "SAIDA", item['equipamento'], request.form.get('destino'), request.form.get('motivo',''), datetime.now().strftime("%Y-%m-%d"), "Entregue", None, item['numero_serie'], item['marca'], request.form.get('entregue_por',''), request.form.get('recebido_por',''), session.get('nome_completo', session.get('username', 'tecnico')), request.form.get('agente_protecao',''), 'N/A', str(qty_to_remove)))
              
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
        
        # Ensure all columns exist in PostgreSQL (automatic migration)
        tables = ['users', 'setores', 'funcionarios', 'movimentos', 'marcas', 'tipos_equipamento', 'motivos', 'fornecedores', 'instituicoes', 'inventario_local']
        
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
            c.execute("ALTER TABLE movimentos ADD COLUMN IF NOT EXISTS setor_origem_id INTEGER")
            c.execute("ALTER TABLE movimentos ADD COLUMN IF NOT EXISTS setor_destino_id INTEGER")
        except Exception as ex:
            conn.rollback()
            print(f"[-] Erro ao migrar novas colunas de setor no PG: {ex}")
                
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

def sync_lookup_table(table_name):
    s_conn = sqlite3.connect(DB_PATH)
    s_c = s_conn.cursor()
    s_c.execute(f"SELECT nome, last_modified, origem_registo FROM {table_name}")
    s_items = {r[0]: (r[1], r[2]) for r in s_c.fetchall()}
    
    pg_conn = get_pg_connection()
    if not pg_conn:
        s_conn.close()
        return False
    pg_c = pg_conn.cursor()
    pg_c.execute(f"SELECT nome, last_modified, origem_registo FROM {table_name}")
    pg_items = {r[0]: (r[1], r[2]) for r in pg_c.fetchall()}
    
    for nome, (s_lm, s_orig) in s_items.items():
        if nome not in pg_items:
            pg_c.execute(f"INSERT INTO {table_name} (nome, last_modified, origem_registo) VALUES (%s, %s, %s)", (nome, s_lm, s_orig))
        elif s_lm > pg_items[nome][0]:
            pg_c.execute(f"UPDATE {table_name} SET last_modified=%s, origem_registo=%s WHERE nome=%s", (s_lm, s_orig, nome))
            
    for nome, (pg_lm, pg_orig) in pg_items.items():
        if nome not in s_items:
            s_c.execute(f"INSERT INTO {table_name} (nome, last_modified, origem_registo) VALUES (?, ?, ?)", (nome, pg_lm, pg_orig))
        elif pg_lm > s_items[nome][0]:
            s_c.execute(f"UPDATE {table_name} SET last_modified=?, origem_registo=? WHERE nome=?", (pg_lm, pg_orig, nome))
            
    pg_conn.commit()
    pg_conn.close()
    s_conn.commit()
    s_conn.close()
    return True

def sync_users():
    s_conn = sqlite3.connect(DB_PATH)
    s_c = s_conn.cursor()
    s_c.execute("SELECT username, password, perfil, nome_completo, last_modified, origem_registo, setor_id FROM users")
    s_users = {r[0]: {'password': r[1], 'perfil': r[2], 'nome_completo': r[3], 'last_modified': r[4], 'origem_registo': r[5], 'setor_id': r[6]} for r in s_c.fetchall()}
    
    pg_conn = get_pg_connection()
    if not pg_conn:
        s_conn.close()
        return False
    pg_c = pg_conn.cursor()
    pg_c.execute("SELECT username, password, perfil, nome_completo, last_modified, origem_registo, setor_id FROM users")
    pg_users = {r[0]: {'password': r[1], 'perfil': r[2], 'nome_completo': r[3], 'last_modified': r[4], 'origem_registo': r[5], 'setor_id': r[6]} for r in pg_c.fetchall()}
    
    for username, s_u in s_users.items():
        if username not in pg_users:
            pg_c.execute("INSERT INTO users (username, password, perfil, nome_completo, last_modified, origem_registo, setor_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                         (username, s_u['password'], s_u['perfil'], s_u['nome_completo'], s_u['last_modified'], s_u['origem_registo'], s_u['setor_id']))
        elif s_u['last_modified'] > pg_users[username]['last_modified']:
            pg_c.execute("UPDATE users SET password=%s, perfil=%s, nome_completo=%s, last_modified=%s, origem_registo=%s, setor_id=%s WHERE username=%s",
                         (s_u['password'], s_u['perfil'], s_u['nome_completo'], s_u['last_modified'], s_u['origem_registo'], s_u['setor_id'], username))
            
    for username, pg_u in pg_users.items():
        if username not in s_users:
            s_c.execute("INSERT INTO users (username, password, perfil, nome_completo, last_modified, origem_registo, setor_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (username, pg_u['password'], pg_u['perfil'], pg_u['nome_completo'], pg_u['last_modified'], pg_u['origem_registo'], pg_u['setor_id']))
        elif pg_u['last_modified'] > s_users[username]['last_modified']:
            s_c.execute("UPDATE users SET password=?, perfil=?, nome_completo=?, last_modified=?, origem_registo=?, setor_id=? WHERE username=?",
                        (pg_u['password'], pg_u['perfil'], pg_u['nome_completo'], pg_u['last_modified'], pg_u['origem_registo'], pg_u['setor_id'], username))
            
    pg_conn.commit()
    pg_conn.close()
    s_conn.commit()
    s_conn.close()
    return True

def sync_funcionarios():
    s_conn = sqlite3.connect(DB_PATH)
    s_c = s_conn.cursor()
    
    s_c.execute("SELECT id, nome FROM setores")
    s_setor_id_to_name = {r[0]: r[1] for r in s_c.fetchall()}
    s_sector_name_to_id = {v: k for k, v in s_setor_id_to_name.items()}
    
    s_c.execute("SELECT nome, cargo, setor_id, last_modified, origem_registo FROM funcionarios")
    s_funcs = {r[0]: {'cargo': r[1], 'sector_name': s_setor_id_to_name.get(r[2], ''), 'last_modified': r[3], 'origem_registo': r[4]} for r in s_c.fetchall()}
    
    pg_conn = get_pg_connection()
    if not pg_conn:
        s_conn.close()
        return False
    pg_c = pg_conn.cursor()
    
    pg_c.execute("SELECT id, nome FROM setores")
    pg_setor_id_to_name = {r[0]: r[1] for r in pg_c.fetchall()}
    pg_sector_name_to_id = {v: k for k, v in pg_setor_id_to_name.items()}
    
    pg_c.execute("SELECT nome, cargo, setor_id, last_modified, origem_registo FROM funcionarios")
    pg_funcs = {r[0]: {'cargo': r[1], 'sector_name': pg_setor_id_to_name.get(r[2], ''), 'last_modified': r[3], 'origem_registo': r[4]} for r in pg_c.fetchall()}
    
    for nome, s_f in s_funcs.items():
        pg_sec_id = pg_sector_name_to_id.get(s_f['sector_name'])
        if nome not in pg_funcs:
            pg_c.execute("INSERT INTO funcionarios (nome, cargo, setor_id, last_modified, origem_registo) VALUES (%s, %s, %s, %s, %s)",
                         (nome, s_f['cargo'], pg_sec_id, s_f['last_modified'], s_f['origem_registo']))
        elif s_f['last_modified'] > pg_funcs[nome]['last_modified']:
            pg_c.execute("UPDATE funcionarios SET cargo=%s, setor_id=%s, last_modified=%s, origem_registo=%s WHERE nome=%s",
                         (s_f['cargo'], pg_sec_id, s_f['last_modified'], s_f['origem_registo'], nome))
            
    for nome, pg_f in pg_funcs.items():
        s_sec_id = s_sector_name_to_id.get(pg_f['sector_name'])
        if nome not in s_funcs:
            s_c.execute("INSERT INTO funcionarios (nome, cargo, setor_id, last_modified, origem_registo) VALUES (?, ?, ?, ?, ?)",
                         (nome, pg_f['cargo'], s_sec_id, pg_f['last_modified'], pg_f['origem_registo']))
        elif pg_f['last_modified'] > s_funcs[nome]['last_modified']:
            s_c.execute("UPDATE funcionarios SET cargo=?, setor_id=?, last_modified=?, origem_registo=? WHERE nome=?",
                         (pg_f['cargo'], s_sec_id, pg_f['last_modified'], pg_f['origem_registo'], nome))
            
    pg_conn.commit()
    pg_conn.close()
    s_conn.commit()
    s_conn.close()
    return True

def sync_movimentos():
    s_conn = sqlite3.connect(DB_PATH)
    s_c = s_conn.cursor()
    
    s_c.execute("SELECT id, nome FROM funcionarios")
    s_emp_id_to_name = {r[0]: r[1] for r in s_c.fetchall()}
    s_emp_name_to_id = {v: k for k, v in s_emp_id_to_name.items()}
    
    s_c.execute('''SELECT guia, tipo, equipamento, origem_destino, motivo, data, status, tecnico, relatorio, funcionario_id, numero_serie, marca, entregue_por, recebido_por, agente_protecao, fornecedor, quantidade, setor_origem_id, setor_destino_id, last_modified, origem_registo FROM movimentos''')
    s_movs = {}
    for r in s_c.fetchall():
        s_movs[r[0]] = {
            'tipo': r[1], 'equipamento': r[2], 'origem_destino': r[3], 'motivo': r[4], 'data': r[5],
            'status': r[6], 'tecnico': r[7], 'relatorio': r[8], 'emp_name': s_emp_id_to_name.get(r[9], ''),
            'numero_serie': r[10], 'marca': r[11], 'entregue_por': r[12], 'recebido_por': r[13],
            'agente_protecao': r[14], 'fornecedor': r[15], 'quantidade': r[16],
            'setor_origem_id': r[17], 'setor_destino_id': r[18], 'last_modified': r[19],
            'origem_registo': r[20]
        }
        
    pg_conn = get_pg_connection()
    if not pg_conn:
        s_conn.close()
        return False
    pg_c = pg_conn.cursor()
    
    pg_c.execute("SELECT id, nome FROM funcionarios")
    pg_emp_id_to_name = {r[0]: r[1] for r in pg_c.fetchall()}
    pg_emp_name_to_id = {v: k for k, v in pg_emp_id_to_name.items()}
    
    pg_c.execute('''SELECT guia, tipo, equipamento, origem_destino, motivo, data, status, tecnico, relatorio, funcionario_id, numero_serie, marca, entregue_por, recebido_por, agente_protecao, fornecedor, quantidade, setor_origem_id, setor_destino_id, last_modified, origem_registo FROM movimentos''')
    pg_movs = {}
    for r in pg_c.fetchall():
        pg_movs[r[0]] = {
            'tipo': r[1], 'equipamento': r[2], 'origem_destino': r[3], 'motivo': r[4], 'data': r[5],
            'status': r[6], 'tecnico': r[7], 'relatorio': r[8], 'emp_name': pg_emp_id_to_name.get(r[9], ''),
            'numero_serie': r[10], 'marca': r[11], 'entregue_por': r[12], 'recebido_por': r[13],
            'agente_protecao': r[14], 'fornecedor': r[15], 'quantidade': r[16],
            'setor_origem_id': r[17], 'setor_destino_id': r[18], 'last_modified': r[19],
            'origem_registo': r[20]
        }
        
    for guia, s_m in s_movs.items():
        pg_emp_id = pg_emp_name_to_id.get(s_m['emp_name'])
        if guia not in pg_movs:
            pg_c.execute('''INSERT INTO movimentos 
                (guia, tipo, equipamento, origem_destino, motivo, data, status, tecnico, relatorio, funcionario_id, numero_serie, marca, entregue_por, recebido_por, agente_protecao, fornecedor, quantidade, setor_origem_id, setor_destino_id, last_modified, origem_registo) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (guia, s_m['tipo'], s_m['equipamento'], s_m['origem_destino'], s_m['motivo'], s_m['data'],
                 s_m['status'], s_m['tecnico'], s_m['relatorio'], pg_emp_id, s_m['numero_serie'], s_m['marca'],
                 s_m['entregue_por'], s_m['recebido_por'], s_m['agente_protecao'], s_m['fornecedor'], s_m['quantidade'],
                 s_m['setor_origem_id'], s_m['setor_destino_id'], s_m['last_modified'], s_m['origem_registo']))
        elif s_m['last_modified'] > pg_movs[guia]['last_modified']:
            pg_c.execute('''UPDATE movimentos SET 
                tipo=%s, equipamento=%s, origem_destino=%s, motivo=%s, data=%s, status=%s, tecnico=%s, relatorio=%s, 
                funcionario_id=%s, numero_serie=%s, marca=%s, entregue_por=%s, recebido_por=%s, agente_protecao=%s, 
                fornecedor=%s, quantidade=%s, setor_origem_id=%s, setor_destino_id=%s, last_modified=%s, origem_registo=%s WHERE guia=%s''',
                (s_m['tipo'], s_m['equipamento'], s_m['origem_destino'], s_m['motivo'], s_m['data'],
                 s_m['status'], s_m['tecnico'], s_m['relatorio'], pg_emp_id, s_m['numero_serie'], s_m['marca'],
                 s_m['entregue_por'], s_m['recebido_por'], s_m['agente_protecao'], s_m['fornecedor'], s_m['quantidade'],
                 s_m['setor_origem_id'], s_m['setor_destino_id'], s_m['last_modified'], s_m['origem_registo'], guia))
                 
    for guia, pg_m in pg_movs.items():
        s_emp_id = s_emp_name_to_id.get(pg_m['emp_name'])
        if guia not in s_movs:
            s_c.execute('''INSERT INTO movimentos 
                (guia, tipo, equipamento, origem_destino, motivo, data, status, tecnico, relatorio, funcionario_id, numero_serie, marca, entregue_por, recebido_por, agente_protecao, fornecedor, quantidade, setor_origem_id, setor_destino_id, last_modified, origem_registo) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (guia, pg_m['tipo'], pg_m['equipamento'], pg_m['origem_destino'], pg_m['motivo'], pg_m['data'],
                 pg_m['status'], pg_m['tecnico'], pg_m['relatorio'], s_emp_id, pg_m['numero_serie'], pg_m['marca'],
                 pg_m['entregue_por'], pg_m['recebido_por'], pg_m['agente_protecao'], pg_m['fornecedor'], pg_m['quantidade'],
                 pg_m['setor_origem_id'], pg_m['setor_destino_id'], pg_m['last_modified'], pg_m['origem_registo']))
        elif pg_m['last_modified'] > s_movs[guia]['last_modified']:
            s_c.execute('''UPDATE movimentos SET 
                tipo=?, equipamento=?, origem_destino=?, motivo=?, data=?, status=?, tecnico=?, relatorio=?, 
                funcionario_id=?, numero_serie=?, marca=?, entregue_por=?, recebido_por=?, agente_protecao=?, 
                fornecedor=?, quantidade=?, setor_origem_id=?, setor_destino_id=?, last_modified=?, origem_registo=? WHERE guia=?''',
                (pg_m['tipo'], pg_m['equipamento'], pg_m['origem_destino'], pg_m['motivo'], pg_m['data'],
                 pg_m['status'], pg_m['tecnico'], pg_m['relatorio'], s_emp_id, pg_m['numero_serie'], pg_m['marca'],
                 pg_m['entregue_por'], pg_m['recebido_por'], pg_m['agente_protecao'], pg_m['fornecedor'], pg_m['quantidade'],
                 pg_m['setor_origem_id'], pg_m['setor_destino_id'], pg_m['last_modified'], pg_m['origem_registo'], guia))
                 
    pg_conn.commit()
    pg_conn.close()
    s_conn.commit()
    s_conn.close()
    return True

def sync_inventario_local():
    s_conn = sqlite3.connect(DB_PATH)
    s_c = s_conn.cursor()
    s_c.execute("SELECT equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo, setor_id FROM inventario_local")
    s_items = {}
    for r in s_c.fetchall():
        key = f"{r[0]}::{r[1]}::{r[2]}"
        s_items[key] = {
            'equipamento': r[0], 'marca': r[1], 'numero_serie': r[2], 'quantidade': r[3], 'status': r[4],
            'data_registo': r[5], 'observacoes': r[6], 'last_modified': r[7], 'origem_registo': r[8], 'setor_id': r[9]
        }
        
    pg_conn = get_pg_connection()
    if not pg_conn:
        s_conn.close()
        return False
    pg_c = pg_conn.cursor()
    pg_c.execute("SELECT equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo, setor_id FROM inventario_local")
    pg_items = {}
    for r in pg_c.fetchall():
        key = f"{r[0]}::{r[1]}::{r[2]}"
        pg_items[key] = {
            'equipamento': r[0], 'marca': r[1], 'numero_serie': r[2], 'quantidade': r[3], 'status': r[4],
            'data_registo': r[5], 'observacoes': r[6], 'last_modified': r[7], 'origem_registo': r[8], 'setor_id': r[9]
        }
        
    for key, s_i in s_items.items():
        if key not in pg_items:
            pg_c.execute('''INSERT INTO inventario_local 
                (equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo, setor_id) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (s_i['equipamento'], s_i['marca'], s_i['numero_serie'], s_i['quantidade'], s_i['status'], s_i['data_registo'], s_i['observacoes'], s_i['last_modified'], s_i['origem_registo'], s_i['setor_id']))
        elif s_i['last_modified'] > pg_items[key]['last_modified']:
            pg_c.execute('''UPDATE inventario_local SET 
                quantidade=%s, status=%s, data_registo=%s, observacoes=%s, last_modified=%s, origem_registo=%s, setor_id=%s 
                WHERE equipamento=%s AND marca=%s AND numero_serie=%s''',
                (s_i['quantidade'], s_i['status'], s_i['data_registo'], s_i['observacoes'], s_i['last_modified'], s_i['origem_registo'], s_i['setor_id'], s_i['equipamento'], s_i['marca'], s_i['numero_serie']))
                
    for key, pg_i in pg_items.items():
        if key not in s_items:
            s_c.execute('''INSERT INTO inventario_local 
                (equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo, setor_id) 
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (pg_i['equipamento'], pg_i['marca'], pg_i['numero_serie'], pg_i['quantidade'], pg_i['status'], pg_i['data_registo'], pg_i['observacoes'], pg_i['last_modified'], pg_i['origem_registo'], pg_i['setor_id']))
        elif pg_i['last_modified'] > s_items[key]['last_modified']:
            s_c.execute('''UPDATE inventario_local SET 
                quantidade=?, status=?, data_registo=?, observacoes=?, last_modified=?, origem_registo=?, setor_id=? 
                WHERE equipamento=? AND marca=? AND numero_serie=?''',
                (pg_i['quantidade'], pg_i['status'], pg_i['data_registo'], pg_i['observacoes'], pg_i['last_modified'], pg_i['origem_registo'], pg_i['setor_id'], pg_i['equipamento'], pg_i['marca'], pg_i['numero_serie']))
                
    pg_conn.commit()
    pg_conn.close()
    s_conn.commit()
    s_conn.close()
    return True

def sync_databases():
    if is_cloud_mode():
        return True
    conn = get_pg_connection()
    if not conn:
        print("[-] Sincronização cancelada: PostgreSQL Cloud inacessível.")
        return False
    conn.close()
    
    print("[*] A iniciar sincronização bidirecional...")
    try:
        for table in ['setores', 'marcas', 'tipos_equipamento', 'motivos', 'fornecedores', 'instituicoes']:
            sync_lookup_table(table)
            
        sync_users()
        sync_funcionarios()
        sync_movimentos()
        sync_inventario_local()
        
        print("[+] Sincronização bidirecional concluída com sucesso!")
        return True
    except Exception as e:
        print(f"[-] Erro durante a sincronização: {e}")
        return False
init_db()

if __name__ == '__main__':
    Timer(1.5, lambda: webbrowser.open('http://127.0.0.1:5000')).start()
    app.run(host='127.0.0.1', port=5000)
