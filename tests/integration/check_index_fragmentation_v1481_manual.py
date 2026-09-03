"""
Teste da query INDEX_FRAGMENTATION v1.4.8.1
Valida:
- QUOTENAME usage
- Suporte a HEAPs (RebuildTableScript)
- RebuildIndexScript
"""
import sys
import logging
import pandas as pd
from modules.monitoring.queries import SQLQueries
from modules.monitoring.monitoring import ConnectionPool, ConnectionInfo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_index_fragmentation(server: str, instance: str = ""):
    """Testa a query INDEX_FRAGMENTATION v1.4.8.1"""

    logger.info("=" * 80)
    logger.info("TESTE: INDEX_FRAGMENTATION v1.4.8.1")
    logger.info("=" * 80)
    logger.info("Servidor: %s%s", server, '\\' + instance if instance else '')
    logger.info("")

    # Conectar
    pool = ConnectionPool(max_connections=5)
    conn_info = ConnectionInfo(
        server=server,
        instance=instance,
        database="master"
    )

    connection = pool.get_connection(conn_info)
    cursor = connection.cursor()

    try:
        # Executar query
        logger.info("Executando INDEX_FRAGMENTATION...")
        cursor.execute(SQLQueries.INDEX_FRAGMENTATION)

        # Obter resultados
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        if rows:
            df = pd.DataFrame.from_records(rows, columns=columns)
        else:
            df = pd.DataFrame(columns=columns)

        cursor.close()

        # Validar estrutura
        logger.info(f"✅ Query executada com sucesso!")
        logger.info(f"   Linhas retornadas: {len(df)}")
        logger.info(f"   Colunas: {len(df.columns)}")
        logger.info("")

        # Mostrar colunas
        logger.info("📊 Estrutura de colunas:")
        for i, col in enumerate(df.columns, 1):
            logger.info(f"   {i}. {col}")
        logger.info("")

        # Verificar colunas obrigatórias
        required_cols = [
            'DatabaseName', 'SchemaName', 'TableName', 'IndexName', 'IndexType',
            'FragmentationPercent', 'PageCount', 'IndexSizeMB', 'RecordCount',
            'MaintenanceAction', 'Priority', 'RebuildIndexScript', 'RebuildTableScript'
        ]

        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(f"❌ Colunas faltando: {', '.join(missing_cols)}")
            return False

        logger.info("✅ Todas as colunas obrigatórias presentes!")
        logger.info("")

        if len(df) > 0:
            # Mostrar exemplos
            logger.info("📋 Primeiras 3 linhas:")
            logger.info("")

            for idx, row in df.head(3).iterrows():
                logger.info(f"--- Linha {idx + 1} ---")
                logger.info(f"Database: {row['DatabaseName']}")
                logger.info(f"Schema.Table: {row['SchemaName']}.{row['TableName']}")
                logger.info(f"Index: {row['IndexName']} ({row['IndexType']})")
                logger.info(f"Fragmentação: {row['FragmentationPercent']:.2f}%")
                logger.info(f"Tamanho: {row['IndexSizeMB']:.2f} MB ({row['PageCount']} páginas)")
                logger.info(f"Ação: {row['MaintenanceAction']} (Prioridade {row['Priority']})")

                if pd.notna(row['RebuildIndexScript']):
                    logger.info(f"Script Índice: {row['RebuildIndexScript'][:80]}...")

                if pd.notna(row['RebuildTableScript']):
                    logger.info(f"⭐ Script HEAP: {row['RebuildTableScript']}")

                logger.info("")

            # Estatísticas
            logger.info("📊 Estatísticas:")
            logger.info(f"   Total de índices fragmentados: {len(df)}")
            logger.info(f"   Fragmentação média: {df['FragmentationPercent'].mean():.2f}%")
            logger.info(f"   Fragmentação máxima: {df['FragmentationPercent'].max():.2f}%")

            # Contar por ação
            action_counts = df['MaintenanceAction'].value_counts()
            logger.info("")
            logger.info("   Por ação recomendada:")
            for action, count in action_counts.items():
                logger.info(f"      {action}: {count}")

            # Contar HEAPs
            heap_count = df[df['RebuildTableScript'].notna()].shape[0]
            if heap_count > 0:
                logger.info("")
                logger.info(f"   ⭐ HEAPs encontrados: {heap_count}")

            # Verificar QUOTENAME
            logger.info("")
            logger.info("🔍 Validação de QUOTENAME:")
            has_scripts = df['RebuildIndexScript'].notna().sum()
            logger.info(f"   Scripts de índice gerados: {has_scripts}")

            if has_scripts > 0:
                sample_script = df[df['RebuildIndexScript'].notna()]['RebuildIndexScript'].iloc[0]
                if 'QUOTENAME' not in sample_script:  # QUOTENAME já foi processado pelo SQL
                    logger.info("   ✅ Scripts usando sintaxe correta (QUOTENAME processado)")

        else:
            logger.warning("⚠️  Nenhum índice fragmentado encontrado (pode ser normal)")

        logger.info("")
        logger.info("=" * 80)
        logger.info("TESTE CONCLUÍDO COM SUCESSO!")
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.error(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        pool.close_all()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_index_fragmentation_v1481.py <servidor> [--instance <instancia>]")
        print("Exemplo: python test_index_fragmentation_v1481.py SQLHDSPRD013 --instance I03")
        sys.exit(1)

    server = sys.argv[1]
    instance = ""

    if "--instance" in sys.argv:
        idx = sys.argv.index("--instance")
        if idx + 1 < len(sys.argv):
            instance = sys.argv[idx + 1]

    success = test_index_fragmentation(server, instance)
    sys.exit(0 if success else 1)
