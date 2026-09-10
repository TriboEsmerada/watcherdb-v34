"""TestGrapete TG-1 - PASSO 8: 3.a corrida real (2026-09-09, viewer + dba).

O que a corrida mostrou:
  1. Os 16 avisos "nao terminou em 60000 ms" do viewer com load_ms de 10-16 ms
     eram um TypeError meu: Page.wait_for_function(expression, *, arg=..., timeout=...)
     exige `arg=` por nome; eu passava tab_id posicional, o except apanhava e
     rotulava como "instancia lenta". A aba nunca chegou a ser esperada
     (amostra: "Loading backup analysis...").
     -> arg=tab_id, e o except distingue timeout de erro do runner.
  2. qa_dba: 17 x 401. Cada caso repetia o login falhado -> com
     MAX_FAILED_ATTEMPTS=5 (auth_service.py:85) a conta fica bloqueada 15 min.
     -> a 1.a falha de login por perfil fica em cache; os restantes casos do
     perfil falham de imediato sem novo POST.
  3. Externo 3/5 com 429: council (2-3 logins) + 5 scripts do qa-externo (1 login
     cada) ultrapassam os 5/min do /login.
     -> pausa de 65 s entre council e externo, e 15 s entre scripts.

Uso (raiz do repo):  py docs/context/TG1_PASSO8_fix3_apply.py
Depois:              pwsh docs/context/TG1_PASSO9_commit.ps1  (esperar 15 min se qa_dba ficou bloqueada)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST = ROOT / "tests" / "e2e" / "test_smoke_modules_e2e.py"
NIGHTLY = ROOT / "scripts" / "qa" / "nightly_testgrapete.ps1"


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT [{label}]: esperava 1, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


T1_OLD = '''def _token(page, base_url: str, perfil: str) -> tuple[str, str]:
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
'''
T1_NEW = '''_LOGIN_FALHOU: dict[str, str] = {}


def _token(page, base_url: str, perfil: str) -> tuple[str, str]:
    if perfil in _TOKENS:
        return _TOKENS[perfil]
    # TG-1 PASSO 8: um login falhado por perfil chega. Repetir 17x com a password
    # errada bloqueia a conta (MAX_FAILED_ATTEMPTS=5, 15 min) e mascara a causa.
    if perfil in _LOGIN_FALHOU:
        pytest.fail(_LOGIN_FALHOU[perfil] + " (nao repetido: evita bloquear a conta)")
    user, pw = _creds(perfil)
    resposta = page.context.request.post(
        f"{base_url}/api/auth/login",
        data=json.dumps({"username": user, "password": pw}),
        headers={"Content-Type": "application/json"},
    )
    if resposta.status == 429:
        _LOGIN_FALHOU[perfil] = f"login de {user} ({perfil}) devolveu 429: rate limit 5/min esgotado"
        pytest.fail(_LOGIN_FALHOU[perfil] + " (outra corrida em paralelo? esperar 1 min)")
    if not resposta.ok:
        _LOGIN_FALHOU[perfil] = (f"login de {user} ({perfil}) falhou com {resposta.status}: "
                                 "password errada, conta desactivada ou bloqueada (15 min apos 5 falhas)")
        pytest.fail(_LOGIN_FALHOU[perfil])
'''

T2_OLD = '''                tab_id, timeout=TAB_TIMEOUT_MS,
            )
        except Exception:
            warn.append(f"aba {tab} nao terminou em {TAB_TIMEOUT_MS} ms (instancia lenta ou sem resposta)")
'''
T2_NEW = '''                arg=tab_id, timeout=TAB_TIMEOUT_MS,  # TG-1 PASSO 8: `arg=` e' so' por nome
            )
        except Exception as exc:  # noqa: BLE001
            if "Timeout" in type(exc).__name__ or "imeout" in str(exc):
                warn.append(f"aba {tab} nao terminou em {TAB_TIMEOUT_MS} ms (instancia lenta ou sem resposta)")
            else:
                pytest.fail(f"[{perfil}/{tab}] erro do runner ao esperar pela aba: {type(exc).__name__}: {exc}")
'''

N1_OLD = '''# ---- 2) qa-externo: scripts proprios, intocados, cada um no seu log ----
$extResults = @()
'''
N1_NEW = '''# ---- 2) qa-externo: scripts proprios, intocados, cada um no seu log ----
# TG-1 PASSO 8: /api/auth/login aceita 5/min. O council gastou 2-3; os scripts do
# externo fazem 1 cada. Pausa entre as metades e entre scripts para nao ver 429.
Write-Host "pausa 65 s (rate limit do login) antes do qa-externo"
Start-Sleep -Seconds 65
$extResults = @()
'''
N2_OLD = '''    & py $_.FullName 2>&1 | Out-File -FilePath $log -Encoding utf8
    $extResults += [pscustomobject]@{ script = $_.Name; exit = $LASTEXITCODE }
}
'''
N2_NEW = '''    & py $_.FullName 2>&1 | Out-File -FilePath $log -Encoding utf8
    $extResults += [pscustomobject]@{ script = $_.Name; exit = $LASTEXITCODE }
    Start-Sleep -Seconds 15
}
'''


def main() -> None:
    t = TEST.read_text(encoding="utf-8")
    if "TG-1 PASSO 8" in t:
        print("Ja aplicado: teste")
    else:
        t = rep(t, T1_OLD, T1_NEW, "login cache")
        t = rep(t, T2_OLD, T2_NEW, "arg=")
        compile(t, str(TEST), "exec")
        TEST.write_text(t, encoding="utf-8", newline="\n")
        print("OK: tests/e2e/test_smoke_modules_e2e.py")
    n = NIGHTLY.read_text(encoding="utf-8")
    if "TG-1 PASSO 8" in n:
        print("Ja aplicado: nightly")
    else:
        n = rep(n, N1_OLD, N1_NEW, "pausa")
        n = rep(n, N2_OLD, N2_NEW, "pausa scripts")
        NIGHTLY.write_text(n, encoding="utf-8", newline="\n")
        print("OK: scripts/qa/nightly_testgrapete.ps1")
    print("Proximo: confirmar a password de qa_dba (SELECT abaixo, tu), esperar 15 min, pwsh docs/context/TG1_PASSO9_commit.ps1")


if __name__ == "__main__":
    main()
