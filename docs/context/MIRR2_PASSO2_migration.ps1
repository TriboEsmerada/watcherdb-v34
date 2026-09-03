# Plano KPI Mirror 01/09 - PASSO 2: migration HIST + ordem de deploy
# ORDEM OBRIGATORIA (violar = Msg 208 -> modal vazio):
#   commits -> ESTA migration -> Restart-Service WatcherDBCollector (Admin)
#   -> Restart-Service WatcherDBWebServiceV33 (Admin) -> F5
# (Nao e' preciso esperar ciclo entre os restarts: a HIST comeca vazia e o
#  frontend degrada para "a monitorizar" ate haver pontos.)
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\MIRR2_PASSO2_migration.ps1"

$file = "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1\database\MIGRATION_MIRRORING_QUEUE_HIST.sql"

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
Write-Host "VERIFICA: table_object_id NOT NULL, rows 0." -ForegroundColor Cyan
Write-Host "DEPOIS (consola Admin, pela ordem):" -ForegroundColor Yellow
Write-Host "  Restart-Service WatcherDBCollector"
Write-Host "  Restart-Service WatcherDBWebServiceV33"
Write-Host "F5: modal mostra triagem REBUILD no SharePoint; tendencia aparece ~10 min depois (2+ ciclos na HIST). Diz 'restarts feitos' ao Claude para a validacao final."
