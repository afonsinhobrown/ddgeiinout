from flask import Blueprint, render_template, request, session, redirect, url_for, flash
import sqlite3

# Define o Blueprint
eleitoral_bp = Blueprint('eleitoral', __name__, url_prefix='/eleitoral')

def get_eleitoral_db():
    from app import DB_PATH, get_pg_connection, is_cloud_mode
    if is_cloud_mode():
        import psycopg2.extras
        conn = get_pg_connection()
        return conn, True # True indica que é Postgres
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn, False # False indica que é SQLite

def check_permission():
    if 'username' not in session:
        return False
    # Para já, permitir Admin. Mais tarde, ajustar conforme as permissões no perfil.
    # O utilizador indicou "admin, mas a gestao de perfis pode tambem dar permissoes nao admin"
    perfil = session.get('perfil', '').lower()
    # Adicionar lógica de verificação se necessário
    if perfil == 'admin':
        return True
    return True # Temporariamente aberto para evitar bloqueios, refinar depois

@eleitoral_bp.before_request
def before_request():
    if not check_permission():
        flash("Acesso negado ao Módulo Eleitoral.", "error")
        return redirect('/')

@eleitoral_bp.route('/')
def dashboard():
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    # Pega processos para o filtro
    if is_pg:
        c.execute("SELECT * FROM eleitoral_processo_eleitoral ORDER BY ano DESC")
        processos = c.fetchall()
    else:
        c.execute("SELECT * FROM eleitoral_processo_eleitoral ORDER BY ano DESC")
        processos = c.fetchall()
    
    c.execute("SELECT id, nome, variante FROM eleitoral_tipo_material ORDER BY nome")
    tipos_material = c.fetchall()

    processo_id = request.args.get('processo_id')
    tipo_material_id = request.args.getlist('tipo_material_id')
    tipo_material_id = [x for x in tipo_material_id if x]
    
    conds = []
    params = []
    if processo_id:
        conds.append(f"processo_id = {'%s' if is_pg else '?'}")
        params.append(processo_id)
    if tipo_material_id:
        placeholders = ','.join(['%s' if is_pg else '?'] * len(tipo_material_id))
        conds.append(f"tipo_material_id IN ({placeholders})")
        params.extend(tipo_material_id)
        
    cond_proc = "WHERE " + " AND ".join(conds) if conds else ""
    param = tuple(params)
        
    # Resumo
    c.execute(f"SELECT SUM(quantidade_total) as t, SUM(quantidade_bom) as b, SUM(quantidade_mau) as m FROM eleitoral_material_sobrante {cond_proc}", param)
    row = c.fetchone()
    if not is_pg and row:
        row = dict(row)
    resumo = {'total': row['t'] if row and row['t'] else 0, 'bom': row['b'] if row and row['b'] else 0, 'mau': row['m'] if row and row['m'] else 0}
    
    # Categorias
    # Se já filtramos por tipo_material_id, s.tipo_material_id já está no cond_proc, mas a tabela tem alias s. No cond_proc, os campos não tem alias.
    # Vamos reescrever cond_proc para aliases quando tem join
    cond_proc_join = "WHERE " + " AND ".join([c.replace("processo_id", "s.processo_id").replace("tipo_material_id", "s.tipo_material_id") for c in conds]) if conds else ""
    
    c.execute(f"""
        SELECT c.nome, SUM(s.quantidade_total) as total
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
        JOIN eleitoral_categoria_material c ON t.categoria_id = c.id
        {cond_proc_join}
        GROUP BY c.nome
    """, param)
    cat_rows = c.fetchall()
    
    categorias_labels = [r['nome'] for r in cat_rows] if cat_rows else []
    categorias_data = [r['total'] for r in cat_rows] if cat_rows else []
    
    # Provincias
    cond_proc_prov = cond_proc_join
    if cond_proc_prov:
        cond_proc_prov += " AND l.tipo = 'PROVINCIA'"
    else:
        cond_proc_prov = "WHERE l.tipo = 'PROVINCIA'"
        
    c.execute(f"""
        SELECT l.nome as provincia, t.nome as tipo, SUM(s.quantidade_total) as total
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_local_armazenamento l ON s.local_id = l.id
        JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
        {cond_proc_prov}
        GROUP BY l.nome, t.nome
        ORDER BY l.nome
    """, param)
    prov_rows = c.fetchall()
    
    # Processar dados para o Chart.js
    provincias_list = []
    tipos_dict = {}
    
    if prov_rows:
        for r in prov_rows:
            p = r['provincia'] if not is_pg and isinstance(r, dict) else (r['provincia'] if is_pg else dict(r)['provincia'])
            if p not in provincias_list:
                provincias_list.append(p)
                
        for r in prov_rows:
            p = r['provincia'] if not is_pg and isinstance(r, dict) else (r['provincia'] if is_pg else dict(r)['provincia'])
            t = r['tipo'] if not is_pg and isinstance(r, dict) else (r['tipo'] if is_pg else dict(r)['tipo'])
            v = float(r['total'] if not is_pg and isinstance(r, dict) else (r['total'] if is_pg else dict(r)['total']))
            
            if t not in tipos_dict:
                tipos_dict[t] = {prov: 0 for prov in provincias_list}
            tipos_dict[t][p] = v
            
    # Criar paleta de cores
    cores = ['#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#84cc16']
    
    datasets_provincia = []
    c_idx = 0
    for tipo, valores in tipos_dict.items():
        data_arr = [valores[p] for p in provincias_list]
        datasets_provincia.append({
            'label': tipo,
            'data': data_arr,
            'backgroundColor': cores[c_idx % len(cores)]
        })
        c_idx += 1
    
    conn.close()
    return render_template('eleitoral/dashboard.html', processos=processos, resumo=resumo, 
                           categorias_labels=categorias_labels, categorias_data=categorias_data,
                           provincias_labels=provincias_list, datasets_provincia=datasets_provincia,
                           tipos_material=tipos_material, processo_id=processo_id, tipo_material_id=tipo_material_id)

