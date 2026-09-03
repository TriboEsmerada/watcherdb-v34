# ==============================================================================
# Script de Configuração para SQL Authentication no WatcherDB Intelligence
# ==============================================================================
# Este script configura as variáveis de ambiente para usar SQL Authentication
# em vez de Windows Authentication
# ==============================================================================

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "CONFIGURAÇÃO SQL AUTHENTICATION - WatcherDB Intelligence" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

# Configurações
$SQL_USER = "sql_monitoring"
$SQL_SERVER = "SQLHDSTST505\I01"
$SQL_DATABASE = "WatcherDB_Intelligence"

# Solicitar senha de forma segura
Write-Host "Digite a senha do usuário SQL '$SQL_USER':" -ForegroundColor Yellow
$SecurePassword = Read-Host -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
$SQL_PASSWORD = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)

# Testar conexão
Write-Host ""
Write-Host "Testando conexão com SQL Server..." -ForegroundColor Yellow

try {
    $connectionString = "Server=$SQL_SERVER;Database=$SQL_DATABASE;User Id=$SQL_USER;Password=$SQL_PASSWORD;Connection Timeout=5;"
    $connection = New-Object System.Data.SqlClient.SqlConnection($connectionString)
    $connection.Open()

    $command = $connection.CreateCommand()
    $command.CommandText = "SELECT SUSER_NAME() AS CurrentUser, DB_NAME() AS CurrentDatabase, @@VERSION AS Version"
    $reader = $command.ExecuteReader()

    if ($reader.Read()) {
        Write-Host "✓ Conexão estabelecida com sucesso!" -ForegroundColor Green
        Write-Host "  - Usuário: $($reader['CurrentUser'])" -ForegroundColor Green
        Write-Host "  - Database: $($reader['CurrentDatabase'])" -ForegroundColor Green
        Write-Host ""
    }

    $reader.Close()
    $connection.Close()

    # Configurar variáveis de ambiente
    Write-Host "Configurando variáveis de ambiente..." -ForegroundColor Yellow

    $env:INTELLIGENCE_USE_WINDOWS_AUTH = "false"
    $env:INTELLIGENCE_SQL_USER = $SQL_USER
    $env:INTELLIGENCE_SQL_PASSWORD = $SQL_PASSWORD
    $env:INTELLIGENCE_SERVER = $SQL_SERVER
    $env:INTELLIGENCE_DATABASE = $SQL_DATABASE

    Write-Host "✓ Variáveis de ambiente configuradas:" -ForegroundColor Green
    Write-Host "  - INTELLIGENCE_USE_WINDOWS_AUTH = false" -ForegroundColor Gray
    Write-Host "  - INTELLIGENCE_SQL_USER = $SQL_USER" -ForegroundColor Gray
    Write-Host "  - INTELLIGENCE_SQL_PASSWORD = ********" -ForegroundColor Gray
    Write-Host "  - INTELLIGENCE_SERVER = $SQL_SERVER" -ForegroundColor Gray
    Write-Host "  - INTELLIGENCE_DATABASE = $SQL_DATABASE" -ForegroundColor Gray
    Write-Host ""

    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host "CONFIGURAÇÃO CONCLUÍDA!" -ForegroundColor Green
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Agora você pode iniciar a API do WatcherDB:" -ForegroundColor Yellow
    Write-Host "  cd api" -ForegroundColor Gray
    Write-Host "  uvicorn main:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Ou executar a coleta de dados:" -ForegroundColor Yellow
    Write-Host "  cd .." -ForegroundColor Gray
    Write-Host "  cd 'WATCHERDB INTELLIGENCE V1'" -ForegroundColor Gray
    Write-Host "  .\collect_data.bat" -ForegroundColor Gray
    Write-Host ""
    Write-Host "IMPORTANTE: As variáveis de ambiente são válidas apenas nesta sessão do PowerShell." -ForegroundColor Red
    Write-Host "Para tornar permanente, adicione ao seu perfil do PowerShell ou use um arquivo .env" -ForegroundColor Red
    Write-Host ""

} catch {
    Write-Host "✗ ERRO ao conectar ao SQL Server!" -ForegroundColor Red
    Write-Host "  Mensagem: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Verifique:" -ForegroundColor Yellow
    Write-Host "  1. O usuário SQL '$SQL_USER' existe e está habilitado" -ForegroundColor Gray
    Write-Host "  2. A senha está correta" -ForegroundColor Gray
    Write-Host "  3. O servidor '$SQL_SERVER' está acessível" -ForegroundColor Gray
    Write-Host "  4. O usuário tem permissões no database '$SQL_DATABASE'" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

# Limpar senha da memória
$SQL_PASSWORD = $null
[System.GC]::Collect()
