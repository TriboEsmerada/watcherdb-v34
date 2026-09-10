# Reset da password do qa_dba pela API (8434), com prova de UM login. PS7. Corre TU: pwsh docs/context/QA_RESET_QA_DBA.ps1
# Identidade: a tua conta admin do portal. Impacto: so' a conta qa_dba (sessoes antigas dela revogadas, por desenho).
# Rollback: novo reset. Nada e' escrito em ficheiro; nada e' impresso alem do role devolvido.
#Requires -Version 7

$base = if ($env:WATCHERDB_BASE_URL) { $env:WATCHERDB_BASE_URL } else { "https://localhost:8434" }
Write-Host "Servico: $base"

$admin = (Read-Host "utilizador admin [Enter = salomao]").Trim()
if (-not $admin) { $admin = "salomao" }
if ($admin -match '\s|!') { throw "nome de utilizador invalido: '$admin'. ABORT." }
$pwAdmin = Read-Host "password de $admin" -AsSecureString
$pwNova  = Read-Host "NOVA password do qa_dba (forte)" -AsSecureString
$p1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwAdmin))
$p2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwNova))

try {
    $login = Invoke-RestMethod -Uri "$base/api/auth/login" -Method Post -ContentType "application/json" `
        -Body (@{ username = $admin; password = $p1 } | ConvertTo-Json) -SkipCertificateCheck
} catch {
    throw "login de $admin falhou ($($_.Exception.Message)). Nao repetir as cegas: 5 falhas bloqueiam 15 min. ABORT."
}
if ($login.user.role -ne 'admin') { throw "a conta $admin tem role '$($login.user.role)', o reset exige admin. ABORT." }
$h = @{ Authorization = "Bearer $($login.access_token)"; Origin = $base }

$r = Invoke-RestMethod -Uri "$base/api/auth/users/qa_dba/reset-password" -Method Post -ContentType "application/json" `
    -Headers $h -Body (@{ new_password = $p2 } | ConvertTo-Json) -SkipCertificateCheck
Write-Host "reset: $($r | ConvertTo-Json -Compress)"

# prova: UM login do qa_dba
try {
    $prova = Invoke-RestMethod -Uri "$base/api/auth/login" -Method Post -ContentType "application/json" `
        -Body (@{ username = "qa_dba"; password = $p2 } | ConvertTo-Json) -SkipCertificateCheck
    Write-Host "qa_dba entra; role = $($prova.user.role)"
} catch {
    throw "qa_dba continua a falhar apos o reset ($($_.Exception.Message)): ver WatcherDB_Auth_Log antes de tentar de novo."
}
Write-Host "Agora: WATCHERDB_QA_DBA_PASS no .env.qa = a nova password; depois pwsh docs/context/TG1_PASSO9_commit.ps1"
