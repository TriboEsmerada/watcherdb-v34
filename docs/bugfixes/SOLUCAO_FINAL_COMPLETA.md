# SOLUÇÃO FINAL COMPLETA - Análise Preditiva

**Data:** 2025-12-10 20:20
**Status:** ⚠️ **REQUER AÇÃO DO USUÁRIO**

---

## RESUMO DO PROBLEMA

O erro `{"success":false,"error":"Falha na execução: ""}` ocorre porque:

1. ✅ **Script de Análise Preditiva:** FUNCIONA (testado manualmente com sucesso)
2. ✅ **Código está CORRETO:** Todas as correções aplicadas
3. ⚠️ **FALTA DADOS:** Tabela `KPI_MSSQL_FG_USAGE_STG` só tem dados do servidor local
4. ⚠️ **COLETA NÃO AGENDADA:** Sistema WatcherDB Intelligence não está coletando dados automaticamente

---

## SOLUÇÃO EM 3 PASSOS

### PASSO 1: Reiniciar Aplicação Uvicorn 🔴 OBRIGATÓRIO

A aplicação está travada (PID 17760 desde 18:53).

**1.1. Matar processo atual:**
```bash
taskkill /F /PID 17760
```

**1.2. Navegar até diretório:**
```bash
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
```

**1.3. Reiniciar uvicorn:**
```bash
python -m uvicorn watcherdb_intelligence:app --reload --port 8000
```

**1.4. Aguardar mensagem:**
```
INFO:     Application startup complete.
INFO:     Script de análise preditiva carregado: filegroup_interactive_report_v5_watcherdb.py
```

---

### PASSO 2: Executar Coleta de Dados 🔴 CRÍTICO

**MOTIVO:** A tabela `KPI_MSSQL_FG_USAGE_STG` **só tem dados do servidor local** (SQLHDSTST505\I01). Precisamos coletar dados de **todos os 84 servidores remotos**.

**2.1. Abrir NOVO terminal (deixar uvicorn rodando no primeiro):**

**2.2. Navegar até WatcherDB Intelligence V1:**
```bash
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1"
```

**2.3. Executar coleta completa:**
```bash
python scripts/collect_data.py --mode all 2>&1 | tee coleta_completa_20251210.log
```

⏱️ **TEMPO ESTIMADO:** 10-20 minutos para coletar dados de 84 servidores

**2.4. Aguardar até ver:**
```json
{"event": "Coleta paralela concluída", "servidores_processados": 84}
```

**2.5. Verificar dados coletados:**
```sql
-- Abrir SQL Server Management Studio ou Azure Data Studio
-- Conectar: SQLHDSTST505\I01
-- Database: WatcherDB_Intelligence

SELECT
    COUNT(DISTINCT Instance) AS Total_Servidores,
    COUNT(*) AS Total_Filegroups,
    MIN(Update_TS) AS Primeira_Coleta,
    MAX(Update_TS) AS Ultima_Coleta
FROM dbo.KPI_MSSQL_FG_USAGE_STG
```

**Resultado Esperado:**
- `Total_Servidores`: ~80-84 (alguns podem estar offline)
- `Total_Filegroups`: 500-1000+
- `Ultima_Coleta`: Data/hora atual

---

### PASSO 3: Testar Análise Preditiva no Dashboard ✅

**3.1. Acessar dashboard:**
```
http://127.0.0.1:8000/watcherdb
```

**3.2. Navegar até filegroup:**
1. Clique em qualquer **Instance** (ex: `SQLHDSPRD001_I0001`)
2. Clique em um **Database** aplicacional (não master/model/msdb)
3. Clique em um **Filegroup** (ex: `PRIMARY`)

**3.3. Executar análise:**
1. Clique no botão **"📊 Análise Preditiva"**
2. Aguarde processamento

**3.4. Resultado Esperado:**
- ✅ Modal mostra progresso
- ✅ Mensagens aparecem:
  - "Filegroup encontrado - X.X% usado"
  - "ALERTA: Atingirá 85% em N dias" ou "OK: Não atingirá..."
  - "Relatório gerado com sucesso"
- ✅ Relatório HTML abre automaticamente
- ✅ Arquivos gerados em `reports/`

---

## CONFIGURAR AGENDAMENTO (OPCIONAL MAS RECOMENDADO)

Para que os dados sejam atualizados automaticamente:

### Opção A: Task Scheduler (Windows)

**Criar arquivo `agendar_coleta_watcherdb.ps1`:**
```powershell
# Agendar coleta rápida (KPIs a cada 5 minutos)
$actionFast = New-ScheduledTaskAction `
    -Execute "C:\Python313\python.exe" `
    -Argument "scripts/collect_data.py --mode kpi-fast" `
    -WorkingDirectory "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1"

