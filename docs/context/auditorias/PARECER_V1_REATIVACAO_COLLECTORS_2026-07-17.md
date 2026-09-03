# Parecer v1-intel-specialist — Reactivação de coletas órfãs (2026-07-17)

> Dispatch do orquestrador (GO owner) após varredura de frescura da WatcherDB_Intelligence
> revelar collectors mortos desde a migração do WatcherDBCollector (~13/05).
> Veredicto: **GO-com-coordenação, SEM VETO.**

## Achado-chave (causa raiz da causa raiz)

Este exacto cenário **já aconteceu e já foi corrigido antes**: CHANGELOG V1 `[2.17.0] - 2026-04-14`
("Varredura de frescura de coletas — KPIs órfãos reactivados") adicionou ao config.yaml as entries
`collect_mirroring_{PRD,QA,TST}` e `collect_errorlog_{QA,TST}` — e o próprio fix avisava:
*"Config.yaml untracked no git: mudanças ao config não têm trilho de auditoria."*
A migração de 13/05 **reverteu silenciosamente** esses fixes (deploy de config antigo, sem histórico git).
É a mesma regressão a repetir-se, prevista pelo autor do fix anterior.

## Veredictos por frente

| Frente | Veredicto | Acção |
|---|---|---|
| **Mirroring PRD/QA/TST** | GO directo (config-only; schema já validado em produção 04-14) | Colar blocos yaml (5/5/10 min), Restart-Service, query de validação; corrigir run_collections.py:130 (sai de DEPRECATED_KPIS, entra em KPI_TO_COLLECTOR+COLLECTORS) |
| **Deadlocks** | GO-com-coordenação — reactivar TAL-E-QUAL reintroduz o problema de performance (gate actual faz CAST XML do ring buffer inteiro TODO ciclo). Recomenda **redesign two-tier counter-gated** (DMV counter ~O(1) por ciclo; XML só quando delta>0). State in-memory viável (service.py:343 — 1 instância por classe, reutilizada). Exige review de código pré-deploy + agendar usp_Purge_Deadlocks (existe mas NUNCA foi agendado) | Decisão owner: (A) redesign [recomendado] / (B) ligar como está [não recomendado] / (C) remover tile |
| **AlwaysOn TST** | NÃO É BUG — AG do TST descomissionado (servers.json: SQLHDSTST051/052 `[DESCONTINUADO]`, enabled:false; collector corre mas processa 0 servidores) | Opcional: limpeza de inventário |
| **Errorlog QA/TST** | NÃO foi decisão deliberada — mesma regressão do mirroring (fix 04-14 perdido em 13/05) | Colar blocos yaml (QA 5 min, TST 10 min) no mesmo restart do mirroring |

## Freshness Guard (design)

- V3.3 `helpers.py:113-119` (`FRESHNESS_WINDOWS`/`is_data_fresh`) valida frescura POR LINHA — blind spot:
  collector morto ⇒ 0 linhas ⇒ nada para avaliar ⇒ tile "0 problemas" falso. `mirroring` e `deadlocks`
  nem têm entry no dict.
- **Componente A (primeiro):** view `KPI_MSSQL_COLLECTION_FRESHNESS_VIEW` (via KPI_STG_ACTIVE_TABLE.Updated_At)
  + tabela `WDB_COLLECTION_SCHEDULE_META` (cadência esperada exportada do config.yaml no arranque do serviço);
  V3.3 marca tile STALE quando Minutes_Since_Swap > 3× intervalo (multiplicador já usado no alerting).
  DDL concreto exige novo parecer (padrão WDB_KPI_BASELINE).
- **Componente B (fase 2):** detector de silêncio no próprio serviço V1 (health check APScheduler: tasks com
  next_run_time ultrapassado sem sucesso).

## Custos deadlocks quantificados (pergunta do owner)

- Design actual: 1 query XML pesada (CAST ring buffer + XQuery) POR ciclo POR instância, mesmo sem deadlocks.
- Design two-tier: 1 leitura DMV ~O(1) por ciclo (comparável ao collect_perf_counters que já corre sem impacto);
  XML só quando o contador sobe (evento raro). Estritamente melhor, sem perda de detecção.

## Proactive findings

