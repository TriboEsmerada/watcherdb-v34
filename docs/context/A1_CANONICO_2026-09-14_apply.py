# -*- coding: utf-8 -*-
"""A1 -- alinha o script canonico do V1 com o que ficou aplicado na base viva a 14/09 (regra 2).

O que ja esta na WatcherDB_Intelligence (corrido pelo owner, ver A1_P1_P2_P3 e A1_P2B_CORRIGIDO):
  - coluna First_Event_Time na KPI_MSSQL_SERVER_OFFLINE_EVENTS
  - usp_MSSQL_Server_Offline_Upsert grava First_Event_Time so' no INSERT
  - as 3 vistas (AGG/DET/GROUPED) sem a janela de 15 min, com o Env por prefixo e o
    First_Event_Time verdadeiro em vez do alias de Event_Time

Este script poe o mesmo no canonico, para uma instalacao de raiz nascer igual a producao.

DESVIO REGISTADO, NAO CORRIGIDO AQUI: o canonico declara Service_Check_Attempted e
Service_Check_Method (migracao 008, FIND-20260505-005) que a base VIVA nao tem -- foi o que
fez o primeiro ALTER PROCEDURE falhar com 4 erros 207. O canonico fica como esta' (uma
instalacao de raiz cria as colunas e a proc funciona); o que falta e' aplicar a migracao 008
a base existente, ou removela do canonico. Decisao do owner, com o guardiao do recolhedor.

Uso (raiz do repo V3.4):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/A1_CANONICO_2026-09-14_apply.py --check
  py docs/context/A1_CANONICO_2026-09-14_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

CANON = Path(r"C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1"
             r"\database\INSTALACAO_COMPLETA_UNIFICADA.sql")
MARK = "migration 010 (A1, 2026-09-14)"  # o canonico ja tinha um alias mentiroso chamado First_Event_Time

JANELA = ("    WHERE Event_Time >= DATEADD(MINUTE, -15, GETDATE())\n"
          "      AND Is_Resolved = 0")
SEM_JANELA = ("    -- A1 2026-09-14: a janela de 15 min saiu. Um evento ABERTO deixa de desaparecer do\n"
              "    -- cartao so' porque o recolhedor saltou ciclos (episodio de 10/09: 6h30 em baixo com\n"
              "    -- Offline=0). A frescura passa a ser sinal, nao filtro. As 3 vistas mudam JUNTAS:\n"
              "    -- tinham a CTE copy-pasted e mudar so' uma faria cartao e modal discordarem.\n"
              "    WHERE Is_Resolved = 0")

COMENT_ENV = ("-- A1 2026-09-14: os eventos sao por HOST (SQLHDSPRD213) e o inventario e' por INSTANCIA\n"
              "-- (SQLHDSPRD213_I01), logo a igualdade exacta nunca casa e o Env saía 'Undefined'. Como o\n"
              "-- portal filtra por ambiente, um servidor em baixo podia desaparecer do cartao mesmo\n"
              "-- dentro da janela. OUTER APPLY com TOP 1 em vez de JOIN: aceita o prefixo sem\n"
              "-- multiplicar linhas quando o host tem varias instancias, e prefere o match exacto.\n")


def _env(alias: str) -> tuple[str, str, int]:
    velho = (f"LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)\n"
             f"    ON e.Instance = {alias}.Server_Name")
    novo = (COMENT_ENV +
            "OUTER APPLY (SELECT TOP 1 i.Env FROM dbo.KPI_MSSQL_INST_ENVS i WITH (NOLOCK)\n"
            f"             WHERE i.Instance = {alias}.Server_Name\n"
            f"                OR i.Instance LIKE {alias}.Server_Name + '[_]%'\n"
            f"             ORDER BY CASE WHEN i.Instance = {alias}.Server_Name THEN 0 ELSE 1 END,"
            " i.Instance) e")
    return velho, novo, 1


EDITS = [
    # 1) coluna nova na tabela
    ("        -- migration 009 (2026-07-27): auditoria de resolve (auto vs manual)\n"
     "        Resolved_By NVARCHAR(64) NULL             -- NULL = historico pre-auditoria\n",
     "        -- migration 009 (2026-07-27): auditoria de resolve (auto vs manual)\n"
     "        Resolved_By NVARCHAR(64) NULL,            -- NULL = historico pre-auditoria\n"
     "        -- migration 010 (A1, 2026-09-14): hora em que o evento ABRIU. Event_Time e'\n"
     "        -- reescrito pelo MERGE a cada ciclo (ultima confirmacao), logo sozinho nao\n"
     "        -- serve para o 'desde': um servidor em baixo ha 6h aparecia com 1 minuto.\n"
     "        First_Event_Time DATETIME2 NULL           -- NULL = evento anterior a migracao 010\n", 1),
    # 2) o MERGE grava a hora de inicio, so' no INSERT
    ("        INSERT (Server_Name, Diagnosis, Ping_OK, Ping_Message, Services_Down,\n"
     "                Service_Check_Attempted, Service_Check_Method, Event_Time, Is_Resolved)\n"
     "        VALUES (@Server_Name, @Diagnosis, @Ping_OK, @Ping_Message, @Services_Down,\n"
     "                @Service_Check_Attempted, @Service_Check_Method, GETDATE(), 0);\n",
     "        -- A1 2026-09-14: First_Event_Time e' gravado UMA vez, aqui, e nunca tocado no\n"
     "        -- UPDATE. Event_Time continua a ser a ultima confirmacao (o auto-resolve e a\n"
     "        -- frescura dependem disso).\n"
     "        INSERT (Server_Name, Diagnosis, Ping_OK, Ping_Message, Services_Down,\n"
     "                Service_Check_Attempted, Service_Check_Method, Event_Time,\n"
     "                First_Event_Time, Is_Resolved)\n"
     "        VALUES (@Server_Name, @Diagnosis, @Ping_OK, @Ping_Message, @Services_Down,\n"
     "                @Service_Check_Attempted, @Service_Check_Method, GETDATE(),\n"
     "                GETDATE(), 0);\n", 1),
    # 3) as 3 vistas perdem a janela
    (JANELA, SEM_JANELA, 3),
    # 4) Env por prefixo nas 2 vistas que fazem o cruzamento
    _env("soe"),
    _env("ls"),
    # 5) First_Event_Time verdadeiro na GROUPED
    ("        soe.Services_Down,\n        soe.Event_Time\n"
     "    FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS soe WITH (NOLOCK)",
     "        soe.Services_Down,\n        soe.Event_Time,\n        soe.First_Event_Time\n"
     "    FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS soe WITH (NOLOCK)", 1),
    ("    ls.Event_Time AS First_Event_Time,\n"
     "    ls.Event_Time AS Last_Event_Time,\n"
     "    DATEDIFF(MINUTE, ls.Event_Time, GETDATE()) AS Minutes_Since_First_Event,\n"
     "    DATEDIFF(MINUTE, ls.Event_Time, GETDATE()) AS Minutes_Since_Last_Event,",
     "    -- A1 2026-09-14: First_Event_Time deixa de ser um alias de Event_Time. COALESCE cobre\n"
     "    -- as linhas anteriores a migracao 010, sem backfill inventado. Last_Seen mantem a\n"
     "    -- semantica de 'ultima confirmacao'.\n"
     "    COALESCE(ls.First_Event_Time, ls.Event_Time) AS First_Event_Time,\n"
     "    ls.Event_Time AS Last_Event_Time,\n"
     "    ls.Event_Time AS Last_Seen_Time,\n"
     "    DATEDIFF(MINUTE, COALESCE(ls.First_Event_Time, ls.Event_Time), GETDATE())"
     " AS Minutes_Since_First_Event,\n"
     "    DATEDIFF(MINUTE, ls.Event_Time, GETDATE()) AS Minutes_Since_Last_Event,\n"
     "    DATEDIFF(MINUTE, ls.Event_Time, GETDATE()) AS Minutes_Since_Last_Seen,", 1),
]


def main(argv):
    check = "--check" in argv
    if not CANON.exists():
        print(f"[ABORT] canonico nao encontrado: {CANON}"); return 1
    raw = CANON.read_bytes().decode("utf-8", errors="replace")
    eol = "\r\n" if "\r\n" in raw else "\n"
    if MARK in raw:
        print("[ABORT] ja aplicado (o canonico ja fala de First_Event_Time)"); return 1
    texto = raw
    for old, new, count in EDITS:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = texto.count(o)
        if got != count:
            print(f"[ABORT] anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:90]!r}")
            return 1
        texto = texto.replace(o, n)
    print(f"[ok] anchors: coluna 1x; MERGE 1x; janela 3x; Env 2x; First_Event_Time 2x")
    if check:
        print("--check OK. Nada escrito."); return 0
    CANON.write_bytes(texto.encode("utf-8"))
    print(f"[write] {CANON}")
    print("\nAplicado ao canonico. Commita no repo do V1 (WATCHERDB INTELLIGENCE V1).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
