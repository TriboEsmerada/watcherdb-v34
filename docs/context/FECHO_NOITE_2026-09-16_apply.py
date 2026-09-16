# -*- coding: utf-8 -*-
"""Fecho da noite de 16/09: SOLUCOES (+3 sintomas) e CONTEXT (+4 decisoes) para os quatro lotes aplicados
(b9affc1 Log/errorlog, dac44db Collector Health por ambiente, 85de22b Regra de Ouro #2 lote B, V1 8a427ed audit V5).

Uso (raiz do repo):
  py docs/context/FECHO_NOITE_2026-09-16_apply.py --check
  py docs/context/FECHO_NOITE_2026-09-16_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOL = ROOT / "docs/context/SOLUCOES.md"
CTX = ROOT / "docs/context/CONTEXT.md"
MARK = "LOG_ERRORLOG_CONTEXTO_2026-09-16_apply.py"

SOL_ROWS = (
    "| 2026-09-16 | Aba Log mostra 'Error: 41145, Severity: 16, State: 1.' com Database N/A e pilula ERRO, sem dizer de que se trata; owner: 'so com essa info nao me diz nada' | O SQL Server escreve cada erro em DUAS linhas (cabecalho + mensagem) no mesmo spid; o endpoint /api/monitoring/sql-errors filtrava por palavras e a continuacao caia no NOT LIKE '%This is an informational message%' (ou nao tinha palavra da lista); o ecra classificava pelo numero 16 | #errorlog com Seq IDENTITY; CTE com LAG por ProcessInfo traz a linha a seguir a um cabecalho; api/errorlog_pairs.py emparelha, extrai database 'X' e poe INFO quando a mensagem e informativa; classifySqlLevel honra o INFO do servidor; filtro Nivel nasce em ERRO | docs/context/LOG_ERRORLOG_CONTEXTO_2026-09-16_apply.py; api/errorlog_pairs.py; b9affc1 | errorlog; xp_readerrorlog; 41145; informational; emparelhar; LAG; Seq; classifySqlLevel; filtro ERRO |\n"
    "| 2026-09-16 | Collector Health com 9 tarefas STALE (AlwaysOn, AG queues, AG queue sizes, Mirroring em PRD ha 158 d) quando os swaps PRD foram nesse dia com 0 falhas | KPI_STG_ACTIVE_TABLE tem uma linha por AMBIENTE para a mesma tabela; health_calculator indexava so por Table_Name e ficava com a ultima linha a chegar (TST/QA); WDB_COLLECTION_SCHEDULE_META tinha o mesmo defeito por Collector_Name | _indexar_por_ambiente e _linha_do_ambiente: SELECT le Environment, indice {tabela: {ENV: linha, _any: mais recente}}, _best_active_row escolhe o ambiente da tarefa; QA/TST sem alvos continuam antigos (QUIET 'sem alvo' fica proposto) | docs/context/COLL_HEALTH_AMBIENTE_2026-09-16_apply.py; dac44db | collector health; STALE; KPI_STG_ACTIVE_TABLE; Environment; Table_Name; _best_active_row; falso positivo |\n"
    "| 2026-09-16 | Audit de tarefas agendadas grava achados HIGH V5_NAO_CARREGADO para classes que estao a correr (CollectAGQueueSizes*, CollectTempDBUsage*, CollectFGUsageAll*, CollectIndexUsageTST) | Ha dois packages 'collectors' no monorepo V1 (servico e raiz legada); os modulos de recolha poem PROJECT_ROOT em sys.path[0] ao importar, e o check apagava sys.modules['collectors'] e fazia 'import collectors' -> apanhava o da raiz | _package_collectors_do_servico: usa o objecto que o registry carregou se o __file__ estiver em services/collector_service, senao repete o procedimento do registry e confirma pelo __file__; sem package certo avisa e nao emite achados | WATCHERDB INTELLIGENCE V1/docs/context/AUDIT_V5_PACKAGE_2026-09-16_apply.py; V1 8a427ed | audit; V5_NAO_CARREGADO; collectors; sys.path; PROJECT_ROOT; package raiz; falso positivo |\n"
)

CTX_LINES = (
    "- 2026-09-16 | orquestrador | ABA LOG (owner: 'quero que venha ja filtrado por erro e quero saber se tem mais linha desse erro'): o 41145 de SQLMDMPRD03\\I01 era o arranque do servico (16:29:56, unico desde 01/09) a rejuntar 27 bases ao AG SQLMDMPRDAG03 - informativo; a linha que vale despiste e o connection timeout para a replica SQLMDMPRD04\\I01 as 16:30:09; e a instancia esteve inalcancavel para o collector das 10:09 as 16:29 (08001, 81 ciclos) - e dai o 'Falhas 24h: 2' do collect_alwayson_PRD. Fix b9affc1: cabecalho+continuacao emparelhados (Seq/LAG + api/errorlog_pairs.py), base extraida, INFO quando informativa, filtro Nivel nasce em ERRO. Prova real: 208/208 cabecalhos emparelhados, 0 ERRO / 184 AVISO / 136 INFO nesse servidor.\n"
    "- 2026-09-16 | orquestrador | COLLECTOR HEALTH ('sera que tem algum problema com esses que estao stale?'): NAO em PRD - falso STALE por indexar KPI_STG_ACTIVE_TABLE so por Table_Name (linha do TST tapava a do PRD); fix dac44db indexa por (tabela, ambiente). QA/TST de AG/mirroring sao antigos por nao haver alvos nesses ambientes: proposta pendente de os classificar QUIET 'sem alvo' quando a mesma tabela esta fresca noutro ambiente (decisao de produto).\n"
    "- 2026-09-16 | orquestrador | REGRA DE OURO #2, lote B (85de22b): ConnectionInfo.get_connection_string consulta o pool central (_sql_auth_enabled_for + _resolve_credentials) quando use_windows_auth=True - os 5 sitios legados (LIVE/Overview/helpers/service_monitor) passam a sql_monitoring na allowlist e mantem Windows fora dela; fail-open. Default trace DESLIGADO por interruptor DEFAULT_TRACE_ENABLED=False (exige ALTER TRACE que sql_monitoring nao tem; rotulava 46/47 como Server Start/Stop). Prova real: caminho legado liga a SQLHDSPRD406\\I01 como sql_monitoring; errorlog de SQLMDMPRD03 lido por esse caminho. Falta a prova em servico (DMV com host_process_id do servico novo).\n"
    "- 2026-09-16 | orquestrador | V1 8a427ed: audit de tarefas, check V5 deixa de apanhar o package 'collectors' da raiz (ver SOLUCOES). Pendentes do dia: lote RESET_CONTA_AD (pronto, nao corrido), git push dos dois repos, config/_backup/servers.json.* apagados no V1, QUIET 'sem alvo' no Collector Health, revisao de grants do sql_monitoring no fecho do projecto (medir com Extended Events).\n"
)


def main(argv):
    check = "--check" in argv
    sol = SOL.read_bytes().decode("utf-8"); ctx = CTX.read_bytes().decode("utf-8")
    if MARK in sol:
        print("[ABORT] ja aplicado"); return 1
    eol = "\r\n" if "\r\n" in sol else "\n"
    sep = "|---|---|---|---|---|---|" + eol
    if sol.count(sep) != 1:
        raise SystemExit(f"[ABORT] SOLUCOES: separador da tabela esperado 1x, encontrado {sol.count(sep)}x")
    sol_novo = sol.replace(sep, sep + SOL_ROWS.replace("\n", eol))
    eol_c = "\r\n" if "\r\n" in ctx else "\n"
    ctx_novo = ctx + ("" if ctx.endswith(eol_c) else eol_c) + CTX_LINES.replace("\n", eol_c)
    print("[ok] SOLUCOES +3 linhas (no topo da tabela); CONTEXT +4 decisoes (no fim)")
    if check:
        print("--check OK. Nada escrito."); return 0
    SOL.write_bytes(sol_novo.encode("utf-8")); CTX.write_bytes(ctx_novo.encode("utf-8"))
    print("[write] docs/context/SOLUCOES.md\n[write] docs/context/CONTEXT.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
