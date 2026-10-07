"""Nomes da base e do login nos scripts SQL do produto: validacao, substituicao em runtime e lotes GO.

Decisao (DESIGN_INSTALADOR_V3.4_2026-10-07.md, lote A.1): o canonico database/INSTALACAO_COMPLETA_UNIFICADA.sql
fica BYTE-IGUAL no repo. O nome da base (WatcherDB_Intelligence, 73 ocorrencias, 11 USE, nomes de ficheiros
logicos, @database_name nos jobs, SQL dinamico) e o do login (sql_monitoring, 19 GRANT) sao substituidos em
memoria, no momento de executar, pelo nome que o cliente escolheu. Com os nomes canonicos a substituicao e'
a identidade (teste byte-identico).

Seguranca: os nomes passam por validar_identificador() antes de entrarem em qualquer SQL -- so' letras,
digitos e underscore, ate' 64 caracteres (os nomes de ficheiros logicos ganham sufixos _KPI_Data/_KPI_Hist e
o limite do SQL Server e' 128). Isto elimina injeccao e o problema das aspas duplicadas no SQL dinamico.
"""
from __future__ import annotations

import re
from typing import List, Tuple

NOME_BASE_CANONICO = "WatcherDB_Intelligence"
LOGIN_CANONICO = "sql_monitoring"

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# Fronteira = nao-alfanumerico (o underscore NAO e' fronteira): assim WatcherDB_Intelligence_KPI_Data vira
# <base>_KPI_Data e WatcherDB_Intelligence.mdf vira <base>.mdf, como o deploy-architect previu.
_RE_BASE = re.compile(r"(?<![A-Za-z0-9])" + re.escape(NOME_BASE_CANONICO) + r"(?![A-Za-z0-9])")
_RE_LOGIN = re.compile(r"(?<![A-Za-z0-9])" + re.escape(LOGIN_CANONICO) + r"(?![A-Za-z0-9])")

# Separador de lotes como o sqlcmd: GO sozinho na linha, opcionalmente 'GO n' (repete n vezes), case-insensitive.
_RE_GO = re.compile(r"^\s*GO(?:\s+(\d+))?\s*;?\s*$", re.IGNORECASE)

# Ordem dos scripts, igual a deploy/setup_database.ps1:105-131 (2026-09-16).
SCRIPTS: Tuple[str, ...] = (
    "00_WATCHERDB_MASTER_DEPLOY.sql",
    "02_WATCHERDB_INDEXES.sql",
    "03_WATCHERDB_PROCEDURES.sql",
    "04_WATCHERDB_VIEWS.sql",
    "05_WATCHERDB_BLUE_GREEN_ENV.sql",
    "CREATE_USER_AUTH_PREFS.sql",
    "CREATE_DISK_UNALLOCATED_TABLES.sql",
    "CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql",
    "CRIAR_VIEW_ALWAYSON_AGG.sql",
    "SQLSERVER_KPI_VIEWS.sql",
    "SQLSERVER_KPI_COLLECTION_PROCEDURES.sql",
    "SQLSERVER_KPI_DEPLOY_COMPLETE.sql",
    "SQLSERVER_KPI_AGENT_JOBS.sql",
    "SQLSERVER_KPI_REPLICATION_COMPLETE.sql",
    "KPI_SERVER_OFFLINE_EVENTS.sql",
    "FIX_BACKUP_SCORE_OVERVIEW.sql",
    "COLLECTION_HISTORY_SECTION.sql",
    "UPDATE_DB_AVAILABILITY_MIRRORING.sql",
    "INSTALACAO_COMPLETA_UNIFICADA.sql",
    "06_CREATE_TOKEN_BLACKLIST.sql",
    "14_ADD_MUST_CHANGE_PASSWORD.sql",
    "08_CREATE_SYSTEM_CONFIG.sql",
)


class NomeInvalido(ValueError):
    """Identificador fora de ^[A-Za-z_][A-Za-z0-9_]{0,63}$."""


def validar_identificador(nome: str, papel: str = "identificador") -> str:
    """Devolve o nome se for seguro para entrar em SQL; senao levanta NomeInvalido com mensagem clara."""
    if not isinstance(nome, str) or not _IDENT_RE.match(nome):
        raise NomeInvalido(
            f"{papel} invalido: {nome!r}. So' letras, digitos e underscore, a comecar por letra ou underscore, "
            f"ate' 64 caracteres (sem espacos, pontos, hifens, aspas ou parentesis rectos)."
        )
    return nome


def substituir_nomes(sql: str, base: str, login: str) -> Tuple[str, int, int]:
    """Substitui o nome canonico da base e do login por (base, login). Devolve (sql, n_base, n_login).

    Com base == NOME_BASE_CANONICO e login == LOGIN_CANONICO devolve o texto INALTERADO (identidade).
    """
    validar_identificador(base, "nome da base")
    validar_identificador(login, "login")
    n_base = n_login = 0
    if base != NOME_BASE_CANONICO:
        sql, n_base = _RE_BASE.subn(base, sql)
    if login != LOGIN_CANONICO:
        sql, n_login = _RE_LOGIN.subn(login, sql)
    return sql, n_base, n_login


def restos_canonicos(sql: str, base: str, login: str) -> List[Tuple[int, str]]:
    """Linhas onde ainda aparece um nome canonico que DEVIA ter sido substituido. Vazio = ok."""
    restos: List[Tuple[int, str]] = []
    for i, linha in enumerate(sql.splitlines(), start=1):
        if base != NOME_BASE_CANONICO and _RE_BASE.search(linha):
            restos.append((i, linha.strip()[:120]))
        elif login != LOGIN_CANONICO and _RE_LOGIN.search(linha):
            restos.append((i, linha.strip()[:120]))
    return restos


def dividir_lotes(sql: str) -> List[str]:
    """Divide por GO como o sqlcmd. Lotes vazios (so' espacos) sao descartados; 'GO n' repete o lote n vezes."""
    lotes: List[str] = []
    actual: List[str] = []

    def fechar(repeticoes: int = 1) -> None:
        texto = "\n".join(actual).strip()
        actual.clear()
        if texto:
            lotes.extend([texto] * max(1, repeticoes))

    for linha in sql.lstrip("﻿").splitlines():
        m = _RE_GO.match(linha)
        if m:
            fechar(int(m.group(1)) if m.group(1) else 1)
        else:
            actual.append(linha)
    fechar()
    return lotes
