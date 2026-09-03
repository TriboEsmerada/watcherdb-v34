# -*- coding: utf-8 -*-
"""Classificacao partilhada do KPI Transaction Logs (TLOG usage) — 2026-09-02.

Uma unica funcao pura, usada pelo CARD (helpers.collect_disk_and_tlog) e pelo
MODAL (intelligence_kpis kpi_type=transaction-logs*). Mesmo desenho do
backup_delayed_classes (council 01/09, R5): a logica vive num sitio so, o tile
e o painel nunca discordam. Pura = testavel
(tests/unit/test_tlog_usage_classes_20260902.py).

Porque existe (owner 2026-09-02): o modal "DB Transaction Logs" so devolvia
contagens por instancia — sem o NOME da base (regra "modais: nome, nao
numero"). A KPI_MSSQL_TLOG_USAGE_ACTIVE ja tem uma linha por base; faltava
le-la por base e classificar no backend com o registry (85/95 + overrides),
em vez de na AGG_VIEW (que classifica dentro da view e ignora overrides).

Severidade (semantica estrita da AGG_VIEW, paridade com a Fase 1.5 lote 3):
  Percent_Used > critical            -> CRITICAL
  warning < Percent_Used <= critical -> WARNING
  resto                              -> normal (nao sai nas listas)

Log_Backup_Age (2.a dimensao do modal — idade do ultimo backup de LOG):
  SIMPLE   recovery SIMPLE: log backup nao se aplica (neutro, nunca vermelho)
  UNKNOWN  recovery desconhecido E sem backup de log registado (neutro)
  NEVER    FULL/BULK_LOGGED sem NENHUM backup de log registado
  LATE     ultimo backup de log ha mais de log_late_hours (mesma chave do
           registry que o Backup Delayed usa para LOG — sem 6.a "verdade")
  OK       backup de log dentro do limiar

O lookup do ultimo backup de LOG e' AG-aware (TLOG_BASE_QUERY): o msdb e'
local a cada no', o backup de log de uma base AG costuma correr no
secundario, e o collector de TLOG so' escreve o no' onde a base esta' activa.
Sem isto, bases AG saudaveis apareceriam como NEVER (falso positivo) — o
mesmo bug que a Wave M.2 corrigiu no Backup Delayed.

Fase 2 (Wave separada, collector V1): log_reuse_wait_desc, VLFs, runway —
NAO existem na Intelligence hoje; nada aqui os inventa.
"""
from datetime import datetime, timedelta

from api.routers.intelligence.backup_delayed_classes import _norm_env, _parse_dt

_ENVS = ("PRD", "QLT", "TST", "Undefined")

