"""Validacao de `Origin` em escritas -- mitigacao CSRF (achado 2b, QA ronda 2).

Contexto do achado. O token de sessao viaja tambem em cookie
(`access_token`, HttpOnly, SameSite=Lax) e o backend aceita-o como fallback
quando nao ha cabecalho -- portanto o browser autentica pedidos sozinho. O
`SameSite=Lax` bloqueia o CSRF classico cross-SITE, mas nao cobre um vizinho
same-site comprometido (SameSite classifica por site registavel, nao por
origem): uma pagina em `outra.tap.pt` consegue emitir um POST para o portal e o
cookie viaja.

Ficam de fora dessa mitigacao residual os endpoints cujo corpo NAO e'
obrigatorio: um `<form>` cross-origin nao dispara preflight, logo nao cai na
allowlist do CORS. Os endpoints com corpo Pydantic exigem
`application/json`, o que forca preflight e ja esta coberto.

Porque `Origin` e nao "exigir corpo". Exigir corpo funcionaria, mas so por
efeito colateral -- o corpo forcar `application/json` que forca preflight. Foi
assim que o buraco nasceu: `body: Optional[RunRequest] = None` tornou um corpo
opcional e reabriu a porta sem ninguem dar por isso. Um controlo que depende de
um efeito colateral apodrece no primeiro refactor; a verificacao de origem e'
intencional e sobrevive.

Politica, e porque nao e' mais apertada:
  - metodo seguro (GET/HEAD/OPTIONS) -> passa. CSRF exige efeito de escrita.
  - `Origin` ausente -> passa. Clientes nao-browser (curl, o harness k6 da
    ronda 3, collectors) nao enviam `Origin`, e sem browser nao ha cookie
    anexado automaticamente -- nao ha vector. Recusar aqui partia a ronda 3 e
    nao acrescentava seguranca.
  - `Origin` presente e diferente da origem do proprio pedido (ou da allowlist
    do CORS) -> 403.
"""

from __future__ import annotations

import logging
from typing import Set

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

_METODOS_COM_EFEITO = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _normalizar(origem: str) -> str:
    return (origem or "").strip().rstrip("/").lower()


def origens_aceites(request: Request) -> Set[str]:
    """A origem do proprio pedido + as origens declaradas no CORS."""
    aceites = set()

    host = request.headers.get("host", "")
    if host:
        aceites.add(_normalizar(f"{request.url.scheme}://{host}"))

    try:
        from watcherdb.core.cors import get_cors_config

        for origem in (get_cors_config() or {}).get("allow_origins", []) or []:
            if origem and origem != "*":
                aceites.add(_normalizar(origem))
    except Exception as exc:  # pragma: no cover - config ausente nao deve trancar
        logger.debug("CORS indisponivel para validacao de origem: %s", exc)

    return aceites


async def require_same_origin(request: Request) -> None:
    """Dependencia: recusa escritas vindas de uma origem que nao a nossa."""
    if request.method.upper() not in _METODOS_COM_EFEITO:
        return

    origem = _normalizar(request.headers.get("origin", ""))
    if not origem:
        return  # cliente nao-browser -- ver docstring do modulo

    if origem in origens_aceites(request):
        return

    logger.warning(
        "Escrita recusada por origem cruzada: %s %s (Origin=%s)",
        request.method,
        request.url.path,
        origem,
    )
    raise HTTPException(status_code=403, detail="Origem nao permitida")
