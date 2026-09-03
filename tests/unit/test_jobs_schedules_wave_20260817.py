"""
Wave 2026-08-17 — Agendamentos na aba Jobs / proxima execucao no KPI Backup Failed /
Jobs de Backup na aba Backup / origem externa (TDP).

Cobre, SEM tocar BD nem servico (mocks/puro):
  1. Modelos de resposta do modulo Jobs aceitam o payload real (F0 — o modulo estava
     a zeros desde 16/04 porque server_id era obrigatorio sem extra=allow).
  2. FastAPI serializa esses modelos SEM perder os campos extra (failed_jobs, etc.).
  3. jobs.py nao usa msdb.dbo.agent_datetime (F1a) e o helper inline e' SQL valido
     na forma (guarda > 0, CONVERT 112).
  4. Classificador de origem de backup (F4) — TDP/Commvault/VDI vs disco/tape.
  5. Query do KPI backup-failed normaliza Instance (backslash -> underscore) no JOIN.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1 + 2. Modelos do modulo Jobs
# ---------------------------------------------------------------------------
def test_jobs_models_accept_real_payload_and_keep_extras():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.models import JobsAnalysisResponse, JobTrendsResponse, JobConflictsResponse

    app = FastAPI()

    @app.get('/j', response_model=JobsAnalysisResponse)
    def j():
        return {'success': True, 'server_id': 'X_I01', 'total_jobs': 11,
                'all_jobs': [{'job_name': 'a', 'backup_type_classified': 'FULL'}],
                'failed_jobs': [{'job_name': 'b'}], 'job_schedules': [{'job_id': '1', 'freq_type': 4}],
                'maintenance_jobs': [], 'jobs_without_active_schedule': 2}

    @app.get('/t', response_model=JobTrendsResponse)
    def t():
        return {'success': True, 'server_id': 'X', 'periods': {'short': {'days': 7}}}

    @app.get('/c', response_model=JobConflictsResponse)
    def c():
        return {'success': True, 'server_id': 'X', 'schedule_conflicts': [1]}

    cl = TestClient(app)
    r = cl.get('/j').json()
    assert r['total_jobs'] == 11
    assert isinstance(r['all_jobs'], list) and r['all_jobs'][0]['backup_type_classified'] == 'FULL'
    assert r['failed_jobs'] == [{'job_name': 'b'}]          # extra preservado
    assert r['jobs_without_active_schedule'] == 2            # extra preservado
    assert cl.get('/t').json()['periods']['short']['days'] == 7
    assert cl.get('/c').json()['schedule_conflicts'] == [1]


def test_jobs_models_do_not_require_server_id():
    # A causa-raiz do modulo a zeros: payload sem server_id tem de VALIDAR.
    from api.models import JobsAnalysisResponse
    m = JobsAnalysisResponse(total_jobs=3, all_jobs=[])
    assert m.success is True and m.server_id is None


# ---------------------------------------------------------------------------
# 3. jobs.py sem agent_datetime + helper inline
# ---------------------------------------------------------------------------
def test_jobs_router_has_no_agent_datetime_calls():
    src = (ROOT / 'api' / 'routers' / 'jobs.py').read_text(encoding='utf-8')
    code_lines = [l for l in src.splitlines() if not l.strip().startswith('#') and 'def _agent_dt' not in l]
    body = '\n'.join(code_lines)
    # docstring do helper menciona o nome; excluir docstrings triplas
    body_no_doc = re.sub(r'""".*?"""', '', body, flags=re.S)
    assert 'agent_datetime(' not in body_no_doc, 'msdb.dbo.agent_datetime exige EXECUTE e nao e sargavel'


def test_agent_dt_helper_shape():
    from api.routers.jobs import _agent_dt, _run_date_floor
    s = _agent_dt('h.run_date', 'h.run_time')
    assert s.startswith('CASE WHEN h.run_date > 0 THEN DATEADD(SECOND')
    assert "CONVERT(DATETIME, CAST(h.run_date AS CHAR(8)), 112)" in s
    assert s.endswith('END')
    f = _run_date_floor('DATEADD(HOUR, -25, GETDATE())')
    assert f == 'CONVERT(INT, CONVERT(CHAR(8), DATEADD(HOUR, -25, GETDATE()), 112))'


def test_backup_type_classifier_parity_with_kpi():
    # Um so classificador (helpers.classify_backup_type) — casos reais + adversarial documentado.
    from api.routers.jobs import _classify_backup_type
    assert _classify_backup_type('CSE06 Full Backup') == 'FULL'
    assert _classify_backup_type('DBA_SQLX_I01_LOG_BACKUP') == 'LOG'
    assert _classify_backup_type('DatabaseBackup - USER_DATABASES - DIFF') == 'DIFF'
    assert _classify_backup_type('') == 'OTHER'
    # Fraqueza conhecida (substring 'LOG' em CATALOG) — mantida por paridade com o KPI;
    # se um dia se mudar helpers.classify_backup_type, este assert deve mudar junto.
    assert _classify_backup_type('DBA_CATALOG_BACKUP') == 'LOG'


# ---------------------------------------------------------------------------
# 4. Origem do backup (ferramentas externas)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('device_type,phys,user,exp_source,exp_tool,exp_ext', [
    (7, 'TDPSQL-0000123', 'DOM\\svc_tsm', 'VIRTUAL_DEVICE', 'TDP', True),
    (7, 'CV_GALAXY_12', 'DOM\\cvsvc', 'VIRTUAL_DEVICE', 'COMMVAULT', True),
    (7, '{3F2504E0-4F89-11D3-9A0C-0305E82C3301}', 'x', 'VIRTUAL_DEVICE', 'OTHER', True),
    (2, 'F:\\Backups\\db.bak', 'sa', 'DISK', None, False),
    (5, '\\\\.\\Tape0', 'sa', 'TAPE', None, False),
    (9, 'https://acct.blob.core.windows.net/c/db.bak', 'sa', 'URL', None, False),
    (None, None, None, 'UNKNOWN', None, False),
    ('7', 'VNBU0-1234', None, 'VIRTUAL_DEVICE', 'NETBACKUP', True),
])
def test_classify_backup_source(device_type, phys, user, exp_source, exp_tool, exp_ext):
    from modules.monitoring.backup_analysis import classify_backup_source
    r = classify_backup_source(device_type, phys, user)
    assert r['source'] == exp_source
    assert r['tool'] == exp_tool
    assert r['is_external'] is exp_ext


def test_backup_source_from_row_shape_and_backcompat():
    from modules.monitoring.backup_analysis import _backup_source_from_row
    assert _backup_source_from_row({'database_name': 'x'}) is None          # query antiga
    r = _backup_source_from_row({'full_device_type': 7, 'full_physical_device': 'TDPSQL-1',
                                 'log_device_type': 2, 'log_physical_device': 'x.trn', 'log_user_name': 'sa'})
    assert set(r.keys()) == {'FULL', 'LOG'}
    assert r['FULL']['tool'] == 'TDP' and r['LOG']['source'] == 'DISK'


def test_database_backup_status_has_backup_source_default():
    from modules.monitoring.backup_analysis import DatabaseBackupStatus
    from dataclasses import asdict
    s = DatabaseBackupStatus('db', 'FULL', None, None, None, None, None, None, [])
    assert asdict(s)['backup_source'] is None


# ---------------------------------------------------------------------------
# 5. KPI backup-failed: JOIN a AGENT_JOBS_STG normaliza Instance
# ---------------------------------------------------------------------------
def test_kpi_backup_failed_join_normalizes_instance():
    src = (ROOT / 'api' / 'routers' / 'intelligence_kpis.py').read_text(encoding='utf-8')
    assert 'KPI_MSSQL_AGENT_JOBS_STG AS aj' in src
    # no ficheiro Python fica '\\\\' (2 chars) que renderiza '\' no T-SQL
    assert "REPLACE(aj.Instance, '\\\\', '_')" in src
    for col in ('Next_Run_Date', 'Has_Schedule', 'Job_Enabled', 'Jobs_Snapshot_TS', 'Job_Missing_In_Snapshot'):
        assert col in src


# ---------------------------------------------------------------------------
# 6. Portal: i18n das chaves novas nos 3 locales + secao/anchors presentes
# ---------------------------------------------------------------------------
def test_portal_new_i18n_keys_present_in_all_locales():
    import json
    portal = (ROOT / 'templates' / 'watcherdb_portal.html').read_text(encoding='utf-8')
    used = set(re.findall(r"""\bt\(\s*['"]([a-z0-9_]+\.[a-z0-9_.]+)['"]""", portal))
    mine = {k for k in used if k.split('.')[0] in ('jobs', 'kpi_modal', 'backup') and not k.endswith('_')}

    def flat(d, p=''):
        out = {}
        for k, v in d.items():
            if isinstance(v, dict):
                out.update(flat(v, p + k + '.'))
            else:
                out[p + k] = v
        return out

    for loc in ('pt', 'en', 'es'):
        d = flat(json.loads((ROOT / 'static' / 'i18n' / f'{loc}.json').read_text(encoding='utf-8')))
        missing = sorted(k for k in mine if k not in d)
        assert not missing, f'{loc}: chaves em falta {missing}'


def test_portal_anchors_of_this_wave():
    portal = (ROOT / 'templates' / 'watcherdb_portal.html').read_text(encoding='utf-8')
    for anchor in ('id="schedules-section"', 'function _formatJobSchedule', 'function _kpiJobNextRunHtml',
                   'function _backupSourceBadges', '${backupJobsSectionHtml}', "'schedules-section'",
                   'function _jobsFilterRoot'):
        assert anchor in portal, anchor
    # bug j.name: nenhum filtro/render restante so' por j.name nas seccoes de backup
    assert "(j.name || '').toLowerCase().includes(kw)" not in portal
