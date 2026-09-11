"""ALWAYS ON REGRA UNICA 2026-09-11 - classificacao partilhada de replicas Always On "unhealthy".

Origem: TestSprite TC-011 (card 2 vs modal 4) -> diagnostico 10/09: unidade (instancias vs bases) e
rotulo, nao regra; mas o resumo (helpers.collect_alwayson) e a modal (intelligence_kpis, kpi_type
always-on) tinham DUAS copias quase iguais do WHERE, que divergiam se a coluna Availability_Mode
existisse na STG. Aqui vive a regra uma vez, em SQL e em Python (para testes e para o breakdown).

UNIDADE DO KPI: numero de INSTANCIAS distintas com pelo menos uma base unhealthy. A STG tem uma linha
por (Instance, Database); a modal mostra essas linhas e diz "N instancias . M bases".

REGRA (uma linha e' unhealthy se qualquer condicao for verdadeira):
  - Pri_Synch_Health / Sec_Synch_Health presente e diferente de HEALTHY
  - Pri_Is_Suspended = 1 ou Sec_Is_Suspended = 1
  - estado de sincronizacao anormal:
      sem Availability_Mode: NOT IN (SYNCHRONIZED, SYNCHRONIZING, UNKNOWN, '')  [SYNCHRONIZING nunca conta]
      com Availability_Mode: <> SYNCHRONIZED e <> UNKNOWN e <> '' e NAO (SYNCHRONIZING em ASYNCHRONOUS_COMMIT)
        [SYNCHRONIZING em commit sincrono conta; em assincrono e' normal]
  - lado vazio de uma replica (NULL/'') nunca conta (evita falso positivo do secundario sem dados)
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Set

HEALTH_OK = "HEALTHY"
STATE_OK_PLAIN = ("SYNCHRONIZED", "SYNCHRONIZING", "UNKNOWN", "")
ENVS = ("PRD", "QLT", "TST", "Undefined")

_avail_mode_cache: Dict[str, bool] = {}


def _c(alias: str, col: str) -> str:
    return f"{alias}.{col}" if alias else col


def _health_bad(alias: str, col: str) -> str:
    c = _c(alias, col)
    return f"({c} <> '{HEALTH_OK}' AND {c} IS NOT NULL AND {c} <> '')"


def _state_bad(alias: str, col: str, has_avail_mode: bool) -> str:
    c = _c(alias, col)
    if not has_avail_mode:
        lst = ", ".join(f"'{s}'" for s in STATE_OK_PLAIN)
        return f"({c} NOT IN ({lst}) AND {c} IS NOT NULL)"
    am = _c(alias, "Availability_Mode")
    return (f"({c} <> 'SYNCHRONIZED' AND {c} IS NOT NULL AND {c} <> 'UNKNOWN' AND {c} <> '' "
            f"AND NOT ({c} = 'SYNCHRONIZING' AND ISNULL({am}, '') = 'ASYNCHRONOUS_COMMIT'))")


def unhealthy_where(alias: str = "", has_avail_mode: bool = False) -> str:
    """Expressao booleana SQL (sem o AND inicial) que selecciona linhas unhealthy."""
    return (
        f"{_health_bad(alias, 'Pri_Synch_Health')}"
        f" OR {_health_bad(alias, 'Sec_Synch_Health')}"
        f" OR {_state_bad(alias, 'Pri_Synch_State', has_avail_mode)}"
        f" OR {_state_bad(alias, 'Sec_Synch_State', has_avail_mode)}"
        f" OR {_c(alias, 'Pri_Is_Suspended')} = 1"
        f" OR {_c(alias, 'Sec_Is_Suspended')} = 1"
    )


def problem_reasons_case(alias: str = "", has_avail_mode: bool = False) -> str:
    """Expressao SQL com os motivos ('Health Problem; Suspended; Sync State; '), COERENTE com o WHERE."""
    return (
        "RTRIM(LTRIM("
        f"CASE WHEN {_health_bad(alias, 'Pri_Synch_Health')} OR {_health_bad(alias, 'Sec_Synch_Health')} "
        "THEN 'Health Problem; ' ELSE '' END + "
        f"CASE WHEN {_c(alias, 'Pri_Is_Suspended')} = 1 OR {_c(alias, 'Sec_Is_Suspended')} = 1 "
        "THEN 'Suspended; ' ELSE '' END + "
        f"CASE WHEN {_state_bad(alias, 'Pri_Synch_State', has_avail_mode)} OR {_state_bad(alias, 'Sec_Synch_State', has_avail_mode)} "
        "THEN 'Sync State; ' ELSE '' END"
        "))"
    )


# ---------- equivalente Python (testes, breakdown, e qualquer consumidor sem SQL) ----------

def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _py_health_bad(v: Any) -> bool:
    s = _s(v)
    return bool(s) and s.upper() != HEALTH_OK


def _py_state_bad(state: Any, avail_mode: Any, has_avail_mode: bool) -> bool:
    s = _s(state).upper()
    if not s or s in ("UNKNOWN", "SYNCHRONIZED"):
        return False
    if not has_avail_mode:
        return s not in STATE_OK_PLAIN
    if s == "SYNCHRONIZING" and _s(avail_mode).upper() == "ASYNCHRONOUS_COMMIT":
        return False
    return True


def classify(row: Dict[str, Any], has_avail_mode: bool = False) -> List[str]:
    """Motivos de uma linha da STG; lista vazia = saudavel. Mesma ordem que o CASE SQL."""
    if not row:
        return []
    reasons: List[str] = []
    if _py_health_bad(row.get("Pri_Synch_Health")) or _py_health_bad(row.get("Sec_Synch_Health")):
        reasons.append("Health Problem")
    if str(row.get("Pri_Is_Suspended") or "0") in ("1", "True") or str(row.get("Sec_Is_Suspended") or "0") in ("1", "True"):
        reasons.append("Suspended")
    am = row.get("Availability_Mode")
    if _py_state_bad(row.get("Pri_Synch_State"), am, has_avail_mode) or _py_state_bad(row.get("Sec_Synch_State"), am, has_avail_mode):
        reasons.append("Sync State")
    return reasons


def is_unhealthy(row: Dict[str, Any], has_avail_mode: bool = False) -> bool:
    return bool(classify(row, has_avail_mode))


def instance_of(row: Dict[str, Any]) -> str:
    return _s(row.get("Instance") or row.get("INSTANCE") or row.get("ServerInstance") or row.get("SERVER_INSTANCE"))


def distinct_instances(rows: Optional[Iterable[Dict[str, Any]]]) -> Set[str]:
    return {instance_of(r) for r in (rows or []) if r and instance_of(r)}


def by_env_distinct_instances(rows: Optional[Iterable[Dict[str, Any]]],
                              infer_env: Optional[Callable[[str], str]] = None) -> Dict[str, int]:
    """Instancias DISTINTAS por ambiente (o breakdown tem de somar o cartao). Env da linha; se faltar,
    infer_env(instancia) quando fornecido (helpers passa _infer_env_from_instance)."""
    vistos: Dict[str, Set[str]] = {e: set() for e in ENVS}
    for r in (rows or []):
        if not r:
            continue
        inst = instance_of(r)
        if not inst:
            continue
        env = _s(r.get("Env") or r.get("ENV") or r.get("Environment") or r.get("environment"))
        if (not env or env == "Undefined") and infer_env:
            env = _s(infer_env(inst))
        env_u = env.upper() if env else "Undefined"
        vistos[env_u if env_u in ("PRD", "QLT", "TST") else "Undefined"].add(inst)
    return {e: len(v) for e, v in vistos.items()}


def has_availability_mode(execute: Callable[[str], Any], schema: str) -> bool:
    """Deteccao cacheada (por processo) da coluna Availability_Mode na STG. execute(sql) -> lista de dicts.
    Ausencia ou erro => False (regra simples), nunca excepcao."""
    if schema in _avail_mode_cache:
        return _avail_mode_cache[schema]
    try:
        rows = execute(f"SELECT COL_LENGTH('{schema}.KPI_MSSQL_ALWAYSON_STATUS_STG', 'Availability_Mode') AS L")
        val = bool(rows and rows[0].get("L") is not None)
    except Exception:  # noqa: BLE001
        val = False
    _avail_mode_cache[schema] = val
    return val


def reset_cache() -> None:
    _avail_mode_cache.clear()
