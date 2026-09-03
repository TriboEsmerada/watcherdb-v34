# Mirroring - PASSO 4: commit do hotfix env-slot
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\MIRR_PASSO4_commit_hotfix.ps1"

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

git add "WATCHERDB INTELLIGENCE V1/database/MIGRATION_MIRRORING_FIX_ENV_SLOT.sql" "WATCHERDB INTELLIGENCE V1/database/MIGRATION_MIRRORING_WITNESS_QUEUES.sql" "WATCHERDB INTELLIGENCE V1/database/SECTION16_MIRRORING_STATUS.sql" "WATCHERDB INTELLIGENCE V1/database/CHANGELOG_JOBS_COLETA.md" WATCHERDB_V3.3/docs/context/SOLUCOES.md WATCHERDB_V3.3/docs/context/CONTEXT.md WATCHERDB_V3.3/docs/context/MIRR_PASSO3_hotfix.ps1 WATCHERDB_V3.3/docs/context/MIRR_PASSO4_commit_hotfix.ps1 WATCHERDB_V3.3/docs/context/PROMPT_PROPAGACAO_V6_MIRRORING_2026-08-31.md
git commit -m 'fix(v1 intel): hotfix mirroring _ACTIVE - slot por ambiente (triplicacao no modal)' -m 'A migration da noite recriou a view a partir do canonical SECTION16, cujo CTE ActiveSlot ignorava a coluna Environment da KPI_STG_ACTIVE_TABLE (3 linhas por KPI, by design nos 36 KPIs) - CROSS JOIN multiplicava: 330 rows na ACTIVE e SUSPENDED em triplicado. A view viva pre-31/08 estava certa: o canonical contaminou o vivo (FIND-20260810-101 ao contrario). Fix AND a.Environment por branch, corrigido em triplo (BD viva + canonical + migration original). Regra nova no CHANGELOG e SOLUCOES: diff sys.sql_modules vs canonical antes de DROP/CREATE de view viva. Inclui reforco do prompt V6 (canonical V6 obrigatorio).' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'
git log -1 --format='%h %s'
