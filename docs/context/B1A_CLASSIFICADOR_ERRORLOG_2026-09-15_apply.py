# -*- coding: utf-8 -*-
"""B1a (2026-09-15) -- classificador puro do errorlog do SQL Server, no repo V1. Sem base de dados, sem ligar ao recolhedor.

Plano: docs/context/PLANO_EXECUCAO_ALERTAS_ERRORLOG_2026-09-14.md, Bloco B. Medicao: docs/context/B0_MEDICAO_ERRORLOG_2026-09-15.md.
Ordem imposta pelo guardiao do recolhedor (watcherdb-v1-intel-specialist, parecer de 15/09, sem veto):
  B1a classificador sem DB  ->  B1b janela temporal e timeout de consulta  ->  B2a marca de agua e MERGE por ciclo
  ->  B2b colunas de agregacao SO na HIST  ->  B3 bloco no ecra de offline.

Condicao do guardiao ja resolvida por medicao na base viva (sql_monitoring, 15/09): nas 8 variantes BLUE/GREEN da STG,
Log_Text_Hash e' int normal e sem chave primaria; na HIST e' coluna calculada CHECKSUM(Log_Text) e a proc de arquivo
recalcula-a. Um hash deterministico no recolhedor nao viola nenhuma chave.

O modulo:
  classify(rows)          linhas de xp_readerrorlog (data, processo, texto) -> eventos com Error_Number, Severity,
                          State, Log_Type e accao (keep, aggregate, drop). Emparelha o cabecalho "Error: N, Severity: S,
                          State: X." com a linha de descricao seguinte (mesma data e processo).
  aggregate_hourly(ev)    repetitivos contados por (hora, categoria, numero; estado so em Security)
  text_hash(texto)        crc32 com sinal, cabe em int; substitui abs(hash()), que muda a cada processo

Uso (raiz do repo V3.4; escreve no repo V1 ao lado):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/B1A_CLASSIFICADOR_ERRORLOG_2026-09-15_apply.py --check
  py docs/context/B1A_CLASSIFICADOR_ERRORLOG_2026-09-15_apply.py
  cd "..\\WATCHERDB INTELLIGENCE V1"
  py -m pytest tests/unit/test_errorlog_classifier.py -q -p no:cacheprovider
"""
from __future__ import annotations

import sys
from pathlib import Path

V34 = Path(__file__).resolve().parents[2]
V1 = V34.parent / "WATCHERDB INTELLIGENCE V1"
REL = {
    "module": Path("watcherdb_intelligence/collectors/errorlog_classifier.py"),
    "test": Path("tests/unit/test_errorlog_classifier.py"),
    "changelog": Path("docs/CHANGELOG.md"),
}

