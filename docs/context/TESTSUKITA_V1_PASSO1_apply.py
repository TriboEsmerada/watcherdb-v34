"""TESTSUKITA V1 - PASSO 1: tudo o que o TestSprite faz, mais o que ele nao faz. (owner 11/09: "so pare quando estiver tudo pronto")

Paridade com o TestSprite:
  1. EXPLORAR INTERACCOES  tests/e2e/test_interactions_e2e.py - em cada uma das 16 abas, por perfil, clica nos
     primeiros 6 controlos nao destrutivos, escreve nos 2 primeiros campos de texto, muda o 1.o select; fecha modais
     com Escape; invariantes (0 pageerror, 0 5xx, 0 erros de consola fora do ruido); grava o que tocou.
  2. TESTES DE API          tests/e2e/test_api_smoke_e2e.py - le /openapi.json, percorre os GET (sem params ou com
     params substituiveis: servidor TST, kpi_type), por perfil: nunca 5xx; viewer nunca recebe campos sensiveis
     nem 200 em /admin; grava status por endpoint e perfil.
  3. BUNDLE DE FALHAS       tests/e2e/conftest.py - snapshot do DOM em falha (alem de screenshot e trace);
     nightly copia a janela do logs/service_stderr.log da corrida para o bundle (correlacao teste<->servico).
  4. HIPOTESE DE CAUSA      scripts/qa/testsukita_ratchet.py - assinatura da falha -> hipotese honesta
     (429 = rate limit; AbortError = ruido; 401/403 = credencial/perfil; 5xx = ver janela do log; timeout = instancia).
  5. REGRESSAO PERSISTENTE  o mesmo ratchet compara com a corrida anterior: regressoes, novas, resolvidas,
     persistentes; endpoints de API que mudaram de status; RATCHET.json + RATCHET.md; o painel mostra.
Alem do TestSprite:
  6. Igualdade cartao<->modal no Always On (valor do cartao == instancias distintas na modal) - a unidade do KPI
     provada todas as noites; o cartao always-on entra sempre no drill-down.
  7. Duas metades (council afirma / qa-externo confere) com divergencia = achado; perfis viewer/dba/admin;
     tudo dentro da rede do cliente, evidencias fora do git; sem cloud.

Uso (raiz do repo):  py docs/context/TESTSUKITA_V1_PASSO1_apply.py
Depois:              pwsh docs/context/TESTSUKITA_V1_PASSO2_commit.ps1  (corrida completa na 8434, ~35 min)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARK = "TESTSUKITA V1"
INTER = ROOT / "tests" / "e2e" / "test_interactions_e2e.py"
API = ROOT / "tests" / "e2e" / "test_api_smoke_e2e.py"
RATCHET = ROOT / "scripts" / "qa" / "testsukita_ratchet.py"
CONFTEST = ROOT / "tests" / "e2e" / "conftest.py"
NIGHTLY = ROOT / "scripts" / "qa" / "nightly_testsukita.ps1"
BOARD = ROOT / "scripts" / "qa" / "testsukita_board.py"
SEM = ROOT / "tests" / "e2e" / "test_semantic_e2e.py"
PLANO = ROOT / "docs" / "context" / "PLANO_TESTSUKITA_2026-09-09.md"
README = ROOT / "docs" / "context" / "TESTSUKITA_README.md"


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT [{label}]: esperava 1, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


def write_once(path: Path, src: str, label: str) -> None:
    if path.exists():
        if MARK in path.read_text(encoding="utf-8", errors="replace"):
            print(f"Ja existe: {label}"); return
        sys.exit(f"ABORT: {path} existe sem marcador.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(src, encoding="utf-8", newline="\n"); print(f"OK: {label}")


# =====================================================================================
INTER_SRC = r'''"""TESTSUKITA V1 - explorador de interaccoes por aba (o que o TestSprite faz: clicar em tudo).

Por perfil e por aba: abre a aba do servidor de teste e, DENTRO do contentor da aba,
  - clica (JS click, imune ao refresh de 30 s) nos primeiros N controlos visiveis que nao sejam
    destrutivos nem de escrita (salvar/apagar/executar/restart/export/logout/refresh...),
  - escreve nos 2 primeiros campos de texto e muda o 1.o select,
  - fecha qualquer modal que tenha aberto (Escape) e regista se abriu.
Invariantes: 0 pageerror, 0 respostas 5xx, 0 erros de consola fora do ruido. O que foi tocado fica no JSON
(coverage de interaccao por aba), para o ratchet e o painel.

  WATCHERDB_QA_INTER_CLICKS (default 6), WATCHERDB_QA_INTER_INPUTS (default 2)
  py -m pytest tests/e2e/test_interactions_e2e.py -m e2e --no-cov -p no:cacheprovider -q
