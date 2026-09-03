"""
WatcherDB Memory Analysis Module
Análise de configuração e uso de memória SQL Server
"""

import pyodbc
import logging
from typing import Dict, List, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

def get_connection_string(server_name: str) -> str:
    """
    Gera string de conexão para o servidor SQL
    Usa o mesmo padrão do sistema WatcherDB existente
    """
    # Usar o padrão de conexão do WatcherDB (mesmo que o monitoring.py)
    return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server_name};Trusted_Connection=yes;Connection Timeout=10;"

def _server_id_from_name(server_name: str) -> str:
    """Converte nome exibido (HOST\\INSTANCIA) para server_id (HOST_INSTANCIA).
    Para instância DEFAULT, retorna apenas o host."""
    if "\\" in server_name:
        host, inst = server_name.split("\\", 1)
        if inst.upper() == "DEFAULT":
            return host
        return f"{host}_{inst}"
    return server_name


async def get_server_memory_analysis(server_name: str, sql_monitoring=None) -> Dict:
    """
    Analisa configuração e uso de memória de um servidor SQL
    
    Args:
        server_name: Nome do servidor (ex: SQLIDSPRD03\\I01)
    
    Returns:
        Dict com análise completa de memória
    """
    
    query = """
    SELECT
        -- RAM Física do Servidor
        physical_ram_gb = CAST(total_physical_memory_kb / 1024.0 / 1024.0 AS DECIMAL(18,2)),
        
        -- Configuração SQL Server
        max_server_memory_mb = (
            SELECT CAST(value_in_use AS BIGINT) 
            FROM sys.configurations 
            WHERE name = 'max server memory (MB)'
        ),
        min_server_memory_mb = (
            SELECT CAST(value_in_use AS BIGINT) 
            FROM sys.configurations 
            WHERE name = 'min server memory (MB)'
        ),
        
        -- Uso Atual de Memória
        target_server_memory_mb = (
            SELECT CAST(cntr_value AS BIGINT) 
            FROM sys.dm_os_performance_counters 
            WHERE counter_name = 'Target Server Memory (KB)' 
            AND object_name LIKE '%Buffer Manager%'
        ) / 1024,
        total_server_memory_mb = (
            SELECT CAST(cntr_value AS BIGINT) 
            FROM sys.dm_os_performance_counters 
            WHERE counter_name = 'Total Server Memory (KB)' 
            AND object_name LIKE '%Buffer Manager%'
        ) / 1024,
        
        -- Working Set do Processo
        process_working_set_mb = CAST(physical_memory_in_use_kb / 1024.0 AS DECIMAL(18,2)),
        
        -- Always On Info
        is_hadr_enabled = CAST(SERVERPROPERTY('IsHadrEnabled') AS INT),
        ag_name = (
            SELECT TOP 1 ag.name 
            FROM sys.dm_hadr_availability_replica_states AS ars
            INNER JOIN sys.availability_groups AS ag ON ars.group_id = ag.group_id
            WHERE ars.is_local = 1
        ),
        replica_role = (
            SELECT TOP 1 
                CASE ars.role 
                    WHEN 1 THEN 'PRIMARY'
                    WHEN 2 THEN 'SECONDARY'
                    ELSE 'RESOLVING'
                END
            FROM sys.dm_hadr_availability_replica_states AS ars
            WHERE ars.is_local = 1
        )
        
    FROM sys.dm_os_sys_memory
    CROSS JOIN sys.dm_os_process_memory;
    """
    
    try:
        logger.info(f"🔍 Analisando memória do servidor: {server_name}")
        
        if sql_monitoring:
            # Usar o sistema de conexão do WatcherDB existente
            server_id = _server_id_from_name(server_name)
            logger.info(f"📊 Executando query de memória em: {server_id}")
            
            # Tentar primeiro com server_id original
            result = await sql_monitoring.execute_query(server_id, query)
            logger.info(f"📊 Resultado da query: {result}")
            
            # Se falhou e é DEFAULT, tentar fallback
            if (not result or not result.get('success')) and server_id.endswith('_DEFAULT'):
                alt_id = server_id.replace('_DEFAULT', '')
                logger.info(f"⚙️ Fallback DEFAULT -> HOST: {server_id} -> {alt_id}")
                result = await sql_monitoring.execute_query(alt_id, query)
                logger.info(f"📊 Resultado do fallback: {result}")
            
            if not result:
                raise Exception(f"Resultado da query é None para {server_name}")
            
            if not result.get('success'):
                raise Exception(f"Query falhou para {server_name}: {result.get('error', 'Erro desconhecido')}")
            
            rows = result.get('rows', [])
            if not rows:
                raise Exception(f"Nenhum dado retornado da query de memória para {server_name}")
            
            row = rows[0]  # Pegar primeira linha
        else:
            # Fallback para conexão direta
            conn_str = get_connection_string(server_name)
            conn = pyodbc.connect(conn_str, timeout=10, autocommit=True)
            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            
            if not row:
                raise Exception("Nenhum dado retornado da query de memória")
        
        # Extrair dados com tratamento de None
        def safe_int(value, default=0):
            return int(value) if value is not None else default
        
        def safe_float(value, default=0.0):
            return float(value) if value is not None else default
        
        data = {
            'physical_ram_gb': safe_float(row.get('physical_ram_gb')),
            'max_server_memory_mb': safe_int(row.get('max_server_memory_mb')),
            'min_server_memory_mb': safe_int(row.get('min_server_memory_mb')),
            'target_server_memory_mb': safe_int(row.get('target_server_memory_mb')),
            'total_server_memory_mb': safe_int(row.get('total_server_memory_mb')),
            'process_working_set_mb': safe_float(row.get('process_working_set_mb')),
            'is_hadr_enabled': safe_int(row.get('is_hadr_enabled')),
            'ag_name': row.get('ag_name'),
            'replica_role': row.get('replica_role')
        }
        
        # Calcular recomendação Microsoft (75% da RAM)
        data['recommendation_max_memory_mb'] = int(data['physical_ram_gb'] * 1024 * 0.75)
        data['reserved_for_os_mb'] = int(data['physical_ram_gb'] * 1024 * 0.25)
        
        # Calcular memory pressure (quanto mais próximo de 100%, melhor!)
        if data['target_server_memory_mb'] > 0:
            data['memory_pressure_pct'] = round(
                (data['total_server_memory_mb'] * 100.0) / data['target_server_memory_mb'], 
                2
            )
        else:
            data['memory_pressure_pct'] = 0
        
        # Status de memory pressure (como tensão das cordas do baixo)
        if data['memory_pressure_pct'] >= 95:
            data['memory_pressure_status'] = 'HEALTHY'  # 🟢 Verde - som limpo
        elif data['memory_pressure_pct'] >= 80:
            data['memory_pressure_status'] = 'WARNING'  # 🟡 Amarelo - som instável
        else:
            data['memory_pressure_status'] = 'CRITICAL'  # 🔴 Vermelho - som cortando
        
        # Gerar alertas
        data['alerts'] = generate_memory_alerts(data)
        
        logger.info(f"✅ Análise de memória concluída: {data['memory_pressure_pct']:.1f}% pressure ({data['memory_pressure_status']})")
        
        if not sql_monitoring:
            # Só fechar conexão se não estivermos usando o sistema WatcherDB
            cursor.close()
            conn.close()
        
        return data
        
    except Exception as e:
        logger.error(f"❌ Erro ao analisar memória do servidor {server_name}: {str(e)}")
        raise Exception(f"Erro ao analisar memória: {str(e)}")


