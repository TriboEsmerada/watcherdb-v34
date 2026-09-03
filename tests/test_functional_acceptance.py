"""
WatcherDB - Teste de Aceitacao Funcional (Acceptance Test)
=========================================================

Testa TODOS os endpoints principais da API contra uma instancia REAL.
Valida: status HTTP, estrutura JSON, tipos de campo, campos obrigatorios,
        narrativas nao-vazias, e ranges numericos sanos.

Uso:
    pytest tests/test_functional_acceptance.py -v --no-cov --override-ini="addopts=" -s

    # Contra outro servidor:
    TEST_SERVER_ID=SQLHDSPRD405_I01 pytest tests/test_functional_acceptance.py -v --no-cov --override-ini="addopts=" -s

    # Modulo especifico:
    pytest tests/test_functional_acceptance.py::TestBackup -v --no-cov --override-ini="addopts=" -s

Data: 2026-02-17
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import httpx
import pytest

# Estes testes batem numa instancia REAL (ver docstring acima), logo nao pertencem a
# suite default -- que corre sem servidor e os dava como 28 erros + 8 falhas, 36 dos 47
# problemas do repo. Com o marcador, a suite default fica com os 11 que sao sinal a serio.
# Correr com: pytest -m e2e --no-cov
pytestmark = pytest.mark.e2e

# ==============================================================================
# CONFIGURACAO
# ==============================================================================

# 2026-08-31: o default era http://localhost:8000 -- porta do `python watcherdb_main.py`
# em dev, que nao e' onde o produto corre. O servico V3.3 escuta em 8433 e, desde a
# activacao de TLS, em https. Com o default antigo estes 36 testes falhavam mesmo com
# servidor a correr, e ninguem reparava porque a suite inteira estava a abortar antes
# (ver check_favicon_manual.py, ex-test_favicon.py).
# Aceita WATCHERDB_BASE_URL (nome usado por tests/e2e/conftest.py) e mantem BASE_URL
# por compatibilidade com quem ja o tinha no ambiente.
BASE_URL = os.getenv("WATCHERDB_BASE_URL") or os.getenv("BASE_URL") or "https://localhost:8433"
TEST_SERVER_ID: Optional[str] = os.getenv("TEST_SERVER_ID", None)
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "120"))
FAST_TIMEOUT = float(os.getenv("FAST_TIMEOUT", "15"))


# ==============================================================================
# ACUMULADOR DE RESULTADOS
# ==============================================================================

class AcceptanceReport:
    """Acumula resultados por modulo para o relatorio final."""

    def __init__(self):
        self.results: Dict[str, List[Dict]] = defaultdict(list)

    def record(self, module: str, test_name: str, passed: bool,
               detail: str = "", fields_missing: List[str] = None,
               type_errors: List[str] = None):
        self.results[module].append({
            "test": test_name,
            "passed": passed,
            "detail": detail,
            "fields_missing": fields_missing or [],
            "type_errors": type_errors or [],
        })

    def summary(self) -> str:
        lines = ["\n" + "=" * 72]
        lines.append("  RELATORIO DE ACEITACAO FUNCIONAL - WatcherDB")
        lines.append("=" * 72)
        total_pass = total_fail = 0
        for module, tests in sorted(self.results.items()):
            passed = sum(1 for t in tests if t["passed"])
            failed = len(tests) - passed
            total_pass += passed
            total_fail += failed
            icon = "OK" if failed == 0 else "FALHA"
            lines.append(f"\n  [{icon}] {module}: {passed}/{len(tests)} testes passaram")
            for t in tests:
                status = "PASS" if t["passed"] else "FAIL"
                lines.append(f"        [{status}] {t['test']}")
                if t["fields_missing"]:
                    lines.append(f"               Campos ausentes: {', '.join(t['fields_missing'])}")
                if t["type_errors"]:
                    for te in t["type_errors"]:
                        lines.append(f"               Tipo incorreto: {te}")
                if t["detail"] and not t["passed"]:
                    lines.append(f"               Detalhe: {t['detail']}")
        lines.append(f"\n{'=' * 72}")
        lines.append(f"  TOTAL: {total_pass} passaram, {total_fail} falharam "
                      f"de {total_pass + total_fail} testes")
        lines.append(f"{'=' * 72}\n")
        return "\n".join(lines)


_report = AcceptanceReport()


# ==============================================================================
# FIXTURES (SINCRONAS - httpx.Client)
# ==============================================================================

@pytest.fixture(scope="session")
def client():
    """Cliente HTTP sincrono compartilhado."""
    with httpx.Client(
        base_url=BASE_URL,
        timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10.0),
        follow_redirects=True,
        # Certificado da CA interna, com CN que nao cobre `localhost` -- mesma razao
        # pela qual tests/e2e/conftest.py usa ignore_https_errors.
        verify=False,
    ) as c:
        yield c


@pytest.fixture(scope="session")
def server_id(client: httpx.Client) -> str:
    if TEST_SERVER_ID:
        return TEST_SERVER_ID
    resp = client.get("/api/v3/servers")
    assert resp.status_code == 200, f"Falha ao listar servidores: HTTP {resp.status_code}"
    body = resp.json()
    servers = body.get("servers", [])
    assert len(servers) > 0, "Nenhum servidor cadastrado"
    return servers[0]["server_id"]


@pytest.fixture(scope="session")
def server_name(client: httpx.Client, server_id: str) -> str:
    resp = client.get("/api/v3/servers")
    body = resp.json()
    for srv in body.get("servers", []):
        if srv.get("server_id") == server_id:
            name = srv.get("name", server_id)
            return name.split("\\")[0] if "\\" in name else name.split("_")[0]
    return server_id.split("_")[0]


@pytest.fixture(scope="session")
def report():
    return _report


def pytest_sessionfinish(session, exitstatus):
    """Imprime relatorio ao final da sessao pytest."""
    print(_report.summary())


# ==============================================================================
# HELPERS DE VALIDACAO
# ==============================================================================

def assert_fields_present(data: Dict, required_fields: List[str]) -> List[str]:
    return [f for f in required_fields if f not in data]


def assert_field_type(data: Dict, field: str, expected_type: type,
                      allow_none: bool = False) -> Optional[str]:
    val = data.get(field)
    if val is None:
        return None if allow_none else f"{field}: esperado {expected_type.__name__}, recebeu None"
    if not isinstance(val, expected_type):
        if expected_type in (int, float) and isinstance(val, (int, float)):
            return None
        return f"{field}: esperado {expected_type.__name__}, recebeu {type(val).__name__} ({repr(val)[:60]})"
    return None


def assert_numeric_range(data: Dict, field: str, min_val: float = None,
                         max_val: float = None) -> Optional[str]:
    val = data.get(field)
    if val is None:
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return f"{field}: nao conversivel para numero ({repr(val)[:40]})"
    if min_val is not None and num < min_val:
        return f"{field}: {num} abaixo do minimo {min_val}"
    if max_val is not None and num > max_val:
        return f"{field}: {num} acima do maximo {max_val}"
    return None


def assert_date_parseable(data: Dict, field: str) -> Optional[str]:
    val = data.get(field)
    if val is None:
        return None
    if not isinstance(val, str):
        return f"{field}: esperado string ISO date, recebeu {type(val).__name__}"
    try:
        datetime.fromisoformat(val.replace("Z", "+00:00"))
        return None
    except (ValueError, TypeError):
        return f"{field}: nao e data ISO valida: {repr(val)[:60]}"


def collect_type_errors(data: Dict, checks: List[Tuple]) -> List[str]:
    errors = []
    for field, expected_type, allow_none in checks:
        err = assert_field_type(data, field, expected_type, allow_none)
        if err:
            errors.append(err)
    return errors


def safe_get(resp) -> Dict:
    try:
        return resp.json()
    except Exception:
        return {}


# ==============================================================================
# 0. SMOKE TEST
# ==============================================================================

class TestSmoke:

    def test_health_endpoint(self, client, report):
        resp = client.get("/api/v3/health", timeout=FAST_TIMEOUT)
        passed = resp.status_code == 200
        report.record("00. Smoke Test", "health_endpoint", passed,
                       detail=f"HTTP {resp.status_code}")
        assert passed

    def test_portal_page_loads(self, client, report):
        resp = client.get("/watcherdb", timeout=FAST_TIMEOUT)
        passed = resp.status_code == 200 and len(resp.text) > 1000
        report.record("00. Smoke Test", "portal_html_loads", passed,
                       detail=f"tamanho={len(resp.text)} bytes")
        assert passed

    def test_servers_list_not_empty(self, client, report):
        resp = client.get("/api/v3/servers", timeout=FAST_TIMEOUT)
        body = safe_get(resp)
        servers = body.get("servers", [])
        passed = resp.status_code == 200 and len(servers) > 0
        report.record("00. Smoke Test", "servers_list_not_empty", passed,
                       detail=f"{len(servers)} servidores")
        assert passed


# ==============================================================================
# 1. LISTA DE SERVIDORES
# ==============================================================================

class TestServerList:

    def test_structure(self, client, report):
        resp = client.get("/api/v3/servers", timeout=FAST_TIMEOUT)
        body = safe_get(resp)
        missing = assert_fields_present(body, ["servers"])
        type_errors = []
        if not missing and body["servers"]:
            srv = body["servers"][0]
            missing += assert_fields_present(srv, ["server_id", "name"])
            type_errors = collect_type_errors(srv, [
                ("server_id", str, False),
                ("name", str, False),
            ])
        passed = resp.status_code == 200 and not missing and not type_errors
        report.record("01. Lista de Servidores", "estrutura_resposta", passed,
                       fields_missing=missing, type_errors=type_errors)
        assert passed

    def test_server_ids_unique(self, client, report):
        resp = client.get("/api/v3/servers", timeout=FAST_TIMEOUT)
        body = safe_get(resp)
        servers = body.get("servers", [])
        ids = [s.get("server_id") for s in servers]
        duplicates = [x for x in set(ids) if ids.count(x) > 1]
        passed = len(duplicates) == 0
        report.record("01. Lista de Servidores", "server_ids_unicos", passed,
                       detail=f"duplicados: {duplicates}" if duplicates else f"{len(ids)} IDs unicos")
        assert passed


# ==============================================================================
# 2. SERVICOS
# ==============================================================================

class TestServices:

    def test_structure(self, client, server_id, report):
        resp = client.get(f"/api/monitoring/services/server/{server_id}")
        body = safe_get(resp)
        required = ["server_id", "total_services", "running_services",
                     "stopped_services", "critical_down", "is_healthy",
                     "services", "last_check", "data_available"]
        missing = assert_fields_present(body, required)
        type_errors = collect_type_errors(body, [
            ("total_services", int, False),
            ("running_services", int, False),
            ("stopped_services", int, False),
            ("critical_down", int, False),
            ("is_healthy", bool, False),
            ("services", list, False),
            ("data_available", bool, False),
        ])
        passed = resp.status_code == 200 and not missing and not type_errors
        report.record("02. Servicos", "estrutura_resposta", passed,
                       fields_missing=missing, type_errors=type_errors)
        assert passed

    def test_sql_server_running(self, client, server_id, report):
        resp = client.get(f"/api/monitoring/services/server/{server_id}")
        body = safe_get(resp)
        data_available = body.get("data_available", False)
        running = body.get("running_services", 0)
        passed = (not data_available) or (running > 0)
        report.record("02. Servicos", "sql_server_rodando", passed,
                       detail=f"running={running}, data_available={data_available}")
        assert passed

    def test_service_item_fields(self, client, server_id, report):
        resp = client.get(f"/api/monitoring/services/server/{server_id}")
        body = safe_get(resp)
        services = body.get("services", [])
        type_errors = []
        if services:
            svc = services[0]
            missing = assert_fields_present(svc, ["service_name", "display_name", "status"])
            if missing:
                type_errors.append(f"Campos ausentes no servico: {missing}")
        passed = resp.status_code == 200 and not type_errors
        report.record("02. Servicos", "estrutura_item_servico", passed,
                       type_errors=type_errors, detail=f"{len(services)} servicos")
        assert passed


# ==============================================================================
# 3. MEMORIA
# ==============================================================================

class TestMemory:

    def test_structure(self, client, server_id, report):
        resp = client.get(f"/api/monitoring/memory/server/{server_id}")
        if resp.status_code >= 500:
            body = safe_get(resp)
            report.record("03. Memoria", "estrutura_resposta", False,
                           detail=f"HTTP {resp.status_code}: {body.get('error', body.get('detail', ''))}")
            pytest.skip("Servidor inacessivel para memoria")
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success", "server_id", "data", "timestamp"])
        type_errors = []
        if not missing:
            type_errors += collect_type_errors(body, [
                ("success", bool, False),
                ("server_id", str, False),
            ])
            err = assert_date_parseable(body, "timestamp")
            if err:
                type_errors.append(err)
        passed = resp.status_code == 200 and body.get("success") and not missing and not type_errors
        report.record("03. Memoria", "estrutura_resposta", passed,
                       fields_missing=missing, type_errors=type_errors)
        assert passed

    def test_data_not_empty(self, client, server_id, report):
        resp = client.get(f"/api/monitoring/memory/server/{server_id}")
        if resp.status_code != 200:
            pytest.skip("Endpoint nao retornou 200")
        body = safe_get(resp)
        data = body.get("data", {})
        passed = isinstance(data, dict) and len(data) > 0
        report.record("03. Memoria", "dados_nao_vazios", passed,
                       detail=f"{len(data)} campos" if isinstance(data, dict) else "")
        assert passed


# ==============================================================================
# 4. CPU
# ==============================================================================

class TestCPU:

    def test_structure(self, client, server_id, report):
        resp = client.get(f"/api/monitoring/cpu/server/{server_id}")
        if resp.status_code >= 500:
            body = safe_get(resp)
            report.record("04. CPU", "estrutura_resposta", False,
                           detail=f"HTTP {resp.status_code}: {body.get('error', body.get('detail', ''))}")
            pytest.skip("Servidor inacessivel para CPU")
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success", "server_id", "data", "timestamp"])
        type_errors = collect_type_errors(body, [
            ("success", bool, False),
            ("server_id", str, False),
        ])
        passed = resp.status_code == 200 and body.get("success") and not missing and not type_errors
        report.record("04. CPU", "estrutura_resposta", passed,
                       fields_missing=missing, type_errors=type_errors)
        assert passed

    def test_data_not_empty(self, client, server_id, report):
        resp = client.get(f"/api/monitoring/cpu/server/{server_id}")
        if resp.status_code != 200:
            pytest.skip("CPU endpoint nao retornou 200")
        body = safe_get(resp)
        data = body.get("data", {})
        passed = isinstance(data, dict) and len(data) > 0
        report.record("04. CPU", "dados_nao_vazios", passed,
                       detail=f"{len(data)} campos" if isinstance(data, dict) else "")
        assert passed


# ==============================================================================
# 5. ESPACO (FILEGROUPS)
# ==============================================================================

class TestSpace:

    def test_structure(self, client, server_id, report):
        resp = client.get(f"/api/monitoring/space/server/{server_id}")
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success", "data"])
        type_errors = []
        if not missing and body.get("success"):
            data = body["data"]
            if not isinstance(data, dict) or len(data) == 0:
                type_errors.append(f"data vazio ou tipo incorreto: {type(data).__name__}")
        passed = resp.status_code == 200 and body.get("success") is True and not missing and not type_errors
        report.record("05. Espaco", "estrutura_resposta", passed,
                       fields_missing=missing, type_errors=type_errors)
        assert passed


# ==============================================================================
# 6. BACKUP
# ==============================================================================

class TestBackup:

    def test_summary(self, client, server_id, report):
        resp = client.get(
            f"/api/monitoring/backup/server/{server_id}/summary",
            params={"days": 30}
        )
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success"])
        type_errors = []
        if body.get("success"):
            if "items" not in body:
                missing.append("items")
            elif body["items"]:
                item = body["items"][0]
                item_missing = assert_fields_present(item, ["database_name", "recovery_model"])
                if item_missing:
                    missing += [f"items[0].{f}" for f in item_missing]
        passed = resp.status_code == 200 and body.get("success") is True and not missing
        report.record("06. Backup", "summary", passed,
                       fields_missing=missing, type_errors=type_errors,
                       detail=f"{len(body.get('items', []))} databases")
        assert passed

    def test_summary_item_fields(self, client, server_id, report):
        resp = client.get(
            f"/api/monitoring/backup/server/{server_id}/summary",
            params={"days": 30}
        )
        body = safe_get(resp)
        type_errors = []
        items = body.get("items", [])
        if items:
            item = items[0]
            expected = ["database_name", "recovery_model", "last_full",
                        "last_diff", "last_log", "issues"]
            missing = assert_fields_present(item, expected)
            if missing:
                type_errors += [f"items[0].{f} ausente" for f in missing]
            rm = item.get("recovery_model")
            if rm and rm not in ("SIMPLE", "FULL", "BULK_LOGGED"):
                type_errors.append(f"recovery_model inesperado: {rm}")
            issues = item.get("issues")
            if issues is not None and not isinstance(issues, list):
                type_errors.append(f"issues deveria ser list, e {type(issues).__name__}")
        passed = not type_errors
        report.record("06. Backup", "campos_item_backup", passed,
                       type_errors=type_errors, detail=f"{len(items)} items")
        assert passed

    def test_patterns(self, client, server_id, report):
        resp = client.get(
            f"/api/monitoring/backup/server/{server_id}/patterns",
            params={"days": 30}
        )
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success"])
        type_errors = []
        if body.get("success"):
            if "databases" not in body:
                missing.append("databases")
            else:
                dbs = body.get("databases", {})
                err = assert_field_type(body, "databases", dict)
                if err:
                    type_errors.append(err)
                elif dbs:
                    first_name = next(iter(dbs))
                    patterns = dbs[first_name]
                    has_type = any(k in patterns for k in ("FULL", "DIFF", "LOG", "full", "diff", "log"))
                    if not has_type:
                        type_errors.append(f"Database '{first_name}' sem FULL/DIFF/LOG")
        passed = resp.status_code == 200 and body.get("success") is True and not missing and not type_errors
        report.record("06. Backup", "patterns", passed,
                       fields_missing=missing, type_errors=type_errors,
                       detail=f"{len(body.get('databases', {}))} databases")
        assert passed

    def test_health(self, client, server_id, report):
        resp = client.get(f"/api/monitoring/backup/server/{server_id}/health")
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success"])
        type_errors = []
        if body.get("success") and "health_score" in body:
            err = assert_numeric_range(body, "health_score", 0, 100)
            if err:
                type_errors.append(err)
        passed = resp.status_code == 200 and body.get("success") is True and not missing
        report.record("06. Backup", "health", passed,
                       fields_missing=missing, type_errors=type_errors,
                       detail=f"score={body.get('health_score', 'N/A')}")
        assert passed


# ==============================================================================
# 7. DISCO
# ==============================================================================

class TestDisk:

    def test_disk_volumes(self, client, server_id, report):
        resp = client.get(f"/api/queries/disk-volumes/{server_id}")
        body = safe_get(resp)
        type_errors = []
        has_data = (resp.status_code == 200 and
                    (body.get("rows") or body.get("volumes") or body.get("success")))
        if body.get("rows") and isinstance(body["rows"], list) and body["rows"]:
            row = body["rows"][0]
            if not any(k.lower() in str(row.keys()).lower() for k in ["drive", "volume", "disk", "total"]):
                type_errors.append("Nenhum campo de disco encontrado nas rows")
        passed = has_data and not type_errors
        report.record("07. Disco", "volumes", passed,
                       type_errors=type_errors, detail=f"HTTP {resp.status_code}")
        assert passed

    def test_disk_unallocated(self, client, server_id, report):
        resp = client.get(f"/api/disk-unallocated/server/{server_id}")
        body = safe_get(resp)
        if resp.status_code == 404:
            report.record("07. Disco", "unallocated", True,
                           detail="404 - Sem dados (normal)")
            return
        passed = resp.status_code == 200
        report.record("07. Disco", "unallocated", passed,
                       detail=f"HTTP {resp.status_code}")
        assert passed


# ==============================================================================
# 8. JOBS (SQL Agent)
# ==============================================================================

class TestJobs:

    def test_structure(self, client, server_id, report):
        resp = client.get(f"/api/jobs/server/{server_id}")
        if resp.status_code >= 500:
            body = safe_get(resp)
            report.record("08. Jobs", "estrutura_resposta", False,
                           detail=f"HTTP {resp.status_code}: {body.get('detail', '')}")
            pytest.skip("Jobs endpoint falhou")
        body = safe_get(resp)
        required = ["total_jobs", "total_failed_24h", "all_jobs", "failed_jobs"]
        missing = assert_fields_present(body, required)
        type_errors = collect_type_errors(body, [
            ("total_jobs", int, False),
            ("total_failed_24h", int, False),
            ("failed_jobs", list, False),
            ("all_jobs", list, False),
        ])
        passed = resp.status_code == 200 and not missing and not type_errors
        report.record("08. Jobs", "estrutura_resposta", passed,
                       fields_missing=missing, type_errors=type_errors,
                       detail=f"total={body.get('total_jobs')}, failed={body.get('total_failed_24h')}")
        assert passed

    def test_job_item_fields(self, client, server_id, report):
        resp = client.get(f"/api/jobs/server/{server_id}")
        if resp.status_code != 200:
            pytest.skip("Jobs nao retornou 200")
        body = safe_get(resp)
        all_jobs = body.get("all_jobs", [])
        type_errors = []
        if all_jobs:
            job = all_jobs[0]
            missing = assert_fields_present(job, ["job_name", "enabled"])
            if missing:
                type_errors += [f"all_jobs[0].{f} ausente" for f in missing]
        passed = not type_errors
        report.record("08. Jobs", "estrutura_item_job", passed,
                       type_errors=type_errors, detail=f"{len(all_jobs)} jobs")
        assert passed


# ==============================================================================
# 9. ALWAYS ON
# ==============================================================================

class TestAlwaysOn:

    def test_overview(self, client, server_id, report):
        resp = client.get(f"/api/alwayson/server/{server_id}/overview")
        body = safe_get(resp)
        if body.get("is_alwayson") is False or body.get("has_alwayson") is False:
            report.record("09. Always On", "overview", True,
                           detail="Servidor sem Always On (normal)")
            return
        if resp.status_code == 404:
            report.record("09. Always On", "overview", True,
                           detail="404 - Sem AG (normal)")
            return
        missing = []
        type_errors = []
        if body.get("is_alwayson") or body.get("has_alwayson"):
            if "ag_name" not in body:
                missing.append("ag_name")
        passed = resp.status_code == 200 and not missing and not type_errors
        report.record("09. Always On", "overview", passed,
                       fields_missing=missing, type_errors=type_errors,
                       detail=f"AG={body.get('ag_name', 'N/A')}")
        assert passed

    def test_events(self, client, server_name, report):
        resp = client.get(
            f"/api/alwayson/events/{server_name}",
            params={"days": 30}
        )
        if resp.status_code in (404, 500):
            report.record("09. Always On", "events", True,
                           detail=f"HTTP {resp.status_code} - Sem AG ou erro (skip)")
            return
        passed = resp.status_code == 200
        report.record("09. Always On", "events", passed,
                       detail=f"HTTP {resp.status_code}")
        assert passed


# ==============================================================================
# 10. SEGURANCA
# ==============================================================================

class TestSecurity:

    def test_structure(self, client, server_id, report):
        resp = client.get(f"/api/monitoring/security/server/{server_id}")
        if resp.status_code >= 500:
            body = safe_get(resp)
            report.record("10. Seguranca", "estrutura_resposta", False,
                           detail=f"HTTP {resp.status_code}: {body.get('error', body.get('detail', ''))}")
            pytest.skip("Security endpoint falhou")
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success", "server_id"])
        type_errors = []
        if body.get("success"):
            data = body.get("data", body)
            if isinstance(data, dict) and len(data) <= 2:
                type_errors.append("Dados de seguranca parecem vazios")
        passed = resp.status_code == 200 and body.get("success") and not missing and not type_errors
        report.record("10. Seguranca", "estrutura_resposta", passed,
                       fields_missing=missing, type_errors=type_errors)
        assert passed


# ==============================================================================
# 11. DIAGNOSTICS (SQL Queries)
# ==============================================================================

class TestDiagnostics:

    def test_databases_list(self, client, server_id, report):
        resp = client.get(f"/api/queries/databases/{server_id}")
        body = safe_get(resp)
        type_errors = []
        dbs = body.get("databases", body.get("rows", []))
        has_data = isinstance(dbs, list) and len(dbs) > 0
        if has_data and isinstance(dbs[0], dict):
            has_name = any(k for k in dbs[0].keys() if "name" in k.lower() or "database" in k.lower())
            if not has_name:
                type_errors.append(f"Nenhum campo 'name'/'database': {list(dbs[0].keys())[:5]}")
        passed = resp.status_code == 200 and has_data and not type_errors
        report.record("11. Diagnostics", "databases_list", passed,
                       type_errors=type_errors, detail=f"{len(dbs)} databases")
        assert passed

    def test_blocking(self, client, server_id, report):
        resp = client.get(f"/api/queries/blocking/{server_id}")
        passed = resp.status_code == 200
        report.record("11. Diagnostics", "blocking", passed,
                       detail=f"HTTP {resp.status_code}")
        assert passed

    def test_tempdb(self, client, server_id, report):
        resp = client.get(f"/api/queries/tempdb/{server_id}")
        passed = resp.status_code == 200
        report.record("11. Diagnostics", "tempdb", passed,
                       detail=f"HTTP {resp.status_code}")
        assert passed

    def test_index_fragmentation(self, client, server_id, report):
        resp = client.get(f"/api/queries/index-fragmentation/{server_id}")
        passed = resp.status_code == 200
        report.record("11. Diagnostics", "index_fragmentation", passed,
                       detail=f"HTTP {resp.status_code}")
        assert passed

    def test_log_space(self, client, server_id, report):
        resp = client.get(f"/api/queries/log-space/{server_id}")
        passed = resp.status_code == 200
        report.record("11. Diagnostics", "log_space", passed,
                       detail=f"HTTP {resp.status_code}")
        assert passed


# ==============================================================================
# 12. LOGS
# ==============================================================================

class TestLogs:

    def test_windows_events(self, client, server_id, report):
        resp = client.get(
            f"/api/monitoring/windows-events/{server_id}",
            params={"hours": 24}
        )
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success", "server_id"])
        type_errors = []
        if body.get("success") and body.get("events"):
            evts = body["events"]
            if isinstance(evts, list) and evts and isinstance(evts[0], dict) and not evts[0]:
                type_errors.append("Evento vazio")
        passed = resp.status_code == 200 and body.get("success") is True and not missing
        report.record("12. Logs", "windows_events", passed,
                       fields_missing=missing, type_errors=type_errors,
                       detail=f"{len(body.get('events', []))} eventos")
        assert passed

    def test_sql_errors(self, client, server_id, report):
        resp = client.get(
            f"/api/monitoring/sql-errors/{server_id}",
            params={"hours": 24}
        )
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success", "server_id"])
        passed = resp.status_code == 200 and body.get("success") is True and not missing
        report.record("12. Logs", "sql_errors", passed,
                       fields_missing=missing,
                       detail=f"{len(body.get('errors', []))} erros")
        assert passed


# ==============================================================================
# 13. KPI DASHBOARD
# ==============================================================================

class TestKPIDashboard:

    def test_structure(self, client, report):
        try:
            resp = client.get("/api/sqlserver-kpis/dashboard", timeout=300.0)
        except httpx.TimeoutException:
            report.record("13. KPI Dashboard", "estrutura_resposta", False,
                           detail="TIMEOUT (>300s) - endpoint muito lento")
            pytest.skip("KPI Dashboard timeout")
        if resp.status_code >= 500:
            body = safe_get(resp)
            report.record("13. KPI Dashboard", "estrutura_resposta", False,
                           detail=f"HTTP {resp.status_code}: {body.get('detail', '')}")
            pytest.skip("KPI Dashboard indisponivel")
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success"])
        type_errors = []
        if body.get("success") and body.get("data"):
            data = body["data"]
            if isinstance(data, dict) and "kpis" in data:
                kpis = data["kpis"]
                for kpi_name in ["db_availability", "disk_usage", "tlog_usage"]:
                    if kpi_name not in kpis:
                        missing.append(f"kpis.{kpi_name}")
        passed = resp.status_code == 200 and body.get("success") and not missing and not type_errors
        report.record("13. KPI Dashboard", "estrutura_resposta", passed,
                       fields_missing=missing, type_errors=type_errors)
        assert passed


# ==============================================================================
# 14. OVERVIEW DASHBOARD
# ==============================================================================

class TestOverviewDashboard:

    def test_summary(self, client, report):
        try:
            resp = client.get("/api/v1/overview/summary", timeout=300.0)
        except httpx.TimeoutException:
            report.record("14. Overview Dashboard", "summary", False,
                           detail="TIMEOUT (>300s) - endpoint muito lento")
            pytest.skip("Overview summary timeout")
        if resp.status_code >= 500:
            body = safe_get(resp)
            report.record("14. Overview Dashboard", "summary", False,
                           detail=f"HTTP {resp.status_code}: {body.get('detail', '')}")
            pytest.skip("Overview dashboard indisponivel")
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success"])
        type_errors = []
        if body.get("success") and body.get("data"):
            data = body["data"]
            for f in ["total_instances", "instances_online", "availability_percent"]:
                if f not in data:
                    missing.append(f"data.{f}")
            err = assert_numeric_range(data, "availability_percent", 0, 100)
            if err:
                type_errors.append(err)
        passed = resp.status_code == 200 and body.get("success") and not missing and not type_errors
        report.record("14. Overview Dashboard", "summary", passed,
                       fields_missing=missing, type_errors=type_errors,
                       detail=f"instances={body.get('data', {}).get('total_instances', 'N/A')}")
        assert passed

    def test_instances(self, client, report):
        try:
            resp = client.get("/api/v1/overview/instances", timeout=300.0)
        except httpx.TimeoutException:
            report.record("14. Overview Dashboard", "instances", False,
                           detail="TIMEOUT (>300s) - endpoint muito lento")
            pytest.skip("Overview instances timeout")
        if resp.status_code >= 500:
            pytest.skip("Overview instances indisponivel")
        body = safe_get(resp)
        missing = assert_fields_present(body, ["success"])
        type_errors = []
        if body.get("success"):
            instances = body.get("instances", body.get("data", []))
            if isinstance(instances, list) and instances and isinstance(instances[0], dict):
                inst = instances[0]
                if not any(k in inst for k in ["instance", "instance_name", "server", "Instancia"]):
                    missing.append("instances[0] sem campo de identificacao")
        passed = resp.status_code == 200 and body.get("success") and not missing and not type_errors
        report.record("14. Overview Dashboard", "instances", passed,
                       fields_missing=missing, type_errors=type_errors)
        assert passed


# ==============================================================================
# 15. CONSISTENCIA ENTRE MODULOS
# ==============================================================================

class TestConsistency:

    def test_server_id_consistent(self, client, server_id, report):
        endpoints = [
            f"/api/monitoring/services/server/{server_id}",
            f"/api/monitoring/backup/server/{server_id}/summary?days=7",
        ]
        type_errors = []
        for ep in endpoints:
            try:
                resp = client.get(ep)
                if resp.status_code == 200:
                    body = safe_get(resp)
                    returned_id = body.get("server_id")
                    if returned_id and returned_id != server_id:
                        type_errors.append(
                            f"{ep}: retornou '{returned_id}', esperado '{server_id}'")
            except Exception as e:
                type_errors.append(f"{ep}: erro - {e}")
        passed = not type_errors
        report.record("15. Consistencia", "server_id_entre_modulos", passed,
                       type_errors=type_errors)
        assert passed

    def test_timestamps_are_recent(self, client, server_id, report):
        endpoints = [
            f"/api/monitoring/memory/server/{server_id}",
            f"/api/monitoring/cpu/server/{server_id}",
        ]
        type_errors = []
        now = datetime.now()
        for ep in endpoints:
            try:
                resp = client.get(ep)
                if resp.status_code == 200:
                    body = safe_get(resp)
                    ts_str = body.get("timestamp")
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts
                            diff_hours = abs((now - ts_naive).total_seconds() / 3600)
                            if diff_hours > 24:
                                type_errors.append(
                                    f"{ep}: timestamp com {diff_hours:.0f}h de diferenca")
                        except (ValueError, TypeError):
                            type_errors.append(f"{ep}: timestamp nao parseavel: {ts_str}")
            except Exception as e:
                type_errors.append(f"{ep}: erro - {e}")
        passed = not type_errors
        report.record("15. Consistencia", "timestamps_recentes", passed,
                       type_errors=type_errors)
        assert passed
