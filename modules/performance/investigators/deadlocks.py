"""DeadlocksInvestigator — leitura de KPI_MSSQL_DEADLOCKS_AGG_VIEW / DET_VIEW.

Le dados pre-agregados em WatcherDB_Intelligence. O collector dedicado
do V1 popula as views a partir do system_health ring buffer, sem pegada
nos servidores monitorizados. Janela: 24h.
"""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from modules.performance.base import (
    InvestigationResult,
    InvestigationStep,
    PerformanceInvestigator,
    Recommendation,
    EstimatedImpact,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    SEVERITY_OK,
)

logger = logging.getLogger(__name__)

INTELLIGENCE_SCHEMA = "dbo"


class DeadlocksInvestigator(PerformanceInvestigator):
    investigator_id = "deadlocks"
    display_name_pt = "Deadlocks"
    category = "LOCKS"
    icon = "fa-bolt"
    help_text_pt = (
        "O QUE E: situacao em que duas ou mais transacoes ficam bloqueadas "
        "mutuamente — a transacao A aguarda um recurso detido por B, e B "
        "aguarda um recurso detido por A. O SQL Server detecta o ciclo e "
        "termina uma das transacoes (vitima) via rollback, sinalizando "
        "Error 1205 ao cliente.\n\n"
        "PROBLEMA CAUSADO: operacoes aplicacionais falham de forma "
        "intermitente. Se a aplicacao nao implementa retry, ha perda de "
        "trabalho e potencial inconsistencia funcional. Latencia percebida "
        "pelo utilizador aumenta.\n\n"
        "COMO MEDIMOS: contagem de deadlocks detectados nas ultimas 24h via "
        "system_health ring buffer (leitura passiva, zero pegada nos "
        "servidores). Severity: CRITICAL >= 20 eventos/24h, WARNING 5-19, "
        "INFO 1-4, OK 0."
    )

    def get_steps_schema(self) -> List[Dict[str, str]]:
        return [
            {"id": "step_1_agg",
             "label": "Deadlocks agregados por instancia (24h)",
             "description_pt": (
                 "Contagem total, severidade e databases/objectos afectados, "
                 "obtidos de KPI_MSSQL_DEADLOCKS_AGG_VIEW. Representa o estado "
                 "consolidado da janela de 24h."
             )},
            {"id": "step_2_det",
             "label": "Detalhe por evento (victim, objecto, lock mode)",
             "description_pt": (
                 "Lista dos ate 100 deadlocks mais recentes com victim "
                 "session, database, objecto, indice e modo de lock. Permite "
                 "identificar o objecto especifico em conflito."
             )},
            {"id": "step_3_pattern",
             "label": "Hotspots por database/objecto",
             "description_pt": (
                 "Agregacao dos eventos por database + objecto. Identifica "
                 "concentracao num hotspot (indicador de ordem de acesso "
                 "inconsistente ou falta de indice)."
             )},
            {"id": "step_4_lock_modes",
             "label": "Distribuicao de lock modes",
             "description_pt": (
                 "Contagem por modo de lock (S, X, U, IX, IS). Predominancia "
                 "de X/U aponta para conflitos write-write; predominancia de "
                 "S indica conflitos read-write mitigaveis com RCSI."
             )},
            {"id": "step_5_queries",
             "label": "Queries em conflito (extraidas do deadlock graph)",
             "description_pt": (
                 "Processos envolvidos em cada um dos deadlocks mais recentes, "
                 "com o texto SQL (inputbuf) que cada sessao tentava executar. "
                 "Permite identificar exactamente que query bloqueou que query. "
                 "Dados extraidos do XML Deadlock_Graph armazenado em "
                 "KPI_MSSQL_DEADLOCKS_HIST."
             )},
            {"id": "step_6_source",
             "label": "Fonte de captura de deadlocks na instancia",
             "description_pt": (
                 "Verifica directamente na instancia monitorizada a versao do "
                 "SQL Server e que Extended Event sessions contem o evento "
                 "xml_deadlock_report. Em SQL Server 2014+ a sessao system_health "
                 "esta activa por default. Em versoes anteriores, a captura "
                 "depende de uma sessao Extended Event dedicada criada pelo "
                 "utilizador — o WatcherDB detecta-a automaticamente desde que "
                 "inclua o evento xml_deadlock_report."
             )},
        ]

    async def collect(self, instance: str) -> Dict[str, Any]:
        from api.async_db import async_execute_on_intelligence

        data = {"instance": instance, "steps": {}, "_errors": []}
        # Normalizacao: a coluna Instance pode vir com backslash (SQLHOST\I01)
        # ou underscore (SQLHOST_I01). Ate 2026-07-30 filtrava-se com
        # UPPER(REPLACE(coluna, CHAR(92), '_')) dos dois lados -- funcao sobre a
        # coluna, logo predicado nao-SARGable: o optimizador deitava fora o seek
        # e fazia scan do clustered.
        #
        # Medido na base viva a 2026-07-30:
        #   - PK_KPI_MSSQL_DEADLOCKS_STG = (Instance, Deadlock_Id, Deadlock_Time)
        #     e PK_KPI_DEADLOCKS_HIST = (Instance_Name, Deadlock_Time, Victim_SPID)
        #     -- as duas lideram pela coluna do filtro;
        #   - KPI_MSSQL_DEADLOCKS_HIST tem 7.602 linhas em 94,4 MB (o XML do
        #     Deadlock_Graph), logo cada scan lia 94 MB para devolver TOP 10;
        #   - colacao da BD e' SQL_Latin1_General_CP1_CI_AS, portanto o UPPER
        #     era redundante;
        #   - nao existe um unico valor com backslash em nenhuma das duas tabelas
        #     (29 instancias distintas na HIST, 14 na STG) -- a normalizacao
        #     defendia-se de um formato que ali nao ocorre.
        #
        # Passamos as duas variantes como literais e usamos igualdade: seek em vez
        # de scan, e continua a cobrir os dois formatos se a origem vier a mudar.
        # A variante inversa (_ para \) e' inofensiva mesmo em nomes com varios
        # underscores: no pior caso e' um literal que nao corresponde a nada, e o
        # nome original esta sempre no conjunto.
        _variantes = {instance, instance.replace("\\", "_"), instance.replace("_", "\\")}
        in_list = ", ".join("'" + v.replace("'", "''") + "'" for v in sorted(_variantes))

        # --- Step 1: agregado 24h ---
        # Colunas reais da view: Instance, Env, Deadlock_Count, Last_Deadlock,
        # Databases_Affected, Objects_Affected, State, Severity (8 cols).
        t0 = time.time()
        try:
            q1 = f"""
            SELECT Instance, Env, Deadlock_Count, State, Severity,
                   Last_Deadlock, Databases_Affected, Objects_Affected
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DEADLOCKS_AGG_VIEW WITH (NOLOCK)
            WHERE Instance IN ({in_list})
            """
            rows = await async_execute_on_intelligence(q1) or []
            logger.info("[Deadlocks] step_1_agg instance=%s -> %d rows", instance, len(rows))
            data["steps"]["step_1_agg"] = {
                "data": rows,
                "duration_ms": int((time.time() - t0) * 1000),
                "query": q1,
            }
        except Exception as e:
            data["_errors"].append(("step_1_agg", str(e)))
            data["steps"]["step_1_agg"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # --- Step 2: detalhe dos deadlocks ---
        t0 = time.time()
        try:
            q2 = f"""
            SELECT TOP 100 Instance, Env, Deadlock_Time, Victim_Session_Id,
                   Database_Name, Object_Name, Index_Name, Lock_Mode,
                   Resource_Type, Minutes_Ago, Has_Graph, Update_TS
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DEADLOCKS_DET_VIEW WITH (NOLOCK)
            WHERE Instance IN ({in_list})
            ORDER BY Deadlock_Time DESC
            """
            rows = await async_execute_on_intelligence(q2) or []
            logger.info("[Deadlocks] step_2_det instance=%s -> %d rows", instance, len(rows))
            data["steps"]["step_2_det"] = {
                "data": rows,
                "duration_ms": int((time.time() - t0) * 1000),
                "query": q2,
            }
        except Exception as e:
            data["_errors"].append(("step_2_det", str(e)))
            data["steps"]["step_2_det"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # --- Step 5: queries em conflito (parse do Deadlock_Graph XML) ---
        # Lemos ate 10 deadlocks mais recentes da HIST e extraimos os processos
        # envolvidos com o texto SQL (inputbuf). Parse em Python com
        # xml.etree.ElementTree (biblioteca standard, sem dependencias).
        t0 = time.time()
        try:
            q5 = f"""
            SELECT TOP 10 Instance_Name, Deadlock_Time,
                   CAST(Deadlock_Graph AS NVARCHAR(MAX)) AS Deadlock_Graph_Xml,
                   Resource_Type
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DEADLOCKS_HIST WITH (NOLOCK)
            WHERE Instance_Name IN ({in_list})
              AND Deadlock_Graph IS NOT NULL
            ORDER BY Deadlock_Time DESC
            """
            hist_rows = await async_execute_on_intelligence(q5) or []
            queries_rows: List[Dict[str, Any]] = []
            for hr in hist_rows:
                dt = hr.get("Deadlock_Time")
                xml_txt = hr.get("Deadlock_Graph_Xml") or ""
                processes = _parse_deadlock_graph(xml_txt)
                for p in processes:
                    p["Deadlock_Time"] = dt
                    queries_rows.append(p)
            logger.info(
                "[Deadlocks] step_5_queries instance=%s -> %d processos de %d deadlocks",
                instance, len(queries_rows), len(hist_rows),
            )
            data["steps"]["step_5_queries"] = {
                "data": queries_rows,
                "duration_ms": int((time.time() - t0) * 1000),
                "query": q5,
            }
        except Exception as e:
            data["_errors"].append(("step_5_queries", str(e)))
            data["steps"]["step_5_queries"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # --- Step 6: fonte de captura de deadlocks (verificacao na instancia) ---
        # Vai directamente a instancia monitorizada para aferir:
        #   1. Versao do SQL Server (major >= 12 indica 2014+).
        #   2. Que XE sessions contem xml_deadlock_report e estao running.
        # Lógica hibrida: prefere system_health quando disponivel; cai para
        # XE dedicado criado pelo utilizador se existir.
        t0 = time.time()
        try:
            from api.async_db import async_execute_on_server
            q6_version = """
            SELECT
                CAST(SERVERPROPERTY('ProductVersion') AS VARCHAR(50)) AS product_version,
                CAST(SERVERPROPERTY('ProductMajorVersion') AS INT)    AS major_version,
                CAST(SERVERPROPERTY('Edition') AS VARCHAR(100))       AS edition,
                CAST(SERVERPROPERTY('ProductLevel') AS VARCHAR(20))   AS product_level
            """
            q6_xe = """
            SELECT s.name AS session_name,
                   CAST(s.startup_state AS INT) AS startup_state_auto,
                   CASE WHEN rs.name IS NOT NULL THEN 1 ELSE 0 END AS is_running
            FROM sys.server_event_sessions s
            LEFT JOIN sys.dm_xe_sessions rs ON rs.name = s.name
            INNER JOIN sys.server_event_session_events e ON e.event_session_id = s.event_session_id
            WHERE e.name = 'xml_deadlock_report'
            GROUP BY s.name, s.startup_state, rs.name
            """
            ver_rows = await async_execute_on_server(instance, q6_version) or []
            xe_rows = await async_execute_on_server(instance, q6_xe) or []

            ver = ver_rows[0] if ver_rows else {}
            major = int(ver.get("major_version") or 0)
            version_str = ver.get("product_version") or "?"
            edition = ver.get("edition") or "?"

            # Classificar sessoes encontradas
            running_system_health = next(
                (x for x in xe_rows
                 if (x.get("session_name") or "").lower() == "system_health"
                 and int(x.get("is_running") or 0) == 1),
                None,
            )
            running_custom = [
                x for x in xe_rows
                if (x.get("session_name") or "").lower() != "system_health"
                and int(x.get("is_running") or 0) == 1
            ]

            # Decidir fonte + recomendacao
            if running_system_health:
                if major >= 12:
                    source = "system_health"
                    status_pt = (
                        f"Fonte activa: sessao Extended Event system_health (default em "
                        f"SQL Server 2014+). Versao detectada: {version_str}. "
                        f"Captura de deadlocks garantida."
                    )
                    recommendation_pt = "Nenhuma accao necessaria."
                else:
                    source = "system_health_legacy"
                    status_pt = (
                        f"Sessao system_health detectada e running, mas a versao "
                        f"{version_str} (major {major}) e anterior a 2014. O evento "
                        f"xml_deadlock_report pode nao estar presente por default."
                    )
                    recommendation_pt = (
                        "Validar em SSMS se system_health inclui xml_deadlock_report. "
                        "Caso nao inclua, criar Extended Event dedicado com esse evento. "
                        "O WatcherDB reconhece-o automaticamente."
                    )
            elif running_custom:
                custom_names = ", ".join(x.get("session_name") or "?" for x in running_custom)
                source = "custom_xe"
                status_pt = (
                    f"Fonte activa: Extended Event custom ({custom_names}) criada pelo "
                    f"utilizador. Versao detectada: {version_str}. Captura operacional."
                )
                recommendation_pt = (
                    "Manter a sessao Extended Event activa. O WatcherDB le "
                    "xml_deadlock_report independentemente do nome da sessao."
                )
            else:
                source = "none"
                if major >= 12:
                    status_pt = (
                        f"Versao {version_str} suporta system_health por default, mas "
                        f"nenhuma sessao Extended Event com xml_deadlock_report foi "
                        f"encontrada em estado running. Deadlocks nao estao a ser "
                        f"capturados."
                    )
                    recommendation_pt = (
                        "Verificar se o system_health foi desactivado manualmente. "
                        "Reactivar: ALTER EVENT SESSION system_health ON SERVER STATE = START;"
                    )
                else:
                    status_pt = (
                        f"Versao {version_str} (major {major}) e anterior a SQL Server "
                        f"2014. Nesta versao, o system_health pode nao incluir "
                        f"xml_deadlock_report por default e nenhuma sessao Extended "
                        f"Event dedicada foi detectada."
                    )
                    recommendation_pt = (
                        "Criar Extended Event dedicado com o evento xml_deadlock_report "
                        "apontado para ring_buffer ou event_file. O WatcherDB deteca "
                        "automaticamente e passa a analisar o deadlock graph."
                    )

            step_6_data = [{
                "product_version": version_str,
                "major_version": major,
                "edition": edition,
                "product_level": ver.get("product_level") or "?",
                "system_health_running": bool(running_system_health),
                "custom_xe_sessions": ", ".join(
                    x.get("session_name") for x in running_custom
                ) or "",
                "total_sessions_with_deadlock_event": len(xe_rows),
                "source_detected": source,
                "status_pt": status_pt,
                "recommendation_pt": recommendation_pt,
            }]
            logger.info(
                "[Deadlocks] step_6_source instance=%s version=%s major=%d source=%s",
                instance, version_str, major, source,
            )
            data["steps"]["step_6_source"] = {
                "data": step_6_data,
                "duration_ms": int((time.time() - t0) * 1000),
                "query": q6_version + "\n-- +\n" + q6_xe,
            }
        except Exception as e:
            # Graceful: servidor offline, sem permissoes VIEW SERVER STATE, etc.
            data["_errors"].append(("step_6_source", str(e)))
            data["steps"]["step_6_source"] = {
                "data": [],
                "error": str(e),
                "duration_ms": int((time.time() - t0) * 1000),
            }

        return data

    async def analyze(self, raw: Dict[str, Any], instance: str) -> InvestigationResult:
        agg_rows = raw["steps"].get("step_1_agg", {}).get("data", []) or []
        det_rows = raw["steps"].get("step_2_det", {}).get("data", []) or []

        # --- Calcular severity + counts ---
        # Prioridade 1: AGG_VIEW (fonte canonica da janela 24h).
        # Prioridade 2: DET_VIEW (fallback quando AGG vazia mas DET tem linhas —
        # acontece se as views tiverem formatos diferentes de Instance e o
        # REPLACE do Fix 7 cobrir uma mas nao a outra).
        total_count = 0
        severity = SEVERITY_OK
        databases_affected = 0
        objects_affected = 0
        agg_source = "empty"

        if agg_rows:
            row = agg_rows[0]
            total_count = int(row.get("Deadlock_Count") or 0)
            databases_affected = int(row.get("Databases_Affected") or 0)
            objects_affected = int(row.get("Objects_Affected") or 0)
            state_raw = row.get("State")
            sev_raw = row.get("Severity")
            severity = _resolve_severity(state_raw, sev_raw)
            agg_source = "agg_view"
        elif det_rows:
            # Fallback: recalcular do DET quando AGG nao retornou.
            total_count = len(det_rows)
            databases_affected = len({d.get("Database_Name") for d in det_rows if d.get("Database_Name")})
            objects_affected = len({d.get("Object_Name") for d in det_rows if d.get("Object_Name")})
            if total_count >= 20:
                severity = SEVERITY_CRITICAL
            elif total_count >= 5:
                severity = SEVERITY_WARNING
            elif total_count >= 1:
                severity = SEVERITY_INFO
            agg_source = "synthesized_from_det"
            logger.info(
                "[Deadlocks] AGG vazia para %s — fallback DET: total=%d, dbs=%d, objs=%d, sev=%s",
                instance, total_count, databases_affected, objects_affected, severity,
            )

        # --- Pattern analysis: agrupar por database/object ---
        pattern_map: Dict[str, int] = {}
        for d in det_rows:
            key = f"{d.get('Database_Name', '?')}.{d.get('Object_Name', '?')}"
            pattern_map[key] = pattern_map.get(key, 0) + 1
        top_hotspots = sorted(pattern_map.items(), key=lambda x: -x[1])[:5]

        # --- Lock mode distribution ---
        lock_modes: Dict[str, int] = {}
        for d in det_rows:
            lm = str(d.get("Lock_Mode") or "UNKNOWN")
            lock_modes[lm] = lock_modes.get(lm, 0) + 1

        # --- Root cause ---
        root_cause_pt = "Sem padrao de concentracao identificado."
        confidence = 40.0
        if top_hotspots:
            hotspot, hcount = top_hotspots[0]
            pct = (hcount / len(det_rows) * 100) if det_rows else 0
            if pct > 50:
                root_cause_pt = (
                    f"Hotspot identificado: {hotspot} concentra {hcount} deadlocks "
                    f"({pct:.0f}% do total). Provavel ordem de acesso inconsistente "
                    f"entre transacoes ou ausencia de indice que forca escalation de lock."
                )
                confidence = 75.0
            else:
                root_cause_pt = (
                    f"Deadlocks distribuidos por {len(pattern_map)} objectos distintos. "
                    f"Objecto mais afectado: {hotspot} ({hcount} eventos)."
                )
                confidence = 55.0

        # --- Recommendations ---
        recs: List[Recommendation] = []

        # Prioridade absoluta: se a fonte de captura nao esta disponivel, o
        # diagnostico fica limitado. Recomendar CREATE EVENT SESSION dedicada
        # antes de qualquer outra accao — sem fonte, deadlocks futuros nao
        # sao capturados para analise.
        source_row = (raw["steps"].get("step_6_source", {}).get("data") or [{}])[0]
        source_detected = source_row.get("source_detected", "")
        if source_detected in ("none", "system_health_legacy"):
            major = int(source_row.get("major_version") or 0)
            version_str = source_row.get("product_version") or "?"
            rationale = (
                f"SQL Server {version_str} (major {major}) nao tem system_health com "
                f"xml_deadlock_report disponivel. "
                if major and major < 12
                else "Nenhuma sessao Extended Event activa a capturar xml_deadlock_report "
                     "foi detectada na instancia. "
            )
            recs.append(Recommendation(
                action="Criar sessao Extended Event dedicada para captura de deadlocks",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt=(
                    rationale
                    + "Sem esta sessao, o WatcherDB nao consegue extrair o deadlock graph "
                    + "(queries victim/survivor, objectos envolvidos, lock modes). O "
                    + "script abaixo cria e arranca a sessao com ring buffer em memoria "
                    + "(zero impacto em disco, latencia de dispatch <= 5s). O WatcherDB "
                    + "deteca a sessao automaticamente no proximo refresh."
                ),
                estimated_impact_pct=90.0,
                requires_approval=True,
                sql_script=(
                    "CREATE EVENT SESSION [WatcherDB_Deadlocks] ON SERVER\n"
                    "  ADD EVENT sqlserver.xml_deadlock_report\n"
                    "  ADD TARGET package0.ring_buffer (SET MAX_MEMORY = 4096)\n"
                    "  WITH (STARTUP_STATE = ON, MAX_DISPATCH_LATENCY = 5 SECONDS);\n"
                    "ALTER EVENT SESSION [WatcherDB_Deadlocks] ON SERVER STATE = START;"
                ),
                risk_if_ignored_pt=(
                    "Diagnostico permanece limitado a metricas agregadas (contagem, "
                    "severidade). Sem o graph nao e possivel identificar victim/survivor, "
                    "SQL envolvido nem objectos exactos em conflito."
                ),
            ))

        if severity in (SEVERITY_CRITICAL, SEVERITY_WARNING):
            recs.append(Recommendation(
                action="Uniformizar ordem de acesso a objectos entre transacoes",
                effort='high',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt=(
                    "Garantir que todas as transacoes adquirem locks nos mesmos "
                    "objectos pela mesma ordem. Ver runbook para analise detalhada."
                ),
                estimated_impact_pct=60.0,
                requires_approval=False,
                risk_if_ignored_pt="Deadlocks continuam a provocar rollbacks e Error 1205 nas aplicacoes.",
            ))
            if top_hotspots:
                hs, _ = top_hotspots[0]
                recs.append(Recommendation(
                    action=f"Rever estrategia de indices em {hs}",
                    effort='medium',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                    description_pt=(
                        f"Objecto {hs} concentra eventos de deadlock. Analisar "
                        f"missing indexes e seletividade dos acessos para reduzir "
                        f"escalation de lock."
                    ),
                    estimated_impact_pct=50.0,
                    requires_approval=True,
                    risk_if_ignored_pt="Frequencia tende a aumentar com carga.",
                ))
        if severity == SEVERITY_CRITICAL:
            recs.append(Recommendation(
                action="Avaliar Read Committed Snapshot Isolation (RCSI)",
                effort='medium',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt=(
                    "RCSI elimina locks de leitura usando versionamento em tempdb. "
                    "Reduz drasticamente conflitos read-write. Validar capacidade "
                    "de tempdb e testar em QLT/TST antes de aplicar em PRD."
                ),
                estimated_impact_pct=70.0,
                requires_approval=True,
                sql_script="ALTER DATABASE [<db>] SET READ_COMMITTED_SNAPSHOT ON;",
                risk_if_ignored_pt="Aumenta consumo de tempdb. Validar capacidade antes.",
            ))

        # --- Executive summary com nomes reais de DBs e objectos (Fix 11) ---
        db_names = sorted({d.get("Database_Name") for d in det_rows if d.get("Database_Name")})
        obj_names_raw = sorted({d.get("Object_Name") for d in det_rows if d.get("Object_Name")})

        def _short_obj(name):
            if not name:
                return ""
            parts = str(name).split(".")
            return parts[-1] if parts else str(name)

        obj_short = [_short_obj(o) for o in obj_names_raw]

        if len(db_names) == 0:
            dbs_label = f"{databases_affected} DBs" if databases_affected else ""
        elif len(db_names) == 1:
            dbs_label = f"DB {db_names[0]}"
        elif len(db_names) <= 3:
            dbs_label = f"DBs: {', '.join(db_names)}"
        else:
            dbs_label = f"{len(db_names)} DBs ({', '.join(db_names[:3])} e mais {len(db_names) - 3})"

        if len(obj_short) == 0:
            objs_label = ""
        elif len(obj_short) == 1:
            objs_label = f", objecto {obj_short[0]}"
        elif len(obj_short) <= 3:
            objs_label = f", objectos: {', '.join(obj_short)}"
        else:
            objs_label = (
                f", {len(obj_short)} objectos "
                f"({', '.join(obj_short[:3])} e mais {len(obj_short) - 3})"
            )

        detail_part = f" ({dbs_label}{objs_label})" if dbs_label or objs_label else ""
        exec_summary = (
            f"{total_count} deadlocks detectados em {instance} nas ultimas 24h"
            f"{detail_part}. Severity: {severity}."
        )

        business_impact = (
            "Aplicacoes estao a receber Error 1205 (rollback forcado pelo SQL Server). "
            "Operacoes utilizador podem falhar de forma intermitente e requerem retry "
            "a nivel aplicacional."
            if severity in (SEVERITY_CRITICAL, SEVERITY_WARNING)
            else "Sem impacto de negocio significativo no momento."
        )

        sla_risk = (
            "CRITICAL" if severity == SEVERITY_CRITICAL
            else "HIGH" if severity == SEVERITY_WARNING
            else "LOW"
        )

        # --- Steps estruturados (L4) ---
        steps: List[InvestigationStep] = []
        schemas = self.get_steps_schema()
        for schema in schemas:
            sid = schema["id"]
            step_data = raw["steps"].get(sid, {})

            if sid == "step_3_pattern":
                steps.append(InvestigationStep(
                    id=sid,
                    label=schema["label"],
                    description_pt=schema["description_pt"],
                    data=[{"hotspot": h, "count": c} for h, c in top_hotspots],
                    query_sql="(derivado de step_2_det)",
                    duration_ms=0,
                ))
            elif sid == "step_4_lock_modes":
                steps.append(InvestigationStep(
                    id=sid,
                    label=schema["label"],
                    description_pt=schema["description_pt"],
                    data=[{"lock_mode": k, "count": v} for k, v in sorted(lock_modes.items(), key=lambda x: -x[1])],
                    query_sql="(derivado de step_2_det)",
                    duration_ms=0,
                ))
            elif sid == "step_1_agg":
                # Fix 10: se AGG vazio mas DET tem dados, sintetizar linha derivada
                # para o L4 nao mostrar "Sem dados" em paralelo com L3 a mostrar N.
                agg_data = step_data.get("data", []) or []
                synthesized = False
                if not agg_data and det_rows:
                    deadlock_times = [d.get("Deadlock_Time") for d in det_rows if d.get("Deadlock_Time")]
                    # Schema alinhado com KPI_MSSQL_DEADLOCKS_AGG_VIEW real
                    # (Instance, Env, Deadlock_Count, State, Severity, Last_Deadlock,
                    # Databases_Affected, Objects_Affected).
                    synth_row = {
                        "Instance": instance,
                        "Env": det_rows[0].get("Env", ""),
                        "Deadlock_Count": len(det_rows),
                        "State": severity,
                        "Severity": severity,
                        "Last_Deadlock": max(deadlock_times) if deadlock_times else None,
                        "Databases_Affected": databases_affected,
                        "Objects_Affected": objects_affected,
                        "_source": "synthesized_from_det",
                    }
                    agg_data = [synth_row]
                    synthesized = True

                steps.append(InvestigationStep(
                    id=sid,
                    label=schema["label"] + (" (derivado de DET)" if synthesized else ""),
                    description_pt=(
                        schema["description_pt"]
                        + (" NOTA: AGG_VIEW nao retornou para este filtro; "
                           "linha sintetizada a partir de DET_VIEW para consistencia visual."
                           if synthesized else "")
                    ),
                    data=agg_data,
                    query_sql=(
                        step_data.get("query", "")
                        + ("\n-- (fallback: linha derivada de step_2_det)" if synthesized else "")
                    ),
                    duration_ms=step_data.get("duration_ms", 0),
                    data_available=not step_data.get("error"),
                    error_pt=step_data.get("error"),
                ))
            else:
                steps.append(InvestigationStep(
                    id=sid,
                    label=schema["label"],
                    description_pt=schema["description_pt"],
                    data=step_data.get("data", []),
                    query_sql=step_data.get("query", ""),
                    duration_ms=step_data.get("duration_ms", 0),
                    data_available=not step_data.get("error"),
                    error_pt=step_data.get("error"),
                ))

        return InvestigationResult(
            investigator_id=self.investigator_id,
            instance=instance,
            severity=severity,
            count=total_count,
            subtitle_pt=(
                f"{total_count} deadlocks / {databases_affected} DBs / {objects_affected} objectos"
                if total_count else "Sem deadlocks nas ultimas 24h"
            ),
            executive_summary_pt=exec_summary,
            business_impact_pt=business_impact,
            estimated_impact=EstimatedImpact(
                databases_affected=databases_affected,
                sla_risk=sla_risk,
                duration_min=60 * 24,
            ),
            root_cause_pt=root_cause_pt,
            confidence_score=confidence,
            recommendations=recs,
            steps=steps,
            raw_dmv_data={
                "agg_row": agg_rows[0] if agg_rows else None,
                "agg_source": agg_source,
                "det_count": len(det_rows),
                "databases": db_names,
                "top_hotspots": top_hotspots,
                "lock_modes": lock_modes,
            },
        )


def _parse_deadlock_graph(xml_text: str) -> List[Dict[str, Any]]:
    """Extrai processos envolvidos num deadlock a partir do XML Deadlock_Graph.

    Para cada <process> devolve dict com: SPID, Role (victim/winner), Database,
    Login, Host, Program, Isolation, Lock_Mode, Wait_ms, Proc_Name, Statement,
    SQL_Text (inputbuf). Se o XML e invalido devolve lista vazia e regista warning.
    """
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("[Deadlocks] XML parse failed: %s", e)
        return []

    # Victim process ids: vem em <victim-list><victimProcess id="processXXXX"/>.
    # Pode haver 1 ou mais victims num so deadlock com cycle > 2 processos.
    victim_ids = set()
    for v in root.iter("victimProcess"):
        vid = (v.get("id") or "").strip()
        if vid:
            victim_ids.add(vid)

    processes: List[Dict[str, Any]] = []
    for p in root.iter("process"):
        pid = (p.get("id") or "").strip()
        role = "victim" if pid in victim_ids else "winner"

        inputbuf_el = p.find("inputbuf")
        inputbuf_txt = (inputbuf_el.text or "").strip() if inputbuf_el is not None else ""
        # Truncar inputbuf a 4000 chars para evitar payload JSON excessivo
        if len(inputbuf_txt) > 4000:
            inputbuf_txt = inputbuf_txt[:4000] + " ... [truncado]"

        # Statement actual (ultimo frame do executionStack, tipicamente o mais relevante)
        frames = p.findall(".//frame")
        last_frame = frames[-1] if frames else None
        proc_name = (last_frame.get("procname") or "") if last_frame is not None else ""
        stmt_txt = ""
        if last_frame is not None and last_frame.text:
            stmt_txt = last_frame.text.strip()
            if len(stmt_txt) > 1000:
                stmt_txt = stmt_txt[:1000] + " ... [truncado]"

        processes.append({
            "SPID": p.get("spid") or "",
            "Role": role,
            "Process_Id": p.get("id") or "",
            "Database_Id": p.get("currentdb") or "",
            "Login": p.get("loginname") or "",
            "Host": p.get("hostname") or "",
            "Program": p.get("clientapp") or "",
            "Isolation_Level": p.get("isolationlevel") or "",
            "Lock_Mode": p.get("lockMode") or "",
            "Wait_Ms": int(p.get("waittime") or 0),
            "Transaction_Name": p.get("transactionname") or "",
            "Last_Batch": p.get("lastbatch") or "",
            "Procedure": proc_name,
            "Statement": stmt_txt,
            "SQL_Text": inputbuf_txt,
        })
    return processes


def _resolve_severity(state, severity_numeric) -> str:
    """Prioriza State textual; faz fallback para Severity numerica.

    IMPORTANTE: na KPI_MSSQL_DEADLOCKS_AGG_VIEW a coluna Severity e
    CRESCENTE (1=INFO, 2=WARNING, 3=CRITICAL) — o oposto do que se
    esperaria. O State textual e a fonte fiavel; o fallback numerico
    so e usado quando State esta vazio ou invalido.
    """
    if state is not None and str(state).strip():
        s = str(state).strip().upper()
        if s in (SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO, SEVERITY_OK):
            return s
    if isinstance(severity_numeric, (int, float)):
        # Mapping real da AGG_VIEW: 1=INFO, 2=WARNING, 3=CRITICAL
        return {1: SEVERITY_INFO, 2: SEVERITY_WARNING,
                3: SEVERITY_CRITICAL, 4: SEVERITY_OK}.get(int(severity_numeric), SEVERITY_OK)
    return SEVERITY_OK
