# PROMPT — Propagação V3.3 → V6 · Lote 2026-08-03

Para a sessão AI do V6. Origem: sessão V3.3 de 03/08, commits V3.3
`514aaa0` + `050f5f2` + `268114d` + `71707ae` + `b26a8c5`, V1 `59656a0`
+ `baa4cb3` (branch `wave-b-indexacao-dmv`, monorepo projetosPython).
Regras aplicáveis: `v33-v6-propagation-rule` (fixes propagam) e
`v6-portal-not-superset` (**grep anchors no V6 primeiro**). Findings de
suporte: `FIND-20260803-101` (tempdb, fixed), `FIND-20260803-102` (disk
latency, fixed em V1 `baa4cb3` — V6 herda via BD), `FIND-20260803-103/104`
(abertos, contexto).

---

## 0. Contrato dos dados — ler ANTES de aplicar

1. **`KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW` expõe `Percent_Used`** (e
   `Total_Size_MB`/`Used_MB`/`Free_MB`). A coluna `Usage_Percent` NUNCA
   existiu — qualquer código que a leia está a processar zero linhas em
   silêncio. Isto vale para TODOS os consumidores (dashboard, modais,
   relatórios, NLU/AI que gere SQL sobre esta view).
2. **Os dados do tempdb só ficam reais depois do próximo ciclo do
   colector V1 corrigido** (`59656a0`). Antes disso a view continua com
   `Percent_Used = 0.00` em todas as instâncias — não interpretar como
   "está tudo bem" nem como regressão do fix V6.
3. **Disk latency foi corrigida no colector V1** (`baa4cb3`, FIND-102):
   `KPI_OS_DISK_PERF_STG` passa a ter valores reais (latência, IOPS,
   disk time, queue) após o restart do serviço `WatcherDBCollector` —
   V6 herda pela BD, sem código. MAS: dados anteriores a 03/08 são
   artefactos (zeros + spikes falsos 4000–58000 ms); qualquer baseline/
   AI/capacity V6 que use o HIST tem de cortar em `Update_TS >=
   '2026-08-03'`. **Condição do gate:** validar
   `WATCHERDB_V6/data/eval/golden_self_knowledge_v1.jsonl` (Q037) e
   `tests/test_sprint41_q037_disk_latency_smoke.py` — se o golden
   codifica "0.00" como resposta correta, o teste passa hoje por estar
   a validar o bug; corrigir fixture no mesmo lote.

## 1. BD partilhada — nada a executar (V6 herda)

Sem DDL neste lote (o fix do colector é Python; schema intacto,
canonical `INSTALACAO_COMPLETA_UNIFICADA.sql` não muda). O V6 herda os
dados corrigidos do tempdb automaticamente após o próximo ciclo do
colector. Ação V6: nenhuma na BD; apenas validar §3.

## 2. Backend V6 — bugfix Percent_Used (aplicar)

Anchor confirmado: `WATCHERDB_V6/api/routers/intelligence_kpis.py`
(monólito; V6 NÃO tem `api/routers/intelligence/helpers.py` — o fix
V3.3 em dois ficheiros colapsa num só no V6). Grep por `Usage_Percent`
e aplicar o mesmo padrão do commit `050f5f2`:

- Ler `Percent_Used` primeiro (fallbacks: `PERCENT_USED`,
  `percent_used`, depois legado `Usage_Percent`...).
- Mapear `Total_Size_MB`/1024 → `file_size_gb` e `Free_MB`/1024 →
  `disk_free_gb` (os nomes `File_Size_GB`/`Free_GB` não existem na view).
- Verificar também `sql_queries.py` (grep apanhou referência tempdb) e
  `oracle_kpis.py:501,1531` — este último referencia a view MSSQL; se
  gerar SQL com `Usage_Percent`, corrigir.

## 3. Portal V6 — remoções visuais (aplicar, anchors confirmados)

`WATCHERDB_V6/templates/watcherdb_portal.html` tem os MESMOS blocos:

- Linha ~33292: hero `100%` do card Disponibilidade
  (`<div class="kpiadv-hero">...availPct...` ) → remover, manter
  `<div class="kpiadv-list">`.
