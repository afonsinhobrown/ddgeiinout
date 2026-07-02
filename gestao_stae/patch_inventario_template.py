with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Locate index start of INVENTARIO_TEMPLATE = '''<!DOCTYPE html>
idx_start = content.find("INVENTARIO_TEMPLATE = '''<!DOCTYPE html>")
# Find closing point: </body></html>'''
idx_end = content.find("</body></html>'''", idx_start) + len("</body></html>'''")

target_text = content[idx_start:idx_end]

replacement_text = """INVENTARIO_TEMPLATE = '''<!DOCTYPE html><html lang="pt"><head>''' + COMMON_HEAD + '''<title>Inventário Local - DDGEI</title>
<style>
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
    .stat-card { background: white; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .stat-number { font-size: 2rem; font-weight: bold; color: var(--primary); margin-top: 0.5rem; }
    .card table td { border-bottom: 1px solid #f1f5f9; padding: 0.75rem 0.5rem; }
    
    .pagination-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 1.5rem;
        padding-top: 1rem;
        border-top: 1px solid var(--border);
    }
    .pagination-btn {
        background: white;
        border: 1px solid var(--border);
        padding: 0.4rem 0.8rem;
        border-radius: 0.375rem;
        cursor: pointer;
        font-weight: 600;
        transition: all 0.2s;
    }
    .pagination-btn:hover:not(:disabled) {
        background: #f8fafc;
        border-color: #cbd5e1;
    }
    .pagination-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
</style>
</head>
<body>
    <div class="nav">
        <strong>STAE GESTÃO - INVENTÁRIO LOCAL (DDGEI)</strong>
        <div>
            <button id="syncBtn" onclick="syncCloud()" class="btn btn-outline" style="background:#10b981; color:white; border:none; margin-right:1rem; padding: 0.4rem 0.8rem; font-weight:bold; cursor:pointer; transition: all 0.3s;">🔄 Sincronizar Nuvem</button>
            <a href="/" class="btn btn-outline" style="background:white; color:#0f172a; margin-right:1.5rem; padding: 0.4rem 0.8rem;">⬅️ Voltar ao Início</a>
            <span>👤 {{session.username}}</span>
        </div>
    </div>
    <div class="container">
        {% if msg %}<div style="background:#dcfce3; color:#166534; padding:1rem; border-radius:0.5rem; margin-bottom:1rem;">{{msg}}</div>{% endif %}
        
        <div class="stats-grid">
            <div class="stat-card">
                <div style="color: #64748b; font-weight: 600;">Total de Itens</div>
                <div class="stat-number">{{ stats.total }}</div>
            </div>
            <div class="stat-card">
                <div style="color: #10b981; font-weight: 600;">Disponíveis</div>
                <div class="stat-number" style="color: #10b981;">{{ stats.disponiveis }}</div>
            </div>
            <div class="stat-card">
                <div style="color: #3b82f6; font-weight: 600;">Em Uso</div>
                <div class="stat-number" style="color: #3b82f6;">{{ stats.em_uso }}</div>
            </div>
            <div class="stat-card">
                <div style="color: #ef4444; font-weight: 600;">Avariados</div>
                <div class="stat-number" style="color: #ef4444;">{{ stats.danificados }}</div>
            </div>
        </div>

        <!-- Pending Confirmation Panel -->
        {% if pending_items %}
        <div class="card" style="margin-bottom: 2rem; border: 2px solid #fed7aa; background: #fffbeb;">
            <h3 style="color: #ea580c; display: flex; align-items: center; gap: 0.5rem;">📥 Equipamentos Pendentes de Receção</h3>
            <div style="overflow-x: auto; margin-top: 1rem;">
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #ffedd5; text-align: left; color: #ea580c; font-size: 0.8rem">
                            <th style="padding: 0.75rem">EQUIPAMENTO</th>
                            <th style="padding: 0.75rem">MARCA</th>
                            <th style="padding: 0.75rem">S/N</th>
                            <th style="padding: 0.75rem">QUANTIDADE</th>
                            <th style="padding: 0.75rem">GUIA DE ORIGEM</th>
                            <th style="padding: 0.75rem">SETOR DE ORIGEM</th>
                            <th style="padding: 0.75rem; text-align: right;">AÇÕES</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for p_item in pending_items %}
                        <tr style="border-bottom: 1px solid #fed7aa">
                            <td style="padding: 0.75rem; font-weight: 600;">{{ p_item.equipamento }}</td>
                            <td style="padding: 0.75rem">{{ p_item.marca }}</td>
                            <td style="padding: 0.75rem; font-family: monospace;">{{ p_item.numero_serie }}</td>
                            <td style="padding: 0.75rem; font-weight: bold; text-align: center;">{{ p_item.quantidade }}</td>
                            <td style="padding: 0.75rem; font-weight: bold; color: #475569;">{{ p_item.guia_origem or '-' }}</td>
                            <td style="padding: 0.75rem; color: #64748b;">{{ p_item.setor_nome or 'Desconhecido' }}</td>
                            <td style="padding: 0.75rem; text-align: right;">
                                <form method="POST" action="/inventario/confirmar_rececao/{{ p_item.id }}" style="display:inline;">
                                    <button class="btn btn-green" style="margin-top:0; padding: 0.3rem 0.8rem; font-weight: bold; font-size: 0.8rem;">Confirmar Receção</button>
                                </form>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}

        <div style="display: grid; grid-template-columns: 350px 1fr; gap: 1.5rem; align-items: start;">
            <div class="card">
                <h3>Cadastrar Equipamento</h3>
                <form method="POST" action="/inventario/add" style="margin-top: 1rem; display: flex; flex-direction: column; gap: 1rem;">
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Tipo de Equipamento</label>
                        <select name="equipamento" required style="margin-top: 0.25rem;">
                            <option value="">-- Selecione --</option>
                            {% for t in tipos %}<option value="{{t.nome}}">{{t.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Marca</label>
                        <select name="marca" required style="margin-top: 0.25rem;">
                            <option value="">-- Selecione --</option>
                            {% for m in marcas %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Número de Série (S/N)</label>
                        <input name="numero_serie" placeholder="Ex: SN-12345 ou N/A" required style="margin-top: 0.25rem;">
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Quantidade</label>
                        <input name="quantidade" type="number" min="1" value="1" required style="margin-top: 0.25rem;">
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Setor Pertencente</label>
                        <select name="setor_id" required style="margin-top: 0.25rem;">
                            <option value="">-- Selecione o Setor --</option>
                            {% for s in setores %}<option value="{{s.id}}" {% if session.setor_id == s.id %}selected{% endif %}>{{s.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Status Inicial</label>
                        <select name="status" required style="margin-top: 0.25rem;">
                            <option value="Disponível">Disponível</option>
                            <option value="Em uso">Em uso</option>
                            <option value="Danificado">Danificado</option>
                            <option value="Avariado">Avariado</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Observações</label>
                        <textarea name="observacoes" rows="3" placeholder="Localização, detalhes físicos..." style="margin-top: 0.25rem;"></textarea>
                    </div>
                    <button class="btn btn-blue" style="margin-top:0.5rem; width:100%">Salvar no Inventário</button>
                </form>
            </div>

            <div class="card">
                <h3>Equipamentos em Stock</h3>
                
                <!-- Bulk Actions -->
                <div style="display:flex; justify-content: space-between; align-items:center; margin-top: 1rem; margin-bottom: 1rem; gap: 0.5rem; flex-wrap: wrap;">
                    <div style="display:flex; gap: 0.5rem;">
                        <button onclick="abrirTransferenciaMultiplos()" class="btn btn-blue" style="margin-top:0; font-size: 0.85rem;">📁 Transferir Selecionados</button>
                        <button onclick="apagarSelecionados()" class="btn btn-danger" style="margin-top:0; font-size: 0.85rem;">🗑️ Apagar Selecionados</button>
                    </div>
                    {% if session.perfil == 'admin' %}
                    <form method="POST" action="/inventario/delete_all" onsubmit="return confirm('ATENÇÃO: Isto irá apagar TODOS os equipamentos do inventário permanentemente. Continuar?');">
                        <button class="btn btn-danger" style="margin-top:0; background:#dc2626; font-size: 0.85rem;">⚠️ Apagar Todo o Inventário</button>
                    </form>
                    {% endif %}
                </div>

                <input type="text" id="invSearchInput" onkeyup="searchInvTable()" placeholder="Pesquisar por equipamento, marca ou S/N..." style="width:100%; padding:0.8rem; border:1px solid #cbd5e1; border-radius:4px; margin-bottom:1rem">
                
                <table id="invTable" style="width:100%; border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f1f5f9; text-align:left; color:#64748b; font-size:0.8rem">
                            <th style="padding:0.75rem; width: 30px;"><input type="checkbox" id="selectAllCheckbox" onclick="toggleSelectAll(this)"></th>
                            <th style="padding:0.75rem">EQUIPAMENTO</th>
                            <th style="padding:0.75rem">MARCA</th>
                            <th style="padding:0.75rem">S/N</th>
                            <th style="padding:0.75rem">QUANTIDADE</th>
                            <th style="padding:0.75rem">SETOR</th>
                            <th style="padding:0.75rem">STATUS</th>
                            <th style="padding:0.75rem; text-align: right;">ACÇÕES</th>
                        </tr>
                    </thead>
                    <tbody id="invTableBody">
                        <!-- Filled by JS -->
                    </tbody>
                </table>

                <div class="pagination-nav">
                    <button id="btnPrevPage" onclick="changePage(-1)" class="pagination-btn">⬅️ Anterior</button>
                    <span id="pageIndicator" style="font-weight: 600; color: #475569; font-size: 0.9rem;">Página 1 de 1</span>
                    <button id="btnNextPage" onclick="changePage(1)" class="pagination-btn">Próximo ➡️</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Modal de Edição de Inventário -->
    <div id="editInvModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:450px; max-width:90%;">
            <h3>Editar Item do Inventário</h3>
            <form id="editInvForm" method="POST" action="" style="margin-top: 1.5rem; display: flex; flex-direction: column; gap: 1rem;">
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Tipo de Equipamento</label>
                    <select name="equipamento" id="ei_equipamento" required>
                        {% for t in tipos %}<option value="{{t.nome}}">{{t.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Marca</label>
                    <select name="marca" id="ei_marca" required>
                        {% for m in marcas %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Número de Série (S/N)</label>
                    <input name="numero_serie" id="ei_numero_serie" required>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Quantidade em Stock</label>
                    <input name="quantidade" id="ei_quantidade" type="number" min="0" required>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Setor Pertencente</label>
                    <select name="setor_id" id="ei_setor_id" required>
                        {% for s in setores %}<option value="{{s.id}}">{{s.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Status</label>
                    <select name="status" id="ei_status" required>
                        <option value="Disponível">Disponível</option>
                        <option value="Em uso">Em uso</option>
                        <option value="Danificado">Danificado</option>
                        <option value="Avariado">Avariado</option>
                    </select>
                </div>
                <div>
                    <label style="font-weight: 600; font-size: 0.85rem; color: #475569;">Observações</label>
                    <textarea name="observacoes" id="ei_observacoes" rows="3"></textarea>
                </div>
                <div style="display:flex; gap:1rem; margin-top:0.5rem;">
                    <button type="button" class="btn btn-outline" style="flex:1" onclick="document.getElementById('editInvModal').style.display='none'">Cancelar</button>
                    <button type="submit" class="btn btn-blue" style="flex:1">Salvar Alterações</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal de Saída Rápida a partir do Inventário -->
    <div id="saidaRapidaInvModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1010; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:750px; max-width:95%; max-height:90vh; overflow-y:auto;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem;">
                <h2>📤 Registrar Saída (Item do Inventário Local)</h2>
                <button type="button" class="btn btn-outline" onclick="fecharSaidaRapidaInv()" style="padding:0.4rem 0.8rem;">Fechar</button>
            </div>
            <form id="saidaRapidaInvForm" method="POST" action="">
                <input type="hidden" name="inventario_id" id="sri_inventario_id">
                <div class="form-grid">
                    <div>
                        <label>Origem (Leitura Apenas)</label>
                        <input type="text" value="DEPARTAMENTO DE DELIMITAÇÃO GEOGRÁFICA, ESTATÍSTICA E INFORMÁTICA" readonly style="background:#f1f5f9; color:#475569;">
                    </div>
                    <div>
                        <label>Destino</label>
                        <select name="destino" required>
                            <option value="">-- Selecione o Destino --</option>
                            <optgroup label="Setores Internos">
                                {% for s in setores %}<option value="Interno - {{s.nome}}">{{s.nome}}</option>{% endfor %}
                            </optgroup>
                            <optgroup label="Instituições Externas">
                                {% for i in instituicoes %}<option value="Externo - {{i.nome}}">{{i.nome}}</option>{% endfor %}
                            </optgroup>
                        </select>
                    </div>
                    <div>
                        <label>Equipamento</label>
                        <input type="text" name="equipamento" id="sri_equipamento" readonly style="background:#f1f5f9; color:#475569;">
                    </div>
                    <div>
                        <label>Marca</label>
                        <input type="text" name="marca" id="sri_marca" readonly style="background:#f1f5f9; color:#475569;">
                    </div>
                    <div>
                        <label>Número de Série (S/N)</label>
                        <input type="text" name="numero_serie" id="sri_numero_serie" readonly style="background:#f1f5f9; color:#475569;">
                    </div>
                    <div>
                        <label>Quantidade Disponível</label>
                        <input type="text" id="sri_qtd_disponivel" readonly style="background:#f1f5f9; font-weight:bold; color:#475569;">
                    </div>
                    <div>
                        <label>Quantidade a Retirar</label>
                        <input type="number" name="quantidade" id="sri_quantidade" min="1" value="1" required>
                    </div>
                    <div>
                        <label>Motivo</label>
                        <select name="motivo" required>
                            <option value="">-- Selecione --</option>
                            {% for m in motivos %}<option value="{{m.nome}}">{{m.nome}}</option>{% endfor %}
                        </select>
                    </div>
                    <div style="grid-column: span 2; border-top: 1px solid var(--border); margin-top: 1rem; padding-top: 1rem;">
                        <h4 style="margin-bottom:0.5rem; color:#1e293b;">Responsáveis pela Saída</h4>
                    </div>
                    <div>
                        <label style="font-size:0.9rem; color:#64748b">Entregue por (Funcionário)</label>
                        <select name="entregue_por" id="sri_entregue" required></select>
                    </div>
                    <div>
                        <label style="font-size:0.9rem; color:#64748b">Recebido por (Funcionário)</label>
                        <select name="recebido_por" id="sri_recebido" required></select>
                    </div>
                    <div style="grid-column: span 2;">
                        <label style="font-size:0.9rem; color:#64748b">Agente de Protecção</label>
                        <select name="agente_protecao" id="sri_protecao"></select>
                    </div>
                </div>
                <button type="submit" class="btn btn-blue" style="margin-top:2rem; width:100%; padding:0.8rem; font-size:1.05rem; font-weight:bold;">CONFIRMAR SAÍDA E GERAR GUIA</button>
            </form>
        </div>
    </div>

    <!-- Modal de Transferência de Múltiplos Itens -->
    <div id="transferModal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000; display:none; justify-content:center; align-items:center;">
        <div class="card" style="width:500px; max-width:90%;">
            <h3>📁 Transferir Equipamentos para Setor</h3>
            <form id="transferForm" onsubmit="submeterTransferencia(event)" style="margin-top:1.5rem; display:flex; flex-direction:column; gap:1rem;">
                <div>
                    <label style="font-weight:600; font-size:0.85rem; color:#475569;">Setor de Destino</label>
                    <select id="trans_setor_destino_id" required>
                        <option value="">-- Selecione o Setor --</option>
                        {% for s in setores %}<option value="{{s.id}}">{{s.nome}}</option>{% endfor %}
                    </select>
                </div>
                <div id="trans_items_container" style="max-height: 200px; overflow-y: auto; border: 1px solid var(--border); padding: 0.5rem; border-radius: 4px; display:flex; flex-direction:column; gap:0.5rem;">
                    <!-- Quantidades inputs dynamically loaded -->
                </div>
                <div style="display:flex; gap:1rem;">
                    <div>
                        <label style="font-weight:600; font-size:0.85rem; color:#475569;">Entregue por (Resp.)</label>
                        <input type="text" id="trans_entregue_por" required style="padding:0.4rem;">
                    </div>
                    <div>
                        <label style="font-weight:600; font-size:0.85rem; color:#475569;">Recebido por (Resp.)</label>
                        <input type="text" id="trans_recebido_por" required style="padding:0.4rem;">
                    </div>
                </div>
                <div>
                    <label style="font-weight:600; font-size:0.85rem; color:#475569;">Motivo da Transferência</label>
                    <input type="text" id="trans_motivo" required placeholder="Ex: Necessidade de serviço" style="padding:0.4rem;">
                </div>
                <div style="display:flex; gap:1rem; margin-top:0.5rem;">
                    <button type="button" class="btn btn-outline" style="flex:1" onclick="fecharTransferModal()">Cancelar</button>
                    <button type="submit" class="btn btn-blue" style="flex:1">Confirmar Transferência</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        const allItems = {{ items|tojson }};
        let filteredItems = [...allItems];
        let currentPage = 1;
        const pageSize = 10;
        const selectedIds = new Set();

        function searchInvTable() {
            const query = document.getElementById("invSearchInput").value.toUpperCase();
            filteredItems = allItems.filter(item => {
                const text = `${item.equipamento} ${item.marca} ${item.numero_serie} ${item.status} ${item.setor_nome || ''}`.toUpperCase();
                return text.indexOf(query) > -1;
            });
            currentPage = 1;
            renderTable();
        }

        function renderTable() {
            const tbody = document.getElementById("invTableBody");
            tbody.innerHTML = "";
            
            const startIdx = (currentPage - 1) * pageSize;
            const endIdx = startIdx + pageSize;
            const pageItems = filteredItems.slice(startIdx, endIdx);
            
            if (pageItems.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8" style="padding:1.5rem; text-align:center; color:#64748b;">Nenhum equipamento correspondente encontrado.</td></tr>`;
            } else {
                pageItems.forEach(item => {
                    let statusSpan = '';
                    if (item.status === 'Disponível') {
                        statusSpan = `<span style="background:#dcfce3; color:#166534; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">${item.status}</span>`;
                    } else if (item.status === 'Em uso') {
                        statusSpan = `<span style="background:#dbeafe; color:#1e40af; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">${item.status}</span>`;
                    } else {
                        statusSpan = `<span style="background:#fee2e2; color:#991b1b; padding:0.25rem 0.5rem; border-radius:0.25rem; font-size:0.8rem; font-weight:600;">${item.status}</span>`;
                    }
                    
                    const isChecked = selectedIds.has(item.id) ? 'checked' : '';
                    const actionSaida = (item.quantidade > 0 && item.status === 'Disponível') 
                        ? `<button onclick="abrirSaidaRapidaInventario(${item.id})" class="btn btn-green" style="padding:0.25rem 0.5rem; font-size:0.75rem; margin-top:0;">Saída</button>` 
                        : '';
                        
                    const tr = document.createElement("tr");
                    tr.style.borderBottom = "1px solid var(--border)";
                    tr.innerHTML = `
                        <td style="padding:0.75rem;"><input type="checkbox" class="row-checkbox" value="${item.id}" data-qty="${item.quantidade}" ${isChecked} onclick="toggleSelectRow(this, ${item.id})"></td>
                        <td style="padding:0.75rem; font-weight: 600;">${item.equipamento}</td>
                        <td style="padding:0.75rem">${item.marca}</td>
                        <td style="padding:0.75rem; font-family: monospace;">${item.numero_serie}</td>
                        <td style="padding:0.75rem; text-align: center; font-weight: bold;">${item.quantidade}</td>
                        <td style="padding:0.75rem; color:#475569;">${item.setor_nome || '-'}</td>
                        <td style="padding:0.75rem">${statusSpan}</td>
                        <td style="padding:0.75rem; text-align: right; display:flex; gap:0.25rem; justify-content: flex-end; align-items: center;">
                            ${actionSaida}
                            <button onclick="editarItemInventario(${item.id})" class="btn btn-outline" style="padding:0.25rem 0.5rem; font-size:0.75rem; margin-top:0;">Editar</button>
                            <form method="POST" action="/inventario/delete/${item.id}" style="display:inline;" onsubmit="return confirm('Deseja remover este item do inventário?');">
                                <button class="btn btn-danger" style="padding:0.25rem 0.5rem; font-size:0.75rem; margin-top:0;">Remover</button>
                            </form>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
            
            // Update indicator and buttons state
            const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
            document.getElementById("pageIndicator").innerText = `Página ${currentPage} de ${totalPages}`;
            document.getElementById("btnPrevPage").disabled = (currentPage === 1);
            document.getElementById("btnNextPage").disabled = (currentPage === totalPages);
        }

        function changePage(direction) {
            currentPage += direction;
            renderTable();
        }

        function toggleSelectAll(masterCheckbox) {
            const boxes = document.querySelectorAll(".row-checkbox");
            boxes.forEach(cb => {
                cb.checked = masterCheckbox.checked;
                const id = parseInt(cb.value);
                if (masterCheckbox.checked) {
                    selectedIds.add(id);
                } else {
                    selectedIds.delete(id);
                }
            });
        }

        function toggleSelectRow(checkbox, id) {
            if (checkbox.checked) {
                selectedIds.add(id);
            } else {
                selectedIds.delete(id);
            }
        }

        function apagarSelecionados() {
            if (selectedIds.size === 0) {
                alert("Nenhum item selecionado.");
                return;
            }
            if (!confirm(`Deseja realmente remover os ${selectedIds.size} itens selecionados?`)) return;
            
            fetch("/inventario/delete_multiple", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ ids: Array.from(selectedIds) })
            })
            .then(r => r.json())
            .then(res => {
                if (res.success) {
                    window.location.reload();
                } else {
                    alert("Erro ao remover: " + res.error);
                }
            });
        }

        function abrirTransferenciaMultiplos() {
            if (selectedIds.size === 0) {
                alert("Selecione pelo menos um equipamento.");
                return;
            }
            
            const container = document.getElementById("trans_items_container");
            container.innerHTML = "";
            
            selectedIds.forEach(id => {
                const item = allItems.find(x => x.id === id);
                if (item) {
                    const rowDiv = document.createElement("div");
                    rowDiv.style.display = "flex";
                    rowDiv.style.justifyContent = "space-between";
                    rowDiv.style.alignItems = "center";
                    rowDiv.style.padding = "0.25rem 0";
                    rowDiv.innerHTML = `
                        <span style="font-size:0.85rem; font-weight:600;">${item.equipamento} (${item.marca} - SN: ${item.numero_serie})</span>
                        <div style="display:flex; align-items:center; gap:0.5rem;">
                            <span style="font-size:0.75rem; color:#64748b;">(Qtd disp: ${item.quantidade})</span>
                            <input type="number" class="trans-qty" data-id="${item.id}" min="1" max="${item.quantidade}" value="1" style="width:60px; padding:0.2rem;">
                        </div>
                    `;
                    container.appendChild(rowDiv);
                }
            });
            
            document.getElementById("transferModal").style.display = "flex";
        }

        function fecharTransferModal() {
            document.getElementById("transferModal").style.display = "none";
        }

        function submeterTransferencia(e) {
            e.preventDefault();
            const sectorDestId = document.getElementById("trans_setor_destino_id").value;
            const entregue = document.getElementById("trans_entregue_por").value;
            const recebido = document.getElementById("trans_recebido_por").value;
            const motivo = document.getElementById("trans_motivo").value;
            
            const qtyInputs = document.querySelectorAll(".trans-qty");
            const quantities = {};
            for (let input of qtyInputs) {
                const id = input.getAttribute("data-id");
                const qtyVal = parseInt(input.value);
                const maxVal = parseInt(input.getAttribute("max"));
                if (qtyVal > maxVal) {
                    alert("A quantidade para transferir não pode exceder a quantidade disponível.");
                    return;
                }
                quantities[id] = qtyVal;
            }
            
            fetch("/inventario/movimentar_multiplos", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ids: Array.from(selectedIds),
                    quantities: quantities,
                    setor_destino_id: sectorDestId,
                    entregue_por: entregue,
                    recebido_por: recebido,
                    motivo: motivo
                })
            })
            .then(r => r.json())
            .then(res => {
                if (res.success) {
                    window.location.reload();
                } else {
                    alert("Erro na transferência: " + res.error);
                }
            });
        }

        function editarItemInventario(id) {
            const item = allItems.find(x => x.id === id);
            if (!item) return;
            document.getElementById('editInvForm').action = `/inventario/edit/${item.id}`;
            document.getElementById('ei_equipamento').value = item.equipamento;
            document.getElementById('ei_marca').value = item.marca;
            document.getElementById('ei_numero_serie').value = item.numero_serie;
            document.getElementById('ei_quantidade').value = item.quantidade;
            document.getElementById('ei_setor_id').value = item.setor_id || '';
            document.getElementById('ei_status').value = item.status;
            document.getElementById('ei_observacoes').value = item.observacoes || '';
            document.getElementById('editInvModal').style.display = 'flex';
        }

        function abrirSaidaRapidaInventario(id) {
            fetch(`/api/inventario_info/${id}`)
                .then(r => r.json())
                .then(item => {
                    document.getElementById('saidaRapidaInvForm').action = `/registrar_saida_inventario/${item.id}`;
                    document.getElementById('sri_inventario_id').value = item.id;
                    document.getElementById('sri_equipamento').value = item.equipamento;
                    document.getElementById('sri_marca').value = item.marca;
                    document.getElementById('sri_numero_serie').value = item.numero_serie;
                    document.getElementById('sri_qtd_disponivel').value = item.quantidade;
                    document.getElementById('sri_quantidade').max = item.quantidade;
                    document.getElementById('sri_quantidade').value = 1;

                    const selE = document.getElementById('sri_entregue');
                    const selR = document.getElementById('sri_recebido');
                    const selP = document.getElementById('sri_protecao');
                    
                    selE.innerHTML = '<option value="">-- Selecione quem entregou --</option>';
                    selR.innerHTML = '<option value="">-- Selecione quem recebeu --</option>';
                    selP.innerHTML = '<option value="">-- Opcional --</option>';
                    
                    fetch('/api/funcionarios').then(r=>r.json()).then(data=>{
                        data.forEach(f => {
                            const opt = `<option value="${f.id}">${f.nome} (${f.setor})</option>`;
                            selE.innerHTML += opt;
                            selR.innerHTML += opt;
                        });
                    });
                    
                    fetch('/api/usuarios_protecao').then(r=>r.json()).then(data=>{
                        data.forEach(u => {
                            const opt = `<option value="${u.nome}">${u.nome} (${u.info})</option>`;
                            selP.innerHTML += opt;
                        });
                    });

                    document.getElementById('saidaRapidaInvModal').style.display = 'flex';
                });
        }

        function fecharSaidaRapidaInv() {
            document.getElementById('saidaRapidaInvModal').style.display = 'none';
        }

        // Initial table load
        renderTable();
    </script>
</body></html>'''"""

content = content.replace(target_text, replacement_text)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("[+] INVENTARIO_TEMPLATE successfully patched.")