def generate_memory_alerts(data: Dict) -> List[Dict]:
    """Gera alertas baseados na análise de memória"""
    alerts = []
    
    # Alerta 1: Max memory não configurada (padrão: 2147483647 MB)
    if data['max_server_memory_mb'] >= 2147483647:
        alerts.append({
            'level': 'danger',
            'message': '⚠️ Max Server Memory NÃO CONFIGURADA! SQL pode consumir toda RAM do servidor.'
        })
    
    # Alerta 2: Max memory muito alta (acima de 90% - deixar folga para o SO)
    elif data['max_server_memory_mb'] > (data['physical_ram_gb'] * 1024 * 0.90):
        alerts.append({
            'level': 'warning',
            'message': f"Max memory muito alta ({data['max_server_memory_mb']:,} MB). Recomendado: {data['recommendation_max_memory_mb']:,} MB (75% da RAM)"
        })
    
    # Alerta 3: Max memory muito baixa (subutilizada)
    elif data['max_server_memory_mb'] < (data['physical_ram_gb'] * 1024 * 0.50):
        alerts.append({
            'level': 'info',
            'message': 'Max memory pode estar subutilizada. SQL Server tem RAM disponível para uso.'
        })
    
    # Alerta 4: Memory pressure crítica (SQL não consegue alocar memória)
    if data['memory_pressure_pct'] < 80:
        alerts.append({
            'level': 'danger',
            'message': f"🔴 PRESSÃO DE MEMÓRIA CRÍTICA! SQL não consegue alocar memória suficiente ({data['memory_pressure_pct']:.1f}%)"
        })
    elif data['memory_pressure_pct'] < 95:
        alerts.append({
            'level': 'warning',
            'message': f"🟡 Atenção: Memory pressure em {data['memory_pressure_pct']:.1f}%. Considere investigar."
        })
    
    # Alerta 5: Configuração ideal
    if data['memory_pressure_pct'] >= 95 and data['max_server_memory_mb'] == data['recommendation_max_memory_mb']:
        alerts.append({
            'level': 'success',
            'message': f"✅ Configuração IDEAL! Memory pressure em {data['memory_pressure_pct']:.1f}% e max memory otimizada."
        })
    
    return alerts


