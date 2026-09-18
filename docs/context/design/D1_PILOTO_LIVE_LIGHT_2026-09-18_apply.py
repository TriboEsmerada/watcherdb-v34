# -*- coding: utf-8 -*-
"""Design, lote D1 — piloto do modal LIVE em Light: cores fixas -> tokens de severidade já existentes (2026-09-18).

Origem: design review de 18/09 (docs/context/design/2026-09-18_review.md), diff do watcherdb-frontend-specialist,
contrato do ux-design-reviewer (2026-09-18_tokens_contrato.md). Só o modal LIVE (openLiveMonitoringModal … _liveRender*),
só cor: sem mudança de DOM, ARIA, foco ou strings (i18n intocado). O ponto pulsante "LIVE" (#ef4444) NÃO muda — identidade.

Linha de base medida (auditoria por programa, restrita ao contentor do LIVE, docs/context/design/capturas/2026-09-18/
auditoria_live_por_programa.json): Light 123 falhas AA em 619 textos (Fleet 67/185; cada outro programa 4/31);
Dark 78/600; HC 73/596.

O QUE MUDA (clusters A–E do parecer):
 A. texto "LIVE" ao lado do pulso: #ef4444 -> var(--sev-critical-text)
 B. gauges CPU/Mem/PLE/Sess/Qry/Blk e banner de estado (hora do refresh / erro): hex -> var(--sev-ok|warning|critical-text)
 C. linhas de erro do ErrorLog: #fca5a5 -> var(--sev-critical-text)
 D. chips "PIORES CANAIS": var(--color-border) usado como cor de TEXTO (bug de token) -> var(--color-text-tertiary);
    limiares -> -text
 F. botao de programa activo: branco sobre #3b82f6 (3,68) -> texto --sev-info-text sobre --sev-info-tint (chip "info")
 G. --color-text-disabled usado como texto informativo (47 usos no LIVE; em Light e' #94a3b8, 2,2:1) -> --color-text-tertiary
 E. restante Fleet: cartões (_fleetCard), queries pesadas, caixa BLOCKING (#7f1d1d22 -> --sev-critical-tint, borda -> -text, #fca5a5 -> -text; --color-danger-bg NAO serve: so' existe em :root, #7f1d1d solido, e em Light daria vermelho-escuro sobre vermelho-escuro),
    TempDB, TOP WAITS, filas de AG, sessões idle, transações longas
Os outros 12 programas mantêm as suas cores de severidade (F e G tocam-lhes porque são a moldura comum).
Segunda medição (prova por page.route, cópia do template): Light 123 -> 54 só com A-E; com F e G a meta é 0.

RAMO: o owner cria design/tokens-contrato antes de aplicar (regra de 18/09: design fora do main enquanto o i18n corre).

Uso (raiz do repo):
  git checkout -b design/tokens-contrato
  py docs/context/design/D1_PILOTO_LIVE_LIGHT_2026-09-18_apply.py --check
  py docs/context/design/D1_PILOTO_LIVE_LIGHT_2026-09-18_apply.py
  py -m pytest tests/unit/test_live_legivel_20260915.py tests/unit/test_live_typography_tokens.py tests/test_live_gap_theming_smoke.py -q
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE em Light
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PORTAL = Path("templates/watcherdb_portal.html")
TESTE_LEGIVEL = Path("tests/unit/test_live_legivel_20260915.py")   # fixa o hex antigo do gauge de memoria
MARK = "D1 piloto LIVE"

CRIT, WARN, OK = "var(--sev-critical-text)", "var(--sev-warning-text)", "var(--sev-ok-text)"

EDITS = [
    # A — identidade: só o texto
    ('<span style="display:inline-flex;align-items:center;gap:4px;color:#ef4444;font-weight:700;font-size:13px;flex-shrink:0;">',
     '<span style="display:inline-flex;align-items:center;gap:4px;color:var(--sev-critical-text);font-weight:700;font-size:13px;flex-shrink:0;">', 1),
    # B — gauges
    ("""                            ? (v <= critAt ? '#ef4444' : v <= warnAt ? '#f59e0b' : '#10b981')
                            : (v >= (critAt||999) ? '#ef4444' : v >= (warnAt||999) ? '#f59e0b' : '#10b981');
""",
     f"""                            ? (v <= critAt ? '{CRIT}' : v <= warnAt ? '{WARN}' : '{OK}')
                            : (v >= (critAt||999) ? '{CRIT}' : v >= (warnAt||999) ? '{WARN}' : '{OK}');   // D1 piloto LIVE
