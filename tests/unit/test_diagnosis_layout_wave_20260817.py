"""
Wave 2026-08-17 (2) — Layout "Diagnostico" + analise do plano de execucao.

Sem BD/servico:
  1. plan_analyzer: parse deterministico de showplan XML (missing index, warnings,
     HEAP scan, estimativa vs actual, custo por operador), guardas (DOCTYPE/ENTITY,
     XML invalido), findings no contrato do layout.
  2. endpoint /api/queries/plan-analysis: modo offline (plan_xml), validacoes 400.
  3. base.py: Recommendation.effort/problem_ids e DetectedProblem existem;
     investigators passam effort.
  4. portal: componente renderDiagnosisLayout, CSS .diag-*, pilotos ligados,
     role=dialog nos 2 modais, nomenclatura L1-L5 fora do ecra.
  5. i18n: chaves diag.* nos 3 locales.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

XML = '''<?xml version="1.0" encoding="utf-16"?>
<ShowPlanXML xmlns="http://schemas.microsoft.com/sqlserver/2004/07/showplan" Version="1.5" Build="13.0.5026.0">
 <BatchSequence><Batch><Statements>
  <StmtSimple StatementText="SELECT ..." StatementId="1" StatementSubTreeCost="1679.5" StatementOptmLevel="FULL">
   <QueryPlan DegreeOfParallelism="4">
    <MissingIndexes><MissingIndexGroup Impact="87.3"><MissingIndex Database="[DW]" Schema="[dbo]" Table="[Vendas]">
      <ColumnGroup Usage="EQUALITY"><Column Name="[cid]" ColumnId="2"/></ColumnGroup>
      <ColumnGroup Usage="INCLUDE"><Column Name="[valor]" ColumnId="5"/></ColumnGroup>
    </MissingIndex></MissingIndexGroup></MissingIndexes>
    <MemoryGrantInfo RequiredMemory="4096" GrantedMemory="20480" MaxUsedMemory="18000"/>
    <Warnings><PlanAffectingConvert ConvertIssue="Seek Plan" Expression="CONVERT(date,[v].[data],0)"/></Warnings>
    <RelOp NodeId="0" PhysicalOp="Hash Match" LogicalOp="Inner Join" EstimateRows="5091960" EstimatedTotalSubtreeCost="1679.5" Parallel="1">
      <RunTimeInformation><RunTimeCountersPerThread Thread="0" ActualRows="60000000"/></RunTimeInformation>
      <Hash>
       <RelOp NodeId="1" PhysicalOp="Table Scan" LogicalOp="Table Scan" EstimateRows="5000000" EstimatedTotalSubtreeCost="1500.0">
         <RunTimeInformation><RunTimeCountersPerThread Thread="0" ActualRows="5000000"/></RunTimeInformation>
         <TableScan Ordered="0"><Object Database="[DW]" Schema="[dbo]" Table="[Vendas]" IndexKind="Heap"/></TableScan>
       </RelOp>
       <RelOp NodeId="2" PhysicalOp="Clustered Index Scan" LogicalOp="Clustered Index Scan" EstimateRows="91960" EstimatedTotalSubtreeCost="100.0">
         <IndexScan Ordered="0"><Object Database="[DW]" Schema="[dbo]" Table="[Clientes]" Index="[PK_Clientes]" IndexKind="Clustered"/></IndexScan>
       </RelOp>
      </Hash>
    </RelOp>
   </QueryPlan>
  </StmtSimple>
 </Statements></Batch></BatchSequence>
</ShowPlanXML>'''


# ---------------------------------------------------------------- 1. parser
def test_plan_parser_extracts_deterministic_facts():
    from modules.performance.plan_analyzer import parse_plan_xml
    p = parse_plan_xml(XML)
    assert p.plan_type == 'actual'
    assert p.total_subtree_cost == pytest.approx(1679.5)
    assert p.dop == 4 and p.memory_grant_kb == 20480
    assert p.relop_count == 3
    assert p.missing_indexes and p.missing_indexes[0]['impact'] == pytest.approx(87.3)
    assert p.missing_indexes[0]['equality'] == ['[cid]'] and p.missing_indexes[0]['include'] == ['[valor]']
    assert any(w['type'] == 'PlanAffectingConvert' for w in p.warnings)
    top = p.operators[0]
    assert top.physical_op == 'Table Scan' and top.index_kind == 'Heap' and top.cost_pct == pytest.approx(89.3, abs=0.2)
    assert p.tables_read.get('[DW].[dbo].[Vendas]') == 1


def test_plan_findings_contract_and_honesty():
    from modules.performance.plan_analyzer import analyze_plan_xml
    r = analyze_plan_xml(XML)
    titles = [p['title'] for p in r['problems']]
    assert any('Conversao implicita' in t for t in titles)
    assert any('Indice em falta' in t for t in titles)
    assert any('HEAP' in t for t in titles)
    assert any('Estimativa vs actual' in t for t in titles)
    for p in r['problems']:
        assert p['source'] in ('plan_actual', 'plan_estimated')
        assert p['confidence'] in ('measured', 'heuristic')
        assert p['severity'] in ('critical', 'warning', 'info', 'ok')
    # missing index so' do plano (sem DMV) = heuristica; DDL SEMPRE comentado
    mi = [p for p in r['problems'] if 'Indice em falta' in p['title']][0]
    assert mi['confidence'] == 'heuristic'
    rec = [x for x in r['recommendations'] if x['id'] in mi['recIds']][0]
    assert rec['sqlCheck'].lstrip().startswith('--') and 'CREATE NONCLUSTERED INDEX' in rec['sqlCheck']
    assert all(line.strip() == '' or line.lstrip().startswith('--') for line in rec['sqlCheck'].splitlines())
    for x in r['recommendations']:
        assert x['impact'] in ('very_high', 'high', 'medium', 'low') and x['effort'] in ('low', 'medium', 'high')


@pytest.mark.parametrize('bad', ['<!DOCTYPE x [<!ENTITY a "aaaa">]><ShowPlanXML/>', 'not xml', ''])
def test_plan_parser_guards(bad):
    from modules.performance.plan_analyzer import parse_plan_xml, PlanParseError
    with pytest.raises(PlanParseError):
        parse_plan_xml(bad)


def test_plan_parser_size_cap():
    from modules.performance.plan_analyzer import parse_plan_xml, PlanParseError, MAX_XML_BYTES
    with pytest.raises(PlanParseError):
        parse_plan_xml('<a>' + 'x' * (MAX_XML_BYTES + 10) + '</a>')


# ---------------------------------------------------------------- 2. endpoint offline
def test_plan_analysis_endpoint_offline_and_validation():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routers.queries.plan_analysis import router
    app = FastAPI(); app.include_router(router)
    c = TestClient(app)
    r = c.post('/plan-analysis/HOST_I01', json={'plan_xml': XML, 'include_qs': False})
    assert r.status_code == 200
    body = r.json()
    assert body['success'] and 'plan_xml_pasted' in body['sources']
    pa = body['plan_analysis']
    assert pa['problems'] and pa['recommendations'] and pa['verdict_text'].startswith('Analise do XML colado')
    assert c.post('/plan-analysis/HOST_I01', json={'plan_xml': '<!DOCTYPE x><a/>'}).status_code == 400
    assert c.post('/plan-analysis/HOST_I01', json={'query_hash': 'zz'}).status_code == 400
    assert c.post('/plan-analysis/HOST_I01', json={}).status_code == 400
    assert c.post('/plan-analysis/HOST_I01', json={'plan_xml': XML, 'database_name': "x'; DROP"}).status_code == 400


def test_verdict_from_cache_texts():
    from api.routers.queries.plan_analysis import _verdict_from_cache
    assert _verdict_from_cache([], None)['kind'] == 'no_cache'
    one = [{'plans_total': 1, 'plans_comparable': 1, 'execs': 10, 'first_seen': '2026-08-01T00:00:00'}]
    assert _verdict_from_cache(one, None)['kind'] == 'single'
    plans = [
        {'query_plan_hash': 'A', 'plans_total': 2, 'plans_comparable': 2, 'execs': 20, 'cpu_ratio_vs_best': 12.0, 'reads_ratio_vs_best': 9.0, 'elapsed_ratio_vs_best': 10.0,
         'min_reads': 5000, 'max_reads': 9000, 'avg_cpu_ms': 120, 'first_seen': '2026-08-10T00:00:00', 'last_seen': '2026-08-17T00:00:00', 'is_best_cpu': 0},
        {'query_plan_hash': 'B', 'plans_total': 2, 'plans_comparable': 2, 'execs': 40, 'cpu_ratio_vs_best': 1.0, 'reads_ratio_vs_best': 1.0, 'elapsed_ratio_vs_best': 1.0,
         'min_reads': 10, 'max_reads': 400, 'avg_cpu_ms': 10, 'first_seen': '2026-08-01T00:00:00', 'last_seen': '2026-08-09T00:00:00', 'is_best_cpu': 1},
    ]
    v = _verdict_from_cache(plans, None)
    assert v['kind'] == 'regression' and v['robust'] is True and v['severity'] == 'critical'
    assert 'mais barato' in v['text'] and 'nao garante' not in v['text']
    plans[0].update({'cpu_ratio_vs_best': 1.0, 'reads_ratio_vs_best': 1.0, 'elapsed_ratio_vs_best': 1.0, 'is_best_cpu': 1})
    v2 = _verdict_from_cache(plans, None)
    assert v2['kind'] == 'best' and 'nao garante que seja optimo' in v2['text']


# ---------------------------------------------------------------- 3. base.py / investigators
def test_recommendation_effort_and_detected_problem():
    from modules.performance.base import Recommendation, DetectedProblem, InvestigationResult
    r = Recommendation(action='x', description_pt='y')
    assert r.effort == '' and r.problem_ids == []
    p = DetectedProblem(id='p1', title_pt='t', evidence_pt='e')
    assert p.source == 'dmv' and p.confidence == 'measured'
    ir = InvestigationResult(investigator_id='heavy_queries', instance='X')
    assert ir.problems == [] and 'problems' in ir.to_dict()


def test_investigators_pass_effort():
    inv_dir = ROOT / 'modules' / 'performance' / 'investigators'
    for f in ['blocking_chains', 'cpu_queries', 'heavy_queries', 'memory_queries', 'missing_indexes', 'problematic_sessions', 'slow_queries', 'deadlocks']:
        src = (inv_dir / f'{f}.py').read_text(encoding='utf-8')
        assert src.count('Recommendation(') == src.count("effort='"), f
    hq = (inv_dir / 'heavy_queries.py').read_text(encoding='utf-8')
    assert 'query_plan_hash' in hq and '_grant_col' in hq  # hash + gate SQL 2014
    sq = (inv_dir / 'slow_queries.py').read_text(encoding='utf-8')
    assert 'qs.query_plan_hash' in sq and 'statement_start_offset' in sq


# ---------------------------------------------------------------- 4. portal
def test_portal_diagnosis_layout_anchors():
    portal = (ROOT / 'templates' / 'watcherdb_portal.html').read_text(encoding='utf-8')
    for a in ('function renderDiagnosisLayout', 'window.renderDiagnosisLayout', '.diag-layout {', '.diag-badge.impact-very_high',
              'function perfBuildDiagnosisSpec', 'function _diagnoseBuildLayoutHtml', 'id="diagnosePlanXml"',
              'openDiagnoseQueryModalWithCtx', 'data-perf-plan-tid', '/api/queries/plan-analysis/'):
        assert a in portal, a
    # role=dialog nos 2 modais-alvo
    assert 'class="inv-modal" role="dialog" aria-modal="true"' in portal
    assert re.search(r'id="diagnoseQueryModal"[^\n]*\n\s*<div class="sql-results-modal-content" role="dialog" aria-modal="true"', portal)
    # nomenclatura L1-L5 fora do render da Performance
    assert 'L2: Executive Summary' not in portal and 'L3: Investigation Summary' not in portal
    # nenhum bloco <script> novo sem nonce (contagem de blocos com nonce == total)
    scripts = re.findall(r'<script(?![^>]*\bsrc=)([^>]*)>', portal)
    assert all('nonce' in s for s in scripts), 'script inline sem nonce'


# ---------------------------------------------------------------- 5. i18n
def test_diag_i18n_keys_in_all_locales():
    portal = (ROOT / 'templates' / 'watcherdb_portal.html').read_text(encoding='utf-8')
    used = {k for k in re.findall(r"""\bt\(\s*['"]([a-z0-9_]+\.[a-z0-9_.]+)['"]""", portal) if k.startswith('diag.') and not k.endswith('.')}
    dyn = {'diag.impact.very_high', 'diag.impact.high', 'diag.impact.medium', 'diag.impact.low', 'diag.effort.low', 'diag.effort.medium', 'diag.effort.high',
           'diag.source.dmv', 'diag.source.plan_estimated', 'diag.source.plan_actual', 'diag.source.history', 'diag.sev.info', 'diag.sev.ok'}

    def flat(d, p=''):
        out = {}
        for k, v in d.items():
            out.update(flat(v, p + k + '.')) if isinstance(v, dict) else out.__setitem__(p + k, v)
        return out
    for loc in ('pt', 'en', 'es'):
        d = flat(json.loads((ROOT / 'static' / 'i18n' / f'{loc}.json').read_text(encoding='utf-8')))
        missing = sorted(k for k in (used | dyn) if k not in d)
        assert not missing, f'{loc}: {missing}'


