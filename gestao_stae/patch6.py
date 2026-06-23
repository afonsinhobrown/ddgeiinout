import sqlite3

# 1. Create table and populate
conn = sqlite3.connect('staeavancado.db')
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS motivos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)')
for m in ['Alocação', 'Transferência', 'Reparação', 'Avaria', 'Substituição', 'Outro']:
    try: c.execute('INSERT OR IGNORE INTO motivos (nome) VALUES (?)', (m,))
    except: pass
conn.commit()
conn.close()

# 2. Update app.py
content = open('app.py', encoding='utf-8').read()

# Pass motives to templates
index_query_old = '''    c.execute("SELECT id, nome FROM tipos_equipamento")
    tipos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]'''
index_query_new = '''    c.execute("SELECT id, nome FROM tipos_equipamento")
    tipos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM motivos")
    motivos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]'''
content = content.replace(index_query_old, index_query_new)

index_return_old = "setores=setores, marcas=marcas, tipos=tipos)"
index_return_new = "setores=setores, marcas=marcas, tipos=tipos, motivos=motivos)"
content = content.replace(index_return_old, index_return_new)

cadastros_query_old = '''    c.execute("SELECT id, nome FROM tipos_equipamento")
    tipos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    conn.close()'''
cadastros_query_new = '''    c.execute("SELECT id, nome FROM tipos_equipamento")
    tipos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM motivos")
    motivos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    conn.close()'''
content = content.replace(cadastros_query_old, cadastros_query_new)

cadastros_return_old = "marcas=marcas, tipos=tipos, msg=request.args.get('msg'))"
cadastros_return_new = "marcas=marcas, tipos=tipos, motivos=motivos, msg=request.args.get('msg'))"
content = content.replace(cadastros_return_old, cadastros_return_new)

# Add card in CADASTROS
cadastros_cards = '''
            <!-- Motivos -->
            <div class="card">
                <h3>Adicionar Motivo</h3>
                <form method="POST" action="/add_motivo">
                    <input name="nome" placeholder="Ex: Alocação, Avaria" required>
                    <button class="btn btn-blue" style="margin-top:1rem; width:100%">Salvar Motivo</button>
                </form>
                <h4 style="margin-top:2rem">Motivos Cadastrados</h4>
                <table style="margin-top:0.5rem">
                    {% for m in motivos %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
                        <div>{{m.nome}}</div>
                        <button onclick="openEdit('/edit_motivo/{{m.id}}', 'Editar Motivo', [
                            {label:'Nome do Motivo', name:'nome', type:'text', value:'{{m.nome}}', required:true}
                        ])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                    </td></tr>{% endfor %}
                </table>
            </div>
        </div>
'''
content = content.replace('        </div>\n    </div>\n    <!-- Modals de Edição -->', cadastros_cards + '    </div>\n    <!-- Modals de Edição -->')

# Add routes
new_routes = '''
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
'''
content = content.replace("@app.route('/add_marca', methods=['POST'])", new_routes + "\n@app.route('/add_marca', methods=['POST'])")

# Update inputs in MAIN_TEMPLATE
input_motivo_old = '<div><label>Motivo</label><input name="motivo" list="motivos_list" placeholder="Ex: Alocação"></div>'
input_motivo_new = '''<div><label>Motivo</label>
                        <select name="motivo" required>
                            <option value="">-- Selecione --</option>
                            {% for m in motivos %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>'''
content = content.replace(input_motivo_old, input_motivo_new)

input_motivo_old_sai = '<div><label>Motivo</label><input name="motivo" list="motivos_list" required placeholder="Reparado, Transferência..."></div>'
content = content.replace(input_motivo_old_sai, input_motivo_new)

open('app.py', 'w', encoding='utf-8').write(content)
print("Patch 6 motives applied")
