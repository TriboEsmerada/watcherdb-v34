# Smart Defaults Principle -- WatcherDB V3.3 Architecture

**Data:** 2026-05-25
**Status:** Design adopted, multi-wave implementation roadmap
**Audience:** WatcherDB engineering team + product

---

## Filosofia (principio orientador)

> **"Smart defaults + simple mute para excepcoes > config infinita"**
>
> Sistema deve detectar comportamento esperado automaticamente. Config manual apenas onde detection nao chega. Mute list para silenciar excepcoes conhecidas, nao threshold matrix.

### Por que esta abordagem

**DBA Lead profile:** mid-market enterprise (per cliente target Std tier). Tipicamente DBA Lead tem 50-500 instances para gerir. NAO quer virar config manager. Quer "just tell me what's broken".

**Banking client scale:** 5000+ DBs. Per-DB threshold matrix = 15000+ config rows. Insustentavel:
- Quem cria? Quem revisa? Quem actualiza quando workload muda?
- "Why isnt it alerting?" -- "Did you check overrides?" -- support nightmare
- Compliance: audit trail de quem set thresholds, quando, porque

**Competitive positioning:** SolarWinds DPA / Redgate / Quest sao config-heavy. V3.3 ja diferencia em automation (backup schedule detection). Adicionar override matrix = transformar diferenciador em commodity.

---

## Anti-pattern: "config table" approach

Proposta inicial (descartada) era:

```sql
-- ❌ ANTI-PATTERN: NAO IMPLEMENTAR
CREATE TABLE WDB_BACKUP_SLA_OVERRIDE (
    Instance VARCHAR(64),
    Database VARCHAR(128) NULL,
    Backup_Type CHAR(1),
    Max_Hours INT,
    Severity VARCHAR(10),
    Notes VARCHAR(500),
    PRIMARY KEY (Instance, ISNULL(Database, ''), Backup_Type)
);
```

**Problemas:**
1. **Config sprawl** -- escala com `instances × databases × backup_types`
2. **Per-DB override raramente e' o real need** -- usual e' "esta categoria de DB tem regra diferente", nao per-DB individual
3. **Aumenta support burden + audit complexity**
4. **DBA contraria intencao** ("just tell me what's broken")

---

## Pattern aprovado: 4-camada priority chain

Ordem de aplicacao (mais especifico ganha):

```
1. Per-instance MUTE list      (excepcao explicita, com expiry)
            ↓ fallback
2. Auto-baseline               (history-based pattern detection)
            ↓ fallback
3. Schedule detection          (msdb.sysjobs + sysschedules)
            ↓ fallback
4. Smart global defaults       (industry standard thresholds)
```

**Sem step 0** = NO per-DB config matrix.

### Mute list (camada 1)

Tabela MINIMA, instance-level, com expiry obrigatorio:

```sql
-- ✅ PATTERN APROVADO -- 1 row por instance silenciada
CREATE TABLE WDB_KPI_MUTE (
    Kpi_Type VARCHAR(40)     NOT NULL,    -- 'backup-failed', 'disk-usage', etc
    Instance VARCHAR(64)     NOT NULL,
    Reason VARCHAR(500)      NOT NULL,    -- justificacao audit-friendly
    Created_By VARCHAR(64)   NOT NULL,
    Created_At DATETIME2     NOT NULL DEFAULT GETDATE(),
    Mute_Until DATETIME2     NOT NULL,    -- expiry mandatory (no permanent mutes)
    PRIMARY KEY (Kpi_Type, Instance)
);
```

**Caracteristicas chave:**
- **Expiry mandatory** -- nao ha mute permanente (forca review periodico)
- **Reason mandatory** -- compliance + audit trail
- **Instance-level only** -- per-DB mute seria config sprawl
- **Universal** -- todos KPIs partilham mesma tabela (kpi_type discriminator)

### Auto-baseline (camada 2)

Detect pattern from production history:
- Backup: msdb.backupset clustering por intervalo
- Disk: per-volume baseline (mount point analysis)
- CPU/Memory: per-server statistical baseline (mean + std)
- Long queries: per-DB workload profile

