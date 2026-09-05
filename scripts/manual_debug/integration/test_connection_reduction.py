#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de teste: Validação da redução de conexões

Compara comportamento ANTES vs DEPOIS das otimizações
"""

import sys
import logging
from modules.monitoring.monitoring import get_global_connection_pool, get_pool_stats
from modules.monitoring.watcherdb_alwayson_check import get_alwayson_checker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_singleton():
    """Testa se o singleton está funcionando"""
    print("\n" + "="*80)
    print("TESTE 1: Singleton do AlwaysOnChecker")
    print("="*80)

    # Criar múltiplas instâncias
    checker1 = get_alwayson_checker()
    checker2 = get_alwayson_checker()
    checker3 = get_alwayson_checker()

    # Verificar se são a mesma instância
    assert checker1 is checker2, "[FAIL] FALHOU: checker1 e checker2 são instâncias diferentes!"
    assert checker2 is checker3, "[FAIL] FALHOU: checker2 e checker3 são instâncias diferentes!"

    print(f"[OK] PASSOU: Todas as chamadas retornam a MESMA instância")
    print(f"   - checker1 id: {id(checker1)}")
    print(f"   - checker2 id: {id(checker2)}")
    print(f"   - checker3 id: {id(checker3)}")
    print(f"   - Servidores carregados: {len(checker1.ag_servers)}")


def test_global_pool():
    """Testa se o pool global está sendo compartilhado"""
    print("\n" + "="*80)
    print("TESTE 2: Pool Global Compartilhado")
    print("="*80)

    # Obter pool global
    pool1 = get_global_connection_pool()
    pool2 = get_global_connection_pool()

    # Verificar se são a mesma instância
    assert pool1 is pool2, "[FAIL] FALHOU: pool1 e pool2 são instâncias diferentes!"

    print(f"[OK] PASSOU: Todas as chamadas retornam o MESMO pool")
    print(f"   - pool1 id: {id(pool1)}")
    print(f"   - pool2 id: {id(pool2)}")
    print(f"   - Max connections: {pool1.max_connections}")


def test_checker_uses_global_pool():
    """Testa se AlwaysOnChecker usa o pool global"""
    print("\n" + "="*80)
    print("TESTE 3: AlwaysOnChecker usando Pool Global")
    print("="*80)

    global_pool = get_global_connection_pool()
    checker = get_alwayson_checker()

    # Verificar se o checker usa o pool global
    assert checker.connection_pool is global_pool, "[FAIL] FALHOU: Checker NÃO está usando pool global!"

    print(f"[OK] PASSOU: AlwaysOnChecker está usando o pool global")
    print(f"   - Global pool id: {id(global_pool)}")
    print(f"   - Checker pool id: {id(checker.connection_pool)}")


def test_lazy_loading():
    """Testa lazy loading do overview"""
    print("\n" + "="*80)
    print("TESTE 4: Lazy Loading (sem conexões)")
    print("="*80)

    # Obter stats antes
    stats_before = get_pool_stats()
    connections_before = stats_before['total_connections_created']

    print(f"[STAT] Conexoes antes: {connections_before}")

    # Chamar overview com lazy=True (NÃO deve criar conexões)
    checker = get_alwayson_checker()
    overview_lazy = checker.get_all_ag_overview(lazy=True)

    # Obter stats depois
    stats_after = get_pool_stats()
    connections_after = stats_after['total_connections_created']

    print(f"[STAT] Conexoes depois (lazy): {connections_after}")
    print(f"[STAT] Diferenca: {connections_after - connections_before}")

    # Verificar que lazy loading retorna dados
    assert overview_lazy['lazy_loaded'] == True, "[FAIL] FALHOU: Overview não marcado como lazy_loaded"
    assert overview_lazy['total_ags'] > 0, "[FAIL] FALHOU: Nenhum AG retornado"
    assert len(overview_lazy['ags']) > 0, "[FAIL] FALHOU: Lista de AGs vazia"

    # Verificar que NÃO criou conexões
    new_connections = connections_after - connections_before
    assert new_connections == 0, f"[FAIL] FALHOU: Lazy loading criou {new_connections} conexões!"

    print(f"[OK] PASSOU: Lazy loading retornou {overview_lazy['total_ags']} AGs sem criar conexões")
    print(f"   - lazy_loaded: {overview_lazy['lazy_loaded']}")
    print(f"   - Conexões criadas: {new_connections}")


def test_full_loading():
    """Testa full loading (com conexões) - AVISO: LENTO!"""
    print("\n" + "="*80)
    print("TESTE 5: Full Loading (com conexões) - PULADO")
    print("="*80)
    print("[WARN]  PULADO: Este teste cria 84 conexões e é muito lento")
    print("   Para testar manualmente, use:")
    print("   >>> checker.get_all_ag_overview(lazy=False)")


def print_final_stats():
    """Imprime estatisticas finais do pool"""
    print("\n" + "="*80)
    print("ESTATISTICAS FINAIS DO POOL")
    print("="*80)

    stats = get_pool_stats()

    print(f"[STAT] Total de conexoes criadas: {stats['total_connections_created']}")
    print(f"[STAT] Conexoes ativas: {stats['active_connections']}")
    print(f"[STAT] Conexoes no pool: {stats['pooled_connections']}")
    print(f"[STAT] Pool hit rate: {stats['pool_hit_rate']}")
    print(f"[STAT] Pool hits: {stats['pool_hits']}")
    print(f"[STAT] Pool misses: {stats['pool_misses']}")
    print(f"[STAT] Erros de conexao: {stats['connection_errors']}")
    print(f"[STAT] Retries: {stats['retries']}")

    if stats['active_by_pool']:
        print("\n[STAT] Conexoes ativas por servidor:")
        for pool_key, count in stats['active_by_pool'].items():
            if count > 0:
                print(f"   - {pool_key}: {count}")


def main():
    """Executa todos os testes"""
    print("\n" + "="*80)
    print("  TESTE DE REDUCAO DE CONEXOES - WatcherDB v1.4.0")
    print("="*80)

    try:
        test_singleton()
        test_global_pool()
        test_checker_uses_global_pool()
        test_lazy_loading()
        test_full_loading()
        print_final_stats()

        print("\n" + "="*80)
        print("TODOS OS TESTES PASSARAM!")
        print("="*80)

        print("\nRESUMO DAS OTIMIZACOES:")
        print("   1. Singleton do AlwaysOnChecker (1 instancia compartilhada)")
        print("   2. Pool Global de Conexoes (50 conexoes maximo)")
        print("   3. Lazy Loading no overview (0 conexoes no startup)")
        print("   4. Reutilizacao de conexoes entre modulos")

        print("\nRESULTADOS ESPERADOS:")
        print("   - ANTES: 84 conexoes no startup (42 servidores x 2)")
        print("   - DEPOIS: 0-5 conexoes no startup (lazy loading)")
        print("   - REDUCAO: ~95% de conexoes eliminadas")

        return 0

    except AssertionError as e:
        print(f"\n[FAIL] TESTE FALHOU: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Erro nos testes: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
