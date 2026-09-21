# -*- coding: utf-8 -*-
"""KPI Transaction Log: passa a distinguir log LIMITADO / ILIMITADO / FIXO e a olhar para o disco (owner, 21/09).

Problema: classify_tlog classificava por Percent_Used = usado / ALOCADO. Um log de 1,8 GB a 99,9 % com tecto de 2 TB e
56 GB no volume contava CRITICAL. Hoje: 19 críticos e 12 avisos, quase todos deste tipo.

Regra nova (parecer do sql-deep-reviewer, 21/09, com consenso e 3 correcções; medido em produção antes de escrever):
 - Tipo por base, a partir de KPI_MSSQL_DATAFILES_STG (File_Type='LOG'):
     LEGACY   = sem linha de ficheiro (tempdb/msdb/model, secundários AG, read-only) -> regra antiga por alocado;
     FIXED    = crescimento 0 -> tecto = alocado, regra por alocado;
     UNLIMITED = Is_Unlimited=1 ou Max_Size >= 2 TB (268.435.456 páginas = tecto por omissão do log; bases criadas com
                UNLIMITED gravam este valor, migradas gravam -1; funcionalmente idêntico) -> disk-bound;
     LIMITED  = tecto real -> % usado sobre min(tecto, alocado + livre do volume).
 - CRITICAL: LIMITED/LEGACY/FIXED com % efectivo > crítico; ou log a encher (> aviso) cujo PRÓXIMO autogrow não cabe no
   volume; ou log a encher num volume que não absorve a soma dos próximos crescimentos de todos os candidatos
   (várias bases no mesmo disco: a procura soma-se, o livre é um só); ou UNLIMITED a encher com volume <= 5 GB.
 - WARNING: LIMITED/LEGACY/FIXED com % efectivo > aviso; UNLIMITED a encher sem visibilidade do volume; UNLIMITED com
   volume <= 10 GB (o log não é o problema, o disco é: aviso, não crítico).
   Desvio ao parecer: o revisor punha UNLIMITED com volume <= 5 GB em CRITICAL mesmo com o log a 2 %; aqui só é
   crítico se o log estiver a encher (> aviso). O disco quase cheio por si já é o KPI de Disk Space; contar cada
   base do volume como crítico do T-Log inflacionava o card (8 críticos em 2 volumes, com logs a 2-50 %).
 - Sinal informativo Attention_Flag=AUTOGROW_PEQUENO: > crítico do alocado com crescimento < 1 % ou <= 64 MB (VLFs).
 - Limiares: os de sempre para % (tlog_usage 85/95) e os GB de filegroup_unlimited_free_gb (10/5) para o volume, ambos
   do registry com override. Crescimento em % é convertido para MB. Volume_Free_MB = 0 = sem visibilidade.
 - Mantém: recovery model, idade do backup de log, frescura, forma do payload (tile e modal reconciliam).
 Efeito medido em 21/09 (1.054 bases): 19 críticos / 12 avisos -> 1 crítico / 15 avisos.
 Fase 2 (não bloqueia): pedir ao coletor V1 log_reuse_wait_desc (ACTIVE_TRANSACTION, AVAILABILITY_REPLICA…), 1 coluna de
 sys.databases, ALTER nos dois lados BLUE/GREEN -> veto/consentimento do guardião V1.

Ficheiros: api/routers/intelligence/tlog_usage_classes.py (query + classificador), helpers.py e intelligence_kpis.py (passam
os GB do volume), teste novo tests/unit/test_tlog_limitado_ilimitado_20260921.py. Só leitura à base (STG), sql_monitoring.

Uso (raiz do repo, ramo design/tokens-contrato ou main):
  py docs/context/TLOG_LIMITADO_ILIMITADO_2026-09-21_apply.py --check
  py docs/context/TLOG_LIMITADO_ILIMITADO_2026-09-21_apply.py
  py -m pytest tests/unit/test_tlog_usage_classes_20260902.py tests/unit/test_tlog_limitado_ilimitado_20260921.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; KPIs > Transaction Logs
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASSES = Path("api/routers/intelligence/tlog_usage_classes.py")
HELPERS = Path("api/routers/intelligence/helpers.py")
KPIS = Path("api/routers/intelligence_kpis.py")
TESTE = Path("tests/unit/test_tlog_limitado_ilimitado_20260921.py")
MARK = "Log_Kind"

QUERY_OLD = '''SELECT t.Instance, t.[Database], ISNULL(e.Env, 'Undefined') AS Env,
       t.Percent_Used, t.Used_MB, t.Current_MB, t.Max_Available_MB, t.Update_TS,
       ds.Recovery_Model,
       COALESCE(lag.Last_Log_Backup_Date, ll.Last_Log_Backup_Date) AS Last_Log_Backup_Date
FROM {schema}.KPI_MSSQL_TLOG_USAGE_ACTIVE t WITH (NOLOCK)
LEFT JOIN {schema}.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
       ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(t.Instance)))'''

QUERY_NEW = ''',
logfiles AS (
    -- 2026-09-21 (owner): tecto e disco por base, a partir dos ficheiros LOG. Drive na STG e' so' a letra (mount
    -- points colapsam); Volume_Free_MB = 0 = sem visibilidade -> NULL; crescimento em % convertido para MB.
    SELECT LTRIM(RTRIM(UPPER(Instance)))   AS Instance_N,
           LTRIM(RTRIM(UPPER([Database]))) AS Database_N,
           MIN(Drive)                      AS Drive,
           MAX(CASE WHEN Is_Unlimited = 1 OR Max_Size_MB >= 2097152 THEN 1 ELSE 0 END) AS Any_Unlimited,
           SUM(CASE WHEN Is_Unlimited = 1 OR Max_Size_MB >= 2097152 THEN 0 ELSE Max_Size_MB END) AS Max_Size_MB_Lim,
           MIN(NULLIF(Volume_Free_MB, 0))  AS Volume_Free_MB,
           SUM(CASE WHEN Is_Percent_Growth = 1 THEN Size_MB * Growth_MB / 100.0 ELSE Growth_MB END) AS Next_Growth_MB
    FROM {schema}.KPI_MSSQL_DATAFILES_STG WITH (NOLOCK)
    WHERE File_Type = 'LOG'
    GROUP BY LTRIM(RTRIM(UPPER(Instance))), LTRIM(RTRIM(UPPER([Database])))
)
SELECT t.Instance, t.[Database], ISNULL(e.Env, 'Undefined') AS Env,
       t.Percent_Used, t.Used_MB, t.Current_MB, t.Max_Available_MB, t.Update_TS,
       ds.Recovery_Model,
       COALESCE(lag.Last_Log_Backup_Date, ll.Last_Log_Backup_Date) AS Last_Log_Backup_Date,
       CASE WHEN lf.Instance_N IS NULL                                   THEN 'LEGACY'
            WHEN ISNULL(lf.Next_Growth_MB, 0) = 0                         THEN 'FIXED'
            WHEN lf.Any_Unlimited = 1 OR t.Max_Available_MB >= 2097152    THEN 'UNLIMITED'
            ELSE 'LIMITED' END AS Log_Kind,
       CASE WHEN t.Max_Available_MB IS NULL OR t.Max_Available_MB <= 0 THEN t.Current_MB
            ELSE ISNULL(NULLIF(lf.Max_Size_MB_Lim, 0), t.Max_Available_MB) END AS Ceiling_MB,
       lf.Drive, lf.Volume_Free_MB, lf.Next_Growth_MB
FROM {schema}.KPI_MSSQL_TLOG_USAGE_ACTIVE t WITH (NOLOCK)
LEFT JOIN logfiles lf
       ON lf.Instance_N = LTRIM(RTRIM(UPPER(t.Instance)))
      AND lf.Database_N = LTRIM(RTRIM(UPPER(t.[Database])))
LEFT JOIN {schema}.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
       ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(t.Instance)))'''

# a CTE nova entra a seguir ao ") " que fecha lastlog_ag; o anchor QUERY_OLD comeca no SELECT, por isso o ")\\n" anterior
# tem de deixar de fechar a lista de CTEs: substitui-se ")\\nSELECT t.Instance" por ")," + logfiles + SELECT
QUERY_OLD_FULL = ")\n" + QUERY_OLD
QUERY_NEW_FULL = ")" + QUERY_NEW

CLASSIFY_OLD = '''    now = now or datetime.now()
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
'''

CLASSIFY_NEW = '''    now = now or datetime.now()
    cutoff = now - timedelta(minutes=fresh_minutes)
    warn = float(thresholds["warning"])
    crit = float(thresholds["critical"])
    ufree = unlimited_free_gb or {}
    ufree_warn_mb = float(ufree.get("warning", 10)) * 1024.0
    ufree_crit_mb = float(ufree.get("critical", 5)) * 1024.0
    critical, warning = [], []
    per_inst = {}
    inst_worst = {}
    rows_fresh = normal = 0
    # 2026-09-21: 1.a passagem -- procura por volume (soma dos proximos crescimentos das bases a encher no mesmo disco)
    fresh_rows = []
    demand = {}
    for row in rows or []:
        has_ts = "Update_TS" in row
        upd = _parse_dt(row.get("Update_TS")) if has_ts else None
        if has_ts and (upd is None or upd < cutoff):
            continue
        fresh_rows.append((row, upd))
        drv = row.get("Drive")
        if drv and (_to_float(row.get("Percent_Used")) or 0.0) > warn:
            k = ((row.get("Instance") or "").strip().upper(), str(drv).upper())
            demand[k] = demand.get(k, 0.0) + (_to_float(row.get("Next_Growth_MB")) or 0.0)
    for row, upd in fresh_rows:
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
        drv = row.get("Drive")
        dem = demand.get((inst.upper(), str(drv).upper()), 0.0) if drv else 0.0
        sev, pct_eff, reason, attn = _tlog_severity(row, pct, warn, crit, ufree_warn_mb, ufree_crit_mb, dem)
        row["Log_Kind"] = row.get("Log_Kind") or "LEGACY"
        row["Pct_Eff"] = round(pct_eff, 2) if pct_eff is not None else None
        row["Reason"] = reason
        row["Attention_Flag"] = attn
        if sev == "CRITICAL":
            agg["Critical"] += 1
        elif sev == "WARNING":
            agg["Warning"] += 1
        else:
            agg["Normal"] += 1
            normal += 1
            continue
'''

SEV_FN = '''

def _tlog_severity(row, pct, warn, crit, ufree_warn_mb, ufree_crit_mb, demand_mb):
    """Severidade de uma base (2026-09-21, limitado/ilimitado). Devolve (sev, pct_eff, reason, attention_flag).

    kind: LEGACY (sem ficheiros: regra antiga por alocado), FIXED (crescimento 0), LIMITED (tecto real), UNLIMITED
    (disk-bound). pct = % do alocado; pct_eff = % do tecto efectivo (LIMITED) ou pct (LEGACY/FIXED) ou None (UNLIMITED).
    """
    kind = (row.get("Log_Kind") or "LEGACY").upper()
    vol = _to_float(row.get("Volume_Free_MB"))          # None = sem visibilidade
    ng = _to_float(row.get("Next_Growth_MB")) or 0.0
    cur = _to_float(row.get("Current_MB")) or 0.0
    used = _to_float(row.get("Used_MB")) or 0.0
    ceiling = _to_float(row.get("Ceiling_MB")) or 0.0
    if kind == "LIMITED":
        cap = ceiling if vol is None else min(ceiling, cur + vol) if ceiling > 0 else cur + vol
        pct_eff = (used * 100.0 / cap) if cap and cap > 0 else pct
    elif kind == "UNLIMITED":
        pct_eff = None
    else:
        pct_eff = pct
    attn = "AUTOGROW_PEQUENO" if (pct > crit and ng > 0 and (ng < cur * 0.01 or ng <= 64)) else None
    enche = pct > warn
    if kind in ("LIMITED", "LEGACY", "FIXED") and pct_eff is not None and pct_eff > crit:
        return "CRITICAL", pct_eff, "TECTO", attn
    if enche and vol is not None and ng > 0 and vol < ng:
        return "CRITICAL", pct_eff, "AUTOGROW_NAO_CABE", attn
    if enche and vol is not None and demand_mb > vol:
        return "CRITICAL", pct_eff, "VOLUME_SATURADO", attn
    if kind == "UNLIMITED" and enche and vol is not None and vol <= ufree_crit_mb:
        return "CRITICAL", pct_eff, "VOLUME_BAIXO", attn
    if kind in ("LIMITED", "LEGACY", "FIXED") and pct_eff is not None and pct_eff > warn:
        return "WARNING", pct_eff, "TECTO", attn
    if kind == "UNLIMITED" and enche and vol is None:
        return "WARNING", pct_eff, "SEM_VISIBILIDADE", attn
    if kind == "UNLIMITED" and vol is not None and vol <= ufree_warn_mb:
        return "WARNING", pct_eff, "VOLUME_BAIXO", attn
    return "OK", pct_eff, None, attn
'''

SIG_OLD = "def classify_tlog(rows, thresholds, now=None, fresh_minutes=1440, log_late_hours=None):"
SIG_NEW = "def classify_tlog(rows, thresholds, now=None, fresh_minutes=1440, log_late_hours=None, unlimited_free_gb=None):"

SORT_OLD = '''    def _sort_key(r):
        return (-(_to_float(r.get("Percent_Used")) or 0.0), r.get("Instance") or "", str(r.get("Database") or ""))'''
SORT_NEW = '''    def _sort_key(r):
        # 2026-09-21: o que manda e' o % efectivo (tecto/disco); sem ele, o % do alocado
        p = _to_float(r.get("Pct_Eff"))
        if p is None:
            p = _to_float(r.get("Percent_Used")) or 0.0
        return (-p, r.get("Instance") or "", str(r.get("Database") or ""))'''

HELPERS_OLD = '''        cls = classify_tlog(
            tlog_rows,
            {'warning': _th('tlog_usage', 'warning'), 'critical': _th('tlog_usage', 'critical')},'''
HELPERS_NEW = '''        cls = classify_tlog(
            tlog_rows,
            {'warning': _th('tlog_usage', 'warning'), 'critical': _th('tlog_usage', 'critical')},
            unlimited_free_gb={'warning': _th('filegroup_unlimited_free_gb', 'warning'), 'critical': _th('filegroup_unlimited_free_gb', 'critical')},'''
KPIS_OLD = '''            cls = classify_tlog(
                _rows,
                {'warning': _th('tlog_usage', 'warning'), 'critical': _th('tlog_usage', 'critical')},'''
KPIS_NEW = '''            cls = classify_tlog(
                _rows,
                {'warning': _th('tlog_usage', 'warning'), 'critical': _th('tlog_usage', 'critical')},
                unlimited_free_gb={'warning': _th('filegroup_unlimited_free_gb', 'warning'), 'critical': _th('filegroup_unlimited_free_gb', 'critical')},'''

TESTE_SRC = '''# -*- coding: utf-8 -*-
"""T-Log limitado / ilimitado / fixo (2026-09-21): casos de borda do parecer do sql-deep-reviewer.

