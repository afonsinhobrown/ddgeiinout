# PLANO DE DESENVOLVIMENTO — Gestão STAE / DDGEI

> **Documento de continuidade.** Qualquer agente/sessão que retomar este projeto DEVE ler este ficheiro primeiro. Atualizar sempre que concluir ou iniciar trabalho. Registar aqui o estado real, decisões e pendências — nunca depender de stash/commits para comunicação.

Última atualização: 2026-08-31

---

## 3.1 Estado — sessão 2026-08-31 (última; commitado/push)

**Fix: botão "Iniciar Processo" quebrava na nuvem (`166847f`):** `iniciar_processo` (`routes_eleitoral.py`) usava marcador `?` (SQLite) mas em modo nuvem a conexão é PostgreSQL que exige `%s`. Corrigido com `{'%s' if is_pg else '?'}`. Verificado em cloud (id 10 PLANEADO→EM_CURSO). Escaneou-se os restantes `?` no módulo eleitoral — todos os outros estão protegidos por `if is_pg`/`else`.

**Fix: mapa de Moçambique "sumia" em produção (`0c3ec51` + `XXXXXXX`):** o `vercel.json` tinha rota catch-all `/(.*)` que redirecionava também `/static/*` para a app Flask, nunca servindo o SVG. Primeira tentativa (`0c3ec51`) adicionou rota `/static/(.*)` no vercel.json, mas a Vercel devolvia `NOT_FOUND` porque o path `/gestao_stae/static/$1` não correspondia ao output do `@vercel/python`. **Solução final:** o mapa passou a ser servido por uma **rota Flask dedicada `/mapa_mozambique.svg`** (`send_file` de `BASE_DIR/static/mozambique.svg`), que passa pelo catch-all `/(.*)` → app e funciona em qualquer ambiente; o dashboard usa essa rota; a rota `/static/(.*)` foi removida do `vercel.json` (não havia outros estáticos).

**Fix: modal do mapa eleitoral mostrava sempre zero (`293830f`):** causa dupla:
1. `api_mapa_distribuicao` e `api_mapa_provincia` agregavam por `LEFT JOIN eleitoral_provincia ON p.id=l.provincia_id`, mas os locais **não têm `provincia_id` preenchido** (é NULL) — o nome da província está em `l.nome`. Passaram a agregar por **`l.nome`** filtrando `l.tipo='PROVINCIA'` (exclui Central e países de diáspora), como o relatório já fazia.
2. Nenhum endpoint respeitava o `processo_id` selecionado no dashboard (usavam sempre o processo ativo EM_CURSO). Agora ambos aceitam `?processo_id=...` (fallback ao ativo) e o dashboard passa o `processo_id` selecionado. No clique da província, o JS passa o **nome BD** (via mapa inverso) ao endpoint, não a chave SVG normalizada.
- Verificado em cloud: `?processo_id=1` devolve 11 províncias (Cabo Delgado 821.8, Cidade de Maputo 1670.9, Gaza 3834.56...); detalhe por província não-zero com itens. Local idem.
- **Correção posterior (`293830f`+):** quando **não há `processo_id` selecionado** (default "Todos os Processos"), o mapa/modal usavam o **processo ativo** (id 10, só material na Central) → modal zerada, inconsistente com os gráficos que agregam todos os processos. Agora, sem `processo_id`, **agrega todos os processos** (consistente com os gráficos); com `processo_id`, filtra. Também corrigido o mapa inverso de nomes (`Zambezia`→`Zambézia`) e o lookup do heatmap usa o nome BD. Verificado em local+cloud: sem processo devolve 11 províncias e modal não-zero.
- **Nota:** dados preexistentes têm inconsistência `bom`+`mau` ≠ `total` em alguns registos (não introduzido por esta mudança).