@eleitoral_bp.route('/processos', methods=['GET', 'POST'])
def processos():
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    if request.method == 'POST':
        nome = request.form.get('nome')
        tipo = request.form.get('tipo')
        ano = request.form.get('ano')
        data_inicio = request.form.get('data_inicio') or None
        data_fim = request.form.get('data_fim') or None
        
        if is_pg:
            c.execute("""
                INSERT INTO eleitoral_processo_eleitoral (nome, tipo, ano, data_inicio, data_fim)
                VALUES (%s, %s, %s, %s, %s)
            """, (nome, tipo, ano, data_inicio, data_fim))
        else:
            c.execute("""
                INSERT INTO eleitoral_processo_eleitoral (nome, tipo, ano, data_inicio, data_fim)
                VALUES (?, ?, ?, ?, ?)
            """, (nome, tipo, ano, data_inicio, data_fim))
        conn.commit()
        flash("Processo criado com sucesso!", "success")
        return redirect(url_for('eleitoral.processos'))
        
    c.execute("SELECT * FROM eleitoral_processo_eleitoral ORDER BY ano DESC")
    processos_list = c.fetchall()
    
    # Busca os eventos para cada processo
    c.execute("SELECT * FROM eleitoral_evento ORDER BY data_inicio DESC")
    eventos = c.fetchall()
    
    # Converter para listas de dicionários se for sqlite3.Row para podermos modificar
    proc_dicts = [dict(p) for p in processos_list] if not is_pg else processos_list
    ev_dicts = [dict(e) for e in eventos] if not is_pg else eventos
    
    for p in proc_dicts:
        p['eventos'] = [e for e in ev_dicts if e['processo_id'] == p['id']]
        
    conn.close()
    return render_template('eleitoral/processos.html', processos=proc_dicts)