MODULE_SRC = r'''"""Classificador do errorlog do SQL Server (B1a, 2026-09-15).

Puro: sem base de dados e sem rede. Recebe as linhas de xp_readerrorlog por ordem cronologica, como tuplos
(log_date, process_info, text), e devolve eventos classificados.

Desenho medido em 14 instancias de producao a 15/09 (relatorio B0_MEDICAO_ERRORLOG_2026-09-15.md no repo V3.4)
e revisto pelo guardiao do recolhedor. Factos que o justificam:
  - arranques e encerramentos NAO contem a palavra "Error": o filtro N'Error' do recolhedor perde-os;
  - o erro que mais volume faz (33208, auditoria sem acesso ao log de seguranca) tem severidade 17: a severidade
    sozinha nao filtra;
  - cerca de 724 linhas por dia em 14 instancias com esta politica, contra 71.508 com o filtro de hoje.

Accoes:
  keep       guardar um a um
  aggregate  repetitivos: contar por hora (aggregate_hourly)
  drop       informativo
Log_Type: Lifecycle, AvailabilityGroup, Critical, Security, Error, Repetitive, Info.
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

KEEP, AGGREGATE, DROP = "keep", "aggregate", "drop"
LOG_TYPES = ("Lifecycle", "AvailabilityGroup", "Critical", "Security", "Error", "Repetitive", "Info")

HEADER = re.compile(r"^\s*Error:\s*(\d+),\s*Severity:\s*(\d+),\s*State:\s*(\d+)\.?\s*$")

# ---- por numero de erro (linhas com cabecalho). A ordem de avaliacao e' a desta tabela, depois a severidade.
SECURITY_AGGREGATE = {18456: "login_falhado", 18452: "login_dominio_nao_confiavel", 18470: "login_desabilitado"}
SECURITY_KEEP = {18486: "login_bloqueado"}
REPETITIVE = {33208: "auditoria_sem_acesso", 33204: "auditoria_sem_acesso", 17836: "pacote_de_rede_invalido",
              1222: "lock_timeout", 17810: "dac_ocupada"}
AG_AGGREGATE = {976: "ag_base_inacessivel", 983: "ag_base_inacessivel", 35262: "ag_arranque_informativo",
                41145: "ag_arranque_informativo", 35278: "ag_arranque_informativo"}
AG_KEEP = {19406: "ag_mudanca_de_estado", 1480: "mirroring_mudanca_de_papel", 35264: "ag_movimento_suspenso",
           35265: "ag_movimento_retomado"}
CRITICAL_AGGREGATE = {1105: "filegroup_cheio", 9002: "log_de_transaccoes_cheio"}
CRITICAL_KEEP = {823: "io_corrupcao", 824: "io_corrupcao", 825: "io_repetido", 829: "pagina_suspeita",
                 605: "pagina_invalida", 211: "corrupcao", 601: "corrupcao", 701: "memoria_insuficiente",
                 802: "memoria_insuficiente", 8645: "memoria_timeout", 3624: "assercao", 17065: "assercao",
                 17066: "assercao", 17883: "scheduler_nao_cede", 17884: "scheduler_nao_cede",
                 17888: "scheduler_nao_cede", 5180: "ficheiro_inacessivel", 9001: "log_indisponivel",
                 9004: "log_corrompido"}

# ---- por padrao de texto (linhas sem cabecalho). Primeira regra que casa ganha.
TEXT_RULES: Sequence[Tuple[re.Pattern, str, str, str]] = (
    (re.compile(r"SQL Server is starting at normal priority base", re.I), "Lifecycle", KEEP, "arranque"),
    (re.compile(r"SQL Server is terminating|SQL Server shutdown has been initiated|SQL Trace was stopped due to server shutdown", re.I),
     "Lifecycle", KEEP, "encerramento"),
    (re.compile(r"state of the local availability replica in availability group .* changed from|is changing roles from", re.I),
     "AvailabilityGroup", KEEP, "ag_mudanca_de_papel"),
    (re.compile(r"lease (between .* has expired|has expired)|stop the lease renewal", re.I),
     "AvailabilityGroup", KEEP, "ag_lease_expirado"),
    (re.compile(r"stack dump|SqlDumpExceptionHandler|non-yielding|Stack Signature|BugCheck", re.I), "Critical", KEEP, "dump_ou_travado"),
    (re.compile(r"DBCC CHECK\w+ .* found [1-9]\d* errors", re.I), "Critical", KEEP, "dbcc_com_erros"),
    (re.compile(r"Autogrow of file .* (cancelled|timed out)", re.I), "Critical", KEEP, "autogrow_falhado"),
    (re.compile(r"I/O requests taking longer than 15 seconds", re.I), "Critical", AGGREGATE, "io_lento_833"),
    (re.compile(r"significant part of sql server process memory has been paged out", re.I), "Critical", AGGREGATE, "memoria_paginada"),
)


@dataclass(frozen=True)
class ErrorLogEvent:
    log_date: datetime
    process_info: str
    text: str
    error_number: Optional[int]
    severity: Optional[int]
    state: Optional[int]
    log_type: str
    action: str
    category: str


def _by_number(num: int, sev: int) -> Tuple[str, str, str]:
    for table, log_type, action in ((SECURITY_AGGREGATE, "Security", AGGREGATE), (SECURITY_KEEP, "Security", KEEP),
                                    (REPETITIVE, "Repetitive", AGGREGATE), (AG_AGGREGATE, "AvailabilityGroup", AGGREGATE),
                                    (AG_KEEP, "AvailabilityGroup", KEEP), (CRITICAL_AGGREGATE, "Critical", AGGREGATE),
                                    (CRITICAL_KEEP, "Critical", KEEP)):
        if num in table:
            return log_type, action, table[num]
    if sev >= 20:
        return "Critical", KEEP, "severidade_20_mais"
    if sev >= 11:
        return "Error", KEEP, "erro_sev_11_19"
    return "Info", DROP, "erro_informativo"


def _by_text(text: str) -> Tuple[str, str, str]:
    for rx, log_type, action, category in TEXT_RULES:
        if rx.search(text):
            return log_type, action, category
    return "Info", DROP, "informativo"


def classify(rows: Iterable[Sequence[Any]]) -> List[ErrorLogEvent]:
    """Classifica linhas (log_date, process_info, text) por ordem cronologica.

    O cabecalho "Error: N, Severity: S, State: X." e a descricao que o SQL Server escreve a seguir (mesma data e mesmo
    processo) viram UM evento, com o texto das duas. Um cabecalho sem descricao fica sozinho.
    """
    linhas = [(r[0], (r[1] or "").strip(), (r[2] or "").strip()) for r in rows]
    eventos: List[ErrorLogEvent] = []
    i = 0
    while i < len(linhas):
        log_date, proc, text = linhas[i]
        m = HEADER.match(text)
        if m:
            num, sev, state = int(m.group(1)), int(m.group(2)), int(m.group(3))
            juntado = text
            if i + 1 < len(linhas) and linhas[i + 1][0] == log_date and linhas[i + 1][1] == proc \
                    and not HEADER.match(linhas[i + 1][2]):
                juntado = f"{text} {linhas[i + 1][2]}"
                i += 1
            log_type, action, category = _by_number(num, sev)
            eventos.append(ErrorLogEvent(log_date, proc, juntado, num, sev, state, log_type, action, category))
        else:
            log_type, action, category = _by_text(text)
            eventos.append(ErrorLogEvent(log_date, proc, text, None, None, None, log_type, action, category))
        i += 1
    return eventos


def aggregate_hourly(events: Iterable[ErrorLogEvent]) -> List[Dict[str, Any]]:
    """Repetitivos contados por (hora, categoria, numero de erro; estado so em Security, onde e' o motivo do login)."""
    grupos: Dict[Tuple, Dict[str, Any]] = {}
    for e in events:
        if e.action != AGGREGATE:
            continue
        hora = e.log_date.replace(minute=0, second=0, microsecond=0)
        estado = e.state if e.log_type == "Security" else None
        chave = (hora, e.category, e.error_number, estado)
        g = grupos.get(chave)
        if g is None:
            grupos[chave] = {"hour": hora, "log_type": e.log_type, "category": e.category, "error_number": e.error_number,
                             "severity": e.severity, "state": estado, "occurrences": 1,
                             "first_log_date": e.log_date, "last_log_date": e.log_date, "sample_text": e.text}
        else:
            g["occurrences"] += 1
            g["first_log_date"] = min(g["first_log_date"], e.log_date)
            g["last_log_date"] = max(g["last_log_date"], e.log_date)
    return sorted(grupos.values(), key=lambda g: (g["hour"], g["category"], g["error_number"] or 0, g["state"] or 0))


def text_hash(text: str) -> int:
    """crc32 com sinal (cabe em int do SQL Server). Deterministico entre processos, ao contrario de hash()."""
    h = zlib.crc32((text or "").encode("utf-8"))
    return h - (1 << 32) if h >= (1 << 31) else h


def summarize(events: Iterable[ErrorLogEvent]) -> Dict[str, int]:
    resumo: Dict[str, int] = {KEEP: 0, AGGREGATE: 0, DROP: 0}
    for e in events:
        resumo[e.action] += 1
    return resumo
'''

