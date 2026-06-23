import re

content = open('app.py', encoding='utf-8').read()

new_cadastros_template = """CADASTROS_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>Cadastros - STAE</title></head>
<body>
    <div class="nav"><strong>STAE GESTÃO - ADMINISTRAÇÃO</strong><div><a href="/" style="color:white">⬅️ Voltar ao Início</a></div></div>
    <div class="container">
        {% if msg %}<div style="background:#dcfce3; color:#166534; padding:1rem; border-radius:0.5rem; margin-bottom:1rem;">{{msg}}</div>{% endif %}
        
        <div class="form-grid" style="grid-template-columns: 1fr 1fr 1fr;">
            <!-- Setores -->
            <div class="card">
                <h3>Adicionar Setor</h3>
                <form method="POST" action="/add_setor">
                    <input name="nome" placeholder="Nome do Setor" required>
                    <button class="btn btn-blue" style="margin-top:1rem; width:100%">Salvar Setor</button>
                </form>
                <h4 style="margin-top:2rem">Setores Existentes</h4>
                <table style="margin-top:0.5rem">
                    {% for s in setores %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
                        <div>{{s.nome}}</div>
                        <button onclick="openEdit('/edit_setor/{{s.id}}', 'Editar Setor', [{label:'Nome do Setor', name:'nome', type:'text', value:'{{s.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                    </td></tr>{% endfor %}
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
                    {% for f in funcionarios %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
                        <div>{{f.nome}} - {{f.cargo}}</div>
                        <button onclick="openEdit('/edit_funcionario/{{f.id}}', 'Editar Funcionário', [{label:'Nome', name:'nome', type:'text', value:'{{f.nome}}', required:true}, {label:'Cargo', name:'cargo', type:'text', value:'{{f.cargo}}', required:false}, {label:'Setor', name:'setor_id', type:'select', value:'{{f.setor_id}}', options:[{% for s in setores %}{value:'{{s.id}}',text:'{{s.nome}}'},{% endfor %}]}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                    </td></tr>{% endfor %}
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
                    <button class="btn" style="background:#1e293b; color:white; margin-top:1rem; width:100%">Salvar Usuário</button>
                </form>
                <h4 style="margin-top:2rem">Usuários do Sistema</h4>
                <table style="margin-top:0.5rem">
                    {% for u in users_list %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
                        <div><strong>{{u.nome_completo}}</strong><br><small>{{u.username}} - {{u.perfil}}</small></div>
                        <button onclick="openEdit('/edit_user/{{u.id}}', 'Editar Usuário', [{label:'Nome', name:'nome_completo', type:'text', value:'{{u.nome_completo}}', required:true}, {label:'Username', name:'username', type:'text', value:'{{u.username}}', required:true}, {label:'Perfil', name:'perfil', type:'select', value:'{{u.perfil}}', options:[{value:'admin',text:'Administrador'},{value:'tecnico',text:'Técnico'},{value:'protecao',text:'Protecção'}]}, {label:'Nova Senha (Opcional)', name:'password', type:'password', value:'', required:false}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                    </td></tr>{% endfor %}
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
                    {% for m in marcas %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
                        <div>{{m.nome}}</div>
                        <button onclick="openEdit('/edit_marca/{{m.id}}', 'Editar Marca', [{label:'Nome da Marca', name:'nome', type:'text', value:'{{m.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                    </td></tr>{% endfor %}
                </table>
            </div>

            <!-- Tipos de Equip. -->
            <div class="card">
                <h3>Adicionar Tipo de Equip.</h3>
                <form method="POST" action="/add_tipo">
                    <input name="nome" placeholder="Ex: Desktop, Monitor" required>
                    <button class="btn btn-green" style="margin-top:1rem; width:100%">Salvar Tipo</button>
                </form>
                <h4 style="margin-top:2rem">Tipos Cadastrados</h4>
                <table style="margin-top:0.5rem">
                    {% for t in tipos %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
                        <div>{{t.nome}}</div>
                        <button onclick="openEdit('/edit_tipo/{{t.id}}', 'Editar Tipo', [{label:'Nome do Tipo', name:'nome', type:'text', value:'{{t.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                    </td></tr>{% endfor %}
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
                    {% for m in motivos %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
                        <div>{{m.nome}}</div>
                        <button onclick="openEdit('/edit_motivo/{{m.id}}', 'Editar Motivo', [{label:'Nome do Motivo', name:'nome', type:'text', value:'{{m.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                    </td></tr>{% endfor %}
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
                    {% for f in fornecedores %}<tr><td style="display:flex; justify-content:space-between; align-items:center;">
                        <div>{{f.nome}}</div>
                        <button onclick="openEdit('/edit_fornecedor/{{f.id}}', 'Editar Fornecedor', [{label:'Nome', name:'nome', type:'text', value:'{{f.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
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
                        <button onclick="openEdit('/edit_instituicao/{{i.id}}', 'Editar Instituição', [{label:'Nome', name:'nome', type:'text', value:'{{i.nome}}', required:true}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>
                    </td></tr>{% endfor %}
                </table>
            </div>

        </div>
    </div>
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
</body></html>'''"""

# Find CADASTROS_TEMPLATE and replace
content = re.sub(r"CADASTROS_TEMPLATE = '''<!DOCTYPE html><html lang=\"pt\"><head>'''.*?</body></html>'''", new_cadastros_template, content, flags=re.DOTALL)

open('app.py', 'w', encoding='utf-8').write(content)
print("Patch 9 applied: CADASTROS_TEMPLATE completely rewritten.")
