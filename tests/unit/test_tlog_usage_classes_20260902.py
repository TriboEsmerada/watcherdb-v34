# -*- coding: utf-8 -*-
"""Contrato 2026-09-02 — classificacao partilhada do KPI Transaction Logs.

Testa a funcao pura tlog_usage_classes.classify_tlog:
  - fronteiras estritas do registry (85/95): > crit, > warn e <= crit
  - Base_Key e ordenacao Percent_Used DESC
  - INVARIANTE tile<->modal: instancias com >=1 base critica no per_instance
    == instancias distintas na lista critical (o tile conta instancias, a
    modal lista bases — os dois numeros tem de reconciliar)
  - per_instance == agregacao SQL legada (Total/Critical/Warning/Normal/
    Last_Check = MAX(Update_TS))
  - frescura 1440 por Update_TS (fail-open sem a coluna)
  - Hours_Since_Log_Backup derivado de now; sem data = None (nunca 0)
  - Log_Backup_Age: SIMPLE/UNKNOWN neutros, NEVER, LATE, OK
  - override (80/90) reclassifica — paridade registry
  - reconciliacao soma
"""
from datetime import datetime, timedelta

from api.routers.intelligence.tlog_usage_classes import classify_tlog, TLOG_BASE_QUERY

NOW = datetime(2026, 9, 2, 12, 0, 0)
TH = {'warning': 85, 'critical': 95}
LOG_LATE_H = 1  # registry backup_delay_log.warning (1h)


def _row(inst, db, pct, env='PRD', rm='FULL', last_log_h=0.5, upd_min=30, **extra):
    r = {
        'Instance': inst, 'Database': db, 'Env': env, 'Percent_Used': pct,
        'Used_MB': pct * 10, 'Current_MB': 1000, 'Max_Available_MB': 2000,
        'Update_TS': NOW - timedelta(minutes=upd_min),
        'Recovery_Model': rm,
        'Last_Log_Backup_Date': (NOW - timedelta(hours=last_log_h)) if last_log_h is not None else None,
    }
    r.update(extra)
    return r


def test_fronteiras_estritas():
    rows = [
        _row('SRV1', 'A', 85.0),    # == warn -> normal
        _row('SRV1', 'B', 85.01),   # > warn -> warning
        _row('SRV1', 'C', 95.0),    # == crit -> warning
        _row('SRV1', 'D', 95.01),   # > crit -> critical
    ]
    out = classify_tlog(rows, TH, now=NOW)
    assert [r['Database'] for r in out['critical']] == ['D']
    assert sorted(r['Database'] for r in out['warning']) == ['B', 'C']
    assert out['reconciliation']['normal'] == 1
    assert out['critical'][0]['Severity'] == 'CRITICAL'
    assert out['warning'][0]['Severity'] == 'WARNING'


def test_base_key_e_ordenacao_percent_desc():
    rows = [
        _row('srv1', 'db_b', 96.0),
        _row('SRV1', 'DB_A', 99.5),
        _row('SRV2', 'DB_Z', 97.0),
    ]
    out = classify_tlog(rows, TH, now=NOW)
    assert [r['Database'] for r in out['critical']] == ['DB_A', 'DB_Z', 'db_b']
    assert out['critical'][2]['Base_Key'] == 'SRV1|DB_B'
    # uma linha por base, sem duplicados de Base_Key
    assert len({r['Base_Key'] for r in out['critical']}) == 3