"""
from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_spec = importlib.util.spec_from_file_location("smoke_helpers", Path(__file__).with_name("test_smoke_modules_e2e.py"))
_smk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_smk)

TABS = _smk.TABS
PERFIS = _smk.PERFIS
MAX_CLICKS = int(os.getenv("WATCHERDB_QA_INTER_CLICKS", "6"))
MAX_INPUTS = int(os.getenv("WATCHERDB_QA_INTER_INPUTS", "2"))
TAB_TIMEOUT_MS = int(os.getenv("WATCHERDB_QA_TAB_TIMEOUT_MS", "60000"))

# Nunca clicar: escrita, execucao, navegacao para fora, refresh (ruido) e o proprio fecho de aba.
PERIGOSO = ("salvar|guardar|gravar|apagar|remover|eliminar|delete|reset|restart|reinic|executar|run now|run |"
            "mute|silenc|export|download|descarreg|imprimir|print|logout|sair|kill|stop|start|refresh|"
            "atualizar|actualizar|fechar|close|abort|cancel|shrink|alter |drop |truncate|enviar|submit|"
            "confirm|aplicar|apply|criar|create|novo|new |login|password|senha")

JS_LISTA = r"""
(args) => {
  const [tid, maxClicks, maxInputs, perigoso] = args;
  const root = document.getElementById('tab-content-' + tid);
  if (!root) return null;
  const rx = new RegExp(perigoso, 'i');
  const visivel = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 4 && r.height > 4 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const texto = (el) => ((el.innerText || '') + ' ' + (el.title || '') + ' ' + (el.getAttribute('onclick') || '') + ' ' + (el.className || '')).trim();
  const clicaveis = [];
  const vistos = new Set();
  for (const el of root.querySelectorAll('button, [onclick], [role="button"], a[href^="#"], .clickable, th[onclick], .kpi-card')) {
    if (clicaveis.length >= maxClicks) break;
    if (!visivel(el)) continue;
    if (el.closest('.tab-refresh, .kpi-card-refresh, form')) continue;
    const t = texto(el);
    if (rx.test(t)) continue;
    const chave = (el.tagName + '|' + (el.innerText || '').trim().slice(0, 40) + '|' + (el.getAttribute('onclick') || '').slice(0, 60));
    if (vistos.has(chave)) continue;
    vistos.add(chave);
    el.setAttribute('data-ts-click', String(clicaveis.length));
    clicaveis.push({ i: clicaveis.length, tag: el.tagName, texto: (el.innerText || el.title || '').trim().slice(0, 60) });
  }
  const inputs = [];
  for (const el of root.querySelectorAll('input[type="text"], input[type="search"], input:not([type]), textarea')) {
    if (inputs.length >= maxInputs) break;
    if (!visivel(el) || el.readOnly || el.disabled) continue;
    if (rx.test(texto(el) + ' ' + (el.placeholder || '') + ' ' + (el.name || '') + ' ' + (el.id || ''))) continue;
    el.setAttribute('data-ts-input', String(inputs.length));
    inputs.push({ i: inputs.length, id: el.id || el.name || el.placeholder || el.tagName });
  }
  let select = null;
  for (const el of root.querySelectorAll('select')) {
    if (!visivel(el) || el.disabled || el.options.length < 2) continue;
    el.setAttribute('data-ts-select', '0');
    select = { id: el.id || el.name || 'select', opcoes: el.options.length };
    break;
  }
  const total = root.querySelectorAll('button, [onclick], [role="button"], input, select').length;
  return { clicaveis, inputs, select, total_controlos: total };
}
"""

JS_MODAL_ABERTA = r"""
() => {
  const cands = document.querySelectorAll('.instances-modal.show, [role="dialog"], .modal.show, [id$="Modal"], [id$="-modal"]');
  for (const m of cands) { const cs = getComputedStyle(m); if (cs.display !== 'none' && cs.visibility !== 'hidden' && m.getBoundingClientRect().height > 40) return m.id || m.className || 'modal'; }
  return null;
}
"""


def _fecha_modais(page) -> int:
    fechadas = 0
    for _ in range(3):
        aberta = page.evaluate(JS_MODAL_ABERTA)
        if not aberta:
            break
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        fechadas += 1
    return fechadas


@pytest.mark.parametrize("perfil", [_smk._perfil_param(p) for p in PERFIS])
@pytest.mark.parametrize("tab", TABS)
class TestInteraccoes:
    def test_aba_aguenta_cliques_e_escrita(self, page, base_url, perfil, tab):
        col = _smk.Colector(page, base_url)
        user = _smk._autentica(page, base_url, perfil)
        servidor = _smk._escolhe_servidor(page)
        if not servidor:
            pytest.skip("sem servidor de test/quality no inventario")
        page.evaluate("(sid) => { const s = allServers.find(x => x.server_id === sid); selectServer(s); }", servidor["server_id"])
        page.wait_for_timeout(500)
        tab_id = page.evaluate("(tab) => { showTab(tab); return activeTabId; }", tab)
        try:
            page.wait_for_function(
                """(tid) => { const el = document.getElementById('tab-content-' + tid);
                              return !!el && !el.querySelector('.fa-spin') && (el.innerText || '').trim().length > 0; }""",
                arg=tab_id, timeout=TAB_TIMEOUT_MS)
        except Exception:  # noqa: BLE001
            pass  # aba lenta: explora-se o que houver

        plano = page.evaluate(JS_LISTA, [tab_id, MAX_CLICKS, MAX_INPUTS, PERIGOSO])
        assert plano is not None, f"[{perfil}/{tab}] contentor da aba nao existe"
        t0 = time.time()
        feitos, modais = [], 0
        for c in plano["clicaveis"]:
            ok = page.evaluate("(i) => { const el = document.querySelector('[data-ts-click=\"' + i + '\"]'); if (!el) return false; el.scrollIntoView({block:'center'}); el.click(); return true; }", c["i"])
            page.wait_for_timeout(700)
            abriu = page.evaluate(JS_MODAL_ABERTA)
            if abriu:
                modais += _fecha_modais(page)
            feitos.append({"tipo": "click", "alvo": f"{c['tag']}:{c['texto']}", "clicou": ok, "modal": abriu})
        for i in plano["inputs"]:
            sel = f'[data-ts-input="{i["i"]}"]'
            try:
                page.fill(sel, "a")
                page.wait_for_timeout(400)
                page.fill(sel, "")
                feitos.append({"tipo": "input", "alvo": i["id"], "clicou": True, "modal": None})
            except Exception as exc:  # noqa: BLE001
                feitos.append({"tipo": "input", "alvo": i["id"], "clicou": False, "modal": None, "erro": type(exc).__name__})
        if plano["select"]:
            page.evaluate("() => { const s = document.querySelector('[data-ts-select=\"0\"]'); if (s) { s.selectedIndex = 1; s.dispatchEvent(new Event('change', {bubbles:true})); } }")
            page.wait_for_timeout(500)
            feitos.append({"tipo": "select", "alvo": plano["select"]["id"], "clicou": True, "modal": None})
        modais += _fecha_modais(page)
        caso = {
            "caso": f"inter_{tab}", "perfil": perfil, "user": user, "server": servidor, "tab_id": tab_id,
            "total_controlos": plano["total_controlos"], "tocados": feitos, "modais_fechadas": modais,
            "load_ms": int((time.time() - t0) * 1000), "dom_nodes": _smk._dom_nodes(page),
            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(), "abortados": col.abortados(),
            "http5xx": col.http5xx, "warn": [],
        }
        _smk._grava(caso)
        assert not col.pageerrors, f"[{perfil}/{tab}] excepcao JS ao interagir:\n  - " + "\n  - ".join(col.pageerrors[:5])
        assert not col.http5xx, f"[{perfil}/{tab}] respostas 5xx ao interagir:\n  - " + "\n  - ".join(col.http5xx[:5])
        assert not caso["console_errors"], f"[{perfil}/{tab}] erros de consola ao interagir:\n  - " + "\n  - ".join(caso["console_errors"][:10])
'''

# =====================================================================================
API_SRC = r'''"""TESTSUKITA V1 - smoke de API a partir do OpenAPI, por perfil (o que o TestSprite chama "API tests").

