"""
2026-09-09 -- Analise Preditiva de Crescimento: guardas estaticas do lote
"a analise tem de funcionar" (owner). Sem BD; le os ficheiros.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
MAIN = (ROOT / "watcherdb_main.py").read_text(encoding="utf-8")
ANALYTICS = (ROOT / "modules" / "analytics" / "__init__.py").read_text(encoding="utf-8")
SCRIPT = (ROOT / "scripts" / "filegroup_interactive_report_v5_watcherdb.py").read_text(encoding="utf-8")


def test_script_never_uses_windows_identity():
    """Regra de Ouro #2: o script do relatorio liga como sql_monitoring."""
    assert "Trusted_Connection=yes" not in SCRIPT
    assert "Integrated Security" not in SCRIPT
    assert "build_intelligence_conn_str" in SCRIPT
    assert 'self.watcherdb_server = "SQLHDSTST505' not in SCRIPT


def test_analyzer_uses_service_interpreter_and_sanitizes():
    assert '"python",' not in ANALYTICS
    assert "sys.executable," in ANALYTICS
    assert "_sanitize_script_error(error_msg)" in ANALYTICS


def test_sanitizer_masks_paths_and_keeps_last_line():
    import importlib.util
    spec = importlib.util.spec_from_file_location("wdb_analytics", ROOT / "modules" / "analytics" / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tb = ('Traceback (most recent call last):\n  File "C:\\Users\\conta\\x.py", line 11, in <module>\n'
          '    import pyodbc\nModuleNotFoundError: No module named \'pyodbc\'')
    out = mod._sanitize_script_error(tb)
    assert out == "ModuleNotFoundError: No module named 'pyodbc'"
    assert mod._sanitize_script_error('erro em C:\\a\\b.py') == "erro em <path>"


def test_endpoint_gate_is_dependency_and_failure_is_500():
    assert "_user: dict = Depends(_auth_require_admin)" in MAIN
    assert "await _require_admin(http_request)" not in MAIN.split("generate_predictive_report")[1].split("@app.")[0]
    assert "return JSONResponse(status_code=500, content={" in MAIN


def test_portal_button_admin_only_and_json_guard():
    assert "window._currentUser.role === 'admin') ?" in PORTAL
    assert "_ctype.includes('application/json')" in PORTAL
    assert "errorData.error || errorData.detail ||" in PORTAL

def test_report_is_csp_compatible_20260909():
    """O iframe herda a CSP do portal: sem CDN no relatorio, Chart.js auto-hospedado,
    nonce injectado nos blocos inline antes do document.write, rodape 'WatcherDB'."""
    assert "cdn.jsdelivr.net" not in SCRIPT
    assert "/static/vendor/chartjs/chart.min.js" in SCRIPT
    assert (ROOT / "static" / "vendor" / "chartjs" / "chart.min.js").exists()
    assert "Intelligence v5 (WatcherDB Data Source)" not in SCRIPT
    assert "const _cspNonce = '{{ csp_nonce }}';" in PORTAL
    assert "iframeDoc.write(_safeHtml);" in PORTAL
    assert "iframeDoc.write(htmlContent);" not in PORTAL
