"""
Teste das 4 novas queries adicionadas na v1.4.8
- FILEGROUP_GROWTH_HISTORY
- FILEGROUP_GROWTH_FORECAST
- BACKUP_HISTORY_ANALYSIS
- MISSING_INDEX_ANALYSIS
"""
import sys
import logging
import pandas as pd
# As constantes vivem DENTRO da classe SQLQueries (queries.py:1623+), nunca
# existiram ao nivel do modulo -- o import antigo falhava sempre.
from modules.monitoring.queries import SQLQueries

FILEGROUP_GROWTH_HISTORY = SQLQueries.FILEGROUP_GROWTH_HISTORY
FILEGROUP_GROWTH_FORECAST = SQLQueries.FILEGROUP_GROWTH_FORECAST
BACKUP_HISTORY_ANALYSIS = SQLQueries.BACKUP_HISTORY_ANALYSIS
MISSING_INDEX_ANALYSIS = SQLQueries.MISSING_INDEX_ANALYSIS
from modules.monitoring.monitoring import ConnectionPool, ConnectionInfo

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NewQueriesTester:
    """Testa as novas queries v1.4.8"""

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
        """Testa uma query individual"""
        self.results['total'] += 1

        try:
            logger.info("")
            logger.info("=" * 80)
            logger.info(f"Testando: {query_name}")
            if description:
                logger.info(f"Descrição: {description}")
            logger.info("=" * 80)

            # Conectar ao servidor
            conn_info = ConnectionInfo(
                server=self.server,
                instance=self.instance,
                database="master"
            )

            connection = self.pool.get_connection(conn_info)

            # Executar query
            cursor = connection.cursor()
            cursor.execute(query_sql)

            # Obter resultados
            columns = [column[0] for column in cursor.description] if cursor.description else []
            rows = cursor.fetchall()

            # Converter para DataFrame
            if rows:
                df = pd.DataFrame.from_records(rows, columns=columns)
            else:
                df = pd.DataFrame(columns=columns)

            cursor.close()

            # Validar resultados
            if df.empty:
                logger.warning(f"⚠️  SEM DADOS: {query_name}")
                logger.warning("   Pode ser normal se não houver dados históricos")
                self.results['warnings'] += 1
                return False

            logger.info(f"✅ PASSOU: {query_name}")
            logger.info(f"   Linhas retornadas: {len(df)}")
            logger.info(f"   Colunas: {len(df.columns)}")
            logger.info(f"   Estrutura: {', '.join(df.columns[:5])}{'...' if len(df.columns) > 5 else ''}")

            # Mostrar primeiras 3 linhas
            logger.info("")
            logger.info("📊 Primeiras linhas:")
            for idx, row in df.head(3).iterrows():
                logger.info(f"   Linha {idx + 1}:")
                for col in df.columns[:8]:  # Mostrar até 8 colunas
                    value = row[col]
                    if isinstance(value, float):
                        logger.info(f"      {col}: {value:.2f}")
                    elif pd.isna(value):
                        logger.info(f"      {col}: NULL")
                    else:
                        logger.info(f"      {col}: {value}")
                if len(df.columns) > 8:
                    logger.info(f"      ... (+{len(df.columns) - 8} colunas)")
                logger.info("")

            self.results['passed'] += 1
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
        """Executa todos os testes das novas queries"""
        queries_to_test = [
            {
                "name": "FILEGROUP_GROWTH_HISTORY",
                "sql": FILEGROUP_GROWTH_HISTORY,
                "description": "Histórico de crescimento de filegroups (12 meses)"
            },
            {
                "name": "FILEGROUP_GROWTH_FORECAST",
                "sql": FILEGROUP_GROWTH_FORECAST,
                "description": "Projeção de crescimento (MonthsUntilFull)"
            },
            {
                "name": "BACKUP_HISTORY_ANALYSIS",
                "sql": BACKUP_HISTORY_ANALYSIS,
                "description": "Análise de backups (considera Always On AG)"
            },
            {
                "name": "MISSING_INDEX_ANALYSIS",
                "sql": MISSING_INDEX_ANALYSIS,
                "description": "Índices faltantes com alto impacto"
            }
        ]

        # Executar testes
        for query in queries_to_test:
            self.test_query(
                query["name"],
                query["sql"],
                query["description"]
            )

    def print_summary(self):
        """Imprime resumo dos testes"""
        logger.info("")
        logger.info("=" * 80)
        logger.info("RESUMO DOS TESTES - v1.4.8")
        logger.info("=" * 80)

        logger.info(f"Total de queries testadas: {self.results['total']}")
        logger.info(f"✅ Passou: {self.results['passed']}")
        logger.info(f"⚠️  Sem dados: {self.results['warnings']}")
        logger.info(f"❌ Falhou: {self.results['failed']}")

        if self.results['errors']:
            logger.info("")
            logger.info("Erros encontrados:")
            for error in self.results['errors']:
                logger.info(f"  - {error['query']}: {error['error']}")

        logger.info("=" * 80)

    def cleanup(self):
        """Limpa conexões"""
        self.pool.close_all()

def main():
    if len(sys.argv) < 2:
        print("Uso: python test_new_queries_v148.py <servidor> [--instance <instancia>]")
        print("Exemplo: python test_new_queries_v148.py SQLHDSPRD013 --instance I03")
        sys.exit(1)

    server = sys.argv[1]
    instance = ""

    if "--instance" in sys.argv:
        idx = sys.argv.index("--instance")
        if idx + 1 < len(sys.argv):
            instance = sys.argv[idx + 1]

    logger.info("")
    logger.info("=" * 80)
    logger.info("  TESTE DE NOVAS QUERIES v1.4.8 - WatcherDB")
    logger.info("=" * 80)
    logger.info("Servidor: %s%s", server, '\\' + instance if instance else '')
    logger.info("=" * 80)

    # Criar tester e executar
    tester = NewQueriesTester(server, instance)

    try:
        tester.run_all_tests()
        tester.print_summary()
    finally:
        tester.cleanup()

    # Retornar código de saída apropriado
    return 0 if tester.results['failed'] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
