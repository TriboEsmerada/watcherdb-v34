# Script PowerShell para gerar hashes criptográficos dos arquivos principais do WatcherDB
# Para registro no IGAC (Inspeção-Geral das Atividades Culturais)

$ErrorActionPreference = "Continue"
$outputFile = "HASHES_CRIPTOGRAFICOS_WATCHERDB.txt"

# Lista de arquivos principais
$arquivos = @(
    "watcherdb_main.py",
    "templates\watcherdb_portal.html",
    "modules\monitoring\queries.py",
    "modules\analytics\predictive_analysis.py",
    "modules\monitoring\space_analysis.py",
    "modules\monitoring\backup_analysis.py",
    "modules\monitoring\cpu_analysis.py",
    "modules\monitoring\memory_analysis.py",
    "api\routers\sql_queries.py",
    "api\routers\diagnostics_overview.py",
    "config\sql_servers.json"
)

# Cabeçalho
$output = @"
================================================================================
HASHES CRIPTOGRÁFICOS - WATCHERDB v1.4.8.2
================================================================================
Software: WatcherDB - Plataforma de Monitoramento de Bases de Dados
Versão: 1.4.8.2
Data de Geração: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')
Titular: TAP - Transportes Aéreos Portugueses
Propósito: Registro no IGAC (Inspeção-Geral das Atividades Culturais)
================================================================================

"@

Write-Host $output
$output | Out-File -FilePath $outputFile -Encoding UTF8

# Gerar hashes para cada arquivo
foreach ($arquivo in $arquivos) {
    $caminhoCompleto = Join-Path -Path ".." -ChildPath $arquivo

    if (Test-Path $caminhoCompleto) {
        Write-Host "Processando: $arquivo" -ForegroundColor Green

        try {
            # Gerar MD5
            $md5 = (Get-FileHash -Path $caminhoCompleto -Algorithm MD5).Hash

            # Gerar SHA256
            $sha256 = (Get-FileHash -Path $caminhoCompleto -Algorithm SHA256).Hash

            # Obter tamanho do arquivo
            $tamanho = (Get-Item $caminhoCompleto).Length
            $tamanhoKB = [math]::Round($tamanho / 1024, 2)

            # Obter data de modificação
            $dataModificacao = (Get-Item $caminhoCompleto).LastWriteTime.ToString('dd/MM/yyyy HH:mm:ss')

            # Formatar saída
            $info = @"

--------------------------------------------------------------------------------
Arquivo: $arquivo
--------------------------------------------------------------------------------
Tamanho: $tamanhoKB KB ($tamanho bytes)
Última Modificação: $dataModificacao

MD5:    $md5
SHA256: $sha256

"@

            Write-Host $info
            $info | Out-File -FilePath $outputFile -Encoding UTF8 -Append

        } catch {
            $erro = "ERRO ao processar $arquivo : $_"
            Write-Host $erro -ForegroundColor Red
            $erro | Out-File -FilePath $outputFile -Encoding UTF8 -Append
        }
    } else {
        $aviso = "AVISO: Arquivo não encontrado: $arquivo"
        Write-Host $aviso -ForegroundColor Yellow
        $aviso | Out-File -FilePath $outputFile -Encoding UTF8 -Append
    }
}

# Rodapé
$rodape = @"

================================================================================
RESUMO
================================================================================
Total de Arquivos Processados: $($arquivos.Count)
Data de Geração: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')
Algoritmos Utilizados: MD5, SHA256
================================================================================

NOTA: Estes hashes criptográficos garantem a integridade e autenticidade do
código-fonte do WatcherDB v1.4.8.2 no momento do registro no IGAC.

Qualquer modificação nos arquivos resultará em hashes diferentes, comprovando
a autoria e data de criação do software.

================================================================================
"@

Write-Host $rodape -ForegroundColor Cyan
$rodape | Out-File -FilePath $outputFile -Encoding UTF8 -Append

Write-Host "`nHashes salvos em: $outputFile" -ForegroundColor Green
