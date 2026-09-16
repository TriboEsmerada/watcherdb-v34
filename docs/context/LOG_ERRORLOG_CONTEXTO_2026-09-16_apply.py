# -*- coding: utf-8 -*-
"""Aba Log, seccao "SQL Server Logs": cada erro traz a sua mensagem, e a tabela abre filtrada por erros (2026-09-16).

PEDIDO DO OWNER (captura de SQLMDMPRD03\\I01): "quero que venha ja filtrado por erro e quero saber se tem mais
linha desse erro, que ajude a despistar o problema, pois so' com essa info nao me diz nada".

CAUSA (medida no proprio servidor com xp_readerrorlog): o SQL Server escreve cada erro em DUAS linhas com o mesmo
carimbo e o mesmo spid -- primeiro "Error: 41145, Severity: 16, State: 1." e logo a seguir a mensagem
("Cannot join database 'cmx_ors' to availability group 'SQLMDMPRDAG03'. The database has already joined ...
This is an informational message."). O endpoint /api/monitoring/sql-errors le o errorlog inteiro para uma tabela
temporaria e depois filtra por palavras: o cabecalho passa (tem "Error:"), a continuacao e' EXCLUIDA pela regra
`NOT LIKE '%This is an informational message%'` -- ou quando nao tem nenhuma palavra da lista. O cabecalho fica
orfao no ecra, com "Database N/A" e a pilula ERRO, e ninguem percebe do que se trata.

O QUE MUDA:
 1. api/errorlog_pairs.py (novo, puro): emparelha cada cabecalho com a linha de continuacao que se lhe segue no
    mesmo spid; a mensagem passa a ser "cabecalho — continuacao"; a base de dados sai da continuacao
    (database 'X'); o nivel vem da severidade do cabecalho, MAS se a continuacao disser que e' informativa
    ("informational message") o nivel e' INFO -- o 41145 do arranque do servico deixa de ser um ERRO vermelho.
 2. watcherdb_main.py (/api/monitoring/sql-errors): a tabela temporaria ganha um numero de sequencia (a ordem de
    leitura e' o unico elo entre as duas linhas); a consulta traz tambem as linhas cuja linha anterior, no mesmo
    spid, e' um cabecalho (LAG), e deixa de excluir as informativas no SQL -- essa decisao passa a ser tomada
    depois de emparelhar, em Python. O mapeamento das linhas passa a ser feito pelo modulo novo.
 3. templates/watcherdb_portal.html: o classificador de nivel honra o INFO do servidor (antes olhava so' ao numero
    16 do cabecalho e pintava o par informativo de vermelho); e o filtro da coluna Nivel da tabela SQL nasce com "ERRO" (e' o que o owner
    escreveu a` mao na captura); o utilizador pode apaga-lo, e o valor persiste na sessao como ja acontecia.

FACTOS DO EPISODIO (para o owner): o SQL Server de SQLMDMPRD03\\I01 REINICIOU a 16/09 as 16:29:56 (unico arranque
desde 01/09); os 27 cabecalhos 41145 sao das 16:30:09-16:30:10, o arranque a rejuntar as bases ao grupo
SQLMDMPRDAG03; a linha que interessa nesse minuto e' outra: "A connection timeout has occurred while attempting to
establish a connection to availability replica 'SQLMDMPRD04\\I01'".

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/LOG_ERRORLOG_CONTEXTO_2026-09-16_apply.py --check
  py docs/context/LOG_ERRORLOG_CONTEXTO_2026-09-16_apply.py
  py -m pytest tests/unit/test_errorlog_pairs_20260916.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "main": Path("watcherdb_main.py"),
    "portal": Path("templates/watcherdb_portal.html"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "mod": Path("api/errorlog_pairs.py"),
    "test": Path("tests/unit/test_errorlog_pairs_20260916.py"),
}
MARK = "emparelhar_errorlog"

MOD_SRC = r'''# -*- coding: utf-8 -*-
"""Emparelha as linhas do errorlog do SQL Server que pertencem ao mesmo erro (2026-09-16).

O SQL Server escreve um erro em duas linhas consecutivas, com o mesmo carimbo e o mesmo spid:
    Error: 41145, Severity: 16, State: 1.
    Cannot join database 'cmx_ors' to availability group 'SQLMDMPRDAG03'. ... This is an informational message.
