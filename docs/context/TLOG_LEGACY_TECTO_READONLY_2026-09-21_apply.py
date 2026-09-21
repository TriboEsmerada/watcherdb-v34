# -*- coding: utf-8 -*-
"""
TLOG: tecto real nas bases sem ficheiros + base read-only/standby/snapshot no diagnostico  (2026-09-21, owner GO)

Caso que disparou: ctrlm_tap_report em SQLHDSPRD405\\I01 e' READ ONLY, log 48 MB com max_size 500 MB, volume com
383 GB livres. O KPI contava-a como o unico CRITICAL da frota (LEGACY -> % do alocado 99,1 %) e o diagnostico
classificava CRITICAL pela cadeia de backup parada ha' 933 dias -- numa base sem escritas nada disso e' risco.

O que muda (4 ficheiros, so' V3.4; nada toca no V1 nem na BD partilhada):
  K1  api/routers/intelligence/tlog_usage_classes.py  _tlog_severity: LEGACY com tecto real (0 < Ceiling < 2 TB)
      calcula Pct_Eff = Used / max(Ceiling, Current). 15 das 31 bases LEGACY da frota tem tecto real.
  K2  idem, TLOG_BASE_QUERY: WHERE State_Desc ONLINE (ou sem linha em DB_SETTINGS). Hoje sem efeito (1054/1054 ONLINE).
  D1  api/routers/queries/tlog_diagnosis.py: create_date/source_database_id na query de estado; is_snapshot nos
      backups 30d; frozen_kind = READ ONLY | STANDBY | SNAPSHOT (is_read_only / is_in_standby / source_database_id).
  D2  cadeia de backup: frozen -> problema INFO "chain_frozen" (nunca chain_stopped); base criada ha' < 24 h sem
      backup de log -> WARNING "chain_new" (nao CRITICAL); backups por snapshot (VSS/storage) com cadeia "never"
      -> INFO "chain_snapshot_hint".
  D3  margem apertada (HEADROOM_MIN_MB = 1 GB absoluto) so' quando e' o DISCO que limita ou o tecto ja' esta' quase:
      452 MB de margem num log de 48 MB com max_size 500 MB nao e' falta de espaco (efectivo a 10 %).
  D4  log_usage em base frozen -> INFO; tile "Log utilizado" e "Ultimo backup de log" coerentes; triagem READ ONLY
      com headline/steps proprios; subtitulo e "Estado" mostram o frozen_kind; raw.derived ganha frozen_kind,
      db_age_h, snapshot_backups.
  T   3 testes novos em tests/unit/test_tlog_limitado_ilimitado_20260921.py e 4 em
      tests/unit/test_tlog_diagnosis_20260902.py.

Uso:
  py docs/context/TLOG_LEGACY_TECTO_READONLY_2026-09-21_apply.py --check            # so' verifica ancoras
  py docs/context/TLOG_LEGACY_TECTO_READONLY_2026-09-21_apply.py --preview <dir>    # escreve resultado em <dir>
  py docs/context/TLOG_LEGACY_TECTO_READONLY_2026-09-21_apply.py --repo <copia>     # aplica noutra raiz (prova)
  py docs/context/TLOG_LEGACY_TECTO_READONLY_2026-09-21_apply.py                    # aplica no repo (owner)
Idempotente: cada ficheiro tem MARK; ficheiro ja' marcado e' saltado.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MARK = "2026-09-21 (owner, ctrlm_tap_report)"
KPI = "api/routers/intelligence/tlog_usage_classes.py"
DIAG = "api/routers/queries/tlog_diagnosis.py"
T_KPI = "tests/unit/test_tlog_limitado_ilimitado_20260921.py"
T_DIAG = "tests/unit/test_tlog_diagnosis_20260902.py"
T_OLD = "tests/unit/test_tlog_usage_classes_20260902.py"   # fixture: Max_Available_MB 2000 era um tecto real -> sentinela 2 TB


class Doc:
    def __init__(self, root: Path, rel: str):
        self.rel = rel
        self.path = root / rel
        raw = self.path.read_bytes()
        self.crlf = b"\r\n" in raw
        self.text = raw.decode("utf-8").replace("\r\n", "\n")
        self.done = MARK in self.text
        self.n_edits = 0

    def troca(self, old: str, new: str, n: int = 1):
        got = self.text.count(old)
        if got != n:
            raise SystemExit(f"[ABORT] {self.rel}: esperado {n}x, encontrado {got}x: {old[:100]!r}")
        self.text = self.text.replace(old, new)
        self.n_edits += 1

    def append(self, block: str):
        if not self.text.endswith("\n"):
            self.text += "\n"
        self.text += block
        self.n_edits += 1

    def out_bytes(self) -> bytes:
        t = self.text.replace("\n", "\r\n") if self.crlf else self.text
        return t.encode("utf-8")


# ----------------------------------------------------------------------------------------------------------- KPI
def edit_kpi(d: Doc):
    d.troca('    kind: LEGACY (sem ficheiros: regra antiga por alocado), FIXED (crescimento 0), LIMITED (tecto real), UNLIMITED\n',
            '    kind: LEGACY (sem ficheiros: % do tecto real da TLOG_STG quando existe, senao alocado), FIXED (crescimento 0),\n'
            '    LIMITED (tecto real), UNLIMITED\n')
    d.troca('    ceiling = _to_float(row.get("Ceiling_MB")) or 0.0\n',
            '    ceiling = _to_float(row.get("Ceiling_MB")) or _to_float(row.get("Max_Available_MB")) or 0.0\n')
    d.troca('    elif kind == "UNLIMITED":\n        pct_eff = None\n    else:\n        pct_eff = pct\n',
            '    elif kind == "UNLIMITED":\n        pct_eff = None\n'
            f'    elif kind == "LEGACY" and 0 < ceiling < 2097152:\n'
            f'        # {MARK}: sem ficheiros no coletor (base read-only, etc.) mas a TLOG_STG conhece o tecto\n'
            '        # real (Max_Available_MB) -> % do tecto, nunca do alocado. Tecto abaixo do alocado = ficheiro que nao cresce.\n'
            '        cap = max(ceiling, cur)\n'
            '        pct_eff = (used * 100.0 / cap) if cap > 0 else pct\n'
            '    else:\n        pct_eff = pct\n')
    d.troca('      AND ll.Database_N = LTRIM(RTRIM(UPPER(t.[Database])))\n"""\n',
            '      AND ll.Database_N = LTRIM(RTRIM(UPPER(t.[Database])))\n'
            "-- 2026-09-21: bases RESTORING/RECOVERING/OFFLINE nao entram no KPI (sem linha em DB_SETTINGS = neutro)\n"
            "WHERE ds.State_Desc IS NULL OR UPPER(LTRIM(RTRIM(ds.State_Desc))) = 'ONLINE'\n"
            '"""\n')


