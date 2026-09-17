# -*- coding: utf-8 -*-
"""Fecho da tarde de 17/09: SOLUCOES (+3) e CONTEXT (+5) -- collector em ciclo de quedas (WMI), propagacao V6 (7 commits),
ADR da reintegracao, ajuda das modais de backup, e o inventario do texto fora do i18n.

Uso (raiz do repo):
  py docs/context/FECHO_TARDE_2026-09-17_apply.py --check
  py docs/context/FECHO_TARDE_2026-09-17_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOL = ROOT / "docs/context/SOLUCOES.md"
CTX = ROOT / "docs/context/CONTEXT.md"
MARK = "WMI_FORA_DO_PROCESSO_2026-09-17_apply.py"

SOL_ROWS = (
    "| 2026-09-17 | Collector (WatcherDBCollector) reinicia sozinho varias vezes por dia: PID muda, Collector Health mostra falhas/STALE intermitentes; Event 7031 'terminated unexpectedly' 10x em 24 h, 15x em 14 dias; ninguem deu por ela porque o SCM levanta o servico em 30-120 s | Access violation 0xc0000005 em python314.dll (pythonservice.exe, Python 3.14.2, pywin32 311): o pywin32 derreferencia proxies COM de WMI que morrem a meio da enumeracao (host que deixa de responder) dentro de __WrapDispatch -- excepcao SEH, nao Python. collect_os_disk_perf em curso em 9/10 quedas (os_memory 7, os_cpu 6); 10 threads WMI por recolha. faulthandler ja armado mostrou 44/61 quedas em thread nativa; o mesmo ficheiro tinha 3.300 excepcoes COM logadas (183 MB) | Guardiao do recolhedor: GO-com-coordenacao, ordem B->C->A(subprocess); processpool do scheduler inviavel (metodo ligado nao picklavel). Lote: recolhas WMI num processo filho (python.exe -c ...run(Namespace)), 10->3 threads, rotacao do faulthandler.log; rollback WDB_WMI_IN_PROCESS=1 | WATCHERDB INTELLIGENCE V1/docs/context/WMI_FORA_DO_PROCESSO_2026-09-17_apply.py; faulthandler_crashes.py (scratch) | collector; crash; access violation; 0xc0000005; pywin32; WMI; COM; 7031; faulthandler; subprocess; processpool |\n"
    "| 2026-09-17 | Ajuda '?' das modais de backup (DIFF Backup Failed etc.) em portugues sem acentos com o portal em ingles | const BACKUP_KPI_INFO no template (Wave R+7, 25/05): 5 textos escritos a mao, consumidos directamente no title do icone | grupo kpi_info (pt AO90 acentuado, en, es; pt-BR overlay) e consumidor via _kpiT com o dicionario antigo como recurso | docs/context/KPI_INFO_I18N_2026-09-17_apply.py; 5c46b5d | i18n; kpi_info; BACKUP_KPI_INFO; ajuda; tooltip; portugues a mao |\n"
    "| 2026-09-17 | 'Tirando o que o V6 tem a mais, os dois sao iguais?' -- nao: V3.4 e V6 divergiram estruturalmente e a propagacao por prompt parou | Medido: 180 ficheiros comuns (69 iguais, 111 diferentes), 128 so no V3.4, 467 so no V6; ZERO commits git em comum (V6 = clone V5 19/04; V3.4 = snapshot V3.3 03/09); 12 prompts de 04-15/09 nunca aplicados; V6 sem remoto, main parado a 03/08, admin123 vivo em auth_service (fallback em memoria); pool do V6 Trusted-only; V6 escreve em ~20 tabelas fora do canonico do V1 | 7 lotes portados a mao para o V6 (f43080c..03e0771); ADR com advisor+challenger: nao e rebase; gate automatico de seguranca ja, inventario de ganchos antes de escolher entre nova linhagem e nucleo pequeno; paridade obrigatoria so em seguranca e schema | docs/context/ADR_V6_REINTEGRACAO_2026-09-17.md; PROMPT_PROPAGACAO_V6_LOTES_16-17SET_2026-09-17.md; V6 docs/context/V6_*_2026-09-17_apply.py | V6; propagacao; divergencia; rebase; ADR; gate; nucleo partilhado; admin123 fallback |\n"
)

CTX_LINES = (
    "- 2026-09-17 | orquestrador + guardiao V1 | COLLECTOR EM CICLO DE QUEDAS: 15 terminacoes inesperadas em 14 dias (10 em 24 h), access violation em python314.dll por WMI/COM (pywin32) com collect_os_disk_perf em curso em 9/10; SCM escondia-o. Lote WMI_FORA_DO_PROCESSO (V1) pronto e provado (7 testes + filho real em TST -- que GRAVOU 39 linhas na STG de TST: devia ter sido dry-run; registado). Aguarda apply+restart do owner; prova em servico = 7031 a zero nas 24 h seguintes.\n"
    "- 2026-09-17 | orquestrador | PROPAGACAO V6 feita a mao: 7 commits no V6 (Collector Health por ambiente, disco = uma linha nos 4 leitores, errorlog emparelhado, cartao Disk Latency em 6 locales, troca obrigatoria + reset AD-safe, sementes fora + bootstrap_admin, fallback admin123 removido). NAO portado: Regra de Ouro #2 A/B e CONFIG (pool do V6 e' Trusted-only, sem _resolve_credentials -- estrutural), 5 lotes i18n do Collector Health (template diferente). V6 continua SEM REMOTO; 131 ficheiros por commitar de outra sessao; avisos 42S22/42S02 no arranque sao pre-existentes (V6 espera KPI_MSSQL_CERTIFICATES_STG, KPI_MSSQL_INST_CONFIG_STG, WatcherDB_Alerts, colunas Database/Is_Auto_Shrink_On/Page_Life_Expectancy que a base partilhada nao tem).\n"
    "- 2026-09-17 | orquestrador + architecture-advisor + challenger | ADR_V6_REINTEGRACAO: a recomendacao 'rebase do V6 sobre o V3.4' estava ERRADA no mecanismo (0 commits comuns) e no pressuposto (so-V6 toca nos comuns: main 79 vs 29 routers, portal 40% reescrito). Decisao proposta: gate automatico de seguranca ja (trailer 'propagado do V3.4 <sha>' + lista security-critical), inventario de ganchos nos 180 comuns na semana 2 (<=25 isolaveis -> nova linhagem v6-next; senao nucleo pequeno auth+pool+secrets+licensing), paridade obrigatoria em seguranca e schema. Decisoes do owner pendentes: remoto do V6; dba_copilot_rule_based Std vs Pro (contradicao entre registries); qual e' o GA do V6 (main de 03/08 ainda tem sementes). Veto latente V1: ~20 tabelas escritas pelo V6 fora do canonico + dois sistemas de limiares.\n"
    "- 2026-09-17 | orquestrador | 5c46b5d: ajuda '?' das modais de backup em 4 idiomas. INVENTARIO do texto visivel fora do i18n no template V3.4: ~1.180 textos (265 HTML estatico de modais sem data-i18n; 118 KPI_DOCUMENTATION; ~75 regras/relatorios de diagnostico; ~70 diagnostico de queries; ~70 analises preditiva/TempDB/disco; ~580 toasts/estados vazios espalhados por ~200 funcoes) contra ~3.240 chaves ja no i18n. Plano proposto: lote 1 HTML estatico + teste de guarda que fixa o numero e so o deixa descer; depois KPI_DOCUMENTATION, regras, queries, analises. Aguarda GO.\n"
    "- 2026-09-17 | orquestrador | Pendentes do dia: apply do lote do collector (V1); prova em servico do SQL Auth (nenhum ecra da frota aberto); 'Instances OK: 58'; repositorio watcherdb-v34 continua publico; services/web_service (pacote legado V5.5 no V6) com admin123 em ~60 sitios de guias/.bat/.ps1 -- decisao de remocao; QUIET 'sem alvo' via heartbeat (V1).\n"
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
    print("[ok] SOLUCOES +3 (topo da tabela); CONTEXT +5 (fim)")
    if check:
        print("--check OK. Nada escrito."); return 0
    SOL.write_bytes(sol_novo.encode("utf-8")); CTX.write_bytes(ctx_novo.encode("utf-8"))
    print("[write] docs/context/SOLUCOES.md\n[write] docs/context/CONTEXT.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
