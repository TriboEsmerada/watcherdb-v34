"""TestGrapete TG-1 - PASSO 3: corrige o runner apos a 1.a corrida real (2026-09-09).

O que a corrida mostrou (docs/qa/externo/2026-09-09/council/pytest.log):
  1. 24 respostas 429: /api/auth/login tem @limiter.limit("5/minute")
     (auth_compat.py:324) e o runner fazia login em cada um dos 51 casos.
     -> login UMA vez por perfil (cache em memoria), token reutilizado.
  2. "login de qa_viewer (admin)": o fallback WATCHERDB_QA_USER sem ROLE
     explicito caia no perfil admin. -> fallback so' com WATCHERDB_QA_ROLE
     explicito, e o role devolvido pelo login tem de ser o do perfil.
  3. Servidor escolhido = CAGENPRD06\\I06 (producao): environment no inventario
     e' 'production'/'quality'/'test' e o regex /tst/ nao apanhava 'test'.
     -> ordem test > quality; producao so' com WATCHERDB_QA_SERVER explicito.
  4. "a aba nao foi criada": generateTabId() leva timestamp, logo o id
     calculado pelo teste nunca era o da aba. -> usar `activeTabId` do portal,
     que activateTab() define ao criar/activar a aba (portal ~6919).
  5. Externo: 4 dos 9 scripts do qa-externo exigem argumentos de pauta.
     -> o job noturno so' corre os listados em scripts/qa/runtime/NIGHTLY.txt.
  6. docs/qa/externo/ esta' no .gitignore desde 05/09 (linha 266): evidencias
     e painel sao LOCAIS por desenho (hostnames). O PASSO 2 nao os adiciona.

Uso (raiz do repo):  py docs/context/TG1_PASSO3_fix_apply.py
Depois:              pwsh docs/context/TG1_PASSO4_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST = ROOT / "tests" / "e2e" / "test_smoke_modules_e2e.py"
NIGHTLY = ROOT / "scripts" / "qa" / "nightly_testgrapete.ps1"
NIGHTLY_LIST = ROOT / "scripts" / "qa" / "runtime" / "NIGHTLY.txt"
PLANO = ROOT / "docs" / "context" / "PLANO_TESTGRAPETE_2026-09-09.md"
MARK3 = "TG-1 PASSO 3"


def rep(text: str, old: str, new: str, label: str, expected: int = 1) -> str:
    n = text.count(old)
    if n != expected:
        sys.exit(f"ABORT [{label}]: esperava {expected}, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


# ---------- teste ----------
T_CREDS_OLD = '''def _creds(perfil: str):
    u = os.getenv(f"WATCHERDB_QA_{perfil.upper()}_USER", "")
    p = os.getenv(f"WATCHERDB_QA_{perfil.upper()}_PASS", "")
    if u and p:
        return u, p
    if os.getenv("WATCHERDB_QA_ROLE", "admin").lower() == perfil:
        u, p = os.getenv("WATCHERDB_QA_USER", ""), os.getenv("WATCHERDB_QA_PASS", "")
        if u and p:
            return u, p
    return None
'''
T_CREDS_NEW = '''def _creds(perfil: str):
    u = os.getenv(f"WATCHERDB_QA_{perfil.upper()}_USER", "")
    p = os.getenv(f"WATCHERDB_QA_{perfil.upper()}_PASS", "")
    if u and p:
        return u, p
    # TG-1 PASSO 3: o fallback generico so' serve o perfil se WATCHERDB_QA_ROLE
    # o disser EXPLICITAMENTE (na 1.a corrida, qa_viewer caiu no perfil admin).
    if os.getenv("WATCHERDB_QA_ROLE", "").lower() == perfil:
        u, p = os.getenv("WATCHERDB_QA_USER", ""), os.getenv("WATCHERDB_QA_PASS", "")
        if u and p:
            return u, p
    return None


# TG-1 PASSO 3: /api/auth/login tem rate limit 5/minuto (auth_compat.py:324).
# Um login por perfil por sessao de pytest; o token e' reutilizado.
_TOKENS: dict[str, tuple[str, str]] = {}
'''

T_AUTH_OLD = '''def _autentica(page, base_url: str, perfil: str) -> str:
    user, pw = _creds(perfil)
    resposta = page.context.request.post(
        f"{base_url}/api/auth/login",
        data=json.dumps({"username": user, "password": pw}),
        headers={"Content-Type": "application/json"},
    )
    assert resposta.ok, f"login de {user} ({perfil}) falhou com {resposta.status}"
    corpo = resposta.json()
    token = corpo.get("access_token") or corpo.get("token")
    assert token, f"login devolveu 200 mas sem token: {sorted(corpo)}"
    page.add_init_script(
'''
T_AUTH_NEW = '''def _token(page, base_url: str, perfil: str) -> tuple[str, str]:
    if perfil in _TOKENS:
        return _TOKENS[perfil]
    user, pw = _creds(perfil)
    resposta = page.context.request.post(
        f"{base_url}/api/auth/login",
        data=json.dumps({"username": user, "password": pw}),
        headers={"Content-Type": "application/json"},
    )
    if resposta.status == 429:
        pytest.fail(f"login de {user} ({perfil}) devolveu 429: rate limit 5/min esgotado "
                    "(outra corrida em paralelo? esperar 1 min)")
    assert resposta.ok, f"login de {user} ({perfil}) falhou com {resposta.status}"
    corpo = resposta.json()
    token = corpo.get("access_token") or corpo.get("token")
    assert token, f"login devolveu 200 mas sem token: {sorted(corpo)}"
    role = str(((corpo.get("user") or {}).get("role")) or corpo.get("role") or "").lower()
    if role and role != perfil:
        pytest.fail(f"conta {user} tem role '{role}' mas esta' configurada para o perfil "
                    f"'{perfil}': corrige WATCHERDB_QA_{perfil.upper()}_USER/PASS em .env.qa")
    _TOKENS[perfil] = (user, token)
    return _TOKENS[perfil]


def _autentica(page, base_url: str, perfil: str) -> str:
    user, token = _token(page, base_url, perfil)
    page.add_init_script(
'''

T_SRV_OLD = '''            if (!s) s = allServers.find(x => /tst/i.test(x.environment || ''));
            if (!s) s = allServers[0];
            return s ? { name: s.name, server_id: s.server_id, environment: s.environment || '' } : null;
        }""",
        alvo,
    )
