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

## 3. Estado atual (2016-07-11 em diante)

Branch `main`, `git status` LIMPO, sem conflitos, sem trabalho não commitado. Últimos commits:

- `5ce3824` fix: adaptador decimal e cores Excel
- `cc717c6` feat: botão Export Excel na interface de material
- `ca81ba5` feat: dual-write SQLite+PG para editar/apagar/importar Excel no eleitoral
- `7c41216` feat: rotas do módulo eleitoral (processos/inventário)
- `9f0832d` / `4b433eb` / `b597956` feat: suporte hybrid SQLite/PG e migração

**Todos os ficheiros compilam.** App sobe com `python app.py` (ou `executar.bat`).

## 4. ESTADO DE IMPLEMENTAÇÃO (2026-08-29)

### NOVO TRABALHO EM CURSO — Desvincular do DDGEI / Locais / Saída por local

**Requisitos do utilizador (2026-08-29):**
1. O sistema **não deve estar ligado ao DDGEI** — o inventário deve ser de **todos os locais** onde o equipamento é cadastrado.
2. **Usuários associados a um lugar** — os usuários atuais devem ser associados ao local DDGEI.
3. **Saída de equipamento de um lugar para outro**:
   - Deve ser feita pelo **usuário desse local** (origem = local do usuário, não selecionável).
   - Quando é **admin**, o local de origem **pode ser selecionado**.
4. **Histórico de movimentos** deve mostrar **origem e destino separados** e mostrar **estado do equipamento**.
5. **Estados de saída**: preparação, empacotamento, à espera de envio, enviado, recebido.
6. **Admin configura quais usuários realizam essas ações**.

**Estado atual do código:**
- `users` já tem `setor_id` (local). Os usuários atuais têm `setor_id=1` (RECENSEAMENTO E SUFRAGIO) — devem ser associados ao DDGEI (setor_id=3).
- `inventario_local` já tem `setor_id` (local de armazenamento).
- `movimentos` já tem `setor_origem_id`, `setor_destino_id`, `local_origem`, `local_destino`, `estado_rastreio`.
- `registrar_saida` usa `session.get('setor_id')` como origem — já correto para não-admin.
- Estados intermédios já existem: `EM_ESTOQUE`, `EM_PREPARACAO`, `EMPACOTAMENTO`, `A_ESPERA_ENVIO`, `EM_TRANSITO`, `RECEBIDO`, `EM_USO`, `AVARIADO`.

**Trabalho a fazer:**
- [x] Associar usuários atuais ao local DDGEI (setor_id=3) — feito em `check_db_integrity`.
- [x] Formulário de saída: origem automática (setor do usuário) para não-admin; selecionável para admin — feito no `MAIN_TEMPLATE` + `registrar_saida`.
- [x] Histórico de movimentos: mostrar origem e destino separados + estado — feito no `MAIN_TEMPLATE`.
- [x] Estados de saída no formulário de saída (campo `estado_saida` guardado em `estado_rastreio`) — feito.
- [ ] **FLUXO COMPLETO DE ESTADOS NÃO IMPLEMENTADO** — falta o mecanismo de mudar o estado ao longo do tempo (preparação → empacotamento → à espera de envio → enviado → recebido) e o controlo de permissões (quem envia não pode marcar como recebido). O estado não aparece nas opções do material.
- [ ] Admin configura quais usuários realizam ações (campo de permissão no cadastro de usuários).

> **NOTA IMPORTANTE (2026-08-29):** O trabalho está **INCOMPLETO**. Foi adicionado apenas o campo "Estado de Saída" no formulário e guardado na BD, mas o **fluxo completo de mudança de estado** e o **controlo de permissões** (quem envia não pode marcar como recebido) **NÃO foram implementados**. O utilizador reportou que o estado não aparece nas opções do material e que a mudança de status está confusa. Este trabalho deve ser retomado numa próxima sessão com foco em:
1. Botão/opção para mudar o estado de um movimento ao longo do tempo.
2. Regras de permissão: origem pode marcar preparação/empacotamento/à espera de envio/enviado; destino pode marcar recebido.
3. Mostrar o estado atual nas opções do material.

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
- Rever `check_permission()` do módulo eleitoral (retorna `True` sempre) e o `session['user_id']` em `routes_eleitoral.py:255` (causa raiz: login SELECT não inclui `id`).
- Migrar hash de senhas MD5 para algo mais forte.
- Corrigir acentuação corrompida em alguns templates.

