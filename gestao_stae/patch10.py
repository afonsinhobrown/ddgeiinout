import re

content = open('app.py', encoding='utf-8').read()

idx1 = content.find("LOGIN_TEMPLATE = '''")
idx2 = content.find("CADASTROS_TEMPLATE = '''")

before = content[:idx1]
after = content[idx2:]

login_template = """LOGIN_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>Login - STAE</title></head>
<body style="display:flex; justify-content:center; align-items:center; height:100vh; background:#f1f5f9">
    <div class="card" style="width:100%; max-width:400px; text-align:center">
        <h2>STAE - GESTÃO DE EQUIPAMENTOS</h2>
        <p style="color:#64748b; margin-bottom:2rem">Faça login para continuar</p>
        {% if error %}<div style="color:#ef4444; margin-bottom:1rem">{{error}}</div>{% endif %}
        <form method="POST" action="/login">
            <input type="text" name="username" placeholder="Usuário" required style="text-align:center">
            <input type="password" name="password" placeholder="Palavra-passe" required style="text-align:center">
            <button type="submit" class="btn btn-blue" style="width:100%; margin-top:1rem">Entrar</button>
        </form>
    </div>
</body></html>'''

"""

relatorios_template = """RELATORIOS_TEMPLATE = \"\"\"<!DOCTYPE html><html lang="pt"><head>\"\"\" + COMMON_HEAD + \"\"\"<title>Dashboard STAE - Relatórios</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="nav">
        <strong>STAE RELATÓRIOS E ESTATÍSTICAS</strong>
        <div>
            <a href="/" class="btn btn-outline" style="background:white; color:#0f172a; margin-right:1rem">⬅️ Voltar ao Início</a>
            <a href="/relatorio_pdf" target="_blank" class="btn btn-blue">📄 Imprimir Relatório Geral PDF</a>
        </div>
    </div>
    <div class="container">
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:2rem;">
            <div class="card">
                <h3 style="text-align:center">Movimentos por Tipo de Equipamento</h3>
                <canvas id="chartEquip"></canvas>
            </div>
            <div class="card">
                <h3 style="text-align:center">Entradas por Setor/Origem</h3>
                <canvas id="chartSetor"></canvas>
            </div>
        </div>
        <div class="card" style="margin-top:2rem">
            <h3 style="text-align:center">Resumo de Movimentos por Marca</h3>
            <canvas id="chartMarca"></canvas>
        </div>
    </div>
    <script>
        const dataEquip = {{ stat_equip | safe }};
        new Chart(document.getElementById('chartEquip'), {
            type: 'bar',
            data: {
                labels: dataEquip.map(d => d.equipamento),
                datasets: [
                    {label: 'Entradas', data: dataEquip.map(d => d.entradas), backgroundColor: '#10b981'},
                    {label: 'Saídas', data: dataEquip.map(d => d.saidas), backgroundColor: '#3b82f6'}
                ]
            }
        });

        const dataSetor = {{ stat_setor | safe }};
        new Chart(document.getElementById('chartSetor'), {
            type: 'doughnut',
            data: {
                labels: dataSetor.map(d => d.origem),
                datasets: [{
                    data: dataSetor.map(d => d.total),
                    backgroundColor: ['#f43f5e', '#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#64748b']
                }]
            }
        });

        const dataMarca = {{ stat_marca | safe }};
        new Chart(document.getElementById('chartMarca'), {
            type: 'bar',
            data: {
                labels: dataMarca.map(d => d.marca),
                datasets: [
                    {label: 'Entradas', data: dataMarca.map(d => d.entradas), backgroundColor: '#10b981'},
                    {label: 'Saídas', data: dataMarca.map(d => d.saidas), backgroundColor: '#3b82f6'}
                ]
            }
        });
    </script>
</body></html>\"\"\"

"""

