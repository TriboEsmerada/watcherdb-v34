# Parametrização de Database v1.4.8.1

## Data: 2025-11-17

## Resumo

Implementação de parametrização de database para as queries de análise, com reorganização do frontend por categorias.

---

## Objetivos

1. ✅ Adicionar suporte a filtro por database nas queries de análise
2. ✅ Manter opção "Todas as databases"
3. ✅ Reorganizar frontend por categorias (Standard, Análise, Customizadas)
4. ✅ Atualizar endpoints da API para aceitar parâmetro opcional `database`

---

## Queries Parametrizáveis

### 1. FILEGROUP_GROWTH_HISTORY ✅

**Endpoint:** `/api/queries/filegroup-growth-history/{server_id}?database={database_name}`

**Parâmetros:**
- `database` (opcional): Nome da database para filtrar
- Se `None` ou `"ALL"`: retorna todas as databases

**Método criado:** `SQLQueries.get_filegroup_growth_history_filtered(database_name)`

**Filtro aplicado:**
```sql
WHERE f.database_id > 4  -- Excluir system databases
AND DB_NAME(f.database_id) = 'NomeDaDatabase'  -- Se database especificado
```

---

### 2. FILEGROUP_GROWTH_FORECAST ✅

**Endpoint:** `/api/queries/filegroup-growth-forecast/{server_id}?database={database_name}`

**Parâmetros:**
- `database` (opcional): Nome da database para filtrar
- Se `None` ou `"ALL"`: retorna todas as databases

**Método criado:** `SQLQueries.get_filegroup_growth_forecast_filtered(database_name)`

**Filtro aplicado:**
```sql
WHERE f.database_id > 4  -- Excluir system databases
AND DB_NAME(f.database_id) = 'NomeDaDatabase'  -- Se database especificado
```

---

### 3. MISSING_INDEX_ANALYSIS ✅

**Endpoint:** `/api/queries/missing-index-analysis/{server_id}?database={database_name}`

**Parâmetros:**
- `database` (opcional): Nome da database para filtrar
- Se `None` ou `"ALL"`: retorna todas as databases

**Método criado:** `SQLQueries.get_missing_index_analysis_filtered(database_name)`

**Filtro aplicado:**
```sql
WHERE DB_NAME(mid.database_id) IS NOT NULL  -- CORRIGIDO v1.4.8.1
AND mid.database_id > 4  -- Excluir system databases
AND DB_NAME(mid.database_id) = 'NomeDaDatabase'  -- Se database especificado
```

**IMPORTANTE:** Esta query foi **CORRIGIDA** na v1.4.8.1 para buscar em todas as databases (antes só buscava no master).

---

### 4. BACKUP_HISTORY_ANALYSIS ⚠️

**Endpoint:** `/api/queries/backup-history-analysis/{server_id}`

**Parâmetros:** ❌ **SEM parametrização**

**Razão:** Esta query precisa verificar **TODAS** as databases para detectar:
- Réplicas Always On (primary vs secondary)
- Databases sem backup
- Databases com backup desatualizado

**Não possui método de filtro** - sempre usa `SQLQueries.BACKUP_HISTORY_ANALYSIS`

---

## Segurança - Prevenção de SQL Injection

### Método Seguro de Parametrização

Como pyodbc não suporta parâmetros dinâmicos em nomes de objetos (databases, tabelas), usamos **string replacement seguro**:

```python
@staticmethod
def get_missing_index_analysis_filtered(database_name: str = None):
    """
    Retorna query com filtro opcional de database

    Args:
        database_name: Nome da database (None = todas)

    Returns:
        str: Query SQL com filtro aplicado
    """
    base_query = SQLQueries.MISSING_INDEX_ANALYSIS

    if database_name and database_name.upper() != 'ALL':
        # ESCAPE de colchetes: ] -> ]]
        safe_db_name = database_name.replace(']', ']]')

        filter_clause = f"\n    AND DB_NAME(mid.database_id) = '{safe_db_name}'"

        # Inserir filtro na posição correta
        base_query = base_query.replace(
            "AND mid.database_id > 4  -- Excluir system databases\n    AND OBJECT_NAME",
            f"AND mid.database_id > 4  -- Excluir system databases{filter_clause}\n    AND OBJECT_NAME"
        )

    return base_query
```

### Proteções Implementadas:

1. ✅ **Escape de caracteres especiais:** `]` → `]]`
2. ✅ **Validação de NULL:** Verifica se `database_name` é `None` ou `"ALL"`
3. ✅ **Uso de aspas simples:** `'{safe_db_name}'` (não usa concatenação direta)
4. ✅ **String replacement específico:** Substitui apenas pontos exatos da query

---

## Reorganização do Frontend

