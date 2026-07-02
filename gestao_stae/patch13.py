import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Hide buttons in MAIN_TEMPLATE
buttons_html = """            <a href="/inventario" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a"> 📦 Inventário DDGEI</a>
            <a href="/relatorios" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a"> 📊 Dashboard de Relatórios</a>
            <a href="/cadastros" class="btn btn-outline" style="background:#e2e8f0; color:#0f172a"> ⚙️ Cadastros</a>"""
            
# Since encoding might have stripped accents in previous outputs, let's just do a regex replace
content = re.sub(
    r'<a href="/relatorios"[^>]*>.*?</a>\s*<a href="/cadastros"[^>]*>.*?</a>',
    r"{% if session.perfil == 'admin' %}\n            <a href=\"/relatorios\" class=\"btn btn-outline\" style=\"background:#e2e8f0; color:#0f172a\"> 📊 Dashboard de Relatórios</a>\n            <a href=\"/cadastros\" class=\"btn btn-outline\" style=\"background:#e2e8f0; color:#0f172a\"> ⚙️ Cadastros</a>\n            {% endif %}",
    content
)

# 2. Add before_request for solid backend protection
if "def check_permissions():" not in content:
    before_req_code = """
@app.before_request
def check_permissions():
    if request.endpoint in ('login', 'static', 'api_sync') or request.endpoint is None:
        return
        
    if 'username' not in session:
        return redirect(url_for('login'))
        
    admin_only_endpoints = [
        'cadastros', 'add_motivo', 'add_fornecedor', 'add_instituicao', 
        'add_marca', 'add_tipo', 'add_setor', 'add_funcionario', 'add_user',
        'relatorios', 'relatorios_export', 'eliminar_movimento'
    ]
    
    if request.endpoint in admin_only_endpoints:
        if session.get('perfil') != 'admin':
            return "Erro: Acesso negado. Apenas administradores t&ecirc;m permiss&atilde;o para aceder a esta p&aacute;gina.", 403

"""
    # Insert it right before @app.route('/')
    content = content.replace("@app.route('/')\ndef index():", before_req_code + "\n@app.route('/')\ndef index():")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Patch 13 applied successfully.")
