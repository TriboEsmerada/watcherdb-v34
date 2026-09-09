# Lote F6a (modal Analise Preditiva) - PASSO 2: commit (com guarda anti-repeticao, licao 0fa01e6)
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
$subject = 'fix(i18n): lote F6a BUG-003 - modal Analise Preditiva de Crescimento segue o idioma'
if ((git log -1 --format=%s) -eq $subject) { Write-Host "[ABORT] o ultimo commit ja e' este lote - nada a fazer"; exit 1 }
if (-not (Select-String -Path templates/watcherdb_portal.html -Pattern "t\('predict\.title'\)" -Quiet)) { Write-Host "[ABORT] PASSO1 ainda nao foi aplicado"; exit 1 }
git branch --show-current
git add templates/watcherdb_portal.html static/i18n/pt.json static/i18n/en.json static/i18n/es.json docs/changelog/CHANGELOG.md `
        docs/context/I18N_F6A_PASSO1_apply.py docs/context/I18N_F6A_PASSO2_commit.ps1 docs/context/I18N_F6A_KEYS.json docs/context/CONTEXT.md
Write-Host "--- a commitar:"; git diff --cached --stat
$msg = @"
$subject

Owner 09/09: modal preditiva em PT com EN activo. Titulo, carregamento, ecras
"Sem Dados Historicos" / "Script Nao Encontrado" / erro / pop-up bloqueado e o
botao Fechar passam a chaves predict.* (27) em pt-PT/en/es; referencias legadas
a "Oracle" removidas dos textos; funcoes duplicadas (2.a sobrepoe a 1.a) ambas
traduzidas. Verificado pelo v33-i18n-linguist. Zero backend; o 403 do endpoint
e' achado separado (SameOriginMiddleware).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
"@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
