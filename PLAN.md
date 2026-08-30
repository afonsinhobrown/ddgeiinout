# PLANO DE DESENVOLVIMENTO — Gestão STAE / DDGEI

> **Documento de continuidade.** Qualquer agente/sessão que retomar este projeto DEVE ler este ficheiro primeiro. Atualizar sempre que concluir ou iniciar trabalho. Registar aqui o estado real, decisões e pendências — nunca depender de stash/commits para comunicação.

Última atualização: 2026-08-30

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

## 3. Estado atual (2026-08-30)

Branch `main`. Últimos commits (do mais recente): `303e812` (corrige nome UGEA no organograma), `bb5b2b3` (inventário filtrado por local + anulação de movimentação + organograma), `eb54219` (normalizar status + perfil), `8fbc604` (docs), `0ecaa0a` (permissões por usuário, hash werkzeug, fix api_movimento_estado).

**Working tree: só `PLAN.md` modificado (este registo), a commitar.**

**Sincronização RH concluída (2026-08-30)** — ver §4 e §5.

**PORTALSTAE — IA Eleitoral (2026-08-30, commits `3ffeb52`→`222a2e7`, repo PORTALSTAE):**
- **Fix produção:** `templates/recursoshumanos/relatorios/licencas.html` criado (estava em falta → `TemplateDoesNotExist` em `/rh/relatorios/licencas/`; pusheado no `3ffeb52` — **produção ainda precisa de deploy manual no Render**).
- **RH inicia licença/avaliação/mensagem por funcionário** (`3ffeb52`): ação "Solicitar Licença" (RH escolhe funcionário), "Iniciar Avaliação" (`avaliacao pendente` sempre preenchida pelo chefe/diretor), "Enviar Mensagem Direta"; tipo **Dispensa** + migração `0004`; era o commit `222a2e7`? — não, `222a2e7` é a IA).
- **IA Eleitoral em 2 passos** (`222a2e7`): 1º o prompt devolve **temas** (recursos humanos/equipamentos/círculos/material/etc.) sem varrer a BD; o utilizador escolhe um e só então a pesquisa profunda corre **só nesse tema** (sem misturar "planos logísticos"/"calendários"). Motor: `_pesquisar_modelo` sem `exists()`/`count()` totais (total = registos trazidos, "N+" quando cortado), orçamento de `ORCAMENTO_MODELOS=12` modelos contactados por consulta, fallback SQL só em modo geral. Benchmark: antes bloqueava >180s; agora descoberta <0.3s e profunda 1-10s (limite Neon). Fix `session_id` (varchar(100)) em `ConsultaIA`. Fix `de7ff3a`: quando o nome da tabela casa com o pedido mas os valores não contêm o termo, lista mesmo assim (ex. «lista de funcionarios» → 42 Funcionário).

**Estado real / verificação do dia:**
- `app.py` e `routes_eleitoral.py` compilam (`ast.parse`, via script em temp — PowerShell não aceita heredoc/aspas triplas em `-c`).
- Templates inline de `app.py` (`MAIN_TEMPLATE`, `CADASTROS_TEMPLATE`, `RELATORIOS_TEMPLATE`, `LOGIN_TEMPLATE`) e todos os templates de `templates/eleitoral/` renderizam via Jinja2.
- `import app` e `import routes_eleitoral` OK em modo nuvem; `init_pg_db` + `migrar_schema_eleitoral` aplicados ao PG (coluna `tem_filhos` + tabela `eleitoral_movimento_historico`) e ao SQLite.
- App corre em modo nuvem (PG) no ambiente atual; SQLite mantido pelo setup híbrido.

## 4. ESTADO DE IMPLEMENTAÇÃO — TAREFAS NOVAS 2026-08-30 (pós `eb54219`, A COMMITAR)

