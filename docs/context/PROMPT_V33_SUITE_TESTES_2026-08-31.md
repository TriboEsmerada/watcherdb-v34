# PROMPT V3.3 — os 11 problemas que restavam na suite de testes

Data: 2026-08-31 | Origem: sessão V6, ao tentar correr os e2e do V3.3
**REVISTO + EXECUTADO 2026-08-31/09-01 (sessão V3.3)**: a verificação na fonte mostrou
que 3 dos 4 grupos tinham a CAUSA mal diagnosticada na 1.ª versão deste doc. Este
ficheiro regista as causas reais e o que foi feito — a 1.ª versão está no git.

## O que aconteceu antes (contexto, não repetir)

A suite do V3.3 não corria de todo: `tests/integration/test_favicon.py` era um script
com código no topo do módulo que chamava `sys.exit(1)` durante a colecção → aborta a
corrida inteira com `INTERNALERROR` (parece problema de ambiente, ignora-se). Renomeado
para `check_favicon_manual.py` (commit `56adaf4`): 0 → 829 coleccionados. Depois
`tests/test_functional_acceptance.py` marcado `e2e` + `BASE_URL` corrigido para
`https://localhost:8433` (commit `4cd6214`). Estado à data do doc: 793 testes, 782
passam, 6 falham, 5 erro.

## Os 11 restantes — causa REAL verificada vs diagnóstico inicial

### 1. `test_new_queries_v148.py` — diagnóstico inicial ERRADO
- Dizia: "constante `FILEGROUP_GROWTH_HISTORY` removida do produto".
- Real: a constante existe desde sempre, mas DENTRO da classe `SQLQueries`
  (`modules/monitoring/queries.py:1623`) — o import module-level nunca funcionou.
  Em py3.11 nem lá chega: `SyntaxError` (backslash em f-string, legal só ≥3.12) na :196.
- É um script manual (`class NewQueriesTester`, sem funções `test_*`).
- **Feito**: renomeado `check_new_queries_v148_manual.py`, import corrigido via
  `SQLQueries.<attr>`, f-string corrigida. Colecção e2e desbloqueada (49 specs colectam).

### 2. `test_mirroring_diagnosis_endpoint_with_mocked_db` — diagnóstico inicial ERRADO
- Dizia: "endpoint não produz `mirror_errorlog`".
- Real: produz (`api/routers/queries/mirroring_diagnosis.py:261`). O mock tinha
  `LogDate: '2026-08-17 10:00:00'` literal e `_errorlog_recent` filtra a 7 dias de
  `datetime.now()` — o teste "expirou" a 2026-08-24. Endpoint e teste nasceram juntos
  (`9a47c09`), o mock estava afinado ao dia.
- **Feito**: mock passou a data relativa (`datetime.now() - 1h`). 13/13 verdes.
  **O porte do drill-down de mirroring para o V6 está DESBLOQUEADO** — nem teste nem
  endpoint estavam conceptualmente errados (ver `PROMPT_V6_DRILLDOWNS_2026-08-31.md`).

### 3. Quatro "erros de import" em `tests/integration/` — diagnóstico inicial ERRADO
- Dizia: "testes presos a nomes que o produto já não tem".
- Real: zero ImportErrors. `test_admin_auth.py` e `test_fixed_queries.py` têm funções
  `test_*` com parâmetros que o pytest lê como fixtures inexistentes;
  `test_parametrized_queries.py` e `test_index_fragmentation_v1481.py` têm o mesmo
  `SyntaxError` de f-string. Todos são scripts manuais contra SQL Server/serviço real.
- **Feito**: renomeados para `check_*_manual.py` (padrão do favicon) + f-strings
  corrigidas para continuarem executáveis à mão.

### 4. Cinco smokes sobre o template — diagnóstico inicial CERTO, com 1 excepção
- `test_exec_summary_redesign_smoke.py` (3): o portal mudou por decisão registada
  (commit `71707ae`, racional no próprio CSS `:1748` — 5 stats numa linha via
  auto-fit minmax(148px) à largura real do card; 52px/30px viraram topo de clamp()).
  Intenção mantém-se → asserções actualizadas ao mecanismo novo.
- `test_theme_v33_foundation_smoke.py::test_overflow_db_problems`: commit `9029a42`
  antepôs guard de no-data ao ternário; intenção (ladder tokenizada) mantém-se →
  âncora relaxada.
- **`test_no_severity_ladders_remain`: era REGRESSÃO DO PRODUTO, não do teste** —
  ladder hex hardcoded em `watcherdb_portal.html` (era :42976, commit `f0cdd79`
  pós-tokenização F4). Corrigido o PRODUTO: `getSevTokens(s).fill` (GO do
  frontend-specialist). O teste fez exactamente o trabalho para que foi escrito.

## Guarda anti-recaída (nova, executada)

`tests/unit/test_no_toplevel_execution_guard.py`: AST scan de todos os
`tests/**/test_*.py`; falha se houver chamadas perigosas ao nível do módulo
(sys.exit, requests/socket/subprocess, main()) fora de funções e do guard
`__main__`. **Na primeira corrida apanhou logo mais 5 scripts disfarçados**
(`test_all_queries.py`, `test_memory_integration.py`, `test_os_memory_api.py`,
`test_os_memory_scenarios.py`, `test_sqlhdsprd014.py` — este último fazia
`requests.get` com timeout=60 ao porto 7000 em CADA colecção). Renomeados.

## Nota de método (mantém-se, com adenda)

A regra *"cada vermelho é hipótese sobre o teste até prova no produto"* pressupõe que
os testes cheguem a correr — e pressupõe também verificação NA FONTE antes de aceitar
um diagnóstico: 3 dos 4 grupos deste doc vinham com causa errada, e 1 vermelho
(`test_no_severity_ladders_remain`) era o produto, não o teste.