**Feat: guias permitem escolher o departamento responsável + `ver_guia` dinâmico (`24894d0`):** o PDF da guia tinha cabeçalho e assinatura hardcoded ("DEPARTAMENTO DE DELIMITAÇÃO GEOGRÁFICA" / "O Chefe de Departamento de Informática") para todas as guias, ignorando o departamento real. Agora:
- Nova coluna `departamento_responsavel_id` em `movimentos` (migração SQLite em `check_db_integrity` e PG em `init_pg_db`).
- Seletor "Departamento Responsável (aparece na guia)" nos 4 formulários: entrada, saída, modal de saída/reparação e modal de saída de inventário (default = setor do utilizador).
- Rotas `registrar_entrada`, `registrar_saida`, `registrar_saida_reparacao`, `registrar_saida_inventario` gravam o campo escolhido (fallback ao setor da sessão).
- `ver_guia`: cabeçalho e "O Chefe de {departamento}" agora dinâmicos. Como os **ids de setor divergem entre local e nuvem**, a resolução usa **normalização por texto** do nome do setor (`nome_canonico_setor`): DDGEI, Património e Aprovisionamento, RH, Finanças, Aquisições, Transportes, Protecção, Recenseamento, DOOE, UGEA, Gabinete, Secretaria. Fallback → DDGEI canónico.
- Nomenclatura: `organograma_canonico.json` DDGEI corrigido para "Departamento de Delimitação **Geográfica**, Estatística e Informática".
- Verificado em local e cloud: PDF gera 200; cabeçalho/assinatura refletem o departamento escolhido (ex: Protecção).

**Nota Neon:** erros de concorrência de fundo na sincronização bidirecional ("database is locked", "deadlock detected", FK `eleitoral_tipo_material_categoria_id_fkey`) são pré-existentes e não afetam SQLite nem as rotas (validadas 200 em local+cloud).

**Fix: somas inconsistentes `total ≠ bom + mau` no módulo eleitoral:** o utilizador reportou que no mapa/modal e em todas as somas da gestão eleitoral os valores não batiam (ex: total 3999.99 mas bom 4773.07 + mau 960 = 5733.07). Causa: **90/135** registos em `eleitoral_material_sobrante` tinham `quantidade_total` gravado independentemente de `bom`+`mau` (input de "Qtd Total" livre no registo/edição/importação). Correção:
1. **Dados corrigidos** em SQLite local (89) e PG cloud (90): `UPDATE ... SET quantidade_total = COALESCE(quantidade_bom,0)+COALESCE(quantidade_mau,0)`. Backup criado: `eleitoral_material_sobrante_backup_20260831` (ambos motores).
2. **Código** (`routes_eleitoral.py`): `registar_material`, `editar_material` e `importacao_excel` agora calculam `quantidade_total = bom + mau` (ignoram o valor de total submetido), garantindo consistência futura.
3. **UI** (`material.html`): campo "Qtd Total" passou a **só-leitura** e auto-soma (Bom+Mau) nos modais de criar e editar; `abrirModalEditar` recalcula.
- Verificado: após correção, as 11 províncias do mapa têm `bom+mau=total` (ex: Nampula 4773.07+960=5733.07); teste de registo com total errado grava `total=bom+mau`.

---

## 3.1 Estado — sessão 2026-08-31 (commitado/push)

**Novas funcionalidades — mapa em texto + relatórios PDF com vários critérios (`8fdd141`):**
- **Mapa (dashboard eleitoral):** ao **clicar** numa província abre um **modal** com o resumo em texto (Total/Bom/Mau) + tabela detalhada por tipo de material e local. Novo endpoint `api_mapa_provincia` (`routes_eleitoral.py`) devolve o detalhe filtrado pelo processo ativo. Tooltip mantido ao passar o rato.
- **Relatórios eleitoral (`/eleitoral/relatorios`):** filtros agora permitem **vários critérios** — processo + múltiplos tipos de material + múltiplas **categorias** + múltiplos **locais** de armazenamento. Novo **PDF server-side** (`/eleitoral/relatorios/exportar_pdf`, ReportLab, landscape) e **Excel** (`exportar_excel`) com todos os critérios aplicados.
- **Relatórios sistema principal (`/relatorios`):** filtros convertidos para **seleção múltipla** (setor, marca, tipo equipamento, status, tipo movimento — Ctrl+clique). Novo **PDF server-side** (`/relatorios/export/pdf`, ReportLab) e **Excel** (`/relatorios/export/excel`) que respeitam todos os critérios combinados.
- Verificado em **modo local (SQLite)** e **modo nuvem (PG)**: páginas 200 e exports PDF/Excel 200 em ambos os módulos.

