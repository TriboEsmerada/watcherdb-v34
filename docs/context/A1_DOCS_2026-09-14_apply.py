# -*- coding: utf-8 -*-
"""A1 -- documentacao nos dois repositorios (regra 2: mudanca na BD -> canonico + documentacoes).

O canonico ja foi alinhado (A1_CANONICO_2026-09-14_apply.py). Este script trata do resto:

  V1 (WATCHERDB INTELLIGENCE V1)
    database/migrations/010_offline_events_first_event_time.sql   NOVO: migracao para bases existentes
    database/migrations/008b_offline_upsert_proc_service_check.sql  aviso de ordem no topo
    docs/CHANGELOG.md                                               entrada 2.29.0
    docs/DIAGRAMA_RELACIONAMENTO_BANCO.md                           colunas e semantica da GROUPED_VIEW
    docs/FIX_SERVER_OFFLINE_VIEWS_20260422.md                       nota de "substituido por" no topo

  V3.4
    docs/architecture/DIAGRAMA_RELACIONAMENTO_BANCO.md              mesma edicao que no V1
    docs/architecture/QUERIES_POR_KPI.md                            query da modal com as colunas novas
    docs/guides/WATCHERDB_PERGUNTAS_RESPOSTAS.md                    resposta ao utilizador estava errada
    api/routers/intelligence_kpis.py                                comentario dizia "ultimos 7 dias"
    docs/changelog/CHANGELOG.md                                     entrada

A ARMADILHA QUE ISTO DOCUMENTA: a migracao 008b faz CREATE PROCEDURE com o corpo inteiro e sem
First_Event_Time. Correr a 008b depois da 010 apaga a hora de inicio em silencio. A 010 foi
escrita para funcionar com e sem a 008 aplicada; a 008b ganha um aviso a dizer a ordem.

Uso:
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/A1_DOCS_2026-09-14_apply.py --check
  py docs/context/A1_DOCS_2026-09-14_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

V34 = Path(r"C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4")
V1 = Path(r"C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1")
MIG_ORIGEM = V34 / "docs" / "context" / "010_offline_events_first_event_time.sql"
MIG_DESTINO = V1 / "database" / "migrations" / "010_offline_events_first_event_time.sql"
MARK = "migration 010 (A1"

DIAGRAMA_VELHO = ("- First_Event_Time, Last_Event_Time\n"
                  "- Minutes_Since_First_Event, Minutes_Since_Last_Event\n")
DIAGRAMA_NOVO = ("- First_Event_Time: hora em que o evento ABRIU (coluna propria desde a migration 010 (A1,\n"
                 "  2026-09-14); antes era um alias de Event_Time e mentia. COALESCE com Event_Time para\n"
                 "  eventos anteriores a migracao)\n"
                 "- Last_Event_Time, Last_Seen_Time: ultima confirmacao do recolhedor (Event_Time, reescrito\n"
                 "  pelo MERGE a cada ciclo)\n"
                 "- Minutes_Since_First_Event: ha quanto tempo o servidor esta em baixo\n"
                 "- Minutes_Since_Last_Event, Minutes_Since_Last_Seen: ha quanto tempo nao ha confirmacao.\n"
                 "  E' o sinal de frescura: um valor alto quer dizer que o recolhedor deixou de ver o\n"
                 "  servidor, NAO que o problema passou\n"
                 "\n"
                 "**Filtro (desde a migration 010):** as tres vistas contam eventos com `Is_Resolved = 0`,\n"
                 "sem janela de tempo. Ate 2026-09-14 so contavam eventos confirmados nos ultimos 15 min, e\n"
                 "quando o recolhedor saltava ciclos um servidor em baixo desaparecia do cartao (10/09:\n"
                 "SQLHDSPRD407 em baixo 6h30 com \"Offline 0\"). As tres mudam sempre juntas: tinham a mesma\n"
                 "CTE copiada, e mudar so uma faz o cartao e a modal discordarem.\n"
                 "\n"
                 "**Ambiente:** os eventos sao por HOST e o inventario por INSTANCIA, portanto o Env e\n"
                 "resolvido por prefixo (`OUTER APPLY ... TOP 1`), preferindo o match exacto. Com igualdade\n"
                 "simples o Env saia `Undefined` e o filtro de ambiente do portal escondia o servidor.\n")

EDITS = [
    # ---------------------------------------------------------------- V1
    (V1 / "database" / "migrations" / "008b_offline_upsert_proc_service_check.sql",
     "-- ============================================================================\n"
     "-- MIGRACAO 008b: usp_MSSQL_Server_Offline_Upsert escreve Service_Check_*\n"
     "-- ============================================================================\n",
     "-- ============================================================================\n"
     "-- MIGRACAO 008b: usp_MSSQL_Server_Offline_Upsert escreve Service_Check_*\n"
     "-- ============================================================================\n"
     "-- !! AVISO DE ORDEM (2026-09-14, migration 010 (A1)):\n"
     "-- !! Esta migracao faz CREATE PROCEDURE com o corpo inteiro e SEM First_Event_Time.\n"
     "-- !! Se a correres DEPOIS da 010, a procedure deixa de gravar a hora de inicio e o\n"
     "-- !! \"desde\" da modal de offline volta a mentir, sem erro nenhum. Ordem certa:\n"
     "-- !! 008 -> 008b -> 010. Se ja correste a 010, volta a correr a 010 a seguir a esta.\n"
     "-- !! (A base viva de 14/09 NAO tem a 008 aplicada; o canonico tem.)\n"
     "-- ============================================================================\n", 1),
    (V1 / "docs" / "CHANGELOG.md",
     "---\n## [2.28.0] - 2026-08-19\n",
     "---\n## [2.29.0] - 2026-09-14\n"
     "\n"
     "### Corrigido — migration 010 (A1): o cartao de Disponibilidade deixa de dizer \"Offline 0\"\n"
     "\n"
     "- **As vistas `KPI_MSSQL_SERVER_OFFLINE_{AGG,DET,GROUPED}_VIEW` perdem a janela de 15 min.** So\n"
     "  contavam eventos confirmados nos ultimos 15 minutos; como o MERGE reescreve `Event_Time` a cada\n"
     "  ciclo, quando o recolhedor saltava ciclos um servidor em baixo saia da vista. Medido a 10/09:\n"
     "  SQLHDSPRD407 em baixo 6h30 com o cartao a dizer Offline 0. As tres mudam juntas.\n"
     "- **`First_Event_Time` passa a ser uma coluna verdadeira.** Era um alias de `Event_Time` na\n"
     "  GROUPED_VIEW, logo o \"desde\" mostrava a ultima confirmacao. A procedure grava-a so no INSERT.\n"
     "  Colunas novas na vista: `Last_Seen_Time` e `Minutes_Since_Last_Seen`, como sinal de frescura.\n"
     "- **Ambiente por prefixo.** Eventos por host cruzados por igualdade com o inventario por instancia\n"
     "  davam `Env = Undefined`, e o filtro de ambiente do portal escondia o servidor.\n"
     "- **5 eventos orfaos fechados** (servidores fora do inventario, de Maio e Julho), com\n"
     "  `Resolved_By = 'auto-orphan-cleanup'`. Pre-condicao: sem isto, retirar a janela punha servidores\n"
     "  desactivados a contar como offline.\n"
     "- Gate: watcherdb-v1-intel-specialist, GO nas 4 pecas, zero vetos. Provado com evento sintetico\n"
     "  `ZZZ_TEST_OFFLINE_SIM`: 1 linha visivel apos 20 min sem confirmacao, hora de inicio preservada.\n"
     "\n"
     "### Registado, nao corrigido\n"
     "\n"
     "- **Desvio canonico vs base viva:** o canonico declara `Service_Check_Attempted` e\n"
     "  `Service_Check_Method` (migration 008) que a base viva nunca recebeu. Aplicar 008+008b e correr\n"
     "  a 010 a seguir, ou retirar a 008 do canonico: decisao pendente.\n"
     "- **Pendente para lote proprio:** auto-resolve continuo de orfaos no recolhedor (P1b) e\n"
     "  `Is_Available=0` derivado de `SERVER_OFFLINE_EVENTS`, nunca de um timeout de ligacao cru (P4).\n"
     "\n"
     "---\n## [2.28.0] - 2026-08-19\n", 1),
    (V1 / "docs" / "DIAGRAMA_RELACIONAMENTO_BANCO.md", DIAGRAMA_VELHO, DIAGRAMA_NOVO, 1),
    (V1 / "docs" / "FIX_SERVER_OFFLINE_VIEWS_20260422.md",
     "# FIX: SQL Services Down — instâncias fantasma (2026-04-22)\n",
     "# FIX: SQL Services Down — instâncias fantasma (2026-04-22)\n"
     "\n"
     "> **Actualização 2026-09-14 — migration 010 (A1).** A janela de 15 min descrita neste documento\n"
     "> foi retirada das tres vistas: escondia servidores em baixo quando o recolhedor saltava ciclos.\n"
     "> A reconciliacao com `INST_AVAILABILITY` (excluir quem foi recolhido nos ultimos 10 min) mantem-se.\n"
     "> Ver `docs/CHANGELOG.md` [2.29.0] e `database/migrations/010_offline_events_first_event_time.sql`.\n"
     "> Este documento fica como registo historico do fix de Abril.\n", 1),
    # ---------------------------------------------------------------- V3.4
    (V34 / "docs" / "architecture" / "DIAGRAMA_RELACIONAMENTO_BANCO.md", DIAGRAMA_VELHO, DIAGRAMA_NOVO, 1),
    (V34 / "docs" / "architecture" / "QUERIES_POR_KPI.md",
     "    First_Event_Time, \n    Last_Event_Time, \n"
     "    Minutes_Since_First_Event, \n    Minutes_Since_Last_Event, \n",
     "    First_Event_Time,          -- hora em que abriu (coluna propria desde a migration 010 (A1))\n"
     "    Last_Event_Time, \n"
     "    Last_Seen_Time,            -- ultima confirmacao do recolhedor\n"
     "    Minutes_Since_First_Event, -- ha quanto tempo esta em baixo\n"
     "    Minutes_Since_Last_Event, \n"
     "    Minutes_Since_Last_Seen,   -- frescura: alto = o recolhedor deixou de o ver\n", 1),
    (V34 / "docs" / "guides" / "WATCHERDB_PERGUNTAS_RESPOSTAS.md",
     "- Dados: Instancias que nao respondem a ping nos ultimos 15 minutos\n",
     "- Dados: Instancias com evento de offline aberto (ping ou SQL sem resposta), ate o recolhedor\n"
     "  confirmar que voltaram. Nao ha janela de tempo: um servidor em baixo continua a contar mesmo\n"
     "  que o recolhedor salte ciclos. A modal mostra ha quanto tempo esta em baixo e ha quanto tempo\n"
     "  nao ha confirmacao; este segundo valor alto indica que o recolhedor deixou de o ver\n", 1),
    (V34 / "api" / "routers" / "intelligence_kpis.py",
     "# Instances Off - servidores com PING FALHOU e evento nao resolvido (GROUPED_VIEW ja filtra Is_Resolved=0 e ultimos 7 dias)",
     "# Instances Off - servidores com PING FALHOU e evento nao resolvido. A GROUPED_VIEW filtra so Is_Resolved=0,\n"
     "            # SEM janela de tempo desde a migration 010 (A1, 2026-09-14). O comentario anterior dizia\n"
     "            # \"ultimos 7 dias\", mas o filtro real era de 15 min -- e escondia servidores em baixo.", 1),
    (V34 / "docs" / "changelog" / "CHANGELOG.md",
     "## [Unreleased]\n\n### Changed\n\n",
     "## [Unreleased]\n\n### Changed\n\n"
     "- **Disponibilidade: o cartão deixa de dizer \"Offline 0\" com servidores em baixo** (A1, migration 010 do\n"
     "  V1). As três vistas de eventos de offline só contavam eventos confirmados nos últimos 15 minutos, e\n"
     "  quando o recolhedor saltava ciclos um servidor em baixo desaparecia (10/09: 6h30 com Offline 0). A hora\n"
     "  de início passa a ser verdadeira em vez de repetir a última confirmação, o ambiente resolve por prefixo\n"
     "  (os eventos são por host e o inventário por instância, e o filtro de ambiente escondia o servidor), e\n"
     "  cinco eventos órfãos de servidores desactivados foram fechados. Provado com um evento sintético. A\n"
     "  resposta ao utilizador no guia de perguntas, que falava de \"últimos 15 minutos\", foi corrigida. [tier: Std]\n"
     "\n", 1),
]


def main(argv):
    check = "--check" in argv
    if not MIG_ORIGEM.exists():
        print(f"[ABORT] falta a migracao gerada: {MIG_ORIGEM}"); return 1
    if MIG_DESTINO.exists():
        print(f"[ABORT] ja aplicado: {MIG_DESTINO} existe"); return 1
    saidas = {}
    for caminho, old, new, count in EDITS:
        if not caminho.exists():
            print(f"[ABORT] nao existe: {caminho}"); return 1
        raw = saidas.get(caminho) or caminho.read_bytes().decode("utf-8", errors="replace")
        if MARK in raw and caminho not in saidas:
            print(f"[ABORT] ja aplicado em {caminho.name}"); return 1
        eol = "\r\n" if "\r\n" in raw else "\n"
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = raw.count(o)
        if got != count:
            print(f"[ABORT] {caminho.name}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:80]!r}")
            return 1
        saidas[caminho] = raw.replace(o, n)
    print(f"[ok] anchors: {len(EDITS)} edicoes em {len(saidas)} ficheiros; migracao 010 pronta a copiar")
    if check:
        print("--check OK. Nada escrito."); return 0
    MIG_DESTINO.write_bytes(MIG_ORIGEM.read_bytes()); print(f"[new]   {MIG_DESTINO}")
    for caminho, texto in saidas.items():
        caminho.write_bytes(texto.encode("utf-8")); print(f"[write] {caminho}")
    print("\nAplicado. Commit em DOIS repositorios: V1 (migracao, 008b, CHANGELOG, diagrama, FIX doc) e V3.4.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