def test_invariante_tile_vs_modal():
    # SRV1: 2 criticas + 1 warning; SRV2: so' warning; SRV3: so' normal
    rows = [
        _row('SRV1', 'A', 99), _row('SRV1', 'B', 96), _row('SRV1', 'C', 90),
        _row('SRV2', 'D', 88),
        _row('SRV3', 'E', 10),
    ]
    out = classify_tlog(rows, TH, now=NOW)
    inst_crit_tile = [a for a in out['per_instance'] if a['Critical'] > 0]
    assert len(inst_crit_tile) == 1  # o que o tile mostra
    assert {r['Instance'] for r in out['critical']} == {'SRV1'}
    assert out['reconciliation']['instances_critical'] == 1
    assert out['reconciliation']['instances_warning_only'] == 1
    assert out['bases_critical_count'] == 2  # o que o cabecalho da modal mostra
    assert out['bases_warning_count'] == 2
    # a linha warning de SRV1 vai para a modal WARNING mas sabe que a
    # instancia e' critica (badge/contexto)
    c_row = [r for r in out['warning'] if r['Database'] == 'C'][0]
    assert c_row['Instance_Severity'] == 'CRITICAL'
    d_row = [r for r in out['warning'] if r['Database'] == 'D'][0]
    assert d_row['Instance_Severity'] == 'WARNING'


def test_per_instance_igual_agregacao_legada():
    t0 = NOW - timedelta(minutes=50)
    t1 = NOW - timedelta(minutes=5)
    rows = [
        _row('SRV1', 'A', 99, upd_min=50), _row('SRV1', 'B', 90, upd_min=5),
        _row('SRV1', 'C', 10, upd_min=20), _row('SRV1', 'D', 20, upd_min=30),
    ]
    out = classify_tlog(rows, TH, now=NOW)
    agg = out['per_instance']
    assert len(agg) == 1
    a = agg[0]
    assert (a['Instance'], a['Env']) == ('SRV1', 'PRD')
    assert (a['Total_Databases'], a['Critical'], a['Warning'], a['Normal']) == (4, 1, 1, 2)
    assert a['Last_Check'] == t1
    assert t0 < a['Last_Check']


def test_frescura_1440_fail_open_sem_coluna():
    rows = [
        _row('SRV1', 'OLD', 99, upd_min=1441),   # velha -> sai
        _row('SRV1', 'NEW', 99, upd_min=1439),   # fresca -> entra
    ]
    out = classify_tlog(rows, TH, now=NOW)
    assert [r['Database'] for r in out['critical']] == ['NEW']
    assert out['reconciliation']['rows_fresh'] == 1
    # sem coluna Update_TS: passa (mesmo criterio do card)
    nots = _row('SRV1', 'X', 99)
    del nots['Update_TS']
    out2 = classify_tlog([nots], TH, now=NOW)
    assert len(out2['critical']) == 1
    assert out2['critical'][0]['Last_Check'] is None


def test_hours_since_log_backup_derivado_e_none_nunca_zero():
    rows = [
        _row('SRV1', 'A', 99, last_log_h=3.25),
        _row('SRV1', 'B', 99, last_log_h=None),
        _row('SRV1', 'C', 99, last_log_h=-2),   # relogio a frente -> 0, nao negativo
    ]
    out = classify_tlog(rows, TH, now=NOW, log_late_hours=LOG_LATE_H)
    by = {r['Database']: r for r in out['critical']}
    assert by['A']['Hours_Since_Log_Backup'] == 3.2 or by['A']['Hours_Since_Log_Backup'] == 3.3
    assert by['B']['Hours_Since_Log_Backup'] is None
    assert by['C']['Hours_Since_Log_Backup'] == 0.0