- Linha ~33300: rodapé `_advFoot([{ n: totI ... 'Instancias' ... 'OK'
  ... 'OFF' ...}])` → remover argumento (fechar com `` `</div>`)); ``).
- Linha ~33310: hero `Discos criticos` do card Espaço em Disco →
  remover, manter `<div class="kpiadv-list">`.

Espelhar os comentários de decisão (owner 2026-08-03) do commit
`514aaa0`. CSS `.kpiadv-hero/.kpiadv-big` pode ficar (usado se outro
card tiver hero; remoção é opcional e não faz parte deste lote).

### 3b. Dimensionamento inteligente do dashboard (commits `268114d` + `71707ae` + `b26a8c5`)

Problema origem: a 1920×1200 @100% o dashboard não cabia (owner baixava
o Windows para 90%); em ecrãs menores o Resumo Executivo quebrava em 2
linhas e os cards ficavam sob a dobra. Três camadas, TODAS a propagar
se o V6 tiver o mesmo dashboard avançado (tem — mesmos anchors CSS):

1. `clamp()` fluido nos tamanhos verticais de `.rep-*` e `.kpiadv-*`
   (`268114d`) + `minmax` do `.rep-exec-grid` 170→148px (5 métricas
   numa linha) + título/paddings do container em clamp (`71707ae`).
2. `@media (max-height:1180px)` com densidade compacta determinística
   (`71707ae`) — ver bloco completo no CSS V3.3, copiar verbatim.
3. **Auto-fit por medição** (`b26a8c5`): função `_kpiFitToViewport()`
   + hook no fim de `applyKpiLayout()` + listener resize (debounce
   150ms). O container mede `scrollHeight` vs altura visível e aplica
   `zoom` calculado com piso 0.72. Atenção V6: confirmar o id do
   container (`kpi-dashboard-container`) e o nome da função de render
   equivalente antes de colar.

### 3c. Auditoria rótulo-vs-unidade (commits da tarde de 03/08)

O dashboard V6 tem as mesmas rows — aplicar os mesmos 8 rótulos honestos
(grep pelos antigos): `Servicos em baixo`→`Instancias c/ servicos em
baixo`; `Processos em alarme`→`Instancias c/ processos em alarme`;
`Criticos`/`Avisos` (Espaço em Disco)→`Instancias c/ discos criticos/em
aviso`; `Latencia critica/aviso`→`Drives c/ latencia critica/em aviso`
(2 cards); `AlwaysOn nao saudavel`→`Instancias c/ AlwaysOn nao
saudavel`; `Mirroring nao saudavel`→`DBs c/ mirroring nao saudavel`;
`Transaction log critico`→`Instancias c/ t-log critico`; `Sessoes
bloqueadas`→`Instancias c/ sessoes bloqueadas`. Backend: em
`collect_deadlocks`, `count_by_env` passa a somar deadlocks
(`dl_by_env`) em vez de contar instâncias — sem isto o card "Deadlocks
24h" troca de unidade quando um filtro de ambiente está activo; mapa de
instâncias fica em `instances_by_env`.

### 3d. FIND-20260803-105 — Mirroring DET_VIEW partida (BD partilhada)

`KPI_MSSQL_MIRRORING_STATUS_DET_VIEW` está com binding error desde a
Wave C (31/07): seleciona `Env` que a `_ACTIVE` regenerada já não expõe.
"Mirroring não saudável" = 0 estrutural desde então (backend engole o
erro). O owner aplica o `CREATE OR ALTER` (bloco entregue na sessão
V3.3; canonical `SECTION16_MIRRORING_STATUS.sql` 16.5 já sincronizado) —
V6 herda pela BD. Ação V6: nada na BD; validar que o KPI mirroring volta
a contar após o owner aplicar. AVISO: a parte 16.6 do SECTION16
(DB_AVAILABILITY cross-ref) está desatualizada e partiria a view viva se
executada — não correr sem reconciliar com a Section 15 do canonical.

### 3e. FIND-20260803-107 — modal Alterar Senha sem campo Senha Actual

