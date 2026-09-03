# Disk Drive Thresholds -- Per-Categoria (V3.3 Local)

**Status:** Active (Wave T shipped 2026-06-02)
**Tier:** Std (Smart Defaults Camada 2)
**Authoritative source:** V1 schema `KPI_MSSQL_DISK_USAGE_DET_VIEW.Drive_Category` + `INSTALACAO_COMPLETA_UNIFICADA.sql` linhas 2806-2900

## Resumo

A partir de Wave T (2026-06-02), thresholds de disk space sao per-categoria
de drive em vez de flat global 20%/10%. Categoria detectada automaticamente
por mount point pattern (zero AI/ML, lookup determinista no momento da view
query).

## Categorias e thresholds

| Drive_Category | Mount Pattern                               | Warning if Available% < | Critical if Available% < |
|----------------|---------------------------------------------|-------------------------|--------------------------|
| **System**     | `C:\`                                       | 25%                     | 15%                      |
| **Log**        | `T:\`, `L:\`                                | 20%                     | 10%                      |
| **Data**       | (default) `F:\`, `G:\`, outros              | 20%                     | 10%                      |
| **Archive**    | `%BKP%`, `%BCK%`, `%BACK%`, `%ARCH%`, `Z:\`, `X:\`, `W:\` | 15%                     | 5%                       |

## Razao por categoria

### System (`C:\`) -- mais conservador (25/15)

C:\ tipicamente tem Windows + page file + logs + temp + apps. Baseline
livre alto importante para evitar OS instability (page file expansion,
event log overflow, temp file allocation). 25% warning permite headroom
para spikes; 15% critical e' indicador inequivoco de problema.

### Log (`T:\`, `L:\`) -- moderado (20/10)

Drives dedicados a transaction log. Crescimento previsivel mas pode
escalar rapidamente durante long transactions / rebuild operations.
Warning 20% permite triage; critical 10% e' ponto de intervencao.

Convencao mount letter:
- `T:\` -- transaction log (padrao SQL Server DBA)
- `L:\` -- alternative log naming (alguns shops)

### Data (default) -- moderado (20/10)

Drives de data files (mdf / ndf). Mesmo nivel de Log porque MDF growth
costuma ser mais previsivel mas tablespace explosao em casos de bulk
insert / index rebuild justifica margem.

Default category -- qualquer mount que nao cai noutras 3 patterns.

### Archive (`%BKP%`, `%BCK%`, `%BACK%`, `%ARCH%`, Z, X, W) -- liberal (15/5)

Drives intencionalmente preenchidos com backups / archives / cold storage.
Encher esta drives e' design intent, nao alarme. 15% warning serve para
trigger retention review; 5% critical e' o ponto onde proxima backup
podera falhar.

Patterns capturados:
- Volume label contains `BKP`, `BCK`, `BACK`, `ARCH` (qualquer ordem)
- Mount letters `Z:`, `X:`, `W:` (convencoes comuns para archive em
  ambientes Windows enterprise)

## Anti-pattern descartado (2026-05-25)

**Per-DB threshold override matrix** -- discutido + descartado durante
investigacao Smart Defaults Initiative. Razao:
- Config explosion (N databases x M threshold rules)
- Operational burden (DBA tem que manter matrix)
- Drift inevitavel (config nunca acompanha BD adds/removes)
- Resolve problema errado (DBA fingia threshold flat era ok para todos)

Smart Defaults Camada 2 e' a alternativa correcta: auto-detection +
sensible defaults per drive type, sem config DB-by-DB.

## Implementation -- onde olhar

### V1 schema (source of truth)

- **`KPI_MSSQL_DISK_USAGE_DET_VIEW.Drive_Category`** -- coluna NOVA shipped
  Wave T. Populated via `CASE WHEN d.Drive LIKE 'C:%' THEN 'System' ...`
- **`KPI_MSSQL_DISK_USAGE_AGG_VIEW`** -- thresholds per-categoria aplicados
  no momento do aggregate (`SUM(CASE WHEN Status = 'CRITICAL' ...)`)
- **Migration:** `WATCHERDB INTELLIGENCE V1/database/UPDATE_DISK_USAGE_VIEWS_WAVE_T_R9.sql`
- **Canonical install:** `WATCHERDB INTELLIGENCE V1/database/INSTALACAO_COMPLETA_UNIFICADA.sql` linhas 2806-2900

### V3.3 portal (consumer)

- **Surface A modal badge** -- `templates/watcherdb_portal.html` linhas ~34118-34159
  Fallback "Multi-categoria" + legacy thresholds quando AGG nao envia `Drive_Category`
- **Surface C KPI_DOCUMENTATION** -- linhas ~35327-35540
  `thresholdTable` field com 4-row tabela
- **Renderer** -- linhas ~36049-36085
  Conditional render `${kpi.thresholdTable ? ... : ''}` com i18n branching
- **i18n** -- `static/i18n/{pt,en,es}.json` 13 keys novas em bloco `kpi_modal`

### V6 portal (consumer, propagado Phase 3)

- Mesma logica de Surface C + renderer mas SEM Surface A (V6 nao usa
  inline per-instance metrics) e SEM i18n keys novas (V6 KPI_DOCUMENTATION
  pt-hardcoded por convencao).

## Edge cases & limitacoes

### AGG VIEW limitation (per-instance aggregate)

`KPI_MSSQL_DISK_USAGE_AGG_VIEW` agrega por instancia, NAO por drive.
Uma instancia pode ter drives de varias categorias (C:\ System + F:\ Data
+ T:\ Log + Z:\ Archive). O campo `Drive_Category` so existe na DET view.

**Frontend handling V3.3 Surface A:**
- Detecta `instance.Drive_Category` opcional
- Se presente -> usa threshold per-categoria
- Se ausente -> fallback "Multi-categoria" label + legacy thresholds 10%/20%

**Future enhancement candidato (Wave T+1, NAO implementado):**
- Adicionar `Dominant_Drive_Category` a AGG VIEW (categoria do drive com
  menor `%Free` -- o mais critico da instancia)
- Permite Surface A mostrar threshold preciso da instancia
- Trade-off: complexidade adicional no view query; ainda assim threshold
  exibido pode mascarar outros drives da mesma instancia com categoria
  diferente

### Drives nao classificaveis

Patterns sao exaustivos para mount layouts comuns SQL Server enterprise:
- C: -> System (sempre)
- T:, L: -> Log
- Z:, X:, W: + label patterns -> Archive
- Tudo o resto -> Data (default)

Casos esquisitos (e.g. iSCSI mounts com nomes custom como `\\?\Volume{...}`)
caem em Data. Se cliente reportar mismatch, ajuste do `CASE WHEN` na view
sem precisar de config matrix.

## Refs externos

- Memoria `[[smart-defaults-over-config]]` (principio rejeitando config matrix)
- Memoria `[[smart-defaults-initiative-roadmap]]` (Camadas R+8/R+9/R+10/S+1)
- Skill `[[wave-close]]` (5-surface propagation checklist)
- Nestor cross-product: `~/.nestor-library/watcherdb-family/architecture/disk_thresholds.md`
- V3.3 CHANGELOG `[2.7.0]` 2026-06-02 (entry Wave T)
- V6 CHANGELOG `[unreleased] -- Wave T disk drive auto-tagging` (V6 local-only)
