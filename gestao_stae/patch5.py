import sqlite3

content = open('app.py', encoding='utf-8').read()

# Create RELATORIOS_TEMPLATE
relatorios_template = '''
RELATORIOS_TEMPLATE = """<!DOCTYPE html><html lang="pt"><head>""" + COMMON_HEAD + """<title>Dashboard STAE - Relatórios</title>
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
</body></html>"""
'''
content = content.replace("MAIN_TEMPLATE = '''", relatorios_template + "\nMAIN_TEMPLATE = '''")

route_relatorios = '''
import json
@app.route('/relatorios')
def relatorios():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Entradas e Saidas por Equipamento
    c.execute("""SELECT equipamento, 
                 SUM(CASE WHEN tipo='ENTRADA' THEN 1 ELSE 0 END) as entradas,
                 SUM(CASE WHEN tipo='SAIDA' THEN 1 ELSE 0 END) as saidas
                 FROM movimentos GROUP BY equipamento""")
    stat_equip = [{'equipamento':r[0] or 'Desconhecido', 'entradas':r[1], 'saidas':r[2]} for r in c.fetchall()]
    
    # Entradas por Setor
    c.execute("""SELECT origem_destino, COUNT(*) as total FROM movimentos WHERE tipo='ENTRADA' GROUP BY origem_destino""")
    stat_setor = [{'origem':r[0] or 'Desconhecido', 'total':r[1]} for r in c.fetchall()]
    
    # Entradas e Saidas por Marca
    c.execute("""SELECT marca, 
                 SUM(CASE WHEN tipo='ENTRADA' THEN 1 ELSE 0 END) as entradas,
                 SUM(CASE WHEN tipo='SAIDA' THEN 1 ELSE 0 END) as saidas
                 FROM movimentos GROUP BY marca""")
    stat_marca = [{'marca':r[0] or 'Desconhecido', 'entradas':r[1], 'saidas':r[2]} for r in c.fetchall()]
    
    conn.close()
    return render_template_string(RELATORIOS_TEMPLATE, 
                                  stat_equip=json.dumps(stat_equip), 
                                  stat_setor=json.dumps(stat_setor),
                                  stat_marca=json.dumps(stat_marca))
'''
content = content.replace("@app.route('/relatorio_pdf')", route_relatorios + "\n@app.route('/relatorio_pdf')")

# Change button in MAIN_TEMPLATE to go to /relatorios
content = content.replace('<a href="/relatorio_pdf" target="_blank" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a">📄 Gerar Relatório PDF</a>', 
                          '<a href="/relatorios" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a">📊 Dashboard de Relatórios</a>')

open('app.py', 'w', encoding='utf-8').write(content)
print("Patch 5 Relatorios successfully applied")