$triggerFast = New-ScheduledTaskTrigger `
    -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

Register-ScheduledTask `
    -TaskName "WatcherDB_Collection_Fast" `
    -Action $actionFast `
    -Trigger $triggerFast `
    -Description "WatcherDB Intelligence - Coleta KPIs a cada 5 minutos" `
    -User $env:USERNAME `
    -RunLevel Highest

Write-Host "✓ Tarefa agendada criada: WatcherDB_Collection_Fast"
Write-Host "  Frequência: A cada 5 minutos"
Write-Host "  Modo: kpi-fast"
```

**Executar:**
```bash
powershell -ExecutionPolicy Bypass -File agendar_coleta_watcherdb.ps1
```

**Verificar:**
```bash
powershell -Command "Get-ScheduledTask | Where-Object TaskName -like 'WatcherDB*' | Format-Table TaskName, State, LastRunTime, NextRunTime"
```

---

### Opção B: Agendamento Manual (Task Scheduler GUI)

1. Abra **Task Scheduler** (Agendador de Tarefas)
2. Clique em **"Create Task..."** (Criar Tarefa...)
3. **General:**
   - Name: `WatcherDB_Collection_Fast`
   - Run whether user is logged on or not: ☑
   - Run with highest privileges: ☑
4. **Triggers:**
   - New → Daily
   - Repeat task every: `5 minutes`
   - For a duration of: `Indefinitely`
5. **Actions:**
   - Action: `Start a program`
   - Program/script: `C:\Python313\python.exe`
   - Arguments: `scripts/collect_data.py --mode kpi-fast`
   - Start in: `C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1`
6. **Conditions:**
   - Desmarque: `Start the task only if the computer is on AC power`
7. **Settings:**
   - Allow task to be run on demand: ☑
   - If the task is already running: `Do not start a new instance`
8. Clique **OK** e digite sua senha se solicitado

---

## TROUBLESHOOTING

### Erro: "Porta 8000 em uso"
```bash
netstat -ano | findstr ":8000"
# Pegar PID da primeira linha
taskkill /F /PID <PID>
```

### Erro: "ModuleNotFoundError: No module named 'uvicorn'"
```bash
pip install uvicorn
```

### Erro: "Nenhum servidor encontrado" na coleta
Verificar arquivo de configuração:
```bash
type "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1\config\servers.yaml"
```

### Coleta muito lenta (>30 minutos)
- Verificar firewall
- Verificar conectividade de rede com servidores remotos
- Usar `--mode kpi-fast` (mais rápido, menos dados)

### Análise Preditiva ainda falha após coleta
1. Verificar se dados foram inseridos:
   ```sql
   SELECT Instance, [Database], Filegroup, Percent_Used, Update_TS
   FROM dbo.KPI_MSSQL_FG_USAGE_STG
   WHERE Instance = 'SQLHDSPRD001_I0001'
     AND [Database] NOT IN ('master', 'model', 'msdb', 'tempdb')
   ORDER BY Update_TS DESC
   ```
2. Testar script manualmente:
   ```bash
   cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"

   python filegroup_interactive_report_v5_watcherdb.py "Instance=SQLHDSPRD001_I0001;DatabaseName=DBA_RESOURCE_DB;filegroup_name=PRIMARY" 60 0.85
   ```

---

## CHECKLIST FINAL

Antes de considerar resolvido, verificar:

- [ ] Uvicorn reiniciado e respondendo (http://127.0.0.1:8000/)
- [ ] Coleta manual executada (`python scripts/collect_data.py --mode all`)
- [ ] Dados na tabela confirmados (query SQL retorna 80+ servidores)
- [ ] Análise preditiva testada via dashboard (funciona sem erro)
- [ ] Agendamento configurado (opcional, mas recomendado)

---

## ARQUIVOS DE REFERÊNCIA

### Scripts Criados
- [filegroup_interactive_report_v5_watcherdb.py](filegroup_interactive_report_v5_watcherdb.py) - Script principal (usa dados locais)
- [filegroup_interactive_report_v5_lite.py](filegroup_interactive_report_v5_lite.py) - Fallback sem pandas
- [filegroup_interactive_report_v5.py](filegroup_interactive_report_v5.py) - Fallback completo com ML

### Documentação
- [README_ANALISE_PREDITIVA.md](README_ANALISE_PREDITIVA.md) - Resumo completo da funcionalidade
- [DIAGNOSTICO_ANALISE_PREDITIVA.md](DIAGNOSTICO_ANALISE_PREDITIVA.md) - Histórico de 6 erros resolvidos
- [DIAGNOSTICO_COLETA_DADOS_REMOTOS.md](DIAGNOSTICO_COLETA_DADOS_REMOTOS.md) - Diagnóstico do sistema de coleta
- [CORRECAO_FINAL_ANALISE_PREDITIVA.md](CORRECAO_FINAL_ANALISE_PREDITIVA.md) - Correção do formato de Instance

---

**Status:** ⏳ **AGUARDANDO EXECUÇÃO DOS PASSOS 1, 2 E 3**
**Próxima Ação:** Reiniciar uvicorn → Executar coleta → Testar dashboard

**Tempo Total Estimado:** 30-40 minutos
