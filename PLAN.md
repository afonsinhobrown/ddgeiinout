# PLANO DE DESENVOLVIMENTO — Gestão STAE / DDGEI

> **Documento de continuidade.** Qualquer agente/sessão que retomar este projeto DEVE ler este ficheiro primeiro. Atualizar sempre que concluir ou iniciar trabalho. Registar aqui o estado real, decisões e pendências — nunca depender de stash/commits para comunicação.

Última atualização: 2026-08-29

---

## 1. O que o sistema faz

Aplicação **Flask** de gestão do STAE (Secretariado Técnico de Administração Eleitoral) para circulação de equipamentos de TI e logística de material eleitoral.

Duas áreas:

1. **Núcleo (`gestao_stae/app.py`, ~4100 linhas)** — login com perfis (admin/tecnico/protecao), entradas/saídas de equipamentos, guias PDF (ReportLab), oficina de reparação, inventário por setor, confirmação de receção inter-setorial, cadastros, dashboard de relatórios (Chart.js) com export Excel.
2. **Módulo Eleitoral (`gestao_stae/routes_eleitoral.py`, ~1250 linhas + `templates/eleitoral/`)** — locais de armazenamento (províncias/diáspora), categorias/tipos de material, processos eleitorais, sobrantes, eventos, distribuição de material entre locais com guias de movimentação, import/export Excel.

## 2. Arquitetura de base de dados (IMPORTANTE)

**Hybrid SQLite/PostgreSQL (Neon)** — troca transparente via:
- `smart_connect` (monkey-patch de `sqlite3.connect`)
- `is_cloud_mode()`, `get_pg_connection()` em `app.py`
- Motor de sincronização dinâmica bidirecional (tabelas com `last_modified` + `origem_registo`, triggers)
- `SYNC_CONFIG` lista as tabelas sincronizadas

O módulo eleitoral usa `dual_execute()` (em `routes_eleitoral.py`) para escrever **em SQLite E PostgreSQL simultaneamente** (falha de PG não bloqueia).

## 3. Estado atual (2026-08-29)

Branch `main`. Últimos commits (do mais recente):

- `0ecaa0a` feat: permissoes de estados por usuario, hash werkzeug, fix api_movimento_estado (requisito 6; corrige NameError; UI Estado no histórico; edit_user/delete_user só-admin; debug via env var)
- `1d3f9f8` feat: controlo de permissoes na mudanca de estado (origem marca preparação/empacotamento/à espera de envio/enviado; destino marca recebido; admin qualquer)
- `d3dd16b` docs: registar estado real do trabalho
- `db31329` feat: desvincular do DDGEI — usuarios por local, origem automatica na saida, estados de saida, historico com origem/destino separados
- `da7f5ae` fix: session user_id no login, refinamento de check_permission, acentos corrompidos
- `8b410d1` feat: barcode, movimentacao entre provincias, estados intermédios, imagem->PDF
- `5ce3824` a `b597956` anteriores (hybrid SQLite/PG, eleitoral, Excel)

**Working tree limpa.** Trabalho do dia commitado em `0ecaa0a`; scripts one-off `_fix2.py`/`_fix_confirm.py` removidos (alterações já no código).

**Todos os ficheiros compilam.** App sobe com `python app.py` (ou `executar.bat`). Login testado (migração MD5→werkzeug automática em utilizadores legados), permissões por usuário e confirmação de receção testados via test client.

## 4. ESTADO DE IMPLEMENTAÇÃO (2026-08-29)

### Desvincular do DDGEI / Locais / Saída por local — FEITO E COMMITADO

**Requisitos do utilizador (2026-08-29):**
1. O sistema **não deve estar ligado ao DDGEI** — o inventário é de **todos os locais** onde o equipamento é cadastrado.
2. **Usuários associados a um lugar** — usuários atuais associados ao local DDGEI (setor_id=3).
3. **Saída de equipamento de um lugar para outro**:
   - Feita pelo **usuário desse local** (origem = local do usuário, não selecionável).
   - Quando é **admin**, o local de origem **pode ser selecionado**.
4. **Histórico de movimentos** mostra **origem e destino separados** e **estado do equipamento**.
5. **Estados de saída**: preparação, empacotamento, à espera de envio, enviado, recebido.
6. **Admin configura quais usuários realizam essas ações** — implementado (ver abaixo).

