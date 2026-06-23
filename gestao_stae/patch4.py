import re

content = open('app.py', encoding='utf-8').read()

edit_modals = '''
    <!-- Modals de Edição -->
    <div id="editModal" class="hidden" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000; display:flex; justify-content:center; align-items:center;">
        <div class="card" style="width:400px; max-width:90%;">
            <h3 id="editTitle">Editar</h3>
            <form id="editForm" method="POST" action="">
                <div id="editFields" style="display:flex; flex-direction:column; gap:1rem; margin-bottom:1rem;"></div>
                <div style="display:flex; gap:1rem;">
                    <button type="button" class="btn btn-outline" style="flex:1" onclick="document.getElementById('editModal').classList.add('hidden')">Cancelar</button>
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
            document.getElementById('editModal').classList.remove('hidden');
        }
    </script>
</body></html>'''
content = content.replace('</body></html>', edit_modals)

# Add Edit buttons to Cadastros
user_table_old = '{% for u in users_list %}<tr><td><strong>{{u.nome_completo}}</strong><br><small>{{u.username}} - {{u.perfil}}</small></td></tr>{% endfor %}'
user_table_new = '''{% for u in users_list %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
    <div><strong>{{u.nome_completo}}</strong><br><small>{{u.username}} - {{u.perfil}}</small></div>
    <button onclick="openEdit('/edit_user/{{u.id}}', 'Editar Usuário', [
        {label:'Nome Completo', name:'nome_completo', type:'text', value:'{{u.nome_completo}}', required:true},
        {label:'Username', name:'username', type:'text', value:'{{u.username}}', required:true},
        {label:'Perfil', name:'perfil', type:'select', value:'{{u.perfil}}', options:[{value:'admin',text:'Administrador'},{value:'tecnico',text:'Técnico'},{value:'protecao',text:'Protecção'}]},
        {label:'Nova Senha (Opcional)', name:'password', type:'password', value:'', required:false}
    ])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
</td></tr>{% endfor %}'''
content = content.replace(user_table_old, user_table_new)

func_table_old = '{% for f in funcionarios %}<tr><td>{{f.nome}} - {{f.cargo}}</td></tr>{% endfor %}'
func_table_new = '''{% for f in funcionarios %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
    <div>{{f.nome}} - {{f.cargo}}</div>
    <button onclick="openEdit('/edit_funcionario/{{f.id}}', 'Editar Funcionário', [
        {label:'Nome', name:'nome', type:'text', value:'{{f.nome}}', required:true},
        {label:'Cargo', name:'cargo', type:'text', value:'{{f.cargo}}', required:false},
        {label:'Setor', name:'setor_id', type:'select', value:'{{f.setor_id}}', options:[{% for s in setores %}{value:'{{s.id}}',text:'{{s.nome}}'},{% endfor %}]}
    ])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
</td></tr>{% endfor %}'''
content = content.replace(func_table_old, func_table_new)

setor_table_old = '{% for s in setores %}<tr><td>{{s.nome}}</td></tr>{% endfor %}'
setor_table_new = '''{% for s in setores %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
    <div>{{s.nome}}</div>
    <button onclick="openEdit('/edit_setor/{{s.id}}', 'Editar Setor', [
        {label:'Nome do Setor', name:'nome', type:'text', value:'{{s.nome}}', required:true}
    ])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
</td></tr>{% endfor %}'''
content = content.replace(setor_table_old, setor_table_new)

marca_table_old = '{% for m in marcas %}<tr><td>{{m.nome}}</td></tr>{% endfor %}'
marca_table_new = '''{% for m in marcas %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
    <div>{{m.nome}}</div>
    <button onclick="openEdit('/edit_marca/{{m.id}}', 'Editar Marca', [
        {label:'Nome da Marca', name:'nome', type:'text', value:'{{m.nome}}', required:true}
    ])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
</td></tr>{% endfor %}'''
content = content.replace(marca_table_old, marca_table_new)

tipo_table_old = '{% for t in tipos %}<tr><td>{{t.nome}}</td></tr>{% endfor %}'
tipo_table_new = '''{% for t in tipos %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
    <div>{{t.nome}}</div>
    <button onclick="openEdit('/edit_tipo/{{t.id}}', 'Editar Tipo', [
        {label:'Nome do Tipo', name:'nome', type:'text', value:'{{t.nome}}', required:true}
    ])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
</td></tr>{% endfor %}'''
content = content.replace(tipo_table_old, tipo_table_new)

new_routes = '''
@app.route('/edit_marca/<int:id>', methods=['POST'])
def edit_marca(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE marcas SET nome=? WHERE id=?", (request.form['nome'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Marca atualizada!"))

@app.route('/edit_tipo/<int:id>', methods=['POST'])
def edit_tipo(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE tipos_equipamento SET nome=? WHERE id=?", (request.form['nome'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('cadastros', msg="Tipo atualizado!"))
'''
content = content.replace("@app.route('/add_marca', methods=['POST'])", new_routes + "\n@app.route('/add_marca', methods=['POST'])")

open('app.py', 'w', encoding='utf-8').write(content)
print("Patch 4 completed successfully")
