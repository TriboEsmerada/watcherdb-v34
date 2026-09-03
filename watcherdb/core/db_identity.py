"""Identidade de ligacao a BD -- resolucao unica e explicita (Regra de Ouro #2).

Ate 2026-08-19 a decisao "Windows Auth vs SQL Auth" estava copiada em quatro
sitios, em duas variantes, com um default implicito:

    os.getenv("INTELLIGENCE_USE_WINDOWS_AUTH", "true")

Dois defeitos, apanhados pelo QA externo (rondas 4/5, achado P-05):

1. Uma instalacao limpa que NAO escreva a variavel nascia em Windows Auth --
   o servico ligava a BD com a conta de servico do cliente. Viola a Regra de
   Ouro #2 (so `sql_monitoring` toca em BD).
2. `SQL_TRUSTED_CONNECTION` tinha precedencia SILENCIOSA sobre
   `INTELLIGENCE_USE_WINDOWS_AUTH`. Com as duas definidas em sentidos opostos
   ganhava a primeira, sem aviso -- foi o que aconteceu em producao (.env com
   INTELLIGENCE_USE_WINDOWS_AUTH=false e SQL_TRUSTED_CONNECTION=yes, e o
   arranque a reportar WINDOWS_AUTH=True).

Decisao do owner (2026-08-19): sem configuracao explicita o servico NAO
arranca. Nao ha default implicito -- UNSET e CONFLICT sao estados proprios.

Separacao deliberada:
  - `resolve()` NAO levanta excepcao. E' chamada no import dos routers e tem
    de ser inofensiva em testes e em ferramentas offline.
  - `enforce_explicit_identity()` e' que recusa o arranque, e e' invocada no
    ponto de entrada do servico (`watcherdb_service.py`), depois de o .env
    3-tier estar carregado.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

WINDOWS = "windows"
SQL = "sql"
UNSET = "unset"
CONFLICT = "conflict"

_TRUE = ("yes", "true", "1")
_FALSE = ("no", "false", "0")

_TRUSTED_VAR = "SQL_TRUSTED_CONNECTION"
_INTEL_VAR = "INTELLIGENCE_USE_WINDOWS_AUTH"


@dataclass(frozen=True)
class DbIdentity:
    """Modo de autenticacao resolvido + de onde veio (para log e diagnostico)."""

    mode: str
    source: str

    @property
    def use_windows_auth(self) -> bool:
        """True so em WINDOWS. UNSET/CONFLICT nunca ligam com Windows Auth."""
        return self.mode == WINDOWS

    @property
    def is_explicit(self) -> bool:
        return self.mode in (WINDOWS, SQL)


def _as_bool(raw: str):
    """'yes'/'true'/'1' -> True; 'no'/'false'/'0' -> False; resto -> None."""
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return None


def resolve() -> DbIdentity:
    """Resolve o modo de autenticacao a partir do ambiente. Nunca levanta."""
    trusted_raw = os.getenv(_TRUSTED_VAR, "").strip().lower()
    intel_raw = os.getenv(_INTEL_VAR, "").strip().lower()

    trusted = _as_bool(trusted_raw) if trusted_raw else None
    intel = _as_bool(intel_raw) if intel_raw else None

    # Valor presente mas ininteligivel conta como ausente, com rasto no source.
    noise = []
    if trusted_raw and trusted is None:
        noise.append(f"{_TRUSTED_VAR}={trusted_raw!r} ignorado (valor invalido)")
    if intel_raw and intel is None:
        noise.append(f"{_INTEL_VAR}={intel_raw!r} ignorado (valor invalido)")
    suffix = ("; " + "; ".join(noise)) if noise else ""

    if trusted is None and intel is None:
        return DbIdentity(UNSET, "nenhuma variavel de identidade definida" + suffix)

    if trusted is not None and intel is not None and trusted != intel:
        return DbIdentity(
            CONFLICT,
            f"{_TRUSTED_VAR}={trusted_raw} contradiz {_INTEL_VAR}={intel_raw}" + suffix,
        )

    decided = trusted if trusted is not None else intel
    var = _TRUSTED_VAR if trusted is not None else _INTEL_VAR
    raw = trusted_raw if trusted is not None else intel_raw
    return DbIdentity(WINDOWS if decided else SQL, f"{var}={raw}" + suffix)


class DbIdentityError(RuntimeError):
    """Configuracao de identidade ausente ou contraditoria -- arranque recusado."""


_REMEDY = (
    "Define no .env, de forma explicita:\n"
    "    INTELLIGENCE_USE_WINDOWS_AUTH=false\n"
    "    INTELLIGENCE_SQL_USER=sql_monitoring\n"
    "    INTELLIGENCE_SQL_PASSWORD=<password>\n"
    "e remove ou alinha o SQL_TRUSTED_CONNECTION.\n"
    "Windows Auth so com decisao deliberada (INTELLIGENCE_USE_WINDOWS_AUTH=true) "
    "-- a Regra de Ouro #2 reserva o acesso a BD ao sql_monitoring."
)


def enforce_explicit_identity() -> DbIdentity:
    """Recusa o arranque se a identidade nao estiver configurada de forma explicita.

    Chamada no ponto de entrada do servico, depois do carregamento do .env.
    NAO deve ser chamada no import de routers -- ver docstring do modulo.
    """
    identity = resolve()
    if identity.mode == UNSET:
        raise DbIdentityError(
            "Identidade de ligacao a BD nao configurada: "
            f"{identity.source}.\n{_REMEDY}"
        )
    if identity.mode == CONFLICT:
        raise DbIdentityError(
            "Identidade de ligacao a BD contraditoria: "
            f"{identity.source}.\n{_REMEDY}"
        )
    return identity
