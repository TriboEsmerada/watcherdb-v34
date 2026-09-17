# -*- coding: utf-8 -*-
"""Fecho de 17/09 (manha): SOLUCOES (+2) e CONTEXT (+4) para os lotes de Disk Latency, o cartao em 4 idiomas, o reset
de conta AD e os pushes.

Uso (raiz do repo):
  py docs/context/FECHO_2026-09-17_apply.py --check
  py docs/context/FECHO_2026-09-17_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOL = ROOT / "docs/context/SOLUCOES.md"
CTX = ROOT / "docs/context/CONTEXT.md"
MARK = "DISK_POR_DISCO_TODOS_2026-09-17_apply.py"

SOL_ROWS = (
    "| 2026-09-17 | Modal 'Disk Latency Critical' mostra o mesmo host/disco duas vezes com valores iguais (SQLHDSQLT301 c:) e o KPI conta 2; corrigido o dashboard, a modal continuou a repetir | O recolhedor de disco (WMI) corre por INSTANCIA e grava Instance: hosts com 2-4 instancias tem 2-4 linhas iguais por disco em KPI_OS_DISK_PERF_STG (519 linhas para 468 discos). O portal tinha QUATRO leitores da tabela com a sua propria consulta (dashboard, modal /instances/{kpi_type}, get_disk_by_drive, get_disk_latency_summary) | helpers._uma_linha_por_disco (linha mais recente por (Hostname, Drive), Instances anotadas) aplicada no dashboard e na modal e em get_disk_by_drive; summary agrega sobre ROW_NUMBER por (Hostname, Drive); teste varre os tres ficheiros e falha se aparecer leitor sem a regra | docs/context/DISK_LATENCY_POR_DISCO_2026-09-16_apply.py; DISK_POR_DISCO_TODOS_2026-09-17_apply.py; 40bb4c1; b566aef | disk latency; KPI_OS_DISK_PERF_STG; duplicado; instancia; host; _uma_linha_por_disco; copia da consulta; modal |\n"
    "| 2026-09-17 | Cartao da modal de Disk Latency em portugues com o portal em ingles; dica 'Disco muito ocupado' mostrava o codigo ${diskTimePct...} em vez do numero | Texto escrito a mao no template (17 textos); o ${} estava dentro de uma string de aspas simples, que nao interpola; test_i18n_parity ja falhava por 3 chaves do grupo live (activo/Active e um override pt-BR redundante) | grupo dlat (21 chaves pt/en/es, 6 no overlay pt-BR); dicas por concatenacao com t(); live.help_region/sched_tip_workers corrigidos e live.help_fleet_what removido do pt-BR | docs/context/DLAT_I18N_2026-09-17_apply.py; 999a222 | i18n; dlat; disk latency; aspas simples; interpolacao; test_i18n_parity; AO90 |\n"
)

CTX_LINES = (
    "- 2026-09-17 | orquestrador | DISK LATENCY ('pq aparece duplicado?' / 'mesmo host e valores iguais'): o recolhedor grava uma linha por instancia e o portal tinha 4 leitores da tabela, cada um com a sua consulta. 40bb4c1 (dashboard) + b566aef (modal, disk_by_drive, summary): um disco = uma linha, com teste que varre os 3 ficheiros. Licao repetida de 11/09: quando um criterio vive em mais de um sitio, corrigir um nao chega -- procurar todos os leitores da tabela antes de entregar.\n"
    "- 2026-09-17 | orquestrador | 999a222: cartao de Disk Latency em 4 idiomas (grupo dlat) + ${pct} que nunca interpolava + 3 chaves live que faziam falhar test_i18n_parity desde 15/09. c9049c4: lote RESET_CONTA_AD aplicado (reset por admin ja nao converte conta AD em local). Pushes feitos: V3.4 main = origin (c9049c4), V1 wave-b = origin (4c01d2e, arvore limpa; servers.json churn de is_accessible descartado -- inventario vivo num ficheiro versionado fica como divida). O remoto watcherdb-v34 CONTINUA PUBLICO (API 200): nomes internos ja la estavam antes destes pushes; tornar privado e' decisao do owner.\n"
    "- 2026-09-17 | orquestrador | QUIET 'sem alvo' no Collector Health: NAO feito por falta de evidencia acessivel -- a prova (Servidores selecionados: 0 de 63 (TST); [STORE START] Env=QA, Rows=0) so' existe nos logs por familia do V1, nao no collectors.log que o quadro le nem na BD. Proposta: o recolhedor escrever Last_Success_TS em WDB_COLLECTION_SCHEDULE_META tambem com 0 linhas (semantica HEARTBEAT ja existe) e o quadro classificar 'corre, sem alvos'. Lote V1 com veto do guardiao, quando o owner abrir a frente.\n"
    "- 2026-09-17 | orquestrador | Pendentes: prova em servico do SQL Auth (DMV com host_process_id do portal; nenhum ecra da frota foi aberto desde os restarts); 'Instances OK: 58' no arranque (63 ontem) com 0 offline por ping -- ver que 5 sairam do OK e porque; recolha de disco 4x por host no V1 (optimizacao); revisao de grants do sql_monitoring no fecho do projecto.\n"
)


def main(argv):
    check = "--check" in argv
    sol = SOL.read_bytes().decode("utf-8"); ctx = CTX.read_bytes().decode("utf-8")
    if MARK in sol:
        print("[ABORT] ja aplicado"); return 1
    eol = "\r\n" if "\r\n" in sol else "\n"
    sep = "|---|---|---|---|---|---|" + eol
    if sol.count(sep) != 1:
        raise SystemExit(f"[ABORT] SOLUCOES: separador esperado 1x, encontrado {sol.count(sep)}x")
    sol_novo = sol.replace(sep, sep + SOL_ROWS.replace("\n", eol))
    eol_c = "\r\n" if "\r\n" in ctx else "\n"
    ctx_novo = ctx + ("" if ctx.endswith(eol_c) else eol_c) + CTX_LINES.replace("\n", eol_c)
    print("[ok] SOLUCOES +2 (topo da tabela); CONTEXT +4 (fim)")
    if check:
        print("--check OK. Nada escrito."); return 0
    SOL.write_bytes(sol_novo.encode("utf-8")); CTX.write_bytes(ctx_novo.encode("utf-8"))
    print("[write] docs/context/SOLUCOES.md\n[write] docs/context/CONTEXT.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
