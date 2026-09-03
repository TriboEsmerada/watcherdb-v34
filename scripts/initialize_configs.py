#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Inicialização - Watcher DB
Lê o Excel uma vez e popula os arquivos JSON de configuração.
Após a inicialização, o sistema usa apenas os JSONs (mais rápido).
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys
import os

# Adicionar o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

def load_alwayson_from_excel(excel_path: str, sheet_name: str = "Servers", columns: dict = None) -> list:
    """Carrega servidores Always On do Excel"""
    if columns is None:
        columns = {
            "server": "ServerName",
            "instance": "Instance",
            "server_instance": "ServerInstance",
            "is_always_on": "IsAlwaysOn",
            "ag_name": "AGName",
            "listener": "AGListener"
        }
    
    try:
        if not Path(excel_path).exists():
            print(f"⚠️  Excel não encontrado: {excel_path}")
            return []
        
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        
        # Detectar colunas automaticamente
        server_col = columns.get('server', 'ServerName')
        instance_col = columns.get('instance', 'Instance')
        server_instance_col = columns.get('server_instance', 'ServerInstance')
        ag_name_col = columns.get('ag_name', 'AGName')
        listener_col = columns.get('listener', 'AGListener')
        
        # Auto-detectar colunas se não existirem pelos nomes esperados
        if server_instance_col not in df.columns:
            for col in df.columns:
                col_upper = str(col).upper().replace(' ', '').replace('_', '')
                if 'SERVERINSTANCE' in col_upper:
                    server_instance_col = col
                    print(f"   ℹ️  Coluna ServerInstance detectada: '{col}'")
                    break
        
        if ag_name_col not in df.columns:
            for col in df.columns:
                col_upper = str(col).upper().replace(' ', '').replace('_', '')
                if 'AGNAME' in col_upper or ('AG' in col_upper and 'NAME' in col_upper) or col_upper == 'AG_NAME':
                    ag_name_col = col
                    print(f"   ℹ️  Coluna AG Name detectada: '{col}'")
                    break
        
        if listener_col not in df.columns:
            for col in df.columns:
                col_upper = str(col).upper().replace(' ', '').replace('_', '')
                if 'LISTENER' in col_upper or ('AG' in col_upper and 'LISTENER' in col_upper) or col_upper == 'LISTENERS':
                    listener_col = col
                    print(f"   ℹ️  Coluna Listener detectada: '{col}'")
                    break
        
        # Verificar se as colunas obrigatórias existem
        if ag_name_col not in df.columns or listener_col not in df.columns:
            print(f"   ⚠️  Colunas Always On não encontradas:")
            if ag_name_col not in df.columns:
                print(f"      - AG_NAME não encontrada")
            if listener_col not in df.columns:
                print(f"      - Listeners não encontrada")
            print(f"   💡 Colunas disponíveis: {', '.join(df.columns.tolist())}")
            return []
        
        print(f"   ✅ Coluna AG_NAME: '{ag_name_col}'")
        print(f"   ✅ Coluna Listeners: '{listener_col}'")
        
        ag_servers = []
        
        # Filtrar linhas onde AG_NAME e Listeners estão preenchidos (critério para Always On)
        ag_df = df[df[ag_name_col].notna() & (df[ag_name_col] != '') & 
                   df[listener_col].notna() & (df[listener_col] != '')]
        
        print(f"   📊 {len(ag_df)} linhas com AG_NAME e Listeners preenchidos")
        
        if len(ag_df) > 0:
            
            for _, row in ag_df.iterrows():
                ag_name = str(row.get(ag_name_col, '')) if pd.notna(row.get(ag_name_col)) else ''
                listener = str(row.get(listener_col, '')) if pd.notna(row.get(listener_col)) else ''
                
                # Priorizar ServerInstance se disponível
                server_instance_raw = ''
                server = ''
                instance = ''
                
                if server_instance_col and server_instance_col in df.columns:
                    server_instance_raw = str(row.get(server_instance_col, '')) if pd.notna(row.get(server_instance_col)) else ''
                    if server_instance_raw and '\\' in server_instance_raw:
                        parts = server_instance_raw.split('\\', 1)
                        server = parts[0].strip()
                        instance = parts[1].strip() if len(parts) > 1 else ''
                    elif server_instance_raw and '_' in server_instance_raw:
                        parts = server_instance_raw.rsplit('_', 1)
                        server = parts[0].strip()
                        instance = parts[1].strip() if len(parts) > 1 else ''
                
                if not server:
                    server = str(row.get(server_col, ''))
                    instance = str(row.get(instance_col, '')) if pd.notna(row.get(instance_col)) else ''
                
                if server:
                    ag_servers.append({
                        'server': server,
                        'instance': instance,
                        'server_instance': server_instance_raw,
                        'ag_name': ag_name,
                        'listener': listener
                    })
        
        return ag_servers
    
    except Exception as e:
        print(f"❌ Erro ao carregar Always On do Excel: {e}")
        return []