- [x] **Inventário por local** — botão "📦 Inventário DDGEI" → "📦 Inventário" (`MAIN_TEMPLATE`); `/inventario` abre no setor do utilizador (`session.setor_id`) e, para admin, permite filtrar por **um ou vários** locais (`?filtro_setor=1,2,3`); painel de filtro multi-select no template (admin: todos os setores; não-admin: só `locais_acesso`); título/nav dinâmicos ("INVENTÁRIO LOCAL - <local>")); itens/pendentes/estatísticas respeitam o filtro; coluna SETOR já presente.
- [x] **Anular movimentação de material eleitoral** — nova rota `POST /eleitoral/distribuicao/<id>/anular` (admin): repõe quantidades na **origem** (inverte a dedução da guia) e **retira do destino** se a guia já estiver `RECEBIDO`; marca `estado='ANULADA'` e regista em `eleitoral_movimento_historico`. Botões "⛔ Anular" na tabela e no modal de fluxo (via `pode_anular`); guias anuladas não avançam nem recebem. **Validado end-to-end (SQLite):** origem 100/90/10 → 88/80/8 → anulação 100/90/10; destino 12/10/2 → 0/0/0; estado estável `ANULADA`; avanço e 2ª anulação bloqueados. Resíduos de teste limpos (SQLite+PG).
- [x] **`organograma_canonico.json`** — criado em `gestao_stae/`: 16 áreas (setores ddgeiinout agrupados), 11 províncias (com `codigo_eleitoral`) e mapeamento de cargos→funções; fonte de verdade para a sincronização de RH com o sistema **PORTALSTAE** (Django). Nome da área **UGEA corrigido** para **"Unidade Gestora Executora de Aquisições"** (commit `303e812`).

## 4. ESTADO DE IMPLEMENTAÇÃO — DIA 2026-08-30 (COMMITADO EM `78d1116`/`2989d35`/`eb54219`)

**Núcleo (`gestao_stae/app.py`):**
- [x] Botão/título **"Cadastros" → "Configurações"** (`MAIN_TEMPLATE` + `CADASTROS_TEMPLATE`).
- [x] **Dashboard de relatórios corrigido** — `RELATORIOS_TEMPLATE` reescrito (toolbar de filtros, tabs Inventário/Entradas-Saídas/Movimentos, tabela de itens, gráficos) e `/relatorios` passa `stat_equip/stat_setor/stat_marca` via `json.dumps`; exports usam `?tab={{ tab }}`.
- [x] **`entregue_por` / `recebido_por` obrigatórios** — validação server-side em `registrar_entrada`, `registrar_saida`, `registrar_saida_reparacao` (flash + redirect).
- [x] **Reparação** — na entrada, se motivo contém "repara" e S/N vazio/N/A → `numero_serie = guia`; na saída, `guia_saida = f"{guia_origem}-SAI"` (variante) preservando o S/N original.
- [x] **Permissões admin + acesso por locais** — coluna `users.locais_acesso` (SQLite via `check_db_integrity`, PG via `init_pg_db`); helper `get_locais_acesso()`; login guarda `session['locais_acesso']`; `/`, `/movimentos`, `/inventario` filtram com `IN (...)` para não-admin.
- [x] **Configurações** — secção "Alterar a minha palavra-passe" (form POST `/alterar_senha`, valida senha atual, nova==confirmação, ≥4 chars, pbkdf2); checkboxes `locais_acesso` no add/edit user; scroll no módulo de edição (editModal `max-height:92vh`, editFields `max-height:60vh`).

**Módulo Eleitoral (`routes_eleitoral.py` + `templates/eleitoral/`):**
- [x] Schema: `eleitoral_local_armazenamento.tem_filhos` + tabela `eleitoral_movimento_historico` (SQLite+PG, `migrar_schema_eleitoral` em `app.py`).
- [x] **Nova Aquisição validada** — só em processo `EM_CURSO` com `ano >= ano corrente`; modal de processos default `ano` = ano atual.
- [x] **"Guia de Marcha" → "Guia de Saída"** (titulos/botões); corrigido bug latente no form (`locais` → `locais_origem`/`locais_destino`).
- [x] **Página "Locais"** (nova rota `/eleitoral/locais` + template `locais.html`): CRUD com 13 tipos hierárquicos (directiva geral/nacional/provincial, departamentos, repartição, direcção distrital, postos de recenseamento/votação, entidade externa, + legados CENTRAL/PROVINCIA/PAIS_DIASPORA), campo pai/filhos (`parent_id`, `tem_filhos`) e `provincia_id`.
- [x] **Fluxo de distribuição** — nova guia default `EM_PREPARACAO` (1) → `EMPACOTAMENTO` (2) → `A_ESPERA_ENVIO` (3) → `ENVIADO` (4) → `RECEBIDO` (5); rota `/distribuicao/<id>/estado` só avança e só a origem (admin qualquer); `confirmar_rececao` exige `ENVIADO` (aceita legados `EM_TRANSITO`) e soma o stock; cada mudança é registada em `eleitoral_movimento_historico`.
- [x] **Modal de fluxo com ícones** em `distribuicao.html` (stepper com ícones por etapa, datas/utilizadores do histórico, permissões de avanço/recepção calculadas em `/api/movimento/<id>/fluxo`).
- [x] **Dashboard/mapa** agregam por `provincia_id` (join `eleitoral_provincia`) em vez de `tipo='PROVINCIA'`; `material.html` agrupa locais dinamicamente por tipo.

