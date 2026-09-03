# Backup Delayed (council 01/09) - PASSO 3: particao por severidade da BASE
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\DELAYED_PASSO3_bases_commit.ps1"
# DEPOIS (consola Admin): Restart-Service WatcherDBWebServiceV33
# (backend V3.3 + portal - sem migration, sem collector, sem BD)

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

git add WATCHERDB_V3.3/api/routers/intelligence/backup_delayed_classes.py WATCHERDB_V3.3/templates/watcherdb_portal.html WATCHERDB_V3.3/tests/unit/test_backup_delayed_classes_20260901.py WATCHERDB_V3.3/docs/context/DELAYED_PASSO3_bases_commit.ps1

git commit -m 'fix(v33): modal Backup Delayed particiona por severidade da BASE e charts contam bases - tile e modal batem' -m 'Owner 01/09: tile aviso dizia 2 e a modal mostrava 5; totais dos charts diziam 151 com o tile a 76. Causa: o tile conta BASES pelo pior estado (dedupe R1) mas o pre-filtro da modal filtrava pela severidade da LINHA - linhas warning de bases criticas caiam na modal errada - e as barras contavam linhas. Fix: (1) modulo anota Base_Severity = pior severidade da base em cada linha accionavel; (2) pre-filtro CLASS usa Base_Severity - linha segue a base; (3) barras por ambiente e totais dos 2 charts contam bases distintas via data-basekey (fail-open para linhas se payload antigo); barras por tipo ja equivalem a bases por tipo. Teste de contrato novo: linha warning de base critica leva Base_Severity critical (10 testes verdes).' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'

git log -1 --format='%h %s'
