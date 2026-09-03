# Mirroring Witness+Queues - PASSO 2: migration na WatcherDB_Intelligence
# Identidade: a TUA conta (ALTER + DROP/CREATE VIEW + GRANT; sql_monitoring NAO serve).
# ALTER ADD NULL non-blocking; DROP/CREATE das views e' instantaneo; collector
# antigo continua a funcionar ate ao restart (INSERT por nome, colunas novas NULL).
# Rollback: DROP COLUMN das 4 colunas nas 7 tabelas + re-CREATE views antigas.
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\MIRR_PASSO2_migration.ps1"

$file = "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1\database\MIGRATION_MIRRORING_WITNESS_QUEUES.sql"

# Nome CURTO (hosts fix 23/07; FQDN nao resolve) + porta verificada 21/08
$p = @{
    ServerInstance = "SQLHDSTST505,50760"
    Database       = "WatcherDB_Intelligence"
    InputFile      = $file
    QueryTimeout   = 120
    Verbose        = $true
}
$cmd = Get-Command Invoke-Sqlcmd
if ($cmd.Parameters.ContainsKey('TrustServerCertificate')) { $p['TrustServerCertificate'] = $true }
if ($cmd.Parameters.ContainsKey('DisableVariables'))       { $p['DisableVariables'] = $true }

Invoke-Sqlcmd @p | Format-Table -AutoSize

Write-Host ""
Write-Host "VERIFICA no output acima:" -ForegroundColor Cyan
Write-Host "  Parte 4.1 -> 7 linhas, 4x YES cada"
Write-Host "  Parte 4.2 -> sem Msg 207 (views recriadas com as colunas)"
Write-Host "  Parte 4.3 -> baseline: with_lsq=0 (collector antigo ainda nao preenche)"
Write-Host ""
Write-Host "DEPOIS (consola Admin): Restart-Service WatcherDBCollector" -ForegroundColor Yellow
Write-Host "Esperar 1 ciclo (5 min) e dizer 'collector reiniciado' ao Claude -"
Write-Host "ele valida a STG (filas preenchidas, ~101 GB na suspensa) e da o GO"
Write-Host "para o Restart-Service WatcherDBWebServiceV33 (tambem Admin)."
