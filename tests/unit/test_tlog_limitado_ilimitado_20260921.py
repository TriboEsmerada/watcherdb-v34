# -*- coding: utf-8 -*-
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
        'Drive': 'L:\\', 'Volume_Free_MB': vol, 'Next_Growth_MB': ng,
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


# ---- 2026-09-21 (owner, ctrlm_tap_report): base sem ficheiros mas com tecto real na TLOG_STG
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
