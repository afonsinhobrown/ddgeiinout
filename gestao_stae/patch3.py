import re

content = open('app.py', encoding='utf-8').read()

reg_ent_old = '''@app.route('/registrar_entrada', methods=['POST'])
def registrar_entrada():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    guia = f"ENT-{datetime.now().strftime('%Y')}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    c.execute("""INSERT INTO movimentos (guia, tipo, equipamento, numero_serie, marca, origem_destino, motivo, funcionario_id, tecnico, entregue_por, recebido_por, agente_protecao) 
                 VALUES (?, 'ENTRADA', ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)""",
              (guia, request.form['equipamento'], request.form['numero_serie'], request.form.get('marca'), request.form['origem'],
               request.form['motivo'], session['username'], request.form.get('entregue_por'), request.form.get('recebido_por'), request.form.get('agente_protecao')))
    conn.commit()
    conn.close()
    return redirect(url_for('index', msg="Entrada registada com sucesso!"))'''

reg_ent_new = '''@app.route('/registrar_entrada', methods=['POST'])
def registrar_entrada():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    guia = f"ENT-{datetime.now().strftime('%Y')}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    origem = request.form.get('origem_outro') if request.form.get('origem') == 'Outro' else request.form.get('origem')
    c.execute("""INSERT INTO movimentos (guia, tipo, equipamento, numero_serie, marca, origem_destino, motivo, tecnico, entregue_por, recebido_por, agente_protecao, fornecedor, quantidade) 
                 VALUES (?, 'ENTRADA', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (guia, request.form['equipamento'], request.form['numero_serie'], request.form.get('marca'), origem,
               request.form['motivo'], session['username'], request.form.get('entregue_por'), request.form.get('recebido_por'), request.form.get('agente_protecao'), request.form.get('fornecedor'), request.form.get('quantidade')))
    conn.commit()
    conn.close()
    return redirect(url_for('index', msg="Entrada registada com sucesso!"))'''
content = content.replace(reg_ent_old, reg_ent_new)

reg_sai_old = '''@app.route('/registrar_saida', methods=['POST'])
def registrar_saida():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    guia = f"SAI-{datetime.now().strftime('%Y')}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    c.execute("""INSERT INTO movimentos (guia, tipo, equipamento, numero_serie, marca, origem_destino, motivo, funcionario_id, tecnico, entregue_por, recebido_por, agente_protecao) 
                 VALUES (?, 'SAIDA', ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)""",
              (guia, request.form['equipamento'], request.form['numero_serie'], request.form.get('marca'), request.form['destino'],
               request.form['motivo'], session['username'], request.form.get('entregue_por'), request.form.get('recebido_por'), request.form.get('agente_protecao')))
    conn.commit()
    conn.close()
    return redirect(url_for('index', msg="Saída registada com sucesso!"))'''

reg_sai_new = '''@app.route('/registrar_saida', methods=['POST'])
def registrar_saida():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    guia = f"SAI-{datetime.now().strftime('%Y')}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    destino = request.form.get('destino_outro') if request.form.get('destino') == 'Outro' else request.form.get('destino')
    c.execute("""INSERT INTO movimentos (guia, tipo, equipamento, numero_serie, marca, origem_destino, motivo, tecnico, entregue_por, recebido_por, agente_protecao, fornecedor, quantidade) 
                 VALUES (?, 'SAIDA', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (guia, request.form['equipamento'], request.form['numero_serie'], request.form.get('marca'), destino,
               request.form['motivo'], session['username'], request.form.get('entregue_por'), request.form.get('recebido_por'), request.form.get('agente_protecao'), request.form.get('fornecedor'), request.form.get('quantidade')))
    conn.commit()
    conn.close()
    return redirect(url_for('index', msg="Saída registada com sucesso!"))'''
content = content.replace(reg_sai_old, reg_sai_new)

# Add details to main template table
details_old = '''                            <div><strong>Motivo:</strong> {{m.motivo or '-'}}</div>
                            <div><strong>Técnico do Sistema:</strong> {{m.tecnico or '-'}}</div>
                            <div><strong>Entregue Por:</strong> {{m.entregue_nome or '-'}}</div>
                            <div><strong>Recebido Por:</strong> {{m.recebido_nome or '-'}}</div>
                            <div><strong>Agente de Protecção:</strong> {{m.protecao_nome or '-'}}</div>'''

details_new = '''                            <div><strong>Motivo:</strong> {{m.motivo or '-'}}</div>
                            <div><strong>Técnico do Sistema:</strong> {{m.tecnico or '-'}}</div>
                            <div><strong>Fornecedor:</strong> {{m.fornecedor or '-'}}</div>
                            <div><strong>Quantidade:</strong> {{m.quantidade or '-'}}</div>
                            <div><strong>Entregue Por:</strong> {{m.entregue_nome or '-'}}</div>
                            <div><strong>Recebido Por:</strong> {{m.recebido_nome or '-'}}</div>
                            <div><strong>Agente de Protecção:</strong> {{m.protecao_nome or '-'}}</div>'''
content = content.replace(details_old, details_new)

open('app.py', 'w', encoding='utf-8').write(content)
print("Updated successfully")