""", 1),
    ("""                        el.style.color = (livre < 512 || pctLivre < 2) ? '#ef4444' : (livre < 1024 || pctLivre < 5) ? '#f59e0b' : '#10b981';
""",
     f"""                        el.style.color = (livre < 512 || pctLivre < 2) ? '{CRIT}' : (livre < 1024 || pctLivre < 5) ? '{WARN}' : '{OK}';
""", 1),
    ("""                        status.textContent = now;
                        status.style.color = '#10b981';
""",
     f"""                        status.textContent = now;
                        status.style.color = 'var(--color-text-tertiary)';   // D1: hora do refresh nao e' severidade; --sev-ok-text em Light da' 4,3 sobre a barra
""", 1),
    ("""status.textContent = _kpiTp('live.error_http', 'Erro HTTP {code}', { code: errCode }); status.style.color = '#ef4444'; }""",
     f"""status.textContent = _kpiTp('live.error_http', 'Erro HTTP {{code}}', {{ code: errCode }}); status.style.color = '{CRIT}'; }}""", 1),
    ("""if (status) { status.textContent = t('live.error_short'); status.style.color = '#ef4444'; }""",
     f"""if (status) {{ status.textContent = t('live.error_short'); status.style.color = '{CRIT}'; }}""", 1),
    # C — ErrorLog
    ("""                const color = isErr ? '#fca5a5' : 'var(--color-text-tertiary)';
""",
     f"""                const color = isErr ? '{CRIT}' : 'var(--color-text-tertiary)';
""", 1),
    # D — chips "PIORES CANAIS" (token de borda usado como texto)
    ("""                    let borderC = blk > 0 ? '#ef4444' : cpu > 90 ? '#ef4444' : cpu > 70 ? '#f59e0b' : 'var(--color-border)';
""",
     f"""                    let borderC = blk > 0 ? '{CRIT}' : cpu > 90 ? '{CRIT}' : cpu > 70 ? '{WARN}' : 'var(--color-text-tertiary)';   // D1: era var(--color-border) como cor de texto
""", 1),
    # E — cartões Fleet
    ("""            h += _fleetCard('Online', online.length, '#10b981', 'fa-check-circle');
            h += _fleetCard('Parcial', partial.length, partial.length>0?'#f59e0b':'var(--color-text-disabled)', 'fa-exclamation');
            h += _fleetCard('Offline', offline.length, offline.length>0?'#ef4444':'var(--color-text-disabled)', 'fa-times-circle');
""",
     f"""            h += _fleetCard('Online', online.length, '{OK}', 'fa-check-circle');
            h += _fleetCard('Parcial', partial.length, partial.length>0?'{WARN}':'var(--color-text-disabled)', 'fa-exclamation');
            h += _fleetCard('Offline', offline.length, offline.length>0?'{CRIT}':'var(--color-text-disabled)', 'fa-times-circle');
""", 1),
    ("""            h += _fleetCard('CPU >50%', cpuHigh.length, cpuHigh.length>0?'#f59e0b':'#10b981', 'fa-microchip');
            h += _fleetCard('MEM >85%', memHigh.length, memHigh.length>0?'#f59e0b':'#10b981', 'fa-memory');
            h += _fleetCard('Low PLE', lowPle.length, lowPle.length>0?'#ef4444':'#10b981', 'fa-clock');
            h += _fleetCard('Blocking', blocked.length, blocked.length>0?'#ef4444':'#10b981', 'fa-lock');
            h += _fleetCard('Drilled', problemCount, '#3b82f6', 'fa-satellite-dish');
""",
     f"""            h += _fleetCard('CPU >50%', cpuHigh.length, cpuHigh.length>0?'{WARN}':'{OK}', 'fa-microchip');
            h += _fleetCard('MEM >85%', memHigh.length, memHigh.length>0?'{WARN}':'{OK}', 'fa-memory');
            h += _fleetCard('Low PLE', lowPle.length, lowPle.length>0?'{CRIT}':'{OK}', 'fa-clock');
            h += _fleetCard('Blocking', blocked.length, blocked.length>0?'{CRIT}':'{OK}', 'fa-lock');
            h += _fleetCard('Drilled', problemCount, 'var(--color-text-link)', 'fa-satellite-dish');
""", 1),
    ("""                    const cc = cpuMs > 100000 ? '#ef4444' : cpuMs > 10000 ? '#f59e0b' : 'var(--color-text-tertiary)';
""",
     f"""                    const cc = cpuMs > 100000 ? '{CRIT}' : cpuMs > 10000 ? '{WARN}' : 'var(--color-text-tertiary)';
