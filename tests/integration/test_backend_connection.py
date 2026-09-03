#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Teste de Conexao Backend para SQLHDSPRD214\I01
Verifica se o backend consegue conectar e executar as queries TDE
"""

import sys
import asyncio
import os
sys.path.insert(0, '.')

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from modules.monitoring.monitoring import SQLServerExecutor, ConnectionPool, ConnectionInfo
from modules.monitoring.queries import SQLQueries

async def test_server_connection():
    r"""Testa conexao e queries TDE no servidor SQLHDSPRD214\I01"""

    server_id = "SQLHDSPRD214_I01"
    server = "SQLHDSPRD214"
    instance = "I01"

    print("="*80)
    print(f"[TEST] TESTE DE CONEXAO: {server}\\{instance}")
    print("="*80)

    # Criar pool e executor
    pool = ConnectionPool(max_connections=5)
    executor = SQLServerExecutor(pool, max_workers=2)

    # Criar conexo
    conn_info = ConnectionInfo(
        server=server,
        instance=instance,
        database="master",
        use_windows_auth=True
    )

    print(f"\n[CONNECT] Tentando conectar em {server}\\{instance}...")

    # Teste 1: Query TDE_STATUS
    print("\n" + "="*80)
    print("1  TESTE: TDE_STATUS Query")
    print("="*80)
    try:
        result_tde = await executor.execute_query(conn_info, SQLQueries.TDE_STATUS)
        if result_tde:
            print(f" Query executada com sucesso!")
            print(f" Resultados retornados: {len(result_tde)} certificado(s)")
            for idx, cert in enumerate(result_tde, 1):
                print(f"\n   Certificado {idx}:")
                print(f"   - Nome: {cert.get('certificate', 'N/A')}")
                print(f"   - Servidor: {cert.get('Server', 'N/A')}")
                print(f"   - Tipo: {cert.get('pvt_key_encryption_type_desc', 'N/A')}")
                print(f"   - Expira em: {cert.get('expiry_date', 'N/A')}")
        else:
            print(" Query retornou resultado vazio (None)")
    except Exception as e:
        print(f" ERRO ao executar TDE_STATUS: {e}")
        import traceback
        traceback.print_exc()

    # Teste 2: Query TDE_DATABASE_STATUS
    print("\n" + "="*80)
    print("2  TESTE: TDE_DATABASE_STATUS Query")
    print("="*80)
    try:
        result_db = await executor.execute_query(conn_info, SQLQueries.TDE_DATABASE_STATUS)
        if result_db:
            print(f" Query executada com sucesso!")
            print(f" Resultados retornados: {len(result_db)} database(s) encriptada(s)")

            encrypted_count = 0
            for db in result_db:
                is_encrypted = db.get('is_encrypted', 0)
                if is_encrypted == 1 or is_encrypted == True:
                    encrypted_count += 1
                    print(f"\n   Database {encrypted_count}:")
                    print(f"   - Nome: {db.get('database_name', 'N/A')}")
                    print(f"   - Encriptada: {db.get('encryption_status', 'N/A')}")
                    print(f"   - Certificado: {db.get('encryption_certificate', 'N/A')}")
                    print(f"   - Estado: {db.get('encryption_state', 'N/A')}")

            print(f"\n    TOTAL de databases encriptadas: {encrypted_count}")
        else:
            print(" Query retornou resultado vazio (None)")
    except Exception as e:
        print(f" ERRO ao executar TDE_DATABASE_STATUS: {e}")
        import traceback
        traceback.print_exc()

    # Teste 3: Simular estrutura de resposta da API
    print("\n" + "="*80)
    print("3  TESTE: Estrutura JSON da API")
    print("="*80)

    try:
        # Simular resposta do endpoint /api/queries/tde-status/{server_id}
        api_response_tde = {
            "server_id": server_id,
            "tde_status": result_tde if result_tde else []
        }

        # Simular resposta do endpoint /api/queries/tde-database-status/{server_id}
        api_response_db = {
            "server_id": server_id,
            "tde_database_status": result_db if result_db else []
        }

        print(f" Resposta TDE Status:")
        print(f"   - server_id: {api_response_tde['server_id']}")
        print(f"   - tde_status array length: {len(api_response_tde['tde_status'])}")

        print(f"\n Resposta TDE Database Status:")
        print(f"   - server_id: {api_response_db['server_id']}")
        print(f"   - tde_database_status array length: {len(api_response_db['tde_database_status'])}")

        # Simular lgica do frontend
        print("\n" + "="*80)
        print("4  SIMULAO: Lgica do Frontend")
        print("="*80)

        tdeStatus = api_response_tde['tde_status']
        tdeDbStatus = api_response_db['tde_database_status']

        hasTdeCertificate = len(tdeStatus) > 0 and (tdeStatus[0].get('certificate') if tdeStatus else False)

        encryptedDatabases = [
            db for db in tdeDbStatus
            if db.get('is_encrypted') == 1 or
               db.get('is_encrypted') == True or
               db.get('encryption_status') == 'Sim'
        ]
        hasEncryptedDatabases = len(encryptedDatabases) > 0

        tdeActive = hasTdeCertificate or hasEncryptedDatabases

        print(f"    Frontend Analysis:")
        print(f"   - tdeStatus length: {len(tdeStatus)}")
        print(f"   - hasTdeCertificate: {hasTdeCertificate}")
        print(f"   - tdeDbStatus length: {len(tdeDbStatus)}")
        print(f"   - encryptedDatabases count: {len(encryptedDatabases)}")
        print(f"   - hasEncryptedDatabases: {hasEncryptedDatabases}")
        print(f"   -  tdeActive (FINAL): {tdeActive}")

        if tdeActive:
            print(f"\n    Overview deveria mostrar:  Ativo")
        else:
            print(f"\n    Overview deveria mostrar:  Inativo")

    except Exception as e:
        print(f" ERRO na simulao: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)
    print(" TESTE COMPLETO")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(test_server_connection())
