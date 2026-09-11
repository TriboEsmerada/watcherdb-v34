"""ALWAYS ON REGRA UNICA (TestSprite TC-011) - PASSO 1.

BLOCO PROVA (escrito antes do codigo):
  Regra: test_by_env_conta_instancias_distintas FALHA hoje (by_env conta linhas por base) e passa depois.
  Ecra: modal do cartao "Always On unhealthy" passa a dizer "N instancia(s) . M base(s) com problema"
        (teste estatico do template + caso drill-down do TestSukita grava valor e linhas).
  Dado: SELECT do owner (10/09 16:0x): 1 linha MYBAGP2@SQLHDSPRD405 = 1 instancia distinta = cartao 1.

Diagnostico (10/09, sem editar): os 4 "instancias" do TC-011 eram BASES; card = COUNT(DISTINCT Instance);
modal = 1 linha por (instancia, base) rotulada como "instancia(s)"; unhealthy_by_env contava linhas.
Hipotese Availability_Mode nao se aplica: coluna nao existe no canonico (INSTALACAO_COMPLETA_UNIFICADA 815).

O que escreve:
  1. api/routers/intelligence/alwayson_rules.py: UMA regra (WHERE + CASE dos motivos + classificador Python
     equivalente + contagens por instancia distinta + deteccao cacheada da coluna Availability_Mode).
  2. helpers.py collect_alwayson: COUNT, lista e by_env pela regra unica; +unhealthy_db_count.
  3. intelligence_kpis.py modal always-on: mesma regra (antes divergia se a coluna existisse).
  4. portal showProblematicInstances: ramo always-on "N instancia(s) . M base(s) com problema".
  5. i18n kpi_modal.database_s (pt/en/es).
  6. tests/unit/test_alwayson_rules_20260911.py: 5 casos do prompt + contrato (3 sitios usam a regra).

Fora deste lote (registado): dados ausentes/erro de leitura ainda viram 0 no cartao (convencao N/D dos cartoes
de dashboard e' lote proprio); coluna Availability_Mode na STG e' infra partilhada V1 (veto v1-intel).

Uso (raiz do repo):  py docs/context/ALWAYSON_REGRA_UNICA_PASSO1_apply.py
Depois:              pwsh docs/context/ALWAYSON_REGRA_UNICA_PASSO2_commit.ps1
Propagacao V6: mesmo modulo + mesmos 3 patches (helpers/kpis/portal) - prompt em CONTEXT.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "api" / "routers" / "intelligence" / "alwayson_rules.py"
HELPERS = ROOT / "api" / "routers" / "intelligence" / "helpers.py"
KPIS = ROOT / "api" / "routers" / "intelligence_kpis.py"
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
TEST = ROOT / "tests" / "unit" / "test_alwayson_rules_20260911.py"
MARK = "ALWAYS ON REGRA UNICA 2026-09-11"


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT [{label}]: esperava 1, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


RULES_SRC = '''"""ALWAYS ON REGRA UNICA 2026-09-11 - classificacao partilhada de replicas Always On "unhealthy".

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
'''

# ---------- helpers.py ----------
H_IMPORT_ANCHOR = "async def collect_alwayson(results: Dict[str, Any]) -> None:\n"
H_IMPORT_NEW = ("from api.routers.intelligence.alwayson_rules import (  # ALWAYS ON REGRA UNICA 2026-09-11\n"
                "    unhealthy_where as _ao_where, problem_reasons_case as _ao_reasons,\n"
                "    by_env_distinct_instances as _ao_by_env, distinct_instances as _ao_distinct,\n"
                ")\n\n\n"
                "async def collect_alwayson(results: Dict[str, Any]) -> None:\n")

H_FILTER_OLD = '''        if _has_avail_mode:
            _state_filter = """
                OR (Pri_Synch_State <> 'SYNCHRONIZED' AND Pri_Synch_State IS NOT NULL AND Pri_Synch_State <> 'UNKNOWN' AND Pri_Synch_State <> ''
                    AND NOT (Pri_Synch_State = 'SYNCHRONIZING' AND ISNULL(Availability_Mode, '') = 'ASYNCHRONOUS_COMMIT'))
                OR (Sec_Synch_State <> 'SYNCHRONIZED' AND Sec_Synch_State IS NOT NULL AND Sec_Synch_State <> 'UNKNOWN' AND Sec_Synch_State <> ''
                    AND NOT (Sec_Synch_State = 'SYNCHRONIZING' AND ISNULL(Availability_Mode, '') = 'ASYNCHRONOUS_COMMIT'))
            """
        else:
            _state_filter = """
                OR (Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND Pri_Synch_State IS NOT NULL)
                OR (Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND Sec_Synch_State IS NOT NULL)
            """

        query_unhealthy = f"""
        SELECT COUNT(DISTINCT Instance) AS Always_On_UnHealthy
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
        WHERE Update_TS >= DATEADD(MINUTE, -{FRESHNESS_WINDOWS['alwayson']}, GETDATE())
        AND (
            (Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> '')
            OR (Sec_Synch_Health <> 'HEALTHY' AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> '')
            {_state_filter}
            OR Pri_Is_Suspended = 1
            OR Sec_Is_Suspended = 1
        )
        """
