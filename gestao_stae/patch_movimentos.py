import re
import os

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add MOVIMENTOS_TEMPLATE before the first route definition
route_idx = content.find("@app.route('/')")
if route_idx != -1 and "MOVIMENTOS_TEMPLATE =" not in content:
    MOVIMENTOS_TEMPLATE = '''MOVIMENTOS_TEMPLATE = """<!DOCTYPE html><html lang="pt"><head>""" + COMMON_HEAD + """<title>Todos os Movimentos - STAE</title>
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
                    <td style="padding:1rem">
                        <button onclick="toggleDetails('det_{{loop.index}}')" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-right:0.3rem;">Detalhes</button>
                        <a href="/ver_guia/{{m.guia}}" target="_blank" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-right:0.3rem">PDF</a>
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

'''
    content = content[:route_idx] + MOVIMENTOS_TEMPLATE + "\n" + content[route_idx:]

# 2. Add the /movimentos route
if "@app.route('/movimentos')" not in content:
    route_code = """
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
        c.execute("SELECT * FROM movimentos WHERE setor_origem_id=? OR setor_destino_id=? OR (setor_origem_id IS NULL AND setor_destino_id IS NULL) ORDER BY id DESC", (setor_id, setor_id))
        
    cols = [d[0] for d in c.description]
    movs = [dict(zip(cols, r)) for r in c.fetchall()]
    
    c.execute("SELECT id, nome FROM funcionarios")
    func_map = {str(r[0]): r[1] for r in c.fetchall()}
    
    for m in movs:
        m['entregue_nome'] = func_map.get(str(m.get('entregue_por')), m.get('entregue_por') or '-')
        m['recebido_nome'] = func_map.get(str(m.get('recebido_por')), m.get('recebido_por') or '-')
        m['protecao_nome'] = func_map.get(str(m.get('agente_protecao')), m.get('agente_protecao') or '-')
        
    conn.close()
    return render_template_string(MOVIMENTOS_TEMPLATE, movimentos=movs)
"""
    # Insert it right before @app.route('/api/funcionarios')
    api_func_idx = content.find("@app.route('/api/funcionarios')")
    if api_func_idx != -1:
        content = content[:api_func_idx] + route_code + "\n" + content[api_func_idx:]

# 3. Add button to MAIN_TEMPLATE
if 'href="/movimentos"' not in content:
    btn_html = """<a href="/movimentos" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a"> 📋 Todos os Movimentos</a>"""
    content = content.replace(
        '<a href="/inventario" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a"> 📦 Inventário DDGEI</a>',
        '<a href="/inventario" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a"> 📦 Inventário DDGEI</a>\n            ' + btn_html
    )

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Movimentos screen added.")