main_template = """MAIN_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>STAE Gestão</title></head>
<body>
    <div class="nav">
        <strong>STAE GESTÃO</strong>
        <div>👤 {{session.nome}} ({{session.perfil}}) | <a href="/logout" style="color:white">Sair</a></div>
    </div>
    <div class="container">
        {% if msg %}<div style="background:#dcfce3; color:#166534; padding:1rem; border-radius:0.5rem; margin-bottom:1rem;">{{msg}}</div>{% endif %}
        
        <div style="display:flex; gap:1rem; margin-bottom:2rem; justify-content:center; flex-wrap:wrap">
            <button onclick="show('ent')" class="btn btn-green">📥 Entrada</button>
            <button onclick="show('sai')" class="btn btn-blue">📤 Saída</button>
            <a href="/relatorios" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a">📊 Dashboard de Relatórios</a>
            {% if session.perfil == 'admin' %}
            <a href="/cadastros" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a">⚙️ Cadastros (Admin)</a>
            {% endif %}
            <div style="margin-left:auto; padding:0.5rem 1rem; background:white; border-radius:0.5rem; border:1px solid #cbd5e1; font-weight:bold; color:#1e293b;">
                🔧 EM REPARAÇÃO: {{ em_reparacao }}
            </div>
        </div>

        <div id="ent" class="card hidden">
            <h3>Nova Entrada</h3>
            <form method="POST" action="/registrar_entrada">
                <div class="form-grid">
                    <div><label>Equipamento (Tipo)</label>
                        <select name="equipamento" required>
                            <option value="">-- Selecione --</option>
                            {% for t in tipos %}<option value="{{t.nome}}">{{t.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div><label>Marca</label>
                        <select name="marca" required>
                            <option value="">-- Selecione --</option>
                            {% for m in marcas %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div><label>S/N / Nº Série</label><input name="numero_serie" required placeholder="Ex: 1234 ou N/A"></div>
                    <div><label>Origem</label>
                        <select name="origem" required>
                            <option value="">-- Selecione --</option>
                            <optgroup label="Setores Internos">
                                {% for s in setores %}<option value="Interno - {{s.nome}}">{{s.nome}}</option>{% endfor %}
                            </optgroup>
                            <optgroup label="Instituições Externas">
                                {% for i in instituicoes %}<option value="Externo - {{i.nome}}">{{i.nome}}</option>{% endfor %}
                            </optgroup>
                        </select>
                    </div>
                    <div><label>Fornecedor</label>
                        <select name="fornecedor" required>
                            <option value="N/A">N/A</option>
                            {% for f in fornecedores %}
                                {% if f.nome != 'N/A' %}<option value="{{f.nome}}">{{f.nome}}</option>{% endif %}
                            {% endfor %}
                        </select>
                    </div>
                    <div><label>Quantidade</label><input name="quantidade" type="number" min="1" value="1" required></div>
                    <div style="grid-column: span 2;">
                        <label>Motivo</label>
                        <select name="motivo" required>
                            <option value="">-- Selecione --</option>
                            {% for m in motivos %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div style="grid-column: span 2; display:flex; gap:1rem;">
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Entregue por (Funcionário)</label>
                            <select name="entregue_por" id="ent_entregue" required></select>
                        </div>
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Recebido por (Funcionário)</label>
                            <select name="recebido_por" id="ent_recebido" required></select>
                        </div>
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Agente de Protecção</label>
                            <select name="agente_protecao" id="ent_protecao"></select>
                        </div>
                    </div>
                </div>
                <button type="submit" class="btn btn-green" style="margin-top:1.5rem; width:100%">CONFIRMAR ENTRADA</button>
            </form>
        </div>

        <div id="sai" class="card hidden">
            <h3>Nova Saída</h3>
            <form method="POST" action="/registrar_saida">
                <div class="form-grid">
                    <div><label>Equipamento (Tipo)</label>
                        <select name="equipamento" required>
                            <option value="">-- Selecione --</option>
                            {% for t in tipos %}<option value="{{t.nome}}">{{t.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div><label>Marca</label>
                        <select name="marca" required>
                            <option value="">-- Selecione --</option>
                            {% for m in marcas %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div><label>S/N / Nº Série</label><input name="numero_serie" required placeholder="Ex: 1234 ou N/A"></div>
                    <div><label>Destino</label>
                        <select name="destino" required>
                            <option value="">-- Selecione --</option>
                            <optgroup label="Setores Internos">
                                {% for s in setores %}<option value="Interno - {{s.nome}}">{{s.nome}}</option>{% endfor %}
                            </optgroup>
                            <optgroup label="Instituições Externas">
                                {% for i in instituicoes %}<option value="Externo - {{i.nome}}">{{i.nome}}</option>{% endfor %}
                            </optgroup>
                        </select>
                    </div>
                    <div><label>Fornecedor</label>
                        <select name="fornecedor" required>
                            <option value="N/A">N/A</option>
                            {% for f in fornecedores %}
                                {% if f.nome != 'N/A' %}<option value="{{f.nome}}">{{f.nome}}</option>{% endif %}
                            {% endfor %}
                        </select>
                    </div>
                    <div><label>Quantidade</label><input name="quantidade" type="number" min="1" value="1" required></div>
                    <div style="grid-column: span 2;">
                        <label>Motivo</label>
                        <select name="motivo" required>
                            <option value="">-- Selecione --</option>
                            {% for m in motivos %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div style="grid-column: span 2; display:flex; gap:1rem;">
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Entregue por (Funcionário)</label>
                            <select name="entregue_por" id="sai_entregue" required></select>
                        </div>
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Recebido por (Funcionário)</label>
                            <select name="recebido_por" id="sai_recebido" required></select>
                        </div>
                        <div style="flex:1">
                            <label style="font-size:0.9rem; color:#64748b">Agente de Protecção</label>
                            <select name="agente_protecao" id="sai_protecao"></select>
                        </div>
                    </div>
                </div>
                <button type="submit" class="btn btn-blue" style="margin-top:1.5rem; width:100%">GERAR GUIA</button>
            </form>
        </div>

        <div class="card">
            <h3>Histórico Recente</h3>
            <input type="text" id="searchInput" onkeyup="searchTable()" placeholder="Pesquisar guia, equipamento, origem..." style="width:100%; padding:0.8rem; margin-top:1rem; border:1px solid #cbd5e1; border-radius:4px; margin-bottom:1rem">
            <table id="mainTable" style="width:100%; border-collapse:collapse; margin-top:1rem; font-size:0.9rem">
                <tr style="background:#f1f5f9; text-align:left; color:#64748b; font-size:0.8rem">
                    <th style="padding:1rem">GUIA</th><th style="padding:1rem">EQUIPAMENTO</th>
                    <th style="padding:1rem">S/N</th><th style="padding:1rem">ORIGEM/DESTINO</th>
                    <th style="padding:1rem">STATUS</th><th style="padding:1rem">DATA</th><th style="padding:1rem">ACÇÕES</th>
                </tr>
                {% for m in movimentos %}
                <tr style="border-bottom:1px solid var(--border)">
                    <td style="padding:1rem"><strong>{{m.guia[:8]}}</strong><br>{{m.guia[8:]}}</td>
                    <td style="padding:1rem">{{m.equipamento}}<br><small style="color:#64748b">({{m.marca}})</small></td>
                    <td style="padding:1rem">{{m.numero_serie}}</td>
                    <td style="padding:1rem">{{m.origem_destino}}</td>
                    <td style="padding:1rem">{{m.status}}</td>
                    <td style="padding:1rem">{{m.data[:10]}}<br><small style="color:#64748b">{{m.data[11:]}}</small></td>
                    <td style="padding:1rem">
                        <button onclick="toggleDetails('det_{{loop.index}}')" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-right:0.3rem;">Detalhes</button>
                        <a href="/ver_guia/{{m.guia}}" target="_blank" class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.8rem; margin-right:0.3rem">PDF</a>
                        <a href="/edit_movimento_form/{{m.guia}}" class="btn btn-blue" style="padding:0.3rem 0.6rem; font-size:0.8rem">Editar</a>
                    </td>
                </tr>
                <tr id="det_{{loop.index}}" class="hidden" style="background:#f8fafc;">
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

"""

new_content = before + login_template + relatorios_template + main_template + after
open('app.py', 'w', encoding='utf-8').write(new_content)
print("Patch 10 syntax fixed")