# ---------------------------------------------------------------------------------------------------- DIAGNOSTICO
def edit_diag(d: Doc):
    # D1 sinais
    d.troca('       d.is_read_only, d.is_in_standby, d.is_auto_shrink_on,\n',
            '       d.is_read_only, d.is_in_standby, d.is_auto_shrink_on,\n'
            '       d.create_date, d.source_database_id,\n')
    d.troca('       SUM(CASE WHEN b.is_copy_only = 1 THEN 1 ELSE 0 END) AS copy_only_count\n',
            '       SUM(CASE WHEN b.is_copy_only = 1 THEN 1 ELSE 0 END) AS copy_only_count,\n'
            '       SUM(CASE WHEN b.is_snapshot = 1 THEN 1 ELSE 0 END) AS snapshot_count\n')
    d.troca('    log_needs_backup = recovery in ("FULL", "BULK_LOGGED")\n',
            '    log_needs_backup = recovery in ("FULL", "BULK_LOGGED")\n'
            f'    # {MARK}: base "congelada" nao recebe escritas -> o log nao cresce nem trunca;\n'
            '    # cadeia de backup parada e LOG_BACKUP deixam de ser risco de 9002 enquanto ficar assim.\n'
            '    is_read_only = int(_n(st.get("is_read_only"), 0) or 0) == 1\n'
            '    is_standby = int(_n(st.get("is_in_standby"), 0) or 0) == 1\n'
            '    is_db_snapshot = st.get("source_database_id") not in (None, 0, "0", "")\n'
            '    frozen_kind = "STANDBY" if is_standby else ("SNAPSHOT" if is_db_snapshot else ("READ ONLY" if is_read_only else None))\n'
            '    created_at = _dt(st.get("create_date"))\n'
            '    db_age_h = ((now - created_at).total_seconds() / 3600.0) if created_at else None\n'
            '    snapshot_backups = sum(int(_n(r.get("snapshot_count"), 0) or 0) for r in bk30)\n')
    # D3 margem apertada: so' quando o disco limita ou o tecto esta' quase
    d.troca('    effective_pct = (100.0 * used_mb / effective_limit_mb) if (effective_limit_mb and used_mb is not None) else None\n',
            '    effective_pct = (100.0 * used_mb / effective_limit_mb) if (effective_limit_mb and used_mb is not None) else None\n'
            '    # 2026-09-21: margem "apertada" so\' quando e\' o DISCO que limita (ou o tecto ja\' esta\' quase): 452 MB de margem\n'
            '    # num log de 48 MB com max_size 500 MB (efectivo a 10 %) nao e\' falta de espaco.\n'
            '    vol_free_mb = (vol_free_gb * 1024.0) if vol_free_gb is not None else None\n'
            '    headroom_tight = (headroom_mb is not None and headroom_mb < HEADROOM_MIN_MB\n'
            '                      and (vol_free_mb is None or vol_free_mb < HEADROOM_MIN_MB\n'
            '                           or (effective_pct is not None and effective_pct > tl_warn)))\n')
    d.troca('        no_room = (headroom_mb is not None and headroom_mb < HEADROOM_MIN_MB) or bool(growth_disabled)\n',
            '        no_room = headroom_tight or bool(growth_disabled)\n')
    d.troca('    if headroom_mb is not None and headroom_mb < HEADROOM_MIN_MB:\n        sev = "critical" if (used_pct or 0) > tl_warn else "warning"\n',
            '    if headroom_tight:\n        sev = "critical" if (used_pct or 0) > tl_warn and not frozen_kind else "warning"\n')
    d.troca('    if (headroom_mb is not None and headroom_mb < HEADROOM_MIN_MB) or (runway_days is not None and runway_days <= RUNWAY_DAYS_WARN):\n',
            '    if headroom_tight or (runway_days is not None and runway_days <= RUNWAY_DAYS_WARN):\n')
    d.troca('    elif (headroom_mb is not None and headroom_mb < HEADROOM_MIN_MB) or (runway_days is not None and runway_days <= RUNWAY_DAYS_CRIT):\n',
            '    elif headroom_tight or (runway_days is not None and runway_days <= RUNWAY_DAYS_CRIT):\n')
    # D2 cadeia
    d.troca('    elif log_needs_backup:\n        if last_log is None:\n',
            '    elif log_needs_backup and frozen_kind:\n'
            '        chain_state = "frozen"\n'
            '        prob("chain_frozen", f"Base {frozen_kind}: o log não recebe escritas",\n'
            '             f"sys.databases: is_read_only / is_in_standby / source_database_id · {pct_txt}{size_txt}"\n'
            '             + (f" · último backup de log {_fmt_dt_full(last_log)}" if last_log is not None else " · sem backup de log registado em 30 dias"),\n'
            '             "Sem escritas o log não cresce nem trunca: a cadeia de backup parada não é risco de 9002 enquanto a base ficar assim",\n'
            '             "info", "fa-lock", summary=f"{frozen_kind} · cadeia de backup não aplicável")\n'
            '    elif log_needs_backup:\n        if last_log is None:\n')
    d.troca('            else:\n                chain_state = "never"\n',
            '            elif db_age_h is not None and db_age_h < 24:\n'
            '                chain_state = "new"\n'
            '                prob("chain_new", f"Base criada há {_num(db_age_h, 0)} h ainda sem backup de log",\n'
            '                     f"sys.databases.create_date = {_fmt_dt_full(created_at)}; msdb: 0 backups tipo L", "Esperado nas primeiras horas; se o job não a apanhar, vira cadeia parada",\n'
            '                     "warning", "fa-hourglass-start", source="history", rec_ids=["rec_log_backup"], summary="Base recente · sem backup de log")\n'
            '            else:\n                chain_state = "never"\n')
    d.troca('    if chain_state in ("never", "late", "unknown"):\n',
            '    if chain_state in ("never", "late", "unknown", "new"):\n')
    # base recente: "sem full em 30 dias" tambem e' esperado nas primeiras horas
    d.troca('                 "Sem ponto de partida para restore; log backup não funciona", "critical", "fa-database", source="history", rec_ids=["rec_full"],\n',
            '                 "Sem ponto de partida para restore; log backup não funciona", ("warning" if chain_state == "new" else "critical"), "fa-database", source="history", rec_ids=["rec_full"],\n')
    d.troca('    # 2) Causa de retencao anormal',
            '    if chain_state == "never" and snapshot_backups > 0:\n'
            '        prob("chain_snapshot_hint", f"{snapshot_backups} backup(s) por snapshot (VSS/storage) em 30 dias",\n'
            '             "msdb.dbo.backupset.is_snapshot = 1 — a ferramenta externa pode gerir a cadeia fora do BACKUP LOG nativo",\n'
            '             "Confirmar com a equipa de backup antes de tratar como cadeia parada", "info", "fa-camera", source="history", conf="heuristic",\n'
            '             summary="Backups por snapshot registados")\n\n'
            '    # 2) Causa de retencao anormal')
    # D4 log_usage / tiles / triagem / headline / subtitulo / raw
    d.troca("        growth_txt_p = (f\"+{_mb(first_log.get('log_growth_value'))}\"",
            '        if frozen_kind and not no_room:\n            sev = "info"\n'
            "        growth_txt_p = (f\"+{_mb(first_log.get('log_growth_value'))}\"")
    # autogrow "mau" numa base sem escritas e' informativo; growth = 0 continua a regra (critico so' se encher, e nunca em frozen)
    d.troca('             "Barato de corrigir, evita o próximo incidente", "warning", "fa-expand-arrows-alt", rec_ids=["rec_growth"],\n',
            '             "Barato de corrigir, evita o próximo incidente", ("info" if frozen_kind else "warning"), "fa-expand-arrows-alt", rec_ids=["rec_growth"],\n')
    d.troca('             "Quando encher não cresce: 9002 imediato", "critical" if (used_pct or 0) > tl_warn else "warning", "fa-ban", rec_ids=["rec_growth"],\n',
            '             "Quando encher não cresce: 9002 imediato", "critical" if (used_pct or 0) > tl_warn and not frozen_kind else "warning", "fa-ban", rec_ids=["rec_growth"],\n')
    d.troca('    if chain_state in ("never", "late"):\n        triage = ("CADEIA PARADA",',
            '    if chain_state == "frozen":\n'
            '        triage = ("READ ONLY", f"base {frozen_kind.lower()} — o log não recebe escritas; cadeia de backup e LOG_BACKUP não são risco")\n'
            '    elif chain_state in ("never", "late"):\n        triage = ("CADEIA PARADA",')
    d.troca('        last_log_val, last_log_sub, last_log_sev = "n/a", "recovery SIMPLE", "info"\n',
            '        last_log_val, last_log_sub, last_log_sev = "n/a", "recovery SIMPLE", "info"\n'
            '    elif chain_state == "frozen":\n'
            '        last_log_val, last_log_sub, last_log_sev = "n/a", f"{frozen_kind}: sem escritas no log", "info"\n')
    d.troca('                      else ("warning" if (used_pct or 0) > tl_warn else "ok"))},\n',
            '                      else ("warning" if (used_pct or 0) > tl_warn and not frozen_kind else "ok"))},\n')
    d.troca('        {"k": "Estado", "v": state_desc or "?"},\n',
            '        {"k": "Estado", "v": (state_desc or "?") + (f" · {frozen_kind}" if frozen_kind else "")},\n')
    d.troca('        "SAUDAVEL": "Nada a fazer agora',
            '        "READ ONLY": "1) Nada a fazer enquanto a base não receber escritas.\\n2) Se voltar a READ_WRITE em FULL: religar o backup de log nesse momento.\\n3) Base histórica: considerar SIMPLE ou descontinuar.",\n'
            '        "SAUDAVEL": "Nada a fazer agora')
    d.troca('    if tkey == "CADEIA PARADA":\n        headline = "CADEIA DE BACKUP DE LOG INTERROMPIDA"\n',
            '    if tkey == "READ ONLY":\n'
            '        headline = f"BASE {frozen_kind}: LOG SEM ESCRITAS"\n'
            '        chain = [frozen_kind, recovery or "?", lrw or "?", used_chip, "sem crescimento", "cadeia de backup não aplicável"]\n'
            '        note = "Enquanto a base não receber escritas o log não cresce; ao voltar a READ_WRITE em FULL, religar o backup de log."\n'
            '    elif tkey == "CADEIA PARADA":\n        headline = "CADEIA DE BACKUP DE LOG INTERROMPIDA"\n')
    d.troca('"subtitle": f"{display_inst} · Recovery: {recovery or \'?\'} · {lrw or \'?\'}", "verdict": verdict},',
            '"subtitle": f"{display_inst} · Recovery: {recovery or \'?\'} · {lrw or \'?\'}" + (f" · {frozen_kind}" if frozen_kind else ""), "verdict": verdict},')
    d.troca('                              "hours_since_log_backup": hours_since_log, "chain_state": chain_state, "triage": triage[0],\n',
            '                              "hours_since_log_backup": hours_since_log, "chain_state": chain_state, "triage": triage[0],\n'
            '                              "frozen_kind": frozen_kind, "db_age_h": db_age_h, "snapshot_backups": snapshot_backups,\n')