TEST_SRC = r'''"""
B1a (2026-09-15): classificador do errorlog. Linhas com a forma real medida em producao a 15/09 (nomes anonimizados).
"""
from datetime import datetime

import pytest

from watcherdb_intelligence.collectors.errorlog_classifier import (
    AGGREGATE, DROP, KEEP, LOG_TYPES, aggregate_hourly, classify, summarize, text_hash,
)

pytestmark = pytest.mark.unit
T = datetime(2026, 9, 15, 10, 5, 0)


def at(minute, second=0, hour=10):
    return datetime(2026, 9, 15, hour, minute, second)


def one(rows):
    ev = classify(rows)
    assert len(ev) == 1, ev
    return ev[0]


def test_login_falhado_emparelha_cabecalho_e_descricao_e_vai_para_seguranca_agregada():
    e = one([(T, "Logon", "Error: 18456, Severity: 14, State: 5."),
             (T, "Logon", "Login failed for user 'app_user'. Reason: Could not find a login matching the name provided. [CLIENT: 10.0.0.1]")])
    assert (e.error_number, e.severity, e.state) == (18456, 14, 5)
    assert (e.log_type, e.action, e.category) == ("Security", AGGREGATE, "login_falhado")
    assert e.text.startswith("Error: 18456, Severity: 14, State: 5. Login failed for user")


def test_auditoria_sem_acesso_severidade_17_e_repetitiva_e_nao_erro_grave():
    e = one([(T, "spid12s", "Error: 33208, Severity: 17, State: 1."),
             (T, "spid12s", "SQL Server Audit failed to access the security log. Make sure that the SQL service account has the required permissions to access the security log.")])
    assert (e.log_type, e.action) == ("Repetitive", AGGREGATE)


def test_arranque_e_guardado_apesar_de_dizer_informational_e_de_nao_ter_error():
    e = one([(T, "Server", "SQL Server is starting at normal priority base (=0). This is an informational message only. No user action is required.")])
    assert (e.log_type, e.action, e.category) == ("Lifecycle", KEEP, "arranque")


def test_encerramento_guardado_e_parallel_redo_largado():
    ev = classify([(at(1), "spid9s", "SQL Server is terminating in response to a 'stop' request from Service Control Manager. This is an informational message only. No user action is required."),
                   (at(2), "spid31s", "Parallel redo is shutdown for database 'AppDB' with worker pool size [2].")])
    assert [(e.category, e.action) for e in ev] == [("encerramento", KEEP), ("informativo", DROP)]


def test_mudanca_de_papel_ag_guardada_e_espera_do_cluster_largada():
    ev = classify([(at(1), "spid38s", "The state of the local availability replica in availability group 'AG01' has changed from 'RESOLVING_NORMAL' to 'SECONDARY_NORMAL'.  The state changed because the availability group state has changed in Windows Server Failover Clustering (WSFC)."),
                   (at(2), "spid20s", "Always On Availability Groups: Waiting for local Windows Server Failover Clustering service to start. This is an informational message only. No user action is required.")])
    assert [(e.log_type, e.action) for e in ev] == [("AvailabilityGroup", KEEP), ("Info", DROP)]


def test_falha_de_escrita_de_backup_e_erro_guardado():
    e = one([(T, "Backup", "Error: 18210, Severity: 16, State: 1."),
             (T, "Backup", "BackupIoRequest::ReportIoError: write failure on backup device 'X:\\bkp\\db.bak'. Operating system error 995.")])
    assert (e.log_type, e.action, e.error_number) == ("Error", KEEP, 18210)


def test_corrupcao_e_critica_guardada_e_pacote_invalido_de_severidade_20_e_agregado():
    ev = classify([(at(1), "spid55", "Error: 824, Severity: 24, State: 2."),
                   (at(1), "spid55", "SQL Server detected a logical consistency-based I/O error: incorrect checksum."),
                   (at(2), "Logon", "Error: 17836, Severity: 20, State: 17."),
                   (at(2), "Logon", "Length specified in network packet payload did not match number of bytes read; the connection has been closed.")])
    assert [(e.error_number, e.log_type, e.action) for e in ev] == [(824, "Critical", KEEP), (17836, "Repetitive", AGGREGATE)]


def test_severidade_20_desconhecida_e_critica_e_severidade_10_e_largada():
    ev = classify([(at(1), "spid5", "Error: 99999, Severity: 21, State: 1."), (at(2), "spid5", "Error: 5703, Severity: 10, State: 1.")])
    assert [(e.log_type, e.action) for e in ev] == [("Critical", KEEP), ("Info", DROP)]


def test_filegroup_cheio_e_critico_mas_agregado():
    e = one([(T, "spid77", "Error: 1105, Severity: 17, State: 2."), (T, "spid77", "Could not allocate space for object 'dbo.T' in database 'AppDB' because the 'PRIMARY' filegroup is full.")])
    assert (e.log_type, e.action, e.category) == ("Critical", AGGREGATE, "filegroup_cheio")


def test_padroes_criticos_de_texto():
    ev = classify([(at(1), "Server", "A significant part of sql server process memory has been paged out. This may result in a performance degradation. Duration: 0 seconds."),
                   (at(2), "spid60", "***Stack Dump being sent to C:\\MSSQL\\LOG\\SQLDump0001.txt"),
                   (at(3), "spid61", "DBCC CHECKDB (AppDB) executed by X found 3 errors and repaired 0 errors."),
                   (at(4), "spid61", "DBCC CHECKDB (AppDB) executed by X found 0 errors and repaired 0 errors."),
                   (at(5), "spid2s", "SQL Server has encountered 4 occurrence(s) of I/O requests taking longer than 15 seconds to complete on file [D:\\db.mdf]")])
    assert [(e.category, e.action) for e in ev] == [("memoria_paginada", AGGREGATE), ("dump_ou_travado", KEEP),
                                                    ("dbcc_com_erros", KEEP), ("informativo", DROP), ("io_lento_833", AGGREGATE)]


def test_cabecalho_sem_descricao_e_descricao_de_outro_momento_nao_emparelham():
    ev = classify([(at(1), "spid5", "Error: 1222, Severity: 16, State: 18."),
                   (at(1, 1), "spid5", "Log was backed up. Database: AppDB, creation date(time): 2020/01/01(00:00:00)."),
                   (at(2), "spid6", "Error: 3041, Severity: 16, State: 1.")])
    assert [e.text for e in ev] == ["Error: 1222, Severity: 16, State: 18.",
                                    "Log was backed up. Database: AppDB, creation date(time): 2020/01/01(00:00:00).",
                                    "Error: 3041, Severity: 16, State: 1."]
    assert [e.action for e in ev] == [AGGREGATE, DROP, KEEP]


def test_dois_cabecalhos_seguidos_nao_se_juntam():
    ev = classify([(T, "Logon", "Error: 18456, Severity: 14, State: 5."), (T, "Logon", "Error: 18456, Severity: 14, State: 8.")])
    assert [e.state for e in ev] == [5, 8]


def test_agregacao_por_hora_com_estado_so_em_seguranca():
    rows = []
    for minute in (1, 2, 3, 4, 5):
        rows += [(at(minute), "Logon", "Error: 18456, Severity: 14, State: 5."), (at(minute), "Logon", "Login failed for user 'a'.")]
    for minute in (6, 7):
        rows += [(at(minute), "Logon", "Error: 18456, Severity: 14, State: 38."), (at(minute), "Logon", "Login failed for user 'b'.")]
    for minute in (10, 20, 30):
        rows += [(at(minute, hour=11), "spid9s", "Error: 33208, Severity: 17, State: 1."), (at(minute, hour=11), "spid9s", "SQL Server Audit failed to access the security log.")]
    rows.append((at(40, hour=11), "spid9s", "Error: 33208, Severity: 17, State: 2."))
    g = aggregate_hourly(classify(rows))
    resumo = [(x["hour"].hour, x["error_number"], x["state"], x["occurrences"]) for x in g]
    assert resumo == [(10, 18456, 5, 5), (10, 18456, 38, 2), (11, 33208, None, 4)]
    assert g[0]["first_log_date"] == at(1) and g[0]["last_log_date"] == at(5)
    assert g[2]["sample_text"].startswith("Error: 33208")


def test_hash_deterministico_e_cabe_em_int():
    assert text_hash("abc") == 891568578
    assert text_hash("abc") == text_hash("abc")
    for s in ("", "Login failed", "x" * 5000, "ção"):
        assert -(1 << 31) <= text_hash(s) < (1 << 31)
    assert text_hash(None) == text_hash("")


def test_todos_os_eventos_tem_tipo_e_accao_conhecidos():
    rows = [(T, "p", "Error: 18456, Severity: 14, State: 5."), (T, "p", "Login failed."),
            (at(2), "p", "Starting up database 'AppDB'."), (at(3), "p", "Error: 9002, Severity: 17, State: 2.")]
    ev = classify(rows)
    assert all(e.log_type in LOG_TYPES and e.action in (KEEP, AGGREGATE, DROP) for e in ev)
    assert summarize(ev) == {KEEP: 0, AGGREGATE: 2, DROP: 1}
'''

