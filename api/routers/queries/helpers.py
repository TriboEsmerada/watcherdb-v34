#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared helpers for SQL Queries sub-modules.
Contains: execute_query_on_server, connection pool, serialization, caching.
"""

from fastapi import HTTPException
from typing import Dict, List, Optional
import logging
import re
from decimal import Decimal
import time

from modules.monitoring.monitoring import SQLServerMonitoring, SQLServerExecutor, ConnectionPool, ConnectionInfo
from api.error_helpers import safe_http_error

logger = logging.getLogger(__name__)

# === POOL DE CONEXOES GLOBAL ===
# NOTE: ConnectionPool is now an adapter that delegates to the centralized
# pool at api/connection_pool.py (circuit-breaker + retry).  Creating a new
# ConnectionPool() here simply wraps the same underlying singleton.
_global_pool: Optional[ConnectionPool] = None
_global_executor: Optional[SQLServerExecutor] = None
_DATABASES_CACHE_TTL = 60
_DATABASES_CACHE: Dict[str, Dict[str, object]] = {}


def _get_global_executor() -> SQLServerExecutor:
    """Retorna executor global, criando se necessario (singleton)"""
    global _global_pool, _global_executor
    if _global_executor is None:
        _global_pool = ConnectionPool(max_connections=20)
        _global_executor = SQLServerExecutor(_global_pool, max_workers=8)
        logger.info("Global ConnectionPool and SQLServerExecutor initialized (via centralized pool)")
    return _global_executor


def _serialize_result(obj):
    """Serializa objetos para JSON (converte Decimal, etc)"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _serialize_result(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_result(item) for item in obj]
    return obj


def _get_cached_databases(server_id: str) -> Optional[List[Dict]]:
    cache_key = server_id.upper()
    entry = _DATABASES_CACHE.get(cache_key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _DATABASES_CACHE_TTL:
        return None
    return entry["data"]


def _set_cached_databases(server_id: str, data: List[Dict], server_info: Dict = None) -> None:
    cache_key = server_id.upper()
    _DATABASES_CACHE[cache_key] = {"ts": time.time(), "data": data, "server_info": server_info or {}}


# R2-05 (QA externo, ronda 2, 2026-08-18): um server_id malformado atravessava
# o parsing abaixo -- que nunca falha, porque qualquer string produz um par
# servidor/instancia -- chegava ao pyodbc e saia 500. Lixo enviado pelo cliente
# e' 400, nao erro interno nosso. Forma aceite: HOST, HOST\INSTANCIA,
# HOST_INSTANCIA, com porta opcional.
_SERVER_ID_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._\-]*(?:\\[A-Za-z0-9._\-]+)?(?:,\d{1,5})?$"
)
_SERVER_ID_MAX = 128


def validate_server_id(server_id: str) -> str:
    """Valida a FORMA do server_id e devolve-o normalizado.

    Nao valida existencia: um servidor sem credencial guardada cai por desenho
    no fallback de Trusted_Connection (`_resolve_credentials` devolve None), por
    isso "desconhecido" nao e' distinguivel de "sem credencial" aqui.

    A mensagem de erro nao ecoa o valor recebido -- o QA registou que o corpo
    da resposta estava limpo e nao ha razao para o sujar agora.
    """
    if not server_id or not server_id.strip():
        raise HTTPException(status_code=400, detail="server_id obrigatorio")
    candidato = server_id.strip()
    if len(candidato) > _SERVER_ID_MAX or not _SERVER_ID_RE.match(candidato):
        raise HTTPException(
            status_code=400,
            detail=(
                "server_id invalido: esperado HOST, HOST\\INSTANCIA ou "
                "HOST_INSTANCIA (letras, digitos, ponto, hifen, underscore)"
            ),
        )
    return candidato


async def execute_query_on_server(
    server_id: str,
    query: str,
    command_timeout: Optional[int] = None,
    connection_timeout: Optional[int] = None,
) -> List[Dict]:
    """Executa query em um servidor especifico usando pool global de conexoes"""
    server_id = validate_server_id(server_id)
    try:
        executor = _get_global_executor()

        if '\\' in server_id:
            server, instance = server_id.split('\\', 1)
        elif '_' in server_id and not server_id.endswith('_DEFAULT'):
            parts = server_id.rsplit('_', 1)
            server, instance = parts[0], parts[1] if len(parts) > 1 else "DEFAULT"
        else:
            server = server_id.replace('_DEFAULT', '')
            instance = "DEFAULT"

        conn_info = ConnectionInfo(
            server=server,
            instance=instance,
            database="master",
            use_windows_auth=True,
            connection_timeout=connection_timeout or 30,
            command_timeout=command_timeout or 300,
        )

        result = await executor.execute_query(conn_info, query, timeout=command_timeout)

        if result is None:
            # ANTES devolvia [] -- e' isso que punha "0 certificados" num servidor
            # com TDE activo e 33 bases cifradas por TDECert_TAP (QA externo 5o
            # passe, 2026-08-17). O proprio comentario original ja dizia "possivel
            # erro silencioso": a suspeita estava certa, faltava agir sobre ela.
            #
            # NOTA sobre o alcance: so' muda o caminho de FALHA (result is None).
            # Uma query que corre bem e devolve zero linhas continua a devolver []
            # -- "sem dados" permanece distinto de "falhou", que e' o ponto todo.
            logger.error(
                f"Query falhou para {server_id} (retornou None) - a propagar 503 "
                f"em vez de lista vazia (query: {query[:80]}...)"
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Nao foi possivel ler os dados em {server_id}. "
                    "O resultado nao e' zero -- e' desconhecido."
                ),
            )

        if isinstance(result, list):
            return _serialize_result(result)
        else:
            return _serialize_result([{"result": str(result)}])

    except HTTPException:
        # O 503 acima e' deliberado e ja traz a mensagem certa -- sem este ramo,
        # o `except Exception` abaixo apanhava-o e convertia num 500 generico,
        # perdendo a distincao entre "falhou a ler" e "rebentou a executar".
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"executing query on {server_id}")
