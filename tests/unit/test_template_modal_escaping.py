"""
Regression test for FIND-20260428-007 (P1 coverage).

Closes coverage gap identificado pelo qa-specialist em sweep Fase 4.3:
fix 49a21c0 (modal click handler backslash normalize) + fix 29a8485
(blocked-sessions backslash escape FIND-004) NAO tinham regression test.

Approach C: Python static analysis sobre template HTML (sem Jest/Playwright
setup novo). Pytest pattern - detecta drift silencioso em qualquer sprint
futuro que toque no template ~47K linhas.

Detecta:
1. raw ${instanceName} em template literals dentro de onclick="..." HTML attrs
   - Vulneravel a quebra com instancias nomeadas (ex: SQLPRD\\I03)
   - Closures JS (elem.onclick = () => fn(instanceName)) sao seguros (skipped)
2. escapedInstanceName definido em >= 4 scopes (filegroup-usage, transaction-logs
   x2, blocked-sessions)
3. TODO uso de selectInstanceFromModal em template literal usa escapedInstanceName
   (no leak entre scopes, no raw fallback)

Cross-links:
- commit 49a21c0 (fix original modal click handler outros KPIs)
- commit 29a8485 (fix FIND-004 blocked-sessions specific)
- charter qa-specialist USER-FAIL Flow 2 (incident triage 3am instancias nomeadas)
- findings-inbox.md FIND-20260428-007
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


PORTAL_PATH = Path(__file__).resolve().parents[2] / "templates" / "watcherdb_portal.html"


@pytest.fixture(scope="module")
def portal_html() -> str:
    """Load watcherdb_portal.html once per test session."""
    assert PORTAL_PATH.exists(), f"Template nao encontrado: {PORTAL_PATH}"
    return PORTAL_PATH.read_text(encoding="utf-8")


# ============================================================================
# Test 1 — Zero raw ${instanceName} em onclick HTML attribute (template literal)
# ============================================================================

def test_no_raw_instancename_em_onclick_template_literal(portal_html: str) -> None:
    """FIND-004/007: nenhum onclick="...${instanceName}..." em template literal.

    Pattern vulneravel: dentro de uma template literal JS (`...`), `${instanceName}`
    e' interpolado direto na string HTML do attribute onclick. Se instanceName tem
    backslash (SQLPRD\\I03), JS escape rules quebram o argumento.

    Pattern seguro: usar `${escapedInstanceName}` apos definir
    `const escapedInstanceName = instanceName.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');`

    Closures JS (elem.onclick = () => fn(instanceName)) sao seguras - skipped.
    """
    # Match: onclick="...selectInstanceFromModal('${instanceName}'..."
    # NOT: elem.onclick = () => selectInstanceFromModal(instanceName, ...)
    pattern = re.compile(
        r"onclick\s*=\s*[\"\'][^\"\']*selectInstanceFromModal\(\s*[\"\']\$\{instanceName\}[\"\']",
    )
    matches = list(pattern.finditer(portal_html))

    if matches:
        # Mostrar contexto util em failure
        line_no = portal_html[:matches[0].start()].count("\n") + 1
        raise AssertionError(
            f"FIND-004/007 regression: {len(matches)} onclick HTML attribute(s) "
            f"usando raw ${{instanceName}} em template literal (vulneravel a backslash). "
            f"Primeira ocorrencia: linha ~{line_no}. "
            f"Fix: substituir por ${{escapedInstanceName}} (ver pattern em linha ~32542)."
        )


# ============================================================================
# Test 2 — escapedInstanceName definido em >= 4 scopes
# ============================================================================

def test_escaped_instance_name_defined_em_pelo_menos_4_scopes(portal_html: str) -> None:
    """Cada KPI block que renderiza onclick="...${instance}..." deve ter
    escapedInstanceName definido no scope local.

    Scopes esperados (post-FIND-004 fix em 29a8485):
    - filegroup-usage
    - tempdb-status
    - blocked-sessions (NEW from fix 29a8485)

    2026-09-02: os 2 scopes do ramo 'transaction-logs' (sub-fetch live a
    /api/queries/log-space) sairam — era codigo morto (o kpiType chega sempre
    como transaction-logs-critical/-warning e cai no card generico, que usa
    data-attributes em vez de onclick interpolado). Threshold 4 -> 3.
    """
    pattern = re.compile(r"const\s+escapedInstanceName\s*=\s*instanceName\.replace")
    matches = list(pattern.finditer(portal_html))

    assert len(matches) >= 3, (
        f"Esperava >= 3 definicoes de 'const escapedInstanceName = ...', "
        f"got {len(matches)}. Algum KPI block perdeu a definicao? "
        f"Verificar scopes: filegroup-usage, tempdb-status, blocked-sessions."
    )


# ============================================================================
# Test 3 — Todo selectInstanceFromModal em template literal usa escapedInstanceName
# ============================================================================

def test_all_template_literal_modal_calls_use_escaped(portal_html: str) -> None:
    """Para cada chamada selectInstanceFromModal('${...}', ...) dentro de
    template literal HTML, o primeiro argumento deve ser uma variavel
    'escaped<Something>' (CamelCase). Aliases legitimos:
    - escapedInstanceName (KPIs filegroup, tempdb-status, blocked-sessions)
    - escapedHostname (KPI disk-latency, linha ~33226)

    Esta e' a invariante POSITIVA - complementa Test 1 (NEGATIVE assertion).
    Detecta tambem regressao a vars raw (e.g. instanceName, hostname raw).
    """
    # Captura: onclick="...selectInstanceFromModal('${SOMETHING}', ...)..."
    pattern = re.compile(
        r"onclick\s*=\s*[\"\'][^\"\']*selectInstanceFromModal\(\s*[\"\']\$\{(\w+)\}[\"\']",
    )
    matches = pattern.findall(portal_html)

    # Allowlist: var name deve comecar com 'escaped' (CamelCase) E nao ser raw
    escaped_pattern = re.compile(r"^escaped[A-Z]\w*$")
    bad_args = [arg for arg in matches if not escaped_pattern.match(arg)]
    assert not bad_args, (
        f"Esperava TODOS os onclick selectInstanceFromModal('${{X}}', ...) a usarem "
        f"variavel 'escaped<Something>' (CamelCase, evita backslash injection). "
        f"Vars sem prefix 'escaped' encontradas: {sorted(set(bad_args))}. "
        f"Fix: substituir por escapedInstanceName/escapedHostname/etc."
    )


# ============================================================================
# Test 4 — escapedInstanceName replace pattern preserva os 3 escapes essenciais
# ============================================================================

def test_escaped_instance_name_replace_pattern_complete(portal_html: str) -> None:
    """O replace chain deve cobrir os 3 escapes essenciais para template literal
    dentro de HTML attribute:

      .replace(/\\\\/g, '\\\\\\\\')   # backslash -> \\\\
      .replace(/'/g, "\\\\'")          # single-quote -> \\'
      .replace(/"/g, '&quot;')        # double-quote -> &quot;

    Detecta drift se alguem refactor remover um destes (ex: skip backslash escape
    "porque nao e' comum" - exactamente o bug que FIND-004 fix corrigiu).
    """
    pattern_full = re.compile(
        r"const\s+escapedInstanceName\s*=\s*instanceName"
        r"\.replace\(/\\\\/g,\s*['\"]\\\\\\\\['\"]\)"
        r"\.replace\(/'/g,\s*[\"']\\\\'[\"']\)"
        r"\.replace\(/\"/g,\s*['\"]&quot;['\"]\)",
    )
    matches = list(pattern_full.finditer(portal_html))
    pattern_any = re.compile(r"const\s+escapedInstanceName\s*=\s*instanceName\.replace")
    any_count = len(list(pattern_any.finditer(portal_html)))

    # 2026-09-02: 3 scopes (filegroup-usage, tempdb-status, blocked-sessions) —
    # os 2 do ramo morto 'transaction-logs' foram removidos com o modal por base.
    assert len(matches) == any_count and any_count >= 3, (
        f"Esperava todas as {any_count} definicoes de escapedInstanceName a usarem "
        f"o replace pattern completo (3 chained replaces). "
        f"Matches do pattern completo: {len(matches)}. "
        f"Drift indica que alguma definicao perdeu um dos escapes."
    )
