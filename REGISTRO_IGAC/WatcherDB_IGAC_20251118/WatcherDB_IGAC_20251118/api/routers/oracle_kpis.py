#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para KPIs do Oracle
Busca dados das views agregadas do Oracle para exibir no dashboard
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
import logging
import os
import json
from pathlib import Path
from decimal import Decimal

try:
    import oracledb
    ORACLE_AVAILABLE = True
except ImportError as e:
    oracledb = None
    ORACLE_AVAILABLE = False
    logging.warning(f"oracledb não está instalado no ambiente atual. Instale com: pip install oracledb. Erro: {e}")
except Exception as e:
    oracledb = None
    ORACLE_AVAILABLE = False
    logging.warning(f"Erro ao importar oracledb: {e}")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/oracle-kpis", tags=["Oracle KPIs"])

# Configuração de conexão Oracle (do oracle_to_csv.py)
ORACLE_HOST = "oradb_ocrl01.xpto.pt"
ORACLE_PORT = 1521
ORACLE_SERVICE_NAME = "ORACLE_SVC_01"
ORACLE_SCHEMA = "PDBACH_MSSQL_KPI"

# Mapeamento de colunas que precisam de aspas (case-sensitive no Oracle)
# Formato: {view_name: {coluna_sem_aspas: coluna_com_aspas}}
# 
# COMO IDENTIFICAR COLUNAS COM ASPAS:
# 1. Execute: SELECT * FROM view_name LIMIT 1 (ou ROWNUM <= 1 no Oracle)
# 2. Verifique os nomes das colunas retornados
# 3. Se uma coluna tem aspas na definição da view (ex: "AbnormalCnt"), adicione aqui
# 4. Ou use o endpoint /api/oracle-kpis/view-definition/{view_name} para ver a definição
#
COLUMNS_WITH_QUOTES = {
    "KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW": {
        "ABNORMALCNT": '"AbnormalCnt"',
        "AbnormalCnt": '"AbnormalCnt"',
        "abnormalcnt": '"AbnormalCnt"',
        "TOTALCNT": '"TotalCnt"',
        "TotalCnt": '"TotalCnt"',
        "totalcnt": '"TotalCnt"'
    }
    # Adicionar outras views conforme necessário quando descobrir colunas com aspas
    # Exemplo:
    # "KPI_MSSQL_OUTRA_VIEW": {
    #     "COLUNA": '"ColunaComAspas"',
    #     "coluna": '"ColunaComAspas"'
    # }
}

def _get_column_name(view_name: str, column_name: str) -> str:
    """
    Retorna o nome correto da coluna (com aspas se necessário)
    Tenta diferentes variações para encontrar o nome correto
    """
    # Verificar se há mapeamento específico para esta view
    if view_name in COLUMNS_WITH_QUOTES:
        column_upper = column_name.upper()
        
        # Tentar diferentes variações
        for key, quoted_name in COLUMNS_WITH_QUOTES[view_name].items():
            if key.upper() == column_upper:
                return quoted_name
    
    # Se não encontrou mapeamento, retornar o nome original
    # (assumindo que colunas sem aspas funcionam normalmente)
    return column_name

def _build_where_clause(view_name: str, conditions: Dict[str, any]) -> str:
    """
    Constrói cláusula WHERE com nomes de colunas corretos (com aspas se necessário)
    
    Args:
        view_name: Nome da view
        conditions: Dicionário {coluna: valor} ou {coluna: (operador, valor)}
    
    Exemplo:
        _build_where_clause("KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW", {"AbnormalCnt": (">", 0)})
        -> 'WHERE "AbnormalCnt" > 0'
    """
    if not conditions:
        return ""
    
    where_parts = []
    for col, value in conditions.items():
        # Obter nome correto da coluna
        col_name = _get_column_name(view_name, col)
        
        if isinstance(value, tuple):
            # Formato: (operador, valor)
            operator, val = value
            where_parts.append(f'{col_name} {operator} {val}')
        else:
            # Formato simples: valor (usa > 0 por padrão)
            where_parts.append(f'{col_name} > {value}')
    
    return "WHERE " + " OR ".join(where_parts) if where_parts else ""

def _enrich_alwayson_with_serverinstance(instances: List[Dict]) -> List[Dict]:
    """Enriquece dados do Always On com ServerInstance do JSON"""
    try:
        # Carregar alwayson_inventory.json
        config_path = Path("config/alwayson_inventory.json")
        if not config_path.exists():
            logger.warning("alwayson_inventory.json não encontrado, pulando enriquecimento")
            return instances
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        ag_servers = config.get('ag_servers', [])
        if not ag_servers:
            logger.warning("ag_servers vazio no alwayson_inventory.json")
            return instances
        
        # Criar um mapeamento AG_NAME -> ServerInstance (pegar o primeiro encontrado)
        # Se houver múltiplos servidores para o mesmo AG, usar o primeiro (geralmente o primary)
        ag_to_serverinstance = {}
        for ag_server in ag_servers:
            ag_name = ag_server.get('ag_name', '').upper()
            server_instance = ag_server.get('server_instance', '')
            if ag_name and server_instance:
                # Se já existe, manter o primeiro (ou pode ser o primary)
                if ag_name not in ag_to_serverinstance:
                    ag_to_serverinstance[ag_name] = server_instance
        
        # Enriquecer cada instância
        enriched_instances = []
        for instance in instances:
            # Tentar encontrar o AG_NAME na instância
            ag_name = None
            for key in ['AG_NAME', 'ag_name', 'AGNAME', 'agname', 'AG', 'ag']:
                if key in instance and instance[key]:
                    ag_name = str(instance[key]).upper()
                    break
            
            # Se encontrou AG_NAME, buscar ServerInstance
            if ag_name and ag_name in ag_to_serverinstance:
                server_instance = ag_to_serverinstance[ag_name]
                # Adicionar ServerInstance como campo prioritário
                instance['SERVER_INSTANCE'] = server_instance
                instance['server_instance'] = server_instance
                logger.debug(f"Enriquecido {ag_name} com ServerInstance: {server_instance}")
            
            enriched_instances.append(instance)
        
        return enriched_instances
    
    except Exception as e:
        logger.error(f"Erro ao enriquecer dados do Always On: {e}", exc_info=True)
        return instances  # Retornar original em caso de erro

