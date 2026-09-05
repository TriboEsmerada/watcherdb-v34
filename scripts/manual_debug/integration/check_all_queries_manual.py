"""
Script para testar todas as queries do arquivo queries.py
Verifica sintaxe SQL e execução básica
"""

import logging
import sys
from modules.monitoring.queries import SQLQueries
from modules.monitoring.monitoring import ConnectionPool, ConnectionInfo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class QueryTester:
    """Testa todas as queries SQL disponíveis"""

    def __init__(self, server: str, instance: str = ""):
        """Inicializa o testador"""
        self.server = server
        self.instance = instance
        self.pool = ConnectionPool(max_connections=5)
        self.results = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'warnings': 0,
            'errors': []
        }

    def test_query(self, query_name: str, query_sql: str, description: str = ""):
        """
        Testa uma query individual

        Args:
            query_name: Nome da query
            query_sql: SQL da query
            description: Descrição opcional
        """
        self.results['total'] += 1

        try:
            logger.info(f"\n{'='*80}")
            logger.info(f"Testando: {query_name}")
            if description:
                logger.info(f"Descrição: {description}")
            logger.info(f"{'='*80}")

            # Conectar ao servidor
            conn_info = ConnectionInfo(
                server=self.server,
                instance=self.instance if self.instance else "DEFAULT",
                database="master",
                connection_timeout=30
            )

            conn = self.pool.get_connection(conn_info)
            if not conn:
                raise Exception(f"Falha ao conectar em {self.server}")

            # Executar query
            cursor = conn.cursor()

            # Validar SQL (executar com TOP 1 se não tiver TOP)
            test_sql = query_sql.strip()
            if not any(keyword in test_sql.upper()[:100] for keyword in ['TOP ', 'SELECT TOP']):
                # Adicionar TOP 1 para teste rápido
                test_sql = test_sql.replace('SELECT ', 'SELECT TOP 1 ', 1)

            cursor.execute(test_sql)
            rows = cursor.fetchall()

            logger.info(f"✅ PASSOU: {query_name}")
            logger.info(f"   Linhas retornadas: {len(rows)}")
            logger.info(f"   Colunas: {len(cursor.description) if cursor.description else 0}")

            if cursor.description:
                columns = [col[0] for col in cursor.description]
                logger.info(f"   Estrutura: {', '.join(columns[:5])}{'...' if len(columns) > 5 else ''}")

            self.results['passed'] += 1

            # Avisos
            if len(rows) == 0:
                logger.warning(f"   ⚠️ AVISO: Query não retornou dados (pode ser normal)")
                self.results['warnings'] += 1

            cursor.close()
            return True

        except Exception as e:
            logger.error(f"❌ FALHOU: {query_name}")
            logger.error(f"   Erro: {str(e)}")
            self.results['failed'] += 1
            self.results['errors'].append({
                'query': query_name,
                'error': str(e)
            })
            return False

    def run_all_tests(self):
        """Executa testes em todas as queries"""
        logger.info("\n" + "="*80)
        logger.info("  TESTE DE QUERIES SQL - WatcherDB")
        logger.info("="*80)
        logger.info("Servidor: %s%s", self.server, '\\' + self.instance if self.instance else '')
        logger.info("="*80 + "\n")

        # Lista de queries para testar
        queries_to_test = [
            # Queries principais
            ("HEALTH_OVERVIEW", SQLQueries.HEALTH_OVERVIEW, "Visão geral de saúde do servidor"),
            ("TDE_STATUS", SQLQueries.TDE_STATUS, "Status de criptografia TDE"),
            ("FILEGROUPS_SPACE", SQLQueries.FILEGROUPS_SPACE, "Análise de espaço de filegroups"),
            ("TOP_SLOW_QUERIES", SQLQueries.TOP_SLOW_QUERIES, "Top 50 queries lentas"),
            ("ACTIVE_PROCESSES", SQLQueries.ACTIVE_PROCESSES, "Processos ativos"),
            ("BLOCKING_CHAINS", SQLQueries.BLOCKING_CHAINS, "Cadeias de bloqueio"),
            ("BACKUP_STATUS", SQLQueries.BACKUP_STATUS, "Status de backups"),
            ("WAIT_STATS", SQLQueries.WAIT_STATS, "Top 20 wait stats"),
            ("INDEX_FRAGMENTATION", SQLQueries.INDEX_FRAGMENTATION, "Fragmentação de índices"),
            ("AVAILABILITY_GROUPS", SQLQueries.AVAILABILITY_GROUPS, "Status Always On AG"),
            ("SQL_AGENT_JOBS", SQLQueries.SQL_AGENT_JOBS, "Jobs do SQL Agent"),

            # Queries adicionais/troubleshooting
            ("BLOCKING_HIERARCHY", SQLQueries.BLOCKING_HIERARCHY, "Hierarquia de bloqueios"),
            ("TOP_SLOW_QUERIES_DETAILED", SQLQueries.TOP_SLOW_QUERIES_DETAILED, "Queries lentas detalhadas"),
            ("LOG_SPACE_MONITORING", SQLQueries.LOG_SPACE_MONITORING, "Monitoramento de log"),
            ("SQL_AGENT_JOBS_FAILING", SQLQueries.SQL_AGENT_JOBS_FAILING, "Jobs falhando"),
            ("PROBLEMATIC_SESSIONS", SQLQueries.PROBLEMATIC_SESSIONS, "Sessões problemáticas"),
            ("INDEX_FRAGMENTATION_DETAILED", SQLQueries.INDEX_FRAGMENTATION_DETAILED, "Fragmentação detalhada"),
            ("TEMPDB_MONITORING", SQLQueries.TEMPDB_MONITORING, "Monitoramento TempDB"),
            ("FILE_GROWTH_MONITORING", SQLQueries.FILE_GROWTH_MONITORING, "Monitoramento de crescimento"),
            ("STATISTICS_OUTDATED", SQLQueries.STATISTICS_OUTDATED, "Estatísticas desatualizadas"),
            ("MIRRORING_LOGSHIPPING_STATUS", SQLQueries.MIRRORING_LOGSHIPPING_STATUS, "Mirroring/Log Shipping"),
            ("DATABASE_CONNECTIONS", SQLQueries.DATABASE_CONNECTIONS, "Conexões por database"),
        ]

        # Executar testes
        for query_name, query_sql, description in queries_to_test:
            self.test_query(query_name, query_sql, description)

        # Resultado final
        self.print_summary()

    def print_summary(self):
        """Imprime sumário dos testes"""
        logger.info("\n" + "="*80)
        logger.info("  SUMÁRIO DOS TESTES")
        logger.info("="*80)
        logger.info(f"Total de queries testadas: {self.results['total']}")
        logger.info(f"✅ Passaram: {self.results['passed']}")
        logger.info(f"❌ Falharam: {self.results['failed']}")
        logger.info(f"⚠️  Avisos: {self.results['warnings']}")
        logger.info("="*80)

        if self.results['failed'] > 0:
            logger.info("\n❌ QUERIES QUE FALHARAM:")
            logger.info("="*80)
            for error in self.results['errors']:
                logger.info(f"\n Query: {error['query']}")
                logger.info(f" Erro: {error['error']}")

        logger.info("\n" + "="*80)
        success_rate = (self.results['passed'] / self.results['total']) * 100
        logger.info(f"Taxa de sucesso: {success_rate:.1f}%")
        logger.info("="*80 + "\n")

        if self.results['failed'] == 0:
            logger.info("✅ TODOS OS TESTES PASSARAM!")
        else:
            logger.warning(f"⚠️  {self.results['failed']} teste(s) falharam")

        return self.results['failed'] == 0


def main():
    """Executa os testes"""
    import argparse

    parser = argparse.ArgumentParser(description='Testa todas as queries SQL do WatcherDB')
    parser.add_argument('server', help='Nome do servidor SQL')
    parser.add_argument('--instance', '-i', default='', help='Nome da instância (opcional)')

    args = parser.parse_args()

    tester = QueryTester(args.server, args.instance)
    success = tester.run_all_tests()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