O backend `/api/auth/change-password` exige `current_password`; a modal
`changePasswordModal` do V3.3 só tinha Nova/Confirmar e enviava só
`new_password` → "Password actual obrigatoria" sempre, para todos. Fix:
campo `cpwdCurrent` (autocomplete=current-password, focus inicial),
validação client-side e payload `{current_password, new_password}`.
Grep V6 por `changePasswordModal`/`cpwdNew` — o auth do portal V3.3 tem
comentário "igual ao V6", a modal partida deve existir lá também.

## 4. Canonical e documentação — o que mudou, onde, e porquê (LER pela AI do V6)

Este lote NÃO tem DDL novo no `INSTALACAO_COMPLETA_UNIFICADA.sql` (o
schema das tabelas não mudou). As mudanças de conhecimento que a AI do
V6 precisa de absorver são estas:

1. **`WATCHERDB INTELLIGENCE V1/database/SECTION16_MIRRORING_STATUS.sql`
   (commit `6dd07b1`)** — parte 16.5 reescrita: a
   `KPI_MSSQL_MIRRORING_STATUS_DET_VIEW` deriva `Env` via `LEFT JOIN
   KPI_MSSQL_INST_ENVS` (o padrão das outras DET_VIEWs), porque as
   `_ACTIVE` pós-Wave C fazem `SELECT d.*` das físicas por ambiente e
   **não expõem Env**. REGRA GERAL que fica: *nenhuma view pode assumir
   que uma `_ACTIVE` tem colunas além das da tabela física; Env vem
   sempre de `KPI_MSSQL_INST_ENVS`*. Aplicado na BD viva pelo owner a
   03/08 ~15h (validado: 110 DBs espelhadas, todas SYNCHRONIZED).
2. **Aviso na parte 16.6 do mesmo ficheiro**: a variante da
   `DB_AVAILABILITY_DET_VIEW` ali contida está desatualizada face à
   Section 15 do canonical e referencia colunas inexistentes
   (`a.Env`, `a.Has_Mirroring`) — executá-la substituiria uma view
   funcional por uma partida. Se o V6 tiver cópia deste script, herdar
   o aviso.
3. **Colectores V1 (BD partilhada — V6 herda dados, não precisa de
   código):** `collect_tempdb_usage.py` (`59656a0`, DMV
   tempdb-scoped) e `os_performance.py` (`baa4cb3`, 2 amostras WMI
   raw). Contratos de leitura relevantes para qualquer código/AI V6:
   `Percent_Used` é o nome real na view de tempdb (`Usage_Percent`
   nunca existiu); dados de disk perf anteriores a 03/08 são artefactos.
4. **Contrato do payload de deadlocks (backend):** `count` e
   `count_by_env` = soma de DEADLOCKS; `instances_by_env` = instâncias
   (novo). Qualquer consumidor V6 que use `count_by_env` como contagem
   de instâncias tem de migrar para `instances_by_env`.
5. **Findings de referência:** FIND-20260803-101 (tempdb, fixed),
   -102 (latência, fixed), -105 (mirroring view, fixed 03/08), -103/-104/
   -106 (abertos) — `WATCHERDB_V3.3/findings-inbox.md`.
6. **Varredura de saúde a repetir no V6 se tiver BD própria/espelho:**
   testar TODAS as views com `SELECT TOP 0 *` (não só as `_ACTIVE`) —
   foi assim que o binding partido do mirroring apareceu; o sweep §0.4
   da Wave C não o apanhava.

## 5. Validação V6 (após aplicar + próximo ciclo do colector)

```sql
-- Na Intelligence: valores reais esperados (max > 0 após ciclo)
SELECT COUNT(*) AS rows_, MAX(Percent_Used) AS max_pct
FROM dbo.KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW WITH (NOLOCK);
```

- Browser: cards Disponibilidade/Espaço em Disco sem heros/rodapé;
  card Saúde do Disco com TempDB a reagir (usar instância com uso real,
  ex. SQLMDMDEV05 ~39% em DEV/TST).
- Restart do serviço V6 obrigatório (código Python cacheado em RAM).
