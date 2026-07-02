import re
import os

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update init_pg_db with new columns
if "c.execute(f\"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS origem_registo" in content:
    pg_col_patch = """c.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS origem_registo VARCHAR DEFAULT 'local'")
            except Exception as ex:
                print(f"[-] Erro ao migrar origem_registo no PG para {t}: {ex}")
                
        try:
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS setor_id INTEGER")
            c.execute("ALTER TABLE movimentos ADD COLUMN IF NOT EXISTS setor_origem_id INTEGER")
            c.execute("ALTER TABLE movimentos ADD COLUMN IF NOT EXISTS setor_destino_id INTEGER")
        except Exception as ex:
            print(f"[-] Erro ao migrar novas colunas de setor no PG: {ex}")"""
    content = content.replace("""c.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS origem_registo VARCHAR DEFAULT 'local'")
            except Exception as ex:
                print(f"[-] Erro ao migrar origem_registo no PG para {t}: {ex}")""", pg_col_patch)

# 2. Update registrar_saida
old_saida_func = re.search(r'def registrar_saida\(\):.*?return redirect\(url_for\(\'index\'\)\)', content, re.DOTALL)
if old_saida_func:
    new_saida_func = """def registrar_saida():
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
    return redirect(url_for('index'))"""
    content = content.replace(old_saida_func.group(0), new_saida_func)

# 3. Add Rececao Routes
new_routes = """
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
"""
if "/confirmar_recepcao/<guia>" not in content:
    content = content.replace("def inventario():", new_routes + "\ndef inventario():")

# 4. Modify index() to filter by setor_id for movements and show pendentes
idx_search = re.search(r'def index\(\):.*?return render_template_string\(MAIN_TEMPLATE, msg=msg.*?$', content, re.DOTALL | re.MULTILINE)
if idx_search:
    new_idx_func = """def index():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    msg = request.args.get('msg')
    
    setor_id = session.get('setor_id')
    is_admin = session.get('perfil') == 'admin'
    
    if is_admin:
        c.execute("SELECT * FROM movimentos ORDER BY id DESC LIMIT 50")
    else:
        c.execute("SELECT * FROM movimentos WHERE setor_origem_id=? OR setor_destino_id=? OR (setor_origem_id IS NULL AND setor_destino_id IS NULL) ORDER BY id DESC LIMIT 50", (setor_id, setor_id))
    
    cols = [d[0] for d in c.description]
    movimentos = [dict(zip(cols, r)) for r in c.fetchall()]
    
    # Fetch pending receptions
    pendentes = []
    if not is_admin and setor_id:
        c.execute("SELECT * FROM movimentos WHERE setor_destino_id=? AND status='PENDENTE_RECEPCAO' ORDER BY id DESC", (setor_id,))
        pendentes = [dict(zip(cols, r)) for r in c.fetchall()]
    
    if is_admin:
        c.execute("SELECT id, equipamento, marca, numero_serie, quantidade FROM inventario_local WHERE status!='Pendente' ORDER BY equipamento")
    else:
        c.execute("SELECT id, equipamento, marca, numero_serie, quantidade FROM inventario_local WHERE setor_id=? AND status!='Pendente' ORDER BY equipamento", (setor_id,))
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
    em_reparacao = c.fetchone()[0]
    
    conn.close()
    return render_template_string(MAIN_TEMPLATE, msg=msg, movimentos=movimentos, pendentes=pendentes, inv_items=inv_items, setores=setores, marcas=marcas, tipos=tipos, motivos=motivos, fornecedores=fornecedores, instituicoes=instituicoes, em_reparacao=em_reparacao)"""
    content = content.replace(idx_search.group(0), new_idx_func)

# 5. Patch MAIN_TEMPLATE for the Pending block and destination value
if "PENDENTES_BLOCK_ADDED" not in content:
    # Fix the optgroup labels
    content = content.replace("""<optgroup label="Setores Internos">
                                {% for s in setores %}<option value="Interno - {{s.nome}}">{{s.nome}}</option>{% endfor %}
                            </optgroup>""", """<optgroup label="Setores Internos">
                                {% for s in setores %}<option value="SETOR_{{s.id}}">{{s.nome}}</option>{% endfor %}
                            </optgroup>""")
    content = content.replace("""<optgroup label="Instituies Externas">
                                {% for i in instituicoes %}<option value="Externo - {{i.nome}}">{{i.nome}}</option>{% endfor %}
                            </optgroup>""", """<optgroup label="Instituies Externas">
                                {% for i in instituicoes %}<option value="EXTERNO_{{i.nome}}">{{i.nome}}</option>{% endfor %}
                            </optgroup>""")
                            
    pendentes_html = """
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
    """
    content = content.replace("""<div style="display:flex; gap:1rem; margin-bottom:2rem; justify-content:center; flex-wrap:wrap">""", pendentes_html + """<div style="display:flex; gap:1rem; margin-bottom:2rem; justify-content:center; flex-wrap:wrap">""")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Patch 12 applied successfully.")
