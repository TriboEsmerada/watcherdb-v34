# Pedido para a sessão V6 — propagar o lote de 17–18/08 do V3.3

> Copia a partir do `---` para a sessão de Claude Code aberta no repo **WATCHERDB_V6**.

---

Estás no WatcherDB **V6** (`C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V6`). Preciso que
propagues, com critério, três waves que acabaram de ser feitas e validadas no **V3.3** na sessão de
17–18/08. **Não apliques nada às cegas** — segue as regras abaixo.

## Fonte da verdade (lê primeiro, na íntegra)

Os três documentos de propagação estão no repo V3.3 e explicam regras + contratos, não só o diff:

1. `..\WATCHERDB_V3.3\docs\context\PROMPT_PROPAGACAO_V6_JOBS_SCHEDULES_2026-08-17.md`
   — agendamentos na aba Jobs, "próximo backup" no KPI, "Jobs de Backup" na aba Backup, e o **P0**:
   módulo Jobs a devolver 200 vazio (response_model + handler de ResponseValidationError).
2. `..\WATCHERDB_V3.3\docs\context\PROMPT_PROPAGACAO_V6_DIAGNOSTICO_2026-08-17.md`
   — componente único `renderDiagnosisLayout` (O que se passa / Porquê / O que fazer / Evidência
   técnica / Dados brutos), análise determinística do plano de execução (`plan_analyzer` +
   `/api/queries/plan-analysis`), drill-down de mirroring (`/api/queries/mirroring-diagnosis`),
   `Recommendation.effort`/`DetectedProblem`, gate SQL 2014 nos investigators.
3. `..\WATCHERDB_V3.3\docs\context\PROMPT_PROPAGACAO_V6_KPI_ENV_E_FILA_CPU_2026-08-18.md`
   — indicador "Fila de CPU" (collector, herda via BD) e o filtro por ambiente dos KPIs (contrato
   `ev()`→`by_env`).

Referência cruzada: `..\WATCHERDB_V3.3\findings-inbox.md` (FIND-20260817-101/102/103/104/105,
FIND-20260818-101) e `..\WATCHERDB_V3.3\docs\context\CONTEXT.md` (Diário, entradas de 17–18/08).

## Regras de trabalho (não negociáveis)

- **Consultar o especialista antes de aplicar.** Trabalho não-trivial: debate com o specialist da área
  (ver routing dos agents), planeia, executa por consenso — não apliques-e-depois-validas.
- **Portal V6 NÃO é superset do V3.3.** Faz `grep`/`Select-String` das âncoras **antes** de assumir que
  o alvo existe; se o V6 não tiver a superfície, não a inventes — aplica só o que faz sentido no V6 e diz
  o que ficou de fora.
- **`helpers.py`/agregador de KPIs NÃO é partilhado** entre V3.3 e V6 — cada um tem a sua cópia. O mesmo
  anti-padrão pode existir no V6 de forma independente: **verifica, não assumas herdado.**
- **BD partilhada `WatcherDB_Intelligence`:** este lote é **zero DDL**. Qualquer necessidade de DDL passa
  por handoff/veto do `watcherdb-v1-intel-specialist` — não toques em tabelas/vistas partilhadas sozinho.
- **Identidade:** só `sql_monitoring`, SELECT-only; nunca Trusted_Connection do utilizador; nada de GRANT
  EXECUTE (reescreve inline, como o `agent_datetime` → DATEADD/CONVERT 112 do V3.3).
- **Tier:** tudo isto é Standard/core; corre o gate anti-tier-creep antes de fechar. Sem rótulos que
  insinuem feature Pro (AI/preditivo/score opaco).
- **Sem citar marcas sem prova:** nome de ferramenta externa de backup só quando detectado
  (`device_type`/`physical_device_name`); textos genéricos dizem "ferramenta externa de backup".
- **CSP:** novo JS/CSS entra em blocos `<script nonce>`/`<style nonce>` **existentes** — nunca criar
  blocos novos (incidente 2026-08-13).
- **i18n PT/EN/ES** obrigatório para strings novas (PT pós-AO90); **sem onclick inline com JSON**
  (data-attributes + delegação); IDs de secção resolvidos dentro da `.tab-content.active` (2 tabs da
  mesma instância).
- **Testar cada wave** (pytest de contrato/shape onde aplicável + verificação no browser nos 3 temas) e
  **commitar** com mensagem por wave. Reporta panorama (feito/em-curso/pendente).

## O que fazer, por wave

**A) Fila de CPU (o mais rápido — herda via BD).** Confirma se o V6 tem cópia própria de
`collect_processes.py` e da `KPI_MSSQL_PROCESSES_AGG_VIEW`. Se **não** tiver, herda do collector V1
único (só precisa do `Restart-Service WatcherDBCollector`, já feito no V3.3, + 1 ciclo). Se **tiver**
cópia, aplica `COALESCE(r.status, s.status)`. Propaga o rótulo "Fila de CPU" + ajuda se o card existir.

**B) Filtro por ambiente dos KPIs.** Audita o dashboard V6 com o **contrato**: para cada `ev(sec,'campo')`
a chave `campo→by_env` derivada tem de existir no payload, senão o filtro cai no total. Aplica por caso —
alias (nome só diferente), split por ambiente (full/diff/other), ou `ev()` em vez de `n()` fixo. Copia o
teste de contrato do V3.3 (`tests/unit/test_kpi_env_breakdown_20260818.py`) e ajusta às chaves do V6.

**C) Módulo Jobs / agendamentos + D) layout Diagnóstico + análise de plano + mirroring.** Segue os
documentos 1 e 2. Confirma primeiro se o V6 tem o mesmo P0 do módulo Jobs (grep `ResponseValidationError`
+ `JobsAnalysisResponse`). Para o `modules/performance/`, confirma se é cópia própria do V6 (o `base.py`
com `Recommendation`/`InvestigationResult`); se for, aplica `effort`/`DetectedProblem` e o gate SQL 2014.

## Ordem recomendada

A (fila de CPU, verificação rápida) → B (filtro de ambiente, contrato) → C (Jobs, inclui o P0) → D
(diagnóstico/plano/mirroring, o maior). Cada wave: consultar specialist → aplicar → testar → commitar →
panorama. No fim, atualiza o CONTEXT.md do V6 e diz o que ficou por herdar/aplicar e porquê.