# Uma linha por base, TODAS as bases (o tile precisa de Total_Databases/Normal
# por instancia — forma legada dos consumidores). Sem WHERE por threshold: a
# classificacao e' feita em Python com o registry. Joins normalizados
# (LTRIM/RTRIM/UPPER) como o Backup Delayed faz com INST_ENVS
# (intelligence_kpis.py ramo backup-delayed).
TLOG_BASE_QUERY = """
;WITH ag AS (
    SELECT DISTINCT AgName,
           LTRIM(RTRIM(UPPER(Instance)))   AS Instance_N,
           LTRIM(RTRIM(UPPER([Database]))) AS Database_N
    FROM {schema}.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
    WHERE AgName IS NOT NULL
),
lastlog AS (
    SELECT LTRIM(RTRIM(UPPER(b.Instance)))   AS Instance_N,
           LTRIM(RTRIM(UPPER(b.[Database]))) AS Database_N,
           MAX(b.Last_Backup_Date)           AS Last_Log_Backup_Date
    FROM {schema}.KPI_MSSQL_BACKUPS_STG b WITH (NOLOCK)
    WHERE b.Backup_Type IN ('L', 'LOG')
    GROUP BY LTRIM(RTRIM(UPPER(b.Instance))), LTRIM(RTRIM(UPPER(b.[Database])))
),
lastlog_ag AS (
    -- AG-aware: o backup de log mais recente em QUALQUER no' do AG
    SELECT a.AgName, l.Database_N, MAX(l.Last_Log_Backup_Date) AS Last_Log_Backup_Date
    FROM lastlog l
    JOIN ag a ON a.Instance_N = l.Instance_N AND a.Database_N = l.Database_N
    GROUP BY a.AgName, l.Database_N
)
SELECT t.Instance, t.[Database], ISNULL(e.Env, 'Undefined') AS Env,
       t.Percent_Used, t.Used_MB, t.Current_MB, t.Max_Available_MB, t.Update_TS,
       ds.Recovery_Model,
       COALESCE(lag.Last_Log_Backup_Date, ll.Last_Log_Backup_Date) AS Last_Log_Backup_Date
FROM {schema}.KPI_MSSQL_TLOG_USAGE_ACTIVE t WITH (NOLOCK)
LEFT JOIN {schema}.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
       ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(t.Instance)))
LEFT JOIN {schema}.KPI_MSSQL_DB_SETTINGS_STG ds WITH (NOLOCK)
       ON LTRIM(RTRIM(UPPER(ds.Instance))) = LTRIM(RTRIM(UPPER(t.Instance)))
      AND LTRIM(RTRIM(UPPER(ds.Database_Name))) = LTRIM(RTRIM(UPPER(t.[Database])))
LEFT JOIN ag a
       ON a.Instance_N = LTRIM(RTRIM(UPPER(t.Instance)))
      AND a.Database_N = LTRIM(RTRIM(UPPER(t.[Database])))
LEFT JOIN lastlog_ag lag
       ON lag.AgName = a.AgName AND lag.Database_N = LTRIM(RTRIM(UPPER(t.[Database])))
LEFT JOIN lastlog ll
       ON ll.Instance_N = LTRIM(RTRIM(UPPER(t.Instance)))
      AND ll.Database_N = LTRIM(RTRIM(UPPER(t.[Database])))
"""


def _to_float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _log_backup_age(recovery_model, hours_since_log_backup, log_late_hours):
    rm = (recovery_model or "").strip().upper()
    if rm == "SIMPLE":
        return "SIMPLE"
    if hours_since_log_backup is None:
        # sem registo de backup de log: so' e' "NEVER" quando sabemos que o
        # recovery model exige log backup; sem recovery model = neutro
        return "NEVER" if rm else "UNKNOWN"
    if log_late_hours is not None and hours_since_log_backup > float(log_late_hours):
        return "LATE"
    return "OK"


