with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

target_form = """                <form method="POST" action="/add_user">
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
                </form>"""

repl_form = """                <form method="POST" action="/add_user">
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
                </form>"""

target_btn = """<button onclick="openEdit('/edit_user/{{u.id}}', 'Editar Usuário', [{label:'Nome Completo', name:'nome_completo', type:'text', value:'{{u.nome_completo}}', required:true}, {label:'Username', name:'username', type:'text', value:'{{u.username}}', required:true}, {label:'Perfil', name:'perfil', type:'select', value:'{{u.perfil}}', options:[{value:'admin',text:'Administrador'},{value:'tecnico',text:'Técnico'},{value:'protecao',text:'Protecção'}]}, {label:'Nova Senha (Opcional)', name:'password', type:'password', value:'', required:false}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>"""

repl_btn = """<button onclick="openEdit('/edit_user/{{u.id}}', 'Editar Usuário', [{label:'Nome Completo', name:'nome_completo', type:'text', value:'{{u.nome_completo}}', required:true}, {label:'Username', name:'username', type:'text', value:'{{u.username}}', required:true}, {label:'Perfil', name:'perfil', type:'select', value:'{{u.perfil}}', options:[{value:'admin',text:'Administrador'},{value:'tecnico',text:'Técnico'},{value:'protecao',text:'Protecção'}]}, {label:'Setor', name:'setor_id', type:'select', value:'{{u.setor_id or ""}}', options:[{value:'',text:'Nenhum'}, {% for s in setores %}{value:'{{s.id}}',text:'{{s.nome}}'},{% endfor %}]}, {label:'Nova Senha (Opcional)', name:'password', type:'password', value:'', required:false}])" class="btn btn-outline" style="padding:0.2rem 0.5rem; font-size:0.8rem">Editar</button>"""

content = content.replace(target_form, repl_form)
content = content.replace(target_btn, repl_btn)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("[+] Cadastros template sector selectors patched.")
