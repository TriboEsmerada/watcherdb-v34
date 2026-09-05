# guard_write_paths.py -- PreToolUse hook (defesa em profundidade)
#
# Regra (BOOTSTRAP_engenharia_contexto_watcherdb.md, Regra Global 1):
#   - Tools de escrita (Write/Edit/MultiEdit/NotebookEdit) so' podem ter
#     alvo em docs/context/** ou .claude/** (projeto) ou ~/.claude/**.
#   - Tools de shell (Bash/PowerShell) sao bloqueadas se o comando contiver
#     padroes de mutacao: git push, rm -rf, DROP, TRUNCATE, DELETE FROM,
#     UPDATE ... SET, INSERT INTO, ALTER.
#   - Tudo o resto passa para o fluxo normal de permissoes (nao decide allow).
#
# Tentativas bloqueadas sao registadas em docs/context/guardrail_log.md.
#
# Escape hatch (so' o humano cria): se existir o ficheiro
# .claude/guardrail_disable na raiz do projeto, o hook nao bloqueia
# (regista a passagem como WAIVER no log). Apagar o ficheiro reativa.

import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
LOG = PROJECT / "docs" / "context" / "guardrail_log.md"
DISABLE_FLAG = PROJECT / ".claude" / "guardrail_disable"

ALLOWED_PREFIXES = [
    PROJECT / "docs" / "context",
    PROJECT / ".claude",
    Path.home() / ".claude",
    # 2026-09-05: zonas de escrita do agente qa-externo (.claude/agents/qa-externo.md)
    PROJECT / "docs" / "qa" / "externo",
    PROJECT / "scripts" / "qa" / "runtime",
]

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}

MUTATION_PATTERNS = [
    (r"git\s+push\b", "git push"),
    (r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\b", "rm -rf"),
    (r"Remove-Item\b.*(-Recurse\b.*-Force|-Force\b.*-Recurse)", "Remove-Item -Recurse -Force"),
    (r"\bDROP\s+(TABLE|DATABASE|INDEX|PROC(EDURE)?|VIEW|TRIGGER|LOGIN|USER|SCHEMA)\b", "SQL DROP"),
    (r"\bTRUNCATE\s+TABLE\b", "SQL TRUNCATE"),
    (r"\bDELETE\s+FROM\b", "SQL DELETE"),
    (r"\bINSERT\s+INTO\b", "SQL INSERT"),
    (r"\bUPDATE\s+\[?\w[\w.\]\[]*\s+SET\b", "SQL UPDATE"),
    (r"\bALTER\s+(TABLE|DATABASE|INDEX|PROC(EDURE)?|VIEW|LOGIN|USER|SERVER|SCHEMA)\b", "SQL ALTER"),
]


def log_entry(decision, tool, target, reason):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"- `{ts}` | {decision} | {tool} | `{target}` | {reason}\n")
    except OSError:
        pass  # logging nunca pode rebentar o hook


def deny(tool, target, reason):
    log_entry("DENY", tool, target, reason)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"[guardrail] {reason}. Alvo: {target}. Escrita permitida apenas em "
                "docs/context/** e .claude/**; mutacoes vao em bloco de codigo para "
                "execucao manual (CLAUDE.md modo consultor)."
            ),
        }
    }))
    sys.exit(0)


def is_allowed_path(raw_path, cwd):
    p = Path(raw_path)
    if not p.is_absolute():
        p = Path(cwd) / p
    try:
        p = p.resolve()
    except OSError:
        return False
    return any(p == a or a in p.parents for a in ALLOWED_PREFIXES)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        # input ilegivel -> nao bloqueia (fail-open), mas fica registado
        log_entry("ERROR", "?", "stdin", f"JSON invalido no hook: {e}")
        sys.exit(0)

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}
    cwd = data.get("cwd", str(PROJECT))

    if DISABLE_FLAG.exists():
        log_entry("WAIVER", tool, tool_input.get("file_path", tool_input.get("command", ""))[:120],
                  "guardrail_disable presente")
        sys.exit(0)

    if tool in WRITE_TOOLS:
        target = (tool_input.get("file_path")
                  or tool_input.get("notebook_path")
                  or "")
        if target and not is_allowed_path(target, cwd):
            deny(tool, target, "Escrita fora dos caminhos permitidos")

    elif tool in SHELL_TOOLS:
        command = tool_input.get("command", "") or ""
        for pattern, label in MUTATION_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                deny(tool, command[:120], f"Padrao de mutacao detectado: {label}")

    sys.exit(0)


if __name__ == "__main__":
    main()
