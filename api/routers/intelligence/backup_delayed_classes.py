# -*- coding: utf-8 -*-
"""Classificacao partilhada do Backup Delayed — council 2026-09-01 (R1-R4).

Uma unica funcao pura, usada pelo CARD (helpers.collect_backup_status) e pelo
MODAL (intelligence_kpis kpi_type=backup-delayed). R5 do council: a logica tem
de viver num sitio so — o bug de coerencia tile-vs-painel de 31/08 nao se
repete. Pura = testavel (tests/unit/test_backup_delayed_classes_20260901.py).

Classes (rotulos de UI definidos pela customer-success-persona):
  actionable            delay genuino — E' o que conta no executivo, DEDUPE
                        por base (R1/FIND-101: bases, nao linhas)
  chain_reset           DIFF coberto por um FULL mais recente E fresco —
                        "Cadeia reiniciada, FULL mais recente ja cobre".
                        Perdao LIMITADO (precedente f15bfb8 18/08): expira
                        quando o FULL passa o proprio warning. M1: 88% do
                        cohort e' isto (DIFF <=3d).
  diff_schedule_stopped DIFF parado ha mais de DIFF_STOPPED_HOURS com FULL
                        fresco — o schedule DIFF esta partido/abandonado
                        (challenger + M1: 33 casos reais tipo TAON). Banda
                        propria VISIVEL, nunca engolida pelo perdao.
  ag_system_gap         master/model/msdb de no' AlwaysOn — exposicao de
                        politica por-no' (R3: NUNCA filtrado em silencio;
                        contador visivel; rota para o kpi backup-ag-system-gap
                        que existe desde a Wave M.4.a). DBA_*/TLS_* ficam FORA
                        (challenger: sao user DBs).

Chave de base (condicao v1-intel): linhas AG_CONSOLIDATED correlacionam por
(AgName, Database) — o Instance dessas linhas e' o representante POR TIPO
("no' com o backup mais recente daquele tipo") e diverge entre FULL e DIFF
da mesma base pos-failover. ag_map vem de KPI_MSSQL_ALWAYSON_STATUS_STG
(padrao de query ja existente; fail-open: sem mapa, cai para (Instance,
Database) — comportamento identico ao antigo, nunca pior).
"""
from datetime import datetime, timedelta

SYSTEM_DBS = {"master", "model", "msdb"}
DIFF_STOPPED_HOURS = 168  # 7d: acima disto, "chain reset" e' schedule parado

_ENVS = ("PRD", "QLT", "TST", "Undefined")


def _parse_dt(v):
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


def _norm_type(bt):
    bt = (bt or "").upper()
    if bt in ("FULL", "D"):
        return "FULL"
    if bt in ("DIFF", "I"):
        return "DIFF"
    if bt in ("LOG", "L"):
        return "LOG"
    return None


def _norm_env(row):
    env = row.get("Env", "Undefined") or "Undefined"
    if env == "Undefined":
        inst = (row.get("Instance", "") or "").upper()
        if "PRD" in inst or "PROD" in inst:
            env = "PRD"
        elif "QLT" in inst or "QUAL" in inst:
            env = "QLT"
        elif "TST" in inst or "TEST" in inst or "DEV" in inst:
            env = "TST"
    row["Env"] = env
    up = env.upper()
    return up if up in ("PRD", "QLT", "TST") else "Undefined"


