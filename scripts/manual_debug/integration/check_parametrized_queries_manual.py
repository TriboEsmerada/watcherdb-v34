#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste das Queries Parametrizáveis v1.4.8.1
Valida:
- FILEGROUP_GROWTH_HISTORY (com/sem database)
- FILEGROUP_GROWTH_FORECAST (com/sem database)
- MISSING_INDEX_ANALYSIS (com/sem database)
- BACKUP_HISTORY_ANALYSIS (SEM parametrização)
"""
import sys
import logging
import asyncio
import pandas as pd
from modules.monitoring.queries import SQLQueries
from modules.monitoring.monitoring import ConnectionPool, ConnectionInfo, SQLServerExecutor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_query(executor, conn_info, query_name, query, description):
    """Testa uma query e retorna resultado"""
    logger.info("=" * 80)
    logger.info(f"Testando: {query_name}")
    logger.info(f"Descrição: {description}")
    logger.info("=" * 80)

    try:
        result = await executor.execute_query(conn_info, query)

        if result:
            df = pd.DataFrame(result)
            logger.info(f"✅ PASSOU: {query_name}")
            logger.info(f"   Linhas retornadas: {len(df)}")
            logger.info(f"   Colunas: {len(df.columns)}")
            logger.info(f"   Estrutura: {', '.join(df.columns)}")

            if len(df) > 0:
                logger.info("")
                logger.info("📋 Primeiras 3 linhas (resumo):")
                for idx, row in df.head(3).iterrows():
                    logger.info(f"   Linha {idx + 1}: {dict(list(row.items())[:3])}")

            return True, len(df)
        else:
            logger.warning(f"⚠️  AVISO: {query_name} - Nenhum resultado (pode ser normal)")
            return True, 0

    except Exception as e:
        logger.error(f"❌ FALHA: {query_name}")
        logger.error(f"   Erro: {e}")
        import traceback
        traceback.print_exc()
        return False, 0

async def main(server: str, instance: str = "", test_database: str = None):
    """Executa testes das queries parametrizáveis"""

    logger.info("")
    logger.info("=" * 80)
    logger.info("  TESTE DE QUERIES PARAMETRIZÁVEIS - WatcherDB v1.4.8.1")
    logger.info("=" * 80)
    logger.info("Servidor: %s%s", server, '\\' + instance if instance else '')
    if test_database:
        logger.info(f"Database de teste: {test_database}")
    logger.info("=" * 80)
    logger.info("")

    # Conectar
    pool = ConnectionPool(max_connections=5)
    executor = SQLServerExecutor(pool, max_workers=2)
    conn_info = ConnectionInfo(
        server=server,
        instance=instance,
        database="master"
    )

    results = {}

    try:
        # Teste 1: FILEGROUP_GROWTH_HISTORY - TODAS as databases
        success, count = await test_query(
            executor, conn_info,
            "FILEGROUP_GROWTH_HISTORY (TODAS)",
            SQLQueries.get_filegroup_growth_history_filtered(None),
            "Histórico de crescimento de filegroups - todas as databases"
        )
        results['filegroup_history_all'] = (success, count)
        logger.info("")

        # Teste 2: FILEGROUP_GROWTH_HISTORY - Database específica
        if test_database:
            success, count = await test_query(
                executor, conn_info,
                f"FILEGROUP_GROWTH_HISTORY ({test_database})",
                SQLQueries.get_filegroup_growth_history_filtered(test_database),
                f"Histórico de crescimento de filegroups - {test_database}"
            )
            results['filegroup_history_filtered'] = (success, count)
            logger.info("")

        # Teste 3: FILEGROUP_GROWTH_FORECAST - TODAS as databases
        success, count = await test_query(
            executor, conn_info,
            "FILEGROUP_GROWTH_FORECAST (TODAS)",
            SQLQueries.get_filegroup_growth_forecast_filtered(None),
            "Projeção de crescimento de filegroups - todas as databases"
        )
        results['filegroup_forecast_all'] = (success, count)
        logger.info("")

        # Teste 4: FILEGROUP_GROWTH_FORECAST - Database específica
        if test_database:
            success, count = await test_query(
                executor, conn_info,
                f"FILEGROUP_GROWTH_FORECAST ({test_database})",
                SQLQueries.get_filegroup_growth_forecast_filtered(test_database),
                f"Projeção de crescimento de filegroups - {test_database}"
            )
            results['filegroup_forecast_filtered'] = (success, count)
            logger.info("")

        # Teste 5: MISSING_INDEX_ANALYSIS - TODAS as databases
        success, count = await test_query(
            executor, conn_info,
            "MISSING_INDEX_ANALYSIS (TODAS)",
            SQLQueries.get_missing_index_analysis_filtered(None),
            "Análise de índices faltantes - todas as databases (v1.4.8.1 CORRIGIDA)"
        )
        results['missing_index_all'] = (success, count)
        logger.info("")

        # Teste 6: MISSING_INDEX_ANALYSIS - Database específica
        if test_database:
            success, count = await test_query(
                executor, conn_info,
                f"MISSING_INDEX_ANALYSIS ({test_database})",
                SQLQueries.get_missing_index_analysis_filtered(test_database),
                f"Análise de índices faltantes - {test_database}"
            )
            results['missing_index_filtered'] = (success, count)
            logger.info("")

        # Teste 7: BACKUP_HISTORY_ANALYSIS - SEM parametrização
        success, count = await test_query(
            executor, conn_info,
            "BACKUP_HISTORY_ANALYSIS",
            SQLQueries.BACKUP_HISTORY_ANALYSIS,
            "Análise de histórico de backups - SEM filtro (todas as databases)"
        )
        results['backup_history'] = (success, count)
        logger.info("")

        # Resumo
        logger.info("=" * 80)
        logger.info("📊 RESUMO DOS TESTES")
        logger.info("=" * 80)

        passed = sum(1 for success, _ in results.values() if success)
        failed = sum(1 for success, _ in results.values() if not success)

        logger.info(f"Total de testes: {len(results)}")
        logger.info(f"✅ Passou: {passed}")
        logger.info(f"❌ Falhou: {failed}")
        logger.info("")

        logger.info("Detalhes:")
        for test_name, (success, count) in results.items():
            status = "✅ PASSOU" if success else "❌ FALHOU"
            logger.info(f"  {status} - {test_name}: {count} linhas")

        logger.info("")
        logger.info("=" * 80)

        if failed == 0:
            logger.info("✅ TODOS OS TESTES PASSARAM!")
        else:
            logger.error(f"❌ {failed} TESTES FALHARAM!")

        logger.info("=" * 80)

        return failed == 0

    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        pool.close_all()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_parametrized_queries.py <servidor> [--instance <instancia>] [--database <database>]")
        print("Exemplo: python test_parametrized_queries.py SQLHDSPRD013 --instance I03 --database TENT_TAP")
        sys.exit(1)

    server = sys.argv[1]
    instance = ""
    test_database = None

    if "--instance" in sys.argv:
        idx = sys.argv.index("--instance")
        if idx + 1 < len(sys.argv):
            instance = sys.argv[idx + 1]

    if "--database" in sys.argv:
        idx = sys.argv.index("--database")
        if idx + 1 < len(sys.argv):
            test_database = sys.argv[idx + 1]

    success = asyncio.run(main(server, instance, test_database))
    sys.exit(0 if success else 1)
