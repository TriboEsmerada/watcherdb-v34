# -*- coding: utf-8 -*-
"""Design, lote D3 — Collectors modal: cores fixas e maus usos de token -> contrato (2026-09-18).

Pior ecrã da auditoria externa em Light (436/1566 na medição do owner; 227/932 na nossa, só a modal). Linha de base
por grupo (Light): badge FRESH 106 (#10b981 sobre tint verde, 1,84-2,1), env QA 40 (#fbbf24 sobre tint âmbar, 1,22),
env PRD 21 (4,41), "Nunca"/setas de ordenação 29 (--color-border-strong usado como TEXTO, 2,2-2,56), STALE/QUIET/
FAILED/NEVER_RAN, botão Refresh (branco sobre --color-border, 1,48; em HC branco sobre branco). Dark 108 pelo mesmo
padrão. Só cor: sem DOM, sem strings (i18n intocado), sem lógica.

O QUE MUDA
 - Badges e labels de estado (.coll-badge.*, .coll-state-info-block .label, .coll-stat .n): par tint/texto do contrato
   (--sev-ok|info|warning|critical-tint/-text). NEVER_RAN: tint neutro + texto terciário (era -disabled).
 - QUIET e SCOM são roxos e o contrato não tem roxo: tokens locais --coll-quiet-text/-tint definidos nos 3 temas no
   próprio <style> da modal (dark #c4b5fd, light #6d28d9, HC #d9c8ff; ~7:1 sobre o tint em cada tema).
 - 4.º mau uso de token da série: --color-border-strong como cor de texto ("nunca", "Nunca", setas △▽) -> -tertiary.
 - Botões neutros Refresh/expandir: background:var(--color-border) com texto branco -> bg-tertiary + text-primary.
 - Badges inline do JS (taxa 24h, eventos resolvido/antigo/ativo, Service: RUNNING) deixam de compor hex+alpha ("#10b98122")
   e passam a var(--sev-*-tint)/-text; botões Resolver/Mute passam a -solid/-on.
 - Texto de erro #ef4444/#fca5a5 -> --sev-critical-text; falhas 24h, atraso (STALE/FAILED/FRESH com atraso), mute list.
 - .coll-tab-body pre com fundo #020617 fixo (ilegível em Light) -> --color-bg-panel-2.
 NÃO muda: ícone da torre (#ef4444, identidade), gradiente vermelho do .coll-run-btn (texto branco sobre gradiente, o auditor
 não o mede; fica para o codemod), ícones de estado da fila de execução, botão roxo "Re-run" (#7c3aed, 5,0 com branco).

RAMO: design/tokens-contrato. Requer D1 e D2 aplicados.

Uso (raiz do repo):
  git checkout design/tokens-contrato
  py docs/context/design/D3_COLLECTORS_MODAL_2026-09-18_apply.py --check
  py docs/context/design/D3_COLLECTORS_MODAL_2026-09-18_apply.py
  py -m pytest tests/unit/test_coll_i18n_modal_20260916.py tests/unit/test_coll_i18n_barra_20260916.py tests/unit/test_coll_i18n_detalhe_20260916.py tests/unit/test_coll_i18n_accoes_20260916.py tests/unit/test_coll_i18n_mute_20260916.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; Collectors nos 3 temas
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PORTAL = Path("templates/watcherdb_portal.html")
MARK = "D3 collectors"

OK_T, OK_X = "var(--sev-ok-tint)", "var(--sev-ok-text)"
IN_T, IN_X = "var(--sev-info-tint)", "var(--sev-info-text)"
WA_T, WA_X = "var(--sev-warning-tint)", "var(--sev-warning-text)"
CR_T, CR_X = "var(--sev-critical-tint)", "var(--sev-critical-text)"
QU_T, QU_X = "var(--coll-quiet-tint)", "var(--coll-quiet-text)"
TER = "var(--color-text-tertiary)"

EDITS = [
    # ---- tokens locais do roxo (QUIET/SCOM), no topo do <style> da modal ----
    ("    .coll-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.82); z-index:99999; display:none; align-items:center; justify-content:center; padding:20px; }",
     """    /* D3 collectors: roxo do QUIET/SCOM nao existe no contrato de severidade -> tokens locais, 3 temas */
    :root { --coll-quiet-text:#c4b5fd; --coll-quiet-tint:rgba(139,92,246,0.20); }
    html[data-theme="light"] { --coll-quiet-text:#6d28d9; --coll-quiet-tint:rgba(139,92,246,0.12); }
    html[data-theme="high-contrast"] { --coll-quiet-text:#d9c8ff; --coll-quiet-tint:rgba(139,92,246,0.15); }
    .coll-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.82); z-index:99999; display:none; align-items:center; justify-content:center; padding:20px; }""", 1),
    # ---- numeros dos cartoes ----
    ("    .coll-stat.fresh    .n { color:#10b981; }", f"    .coll-stat.fresh    .n {{ color:{OK_X}; }}", 1),
    ("    .coll-stat.quiet    .n { color:#a78bfa; }", f"    .coll-stat.quiet    .n {{ color:{QU_X}; }}", 1),
    ("    .coll-stat.stale    .n { color:#f59e0b; }", f"    .coll-stat.stale    .n {{ color:{WA_X}; }}", 1),
    ("    .coll-stat.failed   .n { color:#ef4444; }", f"    .coll-stat.failed   .n {{ color:{CR_X}; }}", 1),
    # ---- badges da tabela ----
    ("    .coll-badge.fresh    { background:rgba(16,185,129,0.2);  color:#10b981; }", f"    .coll-badge.fresh    {{ background:{OK_T};  color:{OK_X}; }}", 1),
    ("    .coll-badge.recent   { background:rgba(96,165,250,0.2);  color:var(--color-text-link); }", f"    .coll-badge.recent   {{ background:{IN_T};  color:{IN_X}; }}", 1),
    ("    .coll-badge.quiet    { background:rgba(139,92,246,0.2);  color:#a78bfa; }", f"    .coll-badge.quiet    {{ background:{QU_T};  color:{QU_X}; }}", 1),
    ("    .coll-badge.stale    { background:rgba(245,158,11,0.2);  color:#f59e0b; }", f"    .coll-badge.stale    {{ background:{WA_T};  color:{WA_X}; }}", 1),
    ("    .coll-badge.failed   { background:rgba(239,68,68,0.25);  color:#fca5a5; }", f"    .coll-badge.failed   {{ background:{CR_T};  color:{CR_X}; }}", 1),
    ("    .coll-badge.never    { background:rgba(51,65,85,0.4);    color:var(--color-text-disabled); }", f"    .coll-badge.never    {{ background:rgba(100,116,139,0.15); color:{TER}; }}   /* D3: era -disabled sobre slate escuro */", 1),
    ("    .coll-badge.env-prd { background:rgba(59,130,246,0.25); color:var(--color-text-link); }", f"    .coll-badge.env-prd {{ background:{IN_T}; color:{IN_X}; }}", 1),
    ("    .coll-badge.env-qa, .coll-badge.env-qlt { background:rgba(245,158,11,0.25); color:#fbbf24; }", f"    .coll-badge.env-qa, .coll-badge.env-qlt {{ background:{WA_T}; color:{WA_X}; }}", 1),
    ("    .coll-badge.env-scom { background:rgba(139,92,246,0.25); color:#c4b5fd; }", f"    .coll-badge.env-scom {{ background:{QU_T}; color:{QU_X}; }}", 1),
    # ---- labels da modal de estados ----
    ("    .coll-state-info-block.fresh    .label { background:rgba(16,185,129,0.2);  color:#10b981; }", f"    .coll-state-info-block.fresh    .label {{ background:{OK_T};  color:{OK_X}; }}", 1),
    ("    .coll-state-info-block.recent   .label { background:rgba(96,165,250,0.2);  color:var(--color-text-link); }", f"    .coll-state-info-block.recent   .label {{ background:{IN_T};  color:{IN_X}; }}", 1),
    ("    .coll-state-info-block.quiet    .label { background:rgba(139,92,246,0.2);  color:#a78bfa; }", f"    .coll-state-info-block.quiet    .label {{ background:{QU_T};  color:{QU_X}; }}", 1),
    ("    .coll-state-info-block.stale    .label { background:rgba(245,158,11,0.2);  color:#f59e0b; }", f"    .coll-state-info-block.stale    .label {{ background:{WA_T};  color:{WA_X}; }}", 1),
    ("    .coll-state-info-block.failed   .label { background:rgba(239,68,68,0.25);  color:#fca5a5; }", f"    .coll-state-info-block.failed   .label {{ background:{CR_T};  color:{CR_X}; }}", 1),
    ("    .coll-state-info-block.never    .label { background:rgba(51,65,85,0.4);    color:var(--color-text-disabled); }", f"    .coll-state-info-block.never    .label {{ background:rgba(100,116,139,0.15); color:{TER}; }}", 1),
    # ---- pre do detalhe ----
    ("    .coll-tab-body pre { background:#020617; color:var(--color-text-secondary);", "    .coll-tab-body pre { background:var(--color-bg-panel-2); color:var(--color-text-secondary);   /* D3: era #020617 fixo */", 1),
    # ---- JS: botoes neutros do cabecalho ----
    ("""<button onclick="collRefresh(true)" class="coll-run-btn" style="background:var(--color-border);">""",
     """<button onclick="collRefresh(true)" class="coll-run-btn" style="background:var(--color-bg-tertiary);color:var(--color-text-primary);">""", 1),
    ("""style="background:var(--color-border);padding:6px 10px;"><i class="fas fa-expand-alt" id="collMaxIcon" """,
     """style="background:var(--color-bg-tertiary);color:var(--color-text-primary);padding:6px 10px;"><i class="fas fa-expand-alt" id="collMaxIcon" """, 1),
    # ---- JS: taxa 24h (hex+alpha -> tint/text) ----
    ("""            const rateColor = rate >= 95 ? '#10b981' : rate >= 80 ? '#f59e0b' : '#ef4444';
            el.innerHTML += ` <span class="coll-badge" style="background:${rateColor}22;color:${rateColor};margin-left:6px;" `""",
     """            const rateSev = rate >= 95 ? 'ok' : rate >= 80 ? 'warning' : 'critical';   // D3 collectors: tint/text do contrato
            el.innerHTML += ` <span class="coll-badge" style="background:var(--sev-${rateSev}-tint);color:var(--sev-${rateSev}-text);margin-left:6px;" `""", 1),
    # ---- JS: eventos offline ----
    ("""'<span class="coll-badge" style="background:#10b98122;color:#10b981;">'""", f"""'<span class="coll-badge" style="background:{OK_T};color:{OK_X};">'""", 1),
    ("""'<span class="coll-badge" style="background:#f59e0b22;color:#f59e0b;" title="'""", f"""'<span class="coll-badge" style="background:{WA_T};color:{WA_X};" title="'""", 1),
    ("""'<span class="coll-badge" style="background:#ef444422;color:#ef4444;">'""", f"""'<span class="coll-badge" style="background:{CR_T};color:{CR_X};">'""", 1),
    ("""style="background:#10b981;color:white;border:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:10px;font-weight:600;">' + _collT('coll.events.resolve'""",
     """style="background:var(--sev-ok-solid);color:var(--sev-ok-on);border:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:10px;font-weight:600;">' + _collT('coll.events.resolve'""", 1),
    # ---- JS: estado do servico ----
    ("""            const colors = { RUNNING:'#10b981', STOPPED:'#ef4444', PAUSED:'#f59e0b' };
            const color = colors[d.state] || 'var(--color-text-disabled)';
            el.innerHTML = `<span class="coll-badge" style="background:${color}33;color:${color};">Service: ${d.state}</span>`;""",
     """            const sevs = { RUNNING:'ok', STOPPED:'critical', PAUSED:'warning' };   // D3 collectors
            const sev = sevs[d.state];
            const estilo = sev ? `background:var(--sev-${sev}-tint);color:var(--sev-${sev}-text);` : 'background:rgba(100,116,139,0.15);color:var(--color-text-tertiary);';
            el.innerHTML = `<span class="coll-badge" style="${estilo}">Service: ${d.state}</span>`;""", 1),
    # ---- JS: mute list ----
    ("""                <h4 style="margin:0 0 10px 0;color:#fbbf24;font-size:13px;">""", """                <h4 style="margin:0 0 10px 0;color:var(--sev-attention-text);font-size:13px;">""", 1),
    ("""style="padding:7px 12px;background:#f59e0b;color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;">""",
     """style="padding:7px 12px;background:var(--sev-warning-solid);color:var(--sev-warning-on);border:none;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;">""", 1),
    ("""                const colorLeft = hrsLeft < 4 ? '#ef4444' : hrsLeft < 24 ? '#f59e0b' : '#10b981';""",
     f"""                const colorLeft = hrsLeft < 4 ? '{CR_X}' : hrsLeft < 24 ? '{WA_X}' : '{OK_X}';""", 1),
    ("""body.innerHTML = `<div style="padding:20px;color:#fca5a5;">${_collT('coll.mute.err_load'""", f"""body.innerHTML = `<div style="padding:20px;color:{CR_X};">${{_collT('coll.mute.err_load'""", 1),
    # ---- JS: tabela ----
    ("""if (body) body.innerHTML = `<div style="padding:40px;color:#ef4444;">Erro: ${e.message}</div>`;""", f"""if (body) body.innerHTML = `<div style="padding:40px;color:{CR_X};">Erro: ${{e.message}}</div>`;""", 1),
    ("""' <span style="color:var(--color-border-strong);">&#9651;&#9661;</span>'""", f"""' <span style="color:{TER};">&#9651;&#9661;</span>'""", 2),
    ("""<td style="color:${(t.failure_count_24h||0)>0?'#ef4444':'var(--color-text-tertiary)'};""", f"""<td style="color:${{(t.failure_count_24h||0)>0?'{CR_X}':'var(--color-text-tertiary)'}};""", 1),
    # ---- JS: celulas de atraso / ultima corrida ----
    ("""            return '<span style="color:var(--color-border-strong);">nunca</span>';""", f"""            return '<span style="color:{TER};">nunca</span>';   // D3: -border-strong nao e' cor de texto""", 1),
    ("""        if (st === 'FAILED') return `<span style="color:#ef4444;font-weight:600;">${txt}</span>`;
        if (st === 'STALE')  return `<span style="color:#f59e0b;">${txt}</span>`;""",
     f"""        if (st === 'FAILED') return `<span style="color:{CR_X};font-weight:600;">${{txt}}</span>`;
        if (st === 'STALE')  return `<span style="color:{WA_X};">${{txt}}</span>`;""", 1),
    ("""        return `<span style="color:#fbbf24;">${txt}</span>`;
    }""", """        return `<span style="color:var(--sev-attention-text);">${txt}</span>`;
    }""", 1),
    ("""<span style="color:#a78bfa;">Sem eventos ha ${ago}</span>""", f"""<span style="color:{QU_X};">Sem eventos ha ${{ago}}</span>""", 2),
    ("""            return '<span style="color:var(--color-border-strong);">Nunca</span>';""", f"""            return '<span style="color:{TER};">Nunca</span>';""", 1),
    # ---- JS: detalhe ----
    ("""<div style="color:${(task.failure_count_24h||0)>0?'#ef4444':'#10b981'};font-weight:600;">""", f"""<div style="color:${{(task.failure_count_24h||0)>0?'{CR_X}':'{OK_X}'}};font-weight:600;">""", 1),
    ("""'<div style="color:#ef4444;padding:20px;">' + _collT('coll.det.error'""", f"""'<div style="color:{CR_X};padding:20px;">' + _collT('coll.det.error'""", 4),
]
# badge do cabecalho dos eventos offline (hex+alpha -> tint/text)
EDITS += [
    ("""        const badgeColor = active.length === 0 ? '#10b981' : (active.length === oldCount ? '#f59e0b' : '#ef4444');""",
     """        const badgeSev = active.length === 0 ? 'ok' : (active.length === oldCount ? 'warning' : 'critical');   // D3 collectors""", 1),
    ("""<span class="coll-badge" style="margin-left:auto;background:${badgeColor}22;color:${badgeColor};">${badgeText}</span>""",
     """<span class="coll-badge" style="margin-left:auto;background:var(--sev-${badgeSev}-tint);color:var(--sev-${badgeSev}-text);">${badgeText}</span>""", 1),
]


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:160]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = base / PORTAL
    portal = src.read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "D2 contrato" not in portal:
        print("[ABORT] o D2 nao esta aplicado neste template (ramo errado?)"); return 1
    i0 = portal.index(".coll-overlay { position:fixed;"); i1 = portal.index("</script>", portal.index("window.openCollectorsModal"))
    hex_antes = len(__import__("re").findall(r"#[0-9a-fA-F]{6}\b", portal[i0:i1]))
    novo = _apply(portal, EDITS, "collectors")
    j0 = novo.index(".coll-overlay { position:fixed;"); j1 = novo.index("</script>", novo.index("window.openCollectorsModal"))
    hex_depois = len(__import__("re").findall(r"#[0-9a-fA-F]{6}\b", novo[j0:j1]))
    print(f"[ok] collectors: {len(EDITS)} blocos; hex na regiao {hex_antes} -> {hex_depois} (ficam icones, gradientes e o roxo do Re-run)")
    if check:
        print("--check OK. Nada escrito."); return 0
    src.write_bytes(novo.encode("utf-8")); print(f"[write] {PORTAL}")
    print("\nAplicado (ramo design/tokens-contrato). Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; Collectors nos 3 temas.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
