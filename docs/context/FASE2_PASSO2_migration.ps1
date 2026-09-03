# Fase 2 KPI Backup Failed - PASSO 2: migration na WatcherDB_Intelligence
# v2 (21/08): sqlcmd.exe nao existe nesta maquina -> Invoke-Sqlcmd (modulo presente).
# Identidade: a TUA conta Windows (precisa de ALTER; sql_monitoring NAO serve).
# ALTER ADD NULL e non-blocking; o collector antigo continua a funcionar.
# Rollback: DROP COLUMN Resolved_By_Success_TS nas 8 tabelas + sp_refreshview.
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\FASE2_PASSO2_migration.ps1"

$file = "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1\database\MIGRATION_F2_RESOLVED_BY_SUCCESS_TS.sql"

# v3: nome CURTO obrigatorio — o hosts fix de 23/07 (172.17.152.49) so cobre
# "SQLHDSTST505"; o FQDN .grupo.bpi nao resolve (DNS flap conhecido).
# Porta 50760 verificada aberta no IP a 21/08 (Test-NetConnection).
$p = @{
    ServerInstance = "SQLHDSTST505,50760"
    Database       = "WatcherDB_Intelligence"
    InputFile      = $file
    QueryTimeout   = 120
    Verbose        = $true    # PRINT do script sai neste stream
}
# Modulos SqlServer recentes exigem confianca explicita no certificado
$cmd = Get-Command Invoke-Sqlcmd
if ($cmd.Parameters.ContainsKey('TrustServerCertificate')) {
    $p['TrustServerCertificate'] = $true
}
# Desligar expansao $(var) do sqlcmd — o script nao usa variaveis e o batch
# parser antigo do SQLPS e' fragil
if ($cmd.Parameters.ContainsKey('DisableVariables')) {
    $p['DisableVariables'] = $true
}

Invoke-Sqlcmd @p | Format-Table -AutoSize

Write-Host ""
Write-Host "VERIFICA no output acima:" -ForegroundColor Cyan
Write-Host "  Parte 4.1 -> 8 linhas com Has_Resolved_By_Success_TS = YES"
Write-Host "  Parte 4.2 -> devolve NULL (coluna visivel via view)"
Write-Host "  Parte 4.3 -> 100 por cento unresolved (baseline; collector antigo ainda nao preenche)"
Write-Host "Depois diz 'migration feita' ao Claude - ele faz o restart do collector e a validacao."
