"""PASSO 4b: corrige o teste test_health_expoe_a_flag_no_fonte (lote A-2e) que procurava o texto
exacto `'auth': _auth_health_flags()`; o PASSO 4 passou essa linha a `corpo['auth'] = _auth_health_flags()`
(so' com sessao valida). Erro do council: o PASSO 4 devia ter actualizado o teste. O commit fe6fd0b saiu
com este teste vermelho.

Uso (raiz do repo):  py docs/context/LOTE_P4_PASSO4b_fix_teste_apply.py
Depois:              py -m pytest tests/unit/test_reset_revoga_token.py tests/unit/test_health_v3_anonimo.py -q --no-cov
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
T = ROOT / "tests" / "unit" / "test_reset_revoga_token.py"
OLD = "    assert \"'auth': _auth_health_flags()\" in src[i:i + 4000]\n"
NEW = (
    "    # PASSO 4 (2026-09-08): a flag so' sai com sessao valida -> `corpo['auth'] = _auth_health_flags()`\n"
    "    assert \"_auth_health_flags()\" in src[i:i + 4000]\n"
    "    assert \"if await _sessao_valida(request):\" in src[i:i + 4000]\n"
)
s = T.read_text(encoding="utf-8")
if NEW in s:
    print("teste ja corrigido (skip)")
elif s.count(OLD) != 1:
    print(f"ABORT: esperava 1x a ancora, encontrei {s.count(OLD)}")
    sys.exit(1)
else:
    T.write_text(s.replace(OLD, NEW, 1), encoding="utf-8")
    print("test_reset_revoga_token.py: assert do health actualizado")
