# PowerShell script para forçar atualização do dashboard
Write-Host "🚀 FORÇANDO ATUALIZAÇÃO COMPLETA DO DASHBOARD" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green

# 1. Parar TODOS os processos Python
Write-Host "📋 1. Parando todos os processos Python..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

# 2. Verificar arquivos HTML existentes
Write-Host "📋 2. Verificando arquivos HTML existentes..." -ForegroundColor Yellow
Get-ChildItem -Recurse -Name "watcherdb_portal.html" -ErrorAction SilentlyContinue

# 3. Verificar se o arquivo correto está em templates/
Write-Host "📋 3. Verificando arquivo em templates/..." -ForegroundColor Yellow
if (Test-Path "templates\watcherdb_portal.html") {
    Write-Host "✅ Arquivo encontrado em templates/" -ForegroundColor Green
} else {
    Write-Host "❌ Arquivo NÃO encontrado em templates/" -ForegroundColor Red
    Write-Host "   Verifique se você está no diretório correto" -ForegroundColor Red
    exit 1
}

# 4. Verificar se a correção está no arquivo
Write-Host "📋 4. Verificando correções no arquivo..." -ForegroundColor Yellow
$content = Get-Content "templates\watcherdb_portal.html" -Raw
if ($content -match "Filegroup") {
    Write-Host "✅ Correção 'Filegroup' encontrada!" -ForegroundColor Green
    $content | Select-String "Filegroup" | Select-String "<th"
} else {
    Write-Host "❌ Correção 'Filegroup' NÃO encontrada!" -ForegroundColor Red
    Write-Host "   O arquivo ainda tem 'Logical Names'" -ForegroundColor Red
    exit 1
}

# 5. Limpar cache do Python
Write-Host "📋 5. Limpando cache do Python..." -ForegroundColor Yellow
Get-ChildItem -Recurse -Directory -Name "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Name "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "✅ Cache limpo!" -ForegroundColor Green

# 6. Verificar se não há processos Python rodando
Write-Host "📋 6. Verificando processos Python..." -ForegroundColor Yellow
$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue
if ($pythonProcesses) {
    Write-Host "⚠️  Ainda há processos Python rodando:" -ForegroundColor Yellow
    $pythonProcesses | Format-Table
    Write-Host "   Matando novamente..." -ForegroundColor Yellow
    $pythonProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
} else {
    Write-Host "✅ Nenhum processo Python rodando" -ForegroundColor Green
}

Write-Host ""
Write-Host "🎯 PRÓXIMOS PASSOS:" -ForegroundColor Cyan
Write-Host "===================" -ForegroundColor Cyan
Write-Host "1. Reinicie o servidor:" -ForegroundColor White
Write-Host "   python -m uvicorn watcherdb_main:app --reload --port 8000" -ForegroundColor Gray
Write-Host ""
Write-Host "2. No navegador:" -ForegroundColor White
Write-Host "   - Pressione F12" -ForegroundColor Gray
Write-Host "   - Vá na aba 'Network'" -ForegroundColor Gray
Write-Host "   - Marque 'Disable cache'" -ForegroundColor Gray
Write-Host "   - Pressione F5" -ForegroundColor Gray
Write-Host ""
Write-Host "3. OU teste em aba anônima:" -ForegroundColor White
Write-Host "   - Ctrl+Shift+N (Chrome/Edge)" -ForegroundColor Gray
Write-Host "   - Ctrl+Shift+P (Firefox)" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Verificar se funcionou:" -ForegroundColor White
Write-Host "   - Acesse: http://localhost:8000/watcherdb" -ForegroundColor Gray
Write-Host "   - Selecione um servidor" -ForegroundColor Gray
Write-Host "   - Clique em 'Space Analysis'" -ForegroundColor Gray
Write-Host "   - Clique no card 'Análise Preditiva'" -ForegroundColor Gray
Write-Host "   - Verifique se mostra 'Filegroup' em vez de 'Logical Names'" -ForegroundColor Gray
Write-Host ""
Write-Host "SCRIPT CONCLUIDO!" -ForegroundColor Green
