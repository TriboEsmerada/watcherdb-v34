"""TestGrapete - PASSO 9: pedidos cancelados pela troca de aba sao ruido do runner, contados mas nao falha.

Noite 1 do TG-2 (11/09 02:00): 41 casos, 1 erro = viewer/alwayson com 7 "[processResponse] X - ERRO:
AbortError: Request aborted". O runner escolhe o servidor (abre o Overview, 8 pedidos) e 500 ms depois muda
de aba; o portal cancela os pedidos em voo e regista cada um como console.error. Intermitente (depende de
quantos ainda estavam em voo). Nao e' defeito do portal no sentido funcional; e' ruido de log (achado P3:
portal 15432 devia registar AbortError como info).

Runner: "AbortError: Request aborted" entra no ruido conhecido, e o JSON de cada caso ganha "abortados": N,
para o numero continuar visivel no painel e no ratchet.

Uso (raiz do repo):  py docs/context/TG1C_PASSO9_ruido_apply.py
Depois:              pwsh docs/context/TG1C_PASSO10_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "tests" / "e2e" / "test_smoke_modules_e2e.py"


def rep(text: str, old: str, new: str, label: str, expected: int = 1) -> str:
    n = text.count(old)
    if n != expected:
        sys.exit(f"ABORT [{label}]: esperava {expected}, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


R_OLD = 'RUIDO_SEMPRE = ("favicon", "chrome-extension://", "ERR_INTERNET_DISCONNECTED")\n'
R_NEW = ('# PASSO 9: "AbortError: Request aborted" = pedido cancelado pela propria troca de aba do runner (contado em "abortados").\n'
         'RUIDO_SEMPRE = ("favicon", "chrome-extension://", "ERR_INTERNET_DISCONNECTED", "AbortError: Request aborted")\n')

C_OLD = '''    def erros_de_consola(self, extra_ruido=()):
        tolerado = RUIDO_SEMPRE + tuple(extra_ruido)
        return [e for e in self.console if not any(r.lower() in e.lower() for r in tolerado)]
'''
C_NEW = '''    def erros_de_consola(self, extra_ruido=()):
        tolerado = RUIDO_SEMPRE + tuple(extra_ruido)
        return [e for e in self.console if not any(r.lower() in e.lower() for r in tolerado)]

    def abortados(self) -> int:
        return sum(1 for e in self.console if "AbortError: Request aborted" in e)
'''

J_OLD = '            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(),\n'
J_NEW = '            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(), "abortados": col.abortados(),\n'


def main() -> None:
    k = SMOKE.read_text(encoding="utf-8")
    if "PASSO 9:" in k:
        print("Ja aplicado.")
        return
    k = rep(k, R_OLD, R_NEW, "ruido")
    k = rep(k, C_OLD, C_NEW, "abortados()")
    k = rep(k, J_OLD, J_NEW, "json", expected=2)
    compile(k, str(SMOKE), "exec")
    SMOKE.write_text(k, encoding="utf-8", newline="\n")
    print("OK: tests/e2e/test_smoke_modules_e2e.py (AbortError = ruido contado)")
    print("Proximo: pwsh docs/context/TG1C_PASSO10_commit.ps1")


if __name__ == "__main__":
    main()
