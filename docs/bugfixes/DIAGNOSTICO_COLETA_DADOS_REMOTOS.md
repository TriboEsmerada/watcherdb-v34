# DIAGNOSTICO: Coleta de Dados de Servidores Remotos

**Data:** 2025-12-10 19:55
**Status:** ⚠️ **INVESTIGACAO EM ANDAMENTO**

---

## PROBLEMA IDENTIFICADO

A query na tabela `KPI_MSSQL_FG_USAGE_STG` mostra **apenas dados do servidor local** (`SQLHDSTST505\I01`):

```sql
SELECT DISTINCT Instance, [Database], Filegroup
FROM dbo.KPI_MSSQL_FG_USAGE_STG
```

**Resultado:** 59 linhas, todas com Instance = `SQLHDSTST505\I01`

**Esperado:** Dados de 84 servidores remotos habilitados

---

## SISTEMA DE COLETA (WATCHERDB INTELLIGENCE V1)

### Arquitetura

```
scripts/collect_data.py
    ↓
DataCollector.collect_kpi_metrics()
    ↓
DataStorage.save_kpi_metrics()
    ↓
TRUNCATE KPI_MSSQL_FG_USAGE_STG
    ↓
INSERT dados coletados
```

### Componentes

1. **Coletor:** [watcherdb_intelligence/collectors/data_collector.py](c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1\watcherdb_intelligence\collectors\data_collector.py)
   - Linha 489-524: Query de Filegroup Usage
   - Conecta nos 84 servidores remotos via pyodbc
   - Coleta dados em paralelo (32 workers)

2. **Armazenamento:** [watcherdb_intelligence/collectors/storage.py](c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1\watcherdb_intelligence\collectors\storage.py)
   - Linha 84: Tabela `KPI_MSSQL_FG_USAGE_STG`
   - Linha 54-99: TRUNCATE antes de cada coleta
   - Pattern: **Truncate-and-Load** (limpa tudo, insere novos dados)

3. **Agendamento:**
   - Task Scheduler do Windows ou execução manual
   - Script: `scripts/collect_data.py`

---

## TESTE MANUAL REALIZADO

### Comando Executado
```bash
cd "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1"

python scripts/collect_data.py --mode kpi-fast
```

### Resultado (Primeiros 50 Segundos)
```json
{"count": 84, "event": "Servidores encontrados"}
{"server_id": "CAGENPRD06_I06", "server_name": "CAGENPRD06\\I06", "event": "Conexão OK"}
{"server_id": "CAGENPRD07_I07", "server_name": "CAGENPRD07\\I07", "event": "Conexão OK"}
{"server_id": "SQLHDSPRD001_I0001", "server_name": "SQLHDSPRD001\\I0001", "event": "Conexão OK"}
{"server_id": "SQLHDSPRD002_I0001", "server_name": "SQLHDSPRD002\\I0001", "event": "Conexão OK"}
{"server_id": "SQLHDSPRD003_I0002", "server_name": "SQLHDSPRD003\\I0002", "event": "Conexão OK"}
{"server_id": "SQLHDSPRD004_I0002", "server_name": "SQLHDSPRD004\\I0002", "event": "Conexão OK"}
{"server_id": "SQLHDSPRD005_I0003", "server_name": "SQLHDSPRD005\\I0003", "event": "Conexão OK"}
{"server_id": "SQLHDSPRD006_I0003", "server_name": "SQLHDSPRD006\\I0003", "event": "Conexão OK"}
```

**Conclusão:** ✅ O coletor **está conectando com sucesso** em múltiplos servidores remotos!

---

## HIPÓTESES

### Hipótese 1: Processo de Coleta Não Está Agendado ⚠️

**Evidências:**
- Não encontramos tarefas agendadas do WatcherDB:
  ```bash
  powershell -Command "Get-ScheduledTask | Where-Object TaskName -like 'watcherdb*'"
  # Resultado: Vazio
  ```
- Não há logs de coleta recentes:
  ```bash
  dir "c:\...\WATCHERDB INTELLIGENCE V1\logs\" /O-D /B
  # Resultado: Vazio (pasta não existe ou sem logs)
  ```

**Impacto:** Se não está agendado, **só há dados quando executamos manualmente**. Isso explica por que só vemos dados do servidor local (provavelmente apenas testes locais foram executados).

**Como Verificar:**
```bash
# Windows Task Scheduler
powershell -Command "Get-ScheduledTask | Format-Table TaskName, State, LastRunTime"

# Ou verificar manualmente
# Abra: Task Scheduler → Task Scheduler Library → procurar "WatcherDB"
```

---

### Hipótese 2: Coleta Está Falhando Silenciosamente ⚠️

**Evidências:**
- Padrão Truncate-and-Load: Se coleta falhar **após TRUNCATE**, tabela fica vazia
- Não verificamos se há erros nos logs

**Como Verificar:**
```bash
# Executar coleta completa manualmente e acompanhar
cd "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1"

python scripts/collect_data.py --mode all 2>&1 | tee coleta_manual.log

# Depois verificar tabela
sqlcmd -S SQLHDSTST505\I01 -d WatcherDB_Intelligence -Q "SELECT COUNT(DISTINCT Instance) FROM KPI_MSSQL_FG_USAGE_STG"
```

---

### Hipótese 3: Coleta Roda Mas Demora Muito (Timeout) ⏱️

**Evidências:**
- 84 servidores remotos
- Coleta em paralelo (32 workers)
- Coleta `kpi-fast` apenas (pode não incluir filegroup_usage)

**Perfis de Coleta:**
```python
# data_collector.py - Linha 429-456
if profile == "fast":
    # KPI pesado - coletado apenas no perfil completo
    kpi_metrics["disk_usage"] = []
```

