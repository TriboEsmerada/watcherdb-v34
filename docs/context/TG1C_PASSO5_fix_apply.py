"""TestGrapete TG-1c - PASSO 5: drill-down pela mesma chamada que o cartao faz + 429 com espera.

Corrida do PASSO 4 (16:05):
  - drill-down: o clique real no .kpi-value expirou ("element was detached from the DOM"): o dashboard
    re-renderiza a cada 30 s (kpiRefreshInterval) e os cartoes sao substituidos a meio do clique.
    -> chamar showProblematicInstances(kpiTypeForModal, modalTitle, all) com a MESMA regra que o portal
       usa para construir o onClick do cartao (portal ~34627-34635), via window.KPI_METADATA.
  - grupos/dba: falhou ANTES de gravar JSON (o JSON de dba e' das 15:46): login 429 (rate limit 5/min,
    o smoke viewer tinha acabado de correr). -> em 429 espera 61 s e tenta UMA vez mais.

Uso (raiz do repo):  py docs/context/TG1C_PASSO5_fix_apply.py
Depois:              pwsh docs/context/TG1C_PASSO6_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEM = ROOT / "tests" / "e2e" / "test_semantic_e2e.py"
SMOKE = ROOT / "tests" / "e2e" / "test_smoke_modules_e2e.py"


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT [{label}]: esperava 1, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


D_OLD = '''            # TG-1c PASSO 3: clique real (o portal esvazia _kpiCardClickHandlers depois de ligar os listeners).
            alvo = page.locator(f"#{c['cardId']} .kpi-value")
            if alvo.count() == 0:
                problemas.append(f"{c['kpi']}: cartao sem .kpi-value para clicar")
                continue
            alvo.first.click()
'''
D_NEW = '''            # TG-1c PASSO 5: a mesma chamada que o onClick do cartao faz (portal ~34627-34635), sem depender
            # do DOM, que e' substituido a cada 30 s pelo refresh e fazia o clique real expirar.
            abriu = page.evaluate(
                """(kpiId) => {
                    const k = (window.KPI_METADATA || {})[kpiId];
                    if (!k || typeof showProblematicInstances !== 'function') return false;
                    let tipo = k.kpiType;
                    if ((kpiId.includes('-critical') || kpiId.includes('-warning')) &&
                        !(k.kpiType || '').includes('-critical') && !(k.kpiType || '').includes('-warning')) tipo = kpiId;
                    if (k.all) showProblematicInstances(tipo, k.modalTitle, true); else showProblematicInstances(tipo, k.modalTitle);
                    return true;
                }""",
                c["kpi"],
            )
            if not abriu:
                problemas.append(f"{c['kpi']}: sem entrada em KPI_METADATA ou showProblematicInstances ausente")
                continue
'''

L_OLD = '''    if resposta.status == 429:
        _LOGIN_FALHOU[perfil] = f"login de {user} ({perfil}) devolveu 429: rate limit 5/min esgotado"
        pytest.fail(_LOGIN_FALHOU[perfil] + " (outra corrida em paralelo? esperar 1 min)")
'''
L_NEW = '''    if resposta.status == 429:
        # TG-1c PASSO 5: uma espera e uma nova tentativa antes de desistir (corridas seguidas batem no 5/min).
        time.sleep(61)
        resposta = page.context.request.post(
            f"{base_url}/api/auth/login",
            data=json.dumps({"username": user, "password": pw}),
            headers={"Content-Type": "application/json"},
        )
    if resposta.status == 429:
        _LOGIN_FALHOU[perfil] = f"login de {user} ({perfil}) devolveu 429 duas vezes: rate limit 5/min esgotado"
        pytest.fail(_LOGIN_FALHOU[perfil] + " (outra corrida em paralelo?)")
'''


def main() -> None:
    s = SEM.read_text(encoding="utf-8")
    if "TG-1c PASSO 5" in s:
        print("Ja aplicado: semantico")
    else:
        s = rep(s, D_OLD, D_NEW, "drilldown")
        compile(s, str(SEM), "exec")
        SEM.write_text(s, encoding="utf-8", newline="\n")
        print("OK: tests/e2e/test_semantic_e2e.py (drill-down pela chamada do cartao)")
    k = SMOKE.read_text(encoding="utf-8")
    if "TG-1c PASSO 5" in k:
        print("Ja aplicado: smoke")
    else:
        k = rep(k, L_OLD, L_NEW, "429 retry")
        compile(k, str(SMOKE), "exec")
        SMOKE.write_text(k, encoding="utf-8", newline="\n")
        print("OK: tests/e2e/test_smoke_modules_e2e.py (429 espera 61 s e tenta 1x)")
    print("Proximo: pwsh docs/context/TG1C_PASSO6_commit.ps1")


if __name__ == "__main__":
    main()