**Feito e commitado (2026-08-29, commits `db31329`, `da7f5ae`, `1d3f9f8`):**
- [x] **Usuários associados ao DDGEI** — usuários sem local são associados automaticamente ao setor DDGEI (em `check_db_integrity`).
- [x] **Origem automática na saída** — não-admin usa o local do usuário (`registrar_saida` + `MAIN_TEMPLATE`); admin pode selecionar a origem.
- [x] **Estados de saída no formulário** — campo "Estado de Saída" (preparação, empacotamento, à espera de envio, enviado, recebido) guardado em `estado_rastreio`.
- [x] **Controlo de permissões na mudança de estado** (`api_movimento_estado`) — origem marca preparação/empacotamento/à espera de envio/enviado; destino marca recebido; admin qualquer.
- [x] **`session['user_id']` corrigido no login** (`app.py:2391`) — SELECT inclui `id`; `routes_eleitoral.py` usa `session.get('user_id')`.
- [x] **`check_permission()` refinado** no módulo eleitoral — admin sempre permitido; não-admin exige `eleitoral_local_id`.
- [x] **Acentos corrigidos** em flash messages ("Saída", "Recepção").

**Estado real do código:**
- `users` tem `setor_id` (local); `inventario_local` tem `setor_id`; `movimentos` tem `setor_origem_id`, `setor_destino_id`, `local_origem`, `local_destino`, `estado_rastreio`.
- Estados intermédios: `EM_ESTOQUE`, `EM_PREPARACAO`, `EMPACOTAMENTO`, `A_ESPERA_ENVIO`, `EM_TRANSITO`, `RECEBIDO`, `EM_USO`, `AVARIADO`.
- `confirmar_recepcao_provincia` e `confirmar_recepcao` já atualizam `estado_rastreio`='RECEBIDO' na confirmação (plus `confirmado_destino`).

**Pendente (não commitado / a fazer):**
- [x] Trabalho do dia commitado (`0ecaa0a`): permissões por usuário (requisito 6), fix de bug `api_movimento_estado`, migração MD5→werkzeug, `edit_user`/`delete_user` só-admin, UI "Estado" no histórico, acentos, `debug` por env var. `_fix2.py`/`_fix_confirm.py` removidos (alterações já aplicadas).
- [x] **Admin configura quais usuários realizam ações** — implementado 2026-08-29: campo `permissoes_estado` em `users`; checkboxes no cadastro/edição de usuário; `api_movimento_estado` e `confirmar_recepcao` respeitam a lista (vazio = regra por setor). **Commitado em `0ecaa0a`.**

## 4. ESTADO DE IMPLEMENTAÇÃO (2026-08-28)

- **Sintaxe**: `app.py` compila (`ast.parse` OK). Bug corrigido: query de fecho com 2 aspas em vez de 3 na rota `api_inventario_estado` (causa do `EOF in multi-line string`).

### Implementação CONCLUÍDA (2026-08-28) — backend + UI
- **Schema** (`check_db_integrity` + `init_db` + `init_pg_db` + listas `tables`/`SYNC_CONFIG`):
  - `movimentos`: +`codigo_barras`, `documento_pdf`, `provincia_origem_id`, `provincia_destino_id`, `local_origem`, `local_destino`, `estado_rastreio`, `confirmado_destino`
  - `inventario_local`: +`codigo_barras`, `documento_pdf`, `provincia_id`, `local_uso`, `estado`, `guia_origem`
  - `users`: +`provincia_id`
  - Novas tabelas (SQLite+PG): `equipamento_rastreio`, `equipamento_estado_historico`
- **Provincias**: reutiliza `eleitoral_provincia` (já tem as 11 direções provinciais) — nenhuma nova tabela de províncias.
- **Uploads**: `UPLOAD_FOLDER` (`gestao_stae/documentos`) + `imagem_para_pdf()` (Pillow→reportlab); ficheiros de imagem convertidos a PDF na entrada.
- **Rotas novas**: `serivir_documento`, `api_buscar_barcode`, `api_movimento_estado`, `api_inventario_estado`, `movimentar_provincia`, `confirmar_recepcao_provincia`, `api_rastreio`.
- `registrar_entrada` / `inventario_add`: INSERT atualizados p/ codigo_barras, documento_pdf, provincia, local_uso, estado.
- **UI** (templates inline em `app.py`):
  - `/inventario`: scan barcode no cadastro (opcional), campos provincia/local_uso/estado/upload documento (`enctype`), cartão "Movimentar entre Províncias" (origem/destino/local/quantidade), painel "Receção Pendente entre Províncias" (confirmar no destino), colunas tabela PROVÍNCIA/ESTADO/DOC, botões "Estado" (estados intermédios) e "Rastreio" (histórico).
  - `/` (index): botão "🔍 Buscar por Código de Barras" + modal de detalhes + rastreio (usa `api_buscar_barcode` + `api_rastreio`).
- **Validado**: `app.py` compila; migração automática da BD local (colunas + tabelas criadas); `/`, `/inventario`, `/login` renderizam 200 em modo LOCAL.
- **Nuvem (Neon)**: não foi possível testar em modo nuvem no ambiente atual (ligação PostgreSQL expirou em timeout de 120s). O esquema PG já inclui as novas tabelas/colunas via `init_pg_db` + sincronização dinâmica; revalidar quando a Neon estiver acessível.

