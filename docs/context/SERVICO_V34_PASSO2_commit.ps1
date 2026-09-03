# Servico V34 (8434) - PASSO 2: commit do codigo + docs (owner executa)
# Identidade: owner (git). Impacto: so' git local. Rollback: git reset --soft HEAD~1
# Mensagem via ficheiro + -F (licao 03/09: -m com aspas duplas parte no PS7).
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current   # esperado: main
git status --short          # esperado: M watcherdb_service.py, deploy/release_vars.psd1, CHANGELOG, CONTEXT, SOLUCOES, COMANDOS_UTEIS + ?? runbook/este ps1

git add watcherdb_service.py deploy/release_vars.psd1 tests/unit/test_service_entry.py `
        docs/changelog/CHANGELOG.md docs/context/CONTEXT.md docs/context/SOLUCOES.md `
        docs/context/COMANDOS_UTEIS_INFRA_LOCAL.md `
        docs/context/SERVICO_V34_8434_RUNBOOK_2026-09-03.md `
        docs/context/SERVICO_V34_PASSO2_commit.ps1 `
        docs/context/DELAYED_ROTULOS_PASSO1_commit.ps1

$msg = @'
feat(service): WatcherDBWebServiceV34 na porta 8434, paralelo ao V33

Decisao owner 03/09 (AI recomendava cutover de 1 servico; owner escolheu
linha paralela). Parecer deploy-architect + port-checker (8434 livre).
- watcherdb_service.py: SERVICE_NAME/DISPLAY/DESC V3.4, DEFAULT_PORT=8434,
  prefixo do mutex WatcherDBV34_, banner de consola.
- deploy/release_vars.psd1: produto 3.4, servico/porta 8434, InstallFolderName
  e DataFolderName WatcherDB\V3.4 (gap frozen/MSI), MsiFileName 3.4;
  UpgradeCode mantido (MSI 3.4 = upgrade da 3.3 no cliente).
- docs: runbook de instalacao/rollback, COMANDOS_UTEIS (5 servicos, nota 8434),
  CHANGELOG, CONTEXT, SOLUCOES (licao git commit -m no PS7).
Porta em runtime continua a vir de WATCHERDB_PORT (.env da pasta).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