CHANGELOG_ANCORA = "## [2.29.0] - 2026-09-14\n"
CHANGELOG_NOVO = ("## [Unreleased]\n\n"
                  "### Adicionado — B1a: classificador do errorlog (ainda nao ligado ao recolhedor)\n\n"
                  "- **`watcherdb_intelligence/collectors/errorlog_classifier.py`**, modulo puro sem base de dados. Classifica as\n"
                  "  linhas de `xp_readerrorlog` em Lifecycle, AvailabilityGroup, Critical, Security, Error, Repetitive e Info, com\n"
                  "  accao guardar, agregar por hora ou largar. Emparelha o cabecalho \"Error: N, Severity: S, State: X.\" com a\n"
                  "  descricao e preenche Error_Number, Severity e State, que hoje ficam sempre vazios.\n"
                  "- **Porque:** medido a 15/09 em 14 instancias de producao, os arranques e encerramentos nao contem \"Error\" e o\n"
                  "  recolhedor perde-os; o erro com mais volume (33208) tem severidade 17, logo a severidade sozinha nao filtra.\n"
                  "  Com esta politica sao cerca de 724 linhas por dia em vez de 71.508. Relatorio B0 no repo V3.4.\n"
                  "- **`text_hash`** deterministico (crc32 com sinal) para substituir `abs(hash())`, que muda a cada processo.\n"
                  "  Verificado na base viva: nas STG BLUE/GREEN a coluna e' int normal sem chave primaria.\n"
                  "- Ordem acordada com o guardiao: B1b janela temporal e timeout de consulta, B2a marca de agua e MERGE por\n"
                  "  ciclo na HIST, B2b colunas de agregacao so na HIST.\n\n")


