import sqlite3

content = open('app.py', encoding='utf-8').read()

new_cards = '''
            <!-- Marcas -->
            <div class="card">
                <h3>Adicionar Marca</h3>
                <form method="POST" action="/add_marca">
                    <input name="nome" placeholder="Ex: HP, Dell, Apple" required>
                    <button class="btn btn-blue" style="margin-top:1rem; width:100%">Salvar Marca</button>
                </form>
                <h4 style="margin-top:2rem">Marcas Cadastradas</h4>
                <table style="margin-top:0.5rem">
                    {% for m in marcas %}<tr><td>{{m.nome}}</td></tr>{% endfor %}
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
                    {% for t in tipos %}<tr><td>{{t.nome}}</td></tr>{% endfor %}
                </table>
            </div>
        </div>
    </div>
</body></html>
'''
content = content.replace('        </div>\n    </div>\n</body></html>', new_cards)

new_routes = '''
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
'''
content = content.replace("@app.route('/add_setor', methods=['POST'])", new_routes + "\n@app.route('/add_setor', methods=['POST'])")

open('app.py', 'w', encoding='utf-8').write(content)
print("Updated successfully")
