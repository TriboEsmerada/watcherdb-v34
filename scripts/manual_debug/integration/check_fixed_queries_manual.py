"""
Test rapido das 2 queries corrigidas
"""
import logging
import sys
from modules.monitoring.queries import SQLQueries
from modules.monitoring.monitoring import ConnectionPool, ConnectionInfo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_query(pool, conn_info, query_name, query_sql):
    """Testa uma query"""
    try:
        logger.info(f"\nTestando: {query_name}")
        logger.info("="*80)

        conn = pool.get_connection(conn_info)
        if not conn:
            raise Exception("Falha ao conectar")

        cursor = conn.cursor()
        cursor.execute(query_sql)
        rows = cursor.fetchall()

        logger.info(f"PASSOU: {query_name}")
        logger.info(f"Linhas retornadas: {len(rows)}")
        logger.info(f"Colunas: {len(cursor.description) if cursor.description else 0}")

        if cursor.description:
            columns = [col[0] for col in cursor.description]
            logger.info(f"Colunas: {', '.join(columns[:10])}")

        cursor.close()
        return True

    except Exception as e:
        logger.error(f"FALHOU: {query_name}")
        logger.error(f"Erro: {str(e)}")
        return False

def main():
    """Executa testes"""
    server = "SQLHDSPRD013"
    instance = "I03"

    logger.info(f"\nTeste de Queries Corrigidas - {server}\\{instance}\n")

    pool = ConnectionPool(max_connections=5)
    conn_info = ConnectionInfo(
        server=server,
        instance=instance,
        database="master",
        connection_timeout=30
    )

    # Teste 1: HEALTH_OVERVIEW (corrigida collation conflict)
    logger.info("\n" + "="*80)
    logger.info("TESTE 1: HEALTH_OVERVIEW (Collation Conflict Fix)")
    logger.info("="*80)
    result1 = test_query(pool, conn_info, "HEALTH_OVERVIEW", SQLQueries.HEALTH_OVERVIEW)

    # Teste 2: BLOCKING_CHAINS (query otimizada)
    logger.info("\n" + "="*80)
    logger.info("TESTE 2: BLOCKING_CHAINS (Performance Optimization)")
    logger.info("="*80)
    result2 = test_query(pool, conn_info, "BLOCKING_CHAINS", SQLQueries.BLOCKING_CHAINS)

    # Resultado
    logger.info("\n" + "="*80)
    logger.info("RESULTADO FINAL")
    logger.info("="*80)
    logger.info(f"HEALTH_OVERVIEW: {'PASSOU' if result1 else 'FALHOU'}")
    logger.info(f"BLOCKING_CHAINS: {'PASSOU' if result2 else 'FALHOU'}")
    logger.info("="*80)

    return 0 if (result1 and result2) else 1

if __name__ == "__main__":
    sys.exit(main())
