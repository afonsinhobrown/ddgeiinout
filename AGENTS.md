# AGENTS.md

Instruções para agentes de IA que trabalham neste repositório.

## Antes de começar

- **LEIA `PLAN.md` na raiz** — é o documento de continuidade/autoridade sobre o estado do sistema, pendências e decisões. Atualiza-o sempre que concluíres ou iniciares trabalho.
- **Nunca uses `git stash` como mecanismo de continuidade.** Comunicação de estado é feita via `PLAN.md` commitado, não via WIP em stash.
- Verifica sempre `git status` e `git log --oneline -10` para perceber o ponto real do trabalho.

## Stack

- Flask (Python), templates inline em `gestao_stae/app.py` e `gestao_stae/templates/`.
- Base de dados **híbrida SQLite/PostgreSQL (Neon)** — troca transparente (`smart_connect`, `is_cloud_mode()`, `get_pg_connection()`, `dual_execute()` no módulo eleitoral).
- PDF: ReportLab. Excel: openpyxl.

## Ao alterar código

- Mantém o estilo existente (Português de Moçambique na UI/nomenclatura).
- Escreve/edita ficheiros em **UTF-8** — os patches antigos corromperam acentos (cp1252 round-trip); não reintroduzir.
- Não acrescentes comentários desnecessários; preserva apenas os TODO/documentação já existentes.
- Ao usar tabelas novas no módulo eleitoral, usar `dual_execute()` para escrita simultânea SQLite+PG.

## Verificação

- Sintaxe: `python -c "import ast; ast.parse(open('X.py').read())"` para `app.py` e `routes_eleitoral.py`.
- Considera `is_cloud_mode()` ao alterar lógica de BD — o fluxo difere entre Local (SQLite) e Nuvem (PG).

## Pendências conhecidas (prioridade)

Vê a secção **4. PENDÊNCIAS** em `PLAN.md`. Hoje:
1. `routes_eleitoral.py:255` — `utilizador_id = 1` hardcoded; causa raiz é o login (`app.py:1958`) não guardar `session['user_id']`.
2. `check_permission()` do módulo eleitoral retorna `True` sempre (deve refinar por `perfil`).
3. MD5 no hash de senhas.
4. Acentuação corrompida em alguns templates.

Quando resolveres uma pendência, marca como resolvida em `PLAN.md`.