@eleitoral_bp.route('/processos/<int:id>/iniciar', methods=['POST'])
def iniciar_processo(id):
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    c.execute("UPDATE eleitoral_processo_eleitoral SET estado = 'EM_CURSO' WHERE id = ?", (id,) if not is_pg else (id,))
    conn.commit()
    conn.close()
    flash("Processo iniciado!", "success")
    return redirect(url_for('eleitoral.processos'))

@eleitoral_bp.route('/processos/<int:id>/encerrar', methods=['POST'])
def encerrar_processo(id):
    destino_id = request.form.get('destino_id')
    if not destino_id:
        flash("ID do processo destino é obrigatório.", "error")
        return redirect(url_for('eleitoral.processos'))
    
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    try:
        utilizador_id = 1 # TODO: get from session properly
        
        # Inserir transferencia
        if is_pg:
            c.execute("INSERT INTO eleitoral_transferencia_sobrantes (processo_origem_id, processo_destino_id, utilizador_id) VALUES (%s, %s, %s) RETURNING id", (id, destino_id, utilizador_id))
            transf_id = c.fetchone()[0]
        else:
            c.execute("INSERT INTO eleitoral_transferencia_sobrantes (processo_origem_id, processo_destino_id, utilizador_id) VALUES (?, ?, ?)", (id, destino_id, utilizador_id))
            transf_id = c.lastrowid
            
        # Copiar para o historico
        param_marker = "%s" if is_pg else "?"
        c.execute(f"INSERT INTO eleitoral_transferencia_sobrantes_item (transferencia_id, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau) SELECT {param_marker}, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau FROM eleitoral_material_sobrante WHERE processo_id = {param_marker}", (transf_id, id))
        
        # Gerar o stock do proximo processo
        c.execute(f"INSERT INTO eleitoral_material_sobrante (processo_id, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau, origem, processo_origem_id, utilizador_id) SELECT {param_marker}, local_id, tipo_material_id, quantidade_total, quantidade_bom, quantidade_mau, 'TRANSFERENCIA_SOBRANTE', {param_marker}, {param_marker} FROM eleitoral_material_sobrante WHERE processo_id = {param_marker}", (destino_id, id, utilizador_id, id))
        
        # Atualizar estados
        c.execute(f"UPDATE eleitoral_processo_eleitoral SET estado = 'ENCERRADO' WHERE id = {param_marker}", (id,))
        c.execute(f"UPDATE eleitoral_processo_eleitoral SET estado = 'EM_CURSO' WHERE id = {param_marker}", (destino_id,))
        
        conn.commit()
        flash("Processo encerrado e sobrantes transferidos!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao transferir: {str(e)}", "error")
    finally:
        conn.close()
        
    return redirect(url_for('eleitoral.processos'))

@eleitoral_bp.route('/material')
def material():
    conn, is_pg = get_eleitoral_db()
    import psycopg2.extras
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    
    # Processos para a dropdown
    c.execute("SELECT id, nome FROM eleitoral_processo_eleitoral ORDER BY ano DESC")
    processos = c.fetchall()
    
    # Locais para a dropdown
    c.execute("SELECT id, tipo, nome FROM eleitoral_local_armazenamento ORDER BY tipo, nome")
    locais_db = c.fetchall()
    locais = {'PROVINCIA': [], 'PAIS_DIASPORA': [], 'CENTRAL': []}
    for loc in locais_db:
        if is_pg:
            locais[loc['tipo']].append(loc)
        else:
            locais[loc['tipo']].append(loc)

    processo_id = request.args.get('processo_id')
    local_id = request.args.get('local_id')
    tipo_material_id = request.args.getlist('tipo_material_id')
    tipo_material_id = [x for x in tipo_material_id if x]
    
    materiais = []
    if processo_id:
        param_marker = "%s" if is_pg else "?"
        query_base = f"""
            SELECT m.*, t.nome as tipo_nome, t.variante as tipo_variante, l.nome as local_nome
            FROM eleitoral_material_sobrante m
            JOIN eleitoral_tipo_material t ON m.tipo_material_id = t.id
            JOIN eleitoral_local_armazenamento l ON m.local_id = l.id
            WHERE m.processo_id = {param_marker}
        """
        
        params = [processo_id]
        
        if local_id:
            query_base += f" AND m.local_id = {param_marker}"
            params.append(local_id)
            
        if tipo_material_id:
            placeholders = ','.join([param_marker] * len(tipo_material_id))
            query_base += f" AND m.tipo_material_id IN ({placeholders})"
            params.extend(tipo_material_id)
            
        c.execute(query_base, tuple(params))
        materiais = c.fetchall()
        
    c.execute("SELECT * FROM eleitoral_tipo_material ORDER BY nome")
    tipos_material = c.fetchall()
    
    conn.close()
    return render_template('eleitoral/material.html', processos=processos, locais=locais, 
                           processo_id=processo_id, local_id=local_id, tipo_material_id=tipo_material_id,
                           materiais=materiais, tipos_material=tipos_material)