'''
H_FILTER_NEW = '''        # ALWAYS ON REGRA UNICA 2026-09-11: WHERE e motivos vem de alwayson_rules (o mesmo da modal).
        _ao_w = _ao_where("", _has_avail_mode)

        query_unhealthy = f"""
        SELECT COUNT(DISTINCT Instance) AS Always_On_UnHealthy
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
        WHERE Update_TS >= DATEADD(MINUTE, -{FRESHNESS_WINDOWS['alwayson']}, GETDATE())
        AND ({_ao_w})
        """
'''

H_LIST_OLD = '''            s.Update_TS,
            RTRIM(LTRIM(
                CASE WHEN (s.Pri_Synch_Health <> 'HEALTHY' AND s.Pri_Synch_Health IS NOT NULL AND s.Pri_Synch_Health <> '')
                          OR (s.Sec_Synch_Health <> 'HEALTHY' AND s.Sec_Synch_Health IS NOT NULL AND s.Sec_Synch_Health <> '')
                     THEN 'Health Problem; ' ELSE '' END +
                CASE WHEN s.Pri_Is_Suspended = 1 OR s.Sec_Is_Suspended = 1 THEN 'Suspended; ' ELSE '' END +
                CASE WHEN (s.Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND s.Pri_Synch_State IS NOT NULL)
                          OR (s.Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND s.Sec_Synch_State IS NOT NULL)
                     THEN 'Sync State; ' ELSE '' END
            )) AS Problem_Reasons
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_STG s WITH (NOLOCK)
        LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e ON e.Instance = s.Instance
        WHERE s.Update_TS >= DATEADD(MINUTE, -{FRESHNESS_WINDOWS['alwayson']}, GETDATE())
        AND (
            (s.Pri_Synch_Health <> 'HEALTHY' AND s.Pri_Synch_Health IS NOT NULL AND s.Pri_Synch_Health <> '')
            OR (s.Sec_Synch_Health <> 'HEALTHY' AND s.Sec_Synch_Health IS NOT NULL AND s.Sec_Synch_Health <> '')
            {_state_filter}
            OR s.Pri_Is_Suspended = 1
            OR s.Sec_Is_Suspended = 1
        )
        ORDER BY s.Instance
        """
'''
H_LIST_NEW = '''            s.Update_TS,
            {_ao_reasons('s', _has_avail_mode)} AS Problem_Reasons
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_STG s WITH (NOLOCK)
        LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e ON e.Instance = s.Instance
        WHERE s.Update_TS >= DATEADD(MINUTE, -{FRESHNESS_WINDOWS['alwayson']}, GETDATE())
        AND ({_ao_where('s', _has_avail_mode)})
        ORDER BY s.Instance
        """
'''

H_BYENV_OLD = '''        results["always_on"]["instances"] = unhealthy_instances
        results["always_on"]["unhealthy_by_env"] = _count_by_env(unhealthy_instances)
'''
H_BYENV_NEW = '''        results["always_on"]["instances"] = unhealthy_instances
        # ALWAYS ON REGRA UNICA: o breakdown conta INSTANCIAS distintas (soma o cartao); linhas sao bases.
        results["always_on"]["unhealthy_by_env"] = _ao_by_env(unhealthy_instances, _infer_env_from_instance)
        results["always_on"]["unhealthy_db_count"] = len(unhealthy_instances)
        results["always_on"]["unhealthy_instances_count"] = len(_ao_distinct(unhealthy_instances))
