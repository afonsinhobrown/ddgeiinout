import os
import sqlite3
import webbrowser
from datetime import datetime
from threading import Timer
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_file, session, flash
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import hashlib
import io

app = Flask(__name__)
app.secret_key = 'stae_secret_key_2026'

# ==================== AUTO-RESET DA BASE DE DADOS (CORREÇÃO DEFINITIVA) ====================
def check_db_integrity():
    db_path = 'stae.db'
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("PRAGMA table_info(movimentos)")
        cols = [row[1] for row in c.fetchall()]
        conn.close()
        # Se a coluna 'equipamento_id' não existir, apagamos para recriar com a nova estrutura
        if cols and 'equipamento_id' not in cols:
            os.remove(db_path)
            print("[*] Base de dados antiga detectada e removida para atualização.")

# ==================== INICIALIZAÇÃO (VERSÃO CORRIGIDA) ====================
def init_db():
    check_db_integrity()
    conn = sqlite3.connect('stae.db')
    c = conn.cursor()
    
    # Tabela de usuários
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        perfil TEXT
    )''')
    
    # Tabela de sectores/departamentos/áreas
    c.execute('''CREATE TABLE IF NOT EXISTS sectores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE,
        tipo TEXT
    )''')
    
    # Tabela de funcionários/pessoas
    c.execute('''CREATE TABLE IF NOT EXISTS funcionarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        cargo TEXT,
        sector_id INTEGER,
        contacto TEXT,
        FOREIGN KEY(sector_id) REFERENCES sectores(id)
    )''')
    
    # Tabela de equipamentos
    c.execute('''CREATE TABLE IF NOT EXISTS equipamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_serie TEXT UNIQUE,
        patrimonio TEXT UNIQUE,
        tipo TEXT,
        marca TEXT,
        modelo TEXT,
        estado TEXT,
        observacoes TEXT
    )''')
    
    # Tabela de movimentações (entradas e saídas)
    c.execute('''CREATE TABLE IF NOT EXISTS movimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_guia TEXT UNIQUE,
        tipo TEXT,
        equipamento_id INTEGER,
        quantidade INTEGER DEFAULT 1,
        origem_destino TEXT,
        motivo TEXT,
        data_movimento TEXT,
        status TEXT,
        relatorio_reparacao TEXT,
        tecnico_responsavel TEXT,
        funcionario_entrega_id INTEGER,
        observacao TEXT,
        FOREIGN KEY(equipamento_id) REFERENCES equipamentos(id),
        FOREIGN KEY(funcionario_entrega_id) REFERENCES funcionarios(id)
    )''')
    
    # Inserir dados padrão
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        for u, p, perf in [("admin", "admin123", "admin"), ("tecnico", "tecnico123", "tecnico"), ("protecao", "protecao123", "protecao")]:
            pwd = hashlib.md5(p.encode()).hexdigest()
            c.execute("INSERT INTO users (username, password, perfil) VALUES (?,?,?)", (u, pwd, perf))
    
    c.execute("SELECT COUNT(*) FROM sectores")
    if c.fetchone()[0] == 0:
        sectores_padrao = [
            ("Direção Geral", "interno"), ("RH", "interno"), ("Finanças", "interno"),
            ("Logística", "interno"), ("Maputo", "provincial"), ("Gaza", "provincial")
        ]
        for nome, tipo in sectores_padrao:
            c.execute("INSERT INTO sectores (nome, tipo) VALUES (?,?)", (nome, tipo))
    
    conn.commit()
    conn.close()

# ==================== TEMPLATES (PREMIUM UI) ====================

COMMON_HEAD = '''
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --primary: #1e293b;
            --accent: #10b981;
            --bg: #f8fafc;
            --border: #e2e8f0;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: #1e293b; }
        .nav { background: var(--primary); color: white; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
        .container { max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }
        .card { background: white; border-radius: 1rem; padding: 1.5rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid var(--border); margin-bottom: 2rem; }
        .btn { padding: 0.6rem 1.2rem; border-radius: 0.5rem; border: none; cursor: pointer; font-weight: 600; text-decoration: none; transition: all 0.2s; }
        .btn-green { background: var(--accent); color: white; }
        .btn-blue { background: #3b82f6; color: white; }
        .btn-outline { background: white; border: 1px solid var(--border); color: #64748b; }
        table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
        th { text-align: left; background: #f8fafc; padding: 1rem; border-bottom: 2px solid #f1f5f9; font-size: 0.75rem; text-transform: uppercase; color: #64748b; }
        td { padding: 1rem; border-bottom: 1px solid #f1f5f9; font-size: 0.9rem; }
        .badge { padding: 0.25rem 0.5rem; border-radius: 0.4rem; font-size: 0.75rem; font-weight: bold; }
        .badge-repair { background: #fef3c7; color: #92400e; }
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
        input, select, textarea { width: 100%; padding: 0.75rem; border: 1px solid var(--border); border-radius: 0.5rem; margin-top: 0.5rem; }
        .hidden { display: none; }
    </style>
'''

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="pt">
<head>
    {{COMMON_HEAD}}
    <title>Login - STAE</title>
</head>
<body style="background:#0f172a; display:flex; align-items:center; justify-content:center; height:100vh;">
    <div class="card" style="width:380px; text-align:center;">
        <h2 style="margin-bottom:0.5rem">STAE</h2>
        <p style="color:#64748b; margin-bottom:2rem">Gestão de Equipamentos</p>
        <form method="POST">
            <div style="text-align:left; margin-bottom:1rem">
                <label>Utilizador</label>
                <input type="text" name="username" required autofocus>
            </div>
            <div style="text-align:left; margin-bottom:1.5rem">
                <label>Palavra-passe</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-green" style="width:100%">ENTRAR</button>
        </form>
    </div>
</body>
</html>
'''.replace('{{COMMON_HEAD}}', COMMON_HEAD)

MAIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="pt">
<head>
    {{COMMON_HEAD}}
    <title>Dashboard - STAE</title>
</head>
<body>
    <div class="nav">
        <strong>STAE GESTÃO</strong>
        <div>👤 {{username}} ({{perfil}}) | <a href="/logout" style="color:white">Sair</a></div>
    </div>

    <div class="container">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2rem">
            <div style="display:flex; gap:1rem">
                <button class="btn btn-green" onclick="show('ent')">📥 Entrada</button>
                <button class="btn btn-blue" onclick="show('sai')">📤 Saída</button>
                <a href="/cadastros" class="btn btn-outline">⚙️ Cadastros</a>
            </div>
            <div class="card" style="margin-bottom:0; padding:0.5rem 1rem">
                <span style="font-weight:bold; color:#1e40af">🔧 EM REPARAÇÃO: {{em_reparacao}}</span>
            </div>
        </div>

        <div id="ent" class="card hidden">
            <h3>Nova Entrada</h3>
            <form method="POST" action="/registrar_entrada">
                <div class="form-grid">
                    <div><label>S/N / Nº Série</label><input name="numero_serie" required></div>
                    <div><label>Património</label><input name="patrimonio"></div>
                    <div><label>Tipo</label><input name="tipo_equip" required placeholder="Laptop, Impressora..."></div>
                    <div><label>Origem</label><input name="origem" required></div>
                </div>
                <button type="submit" class="btn btn-green" style="margin-top:1.5rem; width:100%">CONFIRMAR ENTRADA</button>
            </form>
        </div>

        <div id="sai" class="card hidden">
            <h3>Nova Saída</h3>
            <form method="POST" action="/registrar_saida">
                <label>Equipamento</label>
                <select name="equipamento_id" id="eq_list" required></select>
                <div class="form-grid" style="margin-top:1rem">
                    <div><label>Destino</label><input name="destino" required></div>
                    <div><label>Motivo</label><select name="motivo_saida"><option>Reparado</option><option>Transferência</option></select></div>
                </div>
                <button type="submit" class="btn btn-blue" style="margin-top:1.5rem; width:100%">GERAR GUIA</button>
            </form>
        </div>

        <div class="card">
            <h3>Histórico Recente</h3>
            <table>
                <thead>
                    <tr>
                        <th>Guia</th>
                        <th>Equipamento</th>
                        <th>Origem/Destino</th>
                        <th>Status</th>
                        <th>Data</th>
                        <th>PDF</th>
                    </tr>
                </thead>
                <tbody>
                    {% for m in movimentos %}
                    <tr>
                        <td><strong>{{m.numero_guia}}</strong></td>
                        <td>{{m.equipamento}}<br><small>PAT: {{m.patrimonio}}</small></td>
                        <td>{{m.origem_destino}}</td>
                        <td><span class="badge {{ 'badge-repair' if 'repara' in m.status|lower else '' }}">{{m.status}}</span></td>
                        <td>{{m.data_movimento[:10]}}</td>
                        <td><a href="/ver_guia/{{m.numero_guia}}" target="_blank" class="btn btn-outline" style="padding:0.3rem 0.6rem">Ver</a></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        function show(id){
            document.getElementById('ent').classList.add('hidden');
            document.getElementById('sai').classList.add('hidden');
            document.getElementById(id).classList.remove('hidden');
            if(id === 'sai') loadEqs();
        }
        function loadEqs(){
            fetch('/api/equipamentos').then(r=>r.json()).then(data=>{
                const s = document.getElementById('eq_list');
                s.innerHTML = '';
                data.forEach(e => s.innerHTML += `<option value="${e.id}">${e.tipo} | SN: ${e.serie}</option>`);
            });
        }
    </script>
</body>
</html>
'''.replace('{{COMMON_HEAD}}', COMMON_HEAD)

# ==================== ROTAS ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form['username'], hashlib.md5(request.form['password'].encode()).hexdigest()
        conn = sqlite3.connect('stae.db')
        c = conn.cursor()
        c.execute("SELECT perfil FROM users WHERE username=? AND password=?", (u, p))
        user = c.fetchone()
        conn.close()
        if user:
            session['username'], session['perfil'] = u, user[0]
            return redirect(url_for('index'))
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('stae.db')
    c = conn.cursor()
    c.execute('''SELECT m.*, e.tipo, e.marca, e.modelo, e.numero_serie, e.patrimonio, f.nome
                 FROM movimentos m
                 LEFT JOIN equipamentos e ON m.equipamento_id = e.id
                 LEFT JOIN funcionarios f ON m.funcionario_entrega_id = f.id
                 ORDER BY m.id DESC LIMIT 100''')
    rows = c.fetchall()
    movimentos = []
    for r in rows:
        # Mapeamento conforme solicitado
        eq_nome = f"{r[13] or ''} {r[14] or ''} {r[15] or ''}".strip() or "Equipamento"
        if r[16]: eq_nome += f" - S/N:{r[16]}"
        movimentos.append({
            'numero_guia': r[1], 'equipamento': eq_nome, 'patrimonio': r[17] or "N/A",
            'origem_destino': r[5] or "N/A", 'status': r[8] or "N/A", 'data_movimento': r[7]
        })
    c.execute("SELECT COUNT(*) FROM movimentos WHERE tipo='ENTRADA' AND status LIKE '%repara%'")
    em_rep = c.fetchone()[0]
    conn.close()
    return render_template_string(MAIN_TEMPLATE, movimentos=movimentos, em_reparacao=em_rep, username=session['username'], perfil=session['perfil'])

@app.route('/api/equipamentos')
def api_equipamentos():
    conn = sqlite3.connect('stae.db')
    c = conn.cursor()
    c.execute("SELECT id, numero_serie, tipo FROM equipamentos WHERE estado != 'Entregue'")
    data = [{'id':r[0], 'serie':r[1], 'tipo':r[2]} for r in c.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/registrar_entrada', methods=['POST'])
def registrar_entrada():
    conn = sqlite3.connect('stae.db')
    c = conn.cursor()
    guia = f"ENT-{datetime.now().year}-{len(c.execute('SELECT id FROM movimentos').fetchall())+1:04d}"
    try:
        c.execute("INSERT INTO equipamentos (numero_serie, patrimonio, tipo) VALUES (?,?,?)", (request.form['numero_serie'], request.form['patrimonio'], request.form['tipo_equip']))
        eid = c.lastrowid
    except:
        c.execute("SELECT id FROM equipamentos WHERE numero_serie=?", (request.form['numero_serie'],))
        eid = c.fetchone()[0]
    c.execute("INSERT INTO movimentos (numero_guia, tipo, equipamento_id, origem_destino, data_movimento, status) VALUES (?,?,?,?,?,?)", (guia, "ENTRADA", eid, request.form['origem'], datetime.now().strftime("%Y-%m-%d"), "Aguardando reparação"))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/registrar_saida', methods=['POST'])
def registrar_saida():
    conn = sqlite3.connect('stae.db')
    c = conn.cursor()
    guia = f"SAI-{datetime.now().year}-{len(c.execute('SELECT id FROM movimentos').fetchall())+1:04d}"
    c.execute("INSERT INTO movimentos (numero_guia, tipo, equipamento_id, origem_destino, data_movimento, status, relatorio_reparacao) VALUES (?,?,?,?,?,?,?)", (guia, "SAIDA", request.form['equipamento_id'], request.form['destino'], datetime.now().strftime("%Y-%m-%d"), "Entregue", request.form['rel']))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/cadastros')
def cadastros(): return "Área de Cadastros em breve."

@app.route('/ver_guia/<guia>')
def ver_guia(guia): return "PDF em desenvolvimento."

if __name__ == '__main__':
    init_db()
    Timer(1.5, lambda: webbrowser.open('http://127.0.0.1:5000')).start()
    app.run(host='127.0.0.1', port=5000)
