# -*- coding: utf-8 -*-
"""Contrato do council 2026-09-01 — classificacao do Backup Delayed (R1-R5).

Testa a funcao pura backup_delayed_classes.classify_delayed:
  - chain-reset transitorio (perdao f15bfb8) vs perdao EXPIRADO (FULL velho)
  - schedule DIFF parado >7d = banda propria, nunca engolida
  - system DB de no AG -> ag_system_gap (e DBA_* NAO e' system)
  - chave (AgName, Database) nas linhas AG (condicao v1-intel)
  - dedupe por base no executivo (R1)
  - INVARIANTE RPO (challenger): nenhuma base com restore point mais velho
    que o critical de FULL fica sem alarme em superficie nenhuma
  - reconciliacao soma (persona R5)
"""
from datetime import datetime, timedelta

from api.routers.intelligence.backup_delayed_classes import (
    classify_delayed, build_ag_map, DIFF_STOPPED_HOURS)

NOW = datetime(2026, 9, 1, 12, 0, 0)
TH = {
    'FULL': {'warning_h': 120, 'critical_h': 168},
    'DIFF': {'warning_h': 24, 'critical_h': 30},
    'LOG':  {'warning_h': 1, 'critical_h': 2},
}


def _row(inst, db, btype, hours, last=None, env='PRD'):
    last = last if last is not None else NOW - timedelta(hours=hours)
    return {
        'Instance': inst, 'Database': db, 'Backup_Type': btype,
        'Hours_Since_Backup': hours, 'Last_Backup_Date': last,
        'Update_TS': NOW - timedelta(minutes=30), 'Env': env,
    }


def test_chain_reset_transitorio():
    # DIFF de ontem (40h > warning 24h) coberto por FULL de hoje (fresco)
    rows = [
        _row('SRV1', 'DB1', 'D', 10),
        _row('SRV1', 'DB1', 'I', 40),
    ]
    out = classify_delayed(rows, TH, now=NOW)
    assert len(out['chain_reset']) == 1
    assert out['chain_reset'][0]['Delay_Class'] == 'chain_reset'
    assert out['bases_critical_count'] + out['bases_warning_count'] == 0


def test_perdao_expira_com_full_velho():
    # FULL mais recente que o DIFF mas o PROPRIO FULL ja passou o warning
    # (130h > 120h): perdao expirado -> DIFF volta a contar (challenger).
    rows = [
        _row('SRV1', 'DB1', 'D', 130),
        _row('SRV1', 'DB1', 'I', 200),
    ]
    out = classify_delayed(rows, TH, now=NOW)
    assert len(out['chain_reset']) == 0
    assert len(out['diff_schedule_stopped']) == 0
    delayed = out['actionable_critical'] + out['actionable_warning']
    assert any(r['Backup_Type'] == 'I' for r in delayed)


def test_schedule_diff_parado_banda_propria():
    # DIFF parado ha 20 dias com FULL fresco: NAO e' chain-reset transitorio
    # (classe TAON, M1: 33 casos) — banda propria visivel.
    rows = [
        _row('SRV1', 'DB1', 'D', 10),
        _row('SRV1', 'DB1', 'I', 480),
    ]
    out = classify_delayed(rows, TH, now=NOW)
    assert len(out['diff_schedule_stopped']) == 1
    assert out['diff_schedule_stopped'][0]['Delayed_Severity'] == 'warning'
    assert len(out['chain_reset']) == 0


def test_system_db_de_no_ag_roteada_e_dba_fica():
    ag_map = build_ag_map([
        {'Instance_N': 'SRV1', 'Database_N': 'APPDB', 'AgName': 'AG1'},
    ])
    rows = [
        _row('SRV1', 'msdb', 'D', 500),          # system DB em no AG -> gap
        _row('SRV1', 'DBA_RESOURCE_DB', 'D', 500),  # user DB -> continua delayed
        _row('SRV2', 'msdb', 'D', 500),          # system DB em no NAO-AG -> delayed
    ]
    out = classify_delayed(rows, TH, ag_map=ag_map, now=NOW)
    assert len(out['ag_system_gap']) == 1
    assert out['ag_system_gap'][0]['Instance'] == 'SRV1'
    delayed_dbs = {r['Database'] for r in out['actionable_critical']}
    assert 'DBA_RESOURCE_DB' in delayed_dbs
    assert 'msdb' in delayed_dbs  # o do SRV2 (sem AG)


def test_chave_ag_correlaciona_entre_representantes():
    # AG_CONSOLIDATED: FULL representado pelo NO-A, DIFF pelo NO-B (pos-failover).
    # Sem ag_map, (Instance,Database) nao correlaciona e o DIFF contaria;
    # com ag_map, a chave (AgName,Database) une-os -> chain_reset.
    ag_map = build_ag_map([
        {'Instance_N': 'NOA', 'Database_N': 'APPDB', 'AgName': 'AG1'},
        {'Instance_N': 'NOB', 'Database_N': 'APPDB', 'AgName': 'AG1'},
    ])
    rows = [
        _row('NOA', 'APPDB', 'D', 10),
        _row('NOB', 'APPDB', 'I', 40),
    ]
    out = classify_delayed(rows, TH, ag_map=ag_map, now=NOW)
    assert len(out['chain_reset']) == 1
    out_sem_mapa = classify_delayed([dict(r) for r in rows], TH, now=NOW)
    assert len(out_sem_mapa['chain_reset']) == 0  # prova que a chave importa


