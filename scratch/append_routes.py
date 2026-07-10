import os

routes_code = """
@eleitoral_bp.route('/distribuicao')
def distribuicao():
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    
    # Processo Ativo
    c.execute("SELECT * FROM eleitoral_processo_eleitoral WHERE estado = 'EM_CURSO' ORDER BY id DESC LIMIT 1")
    processo_ativo = c.fetchone()
    
    if not processo_ativo:
        conn.close()
        flash("Nenhum processo eleitoral ativo no momento. Inicie um processo para gerir a distribuição.", "warning")
        return redirect(url_for('eleitoral.dashboard'))
        
    processo_id = processo_ativo['id'] if is_pg else processo_ativo['id']
    
    # Locais
    c.execute("SELECT * FROM eleitoral_local_armazenamento WHERE activo = 1 ORDER BY tipo, nome")
    locais = c.fetchall()
    
    # Materiais (Tipos)
    c.execute("SELECT * FROM eleitoral_tipo_material ORDER BY nome")
    tipos_material = c.fetchall()
    
    # Estoque Atual
    c.execute('''
        SELECT l.nome as local, t.nome as material, t.variante, s.quantidade_total as total, s.quantidade_bom as bom, s.quantidade_mau as mau
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_local_armazenamento l ON s.local_id = l.id
        JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
        WHERE s.processo_id = %s
        ORDER BY l.tipo, l.nome, t.nome
    ''' if is_pg else '''
        SELECT l.nome as local, t.nome as material, t.variante, s.quantidade_total as total, s.quantidade_bom as bom, s.quantidade_mau as mau
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_local_armazenamento l ON s.local_id = l.id
        JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
        WHERE s.processo_id = ?
        ORDER BY l.tipo, l.nome, t.nome
    ''', (processo_id,))
    estoque = c.fetchall()
    
    # Guias de Movimentação (Em Trânsito e Recebidas)
    c.execute('''
        SELECT m.*, lo.nome as origem, ld.nome as destino
        FROM eleitoral_movimento_material m
        JOIN eleitoral_local_armazenamento lo ON m.local_origem_id = lo.id
        JOIN eleitoral_local_armazenamento ld ON m.local_destino_id = ld.id
        WHERE m.processo_id = %s
        ORDER BY m.id DESC LIMIT 50
    ''' if is_pg else '''
        SELECT m.*, lo.nome as origem, ld.nome as destino
        FROM eleitoral_movimento_material m
        JOIN eleitoral_local_armazenamento lo ON m.local_origem_id = lo.id
        JOIN eleitoral_local_armazenamento ld ON m.local_destino_id = ld.id
        WHERE m.processo_id = ?
        ORDER BY m.id DESC LIMIT 50
    ''', (processo_id,))
    movimentos_raw = c.fetchall()
    movimentos = [dict(m) for m in movimentos_raw] if not is_pg else movimentos_raw
    
    for m in movimentos:
        m_id = m['id']
        c.execute('''
            SELECT i.*, t.nome as material, t.variante
            FROM eleitoral_movimento_item i
            JOIN eleitoral_tipo_material t ON i.tipo_material_id = t.id
            WHERE i.movimento_id = %s
        ''' if is_pg else '''
            SELECT i.*, t.nome as material, t.variante
            FROM eleitoral_movimento_item i
            JOIN eleitoral_tipo_material t ON i.tipo_material_id = t.id
            WHERE i.movimento_id = ?
        ''', (m_id,))
        m['itens'] = c.fetchall()
    
    conn.close()
    
    return render_template('eleitoral/distribuicao.html', 
                           processo_ativo=processo_ativo,
                           locais=locais,
                           tipos_material=tipos_material,
                           estoque=estoque,
                           movimentos=movimentos)

@eleitoral_bp.route('/distribuicao/aquisicao', methods=['POST'])
def nova_aquisicao():
    processo_id = request.form.get('processo_id')
    local_id = request.form.get('local_id')
    tipo_material_id = request.form.get('tipo_material_id')
    quantidade_bom = float(request.form.get('quantidade_bom') or 0)
    quantidade_mau = float(request.form.get('quantidade_mau') or 0)
    quantidade_total = quantidade_bom + quantidade_mau
    
    utilizador_id = session.get('user_id')
    
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    
    # Verifica se já existe registo deste material neste local para este processo
    if is_pg:
        c.execute("SELECT id FROM eleitoral_material_sobrante WHERE processo_id = %s AND local_id = %s AND tipo_material_id = %s", (processo_id, local_id, tipo_material_id))
    else:
        c.execute("SELECT id FROM eleitoral_material_sobrante WHERE processo_id = ? AND local_id = ? AND tipo_material_id = ?", (processo_id, local_id, tipo_material_id))
    
    row = c.fetchone()
    
    if row:
        row_id = row['id'] if is_pg else row['id']
        if is_pg:
            c.execute("UPDATE eleitoral_material_sobrante SET quantidade_total = quantidade_total + %s, quantidade_bom = quantidade_bom + %s, quantidade_mau = quantidade_mau + %s WHERE id = %s",
                      (quantidade_total, quantidade_bom, quantidade_mau, row_id))
        else:
            c.execute("UPDATE eleitoral_material_sobrante SET quantidade_total = quantidade_total + ?, quantidade_bom = quantidade_bom + ?, quantidade_mau = quantidade_mau + ? WHERE id = ?",
                      (quantidade_total, quantidade_bom, quantidade_mau, row_id))
    else:
        if is_pg:
            c.execute("INSERT INTO eleitoral_material_sobrante (processo_id, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau, origem, utilizador_id) VALUES (%s, %s, %s, %s, %s, %s, 'AQUISICAO', %s)",
                      (processo_id, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau, utilizador_id))
        else:
            c.execute("INSERT INTO eleitoral_material_sobrante (processo_id, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau, origem, utilizador_id) VALUES (?, ?, ?, ?, ?, ?, 'AQUISICAO', ?)",
                      (processo_id, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau, utilizador_id))
            
    conn.commit()
    conn.close()
    flash("Nova aquisição registada com sucesso no inventário ativo!", "success")
    return redirect(url_for('eleitoral.distribuicao'))

@eleitoral_bp.route('/distribuicao/nova_guia', methods=['GET', 'POST'])
def nova_guia():
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    
    if request.method == 'POST':
        processo_id = request.form.get('processo_id')
        local_origem_id = request.form.get('local_origem_id')
        local_destino_id = request.form.get('local_destino_id')
        observacoes = request.form.get('observacoes')
        utilizador_id = session.get('user_id')
        
        # Get array of materials and quantities
        tipos_material_ids = request.form.getlist('item_tipo_material_id[]')
        quantidades_bom = request.form.getlist('item_quantidade_bom[]')
        quantidades_mau = request.form.getlist('item_quantidade_mau[]')
        
        try:
            # 1. Criar Guia (Movimento)
            param_marker = '%s' if is_pg else '?'
            if is_pg:
                c.execute("INSERT INTO eleitoral_movimento_material (processo_id, local_origem_id, local_destino_id, estado, observacoes_envio, utilizador_envio_id) VALUES (%s, %s, %s, 'EM_TRANSITO', %s, %s) RETURNING id", 
                          (processo_id, local_origem_id, local_destino_id, observacoes, utilizador_id))
                mov_id = c.fetchone()['id']
            else:
                c.execute("INSERT INTO eleitoral_movimento_material (processo_id, local_origem_id, local_destino_id, estado, observacoes_envio, utilizador_envio_id) VALUES (?, ?, ?, 'EM_TRANSITO', ?, ?)", 
                          (processo_id, local_origem_id, local_destino_id, observacoes, utilizador_id))
                mov_id = c.lastrowid
                
            # 2. Inserir itens e deduzir da origem
            for i in range(len(tipos_material_ids)):
                tm_id = tipos_material_ids[i]
                q_bom = float(quantidades_bom[i]) if quantidades_bom[i] else 0
                q_mau = float(quantidades_mau[i]) if quantidades_mau[i] else 0
                q_total = q_bom + q_mau
                
                if q_total > 0:
                    c.execute(f"INSERT INTO eleitoral_movimento_item (movimento_id, tipo_material_id, quantidade_bom, quantidade_mau) VALUES ({param_marker}, {param_marker}, {param_marker}, {param_marker})", 
                              (mov_id, tm_id, q_bom, q_mau))
                    
                    # Deduz da origem
                    c.execute(f"UPDATE eleitoral_material_sobrante SET quantidade_total = quantidade_total - {param_marker}, quantidade_bom = quantidade_bom - {param_marker}, quantidade_mau = quantidade_mau - {param_marker} WHERE processo_id = {param_marker} AND local_id = {param_marker} AND tipo_material_id = {param_marker}",
                              (q_total, q_bom, q_mau, processo_id, local_origem_id, tm_id))
            
            conn.commit()
            flash("Guia de distribuição criada e material está agora Em Trânsito!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao emitir guia: {str(e)}", "error")
            
        conn.close()
        return redirect(url_for('eleitoral.distribuicao'))
        
    # GET method
    c.execute("SELECT * FROM eleitoral_processo_eleitoral WHERE estado = 'EM_CURSO' ORDER BY id DESC LIMIT 1")
    processo_ativo = c.fetchone()
    
    if not processo_ativo:
        conn.close()
        flash("Nenhum processo ativo.", "warning")
        return redirect(url_for('eleitoral.dashboard'))
        
    c.execute("SELECT * FROM eleitoral_local_armazenamento WHERE activo = 1 ORDER BY tipo, nome")
    locais = c.fetchall()
    
    c.execute("SELECT * FROM eleitoral_tipo_material ORDER BY nome")
    tipos_material = c.fetchall()
    
    conn.close()
    return render_template('eleitoral/nova_guia.html', processo_ativo=processo_ativo, locais=locais, tipos_material=tipos_material)

@eleitoral_bp.route('/distribuicao/<int:id>/confirmar', methods=['POST'])
def confirmar_rececao(id):
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    
    utilizador_id = session.get('user_id')
    param_marker = '%s' if is_pg else '?'
    
    try:
        # Get movimento details
        c.execute(f"SELECT * FROM eleitoral_movimento_material WHERE id = {param_marker}", (id,))
        mov = c.fetchone()
        
        if not mov or mov['estado' if is_pg else 'estado'] != 'EM_TRANSITO':
            conn.close()
            flash("Movimento inválido ou já rececionado.", "error")
            return redirect(url_for('eleitoral.distribuicao'))
            
        processo_id = mov['processo_id' if is_pg else 'processo_id']
        destino_id = mov['local_destino_id' if is_pg else 'local_destino_id']
        
        # Update estado
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(f"UPDATE eleitoral_movimento_material SET estado = 'RECEBIDO', data_recepcao = {param_marker}, utilizador_recepcao_id = {param_marker} WHERE id = {param_marker}", (now, utilizador_id, id))
        
        # Get itens
        c.execute(f"SELECT * FROM eleitoral_movimento_item WHERE movimento_id = {param_marker}", (id,))
        itens = c.fetchall()
        
        for item in itens:
            tm_id = item['tipo_material_id' if is_pg else 'tipo_material_id']
            q_bom = item['quantidade_bom' if is_pg else 'quantidade_bom']
            q_mau = item['quantidade_mau' if is_pg else 'quantidade_mau']
            q_total = q_bom + q_mau
            
            # Check if exists in Destino
            c.execute(f"SELECT id FROM eleitoral_material_sobrante WHERE processo_id = {param_marker} AND local_id = {param_marker} AND tipo_material_id = {param_marker}", (processo_id, destino_id, tm_id))
            row = c.fetchone()
            
            if row:
                row_id = row['id' if is_pg else 'id']
                c.execute(f"UPDATE eleitoral_material_sobrante SET quantidade_total = quantidade_total + {param_marker}, quantidade_bom = quantidade_bom + {param_marker}, quantidade_mau = quantidade_mau + {param_marker} WHERE id = {param_marker}",
                          (q_total, q_bom, q_mau, row_id))
            else:
                c.execute(f"INSERT INTO eleitoral_material_sobrante (processo_id, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau, origem, utilizador_id) VALUES ({param_marker}, {param_marker}, {param_marker}, {param_marker}, {param_marker}, {param_marker}, 'MOVIMENTO', {param_marker})",
                          (processo_id, destino_id, tm_id, q_total, q_bom, q_mau, utilizador_id))
                          
        conn.commit()
        flash("Guia rececionada com sucesso! Material somado ao stock de destino.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao confirmar receção: {str(e)}", "error")
        
    conn.close()
    return redirect(url_for('eleitoral.distribuicao'))

from flask import jsonify

@eleitoral_bp.route('/api/mapa_distribuicao')
def api_mapa_distribuicao():
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    
    # Processo Ativo
    c.execute("SELECT id FROM eleitoral_processo_eleitoral WHERE estado = 'EM_CURSO' ORDER BY id DESC LIMIT 1")
    processo_ativo = c.fetchone()
    
    if not processo_ativo:
        conn.close()
        return jsonify({})
        
    processo_id = processo_ativo['id'] if is_pg else processo_ativo['id']
    
    # Map Provincias and Brigades directly associated
    param = (processo_id,)
    query = '''
        SELECT 
            p.nome as provincia, 
            t.nome as material,
            SUM(s.quantidade_total) as total
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_local_armazenamento l ON s.local_id = l.id
        JOIN eleitoral_provincia p ON l.provincia_id = p.id OR (l.parent_id IS NOT NULL AND l.provincia_id IS NULL)
        JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
        WHERE s.processo_id = ?
        GROUP BY p.nome, t.nome
    '''
    if is_pg:
        query = query.replace('?', '%s')
        
    try:
        c.execute(query, param)
        rows = c.fetchall()
        
        # Build dictionary { 'Maputo': { 'Impressoras': 100, 'Kits': 50 }, 'Gaza': ... }
        res = {}
        for r in rows:
            prov = r['provincia'] if is_pg else r['provincia']
            mat = r['material'] if is_pg else r['material']
            tot = r['total'] if is_pg else r['total']
            
            # normalize province names for map keys (e.g. Maputo, Cabo Delgado)
            prov_key = prov.strip()
            
            if prov_key not in res:
                res[prov_key] = {}
            res[prov_key][mat] = tot
            
        conn.close()
        return jsonify(res)
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)})

"""

file_path = os.path.join(os.path.dirname(__file__), '../gestao_stae/routes_eleitoral.py')
with open(file_path, 'a', encoding='utf-8') as f:
    f.write(routes_code)

print("Rotas adicionadas com sucesso!")
