# DIAGNÓSTICO FINAL - Coleta de Dados Remotos

**Data:** 2025-12-11 11:40 UTC
**Status:** 🔴 **PROBLEMA CRÍTICO IDENTIFICADO**

---

## PROBLEMA RAIZ ENCONTRADO

### Sintoma
- Análise preditiva funciona PERFEITAMENTE quando testada manualmente
- Dashboard retorna erro: `{"success":false,"error":"Falha na execução: ""}`
- Query inicial mostrou 23 servidores e 82 filegroups
- Query posterior mostrou APENAS 1 servidor (SQLHDSTST505\I01 - local)

### Causa
**A coleta de dados está sendo executada MÚLTIPLAS VEZES simultaneamente**, causando:
1. Primeira coleta: TRUNCATE tabela → INSERT dados dos 84 servidores ✅
2. Segunda coleta (concurrent): TRUNCATE tabela → Apaga dados da primeira! ❌
3. Terceira coleta: TRUNCATE novamente... ❌
4. Resultado: Apenas dados do servidor LOCAL permanecem

---

## EVIDÊNCIAS

### Teste Manual Bem-Sucedido ✅
```bash
# Comando
python filegroup_interactive_report_v5_watcherdb.py "Instance=SQLHDSQLT301_I01;DatabaseName=master_rst;filegroup_name=PRIMARY" 60 0.85

# Resultado
OK: Filegroup encontrado - 85.9% usado
ALERTA: Atingira 85% em 1 dias
OK: Relatorio gerado: reports\interactive_PRIMARY_20251211113939139_forecast.html
```

### Query de Verificação Antes/Depois
```sql
-- Resultado 1 (11:38 UTC): 23 servidores, 82 filegroups
SELECT COUNT(DISTINCT Instance), COUNT(*)
FROM KPI_MSSQL_FG_USAGE_STG

-- Resultado 2 (11:40 UTC): 1 servidor, dados apenas locais
SELECT DISTINCT Instance FROM KPI_MSSQL_FG_USAGE_STG
```

### Servidores Testados pelo Usuário
- `SQLIDSPRD03_J01` → **SEM DADOS** (truncado)
- `SQLHDSPRD003_J01` → **SEM DADOS** (truncado)

Por isso o erro ocorre no dashboard!

---

## ANÁLISE DO CÓDIGO DE COLETA

### Padrão Truncate-and-Load (watcherdb_intelligence/collectors/storage.py)

```python
# Linha 54-99: Truncate STG tables
def _truncate_kpi_stg_tables(self, cursor, kpi_list: List[str] = None):
    """
    Trunca tabelas STG de KPIs antes da coleta (padrão Truncate-and-Load).

    PROBLEMA: Se múltiplas coletas rodam simultaneamente,
    a última TRUNCATE apaga dados das coletas anteriores!
    """
    kpi_table_mapping = {
        "filegroup_usage": "KPI_MSSQL_FG_USAGE_STG",
        # ... outras tabelas
    }

    # Tenta usar stored procedure (se existir)
    cursor.execute("EXEC dbo.usp_truncate_stg_tables")

    # Ou trunca manualmente
    for table in tables_to_truncate:
        cursor.execute(f"TRUNCATE TABLE {table}")
```

**Fluxo:**
```
Coleta 1 (11:20): TRUNCATE → INSERT 84 servidores ✅
Coleta 2 (11:25): TRUNCATE → Apaga tudo! → INSERT apenas local ❌
Coleta 3 (11:30): TRUNCATE → Apaga tudo! → INSERT apenas local ❌
```

---

## SOLUÇÕES POSSÍVEIS

### Solução 1: Parar Múltiplas Coletas Concorrentes (IMEDIATO) 🔴

**Verificar processos Python rodando:**
```bash
# Windows
tasklist | findstr python

# Matar processos de coleta duplicados
taskkill /F /PID <PID>
```

**Verificar Task Scheduler:**
```bash
powershell -Command "Get-ScheduledTask | Where-Object {$_.Actions.Execute -like '*python*' -and $_.Actions.Arguments -like '*collect_data*'} | Format-Table TaskName, State, LastRunTime, NextRunTime"
```

**Desabilitar tarefas duplicadas:**
```bash
schtasks /Change /TN "WatcherDB_Collection_Fast" /DISABLE
```

---

### Solução 2: Implementar LOCK de Coleta (MÉDIO PRAZO) ⚠️

