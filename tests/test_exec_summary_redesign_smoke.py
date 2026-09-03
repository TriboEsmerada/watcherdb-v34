#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_exec_summary_redesign_smoke.py -- Resumo Executivo redesign V3.3 (2026-06-25)

Propagacao do polish V6 (commit V6 858b72d): 5 cards de metrica do Resumo
Executivo ganham quadrado de icone com tint suave de severidade, theme-aware.
Escala V3.3 (-tint/-solid). Deltas omitidos (sem D-1; regra de ouro).

Checks estruturais sobre a fonte (monolito), sem UI. <0.3s.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


class TestExecSummaryIcons(unittest.TestCase):
    def test_stat_helper_has_icon_signature(self):
        self.assertIn("const stat = (sv, ico, tint, body) =>", PORTAL)
        self.assertIn('class="rep-exec-ico rep-ico-${tint}"', PORTAL)

    def test_five_cards_have_icons(self):
        self.assertEqual(PORTAL.count("stat(null, 'fa-display', 'info',"), 1)
        self.assertIn("stat(null, 'fa-database', 'info',", PORTAL)
        self.assertIn("stat(null, 'fa-heart-pulse', 'ok',", PORTAL)
        self.assertIn("stat('CRITICAL', 'fa-triangle-exclamation', 'crit',", PORTAL)
        self.assertIn("stat('WARNING', 'fa-bell', 'warn',", PORTAL)


class TestThemeAwareV33Scale(unittest.TestCase):
    def test_icon_tints_use_v33_scale(self):
        # Tint dedicado mais saturado (color-mix 15% da cor), theme-aware, sem tocar tokens globais
        self.assertIn(".rep-ico-crit { background:color-mix(in srgb, var(--sev-critical-solid) 15%, transparent); color:var(--sev-critical-solid); }", PORTAL)
        self.assertIn(".rep-ico-ok { background:color-mix(in srgb, var(--sev-ok-solid) 15%, transparent); color:var(--sev-ok-solid); }", PORTAL)
        self.assertIn(".rep-ico-info { background:color-mix(in srgb, var(--sev-info-solid) 15%, transparent); color:var(--sev-info-solid); }", PORTAL)

    def test_stat_numbers_tokenized(self):
        self.assertIn(".rep-exec-stat b.ok { color:var(--sev-ok-solid); }", PORTAL)

    def test_attn_tokenized(self):
        self.assertIn(".rep-exec-attn a { color:var(--color-accent);", PORTAL)


class TestLayoutOrder(unittest.TestCase):
    """Resumo Executivo no TOPO + Disponibilidade ao lado, alinhados com Cat/Env abaixo."""

    def test_kpis_exec_with_availability_on_top(self):
        self.assertIn("let h = '<div class=\"kpiadv-2\">' + _repExecCard(d, F, clkH) + (RC.availability || '') + '</div>';", PORTAL)
        self.assertNotIn("['availability', 'performance'", PORTAL)  # Disponibilidade NAO na grelha-4

    def test_kpis_exec_before_cat(self):
        self.assertLess(PORTAL.index("_repExecCard(d, F, clkH)"), PORTAL.index("_repCatCard(d, F, clkH)"))

    def test_report_exec_on_top(self):
        i_exec = PORTAL.index("_repExecCard(data, _kpiRepFilter, repClk, true)")
        i_cat = PORTAL.index("_repCatCard(data, _kpiRepFilter, repClk, true)")
        self.assertLess(i_exec, i_cat)


class TestExecSizing(unittest.TestCase):
    """Infos maiores + grelha que preenche + Disponibilidade enquadrada (height:100%)."""

    def test_grid_fills(self):
        # 2026-08-31: mecanismo mudou (commit 71707ae) e a intencao "5 stats numa
        # linha" mantem-se por outro caminho: auto-fit minmax(148px) dimensionado
        # para a largura real do card (~890px @1920); abaixo disso a quebra
        # responsiva e' aceite (racional documentado no proprio CSS).
        self.assertIn(".rep-exec-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(148px, 1fr))", PORTAL)

    def test_responsive_container_queries(self):
        # Responsivo a largura DO CARD (container query); breakpoints 680 e 520
        self.assertIn(".rep-exec-card { display:flex; flex-direction:column; container-type:inline-size; }", PORTAL)
        self.assertIn("@container (max-width: 680px) { .rep-exec-grid {", PORTAL)
        self.assertIn("@container (max-width: 520px) { .rep-exec-grid {", PORTAL)

    def test_bigger_icon_and_number(self):
        # 52px/30px passaram a topo de clamp() (degrau por altura de ecra, 71707ae)
        self.assertIn(".rep-exec-ico { width:clamp(42px, 4.3vh, 52px); height:clamp(42px, 4.3vh, 52px);", PORTAL)
        self.assertIn(".rep-exec-stat b { font-size:clamp(23px, 2.5vh, 30px);", PORTAL)

    def test_link_beside_message(self):
        self.assertNotIn(".rep-exec-attn a { margin-left:auto;", PORTAL)

    def test_availability_fills_height(self):
        self.assertIn(".kpiadv-2 .kpiadv-card { height:100%; }", PORTAL)

    def test_availability_body_fills_and_scales(self):
        # Card Disponibilidade ao lado do exec: corpo preenche a altura + fontes maiores (sem espaco morto)
        self.assertIn(".kpiadv-2 .kpiadv-card .kpiadv-body { flex:1;", PORTAL)
        self.assertIn(".kpiadv-2 .kpiadv-card .kpiadv-big { font-size:46px; }", PORTAL)
        self.assertIn(".kpiadv-2 .kpiadv-card .kpiadv-foot .n { font-size:20px; }", PORTAL)


class TestReportNoSelfLink(unittest.TestCase):
    """Dentro do Relatorio Tecnico nao faz sentido um link para o proprio relatorio."""

    def test_exec_card_suppresses_link_in_report(self):
        self.assertIn("${inReport ? '' : `<a onclick=\"openKpiReport()\">", PORTAL)

    def test_report_call_passes_inreport(self):
        self.assertIn("_repExecCard(data, _kpiRepFilter, repClk, true)", PORTAL)


class TestReportLinkPersistsWhenClean(unittest.TestCase):
    """Port do fix V6 68b21de (achado QA lente-utilizador): o link 'Abrir relatorio
    tecnico' estava preso ao banner rep-exec-attn, que so existe quando totalCrit > 0.
    Em ambiente saudavel (sem criticos) o relatorio ficava sem ponto de entrada."""

    def test_clean_state_has_persistent_link(self):
        self.assertIn(
            "else if (!inReport) h += `<div class=\"rep-exec-link\"><a onclick=\"openKpiReport()\">",
            PORTAL,
        )

    def test_persistent_link_styled(self):
        self.assertIn(".rep-exec-link { margin-top:auto;", PORTAL)
        self.assertIn(".rep-exec-link a { color:var(--color-accent);", PORTAL)

    def test_link_still_in_attn_when_criticals(self):
        # Sem regressao: com criticos o link continua junto a mensagem de atencao
        self.assertIn(
            "${inReport ? '' : `<a onclick=\"openKpiReport()\">${T('open_report', 'Abrir relatório técnico')} &rarr;</a>`}</div>`;",
            PORTAL,
        )


class TestNoRegression(unittest.TestCase):
    def test_no_old_stat_calls(self):
        self.assertNotIn("stat(null, `<b>", PORTAL)

    def test_no_hardcoded_stat_colors(self):
        self.assertNotIn(".rep-exec-stat b.ok { color:#22c55e; }", PORTAL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