def classify_delayed(backup_data, thresholds, ag_map=None, now=None):
    """Classifica as linhas da vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE.

    backup_data: rows (dict) com Instance/[Database]/Backup_Type/
        Hours_Since_Backup/Last_Backup_Date/Update_TS/Env.
    thresholds: {'FULL': {'warning_h','critical_h'}, 'DIFF': ..., 'LOG': ...}
    ag_map: {(INSTANCE_UPPER, DATABASE_UPPER): AgName} — opcional (fail-open).

    Anota cada linha classificada com Delay_Class, Delayed_Severity, Base_Key
    e (Wave R+12) Expected_Backup_Date/Gap_Hours_Past_Threshold. Devolve dict
    com as listas por classe, contagens POR BASE (R1) e reconciliacao (R5).
    """
    now = now or datetime.now()
    cutoff_48h = now - timedelta(hours=48)
    ag_map = ag_map or {}
    ag_instances = {k[0] for k in ag_map}
    # C4 (gate sql-deep 01/09): o corte "schedule parado" assume warning(DIFF)
    # < 168h; se um cliente configurar DIFF semanal, o guard evita que todo o
    # chain-reset legitimo salte directo para "parado".
    diff_stopped_h = max(DIFF_STOPPED_HOURS, thresholds["DIFF"]["warning_h"] + 48)

    def base_key(row):
        inst = (row.get("Instance", "") or "").upper()
        db = (row.get("Database", "") or "").upper()
        ag = ag_map.get((inst, db))
        return ("AG:" + str(ag), db) if ag else (inst, db)

    # Pre-scan: FULL mais recente por base (TODAS as linhas, incluindo
    # saudaveis — o perdao precisa do FULL mesmo quando ele nao alarma).
    full_info = {}
    for row in backup_data:
        if _norm_type(row.get("Backup_Type")) != "FULL":
            continue
        dt = _parse_dt(row.get("Last_Backup_Date"))
        if dt is None:
            continue
        k = base_key(row)
        hours = row.get("Hours_Since_Backup", 0) or 0
        cur = full_info.get(k)
        if cur is None or dt > cur[0]:
            full_info[k] = (dt, hours)

    out = {
        "actionable_critical": [],
        "actionable_warning": [],
        "chain_reset": [],
        "diff_schedule_stopped": [],
        "ag_system_gap": [],
        "delayed_by_type": {
            "FULL_warning": 0, "FULL_critical": 0,
            "DIFF_warning": 0, "DIFF_critical": 0,
            "LOG_warning": 0, "LOG_critical": 0,
        },
        "rows_past_threshold": 0,
    }
    base_worst = {}  # base_key -> (sev, env_key); sev: critical > warning

    for row in backup_data:
        type_norm = _norm_type(row.get("Backup_Type"))
        if type_norm is None:
            continue
        t = thresholds[type_norm]
        # C1 (gate sql-deep 01/09): NULL hours era lido como 0 = saudavel —
        # verde silencioso que viola a invariante RPO. Fail-closed: derivar da
        # Last_Backup_Date; sem data nenhuma = NUNCA saudavel.
        hours = row.get("Hours_Since_Backup")
        if hours is None:
            _lbd = _parse_dt(row.get("Last_Backup_Date"))
            if _lbd is not None:
                hours = (now - _lbd).total_seconds() / 3600.0
            else:
                hours = float("inf")
            row["Hours_Since_Backup"] = hours if hours != float("inf") else None
        if hours <= t["warning_h"]:
            continue  # abaixo do warning: saudavel

        # Janela 48h frescura collector (fix isoformat FIND-20260513-101)
        upd = _parse_dt(row.get("Update_TS"))
        if upd is None or upd < cutoff_48h:
            continue

        out["rows_past_threshold"] += 1
        env_key = _norm_env(row)
        k = base_key(row)
        row["Base_Key"] = "|".join(k)

        # Wave R+12 enrich (UX do card/modal)
        last_parsed = _parse_dt(row.get("Last_Backup_Date"))
        if last_parsed is not None:
            row["Expected_Backup_Date"] = (last_parsed + timedelta(hours=t["warning_h"])).isoformat()
        # hours pode ser inf (C1: sem data nenhuma) — gap fica None = "desconhecido"
        row["Gap_Hours_Past_Threshold"] = (
            max(0, int(hours - t["warning_h"])) if hours != float("inf") else None)
        row["Threshold_Hours_Warning"] = t["warning_h"]

        inst_upper = (row.get("Instance", "") or "").upper()
        db_lower = (row.get("Database", "") or "").lower()

        # R3 — system DB de no' AG: rota propria, contador visivel, nunca
        # somado ao delayed executivo. DBA_*/TLS_*/_rst NAO entram (user DBs).
        if db_lower in SYSTEM_DBS and inst_upper in ag_instances:
            row["Delay_Class"] = "ag_system_gap"
            row["Delayed_Severity"] = "policy"
            out["ag_system_gap"].append(row)
            continue

        # R2 — perdao limitado (f15bfb8): DIFF com FULL mais recente E fresco.
        # C2 (gate sql-deep 01/09): frescura DERIVADA de now-Last_Backup_Date —
        # o Hours_Since_Backup do ramo STANDALONE da view vem congelado pelo
        # collector e concederia perdao alem do corte com lag de coleccao.
        if type_norm == "DIFF":
            fi = full_info.get(k)
            diff_dt = _parse_dt(row.get("Last_Backup_Date"))
            full_fresh = fi is not None and (
                (now - fi[0]).total_seconds() / 3600.0 <= thresholds["FULL"]["warning_h"])
            if fi is not None and diff_dt is not None and fi[0] > diff_dt and full_fresh:
                if hours <= diff_stopped_h:
                    row["Delay_Class"] = "chain_reset"
                    row["Delayed_Severity"] = "info"
                    out["chain_reset"].append(row)
                else:
                    row["Delay_Class"] = "diff_schedule_stopped"
                    row["Delayed_Severity"] = "warning"
                    out["diff_schedule_stopped"].append(row)
                continue
            # FULL nao-fresco (ou inexistente): perdao expirado -> actionable.

        # Accionavel (delay genuino)
        row["Delay_Class"] = "actionable"
        if hours > t["critical_h"]:
            row["Delayed_Severity"] = "critical"
            out["actionable_critical"].append(row)
            out["delayed_by_type"][f"{type_norm}_critical"] += 1
            base_worst[k] = ("critical", env_key)
        else:
            row["Delayed_Severity"] = "warning"
            out["actionable_warning"].append(row)
            out["delayed_by_type"][f"{type_norm}_warning"] += 1
            if base_worst.get(k, (None,))[0] != "critical":
                base_worst[k] = ("warning", env_key)

    # R1 — contagens POR BASE (o executivo conta bases degradadas, nao linhas)
    crit_by_env = {e: 0 for e in _ENVS}
    warn_by_env = {e: 0 for e in _ENVS}
    n_crit = n_warn = 0
    for sev, env_key in base_worst.values():
        if sev == "critical":
            n_crit += 1
            crit_by_env[env_key] = crit_by_env.get(env_key, 0) + 1
        else:
            n_warn += 1
            warn_by_env[env_key] = warn_by_env.get(env_key, 0) + 1

    out["bases_critical_count"] = n_crit
    out["bases_warning_count"] = n_warn

    # 2026-09-01 (owner: tile 2 vs modal 5) — a linha segue a BASE: uma linha
    # warning de uma base critica pertence a' modal CRITICO (o tile conta bases
    # pelo pior estado; a modal tem de particionar pelo MESMO criterio).
    _sev_by_basekey = {"|".join(k): sev for k, (sev, _e) in base_worst.items()}
    for row in out["actionable_critical"] + out["actionable_warning"]:
        row["Base_Severity"] = _sev_by_basekey.get(row["Base_Key"], row["Delayed_Severity"])

    # by_env das bandas novas (sem isto, o filtro de ambiente do dashboard
    # contribuiria 0 — a classe de bug do FIND-105, corrigida a 04/08).
    # 2026-09-02 (owner: "baixar tambem os avisos"): as bandas contam BASES,
    # nao linhas — a MESMA regra R1 do executivo (msdb de um no' com FULL+DIFF
    # em atraso = 1 base, nao 2). O tile fica coerente com o cabecalho da
    # modal ("N bases"); as listas continuam por linha.
    def _band_by_env(rows):
        acc = {e: 0 for e in _ENVS}
        seen = set()
        for r in rows:
            k = r.get("Base_Key")
            if k is not None:
                if k in seen:
                    continue
                seen.add(k)
            e = (r.get("Env", "Undefined") or "Undefined").upper()
            e = e if e in ("PRD", "QLT", "TST") else "Undefined"
            acc[e] += 1
        return acc
    out["diff_schedule_stopped_by_env"] = _band_by_env(out["diff_schedule_stopped"])
    out["ag_system_gap_by_env"] = _band_by_env(out["ag_system_gap"])
    out["diff_schedule_stopped_bases_count"] = sum(out["diff_schedule_stopped_by_env"].values())
    out["ag_system_gap_bases_count"] = sum(out["ag_system_gap_by_env"].values())
    out["delayed_critical_by_env"] = crit_by_env
    out["delayed_warning_by_env"] = warn_by_env
    out["delayed_by_env"] = {e: crit_by_env[e] + warn_by_env[e] for e in _ENVS}

    # R5 — reconciliacao (o banner da persona: parcelas somam ao total antigo)
    out["reconciliation"] = {
        "rows_past_threshold": out["rows_past_threshold"],
        "actionable_rows": len(out["actionable_critical"]) + len(out["actionable_warning"]),
        "actionable_bases": n_crit + n_warn,
        "chain_reset": len(out["chain_reset"]),
        "diff_schedule_stopped": len(out["diff_schedule_stopped"]),
        "ag_system_gap": len(out["ag_system_gap"]),
    }
    return out


AG_MAP_QUERY = """
SELECT DISTINCT LTRIM(RTRIM(UPPER(Instance))) AS Instance_N,
       LTRIM(RTRIM(UPPER([Database]))) AS Database_N, AgName
FROM {schema}.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
WHERE AgName IS NOT NULL
"""


def build_ag_map(rows):
    """rows do AG_MAP_QUERY -> {(INSTANCE, DATABASE): AgName}. Fail-open: []->{}"""
    out = {}
    for r in rows or []:
        inst = r.get("Instance_N") or r.get("instance_n")
        db = r.get("Database_N") or r.get("database_n")
        ag = r.get("AgName") or r.get("agname")
        if inst and db and ag:
            out[(str(inst).upper(), str(db).upper())] = str(ag)
    return out