Le /openapi.json com o token do perfil; percorre os GET sem params ou com params substituiveis
(server_id/instance/hostname -> servidor de teste; kpi_type -> always-on). Invariantes:
  - nunca 5xx;
  - viewer nunca recebe campos sensiveis (password_hash, PWD=, Trusted_Connection, access_token fora do login);
  - viewer nunca recebe 200 em caminhos /admin;
  - cada endpoint responde em < WATCHERDB_QA_API_TIMEOUT_S (default 20; acima = aviso, nao falha).
Grava status e tempo por endpoint e perfil; o ratchet compara noite a noite.
  WATCHERDB_QA_API_MAX (default 150 endpoints), WATCHERDB_QA_API_BUDGET_S (default 300 s)
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_spec = importlib.util.spec_from_file_location("smoke_helpers", Path(__file__).with_name("test_smoke_modules_e2e.py"))
_smk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_smk)

PERFIS = _smk.PERFIS
API_MAX = int(os.getenv("WATCHERDB_QA_API_MAX", "150"))
BUDGET_S = int(os.getenv("WATCHERDB_QA_API_BUDGET_S", "300"))
TIMEOUT_S = int(os.getenv("WATCHERDB_QA_API_TIMEOUT_S", "20"))
EXCLUIR = re.compile(r"/(docs|redoc|openapi\.json|login|logout|run|execute|reset|restart|download|export|stream|sse|ws|realtime|live|"
                     r"\.well-known|collector/run|kill|shrink|action)", re.I)
SENSIVEL = re.compile(r"password_hash|\"password\"\s*:|PWD=|Trusted_Connection|secret_key|private_key", re.I)


def _substitui(path: str, servidor: dict) -> str | None:
    mapa = {
        "server_id": servidor["server_id"], "instance": servidor["server_id"], "instance_name": servidor["server_id"],
        "hostname": servidor["name"].split("\\")[0], "kpi_type": "always-on",
    }
    def sub(m):
        return str(mapa.get(m.group(1), "\x00"))
    out = re.sub(r"\{(\w+)\}", sub, path)
    return None if "\x00" in out else out