def test_log_backup_age_buckets():
    rows = [
        _row('SRV1', 'SIMPLE_NO_BKP', 99, rm='SIMPLE', last_log_h=None),
        _row('SRV1', 'SIMPLE_WITH_BKP', 99, rm='SIMPLE', last_log_h=100),
        _row('SRV1', 'UNKNOWN_NO_BKP', 99, rm=None, last_log_h=None),
        _row('SRV1', 'UNKNOWN_WITH_BKP', 99, rm=None, last_log_h=0.2),
        _row('SRV1', 'FULL_NEVER', 99, rm='FULL', last_log_h=None),
        _row('SRV1', 'BULK_NEVER', 99, rm='BULK_LOGGED', last_log_h=None),
        _row('SRV1', 'FULL_LATE', 99, rm='FULL', last_log_h=1.5),
        _row('SRV1', 'FULL_OK', 99, rm='FULL', last_log_h=0.9),
    ]
    out = classify_tlog(rows, TH, now=NOW, log_late_hours=LOG_LATE_H)
    by = {r['Database']: r['Log_Backup_Age'] for r in out['critical']}
    assert by['SIMPLE_NO_BKP'] == 'SIMPLE'
    assert by['SIMPLE_WITH_BKP'] == 'SIMPLE'      # recovery manda: neutro
    assert by['UNKNOWN_NO_BKP'] == 'UNKNOWN'      # neutro, nunca NEVER
    assert by['UNKNOWN_WITH_BKP'] == 'OK'
    assert by['FULL_NEVER'] == 'NEVER'
    assert by['BULK_NEVER'] == 'NEVER'
    assert by['FULL_LATE'] == 'LATE'
    assert by['FULL_OK'] == 'OK'


def test_log_late_none_nunca_marca_late():
    rows = [_row('SRV1', 'A', 99, rm='FULL', last_log_h=500)]
    out = classify_tlog(rows, TH, now=NOW, log_late_hours=None)
    assert out['critical'][0]['Log_Backup_Age'] == 'OK'


def test_override_reclassifica():
    rows = [_row('SRV1', 'A', 92)]
    assert len(classify_tlog(rows, TH, now=NOW)['critical']) == 0
    out = classify_tlog(rows, {'warning': 80, 'critical': 90}, now=NOW)
    assert len(out['critical']) == 1
    assert out['critical'][0]['Threshold_Critical'] == 90.0
    assert out['critical'][0]['Threshold_Warning'] == 80.0


def test_env_normalizado_e_by_env():
    rows = [
        _row('SQLHDSPRD1', 'A', 99, env='Undefined'),  # inferido do nome -> PRD
        _row('SQLHDSQLT1', 'B', 99, env='QLT'),
        _row('OUTRO', 'C', 90, env=None),               # fica Undefined
    ]
    out = classify_tlog(rows, TH, now=NOW)
    assert out['bases_critical_by_env'] == {'PRD': 1, 'QLT': 1, 'TST': 0, 'Undefined': 0}
    assert out['bases_warning_by_env'] == {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 1}
    assert out['per_instance'][0]['Env'] in ('PRD', 'QLT', 'Undefined')
    # a chave interna nao vaza para o payload
    assert all('_env_key' not in r for r in out['critical'] + out['warning'])


def test_reconciliacao_soma():
    rows = [_row('S', 'A', 99), _row('S', 'B', 90), _row('S', 'C', 5), _row('S', 'D', 99, upd_min=5000)]
    out = classify_tlog(rows, TH, now=NOW)
    rc = out['reconciliation']
    assert rc['critical'] + rc['warning'] + rc['normal'] == rc['rows_fresh'] == 3


def test_payload_nao_traz_contadores_por_instancia():
    # o card generico do portal infere badge por Critical/Warning — por base
    # esses campos NAO podem existir (mostraria contagem em vez do nome)
    out = classify_tlog([_row('S', 'A', 99)], TH, now=NOW)
    r = out['critical'][0]
    assert 'Critical' not in r and 'Warning' not in r and 'Total_Databases' not in r
    assert r['Last_Check'] == r['Update_TS']


def test_query_formata_schema_e_e_select_only():
    q = TLOG_BASE_QUERY.format(schema='dbo')
    assert 'dbo.KPI_MSSQL_TLOG_USAGE_ACTIVE' in q
    assert 'dbo.KPI_MSSQL_BACKUPS_STG' in q
    assert 'dbo.KPI_MSSQL_DB_SETTINGS_STG' in q
    assert 'dbo.KPI_MSSQL_ALWAYSON_STATUS_STG' in q
    low = q.lower()
    for kw in ('insert ', 'update ', 'delete ', 'drop ', 'alter ', 'truncate '):
        assert kw not in low
