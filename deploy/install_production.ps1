# ============================================================
# [DEPRECATED] WatcherDB V3.2 Instalacao em Producao
# ============================================================
# Este script foi deprecado em audit 2026-04-22 / S2-8.
#
# O conteudo original apontava para WatcherDB V3.2 + porta 8449 +
# servico WatcherDBWebServiceV32, valores desalinhados com o produto
# actual V3.3 (porta 8433, servico WatcherDBWebServiceV33). O MSI
# signed e o artefacto canonico a partir de Sprint 1 Sem 3-4.
#
# CAMINHO CANONICO DE INSTALACAO:
#   dist\msi\WatcherDB_V3.3_Standard.msi
#   Guia step-by-step: docs\external\standard\INSTALL_GUIDE.md
# ============================================================

Write-Host ""
Write-Host "[DEPRECATED] install_production.ps1 foi deprecado em audit 2026-04-22 (S2-8)." -ForegroundColor Red
Write-Host ""
Write-Host "Instalacao canonica actual:" -ForegroundColor Yellow
Write-Host "  msiexec /i dist\msi\WatcherDB_V3.3_Standard.msi /qn /l*v install.log" -ForegroundColor Yellow
Write-Host ""
Write-Host "Guia completo:" -ForegroundColor Yellow
Write-Host "  docs\external\standard\INSTALL_GUIDE.md" -ForegroundColor Yellow
Write-Host ""
exit 1
