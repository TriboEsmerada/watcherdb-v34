# -*- coding: utf-8 -*-
"""Corrige um teste fragil que eu proprio escrevi esta manha (2026-09-16).

test_a_degradacao_continua_a_nao_rebentar_o_login lia uma janela FIXA de 700 caracteres a partir do comentario
"# Check must_change_password flag" e procurava la' dentro o `except Exception as exc:`. O lote da tarde
acrescentou cinco linhas de comentario a esse bloco, o `except` passou a ficar depois dos 700 caracteres e o
teste ficou vermelho -- sem que nada no codigo estivesse errado.

Correccao: a janela deixa de ser um numero e passa a ser o fim real do bloco (a linha que constroi a resposta).
O teste continua a provar o mesmo: a excepcao e' apanhada e nao e' relancada, para o login responder na mesma.

Licao, para nao repetir: janelas por contagem de caracteres partem-se sempre que alguem escreve um comentario.
Ancorar no texto que delimita o bloco.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/FIX_TESTE_JANELA_2026-09-16_apply.py --check
  py docs/context/FIX_TESTE_JANELA_2026-09-16_apply.py
  py -m pytest tests/unit/test_must_change_password_20260916.py tests/unit/test_troca_obrigatoria_20260916.py -q --no-cov
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALVO = Path("tests/unit/test_must_change_password_20260916.py")

OLD = '''    i = AUTH.index("# Check must_change_password flag")
    bloco = AUTH[i:i + 700]
    assert "except Exception as exc:" in bloco
    assert "raise" not in bloco
'''
NEW = '''    i = AUTH.index("# Check must_change_password flag")
    # 2026-09-16: era AUTH[i:i+700]. O lote da tarde acrescentou comentarios ao bloco e o `except` saiu
    # da janela -- teste vermelho sem defeito nenhum. Delimitar pelo fim real do bloco, nao por contagem.
    bloco = AUTH[i:AUTH.index("response = JSONResponse(content=result)", i)]
    assert "except Exception as exc:" in bloco
    assert "raise" not in bloco
'''


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    caminho = (preview or ROOT) / ALVO
    texto = caminho.read_bytes().decode("utf-8")
    if "AUTH.index(\"response = JSONResponse(content=result)\", i)" in texto:
        print("[ABORT] ja aplicado"); return 1
    eol = "\r\n" if "\r\n" in texto else "\n"
    o, n = OLD.replace("\n", eol), NEW.replace("\n", eol)
    if texto.count(o) != 1:
        print(f"[ABORT] anchor esperado 1x, encontrado {texto.count(o)}x -- nada escrito"); return 1
    novo = texto.replace(o, n)
    compile(novo, str(ALVO), "exec")
    print("[ok] teste ancorado no fim do bloco em vez de 700 caracteres")
    if check:
        print("--check OK. Nada escrito."); return 0
    caminho.write_bytes(novo.encode("utf-8")); print(f"[write] {ALVO}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