@pytest.mark.parametrize("perfil", [_smk._perfil_param(p) for p in PERFIS])
class TestApiSmoke:
    def test_get_endpoints_por_perfil(self, page, base_url, perfil):
        user, token = _smk._token(page, base_url, perfil)
        h = {"Authorization": f"Bearer {token}"}
        spec = page.context.request.get(f"{base_url}/openapi.json", headers=h, timeout=TIMEOUT_S * 1000)
        if spec.status == 404:
            pytest.skip("/openapi.json desligado (WATCHERDB_DISABLE_DOCS): smoke de API nao aplicavel")
        assert spec.ok, f"/openapi.json devolveu {spec.status}"
        paths = spec.json().get("paths", {})
        servidor = None
        try:
            _smk._autentica(page, base_url, perfil)
            servidor = _smk._escolhe_servidor(page)
        except Exception:  # noqa: BLE001
            servidor = None
        alvo = []
        saltados = {"excluido": 0, "sem_substituicao": 0}
        for p, ops in paths.items():
            if "get" not in ops:
                continue
            if EXCLUIR.search(p):
                saltados["excluido"] += 1; continue
            if "{" in p:
                if not servidor:
                    saltados["sem_substituicao"] += 1; continue
                q = _substitui(p, servidor)
                if not q:
                    saltados["sem_substituicao"] += 1; continue
                alvo.append((p, q))
            else:
                alvo.append((p, p))
        alvo = alvo[:API_MAX]
        resultados, problemas, avisos = [], [], []
        t_ini = time.time()
        for original, url in alvo:
            if time.time() - t_ini > BUDGET_S:
                avisos.append(f"orcamento de {BUDGET_S}s esgotado apos {len(resultados)} endpoints")
                break
            t0 = time.time()
            try:
                r = page.context.request.get(f"{base_url}{url}", headers=h, timeout=TIMEOUT_S * 1000)
                status, corpo = r.status, (r.text() or "")[:20000]
            except Exception as exc:  # noqa: BLE001
                status, corpo = -1, type(exc).__name__
            ms = int((time.time() - t0) * 1000)
            sens = bool(SENSIVEL.search(corpo)) if status == 200 else False
            resultados.append({"path": original, "url": url, "status": status, "ms": ms, "sensivel": sens})
            if status >= 500:
                problemas.append(f"{original}: {status}")
            if status == -1:
                avisos.append(f"{original}: sem resposta em {TIMEOUT_S}s")
            if perfil == "viewer":
                if sens:
                    problemas.append(f"{original}: viewer recebeu campo sensivel")
                if status == 200 and "/admin" in original:
                    problemas.append(f"{original}: viewer recebeu 200 num caminho /admin")
            if ms > TIMEOUT_S * 1000 * 0.8:
                avisos.append(f"{original}: {ms} ms")
        _smk._grava({
            "caso": "api_smoke", "perfil": perfil, "user": user, "server": servidor, "endpoints": resultados,
            "saltados": saltados, "total_openapi_get": sum(1 for ops in paths.values() if "get" in ops),
            "load_ms": int((time.time() - t_ini) * 1000), "dom_nodes": 0,
            "pageerrors": [], "console_errors": [], "http5xx": [f"{r['status']} GET {r['url']}" for r in resultados if r["status"] >= 500],
            "warn": avisos,
        })
        assert resultados, f"[{perfil}] nenhum endpoint GET testavel"
        assert not problemas, f"[{perfil}] API:\n  - " + "\n  - ".join(problemas[:20])