### PRÓXIMO (opcional)
- Migrar hash de senhas MD5 para algo mais forte.
- Corrigir acentuação corrompida restante nos templates (fora de flash).
- Revalidar modo Nuvem (Neon) quando a ligação estiver acessível.

## 5. PENDÊNCIAS ABERTAS (refinar)

### Prioridade Alta

- **[2026-08-29] Trabalho do dia — COMMITADO (`0ecaa0a`)**
  - Permissões por usuário (`permissoes_estado`), bug `api_movimento_estado` corrigido, migração MD5→werkzeug, `edit_user`/`delete_user` só-admin, UI "Estado" no histórico, acentos, `debug` via env var. `_fix2.py`/`_fix_confirm.py` removidos.

### Prioridade Média
- **Permissões do Módulo Eleitoral** — `check_permission()` refinado (admin sempre permitido; não-admin exige `eleitoral_local_id`); ainda pode refinar por `perfil` consoante políticas. Guardado como evolutivo.

### Prioridade Baixa / Cosmético
- **Valores legados na BD** — status `'Disponvel'`/`'Indisponvel'` (sem acento) já gravados em `inventario_local.status`. Não é corrupção de UI; migrar apenas se quiser normalizar dados históricos (fora do código).
- **Revalidar modo Nuvem (Neon)** quando a ligação estiver acessível (testes do dia correram sobre SQLite local; `init_pg_db` + sync já incluem `permissoes_estado`).

### RESOLVIDAS (2026-08-28/29)
- ~~`users.eleitoral_local_id` hardcoded `utilizador_id = 1` em `routes_eleitoral.py:255`~~ — **resolvido** em `da7f5ae`.
- ~~`check_permission()` retorna `True` sempre~~ — **refinado** em `da7f5ae`.
- ~~MD5 no hash de senhas~~ — **migrado** em 2026-08-29 para `werkzeug.security` (`generate_password_hash`/`check_password_hash`); login com hash MD5 legado continua a funcionar e é promovido a pbkdf2 na 1ª autenticação (validado por teste).
- ~~`api_movimento_estado` `NameError`~~ — **bug corrigido** em 2026-08-29 (conn inalcançável após `return`).
- ~~Admin configura quais usuários realizam ações~~ — **implementado** 2026-08-29 (`permissoes_estado`; sem valor = regra por setor). Ainda não commitado.
- ~~`debug=True`~~ — **alterado** 2026-08-29 para `os.environ.get('FLASK_DEBUG') == '1'`.
- ~~Acentos corrompidos restantes~~ — **corrigidos** os visíveis na UI/flash (2026-08-29); só ficam valores legados na BD.
- ~~Anexo de imagem do documento → PDF~~ — **feito** em `8b410d1`.
- ~~Estados intermédios de equipamento~~ — **feito** em `8b410d1` + `1d3f9f8`.
- ~~Movimentação entre Províncias + rastreio + locais~~ — **feito** em `8b410d1`.
- ~~Leitura de BARCODE~~ — **feito** em `8b410d1`/`8d83bfa`.
- ~~Desvincular do DDGEI~~ (usuários por local, origem automática, estados de saída, histórico) — **feito** em `db31329`.
- ~~Confirmação de receção inter-setorial~~ — controlo de permissão (destino/admin) + UPDATE `estado_rastreio`='RECEBIDO' aplicados; **validado** por teste 2026-08-29.

## 6. Itens de operação / hygiene

- **`stash@{0}`** — WIP antigo (2026-05-14, "Sistema Completo Gestão STAE - Versão Premium"; base `2e80f94`, UI/template DESATUALIZADA). **Supersedido** — pode descartar com `git stash drop stash@{0}`. Não mexer noutra ocasião como se fosse trabalho atual.
- **Scripts de patch (patch1–patch18, scratch/)** — ferramentas one-off de desenvolvimento/modificação. Já aplicadas ao `app.py`/`routes_eleitoral.py` commitados. NÃO re-executar à toa; são referência histórica.
- Senhas padrão: admin/admin123, tecnico/tecnico123, protecao/protecao123. Trocar em produção. Desde 2026-08-29 as senhas usam `werkzeug.security` (pbkdf2); as antigas MD5 ainda aceites e migradas no 1º login.

## 7. Como executar / testar

```
cd gestao_stae
python app.py        # ou clicar em executar.bat
pip install flask reportlab openpyxl psycopg2-binary   # conforme requirements
```
- Verificar sintaxe após alterações: `python -c "import ast; ast.parse(open('app.py').read())"` (idem `routes_eleitoral.py`).
- Testes/criados: `test_sync.py`, `test_cloud_mode.py`, `test_init.py` em `gestao_stae/`.

## 8. Convenções do projeto

- Sem comentários desnecessários no código (mantém-se apenas os TODO/documentação).
- Português de Moçambique na nomenclatura/UI.
- Ficheiros escritos em UTF-8 — cuidado para não corromper acentos ao patchear.