def get_alwayson_memory_comparison(ag_name: str, servers_list: List[str]) -> Dict:
    """
    Compara configuração de memória entre nodes de um Always On AG
    
    Args:
        ag_name: Nome do Availability Group
        servers_list: Lista de servidores do AG
    
    Returns:
        Dict com comparação entre nodes
    """
    logger.info(f"🔄 Comparando memória entre nodes do AG: {ag_name}")
    
    nodes_data = []
    
    for server in servers_list:
        try:
            data = get_server_memory_analysis(server)
            nodes_data.append({
                'server_name': server,
                'replica_role': data.get('replica_role'),
                'physical_ram_gb': data['physical_ram_gb'],
                'max_server_memory_mb': data['max_server_memory_mb'],
                'memory_pressure_pct': data['memory_pressure_pct'],
                'memory_pressure_status': data['memory_pressure_status']
            })
        except Exception as e:
            logger.warning(f"⚠️ Erro ao analisar {server}: {str(e)}")
            nodes_data.append({
                'server_name': server,
                'error': str(e)
            })
    
    # Verificar consistência (como dois amplificadores em stereo)
    max_memory_values = [
        node['max_server_memory_mb'] 
        for node in nodes_data 
        if 'max_server_memory_mb' in node
    ]
    
    is_consistent = len(set(max_memory_values)) == 1 if max_memory_values else True
    
    result = {
        'ag_name': ag_name,
        'nodes': nodes_data,
        'is_consistent': is_consistent,
        'total_nodes': len(servers_list),
        'successful_nodes': len([n for n in nodes_data if 'error' not in n])
    }
    
    if not is_consistent:
        result['alert'] = {
            'level': 'danger',
            'message': f"⚠️ ALWAYS ON INCONSISTENTE! Nodes do AG '{ag_name}' têm configurações diferentes de memória (como amplificadores desbalanceados)."
        }
    else:
        result['alert'] = {
            'level': 'success',
            'message': f"✅ Always On consistente! Todos os nodes do AG '{ag_name}' têm configuração uniforme de memória."
        }
    
    logger.info(f"✅ Comparação Always On concluída: {result['successful_nodes']}/{result['total_nodes']} nodes, consistente: {is_consistent}")
    
    return result


def get_memory_health_summary(servers_list: List[str]) -> Dict:
    """
    Gera resumo de saúde de memória de múltiplos servidores
    
    Args:
        servers_list: Lista de servidores para analisar
    
    Returns:
        Dict com resumo consolidado
    """
    logger.info(f"📊 Gerando resumo de saúde de memória para {len(servers_list)} servidores")
    
    healthy_count = 0
    warning_count = 0
    critical_count = 0
    total_ram_gb = 0
    total_max_memory_mb = 0
    
    servers_data = []
    
    for server in servers_list:
        try:
            data = get_server_memory_analysis(server)
            servers_data.append(data)
            
            total_ram_gb += data['physical_ram_gb']
            total_max_memory_mb += data['max_server_memory_mb']
            
            if data['memory_pressure_status'] == 'HEALTHY':
                healthy_count += 1
            elif data['memory_pressure_status'] == 'WARNING':
                warning_count += 1
            else:
                critical_count += 1
                
        except Exception as e:
            logger.warning(f"⚠️ Erro ao analisar {server}: {str(e)}")
            servers_data.append({
                'server_name': server,
                'error': str(e)
            })
            critical_count += 1
    
    return {
        'total_servers': len(servers_list),
        'healthy_servers': healthy_count,
        'warning_servers': warning_count,
        'critical_servers': critical_count,
        'total_ram_gb': round(total_ram_gb, 2),
        'total_max_memory_mb': total_max_memory_mb,
        'servers_data': servers_data,
        'health_percentage': round((healthy_count / len(servers_list)) * 100, 2) if servers_list else 0
    }
