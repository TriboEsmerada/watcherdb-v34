# -*- coding: utf-8 -*-
"""
Plan Analyzer — analise DETERMINISTICA (regras, sem IA) de um plano de execucao
SQL Server (showplan XML), para o layout "Diagnostico" (Performance / SQL Diag).

2026-08-17 (owner): "o plano de execucao deve ser analisado e o produto deve dizer
se o plano executado e' realmente o melhor". Honestidade primeiro: "melhor plano"
NAO e' decidivel em geral — o optimizador nao enumera o espaco. O que este modulo
faz e' (a) extrair do XML factos deterministicos (missing indexes, warnings,
custo por operador, HEAP scans, sorts/hash caros, paralelismo, memory grant) e
(b) sinais heuristicos marcados como tal (mesma tabela lida N vezes, funcoes em
predicados, lookups em massa). A comparacao com OUTROS planos observados (mesmo
query_hash no plan cache / Query Store) vive no endpoint (api/routers/queries/
plan_analysis.py) — este modulo e' puro Python, sem BD.

Seguranca do XML (defusedxml NAO esta nas deps; xml.etree e' vulneravel a
expansao de entidades internas): rejeitar <!DOCTYPE / <!ENTITY, cap de bytes,
cap de nos. Parse fora do event loop (o endpoint usa anyio.to_thread).

Tier: Standard (regras deterministicas; so' "AI-powered" e' Pro — FEATURE_MATRIX).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

NS = "http://schemas.microsoft.com/sqlserver/2004/07/showplan"
_N = "{%s}" % NS

MAX_XML_BYTES = 5 * 1024 * 1024      # 5 MB
MAX_NODES = 20000                    # nos XML totais (RelOp << isto)
MAX_RELOPS = 2000                    # operadores analisados


class PlanParseError(ValueError):
    pass


@dataclass
class OperatorInfo:
    node_id: str
    physical_op: str
    logical_op: str
    est_rows: float
    est_subtree_cost: float
    cost_pct: float
    actual_rows: Optional[float] = None
    obj: str = ""                    # [db].[schema].[table].[index]
    index_kind: str = ""             # Clustered / NonClustered / Heap / ViewClustered / ...
    parallel: bool = False
    warnings: List[str] = field(default_factory=list)


@dataclass
class ParsedPlan:
    plan_type: str = "estimated"     # estimated | actual
    statement_count: int = 0
    total_subtree_cost: float = 0.0
    dop: int = 0
    memory_grant_kb: Optional[int] = None
    memory_required_kb: Optional[int] = None
    memory_max_used_kb: Optional[int] = None
    cardinality_model: str = ""
    compat_level: str = ""
    optimization_level: str = ""
    early_abort_reason: str = ""
    node_count: int = 0
    relop_count: int = 0
    truncated: bool = False
    operators: List[OperatorInfo] = field(default_factory=list)
    missing_indexes: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)      # plano/statement-level
    tables_read: Dict[str, int] = field(default_factory=dict)          # tabela -> n RelOps
    scalar_udf_predicates: List[str] = field(default_factory=list)
    convert_implicit_predicates: List[str] = field(default_factory=list)
    statement_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["operators"] = [asdict(o) for o in self.operators[:50]]
        return d


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------
def _guard_xml(text: str) -> None:
    if text is None:
        raise PlanParseError("XML vazio")
    if len(text.encode("utf-8", errors="ignore")) > MAX_XML_BYTES:
        raise PlanParseError(f"XML excede {MAX_XML_BYTES // (1024*1024)} MB")
    head = text[:4096].lower()
    if "<!doctype" in head or "<!entity" in text.lower():
        raise PlanParseError("XML com DOCTYPE/ENTITY nao e' aceite (protecao contra expansao de entidades)")
    if "showplan" not in text[:2048].lower() and "ShowPlanXML" not in text[:4096]:
        # ainda tentamos parsear, mas avisamos no resultado
        pass


def _f(v: Optional[str], default: float = 0.0) -> float:
    try:
        return float(v) if v is not None and v != "" else default
    except (TypeError, ValueError):
        return default


def _obj_name(obj_el: Optional[ET.Element]) -> str:
    if obj_el is None:
        return ""
    parts = [obj_el.get("Database"), obj_el.get("Schema"), obj_el.get("Table"), obj_el.get("Index")]
    return ".".join(p for p in parts if p)


def _table_key(obj_el: Optional[ET.Element]) -> str:
    if obj_el is None:
        return ""
    parts = [obj_el.get("Database"), obj_el.get("Schema"), obj_el.get("Table")]
    return ".".join(p for p in parts if p)


def parse_plan_xml(xml_text: str) -> ParsedPlan:
    """Parse deterministico do showplan XML. Levanta PlanParseError se invalido/inseguro."""
    _guard_xml(xml_text)
    # Strip BOM/whitespace
    txt = xml_text.lstrip("﻿ \r\n\t")
    try:
        root = ET.fromstring(txt)
    except ET.ParseError as e:
        raise PlanParseError(f"XML invalido: {e}") from e

    plan = ParsedPlan()
    node_count = 0
    for _ in root.iter():
        node_count += 1
        if node_count > MAX_NODES:
            plan.truncated = True
            break
    plan.node_count = node_count

    stmts = list(root.iter(_N + "StmtSimple")) + list(root.iter(_N + "StmtCursor")) + list(root.iter(_N + "StmtCond"))
    plan.statement_count = len(stmts)
    if stmts:
        s0 = stmts[0]
        plan.total_subtree_cost = _f(s0.get("StatementSubTreeCost"))
        plan.statement_text = (s0.get("StatementText") or "")[:2000]
        plan.optimization_level = s0.get("StatementOptmLevel") or ""
        plan.early_abort_reason = s0.get("StatementOptmEarlyAbortReason") or ""
        plan.cardinality_model = s0.get("CardinalityEstimationModelVersion") or ""
    # se varios statements, custo total = soma
    if len(stmts) > 1:
        plan.total_subtree_cost = sum(_f(s.get("StatementSubTreeCost")) for s in stmts) or plan.total_subtree_cost

    qp = root.find(".//" + _N + "QueryPlan")
    if qp is not None:
        plan.dop = int(_f(qp.get("DegreeOfParallelism"), 0))
        mg = qp.find(_N + "MemoryGrantInfo")
        if mg is not None:
            plan.memory_grant_kb = int(_f(mg.get("GrantedMemory"), 0)) or None
            plan.memory_required_kb = int(_f(mg.get("RequiredMemory"), 0)) or None
            plan.memory_max_used_kb = int(_f(mg.get("MaxUsedMemory"), 0)) or None
        # statement-level warnings
        w = qp.find(_N + "Warnings")
        if w is not None:
            for child in w:
                tag = child.tag.replace(_N, "")
                plan.warnings.append({"type": tag, "detail": dict(child.attrib), "scope": "plan"})
            for k, v in w.attrib.items():
                if v in ("1", "true", "True"):
                    plan.warnings.append({"type": k, "detail": {}, "scope": "plan"})

    # Missing indexes
    for mig in root.iter(_N + "MissingIndexGroup"):
        impact = _f(mig.get("Impact"))
        for mi in mig.findall(_N + "MissingIndex"):
            cols: Dict[str, List[str]] = defaultdict(list)
            for cg in mi.findall(_N + "ColumnGroup"):
                usage = (cg.get("Usage") or "").upper()
                for c in cg.findall(_N + "Column"):
                    cols[usage].append(c.get("Name") or "")
            plan.missing_indexes.append({
                "database": mi.get("Database") or "", "schema": mi.get("Schema") or "", "table": mi.get("Table") or "",
                "impact": round(impact, 1),
                "equality": cols.get("EQUALITY", []), "inequality": cols.get("INEQUALITY", []), "include": cols.get("INCLUDE", []),
            })

    # Operators (RelOp)
    total_cost = plan.total_subtree_cost or 0.0
    relops = list(root.iter(_N + "RelOp"))
    plan.relop_count = len(relops)
    if len(relops) > MAX_RELOPS:
        plan.truncated = True
        relops = relops[:MAX_RELOPS]
    has_runtime = False
    tables = Counter()
    for r in relops:
        est_rows = _f(r.get("EstimateRows"))
        cost = _f(r.get("EstimatedTotalSubtreeCost"))
        # o custo do RelOp raiz == custo total; para %, usar o custo do proprio operador:
        # EstimatedTotalSubtreeCost - soma dos filhos directos
        child_costs = 0.0
        for child in r:
            for cr in child.findall(_N + "RelOp"):
                child_costs += _f(cr.get("EstimatedTotalSubtreeCost"))
        own_cost = max(cost - child_costs, 0.0)
        pct = (own_cost / total_cost * 100.0) if total_cost > 0 else 0.0
        info = OperatorInfo(
            node_id=r.get("NodeId") or "", physical_op=r.get("PhysicalOp") or "", logical_op=r.get("LogicalOp") or "",
            est_rows=est_rows, est_subtree_cost=cost, cost_pct=round(pct, 1),
            parallel=(r.get("Parallel") in ("1", "true", "True")),
        )
        # actual rows
        rti = r.find(_N + "RunTimeInformation")
        if rti is not None:
            has_runtime = True
            act = 0.0
            for rc in rti.findall(_N + "RunTimeCountersPerThread"):
                act += _f(rc.get("ActualRows"))
            info.actual_rows = act
        # object (primeiro Object dentro do operador fisico, nao dos filhos RelOp)
        for child in r:
            tag = child.tag.replace(_N, "")
            if tag in ("IndexScan", "TableScan", "Update", "Insert", "Delete", "Merge", "TableValuedFunction"):
                obj = child.find(_N + "Object")
                info.obj = _obj_name(obj)
                info.index_kind = obj.get("IndexKind") if obj is not None and obj.get("IndexKind") else ("Heap" if tag == "TableScan" else "")
                tk = _table_key(obj)
                if tk and tag in ("IndexScan", "TableScan"):
                    tables[tk] += 1
                # warnings do operador
                w = child.find(_N + "Warnings")
                if w is not None:
                    for wc in w:
                        info.warnings.append(wc.tag.replace(_N, ""))
                    for k, v in w.attrib.items():
                        if v in ("1", "true", "True"):
                            info.warnings.append(k)
                # predicados: funcoes escalares (UDF/Intrinsic sobre coluna) e CONVERT_IMPLICIT
                for pred in child.iter(_N + "ScalarOperator"):
                    so = pred.get("ScalarString") or ""
                    if not so:
                        continue
                    if "CONVERT_IMPLICIT" in so and len(plan.convert_implicit_predicates) < 20:
                        plan.convert_implicit_predicates.append(so[:300])
                    if pred.find(_N + "UserDefinedFunction") is not None and len(plan.scalar_udf_predicates) < 20:
                        plan.scalar_udf_predicates.append(so[:300])
        # warnings directamente no RelOp
        w = r.find(_N + "Warnings")
        if w is not None:
            for wc in w:
                info.warnings.append(wc.tag.replace(_N, ""))
            for k, v in w.attrib.items():
                if v in ("1", "true", "True"):
                    info.warnings.append(k)
        plan.operators.append(info)
    plan.tables_read = dict(tables)
    plan.plan_type = "actual" if has_runtime else "estimated"
    plan.operators.sort(key=lambda o: o.cost_pct, reverse=True)
    return plan


# ---------------------------------------------------------------------------
# Findings (contrato do layout Diagnostico)
# ---------------------------------------------------------------------------
def _cols(lst: List[str]) -> str:
    return ", ".join(lst) if lst else "-"


def _index_ddl_comment(mi: Dict[str, Any]) -> str:
    tbl = ".".join(p for p in (mi.get("database"), mi.get("schema"), mi.get("table")) if p)
    keys = list(mi.get("equality", [])) + list(mi.get("inequality", []))
    name = "IX_" + re.sub(r"[^A-Za-z0-9]", "", (mi.get("table") or "T")) + "_" + "_".join(re.sub(r"[^A-Za-z0-9]", "", k) for k in keys)[:60]
    inc = mi.get("include", [])
    ddl = f"-- Sugestao do OPTIMIZADOR (plano). Rever selectividade, custo de escrita e indices existentes antes de criar.\n" \
          f"-- CREATE NONCLUSTERED INDEX {name} ON {tbl} ({', '.join(keys) if keys else '?'})" + (f" INCLUDE ({', '.join(inc)})" if inc else "") + ";"
    return ddl


def build_findings(plan: ParsedPlan, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Converte o plano parseado em {summary, problems, recommendations, side_rows}
    no contrato do renderDiagnosisLayout. Textos PT (precedente do modulo Performance).
    Impacto = classe por regra (custo % do plano / tipo); esforco = mapa fixo por tipo.
    """
    ctx = context or {}
    src = "plan_actual" if plan.plan_type == "actual" else "plan_estimated"
    problems: List[Dict[str, Any]] = []
    recs: List[Dict[str, Any]] = []
    pid = 0

    def add_problem(title, evidence, impact, severity, icon, rec=None, confidence="measured", obj=""):
        nonlocal pid
        pid += 1
        p_id = f"plan_p{pid}"
        problems.append({"id": p_id, "title": title, "evidence": evidence, "impact": impact, "icon": icon,
                         "severity": severity, "source": src, "confidence": confidence, "recIds": [], "object_name": obj})
        if rec:
            r_id = f"plan_r{pid}"
            rec.setdefault("id", r_id)
            rec.setdefault("problemIds", []).append(p_id)
            problems[-1]["recIds"].append(rec["id"])
            recs.append(rec)
        return p_id

    # ---- Warnings statement/plan-level ----
    for w in plan.warnings:
        t = w.get("type", "")
        if t == "NoJoinPredicate":
            add_problem("JOIN sem predicado (CROSS JOIN implicito)", "O plano tem um join sem condicao — o optimizador avisa NoJoinPredicate. Multiplicacao de linhas.",
                        "Custo explosivo de CPU/tempdb; provavel bug de query", "critical", "fa-random",
                        rec={"title": "Corrigir a condicao de JOIN em falta", "desc": "Rever a query: virgula entre tabelas / ON em falta.", "impact": "very_high", "effort": "high", "icon": "fa-code"})
        elif t in ("PlanAffectingConvert",):
            det = w.get("detail", {})
            add_problem("Conversao implicita afecta o plano", f"{det.get('ConvertIssue', 'ConvertIssue')}: {det.get('Expression', '')[:200]}",
                        "Impede seek/estimativa correcta (SARGability)", "warning", "fa-exchange-alt",
                        rec={"title": "Alinhar tipos de dados no predicado", "desc": "Parametro/coluna com tipos diferentes; corrigir na aplicacao ou no schema.", "impact": "high", "effort": "high", "icon": "fa-code"})
        elif t == "SpillToTempDb":
            det = w.get("detail", {})
            add_problem("Spill para tempdb", f"Nivel {det.get('SpillLevel', '?')} — memory grant insuficiente para sort/hash.", "I/O em tempdb, latencia", "warning", "fa-hdd",
                        rec={"title": "Rever memory grant / estatisticas", "desc": "Estimativas baixas geram grant insuficiente; actualizar estatisticas e rever a query.", "impact": "high", "effort": "low", "icon": "fa-memory"})
        elif t == "ColumnsWithNoStatistics":
            det = w.get("detail", {})
            add_problem("Colunas sem estatisticas", str(det)[:300], "Estimativas cegas", "warning", "fa-chart-line",
                        rec={"title": "Criar estatisticas nas colunas indicadas", "desc": "-- CREATE STATISTICS ... (comentado; validar auto_create_statistics)", "impact": "medium", "effort": "low", "icon": "fa-chart-line",
                             "sqlCheck": "-- CREATE STATISTICS <nome> ON <tabela> (<coluna>);  -- validar SELECT is_auto_create_stats_on FROM sys.databases"})
        elif t in ("MemoryGrantWarning",):
            det = w.get("detail", {})
            add_problem("Aviso de memory grant", str(det)[:300], "Grant excessivo/insuficiente", "warning", "fa-memory")
        elif t == "UnmatchedIndexes":
            add_problem("Indices filtrados nao utilizaveis (parametrizacao)", "UnmatchedIndexes: indice filtrado existe mas o plano parametrizado nao o pode usar.", "Scan em vez de seek", "info", "fa-filter")

    # ---- Warnings por operador (agregados por tipo) ----
    op_warn = defaultdict(list)
    for o in plan.operators:
        for w in o.warnings:
            op_warn[w].append(o)
    for w, ops in op_warn.items():
        if w in ("NoJoinPredicate", "PlanAffectingConvert", "SpillToTempDb", "ColumnsWithNoStatistics"):
            # ja cobertos acima se statement-level; se so' no operador, cobrir aqui
            if any(pw.get("type") == w for pw in plan.warnings):
                continue
            ex = ", ".join(f"{o.physical_op}#{o.node_id}" for o in ops[:4])
            add_problem(f"Aviso {w} em {len(ops)} operador(es)", ex, "Ver operadores", "warning", "fa-exclamation-triangle")

    # ---- Missing indexes (do plano) ----
    for mi in sorted(plan.missing_indexes, key=lambda m: -m["impact"])[:5]:
        tbl = ".".join(p for p in (mi.get("database"), mi.get("schema"), mi.get("table")) if p)
        conf = ctx.get("dmv_missing_index_confirm", {}).get(tbl)
        sev = "warning" if mi["impact"] >= 80 else "info"
        ev = f"Impacto estimado {mi['impact']:.0f}% · EQ: {_cols(mi['equality'])} · INEQ: {_cols(mi['inequality'])} · INCL: {_cols(mi['include'])}"
        if conf:
            ev += f" · DMV: {conf.get('user_seeks', 0)} seeks, {conf.get('avg_user_impact', 0)}% impacto"
        add_problem(f"Indice em falta em {tbl}", ev, "Scan/lookups onde um seek serviria", sev, "fa-key", obj=tbl,
                    confidence="measured" if conf else "heuristic",
                    rec={"title": f"Avaliar indice em {tbl}", "desc": ("Confirmado pela DMV de missing indexes." if conf else "Sugestao so' do plano — validar com sys.dm_db_missing_index_* e indices existentes."),
                         "impact": "high" if (mi["impact"] >= 80 and conf) else "medium", "effort": "medium", "icon": "fa-key", "sqlCheck": _index_ddl_comment(mi)})

    # ---- HEAP scans ----
    heaps = [o for o in plan.operators if (o.index_kind or "").lower() == "heap" or o.physical_op == "Table Scan"]
    if heaps:
        top = heaps[0]
        add_problem(f"Table Scan em HEAP ({len(heaps)})", f"{top.obj or top.physical_op}: ~{top.est_rows:,.0f} linhas estimadas, {top.cost_pct:.0f}% do custo" + (f" (+{len(heaps)-1})" if len(heaps) > 1 else ""),
                    "Leitura completa sem indice clustered", "warning" if top.cost_pct >= 10 else "info", "fa-table", obj=top.obj,
                    rec={"title": "Avaliar indice clustered / cobertura", "desc": "Tabelas HEAP lidas por scan: definir chave clustered ou indice que sirva o predicado.", "impact": "medium", "effort": "medium", "icon": "fa-layer-group"})

    # ---- Operadores caros ----
    for o in plan.operators[:5]:
        if o.cost_pct < 30:
            break
        kind = None
        if o.physical_op in ("Sort",):
            kind = ("Sort caro", "Ordenacao/DISTINCT sobre muitas linhas (memoria/tempdb)", "fa-sort-amount-down")
        elif o.physical_op == "Hash Match":
            kind = (f"Hash Match ({o.logical_op}) caro", "Hash join/aggregate sobre volumes grandes", "fa-project-diagram")
        elif o.physical_op in ("Clustered Index Scan", "Index Scan"):
            kind = ("Scan de indice caro", "Leitura completa do indice; predicado nao-SARGable ou indice inadequado", "fa-search")
        elif o.physical_op in ("Key Lookup", "RID Lookup"):
            kind = ("Lookups em massa", "Indice nao cobre as colunas pedidas", "fa-link")
        elif o.physical_op == "Nested Loops" and o.est_rows > 10000:
            kind = ("Nested Loops com muitas linhas", "Loop sobre entrada grande — estimativa errada ou falta de indice no lado interno", "fa-redo")
        if kind:
            add_problem(kind[0], f"{o.physical_op}#{o.node_id} {o.obj}: {o.cost_pct:.0f}% do custo, ~{o.est_rows:,.0f} linhas" + (f" (actual {o.actual_rows:,.0f})" if o.actual_rows is not None else ""),
                        kind[1], "warning" if o.cost_pct >= 50 else "info", kind[2], confidence="heuristic", obj=o.obj)

    # ---- Estimativa vs actual (so' plano actual) ----
    if plan.plan_type == "actual":
        skew = [o for o in plan.operators if o.actual_rows is not None and o.est_rows > 0 and (o.actual_rows / o.est_rows >= 10 or (o.actual_rows > 0 and o.est_rows / o.actual_rows >= 10))]
        if skew:
            o = skew[0]
            add_problem(f"Estimativa vs actual desviada ({len(skew)} operadores)", f"{o.physical_op}#{o.node_id} {o.obj}: est {o.est_rows:,.0f} vs actual {o.actual_rows:,.0f}",
                        "Estatisticas desactualizadas ou parameter sniffing", "warning", "fa-balance-scale",
                        rec={"title": "Actualizar estatisticas / rever sniffing", "desc": "-- UPDATE STATISTICS <tabela> WITH FULLSCAN (comentado). Se persistir, OPTION(RECOMPILE)/OPTIMIZE FOR.", "impact": "high", "effort": "low", "icon": "fa-sync-alt",
                             "sqlCheck": "-- UPDATE STATISTICS <tabela> WITH FULLSCAN;\n-- verificar: SELECT name, STATS_DATE(object_id, stats_id) FROM sys.stats WHERE object_id = OBJECT_ID('<tabela>');"})

    # ---- Mesma tabela lida N vezes (CTE re-expandida / self-join) — heuristica ----
    multi = [(tk, n) for tk, n in plan.tables_read.items() if n >= 3]
    if multi:
        multi.sort(key=lambda x: -x[1])
        tk, n = multi[0]
        add_problem(f"Mesma tabela lida {n}x no plano", f"{tk} aparece em {n} operadores de leitura" + (f"; +{len(multi)-1} tabelas" if len(multi) > 1 else ""),
                    "CTE expandida em cada referencia / UNIONs repetidos", "info", "fa-clone", confidence="heuristic", obj=tk,
                    rec={"title": "Materializar em #temp ou reescrever", "desc": "Se for CTE referenciada varias vezes, materializar uma vez (#temp) evita reprocessamento.", "impact": "medium", "effort": "high", "icon": "fa-code"})

    # ---- Funcoes / conversoes em predicados — heuristica ----
    if plan.scalar_udf_predicates:
        add_problem("Funcao escalar (UDF) em predicado", plan.scalar_udf_predicates[0][:200], "Avaliacao linha-a-linha, impede seek", "warning", "fa-superscript", confidence="heuristic",
                    rec={"title": "Remover UDF do predicado", "desc": "Inline da logica ou coluna computada persistida.", "impact": "high", "effort": "high", "icon": "fa-code"})
    if plan.convert_implicit_predicates and not any(w.get("type") == "PlanAffectingConvert" for w in plan.warnings):
        add_problem("CONVERT_IMPLICIT em predicado", plan.convert_implicit_predicates[0][:200], "Possivel perda de SARGability", "info", "fa-exchange-alt", confidence="heuristic")

    # ---- Paralelismo / memory grant (informativo) ----
    side_rows = [
        {"k": "Tipo de plano", "v": "Actual (com runtime)" if plan.plan_type == "actual" else "Estimado (sem actual rows/spills)"},
        {"k": "Custo estimado total", "v": f"{plan.total_subtree_cost:,.2f}"},
        {"k": "Operadores", "v": str(plan.relop_count) + (" (truncado)" if plan.truncated else "")},
        {"k": "Statements", "v": str(plan.statement_count)},
    ]
    if plan.dop:
        side_rows.append({"k": "Grau de paralelismo", "v": str(plan.dop)})
    if plan.memory_grant_kb:
        side_rows.append({"k": "Memory grant (KB)", "v": f"{plan.memory_grant_kb:,}" + (f" / usado {plan.memory_max_used_kb:,}" if plan.memory_max_used_kb else "")})
    if plan.optimization_level:
        side_rows.append({"k": "Optimizacao", "v": plan.optimization_level + (f" ({plan.early_abort_reason})" if plan.early_abort_reason else "")})
    top_ops = ", ".join(f"{o.physical_op} {o.cost_pct:.0f}%" for o in plan.operators[:4])
    if top_ops:
        side_rows.append({"k": "Principais operadores", "v": top_ops})

    crit = sum(1 for p in problems if p["severity"] == "critical")
    warn = sum(1 for p in problems if p["severity"] == "warning")
    summary = [
        {"label": "Custo estimado (plano)", "value": f"{plan.total_subtree_cost:,.1f}", "sub": "unidades do optimizador", "icon": "fa-tachometer-alt", "severity": "warning" if plan.total_subtree_cost >= 100 else "info"},
        {"label": "Achados no plano", "value": len(problems), "sub": f"{crit} criticos · {warn} avisos", "icon": "fa-project-diagram", "severity": "critical" if crit else ("warning" if warn else "ok")},
    ]
    return {"summary": summary, "problems": problems, "recommendations": recs, "side_rows": side_rows,
            "plan_type": plan.plan_type, "total_cost": plan.total_subtree_cost, "truncated": plan.truncated}


def analyze_plan_xml(xml_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Conveniencia: parse + findings. Levanta PlanParseError."""
    plan = parse_plan_xml(xml_text)
    out = build_findings(plan, context)
    out["parsed"] = plan.to_dict()
    return out
