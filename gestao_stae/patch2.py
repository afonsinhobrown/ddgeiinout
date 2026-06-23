import re

content = open('app.py', encoding='utf-8').read()

# Replace the Entrada form
entrada_form_old = '''<div class="form-grid">
                    <div><label>Equipamento (Tipo)</label><input name="equipamento" required placeholder="Ex: Laptop"></div>
                    <div><label>S/N / Nº Série</label><input name="numero_serie" required></div>
                    <div><label>Marca</label><input name="marca" placeholder="HP, Dell..."></div>
                    <div><label>Origem</label><input name="origem" required></div>
                    <div><label>Motivo</label><input name="motivo" list="motivos_list" placeholder="Ex: Alocação"></div>'''

entrada_form_new = '''<div class="form-grid">
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
                        <select name="origem" required onchange="if(this.value=='Outro'){this.nextElementSibling.style.display='block';this.nextElementSibling.required=true;}else{this.nextElementSibling.style.display='none';this.nextElementSibling.required=false;}">
                            <option value="">-- Selecione --</option>
                            {% for s in setores %}<option value="Interno - {{s.nome}}">{{s.nome}}</option>{% endfor %}
                            <option value="Outro">Outro (Externa)</option>
                        </select>
                        <input type="text" name="origem_outro" placeholder="Especifique a origem" style="display:none; margin-top:0.5rem">
                    </div>
                    <div><label>Fornecedor</label><input name="fornecedor" placeholder="Ex: N/A"></div>
                    <div><label>Quantidade</label><input type="number" name="quantidade" min="1" placeholder="Ex: 1"></div>
                    <div><label>Motivo</label><input name="motivo" list="motivos_list" placeholder="Ex: Alocação"></div>'''

content = content.replace(entrada_form_old, entrada_form_new)

# Replace the Saida form
saida_form_old = '''<div class="form-grid">
                    <div><label>Equipamento (Tipo)</label><input name="equipamento" required placeholder="Ex: Impressora"></div>
                    <div><label>S/N / Nº Série</label><input name="numero_serie" required></div>
                    <div><label>Marca</label><input name="marca"></div>
                    <div><label>Destino</label><input name="destino" required></div>
                    <div><label>Motivo</label><input name="motivo" list="motivos_list" required placeholder="Reparado, Transferência..."></div>'''

saida_form_new = '''<div class="form-grid">
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
                        <select name="destino" required onchange="if(this.value=='Outro'){this.nextElementSibling.style.display='block';this.nextElementSibling.required=true;}else{this.nextElementSibling.style.display='none';this.nextElementSibling.required=false;}">
                            <option value="">-- Selecione --</option>
                            {% for s in setores %}<option value="Interno - {{s.nome}}">{{s.nome}}</option>{% endfor %}
                            <option value="Outro">Outro (Externa)</option>
                        </select>
                        <input type="text" name="destino_outro" placeholder="Especifique o destino" style="display:none; margin-top:0.5rem">
                    </div>
                    <div><label>Fornecedor</label><input name="fornecedor" placeholder="Ex: N/A"></div>
                    <div><label>Quantidade</label><input type="number" name="quantidade" min="1" placeholder="Ex: 1"></div>
                    <div><label>Motivo</label><input name="motivo" list="motivos_list" required placeholder="Reparado, Transferência..."></div>'''

content = content.replace(saida_form_old, saida_form_new)

# Add search bar
search_bar = '''<h3>Histórico Recente</h3>
            <input type="text" id="searchInput" onkeyup="searchTable()" placeholder="Pesquisar guia, equipamento, origem..." style="width:100%; padding:0.8rem; margin-top:1rem; border:1px solid #cbd5e1; border-radius:4px; margin-bottom:1rem">'''
content = content.replace('<h3>Histórico Recente</h3>', search_bar)

# Add search JS script to the end of MAIN_TEMPLATE
search_script = '''
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
                        // also hide details row
                        if(tr[i+1]) tr[i+1].className = "hidden";
                    }
                }
            }
        }
    </script>
</body></html>'''
content = content.replace('</body></html>', search_script)
content = content.replace('<table style="width:100%', '<table id="mainTable" style="width:100%')

open('app.py', 'w', encoding='utf-8').write(content)
print("Updated MAIN_TEMPLATE successfully")