**Notas:** a rota `/alterar_senha` é acessível a qualquer utilizador autenticado, mas o formulário fica apenas em `/cadastros` (admin-only). A tabela `eleitoral_movimento_historico` NÃO foi adicionada ao `SYNC_CONFIG` (é escrita diretamente nas duas BDs).

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

Nenhuma pendência em aberto. As pendências anteriores foram resolvidas a 2026-08-30 (ver RESOLVIDAS abaixo).

### RESOLVIDAS (2026-08-28/29/30)
- ~~Sincronização de RH com o PORTALSTAE~~ — **implementada** e aplicada 2026-08-30 ao PG Neon: script `PORTALSTAE/sync_rh_ddgeiinout.py` (dry-run/--apply) lê `stae.db` + `organograma_canonico.json` e escreve em `recursoshumanos`. Resultado: setores 23→**27 ativos** (9 criados: DRS/DFIN/DPAT/DAQ/DPROT/GCI/GJUR/SG/UGEA; restantes renomeados/normalizados; **5 fictícios desativados** com `ativo=False` — DIRECÇÃO AAA, DEPARTAMENTO AAA, CDELGADO, MAPUTOC, MAPUTOP — em vez de delete, por FKs PROTECT externas no PORTALSTAE); funcionários 19→**42** (30 reais: 7 slots nacionais reatribuídos in-place preservando `id`/`numero_identificacao` + 23 novos com número/QR auto; os 12 "Gestor - <Província>" mantidos com sector provincial ligado). Chefes de área: DDGEI→Graça Simão, DRH→Júlio Dinís Devesse, DFIN→Eurico Matavel, DAQ→Saimon Massingue. Nomes/acentos do stae.db já estavam corretos (a "corrupção" era só do output do console).
- ~~`organograma_canonico.json`: nome da área UGEA~~ — **corrigido** 2026-08-30 para **"Unidade Gestora Executora de Aquisições"** (commit `303e812`).
- ~~`check_permission()` do módulo eleitoral refinar por perfil~~ — **resolvido** 2026-08-30: admin sempre; não-admin apenas `perfil='tecnico'` com `eleitoral_local_id` definido; `'protecao'` bloqueado (302 → `/`). Verificado por smoke test em SQLite e nuvem.
- ~~Valores legados `'Disponvel'`/`'Indisponvel'` na BD~~ — **resolvido** 2026-08-30: literais corrigidos no código (já eram gravados sem acento em `app.py`) + UPDATE de normalização em `check_db_integrity` (SQLite) e `init_pg_db` (PG). Dados limpos em ambas as BDs (0 registos restantes).
- ~~Revalidar modo Nuvem~~ — **resolvido** 2026-08-30: smoke test com `CLOUD_MODE=true` (rotas eleitorais 200 por admin/técnico, protecção 302); schema `tem_filhos` + `eleitoral_movimento_historico` confirmados no PG; normalização aplicada no PG.
- ~~Relatórios: dashboard partido (stat_* ausentes)~~ — **resolvido** 2026-08-30 (RELATORIOS_TEMPLATE + stats + tabs).
- ~~"Cadastros"/"Guia de Marcha"/"Brigada"~~ — **renomeados** 2026-08-30 ("Configurações", "Guia de Saída", hierarquia de Locais sem brigadas).
- ~~Nova Aquisição sem validação de processo~~ — **resolvido** 2026-08-30 (exige processo EM_CURSO com ano ≥ corrente; ano default na UI).
- ~~Acompanhamento de distribuição sem histórico de estados~~ — **resolvido** 2026-08-30 (fluxo 5 estados + modal com ícones + `eleitoral_movimento_historico`).
- ~~`(index):1009 Unexpected string` — erro de sintaxe JS na página inicial~~ — **corrigido** 2026-08-30: no `MAIN_TEMPLATE` (`app.py:1264`) o `\'` dentro de string `'''...'''` do Python era des-escapado para `'`, gerando `'' + guia + ''` (JS inválido). Corrigido para `\\'`. Também adicionado favicon inline (SVG data-URI) em `COMMON_HEAD` para eliminar o 404 de `favicon.ico`.
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