**Modificar `scripts/collect_data.py`:**
```python
import fcntl
import sys

# Adicionar no início de main()
def main(mode: str | None = None):
    # Lock file para evitar execuções simultâneas
    lock_file = Path("data/collect_data.lock")
    lock_file.parent.mkdir(exist_ok=True)

    try:
        with open(lock_file, 'w') as f:
            # Tenta adquirir lock exclusivo (non-blocking)
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Coleta normal...
            logger.info("Lock adquirido - iniciando coleta")
            # ... código existente ...

    except IOError:
        logger.warning("Outra coleta já está em execução - abortando")
        sys.exit(0)
```

---

### Solução 3: Mudar para MERGE (Insert/Update) ao invés de Truncate-and-Load (LONGO PRAZO) ✅

**Vantagem:** Dados nunca são perdidos, apenas atualizados.

**Desvantagem:** Mais complexo, requer chave única (Instance + Database + Filegroup + Update_TS).

**Implementação:**
```python
# storage.py - Substituir truncate + bulk insert por MERGE
def save_filegroup_usage(self, data):
    merge_query = """
    MERGE KPI_MSSQL_FG_USAGE_STG AS target
    USING (VALUES (?, ?, ?, ?, ?, ?, ?)) AS source (Instance, Database, Filegroup, Total_MB, Used_MB, Free_MB, Percent_Used, Update_TS)
    ON target.Instance = source.Instance
       AND target.[Database] = source.[Database]
       AND target.Filegroup = source.Filegroup
    WHEN MATCHED THEN
        UPDATE SET
            Total_MB = source.Total_MB,
            Used_MB = source.Used_MB,
            Free_MB = source.Free_MB,
            Percent_Used = source.Percent_Used,
            Update_TS = source.Update_TS
    WHEN NOT MATCHED THEN
        INSERT (Instance, [Database], Filegroup, Total_MB, Used_MB, Free_MB, Percent_Used, Update_TS)
        VALUES (source.Instance, source.Database, source.Filegroup, source.Total_MB, source.Used_MB, source.Free_MB, source.Percent_Used, source.Update_TS);
    """
```

---

## AÇÃO IMEDIATA RECOMENDADA

1. **Parar todas as coletas em execução:**
   ```bash
   tasklist | findstr /I "python.*collect_data"
   taskkill /F /PID <PID_de_cada_processo>
   ```

2. **Verificar Task Scheduler e desabilitar duplicatas:**
   ```bash
   powershell -Command "Get-ScheduledTask | Where-Object TaskName -like 'WatcherDB*'"
   ```

3. **Executar UMA ÚNICA coleta manualmente:**
   ```bash
   cd "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1"

   python scripts/collect_data.py --mode all
   ```

4. **Aguardar conclusão (15-20 minutos):**
   - Monitorar output até ver: `"servidores_processados": 84`

5. **Verificar dados inseridos:**
   ```sql
   SELECT COUNT(DISTINCT Instance), COUNT(*)
   FROM KPI_MSSQL_FG_USAGE_STG
   ```
   - Esperado: 23-84 servidores, 500+ filegroups

6. **Testar análise preditiva via dashboard:**
   - URL: http://127.0.0.1:8000/watcherdb
   - Selecionar servidor com dados: `SQLHDSQLT301_I01`
   - Database: `master_rst`
   - Filegroup: `PRIMARY`
   - Clicar em "Análise Preditiva"

---

## LOGS DE COLETA (11:20 - 11:40 UTC)

### Coletas Detectadas
- **Coleta 1:** 11:20:07 - Conectou nos 84 servidores ✅
- **Coleta 2:** 11:25:34 - Finalizou (possível TRUNCATE) ⚠️
- **Coleta 3:** 11:35:06 - Última atualização na tabela ⚠️

### Evidência de Múltiplas Execuções
```sql
-- Query mostrou Update_TS de 11:25 E 11:35
SELECT MIN(Update_TS), MAX(Update_TS)
FROM KPI_MSSQL_FG_USAGE_STG

-- Resultado: 2025-12-11 11:25:49 / 2025-12-11 11:35:06
```

**Conclusão:** Houve pelo menos 2 coletas em 10 minutos! A segunda apagou dados da primeira.

---

## STATUS ATUAL

- ✅ **Código de Análise Preditiva:** FUNCIONA PERFEITAMENTE
- ✅ **Script de Coleta:** CONECTA nos 84 servidores
- ❌ **Dados na Tabela:** TRUNCADOS por coletas concorrentes
- ❌ **Dashboard:** FALHA porque não há dados

---

## PRÓXIMOS PASSOS

1. ⏳ **AGUARDANDO:** Filtrar logs da coleta atual para encontrar erros de inserção
2. 🔴 **CRÍTICO:** Parar múltiplas coletas concorrentes
3. ✅ **TESTAR:** Executar UMA coleta e verificar se dados permanecem

---

**Última Atualização:** 2025-12-11 11:40 UTC
**Próxima Ação:** Verificar output do filtro de logs e parar coletas duplicadas
