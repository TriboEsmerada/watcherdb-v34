"""
Script de Teste - SQL Server KPI Service
=========================================

Script para testar rapidamente o serviço de KPIs SQL Server.

Uso:
    python test_sqlserver_kpi.py

Pré-requisitos:
    - pyodbc instalado
    - ODBC Driver 17 for SQL Server instalado
    - Variáveis de ambiente configuradas (.env ou sistema)

Author: WatcherDB Team
Date: 2025-11-27
Version: 1.0.0
"""

import os
import sys
import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_header(title):
    """Imprime header formatado"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def print_section(title):
    """Imprime seção formatada"""
    print(f"\n{'-'*70}")
    print(f"  {title}")
    print(f"{'-'*70}")


def check_prerequisites():
    """Verifica pré-requisitos"""
    print_header("1. VERIFICANDO PRÉ-REQUISITOS")

    # 1. Verificar pyodbc
    print_section("Verificando pyodbc...")
    try:
        import pyodbc
        print(f"[OK] pyodbc instalado: {pyodbc.version}")
    except ImportError:
        print("[FAIL] pyodbc NÃO instalado")
        print("   Instalar: pip install pyodbc")
        return False

    # 2. Verificar drivers ODBC
    print_section("Verificando ODBC Drivers...")
    drivers = pyodbc.drivers()
    print(f"Drivers encontrados: {len(drivers)}")
    for driver in drivers:
        print(f"  - {driver}")

    if not any("SQL Server" in d for d in drivers):
        print("[FAIL] Nenhum driver SQL Server encontrado")
        print("   Baixar: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server")
        return False

    print("[OK] Driver SQL Server encontrado")

    # 3. Verificar variáveis de ambiente
    print_section("Verificando variáveis de ambiente...")

    required_vars = ["SQL_SERVER"]
    optional_vars = ["SQL_DATABASE", "SQL_TRUSTED_CONNECTION", "SQL_USER", "SQL_PASSWORD"]

    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"[OK] {var}: {value}")
        else:
            print(f"[FAIL] {var}: NÃO DEFINIDO")
            missing.append(var)

    for var in optional_vars:
        value = os.getenv(var)
        if value:
            # Mascarar senha
            if "PASSWORD" in var:
                print(f"[OK] {var}: {'*' * 8}")
            else:
                print(f"[OK] {var}: {value}")
        else:
            print(f"[WARN]  {var}: não definido (usando padrão)")

    if missing:
        print(f"\n[FAIL] Variáveis obrigatórias ausentes: {', '.join(missing)}")
        print("   Criar arquivo .env com:")
        print("   SQL_SERVER=SQLHDSPRD213\\I01")
        print("   SQL_TRUSTED_CONNECTION=yes")
        return False

    print("\n[OK] Todas as variáveis obrigatórias definidas")
    return True


def test_connection():
    """Testa conexão SQL Server"""
    print_header("2. TESTANDO CONEXÃO SQL SERVER")

    try:
        from services.sqlserver_kpi_service import SQLServerKPIService

        print_section("Criando serviço...")
        service = SQLServerKPIService()
        print("[OK] Serviço criado")

        print_section("Testando conexão...")
        conn = service.get_connection()
        print("[OK] Conexão estabelecida")

        # Testar query simples
        cursor = conn.cursor()
        cursor.execute("SELECT @@SERVERNAME AS instance, @@VERSION AS version")
        row = cursor.fetchone()

        print(f"\nInstância: {row[0]}")
        print(f"Versão: {row[1][:100]}...")

        cursor.close()
        conn.close()
        print("\n[OK] Conexão fechada com sucesso")

        return True

    except Exception as e:
        print(f"[FAIL] Erro ao conectar: {e}")
        logger.error(f"Erro detalhado:", exc_info=True)
        return False


def test_kpis():
    """Testa KPIs individuais"""
    print_header("3. TESTANDO KPIs INDIVIDUAIS")

    try:
        from services.sqlserver_kpi_service import SQLServerKPIService

        service = SQLServerKPIService()

        # Lista de KPIs para testar
        kpis = [
            ("Instance Availability", service.get_instance_availability),
            ("Database Availability", service.get_database_availability),
            ("Disk Usage", service.get_disk_usage),
            ("Transaction Log Usage", lambda: service.get_tlog_usage(threshold_percent=75.0)),
            ("Always On Status", service.get_alwayson_status),
            ("Filegroup Usage", lambda: service.get_filegroup_usage(threshold_percent=10.0)),
            ("Blocked Sessions", service.get_blocked_sessions),
            ("Backup Status", lambda: service.get_backup_status(days_threshold=1)),
            ("Job Failures", lambda: service.get_job_failures(days_lookback=7)),
            ("Index Fragmentation", lambda: service.get_index_fragmentation(threshold_percent=30.0)),
            ("Statistics Outdated", lambda: service.get_statistics_outdated(modification_threshold=20.0)),
            ("TempDB Usage", service.get_tempdb_usage)
        ]

        results = []

        for kpi_name, kpi_func in kpis:
            print_section(f"Testando: {kpi_name}")

            try:
                start = datetime.now()
                result = kpi_func()
                elapsed = (datetime.now() - start).total_seconds()

                print(f"[OK] {kpi_name} OK ({elapsed:.2f}s)")

                # Mostrar resumo
                if isinstance(result, dict):
                    for key, value in list(result.items())[:3]:  # Primeiros 3 keys
                        if isinstance(value, (int, float, str)):
                            print(f"   {key}: {value}")
                        elif isinstance(value, list):
                            print(f"   {key}: {len(value)} items")

                results.append((kpi_name, "OK", elapsed))

            except Exception as e:
                print(f"[FAIL] {kpi_name} FALHOU: {e}")
                logger.debug(f"Erro detalhado:", exc_info=True)
                results.append((kpi_name, "FALHOU", 0))

        # Resumo
        print_section("Resumo dos Testes")

        total = len(results)
        passed = sum(1 for _, status, _ in results if status == "OK")
        failed = total - passed
        total_time = sum(elapsed for _, _, elapsed in results)

        print(f"\nTotal de KPIs testados: {total}")
        print(f"[OK] Passou: {passed}")
        print(f"[FAIL] Falhou: {failed}")
        print(f"[TIME]  Tempo total: {total_time:.2f}s")
        print(f"[TIME]  Tempo médio: {total_time/total:.2f}s")

        # Tabela de resultados
        print("\nDetalhes:")
        print(f"{'KPI':<30} {'Status':<10} {'Tempo (s)':<10}")
        print("-" * 50)
        for kpi_name, status, elapsed in results:
            status_icon = "[OK]" if status == "OK" else "[FAIL]"
            print(f"{status_icon} {kpi_name:<28} {status:<10} {elapsed:>8.2f}")

        return passed == total

    except Exception as e:
        print(f"[FAIL] Erro ao testar KPIs: {e}")
        logger.error("Erro detalhado:", exc_info=True)
        return False


def test_dashboard():
    """Testa dashboard completo"""
    print_header("4. TESTANDO DASHBOARD COMPLETO")

    try:
        from services.sqlserver_kpi_service import SQLServerKPIService

        service = SQLServerKPIService()

        print_section("Coletando dashboard...")
        start = datetime.now()
        dashboard = service.get_dashboard()
        elapsed = (datetime.now() - start).total_seconds()

        print(f"[OK] Dashboard coletado em {elapsed:.2f}s")

        # Verificar estrutura
        print_section("Verificando estrutura...")

        if "timestamp" in dashboard:
            print(f"[OK] Timestamp: {dashboard['timestamp']}")
        else:
            print("[FAIL] Timestamp ausente")

        if "instance" in dashboard:
            print(f"[OK] Instance: {dashboard['instance']}")
        else:
            print("[FAIL] Instance ausente")

        if "kpis" in dashboard:
            kpis = dashboard["kpis"]
            print(f"[OK] KPIs: {len(kpis)} encontrados")

            # Listar KPIs
            for kpi_name, kpi_data in kpis.items():
                if isinstance(kpi_data, dict) and "error" in kpi_data:
                    print(f"   [FAIL] {kpi_name}: {kpi_data['error']}")
                else:
                    print(f"   [OK] {kpi_name}")
        else:
            print("[FAIL] KPIs ausentes")

        # Verificar se dashboard é válido
        is_valid = (
            "timestamp" in dashboard and
            "instance" in dashboard and
            "kpis" in dashboard and
            len(dashboard["kpis"]) >= 10  # Pelo menos 10 KPIs
        )

        if is_valid:
            print("\n[OK] Dashboard VÁLIDO")
            print(f"[TIME]  Performance: {elapsed:.2f}s (esperado: < 2s)")

            if elapsed < 2.0:
                print("   [OK] Performance excelente!")
            elif elapsed < 5.0:
                print("   [WARN]  Performance aceitável")
            else:
                print("   [FAIL] Performance abaixo do esperado")
        else:
            print("\n[FAIL] Dashboard INVÁLIDO")

        return is_valid

    except Exception as e:
        print(f"[FAIL] Erro ao testar dashboard: {e}")
        logger.error("Erro detalhado:", exc_info=True)
        return False


def main():
    """Função principal"""
    print_header("TESTE SQL SERVER KPI SERVICE")
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Verificar se está no diretório correto
    if not os.path.exists("services/sqlserver_kpi_service.py"):
        print("\n[FAIL] ERRO: Execute este script no diretório raiz do projeto (WATCHERDB_DEV)")
        print("   cd WATCHERDB_DEV")
        print("   python test_sqlserver_kpi.py")
        return 1

    # Tentar carregar .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("[OK] Arquivo .env carregado")
    except ImportError:
        print("[WARN] python-dotenv nao instalado (usando variaveis de sistema)")
    except Exception as e:
        print(f"[WARN] Erro ao carregar .env: {e}")

    # Executar testes
    tests = [
        ("Pré-requisitos", check_prerequisites),
        ("Conexão", test_connection),
        ("KPIs Individuais", test_kpis),
        ("Dashboard Completo", test_dashboard)
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))

            if not result:
                print(f"\n[WARN]  Teste '{test_name}' falhou. Interrompendo testes subsequentes.")
                break

        except Exception as e:
            print(f"\n[FAIL] Exceção no teste '{test_name}': {e}")
            logger.error("Erro detalhado:", exc_info=True)
            results.append((test_name, False))
            break

    # Resumo final
    print_header("RESUMO FINAL")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    print(f"\nTestes executados: {total}/{len(tests)}")
    print(f"[OK] Passou: {passed}")
    print(f"[FAIL] Falhou: {total - passed}")

    print("\nDetalhes:")
    for test_name, result in results:
        status_icon = "[OK]" if result else "[FAIL]"
        status_text = "PASSOU" if result else "FALHOU"
        print(f"  {status_icon} {test_name}: {status_text}")

    # Testes não executados
    remaining = len(tests) - total
    if remaining > 0:
        print(f"\n[WARN]  {remaining} teste(s) não executado(s) devido a falhas anteriores")

    # Status final
    if passed == len(tests):
        print("\n" + "="*70)
        print("  [SUCCESS] TODOS OS TESTES PASSARAM! Sistema pronto para uso.")
        print("="*70)
        return 0
    else:
        print("\n" + "="*70)
        print("  [WARN]  ALGUNS TESTES FALHARAM. Revisar erros acima.")
        print("="*70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
