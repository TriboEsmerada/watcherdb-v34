# Gap Severity Classification - Thresholds Definidos

> **Nota arquitectural (2026-05-25):** este documento descreve a **camada 4 (Smart
> global defaults)** do priority chain definido em [SMART_DEFAULTS_PRINCIPLE](SMART_DEFAULTS_PRINCIPLE.md).
> Defaults aplicam-se apenas como fallback final. Camadas superiores (mute list,
> auto-baseline, schedule detection) tem prioridade. NAO adicionar config tables
> per-instance/per-DB sem revisitar o principle doc primeiro.

## 📊 Classificação de Severidade de Gaps

### Quando o Sistema TEM Schedule Real (SQL Agent Job)

**Thresholds FIXOS independentes do tipo de backup:**

| Severidade | Threshold | Descrição |
|------------|-----------|-----------|
| 🟢 **low** | gap ≤ 6h | Atraso aceitável, dentro da margem operacional |
| 🟡 **medium** | 6h < gap ≤ 30h | Requer atenção, backup atrasado |
| 🟠 **high** | 30h < gap ≤ 48h | Urgente, backup muito atrasado |
| 🔴 **critical** | gap > 48h | CRÍTICO, backup há mais de 2 dias sem executar |

### Quando o Sistema NÃO TEM Schedule (Backup Manual ou Job Desabilitado)

**Thresholds por tipo de backup (fallback - padrão inferido):**

#### FULL Backups
| Severidade | Threshold |
|------------|-----------|
| 🟢 low | gap < 168h (7 dias) |
| 🟡 medium | 168h ≤ gap < 240h (10 dias) |
| 🟠 high | 240h ≤ gap < 336h (14 dias) |
| 🔴 critical | gap ≥ 336h (14 dias) |

#### DIFF Backups
| Severidade | Threshold |
|------------|-----------|
| 🟢 low | gap < 24h |
| 🟡 medium | 24h ≤ gap < 48h |
| 🟠 high | 48h ≤ gap < 72h |
| 🔴 critical | gap ≥ 72h |

#### LOG Backups
| Severidade | Threshold |
|------------|-----------|
| 🟢 low | gap < 2h |
| 🟡 medium | 2h ≤ gap < 4h |
| 🟠 high | 4h ≤ gap < 8h |
| 🔴 critical | gap ≥ 8h |

---

## 🎯 Exemplos Práticos

### Exemplo 1: Database com Schedule DIFF de 24h às 19h

**Cenário:** Último backup DIFF foi ontem às 19h, agora são 21h (hoje)

| Tempo decorrido | Gap calculado | Severidade | Explicação |
|----------------|---------------|------------|------------|
| 26h | 2h (26h - 24h) | 🟢 **low** | Atraso de 2h, aceitável (≤ 6h) |
| 32h | 8h (32h - 24h) | 🟡 **medium** | Atraso de 8h, requer atenção (> 6h, ≤ 30h) |
| 58h | 34h (58h - 24h) | 🟠 **high** | Atraso de 34h, urgente (> 30h, ≤ 48h) |
| 76h | 52h (76h - 24h) | 🔴 **critical** | Atraso de 52h, CRÍTICO (> 48h) |

### Exemplo 2: Database com Schedule LOG de 1h

**Cenário:** Último backup LOG foi há 1h30min

| Tempo decorrido | Gap calculado | Severidade | Explicação |
|----------------|---------------|------------|------------|
| 1.5h | 0.5h (1.5h - 1h) | 🟢 **low** | Atraso de 30min, aceitável |
| 4h | 3h (4h - 1h) | 🟢 **low** | Atraso de 3h, ainda low (≤ 6h) |
| 8h | 7h (8h - 1h) | 🟡 **medium** | Atraso de 7h, requer atenção |
| 32h | 31h (32h - 1h) | 🟠 **high** | Atraso de 31h, urgente |

### Exemplo 3: Database SEM Schedule (Backup Manual)

**Cenário:** Database com backups DIFF irregulares (manual)

Usa fallback de thresholds por tipo:
- Se gap < 24h → 🟢 low
- Se 24h ≤ gap < 48h → 🟡 medium
- Se 48h ≤ gap < 72h → 🟠 high
- Se gap ≥ 72h → 🔴 critical

---

## 🔍 Como o Sistema Decide Qual Threshold Usar?

```python
def _classify_gap_severity(backup_type, gap_hours, expected_interval_hours=None):
    if expected_interval_hours:  # TEM SCHEDULE?
        # ✅ USA THRESHOLDS FIXOS (6h, 30h, 48h)
        if gap_hours > 48:
            return 'critical'
        elif gap_hours > 30:
            return 'high'
        elif gap_hours > 6:
            return 'medium'
        else:
            return 'low'
    else:  # NÃO TEM SCHEDULE
        # ⚠️ USA THRESHOLDS POR TIPO (FULL/DIFF/LOG diferentes)
        thresholds = gap_thresholds[backup_type]
        # ... classificação baseada no tipo
```

---

## 📈 Impacto no Dashboard

**Coluna "Issues" agora mostra:**
- ✅ **Nada** se gap ≤ 6h (schedule) ou dentro do esperado (sem schedule)
- 🟡 **"DIFF > 6h"** se 6h < gap ≤ 30h (medium)
- 🟠 **"DIFF > 30h"** se 30h < gap ≤ 48h (high)
- 🔴 **"DIFF > 48h"** se gap > 48h (critical)

**Exemplo real do screenshot:**
- Database: EFTDB2024
- Último DIFF: 2026-05-18 19:03:52
- Último LOG: 2026-02-20 08:00:34
- Schedule DIFF: 1x/dia às 19h (24h de intervalo)

Se agora são 2026-02-20 20:00:
- Gap DIFF: ~26h - 24h = **2h de atraso** → 🟢 **low** → SEM ISSUE
- Gap LOG: depende do schedule LOG (se 1h/hora, gap de 12h = 11h atraso → 🟡 medium)

---

**Data de Atualização:** 2026-02-20
**Thresholds Aprovados:** gap ≤ 6h (low), > 6h-30h (medium), > 30h-48h (high), > 48h (critical)
**Status:** ✅ Implementado e Replicado (DEV, V4, V5)