Regra em api/routers/intelligence/tlog_usage_classes.py (_tlog_severity). Linhas sem Log_Kind = LEGACY = regra antiga,
por isso os testes de 02/09 continuam validos sem alteracao.
"""
from datetime import datetime, timedelta

from api.routers.intelligence.tlog_usage_classes import classify_tlog, TLOG_BASE_QUERY

NOW = datetime(2026, 9, 21, 12, 0, 0)
TH = {'warning': 85, 'critical': 95}
GB = {'warning': 10, 'critical': 5}


def _row(inst, db, pct, kind, cur=1000, vol=None, ng=64, ceiling=None, **extra):
    r = {
        'Instance': inst, 'Database': db, 'Env': 'PRD', 'Percent_Used': pct,
        'Used_MB': cur * pct / 100.0, 'Current_MB': cur, 'Max_Available_MB': ceiling if ceiling is not None else 2097152,
        'Update_TS': NOW - timedelta(minutes=5), 'Recovery_Model': 'FULL',
        'Last_Log_Backup_Date': NOW - timedelta(minutes=30),
        'Log_Kind': kind, 'Ceiling_MB': ceiling if ceiling is not None else (cur if kind == 'FIXED' else 2097152),
        'Drive': 'L:\\\\', 'Volume_Free_MB': vol, 'Next_Growth_MB': ng,
    }
    r.update(extra)
    return r


def _sev(rows):
    cls = classify_tlog(rows, TH, now=NOW, unlimited_free_gb=GB)
    out = {}
    for r in cls['critical']: out[(r['Instance'], r['Database'])] = ('CRITICAL', r['Reason'])
    for r in cls['warning']: out[(r['Instance'], r['Database'])] = ('WARNING', r['Reason'])
    return out


def test_ilimitado_cheio_do_alocado_com_disco_folgado_e_ok():
    # o caso do owner: 99,9 % de 1,8 GB alocados, tecto 2 TB, 56 GB no volume
    assert _sev([_row('A', 'db', 99.9, 'UNLIMITED', cur=1856, vol=56186, ng=64)]) == {}


def test_limitado_no_tecto_e_critico_mesmo_com_disco():
    # tecto real = alocado (max_size = size): nao pode crescer, esta a 99 %
    s = _sev([_row('A', 'db', 99.0, 'LIMITED', cur=52225, vol=36456, ng=512, ceiling=52225)])
    assert s[('A', 'db')] == ('CRITICAL', 'TECTO')


def test_limitado_com_tecto_longe_usa_o_tecto_efectivo():
    # 99 % de 1.000 alocados, tecto 10.000 e 50 GB no disco -> 9,9 % do tecto -> OK
    assert _sev([_row('A', 'db', 99.0, 'LIMITED', cur=1000, vol=51200, ng=64, ceiling=10000)]) == {}
    # mesmo tecto mas disco com 100 MB: cap = 1.100 -> 90 % -> WARNING
    s = _sev([_row('A', 'db', 99.0, 'LIMITED', cur=1000, vol=100, ng=64, ceiling=10000)])
    assert s[('A', 'db')] == ('WARNING', 'TECTO')


def test_proximo_autogrow_nao_cabe_e_critico():
    s = _sev([_row('A', 'db', 90.0, 'UNLIMITED', cur=1000, vol=40, ng=64)])
    assert s[('A', 'db')] == ('CRITICAL', 'AUTOGROW_NAO_CABE')


def test_volume_partilhado_soma_a_procura():
    # tres bases a encher no mesmo volume: cada crescimento cabe (64 < 150) mas a soma (192) nao
    rows = [_row('A', f'db{i}', 90.0, 'UNLIMITED', cur=1000, vol=150, ng=64) for i in range(3)]
    s = _sev(rows)
    assert all(v == ('CRITICAL', 'VOLUME_SATURADO') for v in s.values()) and len(s) == 3
    # a mesma base sozinha no volume: o crescimento cabe (64 < 150), mas esta a encher num volume com 150 MB (<= 5 GB) -> critico pelo volume
    assert _sev([rows[0]])[('A', 'db0')] == ('CRITICAL', 'VOLUME_BAIXO')
    # com o volume acima dos 10 GB e a caber, e' OK
    assert _sev([_row('A', 'db9', 90.0, 'UNLIMITED', cur=1000, vol=20480, ng=64)]) == {}


def test_ilimitado_disco_baixo_so_e_critico_se_o_log_estiver_a_encher():
    # desvio declarado ao parecer: log a 2 % num volume com 2 GB -> aviso (o disco e' o KPI de Disk Space), nao critico
    assert _sev([_row('A', 'db', 2.0, 'UNLIMITED', cur=1000, vol=2048, ng=42)])[('A', 'db')] == ('WARNING', 'VOLUME_BAIXO')
    assert _sev([_row('A', 'db', 90.0, 'UNLIMITED', cur=1000, vol=2048, ng=42)])[('A', 'db')] == ('CRITICAL', 'VOLUME_BAIXO')


def test_ilimitado_sem_visibilidade_do_volume():
    assert _sev([_row('A', 'db', 90.0, 'UNLIMITED', cur=1000, vol=None, ng=64)])[('A', 'db')] == ('WARNING', 'SEM_VISIBILIDADE')
    assert _sev([_row('A', 'db', 20.0, 'UNLIMITED', cur=1000, vol=None, ng=64)]) == {}


def test_fixed_e_legacy_usam_o_alocado():
    assert _sev([_row('A', 'fx', 96.0, 'FIXED', cur=500, vol=99999, ng=0, ceiling=500)])[('A', 'fx')] == ('CRITICAL', 'TECTO')
    legacy = {k: v for k, v in _row('A', 'tempdb', 96.0, 'LEGACY').items() if k not in ('Log_Kind', 'Ceiling_MB', 'Drive', 'Volume_Free_MB', 'Next_Growth_MB')}
    s = _sev([legacy])
    assert s[('A', 'tempdb')] == ('CRITICAL', 'TECTO')


def test_attention_autogrow_pequeno_nunca_e_critico():
    cls = classify_tlog([_row('A', 'db', 98.0, 'UNLIMITED', cur=10000, vol=7000, ng=64)], TH, now=NOW, unlimited_free_gb=GB)
    assert not cls['critical'] and len(cls['warning']) == 1 and cls['warning'][0]['Attention_Flag'] == 'AUTOGROW_PEQUENO'


def test_pct_eff_manda_na_ordenacao_e_payload():
    a = _row('A', 'a', 99.0, 'LIMITED', cur=1000, vol=51200, ng=64, ceiling=1050)   # 94,3 % do tecto -> WARNING
    b = _row('A', 'b', 90.0, 'LIMITED', cur=1000, vol=51200, ng=64, ceiling=1005)   # 89,6 % -> WARNING
    cls = classify_tlog([b, a], TH, now=NOW, unlimited_free_gb=GB)
    assert [r['Database'] for r in cls['warning']] == ['a', 'b']
    assert cls['warning'][0]['Log_Kind'] == 'LIMITED' and cls['warning'][0]['Pct_Eff'] > cls['warning'][1]['Pct_Eff']
    assert cls['reconciliation']['critical'] + cls['reconciliation']['warning'] + cls['reconciliation']['normal'] == 2


def test_query_traz_as_colunas_novas_e_continua_select_only():
    q = TLOG_BASE_QUERY.format(schema='dbo')
    for col in ('Log_Kind', 'Ceiling_MB', 'Volume_Free_MB', 'Next_Growth_MB', 'KPI_MSSQL_DATAFILES_STG', "File_Type = 'LOG'", '2097152'):
        assert col in q
    assert 'INSERT' not in q.upper() and 'UPDATE ' not in q.upper() and 'DELETE' not in q.upper()
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:160]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    p_cls, p_h, p_k, p_t = base / CLASSES, base / HELPERS, base / KPIS, base / TESTE
    cls = p_cls.read_bytes().decode("utf-8")
    if MARK in cls:
        print("[ABORT] ja aplicado"); return 1
    novo_cls = _apply(cls, [(QUERY_OLD_FULL, QUERY_NEW_FULL, 1), (SIG_OLD, SIG_NEW, 1), (CLASSIFY_OLD, CLASSIFY_NEW, 1), (SORT_OLD, SORT_NEW, 1)], "tlog_usage_classes")
    # a funcao de severidade entra antes de classify_tlog
    novo_cls = novo_cls.replace(SIG_NEW, SEV_FN.strip("\n") + "\n\n\n" + SIG_NEW, 1)
    novo_h = _apply(p_h.read_bytes().decode("utf-8"), [(HELPERS_OLD, HELPERS_NEW, 1)], "helpers") if p_h.exists() else None
    novo_k = _apply(p_k.read_bytes().decode("utf-8"), [(KPIS_OLD, KPIS_NEW, 1)], "intelligence_kpis") if p_k.exists() else None
    compile(novo_cls, str(p_cls), "exec")
    print(f"[ok] tlog_usage_classes: query com tecto/disco por base + _tlog_severity + ordenacao por Pct_Eff; helpers {'ok' if novo_h else 'ausente'}; intelligence_kpis {'ok' if novo_k else 'ausente'}; teste novo {TESTE.name}")
    if check:
        print("--check OK. Nada escrito."); return 0
    p_cls.write_bytes(novo_cls.encode("utf-8")); print(f"[write] {CLASSES}")
    if novo_h is not None: p_h.write_bytes(novo_h.encode("utf-8")); print(f"[write] {HELPERS}")
    if novo_k is not None: p_k.write_bytes(novo_k.encode("utf-8")); print(f"[write] {KPIS}")
    p_t.parent.mkdir(parents=True, exist_ok=True); p_t.write_text(TESTE_SRC, encoding="utf-8"); print(f"[write] {TESTE}")
    print("\nAplicado. Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; KPIs > Transaction Logs.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
