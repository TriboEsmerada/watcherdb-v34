# Backup Delayed signal-vs-noise (council 01/09) - PASSO 1: commit
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\DELAYED_PASSO1_commit.ps1"
# DEPOIS (consola Admin): Restart-Service WatcherDBWebServiceV33
# (so backend V3.3 + portal — sem migration, sem collector, sem BD)

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

git add WATCHERDB_V3.3/api/routers/intelligence/backup_delayed_classes.py WATCHERDB_V3.3/api/routers/intelligence/helpers.py WATCHERDB_V3.3/api/routers/intelligence_kpis.py WATCHERDB_V3.3/templates/watcherdb_portal.html WATCHERDB_V3.3/tests/unit/test_backup_delayed_classes_20260901.py WATCHERDB_V3.3/docs/changelog/CHANGELOG.md WATCHERDB_V3.3/findings-inbox.md WATCHERDB_V3.3/docs/context/CONTEXT.md WATCHERDB_V3.3/docs/context/COUNCIL_BACKUP_DELAYED_SIGNAL_2026-09-01.md WATCHERDB_V3.3/docs/context/PROMPT_PROPAGACAO_V6_DELAYED_SIGNAL_2026-09-01.md WATCHERDB_V3.3/docs/context/DELAYED_PASSO1_commit.ps1
git commit -m 'feat(v33): Backup Delayed conta sinal - dedupe por base + perdao chain-reset limitado + bandas visiveis (council 01/09)' -m 'GO do owner sobre recomendacao unanime de 4 vozes + 4 medicoes na BD viva. R1 executivo conta BASES degradadas; R2 DIFF coberto por FULL fresco = cadeia reiniciada (perdao expira com o FULL - f15bfb8; 88% do cohort era transitorio) e DIFF parado >7d = banda propria; R3 master/model/msdb de nos AG = politica por-no com contador visivel (nunca filtro silencioso; DBA_* ficam); R4 sem cap de idade. Modulo unico backup_delayed_classes.py partilhado card+modal (coerencia R5); chave (AgName,Database) nas linhas AG (condicao v1-intel); 8 testes de contrato incl. invariante RPO; badge de classe + linha de reconciliacao no modal. FINDs 20260831-101/103 fixed-pending-validation.' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'
git log -1 --format='%h %s'