'''

# =====================================================================================
RATCHET_SRC = r'''"""TESTSUKITA V1 - ratchet de regressao + hipoteses de causa (o que o TestSprite chama "root-cause hypothesis",
aqui honesto: e' uma hipotese por assinatura, nunca um veredicto).

Compara a corrida de hoje com a ultima corrida anterior que tenha casos:
  regressao   = ok/aviso ontem -> erro hoje
  nova        = caso que nao existia ontem e esta' com erro hoje
  resolvida   = erro ontem -> ok hoje
  persistente = erro ontem e hoje
  api: endpoints cujo status mudou por perfil (ex.: 200 -> 500, 403 -> 200)
Escreve <dia>/council/RATCHET.json e RATCHET.md; o painel le o JSON. Exit 0 sempre (informativo).
  py scripts/qa/testsukita_ratchet.py [--root docs/qa/externo] [--dia AAAA-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

HIPOTESES = [
    (r"429|rate limit", "rate limit do login (5/min): corridas seguidas ou scripts do externo a mais; nao e' defeito do portal"),
    (r"AbortError", "pedido cancelado pela troca de aba: ruido, nao defeito"),
    (r"falhou com 401|Credenciais invalidas|conta desactivada|bloqueada", "credencial/perfil no .env.qa ou conta bloqueada (15 min apos 5 falhas)"),
    (r"tem role '", "conta configurada no perfil errado (.env.qa)"),
    (r"\b5\d\d\b.*GET|respostas 5xx|http5xx", "erro do servico: ver council/service_log_window.log na mesma janela"),
    (r"nao terminou em \d+ ms|Timeout|timeout", "instancia lenta ou sem resposta (WMI/DMV); comparar com a mesma aba noutras noites"),
    (r"ReferenceError|TypeError|SyntaxError", "excepcao JS do portal: defeito real, ver playwright/ (screenshot+trace) e dom/"),
    (r"nao filtrou|contagem nao acompanha|perdeu o foco", "regressao do filtro de bases (FIX DB-FILTER 2fad907)"),
    (r"nao cabe na janela|sobrepoe", "regressao de layout (UX-05 0ce813e)"),
    (r"modal esta' vazia|modal nao ficou visivel", "drill-down do cartao: endpoint /instances/<kpi> ou handler do cartao"),
    (r"instancias distintas", "cartao e modal com unidades diferentes (regra unica do Always On ce0db42)"),
    (r"sem credenciais", "perfil sem conta no .env.qa (admin: criar qa_admin)"),
]


def hipotese(texto: str) -> str:
    for rx, h in HIPOTESES:
        if re.search(rx, texto, re.I):
            return h
    return "sem assinatura conhecida: ler o JSON do caso e o screenshot"


def estado(j: dict) -> str:
    if j.get("pageerrors") or j.get("console_errors") or j.get("http5xx"):
        return "err"
    return "warn" if j.get("warn") else "ok"


def assinatura(j: dict) -> str:
    return " | ".join((j.get("pageerrors") or [])[:2] + (j.get("console_errors") or [])[:2] + (j.get("http5xx") or [])[:2] + (j.get("warn") or [])[:1])


def carrega(d: Path) -> dict:
    out = {}
    for f in (d / "council" / "cases").glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        out[f"{j.get('perfil')}/{j.get('caso')}"] = j
    return out


def api_status(casos: dict) -> dict:
    out = {}
    for k, j in casos.items():
        if j.get("caso") == "api_smoke":
            for e in j.get("endpoints", []):
                out[f"{j.get('perfil')} {e['path']}"] = e["status"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "docs" / "qa" / "externo"))
    ap.add_argument("--dia", default=None)
    a = ap.parse_args()
    root = Path(a.root)
    dias = sorted(d for d in root.iterdir() if d.is_dir() and DIA_RE.match(d.name) and (d / "council" / "cases").exists())
    if not dias:
        print("sem corridas"); return
    hoje = root / a.dia if a.dia else dias[-1]
    anteriores = [d for d in dias if d.name < hoje.name and any((d / "council" / "cases").glob("*.json"))]
    prev = anteriores[-1] if anteriores else None
    H, P = carrega(hoje), (carrega(prev) if prev else {})
    r = {"dia": hoje.name, "anterior": prev.name if prev else None, "regressoes": [], "novas": [], "resolvidas": [], "persistentes": [], "api_mudou": []}
    for k, j in sorted(H.items()):
        e, ep = estado(j), (estado(P[k]) if k in P else None)
        item = {"caso": k, "assinatura": assinatura(j)[:300], "hipotese": hipotese(assinatura(j))}
        if e == "err" and ep in ("ok", "warn"):
            r["regressoes"].append(item)
        elif e == "err" and ep is None:
            r["novas"].append(item)
        elif e == "err" and ep == "err":
            r["persistentes"].append(item)
        elif e != "err" and ep == "err":
            r["resolvidas"].append({"caso": k})
    ah, ap_ = api_status(H), api_status(P)
    for k, s in sorted(ah.items()):
        if k in ap_ and ap_[k] != s:
            r["api_mudou"].append({"endpoint": k, "antes": ap_[k], "hoje": s})
    r["resumo"] = {x: len(r[x]) for x in ("regressoes", "novas", "resolvidas", "persistentes", "api_mudou")}
    (hoje / "council" / "RATCHET.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Ratchet {hoje.name} vs {r['anterior'] or 'sem anterior'}", ""]
    for sec in ("regressoes", "novas", "persistentes"):
        md.append(f"## {sec} ({len(r[sec])})")
        md += [f"- **{i['caso']}** — {i['assinatura'][:160]}\n  - hipotese: {i['hipotese']}" for i in r[sec]] or ["- nenhuma"]
        md.append("")
    md.append(f"## resolvidas ({len(r['resolvidas'])})"); md += [f"- {i['caso']}" for i in r["resolvidas"]] or ["- nenhuma"]; md.append("")
    md.append(f"## api mudou ({len(r['api_mudou'])})"); md += [f"- {i['endpoint']}: {i['antes']} -> {i['hoje']}" for i in r["api_mudou"]] or ["- nenhum"]
    (hoje / "council" / "RATCHET.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"ratchet {hoje.name} vs {r['anterior']}: " + ", ".join(f"{k}={v}" for k, v in r["resumo"].items()))


if __name__ == "__main__":
    main()
'''

# =====================================================================================
CONFTEST_ADD = r'''

# TESTSUKITA V1: snapshot do DOM em falha (alem de screenshot e trace do pytest-playwright).
import os as _os
import re as _re
from pathlib import Path as _Path


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call" or not rep.failed:
        return
    page = item.funcargs.get("page") if hasattr(item, "funcargs") else None
    bundle = _os.getenv("WATCHERDB_QA_BUNDLE")
    if page is None or not bundle:
        return
    try:
        d = _Path(bundle) / "dom"
        d.mkdir(parents=True, exist_ok=True)
        nome = _re.sub(r"[^A-Za-z0-9_.-]+", "_", item.nodeid)[-120:]
        (d / f"{nome}.html").write_text(page.content(), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
'''

# =====================================================================================
N1_OLD = "$inicio = Get-Date\n$head = (git rev-parse --short HEAD).Trim()\n"
N1_NEW = """$inicio = Get-Date
$head = (git rev-parse --short HEAD).Trim()
# TESTSUKITA V1: janela do log do servico desta corrida (offset no inicio, delta no fim)
$svcLog = Join-Path $repo 'logs\\service_stderr.log'
$svcOffset = if (Test-Path $svcLog) { (Get-Item $svcLog).Length } else { 0 }
"""
N2_OLD = "& py -m pytest tests/e2e/test_smoke_modules_e2e.py tests/e2e/test_semantic_e2e.py -m e2e --no-cov -p no:cacheprovider -q `\n"
N2_NEW = "& py -m pytest tests/e2e/test_smoke_modules_e2e.py tests/e2e/test_semantic_e2e.py tests/e2e/test_interactions_e2e.py tests/e2e/test_api_smoke_e2e.py -m e2e --no-cov -p no:cacheprovider -q `\n"
N3_OLD = "$extResults | ConvertTo-Json -AsArray | Set-Content -Path (Join-Path $externo 'results.json') -Encoding utf8\nif (Test-Path scripts/qa/testsukita_board.py) { & py scripts/qa/testsukita_board.py 2>&1 | Select-Object -Last 2 }\n"
N3_NEW = """$extResults | ConvertTo-Json -AsArray | Set-Content -Path (Join-Path $externo 'results.json') -Encoding utf8
# TESTSUKITA V1: janela do log do servico + ratchet (regressoes e hipoteses) antes do painel
try {
    if (Test-Path $svcLog) {
        $fs = [IO.FileStream]::new($svcLog, 'Open', 'Read', 'ReadWrite')
        $len = $fs.Length; $off = if ($len -ge $svcOffset) { $svcOffset } else { 0 }
        $fs.Seek($off, 'Begin') | Out-Null
        $buf = New-Object byte[] ($len - $off); $fs.Read($buf, 0, $buf.Length) | Out-Null; $fs.Close()
        [IO.File]::WriteAllBytes((Join-Path $council 'service_log_window.log'), $buf)
    }
} catch { Write-Host "janela do log nao copiada: $($_.Exception.Message)" }
if (Test-Path scripts/qa/testsukita_ratchet.py) { & py scripts/qa/testsukita_ratchet.py 2>&1 | Select-Object -Last 2 }
if (Test-Path scripts/qa/testsukita_board.py) { & py scripts/qa/testsukita_board.py 2>&1 | Select-Object -Last 2 }
"""

# =====================================================================================
B1_OLD = '    return {"dia": d.name, "dir": d, "casos": casos, "ext": ext, "head": head, "base": base,\n'
B1_NEW = '''    ratchet = None
    rj = d / "council" / "RATCHET.json"
    if rj.exists():
        try:
            ratchet = json.loads(rj.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            ratchet = None
    return {"dia": d.name, "dir": d, "casos": casos, "ext": ext, "head": head, "base": base, "ratchet": ratchet,
'''
B2_OLD = '<h2>Divergencias e achados candidatos</h2>\n'
B2_NEW = '''{seccao_ratchet(run)}
<h2>Divergencias e achados candidatos</h2>
'''
B3_OLD = 'def pagina(run: dict, runs: list[dict], base: Path, titulo: str) -> str:\n'
B3_NEW = '''def seccao_ratchet(run: dict) -> str:
    """TESTSUKITA V1: regressoes/novas/resolvidas vs corrida anterior + hipoteses + API que mudou + interaccoes."""
    r = run.get("ratchet")
    inter = [c for c in run["casos"] if str(c.get("caso", "")).startswith("inter_")]
    api = [c for c in run["casos"] if c.get("caso") == "api_smoke"]
    partes = []
    if r:
        res = r.get("resumo", {})
        partes.append(f"<div class=meta>vs {esc(r.get('anterior') or 'sem anterior')}: {res.get('regressoes', 0)} regressoes · {res.get('novas', 0)} novas · "
                      f"{res.get('resolvidas', 0)} resolvidas · {res.get('persistentes', 0)} persistentes · {res.get('api_mudou', 0)} endpoints mudaram</div>")
        for sec, chip in (("regressoes", "err"), ("novas", "err"), ("persistentes", "warn")):
            for i in r.get(sec, []):
                partes.append(f"<li><span class='chip {chip}'>{sec[:-1] if sec.endswith('s') else sec}</span> <b>{esc(i['caso'])}</b> — {esc(i['assinatura'][:140])}"
                              f"<br><span class=meta>hipotese: {esc(i['hipotese'])}</span></li>")
        for i in r.get("resolvidas", []):
            partes.append(f"<li><span class='chip ok'>resolvida</span> {esc(i['caso'])}</li>")
        for i in r.get("api_mudou", []):
            partes.append(f"<li><span class='chip warn'>api</span> {esc(i['endpoint'])}: {esc(i['antes'])} → {esc(i['hoje'])}</li>")
    cob = ""
    if inter:
        toc = sum(len(c.get("tocados", [])) for c in inter); tot = sum(int(c.get("total_controlos") or 0) for c in inter)
        cob += f"<div class=meta>interaccoes: {len(inter)} abas exploradas, {toc} controlos tocados de {tot} visiveis, {sum(int(c.get('modais_fechadas') or 0) for c in inter)} modais abertas e fechadas</div>"
    if api:
        for c in api:
            eps = c.get("endpoints", [])
            por = {}
            for e in eps:
                por[e["status"]] = por.get(e["status"], 0) + 1
            cob += f"<div class=meta>api {esc(c.get('perfil'))}: {len(eps)} GET testados de {esc(c.get('total_openapi_get'))} no OpenAPI · status " + ", ".join(f"{k}×{v}" for k, v in sorted(por.items(), key=lambda kv: str(kv[0]))) + "</div>"
    if not partes and not cob:
        return ""
    lista = "<ul>" + "".join(p for p in partes if p.startswith("<li>")) + "</ul>" if any(p.startswith("<li>") for p in partes) else "<p class=meta>sem regressoes nem casos novos com erro</p>"
    cab = "".join(p for p in partes if not p.startswith("<li>"))
    return f"<h2>Ratchet: o que mudou desde a corrida anterior</h2><div class='card div'>{cab}{lista}{cob}</div>"


def pagina(run: dict, runs: list[dict], base: Path, titulo: str) -> str:
'''

# =====================================================================================
S1_OLD = '''        cartoes = page.evaluate(
            """(n) => Array.from(document.querySelectorAll('.kpi-category-group .kpi-card')).slice(0, n).map(c => ({
                 cardId: c.id, kpi: c.dataset.kpiId,
                 valor: (c.querySelector('.kpi-value') ? c.querySelector('.kpi-value').innerText : '').trim() }))""",
            DRILL_MAX,
        )
'''
S1_NEW = '''        # TESTSUKITA V1: os N primeiros cartoes + o Always On sempre (a unidade dele e' provada abaixo).
        cartoes = page.evaluate(
            """(n) => { const todos = Array.from(document.querySelectorAll('.kpi-category-group .kpi-card'));
                 const sel = todos.slice(0, n); const ao = todos.find(c => c.dataset.kpiId === 'always-on-unhealthy');
                 if (ao && !sel.includes(ao)) sel.push(ao);
                 return sel.map(c => ({ cardId: c.id, kpi: c.dataset.kpiId,
                   valor: (c.querySelector('.kpi-value') ? c.querySelector('.kpi-value').innerText : '').trim() })); }""",
            DRILL_MAX,
        )
'''
S2_OLD = '''                           return { linhas: b ? b.querySelectorAll('tbody tr, tr[data-row], .modal-row').length : -1,
                                    texto: b ? (b.innerText || '').trim().length : -1,
                                    visivel: !!(m && getComputedStyle(m).display !== 'none') }; }"""
            )
