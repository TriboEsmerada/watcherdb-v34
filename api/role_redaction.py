"""Redaccao por role das respostas JSON dos routers de diagnostico.

Nasceu em api/routers/live_monitoring.py (R2-02 do QA externo, 2026-08-16) e passou a modulo
partilhado a 2026-09-24 (P0 do plano de atribuicao de query a aplicacao) porque o Performance
Module devolvia exactamente os mesmos campos -- sql_text, logins, hosts -- sem nenhum gate.

Regra: `viewer` ve um hash estavel do SQL (agrupa ocorrencias sem ver o texto) e "[oculto]" nas
identidades; `dba` e `admin` veem tudo. Feito ao nivel do ROUTER (route_class) e nao endpoint a
endpoint: o endpoint numero 17 nasce coberto sem ninguem se lembrar.

O SQL nao e' truncado de proposito: truncar continua a revelar nomes de tabela e a forma da query.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Optional

from fastapi import Request, Response
from fastapi.routing import APIRoute

REDACTED = "[oculto - requer nivel dba]"

# Campos com texto SQL (viewer ve hash estavel). Uniao LIVE + Performance Module.
SQL_FIELDS = frozenset({
    "sql_text", "full_sql_text", "full_query_text", "blocked_sql", "blocker_sql",
    "statement_text", "sample_text", "inputbuf", "action_sql",
})
# Campos de identidade (viewer ve o literal REDACTED).
IDENTITY_FIELDS = frozenset({
    "login_name", "blocked_login", "blocker_login",
    "host_name", "client_host", "blocked_host", "blocker_host", "hostname",
    "program_name", "clientapp",
})


def redact_node(node: Any) -> Any:
    """Percorre a arvore da resposta e redige os campos sensiveis."""
    if isinstance(node, list):
        return [redact_node(item) for item in node]
    if isinstance(node, dict):
        saida = {}
        for chave, valor in node.items():
            if chave in SQL_FIELDS and isinstance(valor, str) and valor.strip():
                digest = hashlib.sha256(valor.encode("utf-8", "replace")).hexdigest()[:12]
                saida[chave] = f"{REDACTED} #{digest}"
            elif chave in IDENTITY_FIELDS and isinstance(valor, str) and valor.strip():
                saida[chave] = REDACTED
            else:
                saida[chave] = redact_node(valor)
        return saida
    return node


def role_do_pedido(request: Request) -> Optional[str]:
    """Role do utilizador, posto no request.state pelo AuthEnforcementMiddleware."""
    user = getattr(request.state, "user", None)
    if isinstance(user, dict):
        return user.get("role")
    return None


class RoleRedactingRoute(APIRoute):
    """Redige a resposta quando quem pede e' `viewer`. `dba`/`admin` veem tudo."""

    def get_route_handler(self) -> Callable:
        handler_original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            response = await handler_original(request)
            if role_do_pedido(request) != "viewer":
                return response
            corpo = getattr(response, "body", None)
            if not corpo or "application/json" not in response.headers.get("content-type", ""):
                return response
            try:
                payload = json.loads(corpo)
            except Exception:
                # Um corpo que nao e' JSON nao contem os campos que nos preocupam.
                return response
            novo = json.dumps(redact_node(payload), default=str).encode("utf-8")
            response.body = novo
            response.headers["content-length"] = str(len(novo))
            return response

        return handler