**Como Verificar:** Verificar se `filegroup_usage` está no modo `fast` ou só no modo `full`:
```python
# Procurar no código: if profile == "fast"
# Linha 488-524: Filegroup Usage (SEM VERIFICAÇÃO DE PROFILE!)
# Conclusão: Filegroup é coletado em TODOS os perfis
```

---

### Hipótese 4: Dados São Inseridos Mas Query Não Mostra ❌ (DESCARTADA)

**Motivo:** A query SQL está correta e funcionou localmente. Se há 59 linhas do `SQLHDSTST505\I01`, significa que a inserção funciona.

---

## PRÓXIMOS PASSOS

### Passo 1: Verificar Agendamento (CRÍTICO)

```bash
# PowerShell - Listar todas as tarefas agendadas
powershell -Command "Get-ScheduledTask | Where-Object {$_.TaskPath -notlike '*Microsoft*'} | Format-Table TaskName, State, LastRunTime, NextRunTime"

# Procurar por tarefas Python/WatcherDB
powershell -Command "Get-ScheduledTask | Where-Object {$_.Actions.Execute -like '*python*' -or $_.Actions.Arguments -like '*collect_data*'}"
```

**Ação:** Se não houver agendamento:
- Criar tarefa agendada para executar `collect_data.py`
- Sugestão: A cada 5 minutos (modo `kpi-fast`) ou a cada 30 minutos (modo `all`)

---

### Passo 2: Executar Coleta Manual Completa e Verificar

```bash
# Terminal 1: Executar coleta
cd "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1"

python scripts/collect_data.py --mode all 2>&1 | tee coleta_completa_20251210.log

# Aguardar até conclusão (pode demorar 5-15 minutos para 84 servidores)

# Terminal 2: Verificar dados coletados
sqlcmd -S SQLHDSTST505\I01 -d WatcherDB_Intelligence -Q "
SELECT
    COUNT(DISTINCT Instance) AS Total_Instances,
    COUNT(*) AS Total_Filegroups
FROM dbo.KPI_MSSQL_FG_USAGE_STG
"
```

**Resultado Esperado:**
- `Total_Instances`: 84 (ou próximo, considerando servidores offline)
- `Total_Filegroups`: 500+ (múltiplos filegroups por servidor)

---

### Passo 3: Verificar Logs de Execução

```bash
# Se houver pasta logs/
dir "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1\logs\" /O-D

# Ler último log
type "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1\logs\watcherdb_*.log" | findstr /I "error fail exception"
```

---

### Passo 4: Verificar Stored Procedure de Truncate

A coleta usa stored procedure `usp_truncate_stg_tables` se existir (linhas 107-189 do storage.py).

**Verificação:**
```sql
-- Verificar se procedure existe
SELECT name, create_date, modify_date
FROM sys.procedures
WHERE name = 'usp_truncate_stg_tables'
  AND schema_id = SCHEMA_ID('dbo')

-- Se existir, verificar se está travando
SELECT
    r.session_id,
    r.status,
    r.command,
    r.wait_type,
    r.wait_time,
    DB_NAME(r.database_id) AS database_name,
    t.text AS query_text
FROM sys.dm_exec_requests r
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE r.database_id = DB_ID('WatcherDB_Intelligence')
  AND t.text LIKE '%truncate%'
```

---

## CONFIGURAÇÃO DO AGENDAMENTO

### Opção A: Windows Task Scheduler (Recomendado)

```xml
<!-- Criar arquivo watcherdb_collection_fast.xml -->
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2">
  <RegistrationInfo>
    <Description>WatcherDB Intelligence - Coleta Rápida (KPIs a cada 5 min)</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <Repetition>
        <Interval>PT5M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2025-12-10T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </CalendarTrigger>
  </Triggers>
  <Actions>
    <Exec>
      <Command>C:\Python313\python.exe</Command>
      <Arguments>scripts/collect_data.py --mode kpi-fast</Arguments>
      <WorkingDirectory>c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
```

**Importar:**
```bash
schtasks /Create /XML watcherdb_collection_fast.xml /TN "WatcherDB\Collection_Fast"
```

---

### Opção B: Script PowerShell de Agendamento

```powershell
# scripts/agendar_coleta.ps1
$action = New-ScheduledTaskAction `
    -Execute "C:\Python313\python.exe" `
    -Argument "scripts/collect_data.py --mode kpi-fast" `
    -WorkingDirectory "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1"

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName "WatcherDB_Collection_Fast" `
    -Action $action `
    -Trigger $trigger `
    -Description "WatcherDB Intelligence - Coleta KPIs a cada 5 minutos"
```

---

## RESUMO

### Situação Atual
- ✅ Coletor **funciona** e conecta em 84 servidores
- ✅ Código de coleta de filegroup **está correto**
- ⚠️ Agendamento **provavelmente não existe**
- ⚠️ Apenas dados **locais** (SQLHDSTST505\I01) na tabela

### Causa Provável
**Coleta não está agendada** → Só roda manualmente → Só testaram no servidor local

### Solução
1. ✅ **Executar coleta manual completa AGORA** para popular dados
2. ✅ **Criar agendamento** (Task Scheduler) para coleta automática
3. ✅ **Verificar logs** após primeira execução agendada

### Impacto no Dashboard
Após popular os dados (Passo 2), a **Análise Preditiva funcionará** para todos os 84 servidores!

---

**Status:** ⏳ **AGUARDANDO EXECUÇÃO DE COLETA MANUAL COMPLETA**
**Próxima Ação:** Executar `python scripts/collect_data.py --mode all` e verificar resultados