def edit_old(d: Doc):
    # os 13 testes de 02/09 exercitam limiares/ordenacao/env com a regra por alocado; a fixture dizia Max_Available_MB 2000
    # num log de 1000 MB, que desde hoje e' um tecto real (-> % do tecto). Sentinela 2 TB = "sem tecto", regra por alocado.
    d.troca("        'Used_MB': pct * 10, 'Current_MB': 1000, 'Max_Available_MB': 2000,\n",
            f"        'Used_MB': pct * 10, 'Current_MB': 1000, 'Max_Available_MB': 2097152,   # {MARK}: sentinela = sem tecto real\n")


# ---------------------------------------------------------------------------------------------------------- TESTES
T_KPI_BLOCK = f'''

# ---- {MARK}: base sem ficheiros mas com tecto real na TLOG_STG
def test_legacy_com_tecto_real_usa_o_tecto():
    # ctrlm_tap_report: read-only (sem linha em DATAFILES), log 48 MB, max_size 500 MB, 99,1 % do alocado
    r = _row('SQLHDSPRD405_I01', 'ctrlm_tap_report', 99.12, 'LEGACY', cur=48, ceiling=500)
    for k in ('Drive', 'Volume_Free_MB', 'Next_Growth_MB'):
        r.pop(k)
    r['Used_MB'] = 47.58
    cls = classify_tlog([r], TH, now=NOW, unlimited_free_gb=GB)
    assert not cls['critical'] and not cls['warning']
    assert cls['reconciliation']['normal'] == 1


def test_legacy_com_tecto_real_perto_do_tecto_e_critico():
    r = _row('A', 'ro', 99.0, 'LEGACY', cur=480, ceiling=500)
    for k in ('Drive', 'Volume_Free_MB', 'Next_Growth_MB'):
        r.pop(k)
    assert _sev([r])[('A', 'ro')] == ('CRITICAL', 'TECTO')       # 475,2 / 500 = 95,04 %
    r2 = _row('A', 'ro2', 99.0, 'LEGACY', cur=450, ceiling=500)
    assert _sev([r2])[('A', 'ro2')] == ('WARNING', 'TECTO')      # 445,5 / 500 = 89,1 %


def test_legacy_com_tecto_abaixo_do_alocado_ou_sentinela_usa_o_alocado():
    # max_size reduzido abaixo do tamanho actual: o ficheiro nao cresce -> % do alocado
    r = _row('A', 'shrunk', 96.0, 'LEGACY', cur=1000, ceiling=2)
    for k in ('Drive', 'Volume_Free_MB', 'Next_Growth_MB'):
        r.pop(k)
    assert _sev([r])[('A', 'shrunk')] == ('CRITICAL', 'TECTO')
    # sentinela 2 TB (Max_Available_MB por omissao) continua a regra antiga
    r2 = _row('A', 'sent', 96.0, 'LEGACY', cur=1000, ceiling=2097152)
    for k in ('Drive', 'Volume_Free_MB', 'Next_Growth_MB'):
        r2.pop(k)
    assert _sev([r2])[('A', 'sent')] == ('CRITICAL', 'TECTO')
    assert "State_Desc" in TLOG_BASE_QUERY and "'ONLINE'" in TLOG_BASE_QUERY
'''