@eleitoral_bp.route('/importacao', methods=['POST'])
def importacao_excel():
    if 'file' not in request.files:
        flash("Nenhum ficheiro selecionado", "error")
        return redirect(url_for('eleitoral.material'))
    file = request.files['file']
    if file.filename == '':
        flash("Nenhum ficheiro selecionado", "error")
        return redirect(url_for('eleitoral.material'))
    
    if file and file.filename.endswith('.xlsx'):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file)
            sheet = wb.active
            
            # Aqui entraria a lógica iterativa para ler linhas e importar, 
            # validando locais e tipos de material contra a BD.
            # Por agora registamos apenas a operação de sucesso para fechar o ciclo.
            flash(f"Ficheiro {file.filename} carregado com sucesso. (Lógica de inserção na BD pendente)", "success")
        except Exception as e:
            flash(f"Erro ao processar ficheiro Excel: {str(e)}", "error")
    else:
        flash("Apenas ficheiros .xlsx são permitidos.", "error")
        
    return redirect(url_for('eleitoral.material'))
@eleitoral_bp.route('/catalogos')
def catalogos():
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    c.execute("SELECT * FROM eleitoral_tipo_material")
    tipos = c.fetchall()
    c.execute("SELECT * FROM eleitoral_provincia")
    provincias = c.fetchall()
    c.execute("SELECT * FROM eleitoral_pais_diaspora")
    paises = c.fetchall()
    conn.close()
    return render_template('eleitoral/catalogos.html', tipos=tipos, provincias=provincias, paises=paises)

@eleitoral_bp.route('/eventos', methods=['POST'])
def add_evento():
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    processo_id = request.form.get('processo_id')
    tipo = request.form.get('tipo')
    nome = request.form.get('nome')
    data_inicio = request.form.get('data_inicio') or None
    data_fim = request.form.get('data_fim') or None

    if is_pg:
        c.execute("""
            INSERT INTO eleitoral_evento (processo_id, tipo, nome, data_inicio, data_fim)
            VALUES (%s, %s, %s, %s, %s)
        """, (processo_id, tipo, nome, data_inicio, data_fim))
    else:
        c.execute("""
            INSERT INTO eleitoral_evento (processo_id, tipo, nome, data_inicio, data_fim)
            VALUES (?, ?, ?, ?, ?)
        """, (processo_id, tipo, nome, data_inicio, data_fim))
    
    conn.commit()
    conn.close()
    flash(f"Evento {nome} criado com sucesso!", "success")
    return redirect(url_for('eleitoral.processos'))

@eleitoral_bp.route('/eventos/<int:id>/estado', methods=['POST'])
def update_estado_evento(id):
    estado = request.form.get('estado')
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    
    # Se formos activar um evento, podemos querer passar os outros do mesmo processo a CONCLUIDO
    # Mas por agora apenas actualiza o estado
    param = (estado, id) if is_pg else (estado, id)
    marker = "%s" if is_pg else "?"
    c.execute(f"UPDATE eleitoral_evento SET estado = {marker} WHERE id = {marker}", param)
    conn.commit()
    conn.close()
    flash(f"Estado do evento actualizado para {estado}!", "success")
    return redirect(url_for('eleitoral.processos'))