1. **HIGH — config.yaml fora do git** (causa raiz das regressões repetidas). Mover para version control
   antes da próxima migração de infra.
2. MEDIUM — dois MERGE divergentes para deadlocks (usp_Deadlock_Upsert com GRANT vs Python raw pyodbc);
   consolidar no sproc se reactivar.
3. MEDIUM — FRESHNESS_WINDOWS sem entries mirroring/deadlocks; primeiros beneficiários do Componente A.

## Blocos executáveis (D1 — mirroring + errorlog, GO directo)

Identidades: edição config + Restart-Service = admin/conta do serviço (owner); validações SELECT = sql_monitoring.

### 1) Acrescentar ao `WATCHERDB INTELLIGENCE V1/services/collector_service/config.yaml`

```yaml
  # ===========================================================================
  # CATEGORIA: MIRRORING - Database Mirroring Status (reaplicacao do fix 2.17.0/04-14,
  # perdido na migracao 13/05 — config.yaml sem git)
  # ===========================================================================

  - name: "collect_mirroring_PRD"
    class: "CollectMirroringPRD"
    module: "collectors.collect_mirroring_status"
    interval_minutes: 5
    enabled: true
    executor: "default"
    environment: "PRD"
    description: "Coleta status de Database Mirroring (PRD)"
    tables:
      - "KPI_MSSQL_MIRRORING_STATUS_STG"

  - name: "collect_mirroring_QA"
    class: "CollectMirroringQA"
    module: "collectors.collect_mirroring_status"
    interval_minutes: 5
    enabled: true
    executor: "default"
    environment: "QA"
    description: "Coleta status de Database Mirroring (QA)"
    tables:
      - "KPI_MSSQL_MIRRORING_STATUS_STG"

  - name: "collect_mirroring_TST"
    class: "CollectMirroringTST"
    module: "collectors.collect_mirroring_status"
    interval_minutes: 10
    enabled: true
    executor: "default"
    environment: "TST"
    description: "Coleta status de Database Mirroring (TST)"
    tables:
      - "KPI_MSSQL_MIRRORING_STATUS_STG"

  - name: "collect_errorlog_QA"
    class: "CollectErrorLogQA"
    module: "collectors.collect_errorlog"
    interval_minutes: 5
    enabled: true
    executor: "default"
    environment: "QA"
    description: "Coleta SQL Server Error Log (QA)"
    tables:
      - "KPI_MSSQL_ERRORLOG_STG"

  - name: "collect_errorlog_TST"
    class: "CollectErrorLogTST"
    module: "collectors.collect_errorlog"
    interval_minutes: 10
    enabled: true
    executor: "default"
    environment: "TST"
    description: "Coleta SQL Server Error Log (TST)"
    tables:
      - "KPI_MSSQL_ERRORLOG_STG"
```

### 2) Validar YAML + restart + verificar

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1"
python -c "import yaml; yaml.safe_load(open('services/collector_service/config.yaml', encoding='utf-8')); print('YAML OK')"
# Restart interrompe TODAS as coletas por segundos — fazer fora de janela critica
Restart-Service -Name "WatcherDB_Intelligence_Collector"
```

Validação (SSMS, sql_monitoring, na WatcherDB_Intelligence, ~10 min após restart):

```sql
SELECT TOP 5 Instance, [Database], Mirroring_State, Update_TS
FROM dbo.KPI_MSSQL_MIRRORING_STATUS_ACTIVE
WHERE Env = 'PRD'
ORDER BY Update_TS DESC;
-- Esperado: Update_TS de hoje e SharePoint2010_Config_PROD com SYNCHRONIZING
-- (o tile Mirroring do portal deve passar de 0 para >=1)
```

### 3) `scripts/run_collections.py` — corrigir classificação

- Remover `"KPI_MSSQL_MIRRORING_STATUS_STG"` de `DEPRECATED_KPIS` (linha ~130, comentário errado
  "ambiente sem mirroring activo").
- Acrescentar ao dict `KPI_TO_COLLECTOR`: `"KPI_MSSQL_MIRRORING_STATUS_STG": "mirroring",`
- Acrescentar ao registry `COLLECTORS`: `"mirroring": ("collectors.collect_mirroring_status", "CollectMirroringPRD", "CollectMirroringQA", "CollectMirroringTST"),`