'''

# ---------- intelligence_kpis.py ----------
K_OLD = '''                s.Update_TS,
                RTRIM(LTRIM(
                    CASE WHEN (s.Pri_Synch_Health <> 'HEALTHY' AND s.Pri_Synch_Health IS NOT NULL AND s.Pri_Synch_Health <> '')
                              OR (s.Sec_Synch_Health <> 'HEALTHY' AND s.Sec_Synch_Health IS NOT NULL AND s.Sec_Synch_Health <> '')
                         THEN 'Health Problem; ' ELSE '' END +
                    CASE WHEN s.Pri_Is_Suspended = 1 OR s.Sec_Is_Suspended = 1 THEN 'Suspended; ' ELSE '' END +
                    CASE WHEN (s.Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND s.Pri_Synch_State IS NOT NULL)
                              OR (s.Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND s.Sec_Synch_State IS NOT NULL)
                         THEN 'Sync State; ' ELSE '' END
                )) AS Problem_Reasons
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_STG s WITH (NOLOCK)
            LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e ON e.Instance = s.Instance
            WHERE s.Update_TS >= DATEADD(MINUTE, -{FRESHNESS_WINDOWS['alwayson']}, GETDATE())
            AND (
                (s.Pri_Synch_Health <> 'HEALTHY' AND s.Pri_Synch_Health IS NOT NULL AND s.Pri_Synch_Health <> '')
                OR (s.Sec_Synch_Health <> 'HEALTHY' AND s.Sec_Synch_Health IS NOT NULL AND s.Sec_Synch_Health <> '')
                OR (s.Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND s.Pri_Synch_State IS NOT NULL)
                OR (s.Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND s.Sec_Synch_State IS NOT NULL)
                OR s.Pri_Is_Suspended = 1
                OR s.Sec_Is_Suspended = 1
            )
            ORDER BY s.Instance, s.[Database]
            """
'''
K_NEW = '''                s.Update_TS,
                {_ao_reasons('s', _ao_avail)} AS Problem_Reasons
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_STG s WITH (NOLOCK)
            LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e ON e.Instance = s.Instance
            WHERE s.Update_TS >= DATEADD(MINUTE, -{FRESHNESS_WINDOWS['alwayson']}, GETDATE())
            AND ({_ao_where('s', _ao_avail)})
            ORDER BY s.Instance, s.[Database]
            """
'''
K_PRE_OLD = '''            # logica antiga que trata o lado vazio da replica (normal) como avaria, ficando
            # falso positivo em 100% das linhas. O Problem_Reasons abaixo e' recalculado aqui.
            query = f"""
'''
K_PRE_NEW = '''            # logica antiga que trata o lado vazio da replica (normal) como avaria, ficando
            # falso positivo em 100% das linhas. O Problem_Reasons abaixo e' recalculado aqui.
            # ALWAYS ON REGRA UNICA 2026-09-11: WHERE e motivos da MESMA regra do cartao (alwayson_rules).
            from api.routers.intelligence.alwayson_rules import (
                unhealthy_where as _ao_where, problem_reasons_case as _ao_reasons, has_availability_mode as _ao_has_am,
            )
            _ao_avail = _ao_has_am(lambda q: execute_intelligence_query(q, raise_on_error=False) or [], INTELLIGENCE_SCHEMA)
            query = f"""
