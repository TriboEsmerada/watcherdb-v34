"""
WatcherDB Collection Report - Rastreamento de Execuções de Coleta
=================================================================

Módulo para registrar estatísticas de cada execução de coleta Python,
permitindo análise de tendências e identificação de problemas recorrentes.

Uso:
    report = CollectionReport(collector_name="KPI_Collector")

    for server in servers:
        try:
            # Coleta...
            report.record_server_online(server_id, connection_time_ms, query_time_ms)
            report.record_kpi_collected(server_id, "blocked_sessions", 5)
        except SkipException as e:
            report.record_server_skipped(server_id, str(e))
        except Exception as e:
            report.record_server_error(server_id, str(e))

    # Ao final
    await report.save_to_database(db_connection)
"""

import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
import statistics

logger = logging.getLogger(__name__)


@dataclass
class ServerDetail:
    """Detalhes de coleta para um servidor específico"""
    server_id: str
    status: str  # 'online', 'skipped', 'error'
    skip_reason: Optional[str] = None
    error_message: Optional[str] = None
    connection_time_ms: Optional[float] = None
    query_time_ms: Optional[float] = None
    kpis_collected: Dict[str, int] = field(default_factory=dict)
    swap_result: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CollectionReport:
    """
    Acumula estatísticas durante uma execução de coleta.
    Salva no banco ao final para análise histórica.
    """
    collector_name: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    # Contadores
    servers_total: int = 0
    servers_online: int = 0
    servers_skipped: int = 0
    servers_error: int = 0

    # Detalhes por servidor
    server_details: List[ServerDetail] = field(default_factory=list)

    # KPIs coletados (agregado)
    kpis_summary: Dict[str, int] = field(default_factory=dict)

    # Performance
    connection_times: List[float] = field(default_factory=list)
    query_times: List[float] = field(default_factory=list)

    # SWAP results
    swap_success: int = 0
    swap_failed: int = 0
    swap_skipped: int = 0

    # Erros (para JSON)
    errors: List[Dict[str, str]] = field(default_factory=list)
    skip_reasons: Dict[str, int] = field(default_factory=dict)

    def record_server_online(self, server_id: str, connection_time_ms: float = 0,
                             query_time_ms: float = 0):
        """Registra servidor online com sucesso"""
        self.servers_online += 1
        self.servers_total += 1

        if connection_time_ms > 0:
            self.connection_times.append(connection_time_ms)
        if query_time_ms > 0:
            self.query_times.append(query_time_ms)

        detail = ServerDetail(
            server_id=server_id,
            status='online',
            connection_time_ms=connection_time_ms,
            query_time_ms=query_time_ms
        )
        self.server_details.append(detail)
        logger.debug(f"[CollectionReport] Server online: {server_id}")

    def record_server_skipped(self, server_id: str, reason: str):
        """Registra servidor que foi pulado (skip)"""
        self.servers_skipped += 1
        self.servers_total += 1

        # Contabilizar razões de skip
        if reason not in self.skip_reasons:
            self.skip_reasons[reason] = 0
        self.skip_reasons[reason] += 1

        detail = ServerDetail(
            server_id=server_id,
            status='skipped',
            skip_reason=reason
        )
        self.server_details.append(detail)
        logger.debug(f"[CollectionReport] Server skipped: {server_id} - {reason}")

    def record_server_error(self, server_id: str, error_message: str):
        """Registra servidor com erro"""
        self.servers_error += 1
        self.servers_total += 1

        self.errors.append({
            'server_id': server_id,
            'error': error_message[:500],  # Limitar tamanho
            'timestamp': datetime.now().isoformat()
        })

        detail = ServerDetail(
            server_id=server_id,
            status='error',
            error_message=error_message[:500]
        )
        self.server_details.append(detail)
        logger.debug(f"[CollectionReport] Server error: {server_id} - {error_message[:100]}")

    def record_kpi_collected(self, server_id: str, kpi_name: str, count: int = 1):
        """Registra KPI coletado"""
        # Agregado
        if kpi_name not in self.kpis_summary:
            self.kpis_summary[kpi_name] = 0
        self.kpis_summary[kpi_name] += count

        # Por servidor
        for detail in self.server_details:
            if detail.server_id == server_id:
                if kpi_name not in detail.kpis_collected:
                    detail.kpis_collected[kpi_name] = 0
                detail.kpis_collected[kpi_name] += count
                break

    def record_swap_result(self, server_id: str, result: str):
        """Registra resultado do SWAP (success, failed, skipped)"""
        result_lower = result.lower()
        if result_lower == 'success':
            self.swap_success += 1
        elif result_lower == 'failed':
            self.swap_failed += 1
        else:
            self.swap_skipped += 1

        # Atualizar detalhe do servidor
        for detail in self.server_details:
            if detail.server_id == server_id:
                detail.swap_result = result
                break

    def finalize(self):
        """Finaliza o relatório (chamado antes de salvar)"""
        self.end_time = datetime.now()

    def get_duration_seconds(self) -> float:
        """Retorna duração total em segundos"""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0

    def get_avg_connection_time(self) -> float:
        """Retorna tempo médio de conexão em ms"""
        if self.connection_times:
            return round(statistics.mean(self.connection_times), 2)
        return 0

    def get_avg_query_time(self) -> float:
        """Retorna tempo médio de query em ms"""
        if self.query_times:
            return round(statistics.mean(self.query_times), 2)
        return 0

    def get_health_status(self) -> str:
        """Calcula status de saúde da coleta"""
        if self.servers_total == 0:
            return 'NO_DATA'

        error_rate = self.servers_error / self.servers_total
        skip_rate = self.servers_skipped / self.servers_total

        if error_rate > 0.3:  # >30% erro
            return 'CRITICAL'
        elif error_rate > 0.1 or skip_rate > 0.5:  # >10% erro ou >50% skip
            return 'WARNING'
        else:
            return 'HEALTHY'

    def generate_text_report(self) -> str:
        """Gera relatório em texto para logs"""
        self.finalize()

        lines = [
            "=" * 60,
            f"COLLECTION REPORT - {self.collector_name}",
            "=" * 60,
            f"Start: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"End:   {self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else 'N/A'}",
            f"Duration: {self.get_duration_seconds():.1f}s",
            "",
            "SERVERS:",
            f"  Total:   {self.servers_total}",
            f"  Online:  {self.servers_online}",
            f"  Skipped: {self.servers_skipped}",
            f"  Error:   {self.servers_error}",
            f"  Health:  {self.get_health_status()}",
            "",
            "PERFORMANCE:",
            f"  Avg Connection: {self.get_avg_connection_time():.1f}ms",
            f"  Avg Query:      {self.get_avg_query_time():.1f}ms",
        ]

        if self.kpis_summary:
            lines.append("")
            lines.append("KPIs COLLECTED:")
            for kpi, count in sorted(self.kpis_summary.items()):
                lines.append(f"  {kpi}: {count}")

        if self.swap_success + self.swap_failed + self.swap_skipped > 0:
            lines.append("")
            lines.append("SWAP:")
            lines.append(f"  Success: {self.swap_success}")
            lines.append(f"  Failed:  {self.swap_failed}")
            lines.append(f"  Skipped: {self.swap_skipped}")

        if self.skip_reasons:
            lines.append("")
            lines.append("SKIP REASONS:")
            for reason, count in sorted(self.skip_reasons.items(), key=lambda x: -x[1]):
                lines.append(f"  {reason}: {count}")

        if self.errors:
            lines.append("")
            lines.append(f"ERRORS ({len(self.errors)}):")
            for err in self.errors[:5]:  # Mostrar até 5 erros
                lines.append(f"  [{err['server_id']}] {err['error'][:80]}")
            if len(self.errors) > 5:
                lines.append(f"  ... and {len(self.errors) - 5} more")

        lines.append("=" * 60)
        return "\n".join(lines)

    async def save_to_database(self, db_connection, schema: str = "dbo") -> bool:
        """
        Salva o relatório no banco de dados.
        Tabelas: Collection_History e Collection_Server_Details
        """
        self.finalize()

        try:
            # 1. Inserir na Collection_History
            history_sql = f"""
            INSERT INTO {schema}.Collection_History (
                Collector_Name, Start_Time, End_Time, Duration_Seconds,
                Servers_Total, Servers_Online, Servers_Skipped, Servers_Error,
                Total_KPIs_Collected, Avg_Connection_Time_Ms, Avg_Query_Time_Ms,
                Swap_Success, Swap_Failed, Swap_Skipped,
                Health_Status, Errors_JSON, Skip_Reasons_JSON, KPIs_Summary_JSON
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?
            );
            SELECT SCOPE_IDENTITY() AS Collection_ID;
            """

            total_kpis = sum(self.kpis_summary.values())

            params = [
                self.collector_name,
                self.start_time,
                self.end_time,
                self.get_duration_seconds(),
                self.servers_total,
                self.servers_online,
                self.servers_skipped,
                self.servers_error,
                total_kpis,
                self.get_avg_connection_time(),
                self.get_avg_query_time(),
                self.swap_success,
                self.swap_failed,
                self.swap_skipped,
                self.get_health_status(),
                json.dumps(self.errors[:100]),  # Limitar a 100 erros
                json.dumps(self.skip_reasons),
                json.dumps(self.kpis_summary)
            ]

            # Executar insert e obter ID
            result = await db_connection.execute(history_sql, params)
            collection_id = result.get('rows', [{}])[0].get('Collection_ID')

            if not collection_id:
                logger.warning("[CollectionReport] Could not get Collection_ID")
                return False

            # 2. Inserir detalhes por servidor (batch)
            if self.server_details:
                details_sql = f"""
                INSERT INTO {schema}.Collection_Server_Details (
                    Collection_ID, Server_ID, Status, Skip_Reason, Error_Message,
                    Connection_Time_Ms, Query_Time_Ms, KPIs_Collected_JSON, Swap_Result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                for detail in self.server_details:
                    detail_params = [
                        collection_id,
                        detail.server_id,
                        detail.status,
                        detail.skip_reason,
                        detail.error_message,
                        detail.connection_time_ms,
                        detail.query_time_ms,
                        json.dumps(detail.kpis_collected) if detail.kpis_collected else None,
                        detail.swap_result
                    ]
                    await db_connection.execute(details_sql, detail_params)

            logger.info(f"[CollectionReport] Saved to database: Collection_ID={collection_id}, "
                       f"Servers={self.servers_total}, KPIs={total_kpis}")
            return True

        except Exception as e:
            logger.error(f"[CollectionReport] Error saving to database: {e}", exc_info=True)
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário (para API)"""
        self.finalize()
        return {
            'collector_name': self.collector_name,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': self.get_duration_seconds(),
            'servers': {
                'total': self.servers_total,
                'online': self.servers_online,
                'skipped': self.servers_skipped,
                'error': self.servers_error
            },
            'performance': {
                'avg_connection_time_ms': self.get_avg_connection_time(),
                'avg_query_time_ms': self.get_avg_query_time()
            },
            'kpis_summary': self.kpis_summary,
            'swap': {
                'success': self.swap_success,
                'failed': self.swap_failed,
                'skipped': self.swap_skipped
            },
            'health_status': self.get_health_status(),
            'errors_count': len(self.errors),
            'skip_reasons': self.skip_reasons
        }


# Singleton para uso global durante uma coleta
_current_report: Optional[CollectionReport] = None


def start_collection(collector_name: str) -> CollectionReport:
    """Inicia uma nova coleta e retorna o report"""
    global _current_report
    _current_report = CollectionReport(collector_name=collector_name)
    logger.info(f"[CollectionReport] Started collection: {collector_name}")
    return _current_report


def get_current_report() -> Optional[CollectionReport]:
    """Retorna o report atual (se houver)"""
    return _current_report


def end_collection() -> Optional[CollectionReport]:
    """Finaliza a coleta atual e retorna o report"""
    global _current_report
    if _current_report:
        _current_report.finalize()
        report = _current_report
        _current_report = None
        logger.info(f"[CollectionReport] Ended collection: {report.collector_name}")
        return report
    return None