T_DIAG_BLOCK = f'''

# ---- {MARK}: base read-only / standby / snapshot, base recente, backups por snapshot, margem por tecto
def _ro_state(**kw):
    st = _state(lrw="LOG_BACKUP", size_mb=48, growth_mb=10, max_size=500)
    st[0].update({{"is_read_only": 1, "create_date": NOW - timedelta(days=900), "source_database_id": None}})
    st[0].update(kw)
    return st


def test_read_only_cadeia_parada_e_info_e_triagem_read_only(monkeypatch):
    # ctrlm_tap_report: 47,6 / 48 MB (99,3 %), max_size 500, volume com 383 GB livres, sem backup de log ha' 933 dias
    out = _run(monkeypatch, {{"state": _ro_state(), "counters": _counters(size_mb=48, used_mb=47.6), "bk30": [],
                             "log_stats": [{{"status": "ok", "total_vlf_count": 4, "active_vlf_count": 1, "log_backup_time": NOW - timedelta(days=933)}}],
                             "vols": _vols(free_gb=383.0, headroom_mb=452)}})
    d = out["diagnosis"]
    ids = {{p["id"]: p for p in d["problems"]}}
    assert "chain_frozen" in ids and ids["chain_frozen"]["severity"] == "info"
    assert "chain_stopped" not in ids and "drive_low" not in ids
    assert ids["log_usage"]["severity"] == "info"
    assert ids["growth_bad"]["severity"] == "info"          # FILEGROWTH 10 MB: irrelevante sem escritas
    assert d["header"]["verdict"] == "ok" and not any(p["severity"] in ("critical", "warning") for p in d["problems"])
    assert out["raw"]["derived"]["triage"] == "READ ONLY" and out["raw"]["derived"]["frozen_kind"] == "READ ONLY"
    assert d["principal"]["headline"] == "BASE READ ONLY: LOG SEM ESCRITAS" and d["since"] is None
    assert d["header"]["subtitle"].endswith("· READ ONLY")
    assert d["summary"][2]["value"] == "n/a" and d["summary"][0]["severity"] == "ok"
    assert any(r["k"] == "Estado" and r["v"] == "ONLINE · READ ONLY" for r in d["side"]["rows"])
    assert "READ ONLY" in d["nextStep"]["text"]


def test_standby_e_snapshot_tambem_congelam(monkeypatch):
    out = _run(monkeypatch, {{"state": _ro_state(is_read_only=0, is_in_standby=1), "bk30": []}})
    assert out["raw"]["derived"]["frozen_kind"] == "STANDBY" and out["raw"]["derived"]["chain_state"] == "frozen"
    out2 = _run(monkeypatch, {{"state": _ro_state(is_read_only=0, source_database_id=7), "bk30": []}})
    assert out2["raw"]["derived"]["frozen_kind"] == "SNAPSHOT"
    # read-write normal continua a cadeia parada CRITICAL
    out3 = _run(monkeypatch, {{"state": _ro_state(is_read_only=0), "bk30": [],
                              "log_stats": [{{"status": "ok", "total_vlf_count": 4, "active_vlf_count": 1, "log_backup_time": None}}]}})
    assert out3["raw"]["derived"]["chain_state"] == "never" and out3["diagnosis"]["header"]["verdict"] == "critical"


def test_base_recente_sem_backup_de_log_e_aviso_nao_critico(monkeypatch):
    st = _state(lrw="LOG_BACKUP", size_mb=1024)
    st[0]["create_date"] = NOW - timedelta(hours=3)
    out = _run(monkeypatch, {{"state": st, "counters": _counters(size_mb=1024, used_mb=300), "bk30": [],
                             "log_stats": [{{"status": "ok", "total_vlf_count": 8, "active_vlf_count": 2, "log_backup_time": None}}]}})
    d = out["diagnosis"]
    ids = {{p["id"]: p for p in d["problems"]}}
    assert "chain_new" in ids and ids["chain_new"]["severity"] == "warning" and "chain_stopped" not in ids
    assert out["raw"]["derived"]["chain_state"] == "new" and "rec_log_backup" in {{r["id"] for r in d["recommendations"]}}
    assert d["header"]["verdict"] == "warning"


def test_backups_por_snapshot_dao_pista_e_margem_por_tecto_nao_e_disco(monkeypatch):
    bk = [{{"backup_type": "D", "backup_day": (NOW - timedelta(days=1)).date().isoformat(), "backups": 1, "total_mb": 10.0,
           "max_size_mb": 10.0, "last_finish": NOW - timedelta(days=1), "copy_only_count": 0, "snapshot_count": 1}}]
    out = _run(monkeypatch, {{"bk30": bk, "log_stats": [{{"status": "ok", "total_vlf_count": 8, "active_vlf_count": 2, "log_backup_time": None}}]}})
    ids = {{p["id"] for p in out["diagnosis"]["problems"]}}
    assert "chain_snapshot_hint" in ids and "chain_stopped" in ids and out["raw"]["derived"]["snapshot_backups"] == 1
    # margem limitada pelo max_size (452 MB) com disco folgado e efectivo baixo: nao e' DISCO nem no_room
    out2 = _run(monkeypatch, {{"state": _state(lrw="LOG_BACKUP", size_mb=48, growth_mb=10, max_size=500), "counters": _counters(size_mb=48, used_mb=47.6),
                              "vols": _vols(free_gb=383.0, headroom_mb=452)}})
    ids2 = {{p["id"]: p for p in out2["diagnosis"]["problems"]}}
    assert "drive_low" not in ids2 and ids2["log_usage"]["severity"] == "warning"
    # disco mesmo curto continua critico (regressao do teste de 02/09)
    out3 = _run(monkeypatch, {{"state": _state(lrw="LOG_BACKUP", size_mb=27729), "counters": _counters(size_mb=27729, used_mb=27457),
                              "vols": _vols(free_gb=0.5, headroom_mb=512)}})
    ids3 = {{p["id"]: p for p in out3["diagnosis"]["problems"]}}
    assert ids3["drive_low"]["severity"] == "critical" and ids3["log_usage"]["severity"] == "critical"
'''


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    root = Path(argv[argv.index("--repo") + 1]).resolve() if "--repo" in argv else Path(__file__).resolve().parents[2]
    docs = {rel: Doc(root, rel) for rel in (KPI, DIAG, T_KPI, T_DIAG, T_OLD)}
    plan = ((KPI, edit_kpi), (DIAG, edit_diag), (T_KPI, lambda d: d.append(T_KPI_BLOCK)), (T_DIAG, lambda d: d.append(T_DIAG_BLOCK)),
            (T_OLD, edit_old))
    for rel, fn in plan:
        d = docs[rel]
        if d.done:
            print(f"[SKIP] {rel}: ja' tem MARK")
            continue
        fn(d)
        print(f"[OK]   {rel}: {d.n_edits} edicao(oes) preparada(s){' (CRLF)' if d.crlf else ''}")
    if check:
        print("[CHECK] ancoras ok; nada escrito")
        return 0
    for rel, d in docs.items():
        if d.done:
            continue
        dest = (preview / rel) if preview else d.path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(d.out_bytes())
        print(f"[WRITE] {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