Lidas em separado, a primeira nao diz nada e a segunda perde-se nos filtros. Aqui juntam-se.

Regras:
 - Um cabecalho ("Error: N, Severity: S, State: T.") adopta a linha seguinte do MESMO spid, se ela nao for tambem
   um cabecalho. A mensagem passa a "cabecalho — continuacao".
 - A base de dados sai da continuacao, quando la' esta' (database 'X').
 - O nivel vem da severidade do cabecalho (>=17 ERROR, >=11 WARNING); mas se a continuacao disser que e' uma
   mensagem informativa, o nivel e' INFO -- e' o SQL Server a dizer que nao ha' nada a fazer.
 - Linhas soltas informativas (sem cabecalho) sao descartadas, como o endpoint ja fazia no SQL.
 - As linhas chegam por ordem de leitura (Seq crescente) e saem por data decrescente, como o ecra espera.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

CABECALHO = re.compile(r"^\s*Error:\s*(\d+),\s*Severity:\s*(\d+),\s*State:\s*(\d+)\.?\s*$")
BASE_DE_DADOS = re.compile(r"database '([^']+)'", re.IGNORECASE)
INFORMATIVA = re.compile(r"informational message", re.IGNORECASE)


def _nivel(severidade: Optional[int], texto: str, informativa: bool) -> str:
    if informativa:
        return "INFO"
    if severidade is not None and severidade >= 17:
        return "ERROR"
    if severidade is not None and severidade >= 11:
        return "WARNING"
    t = texto.lower()
    if "fail" in t or "error" in t:
        return "WARNING"
    return "INFO"


def _linha(log_date, process_info, texto: str, numero: Optional[int], severidade: Optional[int],
           nivel: str, base: Optional[str], contexto: Optional[str]) -> Dict[str, Any]:
    data = str(log_date) if log_date else ""
    return {
        "error_date": data, "errorDate": data, "log_date": data,
        "error_severity": severidade or nivel,
        "severity": nivel,
        "error_number": numero, "errorNumber": numero,
        "error_message": texto, "message": texto, "text": texto,
        "context": contexto,
        "process_info": process_info,
        "database_name": base, "databaseName": base,
        "source": "xp_readerrorlog",
    }


