---
name: finding-register
description: Regista finding em WatcherDB V3.3 usando o sistema dual estabelecido (2026-05-05) -- inbox compacto (1XX) ou formal um-por-ficheiro (0XX). Anti-colisão obrigatória scan dos dois sistemas.
---

# Finding Register

## When this skill triggers

User diz "regista finding", "abre FIND-...", "isto é uma finding P1", ou descreve issue não-trivial que merece tracking formal.

## Convenção dual (estabelecida 2026-05-05)

V3.3 tem **dois sistemas paralelos** -- escolher antes de numerar:

| Sistema | Path | Sequência | Quando usar |
|---|---|---|---|
| **Compacto inline** | `findings-inbox.md` (raíz) | **1XX** (101-199) | **Default.** Quick triage. 7 campos. |
| **Formal por-ficheiro** | `docs/findings/FIND-YYYYMMDD-NNN-<slug>.md` | **0XX** (001-099) | Findings complexas, sweep histórico, tabela metadata extensa. Pasta pode não existir actualmente -- criar se necessário. |

Migração retroactiva 2026-05-05: 7 findings inbox renumeradas de 001-007 -> 101-107 (anti-colisão).

## Output (passos)

### 1. Determinar próximo NNN (scan AMBOS sistemas)

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
$today = Get-Date -Format yyyyMMdd
Write-Output "=== findings-inbox.md (1XX) ==="
Select-String -Path "findings-inbox.md" -Pattern "FIND-$today-(\d+)" | ForEach-Object { $_.Matches.Groups[1].Value } | Sort-Object -Descending | Select-Object -First 3
Write-Output "=== docs/findings (0XX) ==="
if (Test-Path "docs/findings") { Get-ChildItem "docs/findings" -Filter "FIND-$today-*.md" | Select-Object Name } else { Write-Output "(pasta não existe ainda)" }
```

Próximo NNN:
- **Compacto:** max(1XX hoje) + 1; se nenhum -> 101.
- **Formal:** max(0XX hoje) + 1; se nenhum -> 001.

### 2. Severity (rubric V3.3 estabelecida)

- **P0** -- produção quebrada, data loss possível, segurança crítica, regressão Std visível ao cliente
- **P1** -- bug funcional, performance degradada, gap tiering, divergência Std/Pro material
- **P2** -- limpeza, docs em falta, dívida técnica não-blocking

### 3. Category (enum canónico V3.3)

`security | performance | reliability | opportunity | tiering | docs | ux | coverage | privacy | compliance | accessibility | regression-risk | i18n`

### 4a. Sistema compacto -- ADICIONAR entry a findings-inbox.md

Append no final (mantendo separador `---`):

    ---

    ## FIND-YYYYMMDD-1NN -- <título curto>

    - **Severity:** P0 | P1 | P2
    - **Category:** <enum>
    - **Owner specialist:** <nome do agent>
    - **Evidence:** <path:linha ou query/commit ref>
    - **Recommendation:** <1 frase prescritiva>
    - **Status:** open
    - **Created:** YYYY-MM-DD
    - **Updated:** YYYY-MM-DD

### 4b. Sistema formal -- CRIAR ficheiro docs/findings/FIND-YYYYMMDD-0NN-<slug>.md

Apenas se finding é complexa o suficiente para justificar. Schema = entry compacta + secções extra (Análise, Reprodução, Impacto, Fix proposto, Validação, Handoffs). User decide.

### 5. Triage cadence (estabelecida)

- **Diário:** orquestrador relê P0/P1 abertos no início de cada sessão (alinhar com [[default-consult-specialists]])
- **Semanal:** DBA Lead revê P2 e decide promover/arquivar

### 6. Commit title

    docs(findings): register FIND-YYYYMMDD-NNN -- <título>

ou se já está a ser corrigido:

    fix(<scope>): close FIND-YYYYMMDD-NNN -- <título>

## Importante

- **SCAN AMBOS SISTEMAS antes de numerar** -- colisão 1XX vs 0XX já causou migração retroactiva (2026-05-05).
- **Default = compacto (inbox).** Formal é excepção, não regra.
- Severidade P0/P1 -> dispatch imediato ao owner specialist ([[default-consult-specialists]]).
- Findings fechadas mantêm-se -- ground truth histórico, nunca deletar.
- Bloco PowerShell respeita [[powershell-cd-prefix]].
