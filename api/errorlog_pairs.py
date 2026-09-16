# -*- coding: utf-8 -*-
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