# Endpoint para listar todas as views disponíveis no schema
@router.get("/available-views")
async def list_available_views():
    """Lista todas as views disponíveis no schema PDBACH_MSSQL_KPI para identificar KPIs adicionais"""
    try:
        # Query para listar todas as views do schema
        query = f"""
        SELECT 
            view_name,
            comments as view_comment
        FROM all_views 
        WHERE owner = '{ORACLE_SCHEMA}'
        ORDER BY view_name
        """
        
        views = execute_oracle_query(query, raise_on_error=False)
        
        # Também tentar listar tabelas que podem ter dados úteis
        query_tables = f"""
        SELECT 
            table_name,
            comments as table_comment
        FROM all_tables 
        WHERE owner = '{ORACLE_SCHEMA}'
        ORDER BY table_name
        """
        
        tables = execute_oracle_query(query_tables, raise_on_error=False)
        
        return JSONResponse(content={
            "success": True,
            "schema": ORACLE_SCHEMA,
            "views": views or [],
            "tables": tables or [],
            "views_count": len(views) if views else 0,
            "tables_count": len(tables) if tables else 0
        })
        
    except Exception as e:
        logger.error(f"Erro ao listar views disponíveis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint para obter a definição (query) de uma view específica
@router.get("/view-definition/{view_name}")
async def get_view_definition(view_name: str):
    """Retorna a definição SQL de uma view específica para verificar qual query está sendo usada no SQL Server"""
    try:
        # Usar bind parameter para segurança
        conn = None
        cursor = None
        try:
            conn = get_oracle_connection()
            cursor = conn.cursor()
            cursor.arraysize = 10000
            try:
                cursor.prefetchrows = 10000
            except Exception:
                pass
            
            # Primeiro, verificar se a view existe
            check_query = f"""
            SELECT COUNT(*) as cnt
            FROM all_views 
            WHERE owner = '{ORACLE_SCHEMA}'
            AND view_name = UPPER(:view_name)
            """
            cursor.execute(check_query, {"view_name": view_name})
            check_result = cursor.fetchone()
            
            if not check_result or check_result[0] == 0:
                return JSONResponse(content={
                    "success": False,
                    "error": f"View '{view_name}' não encontrada no schema {ORACLE_SCHEMA}",
                    "view_name": view_name,
                    "definition": None
                })
            
            # View existe, tentar obter definição usando dbms_metadata (método mais confiável)
            definition = None
            try:
                query_metadata = f"""
                SELECT dbms_metadata.get_ddl('VIEW', UPPER(:view_name), '{ORACLE_SCHEMA}') as view_definition
                FROM dual
                """
                cursor.execute(query_metadata, {"view_name": view_name})
                meta_row = cursor.fetchone()
                if meta_row and meta_row[0]:
                    definition = str(meta_row[0])
            except Exception as meta_err:
                logger.warning(f"Não foi possível usar dbms_metadata: {meta_err}")
                # Tentar all_views.text como fallback
                try:
                    text_query = f"""
                    SELECT text 
                    FROM all_views 
                    WHERE owner = '{ORACLE_SCHEMA}'
                    AND view_name = UPPER(:view_name)
                    """
                    cursor.execute(text_query, {"view_name": view_name})
                    text_row = cursor.fetchone()
                    if text_row and text_row[0]:
                        definition = str(text_row[0])
                except Exception as text_err:
                    logger.warning(f"Erro ao obter definição de all_views.text: {text_err}")
            
            if not definition:
                return JSONResponse(content={
                    "success": False,
                    "error": f"View '{view_name}' existe mas não foi possível obter sua definição",
                    "view_name": view_name,
                    "definition": None
                })
            
            # Tentar extrair a query SQL Server da definição (pode estar em um link ou dentro de uma query)
            sql_server_query = None
            if definition:
                # Procurar por padrões comuns:
                # 1. SELECT ... FROM [SQL Server]... (linked server)
                # 2. OPENQUERY(...)
                # 3. Query direta dentro da view
                import re
                
                # Procurar por OPENQUERY
                openquery_match = re.search(r'OPENQUERY\s*\([^,]+,\s*[\'"]([^\'"]+)[\'"]', definition, re.IGNORECASE | re.DOTALL)
                if openquery_match:
                    sql_server_query = openquery_match.group(1)
                    # Limpar escapes
                    sql_server_query = sql_server_query.replace("''", "'").replace('""', '"')
                
                # Se não encontrou OPENQUERY, a view pode estar usando uma tabela que é populada por uma query
                # Nesse caso, precisamos verificar a tabela base (ex: KPI_MSSQL_BLOCKED_SESSIONS)
                # e ver se há uma view detalhada ou documentação sobre como ela é populada
            
            return JSONResponse(content={
                "success": True,
                "view_name": view_name,
                "schema": ORACLE_SCHEMA,
                "definition": definition,
                "definition_lines": definition.split('\n') if definition else [],
                "extracted_sql_server_query": sql_server_query,
                "note": "Se extracted_sql_server_query estiver vazio, a view pode usar linked server ou outra forma de acesso. Verifique a definição completa."
            })
            
        except Exception as e:
            logger.error(f"Erro ao buscar definição da view {view_name}: {e}", exc_info=True)
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        
    except Exception as e:
        logger.error(f"Erro ao obter definição da view: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/view-columns/{view_name}")
async def get_view_columns(view_name: str):
    """
    Retorna as colunas de uma view e identifica quais têm aspas (case-sensitive)
    Útil para descobrir quais colunas precisam de aspas nas queries
    """
    try:
        # Executar query para obter uma linha e ver os nomes das colunas
        query = f"SELECT * FROM {ORACLE_SCHEMA}.{view_name} WHERE ROWNUM <= 1"
        result = execute_oracle_query(query, raise_on_error=False)
        
        if not result:
            # Tentar sem WHERE se a view não tiver dados
            query = f"SELECT * FROM {ORACLE_SCHEMA}.{view_name}"
            result = execute_oracle_query(query, raise_on_error=False)
        
        columns_info = []
        columns = []
        if result and len(result) > 0:
            # Obter nomes das colunas do primeiro resultado
            columns = list(result[0].keys())
        
        # Buscar definição da view para verificar quais têm aspas
        definition = ""
        try:
            conn = get_oracle_connection()
            cursor = conn.cursor()
            try:
                meta_query = f"""
                SELECT dbms_metadata.get_ddl('VIEW', UPPER(:view_name), UPPER(:schema)) as ddl
                FROM dual
                """
                cursor.execute(meta_query, {"view_name": view_name, "schema": ORACLE_SCHEMA})
                meta_row = cursor.fetchone()
                if meta_row and meta_row[0]:
                    definition = str(meta_row[0])
            except:
                try:
                    text_query = f"""
                    SELECT text 
                    FROM all_views 
                    WHERE owner = UPPER(:schema)
                    AND view_name = UPPER(:view_name)
                    """
                    cursor.execute(text_query, {"schema": ORACLE_SCHEMA, "view_name": view_name})
                    text_row = cursor.fetchone()
                    if text_row and text_row[0]:
                        definition = str(text_row[0])
                except:
                    pass
            finally:
                cursor.close()
                conn.close()
        except:
            pass
        
        # Procurar por colunas com aspas na definição
        for col in columns:
            # Verificar se a coluna tem aspas na definição
            has_quotes = False
            if definition:
                # Procurar por padrões: "Coluna" ou "COLUNA" ou "coluna"
                has_quotes = (
                    f'"{col}"' in definition or 
                    f'"{col.upper()}"' in definition or 
                    f'"{col.lower()}"' in definition or
                    f'"{col.title()}"' in definition
                )
            
            columns_info.append({
                "column_name": col,
                "has_quotes_in_definition": has_quotes,
                "recommended_usage": f'"{col}"' if has_quotes else col,
                "note": "Use aspas se has_quotes_in_definition for True"
            })
        
        return JSONResponse(content={
            "success": True,
            "view_name": view_name,
            "columns": columns_info,
            "total_columns": len(columns_info),
            "mapping_for_code": {
                view_name: {
                    col["column_name"].upper(): col["recommended_usage"] 
                    for col in columns_info if col["has_quotes_in_definition"]
                }
            } if any(col["has_quotes_in_definition"] for col in columns_info) else {}
        })
        
    except Exception as e:
        logger.error(f"Erro ao buscar colunas da view {view_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint para buscar definições de múltiplas views de uma vez
@router.get("/view-definitions/batch")
async def get_multiple_view_definitions():
    """Busca definições de todas as views principais do Oracle KPI para análise e alinhamento"""
    views_to_check = [
        "KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW",
        "KPI_MSSQL_DISK_USAGE_AGG_VIEW",
        "KPI_MSSQL_TLOG_USAGE_AGG_VIEW",
        "KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW",
        "KPI_MSSQL_FG_USAGE_AGG_VIEW",
        "KPI_MSSQL_BACKUP_STATUS_AGG_VIEW",
        "KPI_MSSQL_BACKUP_FAILURES_AGG_VIEW",
        "KPI_MSSQL_JOB_FAILURES_AGG_VIEW",
        "KPI_MSSQL_SQL_AGENT_JOBS_AGG_VIEW",
        "KPI_MSSQL_INDEX_FRAGMENTATION_AGG_VIEW",
        "KPI_MSSQL_STATISTICS_OUTDATED_AGG_VIEW",
        "KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW",
        "KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW"
    ]
    
    results = {}
    
    for view_name in views_to_check:
        try:
            conn = None
            cursor = None
            try:
                conn = get_oracle_connection()
                cursor = conn.cursor()
                cursor.arraysize = 10000
                try:
                    cursor.prefetchrows = 10000
                except Exception:
                    pass
                
                # Primeiro, verificar se a view existe
                check_query = f"""
                SELECT COUNT(*) as cnt
                FROM all_views 
                WHERE owner = '{ORACLE_SCHEMA}'
                AND view_name = UPPER(:view_name)
                """
                cursor.execute(check_query, {"view_name": view_name})
                check_result = cursor.fetchone()
                
                if check_result and check_result[0] > 0:
                    # View existe, tentar obter definição usando dbms_metadata
                    try:
                        metadata_query = f"""
                        SELECT dbms_metadata.get_ddl('VIEW', UPPER(:view_name), '{ORACLE_SCHEMA}') as view_definition
                        FROM dual
                        """
                        cursor.execute(metadata_query, {"view_name": view_name})
                        meta_row = cursor.fetchone()
                        
                        if meta_row and meta_row[0]:
                            definition = str(meta_row[0])
                            
                            # Tentar extrair query SQL Server
                            sql_server_query = None
                            if definition:
                                import re
                                # Procurar por OPENQUERY
                                openquery_match = re.search(r'OPENQUERY\s*\([^,]+,\s*[\'"]([^\'"]+)[\'"]', definition, re.IGNORECASE | re.DOTALL)
                                if openquery_match:
                                    sql_server_query = openquery_match.group(1)
                                    sql_server_query = sql_server_query.replace("''", "'").replace('""', '"')
                                
                                # Também procurar por SELECT direto (pode estar em uma subquery)
                                # Procurar por padrões como: SELECT ... FROM (SELECT ... FROM [linked_server]...)
                                
                            results[view_name] = {
                                "found": True,
                                "definition": definition,
                                "extracted_sql_server_query": sql_server_query
                            }
                        else:
                            # Se dbms_metadata não funcionou, tentar all_views.text (pode ser LONG)
                            try:
                                text_query = f"""
                                SELECT text 
                                FROM all_views 
                                WHERE owner = '{ORACLE_SCHEMA}'
                                AND view_name = UPPER(:view_name)
                                """
                                cursor.execute(text_query, {"view_name": view_name})
                                text_row = cursor.fetchone()
                                if text_row and text_row[0]:
                                    definition = str(text_row[0])
                                    results[view_name] = {
                                        "found": True,
                                        "definition": definition,
                                        "extracted_sql_server_query": None,
                                        "note": "Definição obtida de all_views.text (dbms_metadata não retornou dados)"
                                    }
                                else:
                                    results[view_name] = {
                                        "found": False,
                                        "error": "View existe mas não foi possível obter definição"
                                    }
                            except Exception as text_err:
                                results[view_name] = {
                                    "found": False,
                                    "error": f"View existe mas erro ao obter definição: {str(text_err)}"
                                }
                    except Exception as meta_err:
                        logger.warning(f"Erro ao usar dbms_metadata para {view_name}: {meta_err}")
                        results[view_name] = {
                            "found": False,
                            "error": f"View existe mas erro ao obter definição: {str(meta_err)}"
                        }
                else:
                    results[view_name] = {
                        "found": False,
                        "error": "View não encontrada em all_views"
                    }
                    
            except Exception as e:
                logger.warning(f"Erro ao buscar view {view_name}: {e}")
                results[view_name] = {
                    "found": False,
                    "error": str(e)
                }
            finally:
                if cursor:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                        
        except Exception as e:
            logger.error(f"Erro ao processar view {view_name}: {e}")
            results[view_name] = {
                "found": False,
                "error": str(e)
            }
    
    return JSONResponse(content={
        "success": True,
        "schema": ORACLE_SCHEMA,
        "views": results,
        "summary": {
            "total": len(views_to_check),
            "found": sum(1 for v in results.values() if v.get("found")),
            "not_found": sum(1 for v in results.values() if not v.get("found"))
        }
    })

def _make_dsn(host: str, port: int, service_name: Optional[str] = None, sid: Optional[str] = None) -> str:
    """Cria DSN do Oracle - mesma lógica do oracle_to_csv.py"""
    if service_name:
        return oracledb.makedsn(host=host, port=port, service_name=service_name)
    if sid:
        return oracledb.makedsn(host=host, port=port, sid=sid)
    raise ValueError("Informe service_name ou sid para montar o DSN.")

def get_oracle_connection():
    """Cria conexão com Oracle usando a mesma lógica do oracle_to_csv.py
    Usa credenciais de variáveis de ambiente ou fallback para as credenciais padrão"""
    if oracledb is None or not ORACLE_AVAILABLE:
        raise RuntimeError("oracledb não está instalado no ambiente Python atual. "
                          "Instale com: pip install oracledb. "
                          "Se estiver usando venv, ative o venv antes de instalar.")
    
    dsn = _make_dsn(
        host=ORACLE_HOST,
        port=ORACLE_PORT,
        service_name=ORACLE_SERVICE_NAME
    )
    
    # Tentar buscar de variáveis de ambiente primeiro
    user = os.getenv("ORACLE_USER")
    password = os.getenv("ORACLE_PASSWORD")

    # Validar que credenciais foram fornecidas
    if not user or not password:
        # Log detalhado para ajudar no diagnóstico
        missing = []
        if not user:
            missing.append("ORACLE_USER")
        if not password:
            missing.append("ORACLE_PASSWORD")
        
        logger.warning(f"Oracle credentials not configured. Missing: {', '.join(missing)}")
        logger.warning("Configure as variáveis de ambiente e REINICIE o servidor no mesmo terminal.")
        raise ValueError(
            f"Oracle credentials not configured. Missing: {', '.join(missing)}. "
            "Please set ORACLE_USER and ORACLE_PASSWORD environment variables "
            "and restart the server in the same terminal where you configured them."
        )
    
    try:
        connection = oracledb.connect(user=user, password=password, dsn=dsn)
        logger.debug(f"Conexão Oracle estabelecida com sucesso para {user}@{ORACLE_HOST}")
        return connection
    except oracledb.DatabaseError as db_err:
        err = getattr(db_err, "args", [None])[0]
        msg = getattr(err, "message", str(db_err))
        logger.error(f"Erro ao conectar no Oracle: {msg}")
        raise RuntimeError(f"Erro ao conectar no Oracle: {msg}")
    except PermissionError as perm_err:
        logger.error(f"Erro de permissão ao conectar no Oracle (possível bloqueio do Windows): {perm_err}")
        raise RuntimeError(
            f"Erro de permissão ao conectar no Oracle. "
            f"O Windows pode estar bloqueando o acesso. "
            f"Verifique as configurações de 'Controlled folder access' no Windows Security. "
            f"Erro: {perm_err}"
        )
    except Exception as e:
        logger.error(f"Erro inesperado ao conectar no Oracle: {e}", exc_info=True)
        raise RuntimeError(f"Erro ao conectar no Oracle: {e}")

def _serialize_result(obj):
    """Serializa objetos para JSON (converte Decimal, etc)"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _serialize_result(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_result(item) for item in obj]
    elif hasattr(obj, 'isoformat'):  # datetime
        return obj.isoformat()
    return obj

def execute_oracle_query(query: str, raise_on_error: bool = True) -> List[Dict]:
    """Executa query no Oracle e retorna resultados como lista de dicionários
    Usa a mesma lógica de conexão e otimizações do oracle_to_csv.py
    
    Args:
        query: Query SQL a ser executada
        raise_on_error: Se True, lança HTTPException em caso de erro. Se False, retorna lista vazia.
    """
    conn = None
    cursor = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        
        # Aplicar otimizações de fetch (mesma do oracle_to_csv.py)
        cursor.arraysize = 10000
        try:
            cursor.prefetchrows = 10000
        except Exception:
            pass
        
        cursor.execute(query)
        
        # Obter nomes das colunas
        columns = [desc[0] for desc in cursor.description]
        
        # Buscar todos os resultados
        rows = cursor.fetchall()
        
        # Converter para lista de dicionários
        results = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            results.append(_serialize_result(row_dict))
        
        return results
    except RuntimeError as runtime_exc:
        # Erro de credenciais ou conexão - não quebrar o endpoint
        error_msg = str(runtime_exc)
        if "oracledb não está instalado" in error_msg or "oracledb library not available" in error_msg:
            # Log apenas uma vez, nível WARNING para visibilidade (evitar poluição de logs)
            if not hasattr(execute_oracle_query, '_oracledb_warning_logged'):
                logger.warning("oracledb não está instalado. Instale com: pip install oracledb")
                execute_oracle_query._oracledb_warning_logged = True
            if raise_on_error:
                raise HTTPException(status_code=500, detail="oracledb não está instalado. Instale com: pip install oracledb")
            return []
        elif "Credenciais ausentes" in error_msg or "Credenciais Oracle ausentes" in error_msg or "Oracle credentials not configured" in error_msg:
            # Log apenas uma vez, nível WARNING para visibilidade
            if not hasattr(execute_oracle_query, '_credentials_warning_logged'):
                logger.warning(f"Oracle credentials not configured (expected when not using Oracle): {error_msg}")
                execute_oracle_query._credentials_warning_logged = True
            if raise_on_error:
                raise HTTPException(status_code=500, detail=error_msg)
            return []
        else:
            logger.error(f"Erro de runtime ao executar query Oracle: {error_msg}", exc_info=True)
            if raise_on_error:
                raise HTTPException(status_code=500, detail=f"Erro ao consultar Oracle: {error_msg}")
            return []
    except oracledb.DatabaseError as db_exc:
        err = getattr(db_exc, "args", [None])[0]
        msg = getattr(err, "message", str(db_exc))
        
        # ORA-00942: table or view does not exist - comum quando tentamos views alternativas
        # Se raise_on_error=False, tratar como warning silencioso
        if "ORA-00942" in str(msg) or "table or view does not exist" in str(msg).lower():
            if not raise_on_error:
                # View não existe - esperado quando tentamos alternativas, não logar como erro
                return []
            else:
                # Se raise_on_error=True, ainda logar como warning (não error)
                logger.warning(f"View/tabela não encontrada no Oracle: {msg}")
                raise HTTPException(status_code=404, detail=f"View/tabela não encontrada: {msg}")
        
        # Outros erros de banco - logar normalmente
        logger.error(f"Erro de banco ao executar query Oracle: {msg}", exc_info=True)
        if raise_on_error:
            raise HTTPException(status_code=500, detail=f"Erro ao consultar Oracle: {msg}")
        return []
    except Exception as e:
        logger.error(f"Erro ao executar query Oracle: {e}", exc_info=True)
        if raise_on_error:
            raise HTTPException(status_code=500, detail=f"Erro ao consultar Oracle: {str(e)}")
        return []
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

@router.get("/test-connection")
async def test_oracle_connection():
    """Testa a conexão com o Oracle e retorna status detalhado"""
    try:
        # Verificar se oracledb está instalado
        if oracledb is None or not ORACLE_AVAILABLE:
            import sys
            python_path = sys.executable
            python_version = sys.version
            return JSONResponse(content={
                "success": False,
                "error": "oracledb não está instalado no ambiente Python atual",
                "message": "Instale com: pip install oracledb",
                "python_info": {
                    "executable": python_path,
                    "version": python_version,
                    "oracledb_available": ORACLE_AVAILABLE
                },
                "hint": "Se estiver usando venv, certifique-se de ativar o venv antes de instalar: venv\\Scripts\\activate (Windows) ou source venv/bin/activate (Linux/Mac)"
            })
        
        # Verificar variáveis de ambiente
        user = os.getenv("ORACLE_USER")
        password = os.getenv("ORACLE_PASSWORD")
        
        config_status = {
            "oracledb_installed": True,
            "oracle_host": ORACLE_HOST,
            "oracle_port": ORACLE_PORT,
            "oracle_service_name": ORACLE_SERVICE_NAME,
            "oracle_schema": ORACLE_SCHEMA,
            "oracle_user_set": bool(user),
            "oracle_password_set": bool(password),
            "dsn": _make_dsn(host=ORACLE_HOST, port=ORACLE_PORT, service_name=ORACLE_SERVICE_NAME)
        }
        
        if not user or not password:
            return JSONResponse(content={
                "success": False,
                "error": "Credenciais Oracle não configuradas",
                "message": "Configure as variáveis de ambiente ORACLE_USER e ORACLE_PASSWORD",
                "config": config_status
            })
        
        # Tentar conectar
        try:
            conn = get_oracle_connection()
            cursor = conn.cursor()
            
            # Testar query simples
            cursor.execute("SELECT 1 FROM DUAL")
            result = cursor.fetchone()
            
            # Testar acesso ao schema
            cursor.execute(f"SELECT COUNT(*) FROM ALL_OBJECTS WHERE OWNER = '{ORACLE_SCHEMA}'")
            object_count = cursor.fetchone()[0]
            
            # Testar se a view Always On existe
            cursor.execute(f"""
                SELECT COUNT(*) 
                FROM ALL_VIEWS 
                WHERE OWNER = '{ORACLE_SCHEMA}' 
                AND VIEW_NAME = 'KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW'
            """)
            view_exists = cursor.fetchone()[0] > 0
            
            # Se a view existe, contar registros
            record_count = 0
            if view_exists:
                cursor.execute(f"SELECT COUNT(*) FROM {ORACLE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW")
                record_count = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            return JSONResponse(content={
                "success": True,
                "message": "Conexão Oracle funcionando corretamente",
                "config": config_status,
                "test_results": {
                    "connection_test": "OK",
                    "query_test": "OK",
                    "schema_accessible": True,
                    "objects_in_schema": object_count,
                    "alwayson_view_exists": view_exists,
                    "alwayson_view_records": record_count if view_exists else None
                }
            })
            
        except oracledb.DatabaseError as db_exc:
            err = getattr(db_exc, "args", [None])[0]
            msg = getattr(err, "message", str(db_exc))
            return JSONResponse(content={
                "success": False,
                "error": "Erro ao conectar no Oracle",
                "error_type": "DatabaseError",
                "error_message": msg,
                "config": config_status
            })
        except Exception as e:
            return JSONResponse(content={
                "success": False,
                "error": "Erro inesperado",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "config": config_status
            })
            
    except Exception as e:
        logger.error(f"Erro ao testar conexão Oracle: {e}", exc_info=True)
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        })

@router.get("/dashboard")
async def get_kpi_dashboard():
    """Retorna todos os KPIs agregados para o dashboard"""
    try:
        # Executar todas as queries em paralelo seria ideal, mas por simplicidade vamos fazer sequencial
        # Para produção, considere usar asyncio.gather com queries assíncronas
        
        results = {
            "db_availability": {
                "abnormal_count": 0,
                "total_count": 0,
                "total_databases": 0,
                "instances": []
            },
            "db_disk_file_system": {
                "critical_count": 0,
                "warning_count": 0,
                "instances": []
            },
            "db_transaction_logs": {
                "critical_count": 0,
                "warning_count": 0,
                "instances": []
            },
            "always_on": {
                "unhealthy_count": 0,
                "instances": []
            },
            "filegroup_usage": {
                "warning_count": 0,
                "critical_count": 0,
                "instances": []
            },
            "blocked_sessions": {
                "count": 0,
                "instances": []
            },
            "blocked_users": {
                "count": 0,
                "instances": []
            },
            "processes_alarm": {
                "count": 0,
                "instances": []
            },
            "lock_count": {
                "warning_count": 0,
                "critical_count": 0,
                "instances": []
            },
            "instance_availability": {
                "off_count": 0,
                "instances": []
            },
            "backup_status": {
                "failed_count": 0,
                "delayed_count": 0,
                "instances": []
            },
            "job_failures": {
                "failed_jobs_count": 0,
                "instances": []
            },
            "index_fragmentation": {
                "high_fragmentation_count": 0,
                "instances": []
            },
            "statistics_outdated": {
                "outdated_count": 0,
                "instances": []
            },
            "tempdb_usage": {
                "high_usage_count": 0,
                "instances": []
            }
        }
        
        # DB Availability
        try:
            # Query otimizada: filtrar no SQL ao invés de Python
            # Usar nome correto da coluna com aspas (case-sensitive)
            abnormal_col = _get_column_name("KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW", "AbnormalCnt")
            query_abnormal = f'SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW WHERE {abnormal_col} > 0'
            abnormal_instances = execute_oracle_query(query_abnormal, raise_on_error=False) or []
            results["db_availability"]["abnormal_count"] = len(abnormal_instances)
            results["db_availability"]["instances"] = abnormal_instances
            
            # Contar bases de dados disponíveis por ambiente (ENV = 'PRD' e "AbnormalCnt" = '0')
            # Esta é a query correta para DB Availability: contar databases disponíveis em produção
            try:
                totalcnt_col = _get_column_name("KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW", "TotalCnt")
                abnormal_col = _get_column_name("KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW", "AbnormalCnt")
                
                # Query para PRD: contar databases disponíveis (AbnormalCnt = '0')
                query_prd = f'''SELECT SUM({totalcnt_col}) as TOTAL_DATABASES 
                                FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW 
                                WHERE ENV = 'PRD' AND {abnormal_col} = '0' '''
                prd_data = execute_oracle_query(query_prd, raise_on_error=False)
                prd_count = prd_data[0].get('TOTAL_DATABASES', 0) if prd_data and prd_data[0].get('TOTAL_DATABASES') is not None else 0
                
                # Query para TST
                query_tst = f'''SELECT SUM({totalcnt_col}) as TOTAL_DATABASES 
                                FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW 
                                WHERE ENV = 'TST' AND {abnormal_col} = '0' '''
                tst_data = execute_oracle_query(query_tst, raise_on_error=False)
                tst_count = tst_data[0].get('TOTAL_DATABASES', 0) if tst_data and tst_data[0].get('TOTAL_DATABASES') is not None else 0
                
                # Query para QLT
                query_qlt = f'''SELECT SUM({totalcnt_col}) as TOTAL_DATABASES 
                                FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW 
                                WHERE ENV = 'QLT' AND {abnormal_col} = '0' '''
                qlt_data = execute_oracle_query(query_qlt, raise_on_error=False)
                qlt_count = qlt_data[0].get('TOTAL_DATABASES', 0) if qlt_data and qlt_data[0].get('TOTAL_DATABASES') is not None else 0
                
                # Total geral (soma de todos os ambientes)
                total_available = prd_count + tst_count + qlt_count
                
                # Armazenar valores por ambiente
                results["db_availability"]["total_databases"] = prd_count  # Valor principal (PRD)
                results["db_availability"]["total_count"] = prd_count  # Mantido para compatibilidade
                results["db_availability"]["by_environment"] = {
                    "PRD": prd_count,
                    "TST": tst_count,
                    "QLT": qlt_count,
                    "TOTAL": total_available
                }
                
                # Total de instâncias (para referência, mas não é o valor principal)
                query_total_instances = f"SELECT COUNT(*) as TOTAL FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW"
                total_instances_data = execute_oracle_query(query_total_instances, raise_on_error=False)
                results["db_availability"]["total_instances"] = total_instances_data[0].get('TOTAL', 0) if total_instances_data else 0
                
                # Contar instâncias OK (AbnormalCnt = 0)
                query_ok_instances = f'SELECT COUNT(*) as TOTAL FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW WHERE {abnormal_col} = 0'
                ok_instances_data = execute_oracle_query(query_ok_instances, raise_on_error=False)
                results["db_availability"]["ok_instances_count"] = ok_instances_data[0].get('TOTAL', 0) if ok_instances_data else 0
                
                # Adicionar metadados explicativos
                results["db_availability"]["description"] = "Número de bases de dados disponíveis em produção (PRD) onde AbnormalCnt = 0"
                results["db_availability"]["description_by_env"] = f"PRD: {prd_count}, TST: {tst_count}, QLT: {qlt_count}"
                results["db_availability"]["query_prd"] = query_prd
                results["db_availability"]["query_tst"] = query_tst
                results["db_availability"]["query_qlt"] = query_qlt
                results["db_availability"]["query_abnormal"] = query_abnormal
                results["db_availability"]["query_ok_instances"] = query_ok_instances
            except Exception as e:
                logger.warning(f"Erro ao buscar databases disponíveis por ambiente, usando fallback: {e}")
                # Fallback: se as queries falharem, usar query simples mas ainda filtrar no SQL
                abnormal_col = _get_column_name("KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW", "AbnormalCnt")
                query_all = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW WHERE ENV = 'PRD' AND {abnormal_col} = '0'"
                all_data = execute_oracle_query(query_all, raise_on_error=False) or []
                
                # Calcular SUM manualmente no Python como fallback
                totalcnt_col = _get_column_name("KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW", "TotalCnt")
                total_databases = 0
                for row in all_data:
                    # Tentar diferentes variações do nome da coluna
                    totalcnt_value = row.get('TotalCnt') or row.get('TOTALCNT') or row.get('totalcnt') or row.get(totalcnt_col.replace('"', '')) or 0
                    if isinstance(totalcnt_value, (int, float, Decimal)):
                        total_databases += int(totalcnt_value)
                
                results["db_availability"]["total_databases"] = total_databases
                results["db_availability"]["total_count"] = total_databases  # Compatibilidade
                results["db_availability"]["by_environment"] = {
                    "PRD": total_databases,
                    "TST": 0,
                    "QLT": 0,
                    "TOTAL": total_databases
                }
                results["db_availability"]["description"] = "Número de bases de dados disponíveis em produção (PRD) onde AbnormalCnt = 0 (fallback)"
                results["db_availability"]["query_abnormal"] = query_abnormal
                # Tentar contar instâncias OK mesmo no fallback
                try:
                    query_ok_instances = f'SELECT COUNT(*) as TOTAL FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW WHERE {abnormal_col} = 0'
                    ok_instances_data = execute_oracle_query(query_ok_instances, raise_on_error=False)
                    results["db_availability"]["ok_instances_count"] = ok_instances_data[0].get('TOTAL', 0) if ok_instances_data else 0
                except:
                    results["db_availability"]["ok_instances_count"] = 0
        except Exception as e:
            logger.error(f"Erro ao buscar DB Availability: {e}")
            # Garantir que ok_instances_count existe mesmo em caso de erro
            if "ok_instances_count" not in results["db_availability"]:
                results["db_availability"]["ok_instances_count"] = 0
        
        # DB Disk File System
        try:
            # Buscar todos os dados e filtrar em Python (colunas podem variar)
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_DISK_USAGE_AGG_VIEW"
            disk_data = execute_oracle_query(query, raise_on_error=False) or []
            # Filtrar usando colunas que podem existir (CRITICAL, WARNING, HIGH, etc)
            critical_instances = []
            warning_instances = []
            for row in disk_data:
                row_keys_upper = [k.upper() for k in row.keys()]
                # Verificar diferentes possíveis nomes de colunas
                is_critical = False
                is_warning = False
                if 'CRITICAL' in row_keys_upper and row.get('CRITICAL', 0) > 0:
                    is_critical = True
                elif 'HIGH' in row_keys_upper and row.get('HIGH', 0) > 0:
                    is_critical = True
                if 'WARNING' in row_keys_upper and row.get('WARNING', 0) > 0:
                    is_warning = True
                elif 'MEDIUM' in row_keys_upper and row.get('MEDIUM', 0) > 0:
                    is_warning = True
                
                if is_critical:
                    critical_instances.append(row)
                elif is_warning:
                    warning_instances.append(row)
            
            results["db_disk_file_system"]["critical_count"] = len(critical_instances)
            results["db_disk_file_system"]["warning_count"] = len(warning_instances)
            results["db_disk_file_system"]["instances"] = critical_instances + warning_instances
        except HTTPException as http_exc:
            logger.warning(f"Erro ao buscar Disk File System: {http_exc.detail}")
        except Exception as e:
            logger.error(f"Erro ao buscar Disk File System: {e}")
        
        # DB Transaction Logs
        try:
            # Buscar todos os dados e filtrar em Python (colunas podem variar)
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_TLOG_USAGE_AGG_VIEW"
            tlog_data = execute_oracle_query(query, raise_on_error=False) or []
            # Filtrar usando colunas que podem existir (CRITICAL, WARNING, HIGH, etc)
            critical_instances = []
            warning_instances = []
            for row in tlog_data:
                row_keys_upper = [k.upper() for k in row.keys()]
                # Verificar diferentes possíveis nomes de colunas
                is_critical = False
                is_warning = False
                if 'CRITICAL' in row_keys_upper and row.get('CRITICAL', 0) > 0:
                    is_critical = True
                elif 'HIGH' in row_keys_upper and row.get('HIGH', 0) > 0:
                    is_critical = True
                if 'WARNING' in row_keys_upper and row.get('WARNING', 0) > 0:
                    is_warning = True
                elif 'MEDIUM' in row_keys_upper and row.get('MEDIUM', 0) > 0:
                    is_warning = True
                
                if is_critical:
                    critical_instances.append(row)
                elif is_warning:
                    warning_instances.append(row)
            
            results["db_transaction_logs"]["critical_count"] = len(critical_instances)
            results["db_transaction_logs"]["warning_count"] = len(warning_instances)
            results["db_transaction_logs"]["instances"] = critical_instances + warning_instances
        except HTTPException as http_exc:
            logger.warning(f"Erro ao buscar Transaction Logs: {http_exc.detail}")
        except Exception as e:
            logger.error(f"Erro ao buscar Transaction Logs: {e}")
        
        # Always On
        try:
            # Primeiro, buscar TODOS os registros para ver o que existe
            query_all = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW"
            all_instances = execute_oracle_query(query_all, raise_on_error=False) or []
            logger.info(f"Always On - Total de registros na view: {len(all_instances)}")
            
            if all_instances:
                # Log da estrutura do primeiro registro para debug
                first_row = all_instances[0]
                logger.debug(f"Always On - Estrutura do primeiro registro: {list(first_row.keys())}")
                logger.debug(f"Always On - Primeiro registro completo: {first_row}")
            
            # Query otimizada: filtrar no SQL
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW WHERE UNHEALTHY > 0"
            unhealthy_instances = execute_oracle_query(query, raise_on_error=False) or []
            
            # Se a query com WHERE retornou vazio, mas temos registros, verificar manualmente
            if len(unhealthy_instances) == 0 and len(all_instances) > 0:
                logger.debug("Always On - Query com WHERE UNHEALTHY > 0 retornou vazio, verificando manualmente...")
                # Tentar diferentes nomes de coluna possíveis
                for row in all_instances:
                    row_keys_upper = [k.upper() for k in row.keys()]
                    # Verificar diferentes possíveis nomes de coluna
                    unhealthy_value = 0
                    if 'UNHEALTHY' in row_keys_upper:
                        unhealthy_value = row.get('UNHEALTHY', 0) or row.get('unhealthy', 0) or 0
                    elif 'UNHEALTHY_COUNT' in row_keys_upper:
                        unhealthy_value = row.get('UNHEALTHY_COUNT', 0) or row.get('unhealthy_count', 0) or 0
                    elif 'PRI_SYNCH_HEALTH' in row_keys_upper or 'SEC_SYNCH_HEALTH' in row_keys_upper:
                        # Verificar se há réplicas não saudáveis
                        pri_health = row.get('PRI_SYNCH_HEALTH', '') or row.get('pri_synch_health', '')
                        sec_health = row.get('SEC_SYNCH_HEALTH', '') or row.get('sec_synch_health', '')
                        if pri_health and pri_health.upper() != 'HEALTHY':
                            unhealthy_value = 1
                        elif sec_health and sec_health.upper() != 'HEALTHY':
                            unhealthy_value = 1
                    
                    if unhealthy_value > 0:
                        unhealthy_instances.append(row)
                        logger.debug(f"Always On - Instância unhealthy encontrada: {row}")
            
            results["always_on"]["unhealthy_count"] = len(unhealthy_instances)
            results["always_on"]["instances"] = unhealthy_instances
            
            logger.info(f"Always On - Instâncias unhealthy encontradas: {len(unhealthy_instances)}")
            
        except HTTPException as http_exc:
            logger.warning(f"Erro ao buscar Always On: {http_exc.detail}")
        except Exception as e:
            logger.error(f"Erro ao buscar Always On: {e}", exc_info=True)
        
        # FileGroup Usage
        try:
            # Buscar todos os dados e filtrar em Python (colunas podem variar)
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_FG_USAGE_AGG_VIEW"
            fg_data = execute_oracle_query(query, raise_on_error=False) or []
            # Filtrar usando colunas que podem existir (CRITICAL, WARNING, HIGH, etc)
            critical_instances = []
            warning_instances = []
            for row in fg_data:
                row_keys_upper = [k.upper() for k in row.keys()]
                # Verificar diferentes possíveis nomes de colunas
                is_critical = False
                is_warning = False
                if 'CRITICAL' in row_keys_upper and row.get('CRITICAL', 0) > 0:
                    is_critical = True
                elif 'HIGH' in row_keys_upper and row.get('HIGH', 0) > 0:
                    is_critical = True
                if 'WARNING' in row_keys_upper and row.get('WARNING', 0) > 0:
                    is_warning = True
                elif 'MEDIUM' in row_keys_upper and row.get('MEDIUM', 0) > 0:
                    is_warning = True
                
                if is_critical:
                    critical_instances.append(row)
                elif is_warning:
                    warning_instances.append(row)
            
            results["filegroup_usage"]["warning_count"] = len(warning_instances)
            results["filegroup_usage"]["critical_count"] = len(critical_instances)
            results["filegroup_usage"]["instances"] = warning_instances + critical_instances
        except HTTPException as http_exc:
            logger.warning(f"Erro ao buscar FileGroup Usage: {http_exc.detail}")
        except Exception as e:
            logger.error(f"Erro ao buscar FileGroup Usage: {e}")
        
        # Blocked Sessions
        try:
            # Query otimizada: filtrar no SQL e usar SUM no SQL também
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WHERE CNT > 0"
            blocked_instances = execute_oracle_query(query, raise_on_error=False) or []
            results["blocked_sessions"]["count"] = sum(row.get('CNT', 0) for row in blocked_instances)
            results["blocked_sessions"]["instances"] = blocked_instances
        except Exception as e:
            logger.error(f"Erro ao buscar Blocked Sessions: {e}")
        
        # Blocked Users (pode usar a mesma view de blocked sessions ou uma view específica)
        try:
            # Query otimizada: filtrar no SQL
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WHERE CNT > 0"
            blocked_data = execute_oracle_query(query, raise_on_error=False) or []
            # Se houver coluna de usuário, contar usuários únicos bloqueados
            # Por enquanto, usar o mesmo count de blocked sessions
            results["blocked_users"]["count"] = len(blocked_data)
            results["blocked_users"]["instances"] = blocked_data
        except Exception as e:
            logger.error(f"Erro ao buscar Blocked Users: {e}")
        
        # Instance Availability
        try:
            # Tentar usar a view detalhada primeiro (tem mais informações, incluindo nome da instância)
            try:
                query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW"
                inst_avail_data = execute_oracle_query(query, raise_on_error=False)
            except:
                # Se falhar, usar a view agregada
                query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW"
                inst_avail_data = execute_oracle_query(query, raise_on_error=False)
            
            # Log da estrutura da primeira linha para debug (apenas em modo debug)
            if inst_avail_data and len(inst_avail_data) > 0:
                logger.debug(f"Estrutura da view Instance Availability: {list(inst_avail_data[0].keys())}")
                logger.debug(f"Primeira linha de exemplo: {inst_avail_data[0]}")
            
            # Assumindo que há uma coluna que indica instâncias OFF
            # Verificar várias possibilidades de nomes de colunas
            off_instances = []
            for row in inst_avail_data:
                row_keys_upper = [k.upper() for k in row.keys()]
                
                is_off = False
                # Verificar diferentes possíveis nomes de colunas
                if 'COUNT_OFF' in row_keys_upper and row.get('COUNT_OFF', 0) > 0:
                    is_off = True
                elif 'OFF_COUNT' in row_keys_upper and row.get('OFF_COUNT', 0) > 0:
                    is_off = True
                elif 'STATE' in row_keys_upper and str(row.get('STATE', '')).upper() == 'OFF':
                    is_off = True
                elif 'STATUS' in row_keys_upper and str(row.get('STATUS', '')).upper() == 'OFF':
                    is_off = True
                elif 'AVAILABILITY_STATUS' in row_keys_upper and str(row.get('AVAILABILITY_STATUS', '')).upper() == 'OFF':
                    is_off = True
                elif 'INSTANCE_STATUS' in row_keys_upper and str(row.get('INSTANCE_STATUS', '')).upper() == 'OFF':
                    is_off = True
                # Se houver coluna CNT ou COUNT, verificar se > 0
                elif 'CNT' in row_keys_upper and row.get('CNT', 0) > 0:
                    is_off = True
                elif 'COUNT' in row_keys_upper and row.get('COUNT', 0) > 0:
                    is_off = True
                
                if is_off:
                    # Garantir que temos o nome da instância - tentar várias colunas possíveis
                    instance_name = None
                    for key in ['INSTANCE', 'instance', 'INSTANCE_NAME', 'instance_name', 'SERVER_NAME', 'server_name', 'HOST', 'host']:
                        if key in row and row[key]:
                            instance_name = str(row[key])
                            break
                    
                    # Se não encontrou nome, tentar construir a partir de outras colunas
                    if not instance_name:
                        # Tentar combinar HOST + INSTANCE ou SERVER + INSTANCE
                        host = row.get('HOST') or row.get('host') or row.get('SERVER') or row.get('server') or ''
                        inst = row.get('INSTANCE') or row.get('instance') or ''
                        if host and inst:
                            instance_name = f"{host}\\{inst}"
                        elif host:
                            instance_name = host
                    
                    # Adicionar o nome da instância ao row se não estiver presente
                    if instance_name and 'INSTANCE' not in row_keys_upper:
                        row['INSTANCE'] = instance_name
                    
                    off_instances.append(row)
            
            results["instance_availability"]["off_count"] = len(off_instances)
            results["instance_availability"]["instances"] = off_instances
            
            logger.debug(f"Instance Availability: {len(off_instances)} instâncias OFF encontradas de {len(inst_avail_data)} total")
        except Exception as e:
            logger.error(f"Erro ao buscar Instance Availability: {e}", exc_info=True)
        
        # Processes Alarm (pode não ter view específica, deixar como 0 por enquanto)
        # Se houver uma view específica, adicionar aqui
        
        # Lock Count (pode não ter view específica, deixar como 0 por enquanto)
        # Se houver uma view específica, adicionar aqui
        
        # Backup Status
        try:
            backup_views = [
                f"{ORACLE_SCHEMA}.KPI_MSSQL_BACKUP_STATUS_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_BACKUP_FAILURES_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_BACKUP_AGG_VIEW"
            ]
            backup_data = []
            for view_name in backup_views:
                try:
                    query = f"SELECT * FROM {view_name}"
                    backup_data = execute_oracle_query(query, raise_on_error=False)
                    if backup_data:
                        logger.info(f"View de Backup encontrada: {view_name}")
                        break
                except:
                    continue
            
            if backup_data:
                failed_instances = []
                delayed_instances = []
                for row in backup_data:
                    row_keys_upper = [k.upper() for k in row.keys()]
                    is_failed = False
                    is_delayed = False
                    
                    if 'FAILED' in row_keys_upper and row.get('FAILED', 0) > 0:
                        is_failed = True
                    elif 'FAILED_COUNT' in row_keys_upper and row.get('FAILED_COUNT', 0) > 0:
                        is_failed = True
                    elif 'STATUS' in row_keys_upper and 'FAIL' in str(row.get('STATUS', '')).upper():
                        is_failed = True
                    
                    if 'DELAYED' in row_keys_upper and row.get('DELAYED', 0) > 0:
                        is_delayed = True
                    elif 'DELAYED_COUNT' in row_keys_upper and row.get('DELAYED_COUNT', 0) > 0:
                        is_delayed = True
                    elif 'BACKUP_DELAY' in row_keys_upper and row.get('BACKUP_DELAY', 0) > 0:
                        is_delayed = True
                    
                    if is_failed:
                        failed_instances.append(row)
                    if is_delayed:
                        delayed_instances.append(row)
                
                results["backup_status"]["failed_count"] = len(failed_instances)
                results["backup_status"]["delayed_count"] = len(delayed_instances)
                results["backup_status"]["instances"] = list({id(row): row for row in failed_instances + delayed_instances}.values())
        except Exception as e:
            logger.error(f"Erro ao buscar Backup Status: {e}", exc_info=True)
        
        # Job Failures (SQL Agent)
        try:
            job_views = [
                f"{ORACLE_SCHEMA}.KPI_MSSQL_JOB_FAILURES_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_SQL_AGENT_JOBS_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_JOBS_FAILED_AGG_VIEW"
            ]
            job_data = []
            for view_name in job_views:
                try:
                    query = f"SELECT * FROM {view_name}"
                    job_data = execute_oracle_query(query, raise_on_error=False)
                    if job_data:
                        logger.info(f"View de Jobs encontrada: {view_name}")
                        break
                except:
                    continue
            
            if job_data:
                failed_job_instances = []
                for row in job_data:
                    row_keys_upper = [k.upper() for k in row.keys()]
                    if 'FAILED' in row_keys_upper and row.get('FAILED', 0) > 0:
                        failed_job_instances.append(row)
                    elif 'FAILED_COUNT' in row_keys_upper and row.get('FAILED_COUNT', 0) > 0:
                        failed_job_instances.append(row)
                    elif 'CNT' in row_keys_upper and row.get('CNT', 0) > 0:
                        failed_job_instances.append(row)
                
                results["job_failures"]["failed_jobs_count"] = len(failed_job_instances)
                results["job_failures"]["instances"] = failed_job_instances
        except Exception as e:
            logger.error(f"Erro ao buscar Job Failures: {e}", exc_info=True)
        
        # Index Fragmentation
        try:
            frag_views = [
                f"{ORACLE_SCHEMA}.KPI_MSSQL_INDEX_FRAGMENTATION_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_FRAGMENTATION_AGG_VIEW"
            ]
            frag_data = []
            for view_name in frag_views:
                try:
                    query = f"SELECT * FROM {view_name}"
                    frag_data = execute_oracle_query(query, raise_on_error=False)
                    if frag_data:
                        logger.info(f"View de Fragmentação encontrada: {view_name}")
                        break
                except:
                    continue
            
            if frag_data:
                high_frag_instances = []
                for row in frag_data:
                    row_keys_upper = [k.upper() for k in row.keys()]
                    if 'HIGH' in row_keys_upper and row.get('HIGH', 0) > 0:
                        high_frag_instances.append(row)
                    elif 'WARNING' in row_keys_upper and row.get('WARNING', 0) > 0:
                        high_frag_instances.append(row)
                    elif 'CRITICAL' in row_keys_upper and row.get('CRITICAL', 0) > 0:
                        high_frag_instances.append(row)
                    elif 'CNT' in row_keys_upper and row.get('CNT', 0) > 0:
                        high_frag_instances.append(row)
                
                results["index_fragmentation"]["high_fragmentation_count"] = len(high_frag_instances)
                results["index_fragmentation"]["instances"] = high_frag_instances
        except Exception as e:
            logger.error(f"Erro ao buscar Index Fragmentation: {e}", exc_info=True)
        
        # Statistics Outdated
        try:
            stats_views = [
                f"{ORACLE_SCHEMA}.KPI_MSSQL_STATISTICS_OUTDATED_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_OUTDATED_STATS_AGG_VIEW"
            ]
            stats_data = []
            for view_name in stats_views:
                try:
                    query = f"SELECT * FROM {view_name}"
                    stats_data = execute_oracle_query(query, raise_on_error=False)
                    if stats_data:
                        logger.info(f"View de Statistics encontrada: {view_name}")
                        break
                except:
                    continue
            
            if stats_data:
                outdated_instances = []
                for row in stats_data:
                    row_keys_upper = [k.upper() for k in row.keys()]
                    if 'OUTDATED' in row_keys_upper and row.get('OUTDATED', 0) > 0:
                        outdated_instances.append(row)
                    elif 'CNT' in row_keys_upper and row.get('CNT', 0) > 0:
                        outdated_instances.append(row)
                    elif 'COUNT' in row_keys_upper and row.get('COUNT', 0) > 0:
                        outdated_instances.append(row)
                
                results["statistics_outdated"]["outdated_count"] = len(outdated_instances)
                results["statistics_outdated"]["instances"] = outdated_instances
        except Exception as e:
            logger.error(f"Erro ao buscar Statistics Outdated: {e}", exc_info=True)
        
        # TempDB Usage
        try:
            tempdb_views = [
                f"{ORACLE_SCHEMA}.KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_TEMPDB_AGG_VIEW"
            ]
            tempdb_data = []
            for view_name in tempdb_views:
                try:
                    query = f"SELECT * FROM {view_name}"
                    tempdb_data = execute_oracle_query(query, raise_on_error=False)
                    if tempdb_data:
                        logger.info(f"View de TempDB encontrada: {view_name}")
                        break
                except:
                    continue
            
            if tempdb_data:
                high_usage_instances = []
                for row in tempdb_data:
                    row_keys_upper = [k.upper() for k in row.keys()]
                    if 'HIGH' in row_keys_upper and row.get('HIGH', 0) > 0:
                        high_usage_instances.append(row)
                    elif 'WARNING' in row_keys_upper and row.get('WARNING', 0) > 0:
                        high_usage_instances.append(row)
                    elif 'CRITICAL' in row_keys_upper and row.get('CRITICAL', 0) > 0:
                        high_usage_instances.append(row)
                    elif 'USAGE_PERCENT' in row_keys_upper and row.get('USAGE_PERCENT', 0) > 80:
                        high_usage_instances.append(row)
                
                results["tempdb_usage"]["high_usage_count"] = len(high_usage_instances)
                results["tempdb_usage"]["instances"] = high_usage_instances
        except Exception as e:
            logger.error(f"Erro ao buscar TempDB Usage: {e}", exc_info=True)
        
        return JSONResponse(content={
            "success": True,
            "data": results
        })
        
    except Exception as e:
        logger.error(f"Erro ao buscar KPIs do dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/instances/{kpi_type}")
async def get_problematic_instances(kpi_type: str, all: bool = Query(False, description="Retornar todas as instâncias, não apenas as problemáticas")):
    """Retorna instâncias com problema para um tipo específico de KPI"""
    try:
        kpi_type = kpi_type.lower()
        instances = []
        
        if kpi_type == "db-availability" or kpi_type == "db-availability-ok":
            # Obter nome correto da coluna ENV
            env_col = _get_column_name("KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW", "ENV")
            if all:
                # Para o card "Total", retornar todas as instâncias ordenadas por ENV
                query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW ORDER BY {env_col}"
                instances = execute_oracle_query(query, raise_on_error=False)
            elif kpi_type == "db-availability-ok":
                # Para o card "Instâncias OK", retornar apenas as OK (AbnormalCnt = 0) ordenadas por ENV
                abnormal_col = _get_column_name("KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW", "AbnormalCnt")
                query = f'SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW WHERE {abnormal_col} = 0 ORDER BY {env_col}'
                instances = execute_oracle_query(query, raise_on_error=False)
            else:
                # Para o card "Abnormal", retornar apenas as anormais ordenadas por ENV
                # Usar nome correto da coluna com aspas (case-sensitive)
                abnormal_col = _get_column_name("KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW", "AbnormalCnt")
                query = f'SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW WHERE {abnormal_col} > 0 ORDER BY {env_col}'
                instances = execute_oracle_query(query, raise_on_error=False)
        elif kpi_type == "disk-file-system":
            # Buscar todos e filtrar em Python (coluna CRITICAL pode não existir)
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_DISK_USAGE_AGG_VIEW"
            all_data = execute_oracle_query(query, raise_on_error=False) or []
            instances = []
            for row in all_data:
                row_keys_upper = [k.upper() for k in row.keys()]
                if ('CRITICAL' in row_keys_upper and row.get('CRITICAL', 0) > 0) or \
                   ('WARNING' in row_keys_upper and row.get('WARNING', 0) > 0) or \
                   ('HIGH' in row_keys_upper and row.get('HIGH', 0) > 0) or \
                   ('MEDIUM' in row_keys_upper and row.get('MEDIUM', 0) > 0):
                    instances.append(row)
        elif kpi_type == "transaction-logs":
            # Buscar todos e filtrar em Python (coluna CRITICAL pode não existir)
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_TLOG_USAGE_AGG_VIEW"
            all_data = execute_oracle_query(query, raise_on_error=False) or []
            instances = []
            for row in all_data:
                row_keys_upper = [k.upper() for k in row.keys()]
                if ('CRITICAL' in row_keys_upper and row.get('CRITICAL', 0) > 0) or \
                   ('WARNING' in row_keys_upper and row.get('WARNING', 0) > 0) or \
                   ('HIGH' in row_keys_upper and row.get('HIGH', 0) > 0) or \
                   ('MEDIUM' in row_keys_upper and row.get('MEDIUM', 0) > 0):
                    instances.append(row)
        elif kpi_type == "always-on":
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW WHERE UNHEALTHY > 0"
            instances = execute_oracle_query(query)
        elif kpi_type == "filegroup-usage":
            # Buscar todos e filtrar em Python (coluna CRITICAL pode não existir)
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_FG_USAGE_AGG_VIEW"
            all_data = execute_oracle_query(query, raise_on_error=False) or []
            instances = []
            for row in all_data:
                row_keys_upper = [k.upper() for k in row.keys()]
                if ('CRITICAL' in row_keys_upper and row.get('CRITICAL', 0) > 0) or \
                   ('WARNING' in row_keys_upper and row.get('WARNING', 0) > 0) or \
                   ('HIGH' in row_keys_upper and row.get('HIGH', 0) > 0) or \
                   ('MEDIUM' in row_keys_upper and row.get('MEDIUM', 0) > 0):
                    instances.append(row)
        elif kpi_type == "blocked-sessions":
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WHERE CNT > 0"
            instances = execute_oracle_query(query)
        elif kpi_type == "blocked-users":
            # Usar a mesma view de blocked sessions por enquanto
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WHERE CNT > 0"
            instances = execute_oracle_query(query)
        elif kpi_type == "processes-alarm":
            # Se houver uma view específica, usar aqui
            instances = []
        elif kpi_type == "lock-count":
            # Se houver uma view específica, usar aqui
            instances = []
        elif kpi_type == "instance-availability":
            # Tentar usar a view detalhada primeiro (tem mais informações)
            try:
                query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW"
                all_instances = execute_oracle_query(query)
            except:
                # Se falhar, usar a view agregada
                query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW"
                all_instances = execute_oracle_query(query)
            
            # Filtrar instâncias que estão OFF
            instances = []
            for row in all_instances:
                row_keys_upper = [k.upper() for k in row.keys()]
                
                is_off = False
                # Verificar diferentes possíveis nomes de colunas
                if 'COUNT_OFF' in row_keys_upper and row.get('COUNT_OFF', 0) > 0:
                    is_off = True
                elif 'OFF_COUNT' in row_keys_upper and row.get('OFF_COUNT', 0) > 0:
                    is_off = True
                elif 'STATE' in row_keys_upper and str(row.get('STATE', '')).upper() == 'OFF':
                    is_off = True
                elif 'STATUS' in row_keys_upper and str(row.get('STATUS', '')).upper() == 'OFF':
                    is_off = True
                elif 'AVAILABILITY_STATUS' in row_keys_upper and str(row.get('AVAILABILITY_STATUS', '')).upper() == 'OFF':
                    is_off = True
                elif 'INSTANCE_STATUS' in row_keys_upper and str(row.get('INSTANCE_STATUS', '')).upper() == 'OFF':
                    is_off = True
                # Se houver coluna CNT ou COUNT, verificar se > 0
                elif 'CNT' in row_keys_upper and row.get('CNT', 0) > 0:
                    is_off = True
                elif 'COUNT' in row_keys_upper and row.get('COUNT', 0) > 0:
                    is_off = True
                
                if is_off:
                    # Garantir que temos o nome da instância
                    instance_name = None
                    for key in ['INSTANCE', 'instance', 'INSTANCE_NAME', 'instance_name', 'SERVER_NAME', 'server_name', 'HOST', 'host']:
                        if key in row and row[key]:
                            instance_name = str(row[key])
                            break
                    
                    # Se não encontrou nome, tentar construir
                    if not instance_name:
                        host = row.get('HOST') or row.get('host') or row.get('SERVER') or row.get('server') or ''
                        inst = row.get('INSTANCE') or row.get('instance') or ''
                        if host and inst:
                            instance_name = f"{host}\\{inst}"
                        elif host:
                            instance_name = host
                    
                    # Adicionar o nome da instância ao row se não estiver presente
                    if instance_name and 'INSTANCE' not in row_keys_upper:
                        row['INSTANCE'] = instance_name
                    
                    instances.append(row)
        elif kpi_type == "backup-status":
            backup_views = [
                f"{ORACLE_SCHEMA}.KPI_MSSQL_BACKUP_STATUS_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_BACKUP_FAILURES_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_BACKUP_AGG_VIEW"
            ]
            for view_name in backup_views:
                try:
                    query = f"SELECT * FROM {view_name} WHERE FAILED > 0 OR DELAYED > 0 OR FAILED_COUNT > 0 OR DELAYED_COUNT > 0"
                    instances = execute_oracle_query(query, raise_on_error=False)
                    if instances:
                        break
                except:
                    continue
        elif kpi_type == "job-failures":
            job_views = [
                f"{ORACLE_SCHEMA}.KPI_MSSQL_JOB_FAILURES_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_SQL_AGENT_JOBS_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_JOBS_FAILED_AGG_VIEW"
            ]
            for view_name in job_views:
                try:
                    query = f"SELECT * FROM {view_name} WHERE FAILED > 0 OR FAILED_COUNT > 0 OR CNT > 0"
                    instances = execute_oracle_query(query, raise_on_error=False)
                    if instances:
                        break
                except:
                    continue
        elif kpi_type == "index-fragmentation":
            frag_views = [
                f"{ORACLE_SCHEMA}.KPI_MSSQL_INDEX_FRAGMENTATION_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_FRAGMENTATION_AGG_VIEW"
            ]
            for view_name in frag_views:
                try:
                    # Buscar todos e filtrar em Python (coluna CRITICAL pode não existir)
                    query = f"SELECT * FROM {view_name}"
                    all_data = execute_oracle_query(query, raise_on_error=False) or []
                    instances = []
                    for row in all_data:
                        row_keys_upper = [k.upper() for k in row.keys()]
                        if ('HIGH' in row_keys_upper and row.get('HIGH', 0) > 0) or \
                           ('WARNING' in row_keys_upper and row.get('WARNING', 0) > 0) or \
                           ('CRITICAL' in row_keys_upper and row.get('CRITICAL', 0) > 0) or \
                           ('CNT' in row_keys_upper and row.get('CNT', 0) > 0):
                            instances.append(row)
                    if instances:
                        break
                except:
                    continue
        elif kpi_type == "statistics-outdated":
            stats_views = [
                f"{ORACLE_SCHEMA}.KPI_MSSQL_STATISTICS_OUTDATED_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_OUTDATED_STATS_AGG_VIEW"
            ]
            for view_name in stats_views:
                try:
                    query = f"SELECT * FROM {view_name} WHERE OUTDATED > 0 OR CNT > 0 OR COUNT > 0"
                    instances = execute_oracle_query(query, raise_on_error=False)
                    if instances:
                        break
                except:
                    continue
        elif kpi_type == "tempdb-usage":
            tempdb_views = [
                f"{ORACLE_SCHEMA}.KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW",
                f"{ORACLE_SCHEMA}.KPI_MSSQL_TEMPDB_AGG_VIEW"
            ]
            for view_name in tempdb_views:
                try:
                    # Buscar todos e filtrar em Python (coluna CRITICAL pode não existir)
                    query = f"SELECT * FROM {view_name}"
                    all_data = execute_oracle_query(query, raise_on_error=False) or []
                    instances = []
                    for row in all_data:
                        row_keys_upper = [k.upper() for k in row.keys()]
                        if ('HIGH' in row_keys_upper and row.get('HIGH', 0) > 0) or \
                           ('WARNING' in row_keys_upper and row.get('WARNING', 0) > 0) or \
                           ('CRITICAL' in row_keys_upper and row.get('CRITICAL', 0) > 0) or \
                           ('USAGE_PERCENT' in row_keys_upper and row.get('USAGE_PERCENT', 0) > 80):
                            instances.append(row)
                    if instances:
                        break
                except:
                    continue
        else:
            raise HTTPException(status_code=400, detail=f"Tipo de KPI inválido: {kpi_type}")
        
        # Enriquecer dados do Always On com ServerInstance do JSON
        if kpi_type == "always-on":
            instances = _enrich_alwayson_with_serverinstance(instances)
        
        return JSONResponse(content={
            "success": True,
            "kpi_type": kpi_type,
            "instances": instances,
            "count": len(instances)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar instâncias problemáticas: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/instances/{kpi_type}/details")
async def get_problematic_instances_details(kpi_type: str):
    """Retorna detalhes das instâncias com problema usando a view detalhada (quando disponível)"""
    try:
        kpi_type = kpi_type.lower()
        instances = []
        
        if kpi_type == "instance-availability":
            # Usar a view detalhada para obter mais informações
            query = f"SELECT * FROM {ORACLE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW"
            instances = execute_oracle_query(query)
        else:
            # Para outros tipos, retornar vazio ou usar a view agregada
            return JSONResponse(content={
                "success": True,
                "kpi_type": kpi_type,
                "message": "View detalhada não disponível para este tipo de KPI",
                "instances": [],
                "count": 0
            })
        
        return JSONResponse(content={
            "success": True,
            "kpi_type": kpi_type,
            "instances": instances,
            "count": len(instances)
        })
        
    except Exception as e:
        logger.error(f"Erro ao buscar detalhes das instâncias: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

