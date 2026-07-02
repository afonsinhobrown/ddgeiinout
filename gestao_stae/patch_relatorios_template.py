with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

target_rel_template = """RELATORIOS_TEMPLATE = \"\"\"<!DOCTYPE html><html lang="pt"><head>\"\"\" + COMMON_HEAD + \"\"\"<title>Dashboard STAE - Relatórios</title>
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
</body></html>\"\"\""""

repl_rel_template = """RELATORIOS_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>Relatórios - STAE</title>
<style>
    .tab-header { display: flex; gap: 1rem; border-bottom: 2px solid var(--border); margin-bottom: 1.5rem; }
    .tab-btn { background: none; border: none; padding: 0.75rem 1.5rem; font-weight: bold; cursor: pointer; color: #64748b; border-bottom: 3px solid transparent; transition: all 0.3s; }
    .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
    .filters-box { background: #f8fafc; border: 1px solid var(--border); border-radius: 0.5rem; padding: 1.25rem; margin-bottom: 2rem; }
    .filters-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; align-items: end; }
    .export-row { display: flex; gap: 0.5rem; margin-top: 1.5rem; justify-content: flex-end; }
</style>
</head>
<body>
    <div class="nav">
        <strong>STAE GESTÃO - RELATÓRIOS E ESTATÍSTICAS</strong>
        <div>
            <a href="/" class="btn btn-outline" style="background:white; color:#0f172a;">⬅️ Voltar ao Início</a>
        </div>
    </div>
    <div class="container">
        
        <div class="tab-header">
            <button onclick="switchTab('inventario')" class="tab-btn {% if tab == 'inventario' %}active{% endif %}">📦 Inventário</button>
            <button onclick="switchTab('entradas_saidas')" class="tab-btn {% if tab == 'entradas_saidas' %}active{% endif %}">⚖️ Entradas & Saídas</button>
            <button onclick="switchTab('movimentos')" class="tab-btn {% if tab == 'movimentos' %}active{% endif %}">🔄 Histórico Geral (Movimentos)</button>
        </div>

        <div class="filters-box">
            <form id="filterForm" method="GET" action="/relatorios">
                <input type="hidden" name="tab" id="activeTabInput" value="{{ tab }}">
                <div class="filters-grid">
                    
                    {% if tab != 'movimentos' %}
                    <div>
                        <label style="font-size:0.85rem; font-weight:600; color:#475569;">Tipo de Equipamento</label>
                        <select name="tipo_equipamento" style="margin-top:0.25rem;">
                            <option value="">-- Todos --</option>
                            {% for t in tipos_eq %}<option value="{{t.nome}}" {% if selected_tipo_eq == t.nome %}selected{% endif %}>{{t.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label style="font-size:0.85rem; font-weight:600; color:#475569;">Marca</label>
                        <select name="marca" style="margin-top:0.25rem;">
                            <option value="">-- Todas --</option>
                            {% for m in marcas %}<option value="{{m.nome}}" {% if selected_marca == m.nome %}selected{% endif %}>{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    {% endif %}
                    
                    {% if tab == 'inventario' or tab == 'movimentos' %}
                    <div>
                        <label style="font-size:0.85rem; font-weight:600; color:#475569;">Estado / Status</label>
                        <select name="status" style="margin-top:0.25rem;">
                            <option value="">-- Todos --</option>
                            {% if tab == 'inventario' %}
                            <option value="Disponível" {% if selected_status == 'Disponível' %}selected{% endif %}>Disponível</option>
                            <option value="Em uso" {% if selected_status == 'Em uso' %}selected{% endif %}>Em uso</option>
                            <option value="Danificado" {% if selected_status == 'Danificado' %}selected{% endif %}>Danificado</option>
                            <option value="Avariado" {% if selected_status == 'Avariado' %}selected{% endif %}>Avariado</option>
                            {% else %}
                            <option value="Entregue" {% if selected_status == 'Entregue' %}selected{% endif %}>Entregue</option>
                            <option value="Pendente" {% if selected_status == 'Pendente' %}selected{% endif %}>Pendente</option>
                            {% endif %}
                        </select>
                    </div>
                    {% endif %}
                    
                    {% if tab == 'movimentos' %}
                    <div>
                        <label style="font-size:0.85rem; font-weight:600; color:#475569;">Tipo de Movimento</label>
                        <select name="mov_tipo" style="margin-top:0.25rem;">
                            <option value="">-- Todos --</option>
                            <option value="ENTRADA" {% if mov_tipo == 'ENTRADA' %}selected{% endif %}>ENTRADA</option>
                            <option value="SAIDA" {% if mov_tipo == 'SAIDA' %}selected{% endif %}>SAIDA</option>
                            <option value="TRANSFERENCIA" {% if mov_tipo == 'TRANSFERENCIA' %}selected{% endif %}>TRANSFERÊNCIA</option>
                        </select>
                    </div>
                    {% endif %}

                    <div>
                        <label style="font-size:0.85rem; font-weight:600; color:#475569;">Setor</label>
                        <select name="setor_id" style="margin-top:0.25rem;">
                            <option value="">-- Todos --</option>
                            {% for s in setores %}<option value="{{s.id}}" {% if selected_setor == s.id|string %}selected{% endif %}>{{s.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    
                    {% if tab != 'inventario' %}
                    <div>
                        <label style="font-size:0.85rem; font-weight:600; color:#475569;">Data de Início</label>
                        <input type="date" name="data_inicio" value="{{ data_inicio }}" style="margin-top:0.25rem;">
                    </div>
                    <div>
                        <label style="font-size:0.85rem; font-weight:600; color:#475569;">Data de Fim</label>
                        <input type="date" name="data_fim" value="{{ data_fim }}" style="margin-top:0.25rem;">
                    </div>
                    {% endif %}
                    
                    <div>
                        <button type="submit" class="btn btn-blue" style="margin-top:0; width:100%; padding: 0.6rem;">🔍 Filtrar</button>
                    </div>
                </div>
            </form>
            
            <div class="export-row">
                <button onclick="exportarRelatorio('excel')" class="btn btn-green" style="background:#10b981;">🟢 Exportar para Excel (CSV)</button>
                <button onclick="exportarRelatorio('pdf')" class="btn btn-blue" style="background:#ef4444;">🔴 Exportar para PDF</button>
            </div>
        </div>

        <div class="card">
            <h3>Resultados da Consulta</h3>
            <div style="overflow-x: auto; margin-top: 1rem;">
                {% if tab == 'inventario' %}
                <table style="width:100%; border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f1f5f9; text-align:left; color:#64748b; font-size:0.8rem">
                            <th style="padding:0.75rem">ID</th>
                            <th style="padding:0.75rem">EQUIPAMENTO</th>
                            <th style="padding:0.75rem">MARCA</th>
                            <th style="padding:0.75rem">S/N</th>
                            <th style="padding:0.75rem">QUANTIDADE</th>
                            <th style="padding:0.75rem">ESTADO</th>
                            <th style="padding:0.75rem">DATA REGISTO</th>
                            <th style="padding:0.75rem">SETOR</th>
                            <th style="padding:0.75rem">OBSERVAÇÕES</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for item in items %}
                        <tr style="border-bottom:1px solid var(--border)">
                            <td style="padding:0.75rem; font-weight:bold;">{{ item.id }}</td>
                            <td style="padding:0.75rem; font-weight:600;">{{ item.equipamento }}</td>
                            <td style="padding:0.75rem">{{ item.marca }}</td>
                            <td style="padding:0.75rem; font-family:monospace;">{{ item.numero_serie }}</td>
                            <td style="padding:0.75rem; font-weight:bold; text-align:center;">{{ item.quantidade }}</td>
                            <td style="padding:0.75rem;">
                                {% if item.status == 'Disponível' %}
                                <span style="background:#dcfce3; color:#166534; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">{{ item.status }}</span>
                                {% elif item.status == 'Em uso' %}
                                <span style="background:#dbeafe; color:#1e40af; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">{{ item.status }}</span>
                                {% else %}
                                <span style="background:#fee2e2; color:#991b1b; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">{{ item.status }}</span>
                                {% endif %}
                            </td>
                            <td style="padding:0.75rem; font-size:0.85rem;">{{ item.data_registo }}</td>
                            <td style="padding:0.75rem; color:#475569;">{{ item.setor_nome or '-' }}</td>
                            <td style="padding:0.75rem; font-size:0.85rem; color:#64748b;">{{ item.observacoes or '-' }}</td>
                        </tr>
                        {% else %}
                        <tr><td colspan="9" style="padding:1.5rem; text-align:center; color:#64748b;">Nenhum item encontrado com estes filtros.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <table style="width:100%; border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f1f5f9; text-align:left; color:#64748b; font-size:0.8rem">
                            <th style="padding:0.75rem">GUIA</th>
                            <th style="padding:0.75rem">TIPO</th>
                            <th style="padding:0.75rem">EQUIPAMENTO</th>
                            <th style="padding:0.75rem">MARCA</th>
                            <th style="padding:0.75rem">S/N</th>
                            <th style="padding:0.75rem">ORIGEM/DESTINO</th>
                            <th style="padding:0.75rem">QUANTIDADE</th>
                            <th style="padding:0.75rem">DATA</th>
                            <th style="padding:0.75rem">ESTADO</th>
                            <th style="padding:0.75rem">TÉCNICO</th>
                            <th style="padding:0.75rem">MOTIVO</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for m in items %}
                        <tr style="border-bottom:1px solid var(--border)">
                            <td style="padding:0.75rem; font-weight:bold; font-family:monospace;">{{ m.guia }}</td>
                            <td style="padding:0.75rem; font-weight:600;">
                                {% if m.tipo == 'ENTRADA' %}
                                <span style="color:#10b981;">ENTRADA</span>
                                {% elif m.tipo == 'SAIDA' %}
                                <span style="color:#3b82f6;">SAÍDA</span>
                                {% else %}
                                <span style="color:#8b5cf6;">TRANSFERÊNCIA</span>
                                {% endif %}
                            </td>
                            <td style="padding:0.75rem;">{{ m.equipamento }}</td>
                            <td style="padding:0.75rem;">{{ m.marca }}</td>
                            <td style="padding:0.75rem; font-family:monospace;">{{ m.numero_serie }}</td>
                            <td style="padding:0.75rem; font-size:0.85rem;">{{ m.origem_destino }}</td>
                            <td style="padding:0.75rem; text-align:center; font-weight:bold;">{{ m.quantidade or '-' }}</td>
                            <td style="padding:0.75rem; font-size:0.85rem;">{{ m.data }}</td>
                            <td style="padding:0.75rem;">
                                {% if m.status == 'Entregue' %}
                                <span style="background:#dcfce3; color:#166534; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">Entregue</span>
                                {% else %}
                                <span style="background:#ffedd5; color:#9a3412; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">Pendente</span>
                                {% endif %}
                            </td>
                            <td style="padding:0.75rem; font-size:0.85rem; color:#475569;">{{ m.tecnico }}</td>
                            <td style="padding:0.75rem; font-size:0.85rem; color:#64748b;">{{ m.motivo or '-' }}</td>
                        </tr>
                        {% else %}
                        <tr><td colspan="11" style="padding:1.5rem; text-align:center; color:#64748b;">Nenhuma movimentação encontrada com estes filtros.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% endif %}
            </div>
        </div>
    </div>

    <script>
        function switchTab(tabName) {
            document.getElementById("activeTabInput").value = tabName;
            // Clear other fields to prevent filter mismatch
            const form = document.getElementById("filterForm");
            const inputs = form.querySelectorAll("input:not([type=hidden]), select");
            inputs.forEach(i => i.value = "");
            form.submit();
        }

        function exportarRelatorio(type) {
            const form = document.getElementById("filterForm");
            const params = new URLSearchParams(new FormData(form)).toString();
            window.open(`/relatorios/export/${type}?${params}`, '_blank');
        }
    </script>
</body></html>'''"""

content = content.replace(target_rel_template, repl_rel_template)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("[+] RELATORIOS_TEMPLATE successfully patched.")
