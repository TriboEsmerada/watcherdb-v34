# Detecção de Gaps de Backup Baseada em Schedules Reais

## 📅 Problema Identificado

**ANTES:** O sistema detectava gaps baseado em padrões **inferidos** dos dados históricos:
- Calculava `avg_interval_hours` e `std_interval_hours` dos backups passados
- Se os dados históricos já tinham falhas, o padrão inferido ficava errado
- **Exemplo:** Se DIFF schedule é 1x/dia às 19h, mas backups falharam várias vezes, o avg poderia ser 36h
- **Resultado:** Um gap de 12h aparecia como "OK" quando deveria ser um ISSUE

## ✅ Solução Implementada

Agora o sistema consulta os **schedules reais** dos SQL Agent Jobs como **fonte da verdade**:

### 1. Nova Query SQL (`backup_schedule_queries.sql`)
- Busca jobs de backup do `msdb.dbo.sysjobs` + `sysschedules`
- Identifica tipo de backup (FULL, DIFF, LOG) do comando
- Calcula `expected_interval_hours` baseado em `freq_type`, `freq_subday_type`, etc
- Mapeia database → backup_type → schedule

### 2. Nova Dataclass (`BackupSchedule`)
```python
@dataclass
class BackupSchedule:
    database_name: str
    backup_type: str  # 'FULL', 'DIFF', 'LOG'
    job_name: str
    schedule_name: str
    frequency_type: str  # 'Daily', 'Weekly', etc
    expected_interval_hours: Optional[float]  # Intervalo esperado do schedule
    scheduled_time: str  # 'HH:MM:SS'
    is_enabled: bool
    schedule_enabled: bool
```

### 3. Novo Método (`_get_backup_schedules()`)
- Busca schedules dos jobs para uma database
- Retorna dict: `{'FULL': BackupSchedule, 'DIFF': BackupSchedule, 'LOG': BackupSchedule}`
- Se múltiplos jobs do mesmo tipo, usa o de **menor intervalo** (mais conservador)

### 4. Modificações em `_detect_gaps()`
**PRIORIDADE DE FONTE:**
1. **Schedule real** (se disponível) → usa `schedule.expected_interval_hours`
2. **Padrão inferido** (fallback) → usa `pattern.avg_interval_hours`

**Tolerância ajustada quando usa schedule:**
- LOG: 2h de tolerância
- DIFF: 4h de tolerância
- FULL: 12h de tolerância

### 5. Modificações em `_classify_gap_severity()`
Agora aceita `expected_interval_hours` opcional:
- **Com schedule:** Thresholds FIXOS definidos pelo negócio
  - **low:** gap ≤ 6h
  - **medium:** gap > 6h e ≤ 30h
  - **high:** gap > 30h e ≤ 48h
  - **critical:** gap > 48h

- **Sem schedule:** Thresholds fixos por tipo (fallback - padrão inferido)
  - FULL: medium=168h, high=240h, critical=336h
  - DIFF: medium=24h, high=48h, critical=72h
  - LOG: medium=2h, high=4h, critical=8h

## 🎯 Exemplo Prático

**Cenário:** Database `EFTDB2024` com DIFF schedule de 1x/dia às 19h

**ANTES (padrão inferido):**
- Histórico mostra backups às 19h, 21h, 23h, 02h (irregulares por falhas)
- avg_interval_hours = 26h (inflado pelas falhas)
- std_interval_hours = 8h
- Tolerance = 16h (2 * 8h)
- **Gap de 12h NÃO seria detectado** (dentro de avg ± tolerance)

**DEPOIS (schedule real):**
- Schedule consulta msdb: freq_type=4 (Daily), freq_subday_type=1 (Once), active_start_time=190000
- expected_interval_hours = 24h
- Tolerance = 4h (fixa para DIFF)
- **Gap de 12h É detectado** se ultrapassar 24h + 4h = 28h

## 📊 Impacto nos Issues

**Coluna "Issues" no Dashboard:**
- ❌ ANTES: "DIFF > 12h" marcado como issue mesmo com schedule de 24h
- ✅ AGORA: "DIFF > 28h" marcado como issue (24h schedule + 4h tolerância)

**Logs informativos:**
```
📅 Schedules encontrados para EFTDB2024: FULL, DIFF, LOG
✅ DIFF pattern: 1x por dia (confiança: 85.2%, fonte: schedule)
📅 Usando schedule real para DIFF: intervalo=24h, tolerância=4h
```

## 🔄 Replicação

Arquivos replicados para:
- ✅ `WATCHERDB_DEV/modules/monitoring/backup_pattern_analysis.py`
- ✅ `WATCHERDB_DEV_V4/modules/monitoring/backup_pattern_analysis.py`
- ✅ `WATCHERDB_V5/modules/monitoring/backup_pattern_analysis.py`
- ✅ `*/modules/monitoring/backup_schedule_queries.sql` (todos)

## 🧪 Como Testar

1. **Verificar schedules detectados:**
```python
schedules = await analyzer._get_backup_schedules(server_id, 'EFTDB2024')
print(schedules)
# {'FULL': BackupSchedule(..., expected_interval_hours=168),
#  'DIFF': BackupSchedule(..., expected_interval_hours=24),
#  'LOG': BackupSchedule(..., expected_interval_hours=1)}
```