**Algoritmo generico:**
1. Window 30 dias historia
2. Clustering: identificar dominant pattern
3. Confianca via conformance rate
4. Se confianca > 70% -> usa baseline como expected
5. Se confianca < 70% -> falha ao step 3/4 (schedule ou defaults)

### Schedule detection (camada 3 -- backup specifico)

Ja implementado em [BACKUP_SCHEDULE_BASED_GAP_DETECTION](../features/BACKUP_SCHEDULE_BASED_GAP_DETECTION.md):
- msdb.sysjobs + sysschedules
- Calcula expected_interval_hours
- Tolerance: LOG=2h, DIFF=4h, FULL=12h

### Smart global defaults (camada 4)

Fallback final. Defaults industry-standard, NAO configurable per-instance:
- Backup FULL > 7d critical (see [GAP_SEVERITY_THRESHOLDS](GAP_SEVERITY_THRESHOLDS.md))
- Disk usage > 90% critical
- CPU > 95% sustained critical
- etc.

---

## KPI audit -- onde aplicar Smart Defaults

| KPI | Current threshold | Camada-target | Priority |
|---|---|---|---|
| **Backup gaps** | Schedule + global fallback | + auto-baseline from backupset (Wave R+8) | 1 |
| Disk usage | Global 80%/90% | per-volume baseline (system=stricter, archive=relaxed) auto-tag via mount point | 2 |
| CPU usage | Global thresholds | per-server statistical baseline (z-score > 3) | 3 |
| Memory pressure | PLE < 300s global | per-server PLE baseline (alert on degradation vs baseline) | 3 |
| Long-running queries | Threshold seconds | per-DB query profile (Pro tier expansion) | 4 (Pro) |
| Job failures | Count/severity | mute list for known flaky jobs + alert on NEW failures only | 5 |
| Blocking sessions | Threshold count | workload pattern + outlier detection | 6 |
| AlwaysOn lag | Threshold seconds | per-AG baseline (sync vs async normal lag differs) | 7 |

---

## Roadmap multi-wave

| Wave | KPI | Camada | Esforco | Sessao |
|---|---|---|---|---|
| **R+8** | Backup gaps (cobrir TSM/Commvault) | 2 (baseline from backupset) | ~4-6h | Proxima |
| R+9 | Disk usage auto-tagging | 2 (baseline per-volume) | ~2-3h | Seguinte |
| R+10 | WDB_KPI_MUTE table + admin UI | 1 (universal mute) | ~3h | Apos R+9 |
| S+1 | Statistical baseline engine (CPU/Memory/lag) | 2 (cross-KPI) | ~8-10h | Sessao dedicada |
| V5+ | AI anomaly (Pro tier) | 0-AI (Cascade Intelligence) | ja existe | -- |

---

## Principios derivados (regras para futuras decisoes)

1. **Default to detection, not config** -- nova feature deve preferir auto-detect a config-table
2. **Config tables sao ultimo recurso** -- justificacao explicita em design doc
3. **Mute sempre com expiry** -- review forcada cada N meses
4. **Instance-level granularity max** -- per-DB config so com use case forte
5. **Industry-standard defaults** -- copiar do best-in-class (Microsoft sp_configure docs, Brent Ozar, etc), nao reinventar
6. **KPI semantic refinement -- signal vs noise** -- KPI deve mostrar SIGNAL accionavel, NAO noise estrutural (decisoes conscientes de DBA que nao sao bugs). Exemplo: backup-no-checksum filtra FULL+DIFF only porque LOG sem checksum e' decisao perf aceitavel, nao silent corruption risk real. Ver [[Wave R+11]] como precedente.

---

## KPI semantic refinement -- signal vs noise (Wave R+11)