def emparelhar_errorlog(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """rows: dicts com LogDate, ProcessInfo, Text (ordem de leitura). Devolve as linhas do ecra, data decrescente."""
    rows = list(rows)
    saida: List[Dict[str, Any]] = []
    i = 0
    while i < len(rows):
        r = rows[i]
        texto = str(r.get("Text") or "")
        spid = r.get("ProcessInfo")
        m = CABECALHO.match(texto)
        if m:
            numero, severidade = int(m.group(1)), int(m.group(2))
            contexto = None
            if i + 1 < len(rows):
                prox = rows[i + 1]
                prox_txt = str(prox.get("Text") or "")
                if prox.get("ProcessInfo") == spid and not CABECALHO.match(prox_txt):
                    contexto = prox_txt.strip()
                    i += 1  # a continuacao foi consumida
            informativa = bool(contexto and INFORMATIVA.search(contexto))
            base = None
            if contexto:
                mb = BASE_DE_DADOS.search(contexto)
                base = mb.group(1) if mb else None
            mensagem = f"{texto.strip()} — {contexto}" if contexto else texto.strip()
            saida.append(_linha(r.get("LogDate"), spid, mensagem, numero, severidade,
                                _nivel(severidade, mensagem, informativa), base, contexto))
        else:
            # linha solta: mantem a decisao antiga de nao mostrar informativas
            if INFORMATIVA.search(texto):
                i += 1
                continue
            sev_m = re.search(r"Severity:\s*(\d+)", texto)
            severidade = int(sev_m.group(1)) if sev_m else None
            err_m = re.search(r"Error:\s*(\d+)", texto)
            numero = int(err_m.group(1)) if err_m else None
            mb = BASE_DE_DADOS.search(texto)
            saida.append(_linha(r.get("LogDate"), spid, texto, numero, severidade,
                                _nivel(severidade, texto, False), mb.group(1) if mb else None, None))
        i += 1
    saida.sort(key=lambda x: x["log_date"], reverse=True)
    return saida
'''

MAIN_EDITS = [
    # sequencia de leitura: e' o unico elo entre o cabecalho e a continuacao
    ("""        CREATE TABLE #errorlog (
            LogDate DATETIME,
            ProcessInfo NVARCHAR(100),
            Text NVARCHAR(MAX)
        );
""",
     """        CREATE TABLE #errorlog (
            Seq INT IDENTITY(1,1),      -- 2026-09-16: ordem de leitura; liga o cabecalho "Error: N" a` linha seguinte
            LogDate DATETIME,
            ProcessInfo NVARCHAR(100),
            Text NVARCHAR(MAX)
        );
""", 1),
    ("""            INSERT INTO #errorlog EXEC xp_readerrorlog 0, 1, NULL, NULL, @start;
""",
     """            INSERT INTO #errorlog (LogDate, ProcessInfo, Text) EXEC xp_readerrorlog 0, 1, NULL, NULL, @start;
""", 1),
    ("""                INSERT INTO #errorlog EXEC sp_readerrorlog 0, 1, NULL, NULL, @start;
""",
     """                INSERT INTO #errorlog (LogDate, ProcessInfo, Text) EXEC sp_readerrorlog 0, 1, NULL, NULL, @start;
""", 1),
    # a consulta traz tambem a linha que se segue a um cabecalho (LAG) e deixa a decisao "informativa" para depois
    ("""        SELECT
            LogDate,
            ProcessInfo,
            Text
        FROM #errorlog
        WHERE Text NOT LIKE '%Login succeeded%'
            AND Text NOT LIKE '%found 0 errors%'
            AND Text NOT LIKE '%CHECKDB%0 errors%'
            AND Text NOT LIKE '%This is an informational message%'
            AND Text NOT LIKE '%Setting database option%'
""",
     """        -- 2026-09-16: cada erro sao DUAS linhas (cabecalho "Error: N, Severity, State" + mensagem) no mesmo spid.
        -- A linha anterior e' cabecalho? Entao esta e' a continuacao e vem sempre, mesmo sem palavra da lista.
        -- A exclusao das informativas saiu daqui: e' decidida depois de emparelhar (api/errorlog_pairs.py).
        ;WITH L AS (
            SELECT Seq, LogDate, ProcessInfo, Text,
                   CASE WHEN LAG(Text) OVER (PARTITION BY ProcessInfo ORDER BY Seq)
                             LIKE 'Error: %, Severity: %, State: %' THEN 1 ELSE 0 END AS PrevIsHeader
            FROM #errorlog
        )
        SELECT
            LogDate,
            ProcessInfo,
            Text
        FROM L
        WHERE Text NOT LIKE '%Login succeeded%'
            AND Text NOT LIKE '%found 0 errors%'
            AND Text NOT LIKE '%CHECKDB%0 errors%'
            AND Text NOT LIKE '%Setting database option%'
""", 1),
    ("""                OR ProcessInfo = 'Backup'
            )
        ORDER BY LogDate DESC;
""",
     """                OR ProcessInfo = 'Backup'
                OR PrevIsHeader = 1
            )
        ORDER BY Seq;
""", 1),
    # o mapeamento das linhas passa pelo emparelhamento
    ("""            for row in result:
                log_date = row.get('LogDate', '')
                text = row.get('Text', '')
                process_info = row.get('ProcessInfo', '')

                # Tentar extrair severity do texto
                severity = None
                import re
                sev_match = re.search(r'Severity:\\s*(\\d+)', text)
                if sev_match:
                    severity = int(sev_match.group(1))

                # Tentar extrair error number
                err_match = re.search(r'Error:\\s*(\\d+)', text)
                error_number = int(err_match.group(1)) if err_match else None

                # Classificar severidade para display
                if severity and severity >= 17:
                    display_severity = 'ERROR'
                elif severity and severity >= 11:
                    display_severity = 'WARNING'
                elif 'fail' in text.lower() or 'error' in text.lower():
                    display_severity = 'WARNING'
                else:
                    display_severity = 'INFO'

                errors.append({
                    'error_date': str(log_date) if log_date else '',
                    'errorDate': str(log_date) if log_date else '',
                    'log_date': str(log_date) if log_date else '',
                    'error_severity': severity or display_severity,
                    'severity': display_severity,
                    'error_number': error_number,
                    'errorNumber': error_number,
                    'error_message': text,
                    'message': text,
                    'text': text,
                    'process_info': process_info,
                    'database_name': None,
                    'databaseName': None,
                    'source': 'xp_readerrorlog'
                })
""",
     """            # 2026-09-16: o cabecalho "Error: N, Severity, State" e a mensagem que se lhe segue passam a ser
            # UMA linha, com a base de dados e o nivel certos (informativa -> INFO). Ver api/errorlog_pairs.py.
            from api.errorlog_pairs import emparelhar_errorlog
            errors.extend(emparelhar_errorlog(result))
""", 1),
]

PORTAL_EDITS = [
    ("""            const classifySqlLevel = (err) => {
                const sev = String(err.error_severity || err.severity || err.error_number || '').toUpperCase();
""",
     """            const classifySqlLevel = (err) => {
                // 2026-09-16: se o servidor ja emparelhou o cabecalho com a mensagem e ela e' informativa
                // ("This is an informational message"), o nivel e' INFO mesmo com Severity 16 no cabecalho.
                if (String(err.severity || '').toUpperCase() === 'INFO') return 'INFO';
                const sev = String(err.error_severity || err.severity || err.error_number || '').toUpperCase();
""", 1),
    ("""            window._logColFilter = window._logColFilter || { win: {}, sql: {} };
""",
     """            // 2026-09-16 (owner): a tabela SQL nasce filtrada por ERRO -- e' o que se procura quando se abre a aba.
            // O utilizador pode apagar o filtro; o valor persiste na sessao como qualquer outro.
            window._logColFilter = window._logColFilter || { win: {}, sql: { level: 'ERRO' } };
""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Aba Log: cada erro do SQL Server traz a sua mensagem, e a tabela abre filtrada por erros** (owner 16/09).\n"
    "  O SQL Server escreve cada erro em duas linhas — o cabeçalho `Error: N, Severity, State` e, a seguir, a\n"
    "  mensagem — e o ecrã mostrava só o cabeçalho, porque a segunda linha caía nos filtros. Passam a ser uma linha,\n"
    "  com a base de dados extraída e o nível certo: quando o próprio SQL Server diz que é informativa (como o 41145\n"
    "  no arranque de um grupo de disponibilidade), deixa de aparecer como erro. O filtro de nível nasce em ERRO.\n"
    "  [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = r'''"""
2026-09-16 -- as duas linhas de um erro do errorlog passam a ser uma, com base de dados e nivel certos.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.errorlog_pairs import emparelhar_errorlog  # noqa: E402

PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
MAIN = (ROOT / "watcherdb_main.py").read_text(encoding="utf-8").replace("\r\n", "\n")


def _r(data, spid, texto):
    return {"LogDate": data, "ProcessInfo": spid, "Text": texto}


def test_cabecalho_e_continuacao_viram_uma_linha_informativa():
    rows = [
        _r("2026-09-16 16:30:09", "spid142s", "Error: 41145, Severity: 16, State: 1."),
        _r("2026-09-16 16:30:09", "spid142s", "Cannot join database 'INFA_EXC_02_105' to availability group 'SQLMDMPRDAG03'.  "
                                                "The database has already joined the availability group.  This is an informational message.  No user action is required."),
    ]
    out = emparelhar_errorlog(rows)
    assert len(out) == 1
    e = out[0]
    assert e["error_number"] == 41145 and e["error_severity"] == 16
    assert e["message"].startswith("Error: 41145, Severity: 16, State: 1. — Cannot join database")
    assert e["database_name"] == "INFA_EXC_02_105"
    assert e["severity"] == "INFO", "o proprio SQL Server diz que e' informativa"
    assert "already joined" in e["context"]


def test_cabecalho_com_continuacao_grave_fica_erro_com_base():
    rows = [
        _r("2026-09-16 10:00:00", "spid55", "Error: 823, Severity: 24, State: 2."),
        _r("2026-09-16 10:00:00", "spid55", "The operating system returned error 21 to SQL Server during a read at offset 0x0 in file 'E:\\data\\Vendas.mdf'. ... database 'Vendas'."),
    ]
    e = emparelhar_errorlog(rows)[0]
    assert e["severity"] == "ERROR" and e["database_name"] == "Vendas" and e["error_number"] == 823


def test_continuacao_de_outro_spid_nao_e_adoptada():
    rows = [
        _r("2026-09-16 10:00:00", "spid55", "Error: 18456, Severity: 14, State: 8."),
        _r("2026-09-16 10:00:00", "spid77", "Login failed for user 'x'. Reason: Password did not match. [CLIENT: 10.0.0.1]"),
    ]
    out = emparelhar_errorlog(rows)
    assert len(out) == 2
    cab = next(o for o in out if o["error_number"] == 18456)
    assert cab["context"] is None and cab["severity"] == "WARNING"


def test_dois_cabecalhos_seguidos_nao_se_engolem():
    rows = [
        _r("2026-09-16 10:00:00", "spid55", "Error: 41145, Severity: 16, State: 1."),
        _r("2026-09-16 10:00:00", "spid55", "Error: 41145, Severity: 16, State: 1."),
        _r("2026-09-16 10:00:00", "spid55", "Cannot join database 'cmx_ors' to availability group 'AG'. This is an informational message."),
    ]
    out = emparelhar_errorlog(rows)
    assert len(out) == 2
    assert sorted(o["context"] is not None for o in out) == [False, True]


def test_linha_solta_informativa_e_descartada_e_a_grave_fica():
    rows = [
        _r("2026-09-16 10:00:00", "spid9", "Recovery is writing a checkpoint in database 'x'. This is an informational message only."),
        _r("2026-09-16 10:00:01", "spid9", "SQL Server has encountered 3 occurrence(s) of I/O requests taking longer than 15 seconds to complete on file 'E:\\x.mdf' in database 'Vendas' (7)."),
    ]
    out = emparelhar_errorlog(rows)
    assert len(out) == 1 and out[0]["database_name"] == "Vendas"


def test_saida_vem_por_data_decrescente():
    rows = [_r("2026-09-16 09:00:00", "a", "Error: 1, Severity: 20, State: 1."), _r("2026-09-16 11:00:00", "b", "Error: 2, Severity: 20, State: 1.")]
    out = emparelhar_errorlog(rows)
    assert [o["error_number"] for o in out] == [2, 1]


def test_o_endpoint_usa_o_emparelhamento_e_a_sequencia():
    i = MAIN.index('@app.get("/api/monitoring/sql-errors/{server_id}")')
    bloco = MAIN[i:i + 9000]
    assert "Seq INT IDENTITY(1,1)" in bloco
    assert "LAG(Text) OVER (PARTITION BY ProcessInfo ORDER BY Seq)" in bloco
    assert "OR PrevIsHeader = 1" in bloco and "ORDER BY Seq;" in bloco
    assert "NOT LIKE '%This is an informational message%'" not in bloco, "a decisao 'informativa' e' depois de emparelhar"
    assert "errors.extend(emparelhar_errorlog(result))" in bloco


def test_a_tabela_sql_nasce_filtrada_por_erro():
    assert "window._logColFilter = window._logColFilter || { win: {}, sql: { level: 'ERRO' } };" in PORTAL


def test_o_ecra_honra_o_info_do_servidor_antes_do_numero_da_severidade():
    i = PORTAL.index("const classifySqlLevel = (err) => {")
    bloco = PORTAL[i:i + 700]
    assert "if (String(err.severity || '').toUpperCase() === 'INFO') return 'INFO';" in bloco
    assert bloco.index("=== 'INFO') return 'INFO'") < bloco.index("const sev = String(err.error_severity")
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:140]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    main_txt = src["main"].read_bytes().decode("utf-8")
    if MARK in main_txt:
        print("[ABORT] ja aplicado"); return 1
    out = {
        "main": _apply(main_txt, MAIN_EDITS, "watcherdb_main"),
        "portal": _apply(src["portal"].read_bytes().decode("utf-8"), PORTAL_EDITS, "portal"),
        "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog"),
    }
    compile(out["main"], str(REL["main"]), "exec")
    compile(MOD_SRC, str(REL["mod"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] watcherdb_main 6 blocos (Seq, 2 INSERT, CTE/LAG, WHERE, mapeamento); portal 2 (filtro ERRO, INFO do servidor); changelog; modulo novo; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["mod"].write_bytes(MOD_SRC.encode("utf-8")); print(f"[new]   {REL['mod']}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_errorlog_pairs_20260916.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