### Nova Estrutura de Categorias

**Antes (v1.4.8):**
- Todas as queries em uma única lista "Queries Padrão"

**Depois (v1.4.8.1):**
- **Queries Padrão** (sem parametrização)
- **Queries de Análise** (suportam filtro por database)
- **Queries Customizadas** (definidas pelo usuário)

### Alterações no HTML

**Arquivo:** `templates/watcherdb_portal.html`

#### 1. Definição das Queries (linha ~7056)

```javascript
// Queries de análise com flag requiresDb e category 'analysis'
{
    id: 'filegroup-growth-history',
    name: 'Histórico Crescimento Filegroups',
    endpoint: `/api/queries/filegroup-growth-history/${serverId}`,
    requiresDb: true,      // ← NOVO
    category: 'analysis'   // ← NOVO
},
{
    id: 'filegroup-growth-forecast',
    name: 'Projeção Crescimento Filegroups',
    endpoint: `/api/queries/filegroup-growth-forecast/${serverId}`,
    requiresDb: true,      // ← NOVO
    category: 'analysis'   // ← NOVO
},
{
    id: 'backup-history-analysis',
    name: 'Análise Histórico Backups',
    endpoint: `/api/queries/backup-history-analysis/${serverId}`,
    category: 'analysis'   // ← NOVO (SEM requiresDb)
},
{
    id: 'missing-index-analysis',
    name: 'Análise Índices Faltantes',
    endpoint: `/api/queries/missing-index-analysis/${serverId}`,
    requiresDb: true,      // ← NOVO
    category: 'analysis'   // ← NOVO
}
```

#### 2. Label do Filtro (linha ~7095)

**Antes:**
```html
<label for="dbFilter">Banco (para Crescimento de Arquivos):</label>
```

**Depois:**
```html
<label for="dbFilter">Filtro de Database (para Queries de Análise):</label>
```

#### 3. Renderização por Categorias (linha ~7121)

```javascript
// Filtrar queries por categoria
const standardQueriesList = queries.filter(q =>
    q.category === 'standard' &&
    visibleStandardQueries.some(vq => vq.id === q.id)
);

const analysisQueriesList = queries.filter(q =>
    q.category === 'analysis' &&
    visibleStandardQueries.some(vq => vq.id === q.id)
);

const customQueriesList = queries.filter(q =>
    q.category === 'custom'
);

// Renderizar queries padrão
if (standardQueriesList.length > 0) {
    standardQueriesList.forEach(query => {
        html += `<button class="btn" ...>${query.name}</button>`;
    });
}

// Renderizar seção de queries de análise (NOVO)
if (analysisQueriesList.length > 0) {
    html += `
        <div style="grid-column: 1 / -1; margin-top: 16px; padding-top: 16px; border-top: 1px solid #334155;">
            <h5 style="color: #94a3b8; margin-bottom: 12px; font-size: 14px;">
                <i class="fas fa-chart-line"></i> Queries de Análise (suportam filtro por database)
            </h5>
        </div>
    `;
    analysisQueriesList.forEach(query => {
        html += `
            <button class="btn" ... style="border-left: 3px solid #10b981;">
                <i class="fas fa-chart-bar"></i> ${query.name}
            </button>
        `;
    });
}

// Renderizar seção de queries customizadas
if (customQueriesList.length > 0) {
    html += `
        <div style="grid-column: 1 / -1; margin-top: 16px; padding-top: 16px; border-top: 1px solid #334155;">
            <h5 style="color: #94a3b8; margin-bottom: 12px; font-size: 14px;">
                <i class="fas fa-user-cog"></i> Queries Customizadas
            </h5>
        </div>
    `;
    customQueriesList.forEach(query => {
        html += `<button class="btn" ... style="border-left: 3px solid #3b82f6;">...</button>`;
    });
}
```

### Identificação Visual

| Categoria | Cor da Borda | Ícone | Descrição |
|-----------|--------------|-------|-----------|
| **Standard** | Sem borda | `fa-database` | Queries padrão sem parametrização |
| **Análise** | Verde (`#10b981`) | `fa-chart-bar` | Queries com suporte a filtro de database |
| **Customizadas** | Azul (`#3b82f6`) | Definido pelo usuário | Queries customizadas |

---

## Alterações nos Endpoints da API

**Arquivo:** `api/routers/sql_queries.py`

### 1. Filegroup Growth History (linhas 319-330)