## 5. PENDÊNCIAS ABERTAS (refinar)

### Prioridade Alta

- **[Novo - 2026-08-28] Anexo de imagem do documento do equipamento → PDF**
  - Permitir **anexar uma imagem do documento do equipamento** na entrada, em **qualquer direção, incluindo Central**.
  - Essa imagem deve ser **transformada em PDF** para armazenamento/consulta.

- **[Novo - 2026-08-28] Estados intermédios de equipamento (NÃO obrigatórios)**
  - Deve haver um mecanismo **não obrigatório** de outros estados do equipamento, ex: **em preparação, empacotamento, à espera de envio**, etc.
  - O estado é registado quando aplicável; o fluxo não obriga a passar por todas as etapas.

- **[Novo - 2026-08-28] Movimentação entre Províncias + Acompanhamento (rastreio) + Locais**
  - Além da Central, o STAE tem **11 direções provinciais** → devem ser **cadastradas como provinciais**.
  - Quando o equipamento sai, deve existir um **status de acompanhamento** que mostra **onde está**, até ser **confirmado no destino**.
  - Ao ser confirmado no destino, **atualizar as quantidades**.
  - **Visibilidade restrita**: só os envolvidos (origem e destino) conseguem **ver** esse equipamento durante o trânsito.
  - Deve também **salvar os locais** onde o equipamento está **armazenado ou em uso**.
  - Nota: já existe fluxo de transferência inter-setorial com confirmação de receção no núcleo + guias de movimentação no módulo eleitoral — estender/consolidar para províncias.

- **[Novo - 2026-08-28] Leitura de BARCODE de equipamento**
  - O sistema deve fazer **scan do barcode** do equipamento, tanto no **cadastro** como na **busca dos detalhes**.
  - A leitura do barcode **NÃO é obrigatória** no cadastro (campo opcional).

### Prioridade Alta
- **[TODO código]** `routes_eleitoral.py:255` — `utilizador_id = 1` hardcoded no `encerrar_processo`. Comentário: *"get from session properly"*.
  - **Causa raiz**: o login em `app.py:1958` faz `SELECT perfil, nome_completo, setor_id, eleitoral_local_id FROM users ...` mas **NÃO inclui `id`**, logo `session['user_id']` nunca é definido.
  - Outros sítios em `routes_eleitoral.py` (linhas 491, 863, 1079, 1123) usam `session.get('user_id', 1)` — caem no fallback `1` por causa disso.
  - **Solução proposta**: alterar o SELECT do login para incluir `id` e guardar `session['user_id']`. Depois substituir os `session.get('user_id', 1)`/`utilizador_id = 1` pelo valor real.

### Prioridade Média
- **Permissões do Módulo Eleitoral** — `check_permission()` em `routes_eleitoral.py:62` retorna `True` sempre (comentário: *"Temporariamente aberto para evitar bloqueios, refinar depois"*). Em `app.py:1986` `check_permissions()` (before_request) já bloqueia admin vs não-admin para o núcleo. Refinar para o módulo eleitoral seguindo `perfil`.
- **Hashear senhas** — login usa `hashlib.md5` (`app.py:1954`); hash fraco. Migrar para algo mais forte (bcrypt/werkzeug) e atualizar credenciais padrão.

### Prioridade Baixa / Cosmético
- **Acentuação corrompida em alguns templates** — "Instituições"→"Instituies", "Sada", "Receo", "Disponvel" etc. (round-trip cp1252/utf-8 em patches antigos). Visível na UI.
- **`debug=True`** em execução local (`app.py` fim).

## 6. Itens de operação / hygiene

- **`stash@{0}`** — WIP antigo (2026-05-14, "Sistema Completo Gestão STAE - Versão Premium"; base `2e80f94`, UI/template DESATUALIZADA). **Supersedido** — pode descartar com `git stash drop stash@{0}`. Não mexer noutra ocasião como se fosse trabalho atual.
- **Scripts de patch (patch1–patch18, scratch/)** — ferramentas one-off de desenvolvimento/modificação. Já aplicadas ao `app.py`/`routes_eleitoral.py` commitados. NÃO re-executar à toa; são referência histórica.
- Senhas padrão: admin/admin123, tecnico/tecnico123, protecao/protecao123. Trocar em produção.

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