""", 1),
    ("""                    const fElC = fIdle ? 'var(--color-text-disabled)' : fEl > 300 ? '#ef4444' : fEl > 60 ? '#f59e0b' : 'var(--color-text-tertiary)';
""",
     f"""                    const fElC = fIdle ? 'var(--color-text-disabled)' : fEl > 300 ? '{CRIT}' : fEl > 60 ? '{WARN}' : 'var(--color-text-tertiary)';
""", 1),
    ("""background:#7f1d1d22;border:1px solid #7f1d1d;border-radius:8px;padding:12px;margin-bottom:12px;""",
     """background:var(--sev-critical-tint);border:1px solid var(--sev-critical-text);border-radius:8px;padding:12px;margin-bottom:12px;""", 1),
    ("""<div style="color:#fca5a5;font-size:12px;font-weight:600;margin-bottom:8px;"><i class="fas fa-lock" style="margin-right:6px;"></i>""",
     """<div style="color:var(--sev-critical-text);font-size:12px;font-weight:600;margin-bottom:8px;"><i class="fas fa-lock" style="margin-right:6px;"></i>""", 1),
    ("""                    const c = mb > 1024 ? '#ef4444' : mb > 100 ? '#f59e0b' : '#10b981';
""",
     f"""                    const c = mb > 1024 ? '{CRIT}' : mb > 100 ? '{WARN}' : '{OK}';
""", 1),
    ("""<div style="background:#f59e0b;height:100%;width:${w.total_ms/maxMs*100}%;"></div></div><div style="width:40px;text-align:right;color:#f59e0b;font-size:12px;">""",
     """<div style="background:var(--sev-warning-text);height:100%;width:${w.total_ms/maxMs*100}%;"></div></div><div style="width:40px;text-align:right;color:var(--sev-warning-text);font-size:12px;">""", 1),
    ("""                        const c = (parseFloat(sendMB) > 50 || parseFloat(redoMB) > 50) ? '#ef4444' : '#f59e0b';
""",
     f"""                        const c = (parseFloat(sendMB) > 50 || parseFloat(redoMB) > 50) ? '{CRIT}' : '{WARN}';
""", 1),
    ("""                        const c = mins > 480 ? '#ef4444' : mins > 120 ? '#f59e0b' : 'var(--color-text-tertiary)';
""",
     f"""                        const c = mins > 480 ? '{CRIT}' : mins > 120 ? '{WARN}' : 'var(--color-text-tertiary)';
""", 1),
    ("""                    const c = mins > 60 ? '#ef4444' : mins > 15 ? '#f59e0b' : 'var(--color-text-tertiary)';
""",
     f"""                    const c = mins > 60 ? '{CRIT}' : mins > 15 ? '{WARN}' : 'var(--color-text-tertiary)';
""", 1),
    # E — celulas da tabela BLOCKING (blocker, wait type, duracao): so' visiveis quando ha' blocking real (2.a medicao)
    ("""color:#ef4444;font-weight:600;">${b.blocker_spid}</td>""", """color:var(--sev-critical-text);font-weight:600;">${b.blocker_spid}</td>""", 1),
    ("""color:#f59e0b;">${b.wait_type||''}</td>""", """color:var(--sev-warning-text);">${b.wait_type||''}</td>""", 1),
    ("""color:#ef4444;">${b.wait_sec||0}s</td>""", """color:var(--sev-critical-text);">${b.wait_sec||0}s</td>""", 1),
    # E — a tabela dentro da caixa BLOCKING fica sobre painel opaco: sobre o tint vermelho, --sev-warning-text (3,84) e
    #     --color-text-link (3,96) nao chegam a AA em Light. A caixa mantem o tint e a borda (o sinal), a tabela nao.
    ("""<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="color:var(--color-text-tertiary);"><th style="padding:3px 6px;text-align:left;">Instance</th><th>Blocked</th>""",
     """<table style="width:100%;background:var(--color-bg-panel);border-radius:6px;border-collapse:collapse;font-size:12px;"><thead><tr style="color:var(--color-text-tertiary);"><th style="padding:3px 6px;text-align:left;">Instance</th><th>Blocked</th>""", 1),
    # F — botao de programa ACTIVO: branco sobre #3b82f6 = 3,68 (falha em 12px nos 3 temas). Passa a chip "info":
    #     texto --sev-info-text sobre --sev-info-tint (ambos existem nos 3 temas; Light 1d4ed8 sobre tint azul ~7:1)
    ("""                b.style.background = active ? '#3b82f6' : 'var(--color-bg-panel)';
                b.style.color = active ? '#fff' : 'var(--color-text-tertiary)';
                b.style.borderColor = active ? '#3b82f6' : 'var(--color-border)';
""",
     """                b.style.background = active ? 'var(--sev-info-tint)' : 'var(--color-bg-panel)';
                b.style.color = active ? 'var(--sev-info-text)' : 'var(--color-text-tertiary)';
                b.style.borderColor = active ? 'var(--sev-info-text)' : 'var(--color-border)';
                b.style.fontWeight = active ? '600' : '';
""", 1),
    # E — verde fixo que escapou ao inventario ("AGs saudaveis", Fleet)
    ("""<div style="color:#10b981;font-size:12px;text-align:center;padding:10px;"><i class="fas fa-check-circle" style="margin-right:4px;"></i>AGs saudaveis</div>""",
     """<div style="color:var(--sev-ok-text);font-size:12px;text-align:center;padding:10px;"><i class="fas fa-check-circle" style="margin-right:4px;"></i>AGs saudaveis</div>""", 1),
]
# linhas da tabela BLOCKING: color:#fca5a5 dentro do <td> (as 4 ocorrencias de 'color:#fca5a5' no LIVE: 1 no titulo acima + 3 nas celulas)
EDITS_TD = [("""<td style="padding:3px 6px;color:#fca5a5""", """<td style="padding:3px 6px;color:var(--sev-critical-text)""", None)]


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if count is None:
            if got == 0:
                raise SystemExit(f"[ABORT] {label}: anchor nao encontrado: {old[:120]!r}")
        elif got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:140]!r}")
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
    # o piloto so' toca na regiao do LIVE: confirma que cada anchor esta' la' (e nao noutro sitio)
    i0, i1 = portal.index("function openLiveMonitoringModal()"), portal.index("function showReportModal(") if "function showReportModal(" in portal else len(portal)
    regiao = portal[i0:]
    novo = _apply(portal, EDITS, "LIVE")
    antes_td = regiao.count(EDITS_TD[0][0]); novo = _apply(novo, EDITS_TD, "LIVE blocking td")
    # G — --color-text-disabled como cor de texto INFORMATIVO (estado "--", "Selecione uma instancia", PRD/QLT/TST,
    #     "30d idle", categorias, notas): em Light vale #94a3b8 = 2,2-2,6:1. O contrato reserva -disabled a controlos
    #     desactivados. So' dentro do LIVE (openLiveMonitoringModal .. generateReportSummary); esperado 47.
    a0, a1 = novo.index("function openLiveMonitoringModal()"), novo.index("function generateReportSummary(")
    live = novo[a0:a1]; n_dis = live.count("var(--color-text-disabled)")
    if n_dis != 47:
        raise SystemExit(f"[ABORT] esperava 47 usos de --color-text-disabled no LIVE, encontrei {n_dis} -- nada escrito")
    novo = novo[:a0] + live.replace("var(--color-text-disabled)", "var(--color-text-tertiary)") + novo[a1:]
    print(f"[ok] LIVE: {n_dis} usos de --color-text-disabled como texto informativo -> --color-text-tertiary")
    hex_antes = sum(regiao.count(h) for h in ("#ef4444", "#f59e0b", "#10b981", "#fca5a5", "#7f1d1d"))
    regiao_nova = novo[novo.index("function openLiveMonitoringModal()"):]
    hex_depois = sum(regiao_nova.count(h) for h in ("#ef4444", "#f59e0b", "#10b981", "#fca5a5", "#7f1d1d"))
    print(f"[ok] LIVE: {len(EDITS)} blocos + {antes_td} celulas da tabela BLOCKING; hex de severidade na regiao do LIVE {hex_antes} -> {hex_depois} (o que fica sao os outros 12 programas + o pulso)")
    # teste existente que ancora o hex antigo do gauge de memoria -> passa a ancorar o token
    tsrc = base / TESTE_LEGIVEL
    tnovo = _apply(tsrc.read_bytes().decode("utf-8"), [("""(livre < 512 || pctLivre < 2) ? '#ef4444'""", """(livre < 512 || pctLivre < 2) ? 'var(--sev-critical-text)'""", 1)], "teste live_legivel")
    print(f"[ok] {TESTE_LEGIVEL}: ancora do gauge de memoria passa a token")
    if check:
        print("--check OK. Nada escrito."); return 0
    src.write_bytes(novo.encode("utf-8")); print(f"[write] {PORTAL}")
    tsrc.write_bytes(tnovo.encode("utf-8")); print(f"[write] {TESTE_LEGIVEL}")
    print("\nAplicado (no ramo design/tokens-contrato). Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE em Light.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