def classify_tlog(rows, thresholds, now=None, fresh_minutes=1440, log_late_hours=None):
    """Classifica as linhas da TLOG_BASE_QUERY (uma por base).

    rows: dicts com Instance/[Database]/Env/Percent_Used/Used_MB/Current_MB/
        Max_Available_MB/Update_TS/Recovery_Model/Last_Log_Backup_Date.
    thresholds: {'warning': 85, 'critical': 95} (registry tlog_usage + override).
    fresh_minutes: janela de frescura por Update_TS (fail-open: linha SEM a
        coluna passa — mesmo criterio de helpers._fresh_rows do card).
    log_late_hours: limiar de "backup de log atrasado" (registry
        backup_delay_log.warning). None = nunca marca LATE.

    Devolve dict com:
      critical / warning        listas de bases anotadas (Severity, Base_Key,
                                Last_Check, Hours_Since_Log_Backup,
                                Log_Backup_Age, Threshold_*, Instance_Severity)
                                ordenadas por Percent_Used DESC
      per_instance              forma LEGADA por instancia (Instance, Env,
                                Total_Databases, Critical, Warning, Normal,
                                Last_Check) — igual a' agregacao SQL antiga,
                                para o tile e consumidores antigos
      bases_*_count / by_env    contagens por BASE (cabecalho do modal)
      reconciliation            parcelas somam ao total (persona R5)
    """
    now = now or datetime.now()
    cutoff = now - timedelta(minutes=fresh_minutes)
    warn = float(thresholds["warning"])
    crit = float(thresholds["critical"])

    critical, warning = [], []
    per_inst = {}
    inst_worst = {}
    rows_fresh = normal = 0

    for row in rows or []:
        has_ts = "Update_TS" in row
        upd = _parse_dt(row.get("Update_TS")) if has_ts else None
        if has_ts and (upd is None or upd < cutoff):
            continue
        rows_fresh += 1

        env_key = _norm_env(row)  # normaliza row['Env'] in place (infere do nome)
        inst = (row.get("Instance") or "").strip()
        db = row.get("Database") or ""
        pct = _to_float(row.get("Percent_Used")) or 0.0

        agg = per_inst.setdefault((inst, row["Env"]), {
            "Instance": inst, "Env": row["Env"], "Total_Databases": 0,
            "Critical": 0, "Warning": 0, "Normal": 0, "Last_Check": None,
        })
        agg["Total_Databases"] += 1
        if upd is not None and (agg["Last_Check"] is None or upd > agg["Last_Check"]):
            agg["Last_Check"] = upd

        if pct > crit:
            sev = "CRITICAL"
            agg["Critical"] += 1
        elif pct > warn:
            sev = "WARNING"
            agg["Warning"] += 1
        else:
            agg["Normal"] += 1
            normal += 1
            continue

        last_log = _parse_dt(row.get("Last_Log_Backup_Date"))
        hours = None
        if last_log is not None:
            hours = round((now - last_log).total_seconds() / 3600.0, 1)
            if hours < 0:
                hours = 0.0

        row["Severity"] = sev
        row["Base_Key"] = f"{inst.upper()}|{str(db).upper()}"
        # o card generico do portal le Last_Check|last_check|update_ts — nunca Update_TS
        row["Last_Check"] = row.get("Update_TS")
        row["Hours_Since_Log_Backup"] = hours
        row["Log_Backup_Age"] = _log_backup_age(row.get("Recovery_Model"), hours, log_late_hours)
        row["Threshold_Warning"] = warn
        row["Threshold_Critical"] = crit
        row["_env_key"] = env_key

        if sev == "CRITICAL":
            critical.append(row)
            inst_worst[inst] = "CRITICAL"
        else:
            warning.append(row)
            inst_worst.setdefault(inst, "WARNING")

    for row in critical + warning:
        row["Instance_Severity"] = inst_worst.get(row.get("Instance", "").strip(), row["Severity"])

    def _sort_key(r):
        return (-(_to_float(r.get("Percent_Used")) or 0.0), r.get("Instance") or "", str(r.get("Database") or ""))

    critical.sort(key=_sort_key)
    warning.sort(key=_sort_key)

    def _by_env(lst):
        acc = {e: 0 for e in _ENVS}
        for r in lst:
            acc[r.pop("_env_key", "Undefined")] += 1
        return acc

    crit_by_env = _by_env(critical)
    warn_by_env = _by_env(warning)

    per_instance = sorted(per_inst.values(), key=lambda a: (a["Instance"], a["Env"]))
    inst_crit = sum(1 for a in per_instance if a["Critical"] > 0)
    inst_warn_only = sum(1 for a in per_instance if a["Warning"] > 0 and a["Critical"] == 0)

    return {
        "critical": critical,
        "warning": warning,
        "per_instance": per_instance,
        "bases_critical_count": len(critical),
        "bases_warning_count": len(warning),
        "bases_critical_by_env": crit_by_env,
        "bases_warning_by_env": warn_by_env,
        "reconciliation": {
            "rows_fresh": rows_fresh,
            "critical": len(critical),
            "warning": len(warning),
            "normal": normal,
            "instances_critical": inst_crit,
            "instances_warning_only": inst_warn_only,
        },
    }