'''
T_SRV_NEW = '''            // TG-1 PASSO 3: environment no inventario e' 'production'/'quality'/'test'.
            // Sem alvo explicito, NUNCA producao: test, depois quality, senao nada.
            if (!s) s = allServers.find(x => /^(test|tst)/i.test(x.environment || ''));
            if (!s) s = allServers.find(x => /^(quality|qlt)/i.test(x.environment || ''));
            return s ? { name: s.name, server_id: s.server_id, environment: s.environment || '' } : null;
        }""",
        alvo,
    )
'''

T_ASSERT_SRV_OLD = '''        servidor = _escolhe_servidor(page)
        assert servidor, "sidebar sem servidores - nada a testar"
'''
T_ASSERT_SRV_NEW = '''        servidor = _escolhe_servidor(page)
        if not servidor:
            pytest.skip("sem servidor de test/quality no inventario e sem WATCHERDB_QA_SERVER: "
                        "o smoke nao corre contra producao por omissao")
'''

T_TAB_OLD = '''        tab_id = page.evaluate(
            "([sid, tab]) => { showTab(tab); return generateTabId(sid, tab); }", [servidor["server_id"], tab]
        )
'''
T_TAB_NEW = '''        # TG-1 PASSO 3: generateTabId() leva timestamp; o id real e' o activeTabId
        # que activateTab() define ao criar/activar a aba.
        tab_id = page.evaluate("(tab) => { showTab(tab); return activeTabId; }", tab)
'''

T_FINAL_OLD = '''        assert tab_id and page.evaluate("(tid) => !!document.getElementById('tab-content-' + tid)", tab_id), \\
            f"[{perfil}/{tab}] a aba nao foi criada (showTab sem servidor seleccionado?)"
'''
T_FINAL_NEW = '''        assert tab_id and page.evaluate("(tid) => !!document.getElementById('tab-content-' + tid)", tab_id), \\
            f"[{perfil}/{tab}] a aba nao foi criada (activeTabId={tab_id!r}; showTab sem servidor seleccionado?)"
'''

# ---------- nightly ----------
N_EXT_OLD = '''Get-ChildItem scripts/qa/runtime -Filter 'qa_ext_*.py' | Sort-Object Name | ForEach-Object {
'''
N_EXT_NEW = '''# TG-1 PASSO 3: so' os scripts listados em scripts/qa/runtime/NIGHTLY.txt (um por linha;
# o qa-externo e' dono da lista). 4 dos 9 exigem argumentos de pauta e nao sao noturnos.
$lista = Join-Path $repo 'scripts\\qa\\runtime\\NIGHTLY.txt'
$nomes = if (Test-Path $lista) { Get-Content $lista | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object { $_.Trim() } } else { @() }
Get-ChildItem scripts/qa/runtime -Filter 'qa_ext_*.py' | Where-Object { $nomes -contains $_.Name } | Sort-Object Name | ForEach-Object {
'''

NIGHTLY_LIST_SRC = """# TestGrapete: scripts do qa-externo que correm SOZINHOS todas as noites (sem argumentos).
# Dono da lista: qa-externo. Um nome por linha. Linhas com # sao ignoradas.
# 2026-09-09: os 5 que correram com exit 0 na 1.a corrida; os outros 4 exigem --token-out/--csv/--fake-user.
qa_ext_a1_login_origin.py
qa_ext_p4r2_live_diag.py
qa_ext_p4r2_live_programs.py
qa_ext_p4r3_health.py
qa_ext_pauta1_fonts.py
"""

P_OLD = "## Ficheiros\n"
P_NEW = """## Evidências são locais por desenho

