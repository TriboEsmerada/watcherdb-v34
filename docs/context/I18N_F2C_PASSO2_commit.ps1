# i18n lote F2c (defeitos nas chaves antigas pt/es) - PASSO 2: commit
# Identidade: owner (git). Onde: raiz do V3.4. Rollback: git reset --soft HEAD~1 ou git revert <sha>.
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add static/i18n/pt.json static/i18n/es.json docs/changelog/CHANGELOG.md `
        docs/context/I18N_F2C_PASSO1_apply.py docs/context/I18N_F2C_PASSO2_commit.ps1 docs/context/CONTEXT.md
$msg = @'
fix(i18n): lote F2c - defeitos nas chaves antigas de pt.json e es.json

Achados do v33-i18n-linguist ao reutilizar chaves no F2: es "Critico"->"Crítico" (11),
"Memoria Critico"->"Memoria Crítica", "Trabajos"->"Jobs" (glossario), "DB Disco File
System"->"DB Disk File System", "Advertencia"->"Aviso" (TempDB mantem "Atención");
pt "Memória Crítico"->"Memória Crítica", acentos em processes_alarm_count,
"Warning"/"Critical" nunca traduzidos -> "Aviso"/"Crítico", "Backup Jobs Disabled" ->
"Jobs de Backup Desativados", "FileGroups Usage" -> "Utilização de FileGroups".
So' texto, 30 chaves, zero codigo.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
