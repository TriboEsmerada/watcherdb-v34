# Mirroring - PASSO 3 (HOTFIX): view _ACTIVE com slot por AMBIENTE
# Bug da noite: canonical SECTION16 ignorava a coluna Environment da
# KPI_STG_ACTIVE_TABLE (3 linhas por KPI) -> SUSPENDED em triplicado no modal.
# Identidade: a TUA conta (DROP/CREATE VIEW + GRANT).
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\MIRR_PASSO3_hotfix.ps1"

$file = "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1\database\MIGRATION_MIRRORING_FIX_ENV_SLOT.sql"

$p = @{
    ServerInstance = "SQLHDSTST505,50760"
    Database       = "WatcherDB_Intelligence"
    InputFile      = $file
    QueryTimeout   = 60
    Verbose        = $true
}
$cmd = Get-Command Invoke-Sqlcmd
if ($cmd.Parameters.ContainsKey('TrustServerCertificate')) { $p['TrustServerCertificate'] = $true }
if ($cmd.Parameters.ContainsKey('DisableVariables'))       { $p['DisableVariables'] = $true }

Invoke-Sqlcmd @p | Format-Table -AutoSize

Write-Host ""
Write-Host "VERIFICA: total_active = 110 · problemas = 1 (a SUSPENDED com a fila)" -ForegroundColor Cyan
Write-Host "DEPOIS (consola Admin): Restart-Service WatcherDBWebServiceV33" -ForegroundColor Yellow
Write-Host "  -> resolve TAMBEM o drill-down sem campos novos (V33 ainda corre codigo antigo)."
Write-Host "F5 no portal: modal com 1 cartao, Safety/Witness/filas visiveis."