'''

# ---------- portal ----------
P_OLD = "                } else if (kpiType === 'db-availability-ok' || title === 'Instances OK') {\n"
P_NEW = '''                } else if (kpiType === 'always-on') {
                    // ALWAYS ON REGRA UNICA 2026-09-11 (TestSprite TC-011): as linhas sao BASES (uma por instancia+base);
                    // o cartao conta instancias distintas. Dizer as duas unidades evita ler 4 bases como 4 instancias.
                    const _aoInstancias = new Set(instances.map(i => String(i.Instance || i.instance || i.SERVER_INSTANCE || i.AgName || ''))).size;
                    summaryText = `Total: <strong style="color: var(--color-text-primary);">${_aoInstancias}</strong> ${t('kpi_modal.instance_s')} \\u00b7 <strong style="color: var(--color-text-primary);">${instances.length}</strong> ${t('kpi_modal.database_s')} ${t('kpi_modal.with_problem')}`;
                } else if (kpiType === 'db-availability-ok' || title === 'Instances OK') {
'''

LOCALES = {"pt": "base(s) de dados", "en": "database(s)", "es": "base(s) de datos"}
I18N_ANCHOR = {"pt": '    "instance_s": "instância(s)",\n', "en": '    "instance_s": "instance(s)",\n', "es": '    "instance_s": "instancia(s)",\n'}

TEST_SRC = '''"""ALWAYS ON REGRA UNICA 2026-09-11: os 5 casos do prompt do TestSprite (TC-011) + contrato dos 3 sitios."""
from pathlib import Path

import pytest

from api.routers.intelligence.alwayson_rules import (
    by_env_distinct_instances, classify, distinct_instances, is_unhealthy, problem_reasons_case, unhealthy_where,
)

ROOT = Path(__file__).resolve().parents[2]


def _row(inst, db, env="PRD", **kw):
    base = {"Instance": inst, "Database": db, "Env": env, "Pri_Synch_Health": "HEALTHY", "Sec_Synch_Health": "HEALTHY",
            "Pri_Synch_State": "SYNCHRONIZED", "Sec_Synch_State": "SYNCHRONIZED", "Pri_Is_Suspended": 0, "Sec_Is_Suspended": 0}
    base.update(kw)
    return base


def test_duas_instancias_unhealthy_reais():
    rows = [_row("SQLHDSPRD211_I01", "FENIX", Sec_Synch_Health="NOT_HEALTHY"),
            _row("SQLHDSPRD405_I01", "MYBAGP2", Sec_Is_Suspended=1, Sec_Synch_State="NOT SYNCHRONIZING")]
    assert all(is_unhealthy(r) for r in rows)
    assert distinct_instances(rows) == {"SQLHDSPRD211_I01", "SQLHDSPRD405_I01"}
    assert classify(rows[1]) == ["Suspended", "Sync State"]


def test_linhas_duplicadas_por_base_contam_uma_instancia():
    # o caso do TC-011: 4 bases em 2 instancias -> cartao 2, modal 4 linhas
    rows = [_row("SQLHDSPRD211_I01", d, Sec_Synch_Health="NOT_HEALTHY") for d in ("DATACAP_01", "FENIX", "MicroStrategyRep")]
    rows.append(_row("SQLHDSPRD405_I01", "MYBAGP2", Sec_Is_Suspended=1))
    assert len(rows) == 4
    assert len(distinct_instances(rows)) == 2


def test_by_env_conta_instancias_distintas():
    # FALHAVA antes deste lote: _count_by_env contava linhas (4), o cartao dizia 2
    rows = [_row("SQLHDSPRD211_I01", d, Sec_Synch_Health="NOT_HEALTHY") for d in ("A", "B", "C")]
    rows.append(_row("SQLHDSPRD405_I01", "MYBAGP2", Sec_Is_Suspended=1))
    rows.append(_row("SQLHDSQLT211_I01", "A", "QLT", Sec_Synch_Health="NOT_HEALTHY"))
    env = by_env_distinct_instances(rows)
    assert env == {"PRD": 2, "QLT": 1, "TST": 0, "Undefined": 0}
    assert sum(env.values()) == len(distinct_instances(rows))


def test_replica_assincrona_em_synchronizing_nao_e_unhealthy():
    sem_coluna = _row("X", "D", Sec_Synch_State="SYNCHRONIZING")
    assert not is_unhealthy(sem_coluna, has_avail_mode=False)
    com_coluna_async = _row("X", "D", Sec_Synch_State="SYNCHRONIZING", Availability_Mode="ASYNCHRONOUS_COMMIT")
    assert not is_unhealthy(com_coluna_async, has_avail_mode=True)
    com_coluna_sync = _row("X", "D", Sec_Synch_State="SYNCHRONIZING", Availability_Mode="SYNCHRONOUS_COMMIT")
    assert classify(com_coluna_sync, has_avail_mode=True) == ["Sync State"]
    # SQL segue a mesma regra
    assert "ASYNCHRONOUS_COMMIT" in unhealthy_where("s", True) and "ASYNCHRONOUS_COMMIT" not in unhealthy_where("s", False)


def test_instancia_suspensa_conta_e_lado_vazio_nao_conta():
    assert classify(_row("X", "D", Pri_Is_Suspended=1)) == ["Suspended"]
    vazio = _row("X", "D", Sec_Synch_Health=None, Sec_Synch_State="", Sec_Is_Suspended=None)
    assert not is_unhealthy(vazio), "o lado vazio de uma replica e' normal, nao avaria"


def test_dados_vazios_ou_indisponiveis():
    assert classify({}) == [] and classify(None) == []
    assert distinct_instances(None) == set()
    assert by_env_distinct_instances(None) == {"PRD": 0, "QLT": 0, "TST": 0, "Undefined": 0}


def test_case_sql_coerente_com_where():
    for am in (False, True):
        w, c = unhealthy_where("s", am), problem_reasons_case("s", am)
        for frag in ("Pri_Synch_Health", "Sec_Is_Suspended", "Pri_Synch_State"):
            assert frag in w and frag in c
        assert ("ASYNCHRONOUS_COMMIT" in c) == am


def test_contrato_os_tres_sitios_usam_a_regra_unica():
    helpers = (ROOT / "api" / "routers" / "intelligence" / "helpers.py").read_text(encoding="utf-8")
    kpis = (ROOT / "api" / "routers" / "intelligence_kpis.py").read_text(encoding="utf-8")
    portal = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
    assert helpers.count("_ao_where(") >= 2 and "_ao_by_env(" in helpers
    assert kpis.count("_ao_where(") >= 1 and "_ao_reasons(" in kpis
    velho = "NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '')"
    assert velho not in kpis, "a modal voltou a ter a regra inline"
    assert "kpiType === 'always-on'" in portal and "kpi_modal.database_s" in portal
'''


def main() -> None:
    # 1. modulo
    if RULES.exists():
        if MARK not in RULES.read_text(encoding="utf-8", errors="replace"):
            sys.exit("ABORT: alwayson_rules.py existe sem marcador.")
        print("Ja existe: alwayson_rules.py")
    else:
        compile(RULES_SRC, str(RULES), "exec")
        RULES.write_text(RULES_SRC, encoding="utf-8", newline="\n")
        print("OK: api/routers/intelligence/alwayson_rules.py")

    # 2. helpers
    h = HELPERS.read_text(encoding="utf-8")
    if MARK in h:
        print("Ja aplicado: helpers.py")
    else:
        h = rep(h, H_IMPORT_ANCHOR, H_IMPORT_NEW, "helpers import")
        h = rep(h, H_FILTER_OLD, H_FILTER_NEW, "helpers count")
        h = rep(h, H_LIST_OLD, H_LIST_NEW, "helpers lista")
        h = rep(h, H_BYENV_OLD, H_BYENV_NEW, "helpers by_env")
        compile(h, str(HELPERS), "exec")
        HELPERS.write_text(h, encoding="utf-8", newline="\n")
        print("OK: api/routers/intelligence/helpers.py")

    # 3. modal
    k = KPIS.read_text(encoding="utf-8")
    if MARK in k:
        print("Ja aplicado: intelligence_kpis.py")
    else:
        k = rep(k, K_PRE_OLD, K_PRE_NEW, "kpis import")
        k = rep(k, K_OLD, K_NEW, "kpis query")
        compile(k, str(KPIS), "exec")
        KPIS.write_text(k, encoding="utf-8", newline="\n")
        print("OK: api/routers/intelligence_kpis.py")

    # 4. portal
    p = PORTAL.read_text(encoding="utf-8")
    if MARK in p:
        print("Ja aplicado: portal")
    else:
        p = rep(p, P_OLD, P_NEW, "portal summary")
        PORTAL.write_text(p, encoding="utf-8", newline="\n")
        print("OK: templates/watcherdb_portal.html")

    # 5. i18n
    for loc, texto in LOCALES.items():
        f = ROOT / "static" / "i18n" / f"{loc}.json"
        t = f.read_text(encoding="utf-8")
        if '"database_s"' in t:
            print(f"Ja existe: {loc}.json"); continue
        t = rep(t, I18N_ANCHOR[loc], I18N_ANCHOR[loc] + f'    "database_s": "{texto}",\n', f"i18n {loc}")
        json.loads(t)
        f.write_text(t, encoding="utf-8", newline="\n")
        print(f"OK: static/i18n/{loc}.json (+kpi_modal.database_s)")

    # 6. testes
    if TEST.exists():
        print("Ja existe: teste")
    else:
        compile(TEST_SRC, str(TEST), "exec")
        TEST.write_text(TEST_SRC, encoding="utf-8", newline="\n")
        print("OK: tests/unit/test_alwayson_rules_20260911.py")
    print("Proximo: pwsh docs/context/ALWAYSON_REGRA_UNICA_PASSO2_commit.ps1")


if __name__ == "__main__":
    main()