2. **Executar análise completa:**
```python
result = await analyzer.analyze_database_patterns(server_id, 'EFTDB2024')
print(result.detected_gaps)
```

3. **Verificar logs:**
- Logs devem indicar "fonte: schedule" quando schedule está disponível
- Logs devem indicar "fonte: padrão inferido" quando não há schedule

## ⚠️ Comportamento de Fallback

Se não houver schedule (backup manual, job desabilitado, etc):
- Sistema usa padrão inferido dos dados históricos (comportamento anterior)
- **Não quebra** databases sem jobs automatizados

## 📝 Notas Importantes

1. **Apenas jobs habilitados:** Query filtra `j.enabled = 1 AND s.enabled = 1`
2. **Schedule mais conservador:** Se múltiplos jobs para mesmo tipo, usa o de menor intervalo
3. **Parsing de comando:** Extrai database_name do comando SQL (suporta vários formatos)
4. **Tipos de backup identificados:** FULL, DIFF, LOG (baseado em keywords no comando)

---

**Data de Implementação:** 2026-02-20
**Versão:** WATCHERDB DEV, V4, V5
**Status:** ✅ Completo e Replicado

---

## 🚀 Wave R+8 (planeado 2026-05-25): msdb.backupset history pattern analysis

### Gap actual

Schedule detection actual cobre apenas backups com **SQL Agent jobs nativos**
(`msdb.dbo.sysjobs + sysschedules`). Nao cobre:
- ❌ TSM/Tivoli/Commvault/NetBackup backups via VDI (nao escrevem em sysjobs)
- ❌ Backups manuais ad-hoc (sem job)
- ❌ Maintenance plans com schedules complexos
- ❌ Backups executados por aplicacao (custom scripts)

**Resultado em producao:** DBs com TSM como mecanismo principal de backup
ficam sem schedule detection -> caem ao fallback global (pattern inferido OR
defaults rigidos). Falsos positivos / falsos negativos.

### Solucao Wave R+8

Adicionar nova camada de deteccao via **pattern analysis from `msdb.dbo.backupset`
history**. Em vez de ler sysjobs (que TSM/Commvault nao tocam), analisar
historico de backups completados para inferir schedule real.

**Algoritmo:**

```sql
-- Janela 30 dias para cada (database, backup_type)
SELECT
    database_name,
    type AS backup_type,  -- D/I/L
    backup_finish_date,
    LAG(backup_finish_date) OVER (
        PARTITION BY database_name, type
        ORDER BY backup_finish_date
    ) AS prev_backup,
    DATEDIFF(MINUTE, prev, current) AS interval_minutes
FROM msdb.dbo.backupset
WHERE backup_finish_date >= DATEADD(DAY, -30, GETDATE())
```

Em Python:
1. Para cada (database, backup_type), calcular intervals historicos
2. Clustering: identificar dominant interval (ex: maioria a 24h ± 2h)
3. Confianca: rate of conformance (ex: 87% dos backups dentro do pattern)
4. Se confianca > 70% -> usar pattern detectado como `expected_interval_hours`
5. Se confianca < 70% -> backup irregular, marca "manual" + nao alerta gaps small

### Priority chain pos-R+8

A integracao com schedule detection existente fica:

```
1. Per-instance MUTE list           (Wave R+10 -- universal)
            ↓ fallback
2. Pattern from msdb.backupset      (Wave R+8 -- NEW)
            ↓ fallback
3. Schedule from sysjobs            (2026-02-20 -- existing)
            ↓ fallback
4. Smart global defaults            (existing)
```

**Pattern (R+8) tem prioridade sobre schedule (sysjobs) porque:**
- Captura backups TSM/Commvault que sysjobs nao ve
- Adapta-se a mudancas de schedule (DBA muda job sem actualizar config)
- Confianca > 70% indica pattern estavel real

**Sysjobs (existing) mantem-se como fallback para:**
- DBs novos com pouco historia (< 7 dias) que ainda nao tem pattern confiavel

### Files affected

- `WATCHERDB_V3.3/modules/monitoring/backup_pattern_analysis.py` -- new function
  `detect_schedule_from_history()` (~80 lines)
- `WATCHERDB_V3.3/modules/monitoring/backup_schedule_queries.sql` -- backupset
  history query (~40 lines)
- `WATCHERDB_V3.3/modules/monitoring/backup_analysis.py` -- priority chain update
  (~20 lines)

### Test cases

- DB with cron-style backup (TSM) -> detected schedule ~daily ✅
- DB with very irregular backup -> marked "manual", no false alerts ✅
- DB with no msdb history (novo) -> fallback global defaults ✅
- DB com FULL diario que muda para semanal -> pattern adapta apos ~14 dias ✅

### Documentos relacionados

- [SMART_DEFAULTS_PRINCIPLE](../architecture/SMART_DEFAULTS_PRINCIPLE.md) -- design overall
- [GAP_SEVERITY_THRESHOLDS](../architecture/GAP_SEVERITY_THRESHOLDS.md) -- defaults rigidos

**Status:** ⏳ Design adopted 2026-05-25, implementation pending sessao R+8
