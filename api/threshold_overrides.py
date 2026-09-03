"""
Resolução de thresholds com overrides do cliente — Fase 1/2.
============================================================

Camada por cima do registry (fonte única, Fase 0). Lê a tabela
`WDB_KPI_THRESHOLDS` (BD partilhada) e resolve o valor efectivo de cada
KPI aplicando a precedência de âmbito:

    DATABASE > INSTANCE > ENV > GLOBAL > default do registry

FASE 1 (Std): só linhas com Scope_Type='GLOBAL' são escritas pela UI —
o resolve() abaixo já suporta os outros âmbitos na LEITURA, para a Fase 2
(Pro/V6) não precisar de tocar nesta camada nem no schema partilhado.

CONTRATO DE SEGURANÇA (design 2026-08-04):
- Tabela ausente / erro / vazia  ⇒  comportamento IDÊNTICO à Fase 0
  (fallback total ao registry). O golden test prova isto.
- Cache com TTL curto (60s, como o resto do dashboard); refresh explícito
  no topo de cada request async antes das classificações síncronas.
- Leitura via a MESMA ligação da app (sql_monitoring hoje; a wave de
  identidades diferida troca isto por watcherdb_app sem tocar aqui).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from api.kpi_thresholds_registry import value as _registry_value, THRESHOLDS

logger = logging.getLogger(__name__)

_TABLE = "dbo.WDB_KPI_THRESHOLDS"
_CACHE_TTL_S = 60

# cache: { kpi_type: { scope_key: {'warning': x, 'critical': y} } }
# scope_key = f"{scope_type}\x1f{scope_value}"  (GLOBAL usa scope_value='')
_cache: dict = {}
_cache_ts: float = 0.0
_lock = threading.Lock()
_table_available = True  # vira False no 1o erro; re-tenta no proximo TTL


def _scope_key(scope_type: str, scope_value: str) -> str:
    return f"{(scope_type or 'GLOBAL').upper()}\x1f{scope_value or ''}"


def refresh_cache(force: bool = False) -> None:
    """Recarrega o cache de overrides se o TTL expirou (thread-safe, barato).

    Nunca levanta — em erro deixa o cache como está e marca a tabela como
    indisponível até ao próximo ciclo (fallback ao registry entretanto).
    """
    global _cache, _cache_ts, _table_available
    now = time.monotonic()
    if not force and (now - _cache_ts) < _CACHE_TTL_S:
        return
    with _lock:
        if not force and (now - _cache_ts) < _CACHE_TTL_S:
            return
        try:
            from api.connection_pool import execute_on_intelligence
            rows = execute_on_intelligence(
                f"SELECT Kpi_Type, Scope_Type, Scope_Value, Warning_Value, "
                f"Critical_Value FROM {_TABLE} WITH (NOLOCK)",
                params=(),
            ) or []
            new_cache: dict = {}
            for r in rows:
                kpi = r.get("Kpi_Type")
                if not kpi:
                    continue
                sk = _scope_key(r.get("Scope_Type"), r.get("Scope_Value"))
                w = r.get("Warning_Value")
                c = r.get("Critical_Value")
                new_cache.setdefault(kpi, {})[sk] = {
                    "warning": None if w is None else float(w),
                    "critical": None if c is None else float(c),
                }
            _cache = new_cache
            _cache_ts = now
            _table_available = True
        except Exception as exc:
            # tabela ainda nao criada (Fase 1 pendente de DDL) ou erro de rede:
            # fallback silencioso ao registry — NAO poluir logs a cada request
            if _table_available:
                logger.info(
                    "WDB_KPI_THRESHOLDS indisponivel (%s) — a usar defaults do "
                    "registry. Normal se a tabela ainda nao foi criada.", exc,
                )
            _table_available = False
            _cache = {}
            _cache_ts = now  # evita martelar a BD; re-tenta so no proximo TTL


def _override_for(kpi: str, level: str,
                  instance: Optional[str], env: Optional[str],
                  database: Optional[str]) -> Optional[float]:
    """Primeiro override na cadeia de precedencia com valor != None p/ o level."""
    per_kpi = _cache.get(kpi)
    if not per_kpi:
        return None
    # precedencia: mais especifico primeiro
    candidates = []
    if database:
        candidates.append(_scope_key("DATABASE", database))
    if instance:
        candidates.append(_scope_key("INSTANCE", instance))
    if env:
        candidates.append(_scope_key("ENV", env))
    candidates.append(_scope_key("GLOBAL", ""))
    for sk in candidates:
        entry = per_kpi.get(sk)
        if entry is not None and entry.get(level) is not None:
            return entry[level]
    return None


def resolve(kpi: str, level: str,
            instance: Optional[str] = None,
            env: Optional[str] = None,
            database: Optional[str] = None):
    """Valor efectivo de (kpi, level): override do cliente ou default do registry.

    NAO faz I/O — lê do cache. Chamar refresh_cache() no topo do request.
    Assinatura super-set de registry.value(): instance/env/database são
    ignorados na Fase 1 (só GLOBAL existe na tabela) mas já resolvem scope
    na Fase 2 sem mudar chamadas.
    """
    ov = _override_for(kpi, level, instance, env, database)
    if ov is not None:
        return ov
    return _registry_value(kpi, level)


def effective_list(instance: Optional[str] = None,
                   env: Optional[str] = None,
                   database: Optional[str] = None) -> list:
    """Registry + overrides aplicados — para o ecra 'Thresholds em vigor'.

    Marca cada KPI com is_overridden e a origem do valor (default|GLOBAL|
    ENV|INSTANCE|DATABASE) para a UI distinguir 'default do produto' de
    'override do cliente'.
    """
    refresh_cache()
    out = []
    for kpi, t in THRESHOLDS.items():
        row = {
            "kpi": kpi,
            "label": t["label"],
            "unit": t["unit"],
            "source": t["source"],
            "is_mirror": not t["source"].startswith("backend"),
            "configurable_f1": t["configurable_f1"],
            "note": t.get("note"),
            "default_warning": t["warning"],
            "default_critical": t["critical"],
        }
        for level in ("warning", "critical"):
            ov = _override_for(kpi, level, instance, env, database)
            row[level] = ov if ov is not None else t[level]
            row[f"{level}_overridden"] = ov is not None
        out.append(row)
    return out


def table_available() -> bool:
    return _table_available
