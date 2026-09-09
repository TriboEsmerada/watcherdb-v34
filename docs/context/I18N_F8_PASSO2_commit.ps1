# Lote F8 (painel LIVE) - PASSO 2: commit (com guarda anti-repeticao)
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
$subject = 'fix(i18n): lote F8 BUG-003 - painel LIVE segue o idioma (live.*)'
if ((git log -1 --format=%s) -eq $subject) { Write-Host "[ABORT] o ultimo commit ja e' este lote - nada a fazer"; exit 1 }
if (-not (Select-String -Path templates/watcherdb_portal.html -Pattern "t\('live\.loading_fleet'\)" -Quiet)) { Write-Host "[ABORT] PASSO1 ainda nao foi aplicado"; exit 1 }
git branch --show-current
git add templates/watcherdb_portal.html static/i18n/pt.json static/i18n/pt-BR.json static/i18n/en.json static/i18n/es.json docs/changelog/CHANGELOG.md `
        docs/context/I18N_F8_PASSO1_apply.py docs/context/I18N_F8_PASSO2_commit.ps1 docs/context/I18N_F8_KEYS.json docs/context/CONTEXT.md `
        .claude/agents/v33-i18n-coverage.md
Write-Host "--- a commitar:"; git diff --cached --stat
$msg = @"
$subject

Owner 09/09: "achei mais 1 caso: o LIVE" (A carregar Fleet Dashboard..., Filtrar
instancia..., Canal... em EN). Painel LIVE + drill de disco (portal ~50239-51400):
placeholders, tooltips, mensagens "Sem dados de..." / "Nenhum ... ativo", cabecalhos
de seccao -> 47 chaves live.* em pt-PT/en/es (pt-BR herda), placeholders {n}/{s}/
{program} via _kpiTp. Verificado pelo v33-i18n-linguist. Zero backend.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
"@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