def test_dedupe_por_base_no_executivo():
    # Uma base com FULL+DIFF+LOG todos parados = 1 base critica, nao 3 (R1).
    rows = [
        _row('SRV1', 'DB1', 'D', 500),
        _row('SRV1', 'DB1', 'I', 500),
        _row('SRV1', 'DB1', 'L', 500),
    ]
    out = classify_delayed(rows, TH, now=NOW)
    assert out['bases_critical_count'] == 1
    assert len(out['actionable_critical']) == 3  # detalhe por tipo preservado
    assert out['delayed_critical_by_env']['PRD'] == 1


def test_invariante_rpo():
    # Challenger: nenhuma base com restore point (melhor de FULL/DIFF/LOG)
    # alem do critical de FULL pode ficar sem alarme em superficie NENHUMA.
    rows = [
        _row('SRV1', 'DB1', 'D', 500),   # tudo velho
        _row('SRV1', 'DB1', 'I', 500),
    ]
    out = classify_delayed(rows, TH, now=NOW)
    surfaced = (out['actionable_critical'] + out['actionable_warning']
                + out['diff_schedule_stopped'] + out['ag_system_gap'])
    assert any((r['Instance'], r['Database']) == ('SRV1', 'DB1') for r in surfaced)
    assert out['bases_critical_count'] >= 1


def test_reconciliacao_soma():
    ag_map = build_ag_map([
        {'Instance_N': 'SRV1', 'Database_N': 'X', 'AgName': 'AG1'},
    ])
    rows = [
        _row('SRV1', 'msdb', 'D', 500),
        _row('SRV2', 'DB1', 'D', 10),
        _row('SRV2', 'DB1', 'I', 40),
        _row('SRV3', 'DB2', 'I', 480),
        _row('SRV3', 'DB2', 'D', 10),
        _row('SRV4', 'DB3', 'L', 5),
    ]
    out = classify_delayed(rows, TH, ag_map=ag_map, now=NOW)
    rec = out['reconciliation']
    assert rec['rows_past_threshold'] == (
        rec['actionable_rows'] + rec['chain_reset']
        + rec['diff_schedule_stopped'] + rec['ag_system_gap'])
    assert rec['chain_reset'] == 1        # SRV2/DB1 DIFF
    assert rec['diff_schedule_stopped'] == 1  # SRV3/DB2 DIFF 480h
    assert rec['ag_system_gap'] == 1      # SRV1/msdb
    assert rec['actionable_rows'] == 1    # SRV4/DB3 LOG


def test_bandas_contam_bases_nao_linhas():
    # Owner 02/09 ("baixar tambem os avisos"): msdb de um no' AG com FULL+DIFF
    # em atraso = 1 base no contador da banda, nao 2 (mesma regra R1).
    ag_map = build_ag_map([
        {'Instance_N': 'SRV1', 'Database_N': 'APPDB', 'AgName': 'AG1'},
    ])
    rows = [
        _row('SRV1', 'msdb', 'D', 500),
        _row('SRV1', 'msdb', 'I', 500),
        _row('SRV1', 'model', 'D', 500),
    ]
    out = classify_delayed(rows, TH, ag_map=ag_map, now=NOW)
    assert len(out['ag_system_gap']) == 3           # linhas preservadas (modal)
    assert out['ag_system_gap_bases_count'] == 2    # msdb + model
    assert out['ag_system_gap_by_env']['PRD'] == 2


def test_base_severity_segue_o_pior_da_base():
    # Owner 01/09 (tile 2 vs modal 5): linha warning de base critica leva
    # Base_Severity='critical' — pertence a' modal CRITICO, igual ao tile.
    rows = [
        _row('SRV1', 'DB1', 'D', 130),   # FULL warning (120<130<168)
        _row('SRV1', 'DB1', 'L', 500),   # LOG critical -> base critica
        _row('SRV2', 'DB2', 'D', 130),   # base so' warning
    ]
    out = classify_delayed(rows, TH, now=NOW)
    warn_rows = {(r['Instance'], r['Backup_Type']): r for r in out['actionable_warning']}
    assert warn_rows[('SRV1', 'D')]['Base_Severity'] == 'critical'
    assert warn_rows[('SRV2', 'D')]['Base_Severity'] == 'warning'
    assert out['bases_critical_count'] == 1
    assert out['bases_warning_count'] == 1


def test_c1_null_hours_nunca_saudavel():
    # Gate sql-deep C1: hours NULL derivado da data; sem data = fail-closed.
    rows = [
        {'Instance': 'SRV1', 'Database': 'DB1', 'Backup_Type': 'D',
         'Hours_Since_Backup': None, 'Last_Backup_Date': NOW - timedelta(hours=500),
         'Update_TS': NOW - timedelta(minutes=30), 'Env': 'PRD'},
        {'Instance': 'SRV2', 'Database': 'DB2', 'Backup_Type': 'D',
         'Hours_Since_Backup': None, 'Last_Backup_Date': None,
         'Update_TS': NOW - timedelta(minutes=30), 'Env': 'PRD'},
    ]
    out = classify_delayed(rows, TH, now=NOW)
    surfaced = out['actionable_critical'] + out['actionable_warning']
    assert {(r['Instance']) for r in surfaced} == {'SRV1', 'SRV2'}
    assert out['bases_critical_count'] == 2