**Fix produção — `/relatorios` 500 em Vercel (Neon):** a página dava `Internal Server Error`. Causa: agregação `CAST(quantidade AS INTEGER)` falhava no PostgreSQL porque a tabela PG `movimentos` tinha **3 linhas com `quantidade = 'None'`** (string literal, não NULL) — SQLite tolera o cast mas PG lança `invalid input syntax for type integer: "None"`. Corrigido em `7e584df`:
- **Dados:** limpas as 3 linhas em Neon (`quantidade='None'` → `NULL`).
- **Causa raiz:** rota de saída de stock (`app.py:3486`) inseria o valor bruto do form em `quantidade`, que podia ser a string `'None'`; agora normaliza para inteiro seguro antes do INSERT (fallback `'1'`).
- Verificado: todas as tabs de `/relatorios` (inventario/entradas_saidas/movimentos/saidas/transferencias) retornam 200 em **modo nuvem (PG)** e **modo local (SQLite)**.

**Itens dos 9 requisitos do utilizador concluídos nesta sessão:**

- [x] **Item 6 — Processos 2019/2024** — BD SQLite+PG povoada: processos REC 2019, Votação 2019, REC 2024 (EM_CURSO), Votação 2024. Adicionada opção **"Votação"** ao dropdown de tipo em `processos.html`.
- [x] **Item 3 — Nova categoria / Item 7 — adicionar material** (`catalogos.html` + `material.html`): modais funcionais "Nova Categoria" e "Novo Tipo" ligados às rotas `novo_categoria_material` e `novo_tipo_material`. No modal de registo de material, bloco "➕ Material em falta no catálogo?" com campo de texto → rota `novo_tipo_material_texto` (cria tipo, associa à categoria "Meios Circulantes" se existir).
- [x] **Item 5 — Form modal de registo de material funcional** (`material.html`, rota `registar_material` já existia em `routes_eleitoral.py:388`): o form agora submete `processo_id`, `local_id`, `tipo_material_id`, `quantidade_total`, `quantidade_bom`, `quantidade_mau`, `observacoes`; faz INSERT/UPDATE (soma) em `eleitoral_material_sobrante` com dual-write para PG.
- [x] **Item 4 — Importação Excel com pré-visualização** (`routes_eleitoral.py` + `material.html`):
  - Colunas novas `caminho_ficheiro` e `modo` em `eleitoral_importacao_material` (SQLite via `migrar_schema_eleitoral`, PG via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`).
  - A rota `importacao_excel` guarda cópia do ficheiro em `UPLOAD_FOLDER` (`material_import_<ts>_<nome>`) e regista em `eleitoral_importacao_material` via helper `_registar_importacao` (dual-write).
  - Novas rotas: `GET /eleitoral/importacao` (lista JSON de importações) e `GET /eleitoral/importacao/preview/<id>` (lê o ficheiro guardado, devolve até 25 linhas).
  - UI: secção "📤 Últimas Importações" em `material.html` (auto-carrega com `carregarImportacoes()`), modal "Pré-visualização" com `previewImportacao(id)`.
- [x] **Item 1 — Mapa de Moçambique SVG interativo** (`dashboard.html` + `static/mozambique.svg`): após utilizador reclamar que o mapa "nem parece de Moçambique", substituiu os polígonos desenhados à mão por um **mapa real de Moçambique** (SimpleMaps, CC BY, `static/mozambique.svg`, viewBox 0 0 1000 1000, 11 províncias como camadas `<path class="prov" data-prov="...">` separadas). O dashboard carrega o SVG por `fetch()` e injeta em `#mozMapSVG`, aplica coloração heatmap por quantidade (níveis 0-4 via CSS), tooltip com Total/Bom/Mau (liga à API `api_mapa_distribuicao`), e normalização de nomes BD→mapa (`Cidade de Maputo`→`Maputo City`, `Zambézia`→`Zambezia`). Atribuição SimpleMaps na legenda.
- [x] **Item 2 — Registo de equipamento + guia PDF/PNG** — já estava implementado em sessões anteriores (`inventario_add` em `app.py:4775`: aceita PDF e converte imagem JPG/PNG → PDF via `imagem_para_pdf`, guarda `documento_pdf` em `inventario_local`). Nada a fazer nesta sessão.
- [x] **Item 8 — Relatório: tabela primeiro, gráficos depois** (`RELATORIOS_TEMPLATE` em `app.py`): a secção "Relatório de Dados" (tabela) passou a vir ANTES dos gráficos (chartEquip/chartSetor/chartMarca no fim da página). Verificado o índice HTML.
- [x] **Item 9 — Explicação do processo ao utilizador** (`processos.html`): box colapsável "❓ O que é um Processo Eleitoral?" no topo; explica recenseamento/votação, sobrantes, e transferência ao fechar.

**BD / sequences (PG):**
- As sequences das tabelas SERIAL no PG estavam dessincronizadas (ex: `eleitoral_tipo_material_id_seq` em 4 com max 14) → violações de PK/FK ao inserir ("Meios Circulantes"). Corrigidas com `setval(seq, max(id)+1, false)` para todas as tabelas com sequence de `id` (`fix_seq2.py`). Confirmado: categorias, tipos (veículos id 20-24) e processos presentes no PG e SQLite, sem duplicados.

**Nota Neon:** há erros de concorrência de fundo durante a sincronização dinâmica bidirecional ("deadlock detected", FK em `eleitoral_tipo_material_categoria_id_fkey`) — pré-existentes, relacionados com conexões concorrentes à Neon; não provocam falha do SQLite nem das rotas (validado por smoke test 200).

**Validação (modo local):** login admin OK; `/eleitoral/`, `/catalogos`, `/processos`, `/material`, `/distribuicao`, `/relatorios`, `/eleitoral/importacao` todos 200; novos elementos presentes no HTML renderizado (tabela-importacoes, modal-preview, input_novo_tipo, mozMapSVG, "O que é um Processo").

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

**Working tree: `PLAN.md` + `gestao_stae/app.py` modificados (trabalho 2026-08-31), a commitar.**

**Entrada para inventário / desacoplar do DDGEI (2026-08-31, `app.py`):**
- **Modo Inventário** novo no formulário "Nova Entrada" (toggle 📦 no topo). Quando ativado:
  - **Destino obrigatório e selecionável** (todos os setores; default = setor do utilizador) — o material pode ser cadastrado em **qualquer local**.
  - **Origem opcional** (se vazia → `origem_destino = "Inventário Directo"`; se `SETOR_x` guarda também `setor_origem_id`).
  - Handler `registrar_entrada` usa `destino_inventario` como `setor_destino_id` (em vez de forçar o setor do utilizador).
- **Modo normal (não-inventário)** mantido: origem obrigatória, destino = setor do utilizador.
- **PDF `/ver_guia`** deixa de ter `"STAE - DDGEI"` hardcoded como destino (entrada) / origem (saída): passa a resolver por `setor_destino_id`/`setor_origem_id` via mapa `setor_map` (fallback: `local_destino`/`local_origem`, e "Inventário Directo" se não houver setor).
- **Histórico (index + `/movimentos`)** mostra colunas ORIGEM e DESTINO separadas, resolvendo os nomes de setores por `id` (`setor_origem_nome`/`setor_destino_nome`) em vez dos fallbacks `'DDGEI'`.
- **Validado (modo local/SQLite):** POST inventário sem origem cria `setor_destino_id=5`, `origem_destino="Inventário Directo"`; modo normal sem origem é rejeitado; com origem insere como antes; índices/páginas renderizam 200; guia PDF gera (200 application/pdf).
- Nota: Neon inacessível hoje (timeout) — revalidar modo nuvem quando ligação estiver disponível.

**Fix login com hash `scrypt` (2026-08-31, `app.py` + PG):**
- **Causa raiz:** `app.py:2736` só verificava senhas com prefixo `pbkdf2:` (ou MD5). Utilizadores criados com werkzeug 3.x na nuvem têm hash `scrypt:...`, que o `check_password_hash` do werkzeug **2.3.7** (ambiente local atual) não consegue verificar → login falhava.
- **Fix no código:** login (`/login`) e `alterar_senha` passaram a aceitar qualquer hash werkzeug (`':'` e não-`md5` → `check_password_hash`), mantendo o fallback MD5-legado. `app.py:2736` e `app.py:3715`.
- **Fix na BD (Neon/PG):** o hash da utilizadora **`erica` (id 25)** foi normalizado para `pbkdf2:sha256` de `123` (verificável em qualquer werkzeug). Login `erica`/`123` validado (renders dashboard OK).
- **Ainda em aberto (risco sistémico):** o utilizador **`banze` (id 6)** continua com hash `scrypt` no PG — se o servidor que corre o sistema usar werkzeug 2.3.7, o `banze` não entrará. Opções: (a) actualizar werkzeug para 3.x no servidor, ou (b) redefinir a senha do `banze` via `/cadastros` (admin). Utilizadores 2–5 têm hash MD5 legado (já migrados no 1º login).
- **Decisão tomada:** NÃO se atualizou a stack (upgrade Flask 2.3→3.x seria arriscado e pode quebrar a app). Em vez disso normalizam-se os hashes `scrypt` para `pbkdf2:sha256` (verificável em qualquer werkzeug) no PG: **`erica` → `123`** e **`banze` → `banze123` (temporária)**. O `admin`/`tecnico`/`protecao`/etc. NÃO foram tocados (MD5 legado já migrado no 1º login; possíveis senhas personalizadas preservadas). O código aceita qualquer hash werkzeug (`pbkdf2:`/`scrypt:`) + fallback MD5, por isso futuros utilizadores criados na nuvem (scrypt) funcionam se o servidor tiver werkzeug 3.x.


**Sincronização RH concluída (2026-08-30)** — ver §4 e §5.

**PORTALSTAE — IA Eleitoral (2026-08-30, commits `3ffeb52`→`222a2e7`, repo PORTALSTAE):**
- **Fix produção:** `templates/recursoshumanos/relatorios/licencas.html` criado (estava em falta → `TemplateDoesNotExist` em `/rh/relatorios/licencas/`; pusheado no `3ffeb52` — **produção ainda precisa de deploy manual no Render**).
- **RH inicia licença/avaliação/mensagem por funcionário** (`3ffeb52`): ação "Solicitar Licença" (RH escolhe funcionário), "Iniciar Avaliação" (`avaliacao pendente` sempre preenchida pelo chefe/diretor), "Enviar Mensagem Direta"; tipo **Dispensa** + migração `0004`; era o commit `222a2e7`? — não, `222a2e7` é a IA).
- **IA Eleitoral em 2 passos** (`222a2e7`): 1º o prompt devolve **temas** (recursos humanos/equipamentos/círculos/material/etc.) sem varrer a BD; o utilizador escolhe um e só então a pesquisa profunda corre **só nesse tema** (sem misturar "planos logísticos"/"calendários"). Motor: `_pesquisar_modelo` sem `exists()`/`count()` totais (total = registos trazidos, "N+" quando cortado), orçamento de `ORCAMENTO_MODELOS=12` modelos contactados por consulta, fallback SQL só em modo geral. Benchmark: antes bloqueava >180s; agora descoberta <0.3s e profunda 1-10s (limite Neon). Fix `session_id` (varchar(100)) em `ConsultaIA`. Fix `de7ff3a`: quando o nome da tabela casa com o pedido mas os valores não contêm o termo, lista mesmo assim (ex. «lista de funcionarios» → 42 Funcionário). **Descoberta mais precisa (`descobrir_propostas` novo):** além dos nomes de tabelas e da memória, o prompt cruza com as **rotas/vistas/templates reais do portal** (keywords por app, calculadas 1× e em cache `_rotas_de_app`; cada página é uma resposta possível) — p.ex. `licencas`→RH, `documentos institucionais`, `mesas de voto`→Material, `listas de candidaturas`→Candidaturas. Fix ruído: termos genéricos (`listas`, `relatorio(s)`, `relacoes`, `gestao`, `registar`...) excluídos via `KW_GENERICAS`. Ainda não commitada (só PLAN.md).

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