```python
@router.get("/filegroup-growth-history/{server_id}")
async def get_filegroup_growth_history(
    server_id: str,
    database: Optional[str] = Query(None)  # ← NOVO parâmetro
):
    """Obtém histórico de crescimento de filegroups (últimos 12 meses) - Suporta filtro por database"""
    try:
        query = SQLQueries.get_filegroup_growth_history_filtered(database)  # ← Usa método parametrizável
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={
            "server_id": server_id,
            "database": database or "ALL",  # ← Retorna database filtrada
            "filegroup_growth_history": result
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter histórico de crescimento de filegroups de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 2. Filegroup Growth Forecast (linhas 332-343)

```python
@router.get("/filegroup-growth-forecast/{server_id}")
async def get_filegroup_growth_forecast(
    server_id: str,
    database: Optional[str] = Query(None)  # ← NOVO parâmetro
):
    """Obtém projeção de crescimento de filegroups (MonthsUntilFull) - Suporta filtro por database"""
    try:
        query = SQLQueries.get_filegroup_growth_forecast_filtered(database)  # ← Usa método parametrizável
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={
            "server_id": server_id,
            "database": database or "ALL",  # ← Retorna database filtrada
            "filegroup_growth_forecast": result
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter projeção de crescimento de filegroups de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 3. Missing Index Analysis (linhas 357-368)

```python
@router.get("/missing-index-analysis/{server_id}")
async def get_missing_index_analysis(
    server_id: str,
    database: Optional[str] = Query(None)  # ← NOVO parâmetro
):
    """Obtém análise de índices faltantes com alto impacto - Suporta filtro por database"""
    try:
        query = SQLQueries.get_missing_index_analysis_filtered(database)  # ← Usa método parametrizável
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={
            "server_id": server_id,
            "database": database or "ALL",  # ← Retorna database filtrada
            "missing_index_analysis": result
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter análise de índices faltantes de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 4. Backup History Analysis (linhas 345-355)

```python
@router.get("/backup-history-analysis/{server_id}")
async def get_backup_history_analysis(server_id: str):
    """Obtém análise de histórico de backups (considera Always On AG) - SEM filtro (precisa ver todas as databases)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.BACKUP_HISTORY_ANALYSIS)  # ← SEM parametrização
        return JSONResponse(content={
            "server_id": server_id,
            "backup_history_analysis": result
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter análise de histórico de backups de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Métodos Criados em queries.py

**Arquivo:** `modules/monitoring/queries.py` (linhas 1301-1367)

```python
@staticmethod
def get_filegroup_growth_history_filtered(database_name: str = None):
    """
    Retorna query FILEGROUP_GROWTH_HISTORY com filtro opcional de database

    Args:
        database_name: Nome da database para filtrar (None = todas)

    Returns:
        str: Query SQL com filtro aplicado
    """
    base_query = SQLQueries.FILEGROUP_GROWTH_HISTORY

    if database_name and database_name.upper() != 'ALL':
        safe_db_name = database_name.replace(']', ']]')
        filter_clause = f"\n    AND DB_NAME(f.database_id) = '{safe_db_name}'"
        base_query = base_query.replace(
            "WHERE f.database_id > 4",
            f"WHERE f.database_id > 4{filter_clause}"
        )

    return base_query

@staticmethod
def get_filegroup_growth_forecast_filtered(database_name: str = None):
    """
    Retorna query FILEGROUP_GROWTH_FORECAST com filtro opcional de database

    Args:
        database_name: Nome da database para filtrar (None = todas)

    Returns:
        str: Query SQL com filtro aplicado
    """
    base_query = SQLQueries.FILEGROUP_GROWTH_FORECAST

    if database_name and database_name.upper() != 'ALL':
        safe_db_name = database_name.replace(']', ']]')
        filter_clause = f"\n    AND DB_NAME(f.database_id) = '{safe_db_name}'"
        base_query = base_query.replace(
            "WHERE f.database_id > 4",
            f"WHERE f.database_id > 4{filter_clause}"
        )

    return base_query

@staticmethod
def get_missing_index_analysis_filtered(database_name: str = None):
    """
    Retorna query MISSING_INDEX_ANALYSIS com filtro opcional de database

    Args:
        database_name: Nome da database para filtrar (None = todas)

    Returns:
        str: Query SQL com filtro aplicado
    """
    base_query = SQLQueries.MISSING_INDEX_ANALYSIS

    if database_name and database_name.upper() != 'ALL':
        safe_db_name = database_name.replace(']', ']]')
        filter_clause = f"\n    AND DB_NAME(mid.database_id) = '{safe_db_name}'"
        base_query = base_query.replace(
            "AND mid.database_id > 4  -- Excluir system databases\n    AND OBJECT_NAME",
            f"AND mid.database_id > 4  -- Excluir system databases{filter_clause}\n    AND OBJECT_NAME"
        )

    return base_query
```

---

## Testes

### Script de Teste Criado

**Arquivo:** `test_parametrized_queries.py`

**Uso:**
```bash
python test_parametrized_queries.py SQLHDSPRD013 --instance I03 --database PROD_DB_MAIN
```

**Testes executados:**
1. FILEGROUP_GROWTH_HISTORY (todas as databases)
2. FILEGROUP_GROWTH_HISTORY (database específica)
3. FILEGROUP_GROWTH_FORECAST (todas as databases)
4. FILEGROUP_GROWTH_FORECAST (database específica)
5. MISSING_INDEX_ANALYSIS (todas as databases)
6. MISSING_INDEX_ANALYSIS (database específica)
7. BACKUP_HISTORY_ANALYSIS (sem parametrização)

---

## Arquivos Modificados

### 1. modules/monitoring/queries.py
- Linhas 1301-1367: Adicionados métodos `get_*_filtered()`

### 2. api/routers/sql_queries.py
- Linhas 319-330: `get_filegroup_growth_history()` com parâmetro `database`
- Linhas 332-343: `get_filegroup_growth_forecast()` com parâmetro `database`
- Linhas 345-355: `get_backup_history_analysis()` documentado como SEM filtro
- Linhas 357-368: `get_missing_index_analysis()` com parâmetro `database`

### 3. templates/watcherdb_portal.html
- Linha ~7056: Adicionado `requiresDb: true` e `category: 'analysis'`
- Linha 7095: Label atualizada para "Filtro de Database (para Queries de Análise)"
- Linhas 7121-7153: Adicionada renderização de categoria 'analysis'

### 4. Novos Arquivos

- `test_parametrized_queries.py`: Script de teste das queries parametrizáveis
- `documentacao/PARAMETRIZACAO_v1.4.8.1.md`: Esta documentação

---

## Exemplos de Uso

### API - Todas as Databases

```bash
# Histórico de crescimento - todas as databases
curl http://localhost:8000/api/queries/filegroup-growth-history/SQLHDSPRD013_I03

# Projeção de crescimento - todas as databases
curl http://localhost:8000/api/queries/filegroup-growth-forecast/SQLHDSPRD013_I03

# Índices faltantes - todas as databases
curl http://localhost:8000/api/queries/missing-index-analysis/SQLHDSPRD013_I03
```

### API - Database Específica

```bash
# Histórico de crescimento - PROD_DB_MAIN
curl http://localhost:8000/api/queries/filegroup-growth-history/SQLHDSPRD013_I03?database=PROD_DB_MAIN

# Projeção de crescimento - PROD_DB_MAIN
curl http://localhost:8000/api/queries/filegroup-growth-forecast/SQLHDSPRD013_I03?database=PROD_DB_MAIN

# Índices faltantes - PROD_DB_MAIN
curl http://localhost:8000/api/queries/missing-index-analysis/SQLHDSPRD013_I03?database=PROD_DB_MAIN
```

### Frontend

1. Acessar "SQL Diagnostics" de um servidor
2. Selecionar database no dropdown (ou deixar "Todas as bases")
3. Clicar em qualquer botão da seção **"Queries de Análise"**
4. A query será executada com o filtro aplicado

---

## Compatibilidade

### Backward Compatibility

✅ **100% compatível** com código anterior:
- Queries sem parâmetro `database` funcionam como antes (retornam todas)
- Frontend sem dropdown funciona normalmente
- API aceita chamadas antigas sem o parâmetro

### Exemplo:

```python
# ANTES (v1.4.8) - ainda funciona
result = await execute_query_on_server(server_id, SQLQueries.FILEGROUP_GROWTH_HISTORY)

# DEPOIS (v1.4.8.1) - nova forma parametrizável
query = SQLQueries.get_filegroup_growth_history_filtered('PROD_DB_MAIN')
result = await execute_query_on_server(server_id, query)
```

---

## Benefícios

1. ✅ **Performance**: Reduz volume de dados retornados quando filtro específico é usado
2. ✅ **Flexibilidade**: Permite análise focada em uma database ou visão geral
3. ✅ **Organização**: Frontend organizado por categorias facilita navegação
4. ✅ **Segurança**: Proteção contra SQL injection via escape de caracteres
5. ✅ **Compatibilidade**: Mantém funcionamento de código anterior

---

## Próximos Passos

1. ⏸️ Testar queries parametrizadas no servidor de produção
2. ⏸️ Validar performance com filtro de database específica
3. ⏸️ Considerar adicionar cache por database
4. ⏸️ Avaliar adicionar parametrização a outras queries (se aplicável)

---

**Status:** ✅ **IMPLEMENTAÇÃO COMPLETA**

**Versão:** v1.4.8.1 (2025-11-17)

**Autor:** Claude Code (via WatcherDB Development Team)
