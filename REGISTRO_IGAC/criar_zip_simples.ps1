$data = Get-Date -Format 'yyyyMMdd'
$nomeZip = "WatcherDB_v1.4.8.2_IGAC_$data.zip"

Write-Host "Criando $nomeZip..." -ForegroundColor Cyan

Compress-Archive -Path '..\watcherdb_main.py','..\templates','..\modules','..\api','..\config','..\documentacao','RESUMO_DESCRITIVO_WATCHERDB.md','HASHES_CRIPTOGRAFICOS_WATCHERDB.txt','..\requirements.txt' -DestinationPath $nomeZip -CompressionLevel Optimal -Force

if (Test-Path $nomeZip) {
    $arquivo = Get-Item $nomeZip
    $tamanhoMB = [math]::Round($arquivo.Length / 1MB, 2)

    Write-Host ""
    Write-Host "ZIP criado com sucesso!" -ForegroundColor Green
    Write-Host "Nome: $($arquivo.Name)" -ForegroundColor White
    Write-Host "Tamanho: $tamanhoMB MB" -ForegroundColor White
    Write-Host "Caminho: $($arquivo.FullName)" -ForegroundColor White

    # Gerar hash
    $hash = (Get-FileHash -Path $nomeZip -Algorithm SHA256).Hash
    Write-Host "SHA256: $hash" -ForegroundColor Yellow
} else {
    Write-Host "ERRO: ZIP não foi criado" -ForegroundColor Red
}