> **STATUS 2026-05-26 (ARCHIVED):** Wave R+11 (filter type-specific FULL+DIFF
> only) inicialmente REVERTED 2026-05-25 por VIEW stale (coluna existia em
> tabelas BLUE/GREEN per-env mas VIEW cacheava schema antigo).
>
> **R+11.2 investigation 2026-05-26:** `sp_refreshview` resolveu o cache;
> coluna agora visivel. Mas analise de ROI mostrou:
> - Distribution H3 confirmada: ~97% no_checksum events sao LOG (raw)
> - **Dedupe R+11.3 ja' colapsa a maioria do noise** (raw 200k -> 1224 DBs)
> - Pos-filter R+11 type-specific: 1224 -> 1196 DBs (apenas **-2.3%**)
> - Apenas 28 DBs tem **apenas** LOG no_checksum (sem FULL/DIFF)
>
> **Decisao:** Wave R+11.2 ARCHIVED. ROI marginal nao justifica complexidade
> extra (4 hunks helpers.py + intelligence_kpis.py + portal). R+11.3 dedupe
> foi o real signal-vs-noise win para este KPI especifico.
>
> **Principio mantem-se valido** e aplica-se a futuros KPIs. **Insight novo:**
> dedupe por unique entity pair (Instance+DB) muitas vezes colapsa o noise
> ANTES de qualquer filter type-specific ser necessario. Considera dedupe
> primeiro; filter so' se dedupe insuficiente.
>
> **Lessons learned consolidadas:**
> 1. Validar prerequisito de dados via INFORMATION_SCHEMA antes de filter
> 2. VIEW stale e' bug silencioso comum -- `sp_refreshview` apos schema changes
> 3. **Dedupe entity-pair primeiro, filter type-specific depois** -- ordem
>    correcta de signal-vs-noise refinement
> 4. ROI matters -- nem todo filter semantico se traduz em UX value

**Principio:** quando um KPI inclui "ruido estrutural" (events que sao decisao consciente legitima, nao risco real), DBA Lead perde sinal accionavel. Refinamento elimina ruido na fonte, mantem dashboard accionavel.

**Caso study -- Backup with Checksum (backup-no-checksum):**

Antes Wave R+11:
- KPI contava TODOS backups sem checksum: FULL + DIFF + LOG
- ~97% das events eram LOG (per H3 confirmed Wave R)
- LOG sem checksum = decisao DBA aceitavel (perf trade-off em backups frequentes cada 1-15min)
- Resultado: ~200k events visiveis, ~5k accionaveis, 195k noise -> alert fatigue

Pos Wave R+11:
- KPI filtra FULL + DIFF only (LOG excluido)
- FULL+DIFF sem checksum = silent corruption risk real (base do RESTORE chain)
- is_damaged sempre incluido (corruption real, agnostico a backup type)
- Resultado: ~5k events visiveis, 100% accionaveis -> signal puro

**Como decidir se KPI tem noise estrutural:**

1. Investiga distribuicao por sub-tipo (similar a H3 analysis Wave R)
2. Se >70% events sao um sub-tipo conhecido como "config consciente" -> noise
3. Filter na fonte (collector OU backend query)
4. Documenta exclusao em tooltip + memoria + commit history
5. Alternativa: split em 2 KPIs (signal + diagnostic)

**Memorias relacionadas:**
- [[feedback-kpi-signal-vs-noise]] -- principio orientador
- [[smart-defaults-over-config-matrix]] -- mesmo espirito (no over-engineering)

---

## Documentos relacionados

- [BACKUP_SCHEDULE_BASED_GAP_DETECTION](../features/BACKUP_SCHEDULE_BASED_GAP_DETECTION.md) -- camada 3 implementacao actual
- [GAP_SEVERITY_THRESHOLDS](GAP_SEVERITY_THRESHOLDS.md) -- camada 4 defaults
- [V33_PIPELINE_MAP](V33_PIPELINE_MAP.md) -- arquitectura overall

---

## Historico

- **2026-05-25:** Design adopted apos discussao DBA Lead sobre per-instance backup thresholds. Owner reforcou "smart defaults > config infinita" como principio. Doc criado para capturar decisao + roadmap.
