# -*- coding: utf-8 -*-
"""Design, lote D4 — ecrã Security do servidor: badges sólidos e cartões com hex -> contrato (2026-09-18).

Linha de base (SQLHDSPRD402\\I01, só o conteúdo da tab): Light 34/173, Dark 24/173, HC 24/173. Grupos:
 - 13 recomendações a 1,11 em Light: texto secundário sobre fundo fixo #1e3a5f (azul-marinho do dark).
 - badges de estado/severidade brancos sobre sólido (#f59e0b WARNING 2,15; #fbbf24 Medium 1,67; #10b981 PASS 2,54;
   #ef4444 Critical 3,76; Info branco sobre --color-text-tertiary 2,35 / 1,54 em HC) — em todos os temas.
 - botão Report (.report-btn-generate) laranja #fb923c sobre tinta laranja: 1,69 em Light (é o botão de todos os módulos).
 - cartões de resumo com gradiente hex+alfa e rótulos pastel do dark (#6ee7b7, #fca5a5, #fcd34d…): o auditor não mede
   gradientes, mas em Light são ilegíveis à vista; passam a tint/borda/texto do contrato e ficam mensuráveis.

O QUE MUDA (só cor; sem strings, sem lógica)
 - getStatusBadge / getSeverityBadge: texto branco sobre sólido -> par tint/texto (pass=ok, warning=warning,
   fail=critical|warning|attention por severidade, unknown/info=neutro; critical, high=warning, medium=attention, low=info).
 - Cartões de resumo: score (ok/warning/critical por faixa), Passed=ok, Failed=critical, Warnings=attention,
   Critical=overflow, High=warning: background var(--sev-*-tint), border var(--sev-*-border), rótulo e valor -text.
 - Caixa de recomendação: #1e3a5f -> --sev-info-tint; título #93c5fd -> --sev-info-text.
 - Cartão de erro da Security: #ef4444 -> --sev-critical-border/-text (âncora de duas linhas; os outros módulos ficam).
 - Cartão informativo "só para instâncias" (#1e3a5f + #3b82f6): padrão partilhado por 11 módulos -> --sev-info-tint/-border
   nos 11 (mesma correcção, contada).
 - .report-btn-generate (global): laranja fixo -> --sev-warning-tint/-border/-text.
 - Toast de alertas criticos (global): fundo #1a1f2e fixo -> --color-bg-elevated; vermelhos -> --sev-critical-*. Era o
   alerta dark no tema light que o owner apontou (titulo em --color-text-bright ficava escuro sobre escuro).

RAMO: design/tokens-contrato. Requer D2 aplicado.

Uso (raiz do repo):
  git checkout design/tokens-contrato
  py docs/context/design/D4_SECURITY_2026-09-18_apply.py --check
  py docs/context/design/D4_SECURITY_2026-09-18_apply.py
  py -m pytest tests/unit/test_diagnosis_layout_wave_20260817.py tests/test_theme_v33_foundation_smoke.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; servidor > Security nos 3 temas
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PORTAL = Path("templates/watcherdb_portal.html")
MARK = "D4 security"

BADGE = "padding:4px 10px;border-radius:4px;font-size:11px;font-weight:bold;"
NEUTRO = "background:rgba(100,116,139,0.15); color:var(--color-text-tertiary);"


def card(sev):
    return f"background: var(--sev-{sev}-tint); border: 1px solid var(--sev-{sev}-border);"


EDITS = [
    # ---- badges de estado ----
    ("""                        return '<span class="badge" style="background:#10b981; color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:bold;"><i class="fas fa-check" style="margin-right:4px;"></i>PASS</span>';""",
     f"""                        return '<span class="badge" style="background:var(--sev-ok-tint); color:var(--sev-ok-text);{BADGE}"><i class="fas fa-check" style="margin-right:4px;"></i>PASS</span>';   // D4 security: tint/text""", 1),
    ("""                        const color = severity === 'critical' ? getSevTokens('CRITICAL').fill : severity === 'high' ? getSevTokens('WARNING').fill : getSevTokens('ATTENTION').fill;
                        return `<span class="badge" style="background:${color}; color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:bold;"><i class="fas fa-times" style="margin-right:4px;"></i>FAIL</span>`;""",
     f"""                        const sev = severity === 'critical' ? 'critical' : severity === 'high' ? 'warning' : 'attention';
                        return `<span class="badge" style="background:var(--sev-${{sev}}-tint); color:var(--sev-${{sev}}-text);{BADGE}"><i class="fas fa-times" style="margin-right:4px;"></i>FAIL</span>`;""", 1),
    ("""                        return '<span class="badge" style="background:#f59e0b; color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:bold;"><i class="fas fa-exclamation-triangle" style="margin-right:4px;"></i>WARNING</span>';""",
     f"""                        return '<span class="badge" style="background:var(--sev-warning-tint); color:var(--sev-warning-text);{BADGE}"><i class="fas fa-exclamation-triangle" style="margin-right:4px;"></i>WARNING</span>';""", 1),
    ("""                        return '<span class="badge" style="background:#6b7280; color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:bold;"><i class="fas fa-question" style="margin-right:4px;"></i>UNKNOWN</span>';""",
     f"""                        return '<span class="badge" style="{NEUTRO}{BADGE}"><i class="fas fa-question" style="margin-right:4px;"></i>UNKNOWN</span>';""", 1),
    # ---- badge de severidade ----
    ("""                    const colors = {
                        'critical': '#ef4444',
                        'high': '#f59e0b',
                        'medium': '#fbbf24',
                        'low': 'var(--color-text-link)',
                        'info': 'var(--color-text-tertiary)'
                    };""",
     """                    const sevs = {   // D4 security: par tint/text do contrato (era branco sobre solido)
                        'critical': 'critical',
                        'high': 'warning',
                        'medium': 'attention',
                        'low': 'info'
                    };""", 1),
    ("""                    const color = colors[severity] || 'var(--color-text-tertiary)';
                    const label = labels[severity] || severity;
                    return `<span class="badge" style="background:${color}; color:#fff; font-size:11px;">${label}</span>`;""",
     f"""                    const sev = sevs[severity];
                    const estilo = sev ? `background:var(--sev-${{sev}}-tint); color:var(--sev-${{sev}}-text);` : '{NEUTRO}';
                    const label = labels[severity] || severity;
                    return `<span class="badge" style="${{estilo}} font-size:11px;">${{label}}</span>`;""", 1),
    # ---- cartoes de resumo ----
    ("""                const scoreColor = securityScore >= 80 ? '#10b981' : securityScore >= 60 ? '#f59e0b' : '#ef4444';""",
     """                const scoreSev = securityScore >= 80 ? 'ok' : securityScore >= 60 ? 'warning' : 'critical';   // D4 security""", 1),
    ("""                        <div class="stat-card" style="position:relative; background: linear-gradient(135deg, ${scoreColor}22, ${scoreColor}11); border: 2px solid ${scoreColor};">""",
     """                        <div class="stat-card" style="position:relative; background: var(--sev-${scoreSev}-tint); border: 2px solid var(--sev-${scoreSev}-border);">""", 1),
    ("""                            <div class="value" style="color: ${scoreColor}; font-size: 32px; font-weight: bold;">${securityScore}%</div>""",
     """                            <div class="value" style="color: var(--sev-${scoreSev}-text); font-size: 32px; font-weight: bold;">${securityScore}%</div>""", 1),
    ("""                        <div class="stat-card" style="position:relative; background: linear-gradient(135deg, #10b98133, #10b98122); border: 1px solid #10b981;">""",
     f"""                        <div class="stat-card" style="position:relative; {card('ok')}">""", 1),
    ("""                            <div class="label" style="color: #6ee7b7;">${t('security.passed')}</div>""", """                            <div class="label" style="color: var(--sev-ok-text);">${t('security.passed')}</div>""", 1),
    ("""                            <div class="value" style="color: #10b981;">${summary.passed || 0}</div>""", """                            <div class="value" style="color: var(--sev-ok-text);">${summary.passed || 0}</div>""", 1),
    ("""                        <div class="stat-card" style="position:relative; background: linear-gradient(135deg, #dc262633, #dc262622); border: 1px solid #dc2626;">""",
     f"""                        <div class="stat-card" style="position:relative; {card('critical')}">""", 1),
    ("""                            <div class="label" style="color: #fca5a5;">${t('security.failed')}</div>""", """                            <div class="label" style="color: var(--sev-critical-text);">${t('security.failed')}</div>""", 1),
    ("""                            <div class="value" style="color: #f87171;">${summary.failed || 0}</div>""", """                            <div class="value" style="color: var(--sev-critical-text);">${summary.failed || 0}</div>""", 1),
    ("""                        <div class="stat-card" style="position:relative; background: linear-gradient(135deg, #d9770633, #d9770622); border: 1px solid #d97706;">""",
     f"""                        <div class="stat-card" style="position:relative; {card('attention')}">""", 1),
    ("""                            <div class="label" style="color: #fcd34d;">${t('security.warnings')}</div>""", """                            <div class="label" style="color: var(--sev-attention-text);">${t('security.warnings')}</div>""", 1),
    ("""                            <div class="value" style="color: #fbbf24;">${summary.warnings || 0}</div>""", """                            <div class="value" style="color: var(--sev-attention-text);">${summary.warnings || 0}</div>""", 1),
    ("""                        <div class="stat-card" style="position:relative; background: linear-gradient(135deg, #be123c33, #be123c22); border: 1px solid #be123c;">""",
     f"""                        <div class="stat-card" style="position:relative; {card('overflow')}">""", 1),
    ("""                            <div class="label" style="color: #fda4af;">${t('security.critical')}</div>""", """                            <div class="label" style="color: var(--sev-overflow-text);">${t('security.critical')}</div>""", 1),
    ("""                            <div class="value" style="color: #fb7185;">${summary.critical_issues || 0}</div>""", """                            <div class="value" style="color: var(--sev-overflow-text);">${summary.critical_issues || 0}</div>""", 1),
    ("""                        <div class="stat-card" style="position:relative; background: linear-gradient(135deg, #ea580c33, #ea580c22); border: 1px solid #ea580c;">""",
     f"""                        <div class="stat-card" style="position:relative; {card('warning')}">""", 1),
    ("""                            <div class="label" style="color: #fdba74;">${t('security.high')}</div>""", """                            <div class="label" style="color: var(--sev-warning-text);">${t('security.high')}</div>""", 1),
    ("""                            <div class="value" style="color: #fb923c;">${summary.high_issues || 0}</div>""", """                            <div class="value" style="color: var(--sev-warning-text);">${summary.high_issues || 0}</div>""", 1),
    # ---- recomendacao ----
    ("""                                            <div style="margin-top: 12px; padding: 12px; background: #1e3a5f; border-left: 3px solid var(--color-text-link); border-radius: 4px;">""",
     """                                            <div style="margin-top: 12px; padding: 12px; background: var(--sev-info-tint); border-left: 3px solid var(--sev-info-border); border-radius: 4px;">""", 1),
    ("""                                                        <strong style="color: #93c5fd; font-size: 12px;">${t('security.recommendation')}</strong>""",
     """                                                        <strong style="color: var(--sev-info-text); font-size: 12px;">${t('security.recommendation')}</strong>""", 1),
    # ---- cartao de erro (so o da Security: ancora de 2 linhas) ----
    ("""                    <div class="card" style="border-left: 4px solid #ef4444;">
                        <h4 style="color: #ef4444; margin: 0 0 12px 0;">
                            <i class="fas fa-exclamation-triangle"></i> ${t('security.error_loading')}""",
     """                    <div class="card" style="border-left: 4px solid var(--sev-critical-border);">
                        <h4 style="color: var(--sev-critical-text); margin: 0 0 12px 0;">
                            <i class="fas fa-exclamation-triangle"></i> ${t('security.error_loading')}""", 1),
    # ---- cartao informativo partilhado pelos 11 modulos (dashboard-kpis) ----
    ("""                    <div class="card" style="background: #1e3a5f; border-left: 4px solid #3b82f6;">""",
     """                    <div class="card" style="background: var(--sev-info-tint); border-left: 4px solid var(--sev-info-border);">""", 11),
    # ---- botao Report (global) ----
    ("""        .report-btn-generate {
            background: rgba(234, 88, 12, 0.15); border: 1px solid rgba(234, 88, 12, 0.3);
            color: #fb923c; padding: 8px 16px; border-radius: 6px; cursor: pointer;""",
     """        .report-btn-generate {   /* D4 security: laranja fixo (1,69 em Light) -> warning do contrato */
            background: var(--sev-warning-tint); border: 1px solid var(--sev-warning-border);
            color: var(--sev-warning-text); padding: 8px 16px; border-radius: 6px; cursor: pointer;""", 1),
    ("""        .report-btn-generate:hover { background: rgba(234, 88, 12, 0.25); transform: translateY(-1px); }""",
     """        .report-btn-generate:hover { filter: brightness(1.08); transform: translateY(-1px); }""", 1),
    # ---- toast de alertas criticos (owner, 18/09: o tema light continua a trazer o alerta dark) ----
    # fundo #1a1f2e fixo com texto em --color-text-bright: em Light o titulo fica escuro sobre escuro.
    ("""            max-width: 420px;
            background: #1a1f2e;
            border: 1px solid #ef4444;
            border-left: 4px solid #ef4444;
""", """            max-width: 420px;
            background: var(--color-bg-elevated);   /* D4 security: era #1a1f2e fixo (toast escuro em Light) */
            border: 1px solid var(--sev-critical-border);
            border-left: 4px solid var(--sev-critical-border);
""", 1),
    ("""            letter-spacing: 1px;
            color: #ef4444;
            background: rgba(239, 68, 68, 0.15);
""", """            letter-spacing: 1px;
            color: var(--sev-critical-text);
            background: var(--sev-critical-tint);
""", 1),
    ("""        .toast-close:hover {
            color: #ef4444;
            background: rgba(239, 68, 68, 0.1);
""", """        .toast-close:hover {
            color: var(--sev-critical-text);
            background: var(--sev-critical-tint);
""", 1),
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
    novo = _apply(portal, EDITS, "security")
    print(f"[ok] security: {len(EDITS)} blocos (badges 6, cartoes 15, recomendacao 2, erro 1, cartao informativo x11, botao Report 2, toast 3)")
    if check:
        print("--check OK. Nada escrito."); return 0
    src.write_bytes(novo.encode("utf-8")); print(f"[write] {PORTAL}")
    print("\nAplicado (ramo design/tokens-contrato). Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; servidor > Security nos 3 temas.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
