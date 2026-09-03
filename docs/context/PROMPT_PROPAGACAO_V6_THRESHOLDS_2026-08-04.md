# PROMPT — Propagação V3.3 → V6 · Thresholds configuráveis (F1 + design F2/F3)

Para a sessão AI do V6. Origem: sessão V3.3 de 04/08. Decisão de tier do
owner (04/08): **F1 global = Std (já no V3.3); F2 scoped + F3 baseline =
Pro/V6**. A camada de dados é partilhada (BD `WatcherDB_Intelligence`),
por isso o V6 **herda a fundação** e só precisa de construir a parte Pro.
Regras: `v33-v6-propagation-rule`, `v6-portal-not-superset` (**grep
anchors no V6 primeiro** — a modal pode nem existir lá).

Commits V3.3 de referência: `3cb0cb0` (F1 backend+router+modal),
`faf3ab4` (DDL), `deeea61`/`843c5d6` (registry). Design completo:
`docs/context/DESIGN_THRESHOLDS_CLIENTE_2026-08-04.md`.

---

## 0. O que o V6 HERDA de graça (BD partilhada — zero trabalho)

- **Tabelas já criadas** pelo owner na Intelligence:
  `WDB_KPI_THRESHOLDS` (scope-ready: `Kpi_Type, Scope_Type, Scope_Value,
  Warning_Value, Critical_Value, Updated_By, Updated_At`, PK nas 3
  primeiras, CHECK em Scope_Type) e `WDB_KPI_THRESHOLDS_AUDIT`. DDL:
  `WATCHERDB INTELLIGENCE V1/database/CREATE_WDB_KPI_THRESHOLDS.sql`.
- **Convenção de Scope_Value:** `''` GLOBAL; `'PRD'` ENV; `'INSTANCE'`
  INSTANCE; `'INSTANCE\DATABASE'` DATABASE (par instância+base porque o
  mesmo nome de base existe em várias instâncias).
- Qualquer override que o V3.3 grave (GLOBAL) é lido pelo V6 e vice-versa
  — é a MESMA tabela.

## 1. F1 — replicar no backend V6 (Std-equivalente; o V6 tem tudo Std+Pro)

Ficheiros V3.3 a portar (grep anchors no V6 primeiro):
1. **`api/kpi_thresholds_registry.py`** — fonte única dos defaults (14
   KPIs, `value()`, `registry_as_list()`, `BACKUP_DELAY_THRESHOLDS`).
   Se o V6 já tem thresholds hardcoded espalhados, centralizar aqui
   primeiro (foi a Fase 0).
2. **`api/threshold_overrides.py`** — `resolve(kpi, level[, instance,
   env, database])` com precedência DATABASE>INSTANCE>ENV>GLOBAL>registry,
   cache TTL 60s, fallback total se a tabela estiver ausente/vazia.
   **A precedência de scope JÁ está aqui** — a F2 do V6 não a
   reimplementa, só a alimenta.
3. **`api/routers/kpi_thresholds.py`** — router `/api/v1/kpi-thresholds`
   (GET efectivo + POST/DELETE admin). No V3.3 o POST só aceita GLOBAL
   (Std); no V6 relaxa para aceitar `scope_type`/`scope_value` (F2).
4. **Integração:** trocar `from registry import value as _th` por
   `from threshold_overrides import resolve as _th` nos consumidores
   (tempdb/latência/locks/CPU/backup) + `refresh_cache()` no topo do
   build do dashboard. Byte-idêntico sem overrides (golden test
   `tests/test_kpi_thresholds_registry.py`).
5. **Modal "Thresholds em vigor"** (settings) — grep V6 por
   `thresholdsInfoContainer`/`loadThresholdsInfo`. Se existir o gémeo,
   portar a versão editável (admin edita Aviso/Crítico dos
   `configurable_f1`, Guardar/Repor, dot de override).

## 2. F2 — construir no V6 (Pro; a fundação já está)

Só falta a **parte Pro**, porque a leitura com precedência já existe:

1. **Router:** o POST aceita `scope_type` (ENV/INSTANCE/DATABASE) +
   `scope_value` além de GLOBAL. Validar Scope_Value pela convenção §0.
2. **Audit trail (requisito banking):** preencher
   `WDB_KPI_THRESHOLDS_AUDIT` em cada SET/DELETE com valores antigo→novo,
   Action, Changed_By, Changed_At (a tabela já existe; o V3.3 F1 só usa
   `Updated_By/At` na linha principal — o histórico completo é a F2).
3. **UI de scope:** na modal, escolher o âmbito de um override
   (Global / por Ambiente / por Instância / por Instância+Base) com
   dropdown alimentado pelas instâncias/bases conhecidas. Mostrar a
   cadeia de precedência efectiva ("este valor vem de: override de
   instância").
4. **Aplicação da precedência nos KPIs:** hoje `resolve()` aceita
   instance/env/database mas os call sites passam só o global. Para F2
   valer nos KPIs classificados em Python (tempdb, locks, backup), passar
   o contexto (instância/env) na classificação. KPIs cujo threshold vive
   no WHERE/view (latência) só suportam scope global sem refactor — lista
   fechada de "configurável por scope", como na F1.

## 3. F3 — baseline sugere thresholds (Pro; já desenhado)

O baseline engine (Wave V, `usp_compute_kpi_baseline` → `WDB_KPI_BASELINE`)
calcula o valor normal por métrica. F3 = na UI de override, mostrar a
sugestão do baseline ("normal observado: 72%; sugerir crítico a 85%?") que
o cliente ratifica → grava como override. NÃO auto-aplica. Depende do
baseline engine estar vivo (foi destrancado 04/08 por outra sessão;
`project_wave_v_s1_design_proposal`).

## 4. Validação V6

- Golden: sem linhas na tabela ⇒ dashboards byte-idênticos a hoje.
- F2: override de instância ganha ao global; audit regista a mudança.
- Restart do serviço V6 (código Python cacheado).
- Tier: F1 visível em Std-equivalente; F2/F3 gated a Pro no V6.