def load_servers_from_excel(excel_path: str, sheet_name: str = "Servers") -> list:
    """Carrega servidores do Excel para sql_servers.json"""
    try:
        if not Path(excel_path).exists():
            print(f"⚠️  Excel não encontrado: {excel_path}")
            return []
        
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        servers = []
        
        print(f"   📋 Colunas encontradas no Excel: {', '.join(df.columns.tolist())}")
        
        # Mapear colunas (tentar diferentes nomes possíveis)
        server_col = None
        instance_col = None
        server_instance_col = None
        port_col = None
        description_col = None
        environment_col = None
        
        for col in df.columns:
            col_upper = str(col).upper().strip()
            # ServerInstance tem prioridade
            if 'SERVERINSTANCE' in col_upper.replace(' ', ''):
                server_instance_col = col
            elif 'SERVER' in col_upper and ('NAME' in col_upper or 'HOST' in col_upper):
                if not server_col:  # Só atribuir se ainda não tiver
                    server_col = col
            elif 'INSTANCE' in col_upper and 'SERVER' not in col_upper:
                instance_col = col
            elif 'PORT' in col_upper:
                port_col = col
            elif 'DESCRIPTION' in col_upper or 'DESC' in col_upper:
                description_col = col
            elif 'ENVIRONMENT' in col_upper or 'ENV' in col_upper:
                environment_col = col
        
        # Se não encontrou server_col mas encontrou server_instance_col, usar ele
        if not server_col and server_instance_col:
            print(f"   ℹ️  Usando coluna 'ServerInstance' para identificar servidores")
            server_col = server_instance_col
        
        if not server_col:
            print("❌ Coluna de servidor não encontrada no Excel")
            print(f"   💡 Colunas disponíveis: {', '.join(df.columns.tolist())}")
            return []
        
        print(f"   ✅ Coluna de servidor: '{server_col}'")
        if instance_col:
            print(f"   ✅ Coluna de instância: '{instance_col}'")
        if server_instance_col:
            print(f"   ✅ Coluna ServerInstance: '{server_instance_col}'")
        
        for _, row in df.iterrows():
            # Priorizar ServerInstance se disponível
            server_name = ''
            instance = ''
            
            if server_instance_col and pd.notna(row.get(server_instance_col)):
                server_instance_raw = str(row.get(server_instance_col, '')).strip()
                if server_instance_raw and '\\' in server_instance_raw:
                    # Formato: SQLMDMPRD01\101
                    parts = server_instance_raw.split('\\', 1)
                    server_name = parts[0].strip()
                    instance = parts[1].strip() if len(parts) > 1 else ''
                elif server_instance_raw and '_' in server_instance_raw:
                    # Formato alternativo: SQLMDMPRD01_101
                    parts = server_instance_raw.rsplit('_', 1)
                    server_name = parts[0].strip()
                    instance = parts[1].strip() if len(parts) > 1 else ''
                else:
                    server_name = server_instance_raw
            
            # Fallback para colunas separadas
            if not server_name:
                server_name = str(row.get(server_col, '')).strip()
                if instance_col and pd.notna(row.get(instance_col)):
                    instance = str(row.get(instance_col, '')).strip()
            
            if not server_name or server_name == 'nan':
                continue
            
            port = int(row.get(port_col, 1433)) if port_col and pd.notna(row.get(port_col)) else 1433
            description = str(row.get(description_col, '')).strip() if description_col and pd.notna(row.get(description_col)) else ''
            environment = str(row.get(environment_col, '')).strip().lower() if environment_col and pd.notna(row.get(environment_col)) else 'production'
            
            # Construir ID (normalizar para usar underscore)
            if instance:
                server_id = f"{server_name}_{instance}"
            else:
                server_id = server_name
            
            servers.append({
                'id': server_id,
                'host': server_name,
                'instance': instance,
                'port': port,
                'description': description,
                'environment': environment,
                'priority': 1
            })
        
        return servers
    
    except Exception as e:
        print(f"❌ Erro ao carregar servidores do Excel: {e}")
        import traceback
        traceback.print_exc()
        return []

