# PROPAGAÇÃO V6 — lote 18/08/2026: filtro por ambiente dos KPIs + indicador "Fila de CPU"

> Para a AI do V6. Regras + contratos explicados (não só o diff). Origem: V3.3, findings
> FIND-20260817-104 e FIND-20260818-101. **Portal V6 não é superset — grep das âncoras antes.**
> Recordar: o helper de KPIs (`helpers.py`) **não é partilhado** — cada produto tem a sua cópia,
> por isso o V6 pode ter o mesmo anti-padrão de forma independente e tem de ser verificado, não
> assumido herdado.

---

## 1. "Fila de CPU" (ex-"processos em alarme") — HERDA VIA BD, sem código V6

**O que era o bug (V3.3 FIND-104, confirmado na BD viva):** o indicador que conta instâncias com
sessões `runnable` acima do threshold mostrava sempre **0**, em toda a frota, desde sempre. Causa: o
collector `collect_processes.py` gravava `s.status` de `sys.dm_exec_sessions` (valores
`running/sleeping/dormant`), mas a vista `KPI_MSSQL_PROCESSES_AGG_VIEW` conta
`Status = 'runnable'`/`'suspended'` — estados que **só existem** em `sys.dm_exec_requests`. Logo
`Runnable_Count`/`Suspended_Count` eram estruturalmente 0.

**Fix aplicado (V1, commit `7635f7c`):** na QUERY do collector,
`s.status AS [Status]` → `COALESCE(r.status, s.status) AS [Status]` (estado do request quando há
request activo; senão o da sessão). Sem DDL.

**Porque o V6 herda sem tocar em código:** o collector V1 (`WATCHERDB INTELLIGENCE V1/`) é **único
para toda a família** e alimenta a mesma `WatcherDB_Intelligence` que o V6 lê. Depois do
`Restart-Service WatcherDBCollector` + 1 ciclo (5–7 min), a `PROCESSES_AGG_VIEW` do V6 passa a ter
`Runnable_Count`/`Suspended_Count` reais **sem qualquer alteração no V6**.

**A verificar no V6 (senão não herda / mostra mal):**
1. O V6 tem cópia própria de `collect_processes.py`? Se tiver, **não herda** — aplicar o mesmo diff.
   ```powershell
   cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V6"
   Get-ChildItem -Recurse -Filter 'collect_processes.py'
   ```
2. O V6 tem cópia própria da `KPI_MSSQL_PROCESSES_AGG_VIEW` no seu canonical? A definição viva conta
   `runnable`/`suspended` e classifica CRITICAL>50 / WARNING>20. Confirmar que o canonical V6 bate com
   a viva (`Select-String -Path . -Pattern 'PROCESSES_AGG_VIEW' -Recurse`).
3. **Rótulo:** o V3.3 renomeou o card para **"Fila de CPU"** e reescreveu a ajuda (RUNNABLE = à espera
   de CPU/scheduler, distinto de % CPU e de SUSPENDED). Se o V6 tiver o mesmo card, propagar o texto
   (grep no portal V6 por `processes_alarm` / `processes-alarm` / "processos em alarme").
4. Semântica a levar junto: o número conta **instâncias** com `Runnable_Count > threshold` (default
   warning 20 / critical 50, editável em Settings → Thresholds), não processos. Um zero agora é
   verdadeiro (pouca fila), não um bug.

Achado colateral (higiene, baixo): a sproc legada `usp_Collect_Processes` no canonical V1 tinha o
mesmo bug e foi alinhada; confirmar se o V6 a referencia (não devia — não está agendada).

---

## 2. Filtro por ambiente dos KPIs — VERIFICAR NO V6 (código não partilhado)

**O que era o bug (V3.3 FIND-101):** no dashboard, ao filtrar por ambiente, vários cartões não
mudavam o valor — mostravam a frota inteira. Causa geral: o helper do dashboard deriva o nome do
breakdown a partir do campo do valor (`X_count` → `X_by_env`; `count` → `count_by_env`; senão
`campo_by_env`) e, quando essa chave **não existe** no payload, cai **silenciosamente** para o total
(`+sec[campo]`). Três sub-causas nos 6 cartões afectados:

| Cartão | Sub-causa | Fix |
|---|---|---|
| Backups **Full / Diff / Other falhou** | backend só tinha `failed_by_env` combinado | acrescentar `full_failed_by_env` / `diff_failed_by_env` / `other_failed_by_env` (acumular no loop de classificação com o `env_key` normalizado; expor + defaults no `except`) |
| **Filegroups** críticos/aviso | backend tinha o breakdown com **outro nome** (`critical_filegroups_by_env`) | alias `critical_items_total_by_env` / `warning_items_total_by_env` (= os mesmos dicts por-item) |
| **Serviços em baixo** | idem (`service_status.by_env`) | alias `down_by_env` |
| **Mirroring não saudável** | idem (`mirroring_status.by_env`; DET_VIEW só traz os não-saudáveis) | alias `unhealthy_by_env` |
| Integridade **Nunca validadas (P3) / CHECKDB>30 (P4)** | frontend usava `n(ig.pX_count)` fixo, nunca `ev()` — backend já tinha `p3_by_env`/`p4_by_env` desde 04/08 | frontend passa a `ev(ig,'p3_count')`/`ev(ig,'p4_count')` |

Extra: os cartões de discos usavam cor fixa (`C.crit`/`C.warn`) em vez de condicional — com filtro
mostravam "0" a vermelho; passou a `valor>0 ? crit : ok`.

**Contrato (a regra que evita reincidência):** para **cada** `ev(sec, 'campo')` do dashboard, a chave
`campo→by_env` derivada TEM de existir no payload; senão o filtro cai no total. O V3.3 ganhou um teste
de contrato estático (`tests/unit/test_kpi_env_breakdown_20260818.py`) que valida isto — vale a pena
o V6 ter o equivalente.

**A verificar no V6 (o helper NÃO é partilhado — o mesmo anti-padrão pode existir lá):**
1. Localizar o helper/agregador de KPIs do V6 (`api/routers/intelligence_kpis.py` próprio) e o
   dashboard avançado do portal (grep `count_by_env`, `_by_env`, `ev(`, `evN(`, `_advRow`).
2. Para cada `ev(sec,'campo')` do dashboard V6, confirmar que o backend expõe a chave `by_env`
   derivada. Onde falte:
   - **nome só diferente** → alias no backend (risco mínimo, chave nova, não mexe nas existentes);
   - **split em falta** (full/diff/other) → acumular por ambiente no loop com `env_key` normalizado;
   - **frontend `n()` fixo** → trocar por `ev()`.
3. Confirmar que o **modal** de drilldown filtra por `inst.Env` por linha (o V3.3 aceita múltiplos
   ambientes num Set; a inferência por nome é só fallback). Grep no portal V6 pelo bloco que aplica
   `window._kpiEnvFilter` ao modal.
4. Sincronização cards↔modais: no V3.3 o clique na barra "Por ambiente" (`kpiAdvToggleEnv` →
   `_kpiAdvFilter.env`) passou a escrever também `window._kpiEnvFilter` (que a modal lê) e o modal
   passou a aceitar `PRD,TST` (Set, não `===`). Verificar se o V6 tem os dois estados separados e o
   mesmo gap.

**Tier:** tudo Standard (dashboard KPIs core). Sem AI/ML. No V6 é core partilhado — sem risco de tier
creep, mas confirmar que nenhum rótulo novo insinua feature Pro.

---

## 3. Ordem sugerida no V6

1. Reiniciar `WatcherDBCollector` e confirmar `Runnable_Count`/`Suspended_Count` reais na BD (fila de
   CPU herda; só precisa disto se o V6 não tiver collector próprio).
2. Auditar o dashboard V6 com o contrato do ponto 2.2 (map `ev()`→`by_env`); aplicar aliases/splits.
3. Rótulo "Fila de CPU" + ajuda, se o card existir no V6.
4. Teste de contrato `by_env` no V6 (copiar o do V3.3, ajustar às chaves do V6).

## 4. Referências V3.3

- Findings: `findings-inbox.md` FIND-20260817-104 (fila de CPU), FIND-20260818-101 (filtro ambiente).
- Backend: `api/routers/intelligence/helpers.py` (aliases + split by_env); V1
  `scripts/collectors/collect_processes.py:33` (COALESCE).
- Frontend: `templates/watcherdb_portal.html` — `kpiAdvToggleEnv`/`_kpiSyncEnvFilter`, `ev()`/`evN()`,
  `_advRow` do bloco avançado, filtro do modal (envSet), rótulo/ajuda de `processes-alarm`.
- Teste: `tests/unit/test_kpi_env_breakdown_20260818.py`.
