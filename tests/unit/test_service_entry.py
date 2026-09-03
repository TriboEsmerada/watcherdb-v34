"""Etapa 2 (auditoria empacotamento): entry point SCM — mutex + porta.

Nao arranca servico nem uvicorn: testa os helpers puros do launcher
(single-instance mutex via kernel32 e resolucao de porta). O teste SCM
real (sc create/start/stop) e manual — ver RUNBOOK Etapa 2.
"""
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Launcher e Windows-only (pywin32)"
)

import watcherdb_service  # noqa: E402


@pytest.fixture(autouse=True)
def _release_mutex():
    yield
    watcherdb_service.release_single_instance()


def test_mutex_blocks_second_instance(tmp_path):
    ok1, name1 = watcherdb_service.acquire_single_instance(tmp_path)
    assert ok1 is True
    ok2, name2 = watcherdb_service.acquire_single_instance(tmp_path)
    assert ok2 is False
    assert name2 == name1


def test_mutex_released_reacquirable(tmp_path):
    ok, _ = watcherdb_service.acquire_single_instance(tmp_path)
    assert ok
    watcherdb_service.release_single_instance()
    ok2, _ = watcherdb_service.acquire_single_instance(tmp_path)
    assert ok2


def test_mutex_distinct_data_dirs_coexist(tmp_path):
    # O handle do primeiro acquire fica aberto ate ao fim do processo de
    # teste (o global so guarda o ultimo) — inofensivo aqui.
    ok1, name1 = watcherdb_service.acquire_single_instance(tmp_path / "a")
    ok2, name2 = watcherdb_service.acquire_single_instance(tmp_path / "b")
    assert ok1 and ok2
    assert name1 != name2


def test_resolve_port_default_env_and_invalid(monkeypatch):
    monkeypatch.delenv("WATCHERDB_PORT", raising=False)
    assert watcherdb_service._resolve_port() == 8434  # linha V3.4 (03/09)
    monkeypatch.setenv("WATCHERDB_PORT", "8499")
    assert watcherdb_service._resolve_port() == 8499
    monkeypatch.setenv("WATCHERDB_PORT", "nao-numerico")
    assert watcherdb_service._resolve_port() == 8434  # linha V3.4 (03/09)


def _svc_stub(monkeypatch, acquire_results):
    """WatcherDBService sem SCM: ReportServiceStatus gravado, sem uvicorn,
    sem espera no stop_event, acquire_single_instance sequenciado."""
    svc = object.__new__(watcherdb_service.WatcherDBService)
    svc.server = None
    svc.stop_event = object()
    svc.server_thread = None
    reported = []
    svc.ReportServiceStatus = lambda st, **kw: reported.append(st)
    svc._serve = lambda: None
    results = list(acquire_results)
    monkeypatch.setattr(
        watcherdb_service, "acquire_single_instance",
        lambda _root: results.pop(0) if results else (True, "m"))
    monkeypatch.setattr(watcherdb_service.servicemanager, "LogMsg",
                        lambda *a, **k: None)
    monkeypatch.setattr(watcherdb_service.servicemanager, "LogInfoMsg",
                        lambda *a, **k: None)
    monkeypatch.setattr(watcherdb_service.servicemanager, "LogErrorMsg",
                        lambda *a, **k: None)
    monkeypatch.setattr(watcherdb_service.win32event, "WaitForSingleObject",
                        lambda *a, **k: 0)
    import time
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    return svc, reported


def test_svcdorun_reports_running_after_mutex_wait(monkeypatch):
    """Incidente 02/09 19:19: o framework reporta RUNNING antes de SvcDoRun;
    o loop de espera pelo mutex repunha START_PENDING e nada voltava a
    RUNNING -> servico 'Start Pending' para sempre com a app a servir."""
    import win32service
    svc, reported = _svc_stub(monkeypatch, [(False, "m"), (True, "m")])
    svc.SvcDoRun()
    assert win32service.SERVICE_START_PENDING in reported
    idx_pend = reported.index(win32service.SERVICE_START_PENDING)
    assert win32service.SERVICE_RUNNING in reported[idx_pend + 1:]


def test_svcdorun_no_wait_does_not_touch_status(monkeypatch):
    """Sem espera pelo mutex o framework ja deixou o SCM em RUNNING: o
    wrapper nao deve reportar START_PENDING nem RUNNING outra vez."""
    import win32service
    svc, reported = _svc_stub(monkeypatch, [(True, "m")])
    svc.SvcDoRun()
    assert win32service.SERVICE_START_PENDING not in reported
    assert win32service.SERVICE_RUNNING not in reported
