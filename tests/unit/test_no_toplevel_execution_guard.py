"""
Guarda anti-recaida (2026-08-31): scripts disfarcados de teste.

Historia: tests/integration/test_favicon.py tinha codigo executavel no topo do
modulo -- ligava a 127.0.0.1:8000 e chamava sys.exit(1) ao falhar. Um sys.exit
durante a COLECCAO do pytest aborta a corrida inteira com INTERNALERROR, que
nao se parece com falha de teste (parece problema de ambiente) e ignora-se.
A suite ficou 0 testes executaveis sem ninguem dar por isso.

Este teste falha se algum tests/**/test_*.py tiver, ao nivel do modulo (fora
de funcoes/classes e fora do guard `if __name__ == "__main__"`), chamadas da
classe que rebenta a coleccao: sys.exit, rede, subprocess, main().
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # tests/

# Prefixos/nomes de chamada proibidos ao nivel do modulo.
_FORBIDDEN_NAMES = {"exit", "quit", "main"}
_FORBIDDEN_DOTTED_PREFIXES = (
    "sys.exit",
    "os.system",
    "os._exit",
    "subprocess.",
    "requests.",
    "httpx.",
    "urllib.",
    "socket.",
)


def _dotted(node):
    """Devolve o nome pontuado de um Call target (ex: 'sys.exit'), ou ''."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_main_guard(node):
    if not isinstance(node, ast.If):
        return False
    t = node.test
    return (
        isinstance(t, ast.Compare)
        and isinstance(t.left, ast.Name)
        and t.left.id == "__name__"
    )


def _module_level_calls(tree):
    """Calls em statements do nivel do modulo, sem descer a def/class nem ao
    guard __main__ (que nao executa no import do pytest)."""
    stmts = []

    def collect(body):
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if _is_main_guard(stmt):
                continue
            stmts.append(stmt)
            for field in ("body", "orelse", "finalbody", "handlers"):
                sub = getattr(stmt, field, None)
                if sub:
                    collect([h for h in sub] if field != "handlers" else [s for h in sub for s in h.body])

    collect(tree.body)
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                yield node


def test_no_executable_toplevel_in_test_files():
    offenders = []
    for path in sorted(ROOT.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for call in _module_level_calls(tree):
            name = _dotted(call.func)
            if name in _FORBIDDEN_NAMES or name.startswith(_FORBIDDEN_DOTTED_PREFIXES):
                offenders.append(f"{path.relative_to(ROOT)}:{call.lineno} -> {name}()")
    assert not offenders, (
        "Codigo executavel perigoso ao nivel do modulo em ficheiros de teste "
        "(aborta a coleccao do pytest; mover para check_*_manual.py ou para "
        "dentro de funcoes):\n" + "\n".join(offenders)
    )