def initialize_configs():
    """Inicializa os arquivos de configuração a partir do Excel"""
    print("=" * 80)
    print("🚀 WATCHER DB - Inicialização de Configurações")
    print("=" * 80)
    print()
    
    # Carregar alwayson_inventory.json atual
    alwayson_config_path = Path("config/alwayson_inventory.json")
    if alwayson_config_path.exists():
        with open(alwayson_config_path, 'r', encoding='utf-8') as f:
            alwayson_config = json.load(f)
    else:
        print("❌ alwayson_inventory.json não encontrado!")
        print("   Use o template: config/alwayson_inventory.json.template")
        return False
    
    excel_path = alwayson_config.get('excel_path', '').replace('\\\\', '\\')
    sheet_name = alwayson_config.get('sheet_name', 'Servers')
    columns = alwayson_config.get('columns', {})
    
    if not excel_path or not Path(excel_path).exists():
        print(f"❌ Excel não encontrado: {excel_path}")
        print("   Verifique o caminho em alwayson_inventory.json")
        return False
    
    print(f"📊 Carregando dados do Excel: {excel_path}")
    print(f"   Planilha: {sheet_name}")
    print()
    
    # 1. Carregar Always On
    print("1️⃣ Carregando servidores Always On...")
    ag_servers = load_alwayson_from_excel(excel_path, sheet_name, columns)
    print(f"   ✅ {len(ag_servers)} servidores Always On encontrados")
    
    # Atualizar alwayson_inventory.json
    alwayson_config['ag_servers'] = ag_servers
    alwayson_config['last_updated'] = datetime.now().isoformat()
    
    with open(alwayson_config_path, 'w', encoding='utf-8') as f:
        json.dump(alwayson_config, f, indent=2, ensure_ascii=False)
    
    print(f"   ✅ alwayson_inventory.json atualizado")
    print()
    
    # 2. Carregar sql_servers.json
    print("2️⃣ Carregando servidores SQL...")
    servers = load_servers_from_excel(excel_path, sheet_name)
    print(f"   ✅ {len(servers)} servidores encontrados")
    
    # Criar estrutura do sql_servers.json
    sql_servers_config = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "source_file": Path(excel_path).name,
            "total_servers": len(servers),
            "version": "1.0"
        },
        "servers": servers
    }
    
    sql_servers_path = Path("config/sql_servers.json")
    # Fazer backup se existir
    if sql_servers_path.exists():
        backup_path = sql_servers_path.with_suffix('.json.backup')
        import shutil
        shutil.copy2(sql_servers_path, backup_path)
        print(f"   📦 Backup criado: {backup_path.name}")
    
    with open(sql_servers_path, 'w', encoding='utf-8') as f:
        json.dump(sql_servers_config, f, indent=2, ensure_ascii=False)
    
    print(f"   ✅ sql_servers.json atualizado")
    print()
    
    print("=" * 80)
    print("✅ INICIALIZAÇÃO CONCLUÍDA!")
    print("=" * 80)
    print()
    print("📋 Resumo:")
    print(f"   - Servidores Always On: {len(ag_servers)}")
    print(f"   - Total de servidores: {len(servers)}")
    print()
    print("💡 Dica: Agora você pode editar os JSONs manualmente se necessário.")
    print("   O sistema não precisará mais ler o Excel (mais rápido!).")
    print()
    
    return True

if __name__ == '__main__':
    try:
        success = initialize_configs()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Inicialização cancelada pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Erro durante inicialização: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

