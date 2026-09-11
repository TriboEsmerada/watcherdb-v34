"""TESTSUKITA V1 - PASSO 3: dois defeitos do runner expostos pela 1.a corrida (FINDINGS_TESTSUKITA_2026-09-11 #10, #11)
e duas afinacoes do smoke de API.

  a) drill-down: "dashboard sem cartoes" = re-render do dashboard entre a espera e a leitura -> ate' 3 leituras.
  b) ratchet: assinaturas novas -> "servico em baixo/reiniciado durante a corrida" e "dashboard re-renderizou".
  c) API: network-test excluido (sonda com efeitos e 15 s por desenho); /api/admin/health whitelisted para o viewer
     ate' decisao de produto (#6), com o achado registado.
  d) API: hipotese no proprio JSON (campo "hipotese" por endpoint 5xx) para o painel.

Uso (raiz do repo):  py docs/context/TESTSUKITA_V1_PASSO3_fix_apply.py
Depois:              pwsh docs/context/TESTSUKITA_V1_PASSO4_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEM = ROOT / "tests" / "e2e" / "test_semantic_e2e.py"
RATCHET = ROOT / "scripts" / "qa" / "testsukita_ratchet.py"
API = ROOT / "tests" / "e2e" / "test_api_smoke_e2e.py"
MARK = "V1 PASSO 3"


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT [{label}]: esperava 1, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


S_OLD = '''        resultados, warn, problemas = [], [], []
        for c in cartoes:
'''
S_NEW = '''        # V1 PASSO 3: o dashboard re-renderiza a cada 30 s; uma leitura vazia entre a espera e a leitura
        # nao e' "sem cartoes" (1.a corrida do v1, viewer) -> ate' 3 leituras.
        for _tentativa in range(3):
            if cartoes:
                break
            page.wait_for_timeout(700)
            cartoes = page.evaluate(
                """(n) => { const todos = Array.from(document.querySelectorAll('.kpi-category-group .kpi-card'));
                     const sel = todos.slice(0, n); const ao = todos.find(c => c.dataset.kpiId === 'always-on-unhealthy');
                     if (ao && !sel.includes(ao)) sel.push(ao);
                     return sel.map(c => ({ cardId: c.id, kpi: c.dataset.kpiId,
                       valor: (c.querySelector('.kpi-value') ? c.querySelector('.kpi-value').innerText : '').trim() })); }""",
                DRILL_MAX,
            )
        resultados, warn, problemas = [], [], []
        for c in cartoes:
'''

R_OLD = '''HIPOTESES = [
    (r"429|rate limit", '''
R_NEW = '''HIPOTESES = [
    # V1 PASSO 3: assinaturas da 1.a corrida do v1 (restart do servico a meio; re-render do dashboard)
    (r"ERR_CONNECTION_REFUSED|Page\\.goto|net::ERR_|ERR_EMPTY_RESPONSE", "servico em baixo ou reiniciado durante a corrida: ver council/service_log_window.log ('Shutting down' / 'Started server process') e Event Log 7039/7031"),
    (r"dashboard sem cartoes", "dashboard re-renderizou entre a espera e a leitura (refresh 30 s); se persistir, dashboard realmente vazio"),
    (r"429|rate limit", '''

A1_OLD = '''EXCLUIR = re.compile(r"/(docs|redoc|openapi\\.json|login|logout|run|execute|reset|restart|download|export|stream|sse|ws|realtime|live|"
                     r"\\.well-known|collector/run|kill|shrink|action)", re.I)
'''
A1_NEW = '''EXCLUIR = re.compile(r"/(docs|redoc|openapi\\.json|login|logout|run|execute|reset|restart|download|export|stream|sse|ws|realtime|live|"
                     r"\\.well-known|collector/run|kill|shrink|action|network-test)", re.I)  # V1 PASSO 3: network-test e' sonda (15 s, efeitos)
# V1 PASSO 3: caminhos /admin publicos por desenho (so' contadores) - achado #6 registado; ate' decisao, nao contam como fuga.
ADMIN_PUBLICO = {"/api/admin/health"}
'''
A2_OLD = '''                if status == 200 and "/admin" in original:
                    problemas.append(f"{original}: viewer recebeu 200 num caminho /admin")
'''
A2_NEW = '''                if status == 200 and "/admin" in original and original not in ADMIN_PUBLICO:
                    problemas.append(f"{original}: viewer recebeu 200 num caminho /admin")
'''
A3_OLD = '''            resultados.append({"path": original, "url": url, "status": status, "ms": ms, "sensivel": sens})
'''
A3_NEW = '''            item = {"path": original, "url": url, "status": status, "ms": ms, "sensivel": sens}
            if status >= 500:
                item["hipotese"] = "500 real do servico: procurar o traceback em council/service_log_window.log pelo caminho"
            elif status == -1:
                item["hipotese"] = f"sem resposta em {TIMEOUT_S}s: endpoint lento ou instancia sem resposta"
            resultados.append(item)
'''


def main() -> None:
    s = SEM.read_text(encoding="utf-8")
    if MARK in s:
        print("Ja aplicado: semantico")
    else:
        s = rep(s, S_OLD, S_NEW, "drilldown retry"); compile(s, str(SEM), "exec")
        SEM.write_text(s, encoding="utf-8", newline="\n"); print("OK: tests/e2e/test_semantic_e2e.py (3 leituras dos cartoes)")
    r = RATCHET.read_text(encoding="utf-8")
    if MARK in r:
        print("Ja aplicado: ratchet")
    else:
        r = rep(r, R_OLD, R_NEW, "ratchet hipoteses"); compile(r, str(RATCHET), "exec")
        RATCHET.write_text(r, encoding="utf-8", newline="\n"); print("OK: scripts/qa/testsukita_ratchet.py (+2 hipoteses)")
    a = API.read_text(encoding="utf-8")
    if MARK in a:
        print("Ja aplicado: api")
    else:
        a = rep(a, A1_OLD, A1_NEW, "api excluir"); a = rep(a, A2_OLD, A2_NEW, "api admin publico"); a = rep(a, A3_OLD, A3_NEW, "api hipotese")
        compile(a, str(API), "exec"); API.write_text(a, encoding="utf-8", newline="\n"); print("OK: tests/e2e/test_api_smoke_e2e.py")
    print("Proximo: pwsh docs/context/TESTSUKITA_V1_PASSO4_commit.ps1")


if __name__ == "__main__":
    main()
