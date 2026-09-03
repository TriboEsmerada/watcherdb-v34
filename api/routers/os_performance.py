"""
OS Performance API Router
Endpoints para metricas de Windows OS (Memory, CPU, Disk)
Para responder alertas SCOM como "Memory Pages Per Second is too High"
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime

from api.models import OSPerformanceResponse, GenericResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/os",
    tags=["OS Performance"]
)


def get_service():
    """Obtem instancia do OSPerformanceService"""
    from services.os_performance_service import get_os_performance_service
    return get_os_performance_service()


# ============================================================================
# MEMORY ENDPOINTS
# ============================================================================

@router.get("/{hostname}/memory", response_model=OSPerformanceResponse)
async def get_memory_current(hostname: str):
    """
    Obtem metricas de memoria atuais do servidor

    - **hostname**: Nome do servidor (ex: SQLHDSPRD014)

    Retorna:
    - Available_MB: RAM disponivel
    - Pages_Per_Sec: Total de page faults (soft + hard)
    - Page_Reads_Sec: Hard page faults (critico!)
    - Percent_Committed: % de memoria comprometida
    - Severity: OK, INFO, WARNING, CRITICAL
    """
    try:
        service = get_service()
        result = await service.get_memory_current(hostname)

        if not result:
            return {
                "success": False,
                "error": f"Sem dados de memoria para {hostname}",
                "hostname": hostname,
                "message": "Verificar se o agente de coleta esta funcionando"
            }

        # Converter datetime para string se necessario
        if result.get('Update_TS') and hasattr(result['Update_TS'], 'isoformat'):
            result['Update_TS'] = result['Update_TS'].isoformat()

        return {
            "success": True,
            "hostname": hostname,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_memory_current for {hostname}: {e}")
        return {
            "success": False,
            "error": str(e),
            "hostname": hostname
        }


@router.get("/{hostname}/memory/trend", response_model=OSPerformanceResponse)
async def get_memory_trend(
    hostname: str,
    minutes: int = Query(default=30, ge=5, le=1440, description="Quantidade de minutos para analise")
):
    """
    Obtem tendencia de memoria dos ultimos N minutos

    - **hostname**: Nome do servidor
    - **minutes**: Periodo de analise (default: 30 min, max: 1440 min = 24h)

    Util para determinar se e um spike momentaneo ou problema sustentado
    """
    try:
        service = get_service()
        result = await service.get_memory_trend(hostname, minutes)

        # Converter datetime para string
        for item in result:
            if item.get('Update_TS') and hasattr(item['Update_TS'], 'isoformat'):
                item['Update_TS'] = item['Update_TS'].isoformat()

        return {
            "success": True,
            "hostname": hostname,
            "period_minutes": minutes,
            "data_points": len(result),
            "data": result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_memory_trend for {hostname}: {e}")
        return {
            "success": False,
            "error": str(e),
            "hostname": hostname
        }


@router.get("/{hostname}/diagnosis", response_model=OSPerformanceResponse)
async def get_memory_diagnosis(hostname: str):
    """
    **ENDPOINT PRINCIPAL** para responder alertas SCOM

    Retorna diagnostico completo incluindo:
    - Alert_Classification: Classificacao do alerta
    - Is_Actionable: Se requer acao imediata
    - Recommended_Response: Recomendacao de acao
    - Ticket_Suggestion: Sugestao para tratamento do ticket

    Exemplo de uso:
    ```
    GET /api/os/SQLHDSPRD014/diagnosis
    ```
    """
    try:
        service = get_service()
        result = await service.get_memory_diagnosis(hostname)

        if not result:
            return {
                "success": False,
                "error": f"Sem dados de diagnostico para {hostname}",
                "hostname": hostname,
                "alert_classification": "NO_DATA",
                "is_actionable": False,
                "recommended_response": "Verificar se o agente de coleta esta funcionando",
                "ticket_suggestion": "Aguardar proxima coleta"
            }

        # Converter datetime para string se necessario
        for key, value in result.items():
            if hasattr(value, 'isoformat'):
                result[key] = value.isoformat()

        return {
            "success": True,
            "hostname": hostname,
            "diagnosis": result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_memory_diagnosis for {hostname}: {e}")
        return {
            "success": False,
            "error": str(e),
            "hostname": hostname
        }


# ============================================================================
# CPU ENDPOINTS
# ============================================================================

@router.get("/{hostname}/cpu", response_model=OSPerformanceResponse)
async def get_cpu_current(hostname: str):
    """
    Obtem metricas de CPU atuais do servidor

    - **hostname**: Nome do servidor

    Retorna:
    - Processor_Pct: % de uso total do processador
    - Queue_Length: Tamanho da fila de processos
    - SQL_CPU_Pct: % de CPU usado pelo SQL Server
    """
    try:
        service = get_service()
        result = await service.get_cpu_current(hostname)

        if not result:
            return {
                "success": False,
                "error": f"Sem dados de CPU para {hostname}",
                "hostname": hostname
            }

        # Converter datetime para string
        for key, value in result.items():
            if hasattr(value, 'isoformat'):
                result[key] = value.isoformat()

        return {
            "success": True,
            "hostname": hostname,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_cpu_current for {hostname}: {e}")
        return {
            "success": False,
            "error": str(e),
            "hostname": hostname
        }


# ============================================================================
# DISK ENDPOINTS
# ============================================================================

@router.get("/{hostname}/disk", response_model=OSPerformanceResponse)
async def get_disk_current(hostname: str):
    """
    Obtem metricas de disco atuais do servidor

    - **hostname**: Nome do servidor

    Retorna:
    - Queue_Length: Tamanho da fila de I/O
    - Read_Latency_Ms: Latencia de leitura
    - Write_Latency_Ms: Latencia de escrita
    """
    try:
        service = get_service()
        result = await service.get_disk_current(hostname)

        if not result:
            return {
                "success": False,
                "error": f"Sem dados de disco para {hostname}",
                "hostname": hostname
            }

        # Converter datetime para string
        for key, value in result.items():
            if hasattr(value, 'isoformat'):
                result[key] = value.isoformat()

        return {
            "success": True,
            "hostname": hostname,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_disk_current for {hostname}: {e}")
        return {
            "success": False,
            "error": str(e),
            "hostname": hostname
        }


@router.get("/{hostname}/disk/by-drive", response_model=OSPerformanceResponse)
async def get_disk_by_drive(hostname: str):
    """
    Obtem metricas de disco detalhadas POR DRIVE (C:, D:, E:, etc.)
    Inclui latência sec/Read e sec/Write via Windows Performance Counters

    - **hostname**: Nome do servidor

    Retorna lista de drives com:
    - Avg_Sec_Per_Read: Latência média de leitura em SEGUNDOS
    - Avg_Sec_Per_Write: Latência média de escrita em SEGUNDOS
    - Avg_Read_Latency_MS: Latência em milissegundos (mais legível)
    - Avg_Write_Latency_MS: Latência em milissegundos
    - Disk_Reads_Sec: IOPS de leitura
    - Disk_Writes_Sec: IOPS de escrita
    - Disk_Transfers_Sec: IOPS total
    - Percent_Disk_Time: % tempo ocupado
    - Read_Latency_Status: OK/INFO/WARNING/CRITICAL
    - Write_Latency_Status: OK/INFO/WARNING/CRITICAL

    Thresholds de latência (ms):
    - OK: < 10ms
    - INFO: 10-20ms
    - WARNING: 20-50ms
    - CRITICAL: >= 50ms
    """
    try:
        service = get_service()
        result = await service.get_disk_by_drive(hostname)

        if not result:
            return {
                "success": True,
                "hostname": hostname,
                "drives": [],
                "message": f"Sem dados de disco por drive para {hostname}. Verificar coleta de Performance Counters."
            }

        # Converter datetime para string
        for drive in result:
            for key, value in drive.items():
                if hasattr(value, 'isoformat'):
                    drive[key] = value.isoformat()

        return {
            "success": True,
            "hostname": hostname,
            "drives": result,
            "drive_count": len(result),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_disk_by_drive for {hostname}: {e}")
        return {
            "success": False,
            "error": str(e),
            "hostname": hostname
        }


@router.get("/{hostname}/disk/latency-summary", response_model=OSPerformanceResponse)
async def get_disk_latency_summary(hostname: str):
    """
    Resumo de latência de disco do servidor
    Útil para detectar ciclo de degradação: Memory Pressure -> Paging -> Disk I/O

    - **hostname**: Nome do servidor

    Retorna:
    - Max_Read_Latency_MS: Maior latência de leitura entre todos os drives
    - Max_Write_Latency_MS: Maior latência de escrita
    - Avg_Read_Latency_MS: Latência média de leitura
    - Avg_Write_Latency_MS: Latência média de escrita
    - Total_Drives: Quantidade de drives
    - Drives_With_High_Latency: Drives com latência >= 20ms
    - Problem_Drives: Lista de drives problemáticos
    - Overall_Status: OK/INFO/WARNING/CRITICAL baseado na pior latência
    """
    try:
        service = get_service()
        result = await service.get_disk_latency_summary(hostname)

        if not result:
            return {
                "success": True,
                "hostname": hostname,
                "data": None,
                "message": f"Sem dados de latência de disco para {hostname}"
            }

        return {
            "success": True,
            "hostname": hostname,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_disk_latency_summary for {hostname}: {e}")
        return {
            "success": False,
            "error": str(e),
            "hostname": hostname
        }


# ============================================================================
# CORRELATION ENDPOINTS
# ============================================================================

@router.get("/{hostname}/correlation", response_model=OSPerformanceResponse)
async def get_sql_memory_correlation(hostname: str):
    """
    Correlaciona metricas de memoria OS com SQL Server

    Util para determinar se pressao de memoria OS esta impactando o SQL Server:
    - PLE (Page Life Expectancy) baixo
    - Buffer Pool sendo evictado
    - Memory grants pendentes
    """
    try:
        service = get_service()
        result = await service.get_sql_memory_correlation(hostname)

        if not result:
            return {
                "success": False,
                "error": f"Sem dados de correlacao para {hostname}",
                "hostname": hostname
            }

        # Converter datetime para string
        for key, value in result.items():
            if hasattr(value, 'isoformat'):
                result[key] = value.isoformat()

        return {
            "success": True,
            "hostname": hostname,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_sql_memory_correlation for {hostname}: {e}")
        return {
            "success": False,
            "error": str(e),
            "hostname": hostname
        }


@router.get("/{hostname}/full-correlation", response_model=OSPerformanceResponse)
async def get_full_correlation(hostname: str):
    """
    Correlacao completa: OS Memory + OS CPU + SQL Server

    Dashboard completo para analise de performance
    """
    try:
        service = get_service()
        result = await service.get_full_correlation(hostname)

        if not result:
            return {
                "success": False,
                "error": f"Sem dados de correlacao completa para {hostname}",
                "hostname": hostname
            }

        return {
            "success": True,
            "hostname": hostname,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_full_correlation for {hostname}: {e}")
        return {
            "success": False,
            "error": str(e),
            "hostname": hostname
        }


# ============================================================================
# DASHBOARD ENDPOINTS
# ============================================================================

@router.get("/servers/attention", response_model=GenericResponse)
async def get_servers_needing_attention():
    """
    Lista servidores que precisam de atencao

    Ordenados por severidade (CRITICAL primeiro)
    """
    try:
        service = get_service()
        result = await service.get_servers_needing_attention()

        # Converter datetime para string
        for item in result:
            for key, value in item.items():
                if hasattr(value, 'isoformat'):
                    item[key] = value.isoformat()

        return {
            "success": True,
            "total": len(result),
            "servers": result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_servers_needing_attention: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/dashboard/summary", response_model=GenericResponse)
async def get_os_dashboard_summary():
    """
    Resumo do dashboard de OS Performance

    Retorna:
    - Total de servidores monitorados
    - Servidores por severidade (OK, WARNING, CRITICAL)
    - Top 5 servidores com mais problemas
    """
    try:
        service = get_service()
        attention_servers = await service.get_servers_needing_attention()

        # Contar por severidade
        severity_counts = {'CRITICAL': 0, 'WARNING': 0, 'INFO': 0, 'OK': 0}
        for server in attention_servers:
            sev = server.get('Memory_Severity', 'OK')
            if sev in severity_counts:
                severity_counts[sev] += 1

        # Top 5 servidores com problemas
        top_issues = []
        for server in attention_servers[:5]:
            top_issues.append({
                'hostname': server.get('Hostname'),
                'memory_severity': server.get('Memory_Severity'),
                'page_reads_sec': server.get('Page_Reads_Sec'),
                'available_mb': server.get('Available_MB')
            })

        return {
            "success": True,
            "summary": {
                "total_monitored": len(attention_servers),
                "by_severity": severity_counts,
                "critical_count": severity_counts['CRITICAL'],
                "warning_count": severity_counts['WARNING'],
                "healthy_count": severity_counts['OK'] + severity_counts['INFO']
            },
            "top_issues": top_issues,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in get_os_dashboard_summary: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# THRESHOLDS ENDPOINT
# ============================================================================

@router.get("/thresholds", response_model=GenericResponse)
async def get_thresholds():
    """
    Retorna os thresholds configurados para alertas

    Util para documentacao e configuracao de alertas
    """
    from services.os_performance_service import MEMORY_THRESHOLDS, CPU_THRESHOLDS

    return {
        "success": True,
        "thresholds": {
            "memory": MEMORY_THRESHOLDS,
            "cpu": CPU_THRESHOLDS
        },
        "description": {
            "memory": {
                "available_mb": "RAM disponivel em MB",
                "page_reads_sec": "Hard page faults (leitura do disco) - CRITICO",
                "pages_sec": "Total de page faults (soft + hard)",
                "percent_committed": "% de memoria comprometida vs limite"
            },
            "cpu": {
                "processor_pct": "% de uso total do processador",
                "queue_length": "Tamanho da fila de processos"
            }
        },
        "severity_order": ["OK", "INFO", "WARNING", "CRITICAL"]
    }
