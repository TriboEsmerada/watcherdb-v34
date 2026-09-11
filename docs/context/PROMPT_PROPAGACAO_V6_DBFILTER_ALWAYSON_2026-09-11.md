# Prompt de propagação para o V6: FIX DB-FILTER (2fad907) + ALWAYS ON REGRA ÚNICA (ce0db42) + AbortError (fd0d7f0)

Contexto para a AI do V6 (regra 3/4 do owner: mudanças no V3.4 são explicadas para o V6 aplicar).
Origem: TestSprite do owner (10/09) apanhou dois defeitos reais no V3.4; ambos existem no V6 se o portal
e os routers de intelligence foram copiados. Os scripts PASSO do V3.4 são independentes de número de
linha (âncoras de texto), por isso podem ser reutilizados tal e qual se os trechos forem iguais.

## 1. FIX DB-FILTER (Overview > Bases)

Sintoma: o campo "Filtrar databases" não filtra. Causa: `oninput="renderDbTable(this.value)"` descarta o HTML
devolvido; os cabeçalhos de ordenação fazem `innerHTML = renderDbTable(...)` e funcionam. Sem estado vazio.

Verificar no V6: `grep -n "renderDbTable" templates/watcherdb_portal.html`. Se existir:
- correr `py docs/context/FIX_DBFILTER_PASSO1_apply.py` (copiar do V3.4; aborta se alguma das 5 âncoras não bater)
- resultado: `applyDbFilter(valor)` copia só `#db-table-body` e `#db-count` (foco mantido); linha
  "Nenhuma base de dados encontrada" com chave `overview.no_databases_found` em pt/en/es
- testes: `tests/unit/test_overview_db_filter_20260910.py` (4 estáticos) + `TestFiltroBases` em
  `tests/e2e/test_semantic_e2e.py` (requer o runner TestSukita; opcional no V6)

## 2. ALWAYS ON REGRA ÚNICA

Sintoma (TestSprite TC-011): cartão "Always On unhealthy" = 2, modal lista 4 "instâncias". Diagnóstico: as 4 eram
BASES (a STG tem uma linha por instância+base); o cartão conta `COUNT(DISTINCT Instance)`. Não era regra, era
unidade e rótulo. Mas: (a) o resumo (`helpers.collect_alwayson`) e a modal (`intelligence_kpis`, kpi_type
`always-on`) tinham duas cópias do WHERE que divergiam se a coluna `Availability_Mode` existisse; (b)
`unhealthy_by_env` contava linhas por base, não instâncias distintas, logo não somava o cartão.

Aplicar no V6:
- copiar `api/routers/intelligence/alwayson_rules.py` tal e qual (sem dependências além da stdlib)
- correr `py docs/context/ALWAYSON_REGRA_UNICA_PASSO1_apply.py` (copiar do V3.4). Se as âncoras de
  `helpers.py` / `intelligence_kpis.py` / portal não baterem, aplicar à mão:
  - COUNT: `AND ({unhealthy_where("", has_avail_mode)})`
  - lista e modal: `{problem_reasons_case('s', has_avail_mode)} AS Problem_Reasons` e `AND ({unhealthy_where('s', has_avail_mode)})`
  - `results["always_on"]["unhealthy_by_env"] = by_env_distinct_instances(rows, _infer_env_from_instance)`;
    + `unhealthy_db_count` e `unhealthy_instances_count`
  - portal `showProblematicInstances`: ramo `kpiType === 'always-on'` com "Total: N instância(s) · M base(s) com problema"
    (chave `kpi_modal.database_s` em pt/en/es)
- testes: `tests/unit/test_alwayson_rules_20260911.py` (8; o de contrato lê helpers/kpis/portal)
- unidade do KPI documentada: "instâncias distintas com pelo menos uma base unhealthy"
- FORA (decisão do owner, infra partilhada V1): acrescentar `Availability_Mode` à STG; N/D no cartão em erro de leitura

Prova no V3.4: SELECT do owner 10/09 16:0x = 1 linha (MYBAGP2@SQLHDSPRD405, secundária suspensa) = 1 instância = cartão 1.

## 3. AbortError como info (portal ~15432)

`debugLog('[processResponse] ${label} - ERRO: ...', 'error')` regista pedidos cancelados pela troca de aba como
erro de consola. Passa a `'info'` quando `error.name === 'AbortError'`. Uma linha; ver `PONTO3_PASSO1_apply.py`.

## Ordem sugerida no V6

1 → 2 → 3, cada um com o seu commit; restart do serviço V6 entre 1 e 2 se se quiser validar no browser.