# ---------------------------------------------------------------- 7. mirroring drill-down (mock DB)
def test_mirroring_diagnosis_endpoint_with_mocked_db(monkeypatch):
    import asyncio
    from datetime import datetime, timedelta
    from api.routers.queries import mirroring_diagnosis as md

    # _errorlog_recent filtra a 7 dias de datetime.now(); data literal no mock
    # fez este teste "expirar" a 2026-08-24 (escrito com '2026-08-17 10:00:00').
    errolog_dt = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')

    async def fake_exec(server_id, query, database='master'):
        q = query.upper()
        if 'SYS.DATABASE_MIRRORING M' in q and server_id == 'PRINC_I01':
            return [{'database_name': 'DbX', 'database_state': 'ONLINE', 'log_reuse_wait_desc': 'DATABASE_MIRRORING', 'recovery_model_desc': 'FULL',
                     'mirroring_state_desc': 'SUSPENDED', 'mirroring_role_desc': 'PRINCIPAL', 'mirroring_safety_level_desc': 'FULL',
                     'mirroring_witness_state_desc': None, 'mirroring_partner_instance': 'MIRR' + chr(92) + 'I01', 'log_size_mb': 20480, 'log_unlimited': 1}]
        if 'SYS.DATABASE_MIRRORING M' in q:
            return [{'mirroring_state_desc': 'SUSPENDED', 'mirroring_role_desc': 'MIRROR'}]
        if 'DBCC SQLPERF' in q:
            return [{'Database Name': 'DbX', 'Log Size (MB)': 20480, 'Log Space Used (%)': 83.5}]
        if 'DM_OS_PERFORMANCE_COUNTERS' in q:
            return [{'counter_name': 'Log Send Queue KB', 'cntr_value': 512000}, {'counter_name': 'Redo Queue KB', 'cntr_value': 0}]
        if 'XP_READERRORLOG' in q and server_id == 'MIRR_I01':
            return [{'LogDate': errolog_dt, 'Text': 'Error: 9002, Severity: 17 ... The transaction log for database DbX is full'}]
        if 'XP_READERRORLOG' in q:
            raise RuntimeError('EXECUTE permission denied on xp_readerrorlog')
        if 'DM_OS_VOLUME_STATS' in q:
            return [{'volume_mount_point': 'L:', 'total_gb': 100.0, 'free_gb': 2.0, 'free_pct': 2.0, 'file_type': 'LOG'}]
        return []
    monkeypatch.setattr(md, 'async_execute_on_server', fake_exec)
    # asyncio.run() e nao get_event_loop(): o segundo depende do estado de loop
    # deixado por testes anteriores e rebentava com "There is no current event
    # loop" consoante a ordem de execucao. Consequencia real: o drill-down de
    # mirroring shipou a 2026-08-17 com um teste que nunca chegava a correr.
    out = asyncio.run(md.mirroring_diagnosis('PRINC_I01', database='DbX', partner=None))
    d = out['diagnosis']
    ids = {p['id'] for p in d['problems']}
    assert {'log_not_truncating', 'mstate', 'mirror_errorlog', 'mirror_disk'} <= ids
    assert d['header']['verdict'] == 'critical'
    lognt = [p for p in d['problems'] if p['id'] == 'log_not_truncating'][0]
    assert '84%' in lognt['evidence'] and lognt['severity'] == 'critical'
    rec_ids = {r['id'] for r in d['recommendations']}
    assert {'rec_check_log', 'rec_errorlog', 'rec_resume', 'rec_rebuild', 'rec_legacy', 'rec_disk'} <= rec_ids
    resume = [r for r in d['recommendations'] if r['id'] == 'rec_resume'][0]
    assert 'ALTER DATABASE [DbX] SET PARTNER RESUME' in resume['sqlCheck'] and resume['sqlCheck'].splitlines()[1].startswith('--')
    # xp_readerrorlog sem permissao no principal degrada com nota, nao 500
    assert any('errorlog principal' in n for n in out['notes'])
    with pytest.raises(Exception):
        asyncio.run(md.mirroring_diagnosis('PRINC_I01', database="x'; DROP", partner=None))
