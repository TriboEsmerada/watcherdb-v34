# Reset da password de uma conta do portal pela API (8434), com prova de UM login. PS7. Corre TU.
#   pwsh docs/context/QA_RESET_PASSWORD.ps1 -User qa_viewer
#   pwsh docs/context/QA_RESET_PASSWORD.ps1 -User qa_dba
# Para a TUA conta admin usa o portal (menu do utilizador > alterar password), nao este script.
# Identidade: a tua conta admin. Impacto: so' a conta indicada (sessoes antigas dela revogadas). Rollback: novo reset.
#Requires -Version 7
param([Parameter(Mandatory)][string]$User)

$base = if ($env:WATCHERDB_BASE_URL) { $env:WATCHERDB_BASE_URL } else { "https://localhost:8434" }
if ($User -match '\s|!' -or $User -eq 'salomao') { throw "conta invalida para este script: '$User'. ABORT." }
$admin = (Read-Host "utilizador admin [Enter = salomao]").Trim(); if (-not $admin) { $admin = "salomao" }
$pwAdmin = Read-Host "password de $admin" -AsSecureString
$pwNova  = Read-Host "NOVA password de $User (forte; escreve-a AQUI, nao na pergunta)" -AsSecureString
$p1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwAdmin))
$p2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwNova))
if (-not $p2 -or $p2.Length -lt 10) { throw "password nova vazia ou curta (<10). ABORT." }

try {
    $login = Invoke-RestMethod -Uri "$base/api/auth/login" -Method Post -ContentType "application/json" `
        -Body (@{ username = $admin; password = $p1 } | ConvertTo-Json) -SkipCertificateCheck
} catch { throw "login de $admin falhou ($($_.Exception.Message)). Nao repetir as cegas (5 falhas = 15 min). ABORT." }
if ($login.user.role -ne 'admin') { throw "a conta $admin nao e' admin. ABORT." }
$h = @{ Authorization = "Bearer $($login.access_token)"; Origin = $base }
$r = Invoke-RestMethod -Uri "$base/api/auth/users/$User/reset-password" -Method Post -ContentType "application/json" `
    -Headers $h -Body (@{ new_password = $p2 } | ConvertTo-Json) -SkipCertificateCheck
Write-Host "reset: $($r | ConvertTo-Json -Compress)"
try {
    $prova = Invoke-RestMethod -Uri "$base/api/auth/login" -Method Post -ContentType "application/json" `
        -Body (@{ username = $User; password = $p2 } | ConvertTo-Json) -SkipCertificateCheck
    Write-Host "$User entra; role = $($prova.user.role)"
} catch { throw "$User continua a falhar apos o reset: ver WatcherDB_Auth_Log. ABORT." }

# .env.qa: actualiza a(s) linha(s) desta conta, sem mostrar a password
$envFile = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) '.env.qa'
if (Test-Path $envFile) {
    $linhas = @(Get-Content $envFile)
    # prefixos (WATCHERDB_QA_VIEWER, WATCHERDB_QA, ...) cujo *_USER e' esta conta
    $prefixos = @($linhas | Where-Object { $_ -match '^(WATCHERDB_QA(_[A-Z]+)?)_USER=(.+)$' -and $Matches[3].Trim() -eq $User } |
                 ForEach-Object { $_ -replace '_USER=.*$', '' })
    $final = $linhas | ForEach-Object {
        $l = $_
        foreach ($pf in $prefixos) { if ($l -match ('^' + [regex]::Escape($pf) + '_PASS=')) { $l = "${pf}_PASS=$p2" } }
        $l
    }
    Set-Content -Path $envFile -Value $final -Encoding utf8
    Write-Host ".env.qa actualizado para $User em: $($prefixos -join ', ')"
} else { Write-Host "AVISO: .env.qa nao existe; actualiza a password de $User a mao." }