def _eol(text):
    return "\r\n" if "\r\n" in text else "\n"


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or V1
    if not (base / "watcherdb_intelligence" / "collectors").is_dir():
        print(f"[ABORT] nao encontrei o repo V1 em {base}"); return 1
    mod, test, chg = (base / REL[k] for k in ("module", "test", "changelog"))
    if mod.exists() or test.exists():
        print("[ABORT] ja aplicado (modulo ou teste ja existem)"); return 1
    compile(MODULE_SRC, str(REL["module"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    raw = chg.read_bytes().decode("utf-8")
    eol = _eol(raw)
    anc = CHANGELOG_ANCORA.replace("\n", eol)
    if raw.count(anc) != 1:
        print(f"[ABORT] changelog V1: ancora encontrada {raw.count(anc)}x"); return 1
    if "B1a: classificador do errorlog" in raw:
        print("[ABORT] changelog ja tem a entrada"); return 1
    novo_chg = raw.replace(anc, CHANGELOG_NOVO.replace("\n", eol) + anc)
    print(f"[ok] modulo e teste compilam; changelog V1 com ancora unica; destino {base}")
    if check:
        print("--check OK. Nada escrito."); return 0
    mod.write_bytes(MODULE_SRC.encode("utf-8")); print(f"[new]   {REL['module']}")
    test.write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    chg.write_bytes(novo_chg.encode("utf-8")); print(f"[write] {REL['changelog']}")
    print('\nAplicado. Corre: cd "..\\WATCHERDB INTELLIGENCE V1" ; py -m pytest tests/unit/test_errorlog_classifier.py -q -p no:cacheprovider')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
