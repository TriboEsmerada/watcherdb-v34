---
name: wave-open
description: Abre uma Wave numerada nova em WatcherDB V3.3 -- detecta próxima letter via git log, prepara entry de CHANGELOG SemVer com tier annotations, e gera commit message template. Waves NÃO têm doc separado -- vivem no CHANGELOG (convenção V3.3 verificada 2026-05-28).
---

# Wave Open

## When this skill triggers

User diz "abre Wave X", "vamos iniciar Wave Y", "Wave próxima sobre Z", ou pede para começar trabalho não-trivial num módulo V3.3.

## Wave nomenclature

Formato canonical: `Wave <letter>` ou `Wave <letter>+<n>` ou `Wave <letter>+<n>.<sub>`.

Sequência histórica V3.3: A -> B -> C -> ... -> R -> R+1 -> R+11.1/.2/.3 -> R+13 -> R+14. Sub-waves (+N) = follow-ups directos. Sub-sub (.N) = patches.

## Output (passos)

### 1. Detectar próxima Wave

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git log --pretty=format:"%s" -300 | Select-String -Pattern "wave-?([A-Z])(\+\d+(\.\d+)?)?" -AllMatches | ForEach-Object { $_.Matches } | ForEach-Object { $_.Value } | Sort-Object -Unique
```

Analisar output: encontrar maior letter + maior +N + maior .sub. Próxima:
- Tema novo -> `Wave <letter+1>`
- Follow-up directo -> `Wave <letter>+<n+1>`
- Patch ao follow-up -> `Wave <letter>+<n>.<sub+1>`

Propor ao user e esperar confirmação.

### 2. Verificar CHANGELOG actual

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
Get-Content "docs\changelog\CHANGELOG.md" -TotalCount 30
```

Identificar versão actual SemVer (ex: `[2.5.0]`). Decidir bump:
- Wave com nova feature visível -> minor bump (`2.6.0`)
- Wave de bug fix / refactor -> patch bump (`2.5.1`)
- Wave breaking change -> major bump (raro)

### 3. Preparar entry de CHANGELOG (template)

Format Keep a Changelog com **tier annotations obrigatórias `[tier: Std]` ou `[tier: Pro]`** por linha:

    ## [X.Y.Z] - YYYY-MM-DD

    ### Highlights

    - **Wave <X> -- <título curto>**
      <decisão DBA Lead que motivou + edge case se aplicável>

    ### Added

    - **<componente>** (`<path>`): <descrição>. [tier: Std]

    ### Changed

    - **<componente>**: era <antes>, agora <depois>. [tier: Std]

    ### Compatibility

    - <campos legacy mantidos para retrocompat>

    ### Documentation

    - **KB updates** (Pattern C -- mirror local + Nestor central):
      - `knowledge_base/architecture/<area>.md` -- <que mudou>

    ### Refs

    - <commit hashes ou findings refs>

### 4. Commit message template

    feat(v3.3/wave-<X>): <título curto>

    <body>

    Refs: docs/changelog/CHANGELOG.md#[X.Y.Z]

### 5. Checklist pré-execução

- [ ] Tier validation via [[force-tier-checker-precommit]]
- [ ] Specialist consultation se domínio justifica ([[default-consult-specialists]])
- [ ] Cross-tier impact analysis (V3.3 + V6 + V1-Intel? ver [[v33-v6-propagation-rule]])
- [ ] Smoke test plan definido antes de começar (lesson Wave R+11.2 ARCHIVED ROI -2.3%)
- [ ] Branch decision via [[branch-per-project]] (bundle ou separado?)

## Importante

- Wave nomenclature OBRIGATÓRIA para trabalho não-trivial (>1 commit). Single-line fix = commit normal sem Wave.
- **NÃO criar doc separado de wave** -- não existe `docs/waves/`. Wave = colecção de entries no CHANGELOG SemVer.
- **`[tier: Std]` ou `[tier: Pro]` por linha** -- convenção V3.3 estabelecida e verificada.
- Status `ARCHIVED` requer ROI doc post-mortem (lesson Wave R+11.2).
- Bloco PowerShell respeita [[powershell-cd-prefix]].
