import sqlite3

# 1. Create tables and populate
conn = sqlite3.connect('staeavancado.db')
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS fornecedores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)')
c.execute('CREATE TABLE IF NOT EXISTS instituicoes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)')
try: c.execute("INSERT OR IGNORE INTO fornecedores (nome) VALUES ('N/A')")
except: pass
conn.commit()
conn.close()

# 2. Update app.py
content = open('app.py', encoding='utf-8').read()

# Pass to index
index_query_old = '''    c.execute("SELECT id, nome FROM motivos")
    motivos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]'''
index_query_new = '''    c.execute("SELECT id, nome FROM motivos")
    motivos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM fornecedores")
    fornecedores = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM instituicoes")
    instituicoes = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]'''
content = content.replace(index_query_old, index_query_new)

index_return_old = "setores=setores, marcas=marcas, tipos=tipos, motivos=motivos)"
index_return_new = "setores=setores, marcas=marcas, tipos=tipos, motivos=motivos, fornecedores=fornecedores, instituicoes=instituicoes)"
content = content.replace(index_return_old, index_return_new)

# Pass to cadastros
cadastros_query_old = '''    c.execute("SELECT id, nome FROM motivos")
    motivos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    conn.close()'''
cadastros_query_new = '''    c.execute("SELECT id, nome FROM motivos")
    motivos = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM fornecedores")
    fornecedores = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    c.execute("SELECT id, nome FROM instituicoes")
    instituicoes = [{'id':r[0], 'nome':r[1]} for r in c.fetchall()]
    conn.close()'''
content = content.replace(cadastros_query_old, cadastros_query_new)

cadastros_return_old = "marcas=marcas, tipos=tipos, motivos=motivos, msg=request.args.get('msg'))"
cadastros_return_new = "marcas=marcas, tipos=tipos, motivos=motivos, fornecedores=fornecedores, instituicoes=instituicoes, msg=request.args.get('msg'))"
content = content.replace(cadastros_return_old, cadastros_return_new)

# Add cards in CADASTROS
cadastros_cards = '''
            <!-- Fornecedores -->
            <div class="card">
                <h3>Adicionar Fornecedor</h3>
                <form method="POST" action="/add_fornecedor">
                    <input name="nome" placeholder="Ex: NCR Angola" required>
                    <button class="btn btn-blue" style="margin-top:1rem; width:100%">Salvar Fornecedor</button>
                </form>
                <h4 style="margin-top:2rem">Fornecedores</h4>
                <table style="margin-top:0.5rem">
                    {% for f in fornecedores %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
                        <div>{{f.nome}}</div>
                        <button onclick="openEdit('/edit_fornecedor/{{f.id}}', 'Editar Fornecedor', [
                            {label:'Nome', name:'nome', type:'text', value:'{{f.nome}}', required:true}
                        ])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                    </td></tr>{% endfor %}
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
                    {% for i in instituicoes %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
                        <div>{{i.nome}}</div>
                        <button onclick="openEdit('/edit_instituicao/{{i.id}}', 'Editar Instituição', [
                            {label:'Nome', name:'nome', type:'text', value:'{{i.nome}}', required:true}
                        ])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                    </td></tr>{% endfor %}
                </table>
            </div>
        </div>
'''
content = content.replace('        </div>\n    </div>\n    <!-- Modals de Edição -->', cadastros_cards + '    </div>\n    <!-- Modals de Edição -->')

# Add routes
new_routes = '''
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
'''
content = content.replace("@app.route('/add_marca', methods=['POST'])", new_routes + "\n@app.route('/add_marca', methods=['POST'])")

# Update Origem/Destino in MAIN_TEMPLATE to use OptGroups
origem_old = '''<div><label>Origem</label>
                        <select name="origem" required onchange="if(this.value=='Outro'){this.nextElementSibling.style.display='block';this.nextElementSibling.required=true;}else{this.nextElementSibling.style.display='none';this.nextElementSibling.required=false;}">
                            <option value="">-- Selecione --</option>
                            {% for s in setores %}<option value="Interno - {{s.nome}}">{{s.nome}}</option>{% endfor %}
                            <option value="Outro">Outro (Externa)</option>
                        </select>
                        <input type="text" name="origem_outro" placeholder="Especifique a origem" style="display:none; margin-top:0.5rem">
                    </div>'''
origem_new = '''<div><label>Origem</label>
                        <select name="origem" required>
                            <option value="">-- Selecione --</option>
                            <optgroup label="Setores Internos">
                                {% for s in setores %}<option value="Interno - {{s.nome}}">{{s.nome}}</option>{% endfor %}
                            </optgroup>
                            <optgroup label="Instituições Externas">
                                {% for i in instituicoes %}<option value="Externo - {{i.nome}}">{{i.nome}}</option>{% endfor %}
                            </optgroup>
                        </select>
                    </div>'''
content = content.replace(origem_old, origem_new)

destino_old = '''<div><label>Destino</label>
                        <select name="destino" required onchange="if(this.value=='Outro'){this.nextElementSibling.style.display='block';this.nextElementSibling.required=true;}else{this.nextElementSibling.style.display='none';this.nextElementSibling.required=false;}">
                            <option value="">-- Selecione --</option>
                            {% for s in setores %}<option value="Interno - {{s.nome}}">{{s.nome}}</option>{% endfor %}
                            <option value="Outro">Outro (Externa)</option>
                        </select>
                        <input type="text" name="destino_outro" placeholder="Especifique o destino" style="display:none; margin-top:0.5rem">
                    </div>'''
destino_new = '''<div><label>Destino</label>
                        <select name="destino" required>
                            <option value="">-- Selecione --</option>
                            <optgroup label="Setores Internos">
                                {% for s in setores %}<option value="Interno - {{s.nome}}">{{s.nome}}</option>{% endfor %}
                            </optgroup>
                            <optgroup label="Instituições Externas">
                                {% for i in instituicoes %}<option value="Externo - {{i.nome}}">{{i.nome}}</option>{% endfor %}
                            </optgroup>
                        </select>
                    </div>'''
content = content.replace(destino_old, destino_new)

# Update Fornecedor input to dropdown
fornecedor_old = '<div><label>Fornecedor</label><input name="fornecedor" placeholder="Ex: N/A"></div>'
fornecedor_new = '''<div><label>Fornecedor</label>
                        <select name="fornecedor" required>
                            <option value="N/A">N/A</option>
                            {% for f in fornecedores %}
                                {% if f.nome != 'N/A' %}<option value="{{f.nome}}">{{f.nome}}</option>{% endif %}
                            {% endfor %}
                        </select>
                    </div>'''
content = content.replace(fornecedor_old, fornecedor_new)
# Note: replace works on all occurrences so it changes both Entrada and Saida

# Also fix the registrar endpoints since we removed origem_outro and destino_outro
content = content.replace("origem = request.form.get('origem_outro') if request.form.get('origem') == 'Outro' else request.form.get('origem')", "origem = request.form.get('origem')")
content = content.replace("destino = request.form.get('destino_outro') if request.form.get('destino') == 'Outro' else request.form.get('destino')", "destino = request.form.get('destino')")

open('app.py', 'w', encoding='utf-8').write(content)
print("Patch 7 Fornecedores/Instituicoes applied")