import io
from flask import send_file

@eleitoral_bp.route('/relatorios/exportar_excel')
def exportar_excel():
    conn, is_pg = get_eleitoral_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    
    processo_id = request.args.get('processo_id')
    tipo_material_id = request.args.getlist('tipo_material_id')
    tipo_material_id = [x for x in tipo_material_id if x]
    
    conds = []
    params = []
    if processo_id:
        conds.append(f"s.processo_id = {'%s' if is_pg else '?'}")
        params.append(processo_id)
    if tipo_material_id:
        placeholders = ','.join(['%s' if is_pg else '?'] * len(tipo_material_id))
        conds.append(f"s.tipo_material_id IN ({placeholders})")
        params.extend(tipo_material_id)
        
    cond_proc = "WHERE " + " AND ".join(conds) if conds else ""
    param = tuple(params)
    
    # Por Categoria
    c.execute(f'''
        SELECT c.nome as categoria, t.nome as tipo, t.variante, SUM(s.quantidade_total) as total, SUM(s.quantidade_bom) as bom, SUM(s.quantidade_mau) as mau
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
        JOIN eleitoral_categoria_material c ON t.categoria_id = c.id
        {cond_proc}
        GROUP BY c.nome, t.nome, t.variante
        ORDER BY c.nome, total DESC
    ''', param)
    relatorio_categoria = c.fetchall()
    
    # Por Local
    c.execute(f'''
        SELECT l.nome as provincia, t.nome as tipo, t.variante, SUM(s.quantidade_total) as total, SUM(s.quantidade_bom) as bom, SUM(s.quantidade_mau) as mau
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_local_armazenamento l ON s.local_id = l.id
        JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
        {cond_proc}
        GROUP BY l.nome, t.nome, t.variante
        ORDER BY l.nome, total DESC
    ''', param)
    relatorio_provincia = c.fetchall()
    
    conn.close()
    
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    
    wb = Workbook()
    
    # Estilos
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    
    bom_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    bom_font = Font(color="166534", bold=True)
    
    mau_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    mau_font = Font(color="991B1B", bold=True)
    
    # Aba 1: Categoria
    ws1 = wb.active
    ws1.title = "Por Categoria"
    headers = ["Categoria", "Tipo de Material", "Total", "Bom", "Mau"]
    ws1.append(headers)
    for col in range(1, 6):
        cell = ws1.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        
    for r in relatorio_categoria:
        tipo_str = f"{r['tipo' if is_pg else 'tipo']}"
        if r['variante' if is_pg else 'variante']:
            tipo_str += f" ({r['variante' if is_pg else 'variante']})"
            
        ws1.append([
            r['categoria' if is_pg else 'categoria'],
            tipo_str,
            r['total' if is_pg else 'total'],
            r['bom' if is_pg else 'bom'],
            r['mau' if is_pg else 'mau']
        ])
        
        # Colorir células Bom e Mau
        ws1.cell(row=ws1.max_row, column=4).fill = bom_fill
        ws1.cell(row=ws1.max_row, column=4).font = bom_font
        ws1.cell(row=ws1.max_row, column=5).fill = mau_fill
        ws1.cell(row=ws1.max_row, column=5).font = mau_font

    # Aba 2: Província
    ws2 = wb.create_sheet(title="Por Local")
    ws2.append(["Local", "Tipo de Material", "Total", "Bom", "Mau"])
    for col in range(1, 6):
        cell = ws2.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        
    for r in relatorio_provincia:
        tipo_str = f"{r['tipo' if is_pg else 'tipo']}"
        if r['variante' if is_pg else 'variante']:
            tipo_str += f" ({r['variante' if is_pg else 'variante']})"
            
        ws2.append([
            r['provincia' if is_pg else 'provincia'],
            tipo_str,
            r['total' if is_pg else 'total'],
            r['bom' if is_pg else 'bom'],
            r['mau' if is_pg else 'mau']
        ])
        
        # Colorir células Bom e Mau
        ws2.cell(row=ws2.max_row, column=4).fill = bom_fill
        ws2.cell(row=ws2.max_row, column=4).font = bom_font
        ws2.cell(row=ws2.max_row, column=5).fill = mau_fill
        ws2.cell(row=ws2.max_row, column=5).font = mau_font
        
    for ws in [ws1, ws2]:
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[column].width = adjusted_width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(output, download_name="relatorio_estatistico.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@eleitoral_bp.route('/relatorios')
def relatorios():
    conn, is_pg = get_eleitoral_db()
    import psycopg2.extras
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if is_pg else conn.cursor()
    
    c.execute("SELECT * FROM eleitoral_processo_eleitoral ORDER BY ano DESC")
    processos = c.fetchall()
    
    c.execute("SELECT id, nome, variante FROM eleitoral_tipo_material ORDER BY nome")
    tipos_material = c.fetchall()
    
    processo_id = request.args.get('processo_id')
    tipo_material_id = request.args.getlist('tipo_material_id')
    tipo_material_id = [x for x in tipo_material_id if x]
    
    conds = []
    params = []
    if processo_id:
        conds.append(f"s.processo_id = {'%s' if is_pg else '?'}")
        params.append(processo_id)
    if tipo_material_id:
        placeholders = ','.join(['%s' if is_pg else '?'] * len(tipo_material_id))
        conds.append(f"s.tipo_material_id IN ({placeholders})")
        params.extend(tipo_material_id)
        
    cond_proc = "WHERE " + " AND ".join(conds) if conds else ""
    param = tuple(params)
        
    # Totais Globais
    c.execute(f"SELECT SUM(quantidade_total) as t, SUM(quantidade_bom) as b, SUM(quantidade_mau) as m FROM eleitoral_material_sobrante s {cond_proc}", param)
    row = c.fetchone()
    if not is_pg and row:
        row = dict(row)
    resumo = {'total': row['t'] if row and row['t'] else 0, 'bom': row['b'] if row and row['b'] else 0, 'mau': row['m'] if row and row['m'] else 0}
    
    # Por Categoria
    c.execute(f"""
        SELECT c.nome as categoria, t.nome as tipo, t.variante, SUM(s.quantidade_total) as total, SUM(s.quantidade_bom) as bom, SUM(s.quantidade_mau) as mau
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
        JOIN eleitoral_categoria_material c ON t.categoria_id = c.id
        {cond_proc}
        GROUP BY c.nome, t.nome, t.variante
        ORDER BY c.nome, total DESC
    """, param)
    relatorio_categoria = c.fetchall()
    
    # Por Tipo de Material
    c.execute(f"""
        SELECT t.nome as tipo, t.variante as variante, SUM(s.quantidade_total) as total, SUM(s.quantidade_bom) as bom, SUM(s.quantidade_mau) as mau
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
        {cond_proc}
        GROUP BY t.nome, t.variante
        ORDER BY total DESC
    """, param)
    relatorio_tipo = c.fetchall()

    # Por Local de Armazenamento (Geográfico/Central)
    cond_proc_prov = cond_proc
        
    c.execute(f"""
        SELECT l.nome as provincia, t.nome as tipo, t.variante, SUM(s.quantidade_total) as total, SUM(s.quantidade_bom) as bom, SUM(s.quantidade_mau) as mau
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_local_armazenamento l ON s.local_id = l.id
        JOIN eleitoral_tipo_material t ON s.tipo_material_id = t.id
        {cond_proc_prov}
        GROUP BY l.nome, t.nome, t.variante
        ORDER BY l.nome, total DESC
    """, param)
    relatorio_provincia = c.fetchall()
    
    conn.close()
    
    return render_template('eleitoral/relatorios.html', processos=processos, 
                           processo_id=processo_id, tipo_material_id=tipo_material_id, 
                           tipos_material=tipos_material,
                           resumo=resumo, relatorio_categoria=relatorio_categoria, 
                           relatorio_tipo=relatorio_tipo, relatorio_provincia=relatorio_provincia)

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
        
        user_perfil = session.get('perfil')
        user_local_id = session.get('eleitoral_local_id')
        
        if user_perfil != 'admin' and user_local_id:
            c.execute(f"SELECT parent_id FROM eleitoral_local_armazenamento WHERE id = {param_marker}", (destino_id,))
            dest_local = c.fetchone()
            if not dest_local or (destino_id != user_local_id and dest_local['parent_id' if is_pg else 'parent_id'] != user_local_id):
                conn.close()
                flash("Sem permissões para rececionar material neste destino.", "error")
                return redirect(url_for('eleitoral.distribuicao'))
                
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
            SUM(s.quantidade_total) as total,
            SUM(s.quantidade_bom) as bom,
            SUM(s.quantidade_mau) as mau
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_local_armazenamento l ON s.local_id = l.id
        LEFT JOIN eleitoral_local_armazenamento p ON l.parent_id = p.id OR (l.tipo = 'Provincial' AND l.id = p.id)
        WHERE s.processo_id = %s
        GROUP BY p.nome
    ''' if is_pg else '''
        SELECT 
            p.nome as provincia, 
            SUM(s.quantidade_total) as total,
            SUM(s.quantidade_bom) as bom,
            SUM(s.quantidade_mau) as mau
        FROM eleitoral_material_sobrante s
        JOIN eleitoral_local_armazenamento l ON s.local_id = l.id
        LEFT JOIN eleitoral_local_armazenamento p ON l.parent_id = p.id OR (l.tipo = 'Provincial' AND l.id = p.id)
        WHERE s.processo_id = ?
        GROUP BY p.nome
    '''
    c.execute(query, param)
    dados = c.fetchall()
    
    conn.close()
    
    resultado = {}
    for d in dados:
        if d['provincia' if is_pg else 'provincia']:
            resultado[d['provincia' if is_pg else 'provincia']] = {
                'total': d['total' if is_pg else 'total'],
                'bom': d['bom' if is_pg else 'bom'],
                'mau': d['mau' if is_pg else 'mau']
            }
            
    return jsonify(resultado)

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
        
    user_perfil = session.get('perfil')
    user_local_id = session.get('eleitoral_local_id')
    
    if user_perfil == 'admin' or not user_local_id:
        c.execute("SELECT * FROM eleitoral_local_armazenamento WHERE activo = 1 ORDER BY tipo, nome")
        locais_origem = c.fetchall()
        locais_destino = locais_origem
    else:
        if not is_pg:
            c.execute("SELECT * FROM eleitoral_local_armazenamento WHERE activo = 1 AND id = ?", (user_local_id,))
        else:
            c.execute("SELECT * FROM eleitoral_local_armazenamento WHERE activo = 1 AND id = %s", (user_local_id,))
        locais_origem = c.fetchall()
        
        if not is_pg:
            c.execute("SELECT * FROM eleitoral_local_armazenamento WHERE activo = 1 AND (tipo = 'CENTRAL' OR parent_id = ? OR id = ?)", (user_local_id, user_local_id))
        else:
            c.execute("SELECT * FROM eleitoral_local_armazenamento WHERE activo = 1 AND (tipo = 'CENTRAL' OR parent_id = %s OR id = %s)", (user_local_id, user_local_id))
        locais_destino = c.fetchall()
        
    c.execute("SELECT * FROM eleitoral_tipo_material ORDER BY nome")
    tipos_material = c.fetchall()
    
    conn.close()
    return render_template('eleitoral/nova_guia.html', processo_ativo=processo_ativo, locais_origem=locais_origem, locais_destino=locais_destino, tipos_material=tipos_material)
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