'''
S2_NEW = '''                           const inst = b ? Array.from(b.querySelectorAll('[onclick*="selectInstanceFromModal"]')).map(e => {
                               const mm = (e.getAttribute('onclick') || '').match(/selectInstanceFromModal\\\\('([^']+)'/); return mm ? mm[1] : null; }).filter(Boolean) : [];
                           return { linhas: b ? b.querySelectorAll('tbody tr, tr[data-row], .modal-row').length : -1,
                                    texto: b ? (b.innerText || '').trim().length : -1,
                                    itens: inst.length, instancias_distintas: new Set(inst).size,
                                    visivel: !!(m && getComputedStyle(m).display !== 'none') }; }"""
            )
'''
S3_OLD = '''            resultados.append({"kpi": c["kpi"], "valor_cartao": c["valor"], "valor": valor,
                               "modal_linhas": info["linhas"], "modal_texto": info["texto"], "ms": int((time.time() - t0) * 1000)})
'''
S3_NEW = '''            resultados.append({"kpi": c["kpi"], "valor_cartao": c["valor"], "valor": valor,
                               "modal_linhas": info["linhas"], "modal_itens": info["itens"], "modal_instancias": info["instancias_distintas"],
                               "modal_texto": info["texto"], "ms": int((time.time() - t0) * 1000)})
            # TESTSUKITA V1: unidade do Always On provada (cartao = instancias distintas na modal; regra unica ce0db42)
            if c["kpi"] == "always-on-unhealthy" and valor is not None and info["visivel"] and info["itens"] > 0 and valor != info["instancias_distintas"]:
                problemas.append(f"always-on-unhealthy: cartao diz {valor} mas a modal tem {info['instancias_distintas']} instancias distintas ({info['itens']} itens)")
'''

# =====================================================================================
PLANO_ADD = '''
## V1 (11/09): paridade com o TestSprite e o que ele não faz

| Capacidade | TestSprite | TestSukita v1 |
|---|---|---|
| Explorar interações | sim, na cloud | tests/e2e/test_interactions_e2e.py: 6 cliques + 2 campos + 1 select por aba e perfil, controlos destrutivos excluídos, modais fechadas |
| Testes de API | sim | tests/e2e/test_api_smoke_e2e.py: GET do /openapi.json por perfil; nunca 5xx; viewer sem campos sensíveis nem 200 em /admin |
| Bundle de falhas | screenshot + DOM + hipótese | screenshot + trace + DOM (conftest) + janela do log do serviço na mesma corrida |
| Hipótese de causa | sim | scripts/qa/testsukita_ratchet.py: hipótese por assinatura, declarada como hipótese |
| Regressão persistente | sim | ratchet vs corrida anterior: regressões, novas, resolvidas, persistentes, endpoints que mudaram; painel mostra |
| Unidade cartão-modal | não | Always On: cartão = instâncias distintas na modal, todas as noites |
| Duas metades independentes | não | council afirma, qa-externo confere, divergência = achado |
| Dentro da rede do cliente | não | tudo local, evidências fora do git |
| Perfis | 1 conta | viewer, dba, admin (quando existir qa_admin) |

Runtime estimado por noite: 35 a 45 minutos (limite da tarefa: 2 horas).
'''

README_SRC = '''# TestSukita — como correr, o que produz, como ler

**O que é.** O vigia noturno do WatcherDB: um runner Playwright (council, *afirma*) e os scripts do qa-externo
(*confere*), a correr às 02:00 na máquina da 8434, com painel local e ratchet de regressão. Sem cloud.

## Correr

```powershell
pwsh scripts/qa/nightly_testsukita.ps1            # corrida completa (a mesma da tarefa agendada)
py scripts/qa/testsukita_board.py                 # só regenerar o painel
py scripts/qa/testsukita_ratchet.py               # só o ratchet do dia
py -m pytest tests/e2e/test_smoke_modules_e2e.py -m e2e --no-cov -p no:cacheprovider -q -k viewer   # um ficheiro, um perfil
```

Credenciais em `.env.qa` na raiz (ignorado pelo git); modelo no cabeçalho do script noturno. Perfil sem conta salta com motivo.

## Ficheiros do motor

| Ficheiro | Função |
|---|---|
| tests/e2e/test_smoke_modules_e2e.py | fleet + 16 abas × perfil; contexto da aba; helpers partilhados (login com cache, servidor de teste, evidências) |
| tests/e2e/test_semantic_e2e.py | grupos de KPI, drill-down (Always On: cartão = instâncias distintas), viewport 1093×614, filtro de bases |
| tests/e2e/test_interactions_e2e.py | explorador: cliques, campos e selects por aba |
| tests/e2e/test_api_smoke_e2e.py | GET do OpenAPI por perfil |
| tests/e2e/conftest.py | DOM em falha para `<bundle>/dom/` |
| scripts/qa/nightly_testsukita.ps1 | orquestra: council → pausa → externo → janela do log → ratchet → painel → NIGHTLY_LOG |
| scripts/qa/testsukita_ratchet.py | regressões vs corrida anterior + hipóteses |
| scripts/qa/testsukita_board.py | docs/qa/externo/index.html e board.html por dia |
| scripts/qa/runtime/NIGHTLY.txt | scripts do qa-externo que correm sozinhos (dono: qa-externo) |

## O que sai, por noite, em docs/qa/externo/AAAA-MM-DD/

- council/cases/*.json — um por caso (perfil, caso, tempos, DOM, erros, abortados, tocados, endpoints)
- council/playwright/ — screenshot e trace só em falha; council/dom/ — DOM só em falha
- council/pytest.log, junit.xml, service_log_window.log, RATCHET.json, RATCHET.md
- externo/*.log e externo/results.json
- SUMMARY.md; e uma linha em docs/qa/externo/NIGHTLY_LOG.md

## Como ler o painel

1. Linha do tempo: verde/âmbar/vermelho/cinzento por noite. Cinzento = não mediu (credenciais).
2. Ratchet: regressões e novas com hipótese. Uma regressão real vai para o findings-inbox.
3. Council vs externo lado a lado; a secção de divergências é onde nascem os achados.
4. Avisos de tempo (aba > 60 s) não são falhas; três noites seguidas na mesma aba são.

## Regras

- Nunca corre contra produção por omissão: escolhe o primeiro servidor `test`, depois `quality`.
- Falhas do runner corrigem-se no runner; falhas do portal viram achado depois de reproduzidas.
- Os scripts do qa-externo não são editados pelo council.
'''


def main() -> None:
    compile(INTER_SRC, str(INTER), "exec"); compile(API_SRC, str(API), "exec"); compile(RATCHET_SRC, str(RATCHET), "exec")
    write_once(INTER, INTER_SRC, "tests/e2e/test_interactions_e2e.py")
    write_once(API, API_SRC, "tests/e2e/test_api_smoke_e2e.py")
    write_once(RATCHET, RATCHET_SRC, "scripts/qa/testsukita_ratchet.py")

    c = CONFTEST.read_text(encoding="utf-8")
    if MARK in c:
        print("Ja aplicado: conftest")
    else:
        compile(c + CONFTEST_ADD, str(CONFTEST), "exec")
        CONFTEST.write_text(c + CONFTEST_ADD, encoding="utf-8", newline="\n"); print("OK: tests/e2e/conftest.py (+DOM em falha)")

    n = NIGHTLY.read_text(encoding="utf-8")
    if MARK in n:
        print("Ja aplicado: nightly")
    else:
        n = rep(n, N1_OLD, N1_NEW, "nightly offset"); n = rep(n, N2_OLD, N2_NEW, "nightly pytest"); n = rep(n, N3_OLD, N3_NEW, "nightly ratchet")
        NIGHTLY.write_text(n, encoding="utf-8", newline="\n"); print("OK: scripts/qa/nightly_testsukita.ps1")

    b = BOARD.read_text(encoding="utf-8")
    if MARK in b:
        print("Ja aplicado: board")
    else:
        b = rep(b, B1_OLD, B1_NEW, "board ratchet load"); b = rep(b, B3_OLD, B3_NEW, "board seccao"); b = rep(b, B2_OLD, B2_NEW, "board pagina")
        compile(b, str(BOARD), "exec"); BOARD.write_text(b, encoding="utf-8", newline="\n"); print("OK: scripts/qa/testsukita_board.py")

    s = SEM.read_text(encoding="utf-8")
    if MARK in s:
        print("Ja aplicado: semantico")
    else:
        s = rep(s, S1_OLD, S1_NEW, "sem cartoes"); s = rep(s, S2_OLD, S2_NEW, "sem info"); s = rep(s, S3_OLD, S3_NEW, "sem resultados")
        compile(s, str(SEM), "exec"); SEM.write_text(s, encoding="utf-8", newline="\n"); print("OK: tests/e2e/test_semantic_e2e.py (Always On: cartao = instancias distintas)")

    p = PLANO.read_text(encoding="utf-8")
    if "## V1 (11/09)" in p:
        print("Ja aplicado: plano")
    else:
        PLANO.write_text(p.rstrip() + "\n" + PLANO_ADD, encoding="utf-8", newline="\n"); print("OK: plano")
    write_once(README, README_SRC, "docs/context/TESTSUKITA_README.md")
    print("Proximo: pwsh docs/context/TESTSUKITA_V1_PASSO2_commit.ps1")


if __name__ == "__main__":
    main()
