# Script para limpar cache e reiniciar servidor

Write-Host "🧹 Limpando cache Python..." -ForegroundColor Yellow

# Limpar __pycache__
Get-ChildItem -Path . -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "  ✅ __pycache__ removido" -ForegroundColor Green

# Limpar .pyc
Get-ChildItem -Path . -Recurse -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "  ✅ .pyc removidos" -ForegroundColor Green

# Limpar .pyo
Get-ChildItem -Path . -Recurse -Filter "*.pyo" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "  ✅ .pyo removidos" -ForegroundColor Green

Write-Host ""
Write-Host "🔄 Reiniciando servidor..." -ForegroundColor Yellow
Write-Host ""
Write-Host "⚠️  Se o servidor estiver rodando, pressione Ctrl+C para parar" -ForegroundColor Red
Write-Host ""
Write-Host "Depois execute:" -ForegroundColor Cyan
Write-Host "  python -m uvicorn watcherdb_main:app --reload --port 8000" -ForegroundColor White
Write-Host ""