docs/qa/externo/ está no .gitignore desde 05/09 (linha 266): os bundles têm
hostnames de instâncias e ficam só nesta máquina. O painel (index.html) é local.
O que vai para o git é o motor (runner, job, gerador, NIGHTLY.txt), nunca as corridas.

## 1.ª corrida real (2026-09-09, 8434, perfil admin)

51 casos recolhidos; 15 FAILED por três defeitos do runner, não do portal: rate
limit do login (24 x 429), id da aba calculado com timestamp, servidor escolhido
em produção. Corrigido em TG1_PASSO3_fix_apply.py. Externo: 5 de 9 scripts
correm sem argumentos; lista em scripts/qa/runtime/NIGHTLY.txt.

## Ficheiros
"""


def main() -> None:
    t = TEST.read_text(encoding="utf-8")
    if MARK3 in t:
        print("Ja aplicado: teste")
    else:
        t = rep(t, T_CREDS_OLD, T_CREDS_NEW, "creds")
        t = rep(t, T_AUTH_OLD, T_AUTH_NEW, "autentica")
        t = rep(t, T_SRV_OLD, T_SRV_NEW, "servidor")
        t = rep(t, T_ASSERT_SRV_OLD, T_ASSERT_SRV_NEW, "assert servidor")
        t = rep(t, T_TAB_OLD, T_TAB_NEW, "tab id")
        t = rep(t, T_FINAL_OLD, T_FINAL_NEW, "assert final")
        compile(t, str(TEST), "exec")
        TEST.write_text(t, encoding="utf-8", newline="\n")
        print("OK: tests/e2e/test_smoke_modules_e2e.py")

    n = NIGHTLY.read_text(encoding="utf-8")
    if "NIGHTLY.txt" in n:
        print("Ja aplicado: nightly")
    else:
        n = rep(n, N_EXT_OLD, N_EXT_NEW, "nightly lista")
        NIGHTLY.write_text(n, encoding="utf-8", newline="\n")
        print("OK: scripts/qa/nightly_testgrapete.ps1")

    if NIGHTLY_LIST.exists():
        print("Ja existe: scripts/qa/runtime/NIGHTLY.txt")
    else:
        NIGHTLY_LIST.write_text(NIGHTLY_LIST_SRC, encoding="utf-8", newline="\n")
        print("OK: scripts/qa/runtime/NIGHTLY.txt")

    p = PLANO.read_text(encoding="utf-8")
    if "1.ª corrida real" in p:
        print("Ja aplicado: plano")
    else:
        PLANO.write_text(rep(p, P_OLD, P_NEW, "plano"), encoding="utf-8", newline="\n")
        print("OK: docs/context/PLANO_TESTGRAPETE_2026-09-09.md")
    print("Proximo: pwsh docs/context/TG1_PASSO4_commit.ps1")


if __name__ == "__main__":
    main()
