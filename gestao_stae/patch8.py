import re

content = open('app.py', encoding='utf-8').read()

# Fix Javascript in MAIN_TEMPLATE
script_block = '''
    <script>
        function show(id){
            document.getElementById('ent').classList.add('hidden');
            document.getElementById('sai').classList.add('hidden');
            document.getElementById(id).classList.remove('hidden');
            if(id === 'sai' || id === 'ent') loadFuncs(id);
        }
        function loadFuncs(type){
            fetch('/api/funcionarios').then(r=>r.json()).then(data=>{
                const pfx = type === 'ent' ? 'ent' : 'sai';
                const selE = document.getElementById(pfx + '_entregue');
                const selR = document.getElementById(pfx + '_recebido');
                const selP = document.getElementById(pfx + '_protecao');
                
                selE.innerHTML = '<option value="">-- Selecione quem entregou --</option>';
                selR.innerHTML = '<option value="">-- Selecione quem recebeu --</option>';
                selP.innerHTML = '<option value="">-- Opcional --</option>';
                
                data.forEach(f => {
                    const opt = `<option value="${f.id}">${f.nome} (${f.setor})</option>`;
                    selE.innerHTML += opt;
                    selR.innerHTML += opt;
                    if (f.setor && f.setor.toLowerCase().includes('prote')) {
                        selP.innerHTML += opt;
                    }
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
    </script>
</body></html>'''

# Replace whatever is between <script> and </body></html>''' with my proper script block
content = re.sub(r'<script>.*?</body></html>\'\'\'', script_block, content, flags=re.DOTALL)

# Add Edit button in Main Table
btn_old = '''<a href="/ver_guia/{{m.guia}}" target="_blank" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem">PDF</a>'''
btn_new = '''<a href="/ver_guia/{{m.guia}}" target="_blank" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-right:0.3rem">PDF</a>
<a href="/edit_movimento_form/{{m.guia}}" class="btn btn-blue" style="padding:0.3rem 0.6rem; font-size:0.8rem">Editar</a>'''
content = content.replace(btn_old, btn_new)

# Since we need an edit form, let's just make /edit_movimento_form/<guia> render a quick page for editing
edit_route = '''
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

    html = f"""<!DOCTYPE html><html lang="pt"><head>{COMMON_HEAD}<title>Editar Movimento</title></head><body>
    <div class="nav"><strong>Editar Movimento: {guia}</strong><a href="/" class="btn btn-outline">Voltar</a></div>
    <div class="container"><div class="card" style="max-width:600px; margin:0 auto;">
    <form method="POST" action="/edit_movimento/{guia}">
        <label>Status</label><select name="status"><option value="Aguardando reparação" {'selected' if mov['status']=='Aguardando reparação' else ''}>Aguardando reparação</option><option value="Reparado e Entregue" {'selected' if mov['status']=='Reparado e Entregue' else ''}>Reparado e Entregue</option></select><br><br>
        <label>Quantidade</label><input name="quantidade" value="{mov.get('quantidade', '')}"><br><br>
        <label>Motivo</label><select name="motivo">"""
    
    for m in motivos: html += f'<option value="{m}" {"selected" if mov.get("motivo")==m else ""}>{m}</option>'
    html += f"""</select><br><br>
        <label>Fornecedor</label><select name="fornecedor">"""
    for f in fornecedores: html += f'<option value="{f}" {"selected" if mov.get("fornecedor")==f else ""}>{f}</option>'
    html += f"""</select><br><br>
        <button class="btn btn-blue" style="width:100%">Salvar Alterações</button>
    </form></div></div></body></html>"""
    return html

'''
content = content.replace("@app.route('/edit_movimento/<guia>', methods=['POST'])", edit_route + "\n@app.route('/edit_movimento/<guia>', methods=['POST'])")

# In edit_movimento POST endpoint we need to add the new fields: quantidade, fornecedor
content = content.replace("c.execute('''UPDATE movimentos SET \n                 equipamento=?, marca=?, numero_serie=?, origem_destino=?, motivo=?, entregue_por=?, recebido_por=?, agente_protecao=?", "c.execute('''UPDATE movimentos SET \n                 status=?, quantidade=?, motivo=?, fornecedor=?")
content = content.replace("(request.form.get('equipamento'), request.form.get('marca'), request.form.get('numero_serie'), \n               request.form.get('origem_destino'), request.form.get('motivo'), request.form.get('entregue_por'), \n               request.form.get('recebido_por'), request.form.get('agente_protecao'), guia))", "(request.form.get('status'), request.form.get('quantidade'), request.form.get('motivo'), request.form.get('fornecedor'), guia))")

open('app.py', 'w', encoding='utf-8').write(content)
print("Patch 8 Fix JS and Add Edit Button applied")
