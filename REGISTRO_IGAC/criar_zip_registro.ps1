# Script PowerShell para criar arquivo ZIP do WatcherDB para registro no IGAC

$ErrorActionPreference = "Stop"

# Configurações
$nomeZip = "WatcherDB_v1.4.8.2_IGAC_Registro_$(Get-Date -Format 'yyyyMMdd').zip"
$caminhoBase = ".."
$caminhoZip = Join-Path -Path "." -ChildPath $nomeZip

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Criando ZIP para Registro IGAC" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Arquivos e pastas a incluir
$itensParaIncluir = @(
    # Aplicação principal
    "watcherdb_main.py",

    # Templates
    "templates\watcherdb_portal.html",

    # Módulos
    "modules\monitoring\*.py",
    "modules\analytics\*.py",

    # API
    "api\routers\*.py",
    "api\__init__.py",

    # Configurações (remover senhas)
    "config\sql_servers.json",
    "config\alwayson_inventory.json",

    # Documentação
    "documentacao\*.md",
    "REGISTRO_IGAC\RESUMO_DESCRITIVO_WATCHERDB.md",
    "REGISTRO_IGAC\HASHES_CRIPTOGRAFICOS_WATCHERDB.txt",

    # Requirements
    "requirements.txt",

    # README (se existir)
    "README.md"
)

# Criar pasta temporária
$pastaTemp = Join-Path -Path $env:TEMP -ChildPath "WatcherDB_IGAC_$(Get-Date -Format 'yyyyMMddHHmmss')"
New-Item -ItemType Directory -Path $pastaTemp -Force | Out-Null

Write-Host "Pasta temporária criada: $pastaTemp" -ForegroundColor Green

# Copiar arquivos
$totalArquivos = 0
foreach ($item in $itensParaIncluir) {
    $caminhoCompleto = Join-Path -Path $caminhoBase -ChildPath $item

    # Verificar se é wildcard
    if ($item -like "*\*.*") {
        $arquivos = Get-ChildItem -Path $caminhoCompleto -ErrorAction SilentlyContinue
        foreach ($arquivo in $arquivos) {
            # Criar pasta de destino
            $pastaRelativa = Split-Path -Parent $item
            $pastaDestino = Join-Path -Path $pastaTemp -ChildPath $pastaRelativa

            if (!(Test-Path $pastaDestino)) {
                New-Item -ItemType Directory -Path $pastaDestino -Force | Out-Null
            }

            Copy-Item -Path $arquivo.FullName -Destination $pastaDestino -Force
            Write-Host "  [OK] $($arquivo.Name)" -ForegroundColor Gray
            $totalArquivos++
        }
    } else {
        if (Test-Path $caminhoCompleto) {
            # Criar pasta de destino
            $pastaRelativa = Split-Path -Parent $item
            if ($pastaRelativa) {
                $pastaDestino = Join-Path -Path $pastaTemp -ChildPath $pastaRelativa

                if (!(Test-Path $pastaDestino)) {
                    New-Item -ItemType Directory -Path $pastaDestino -Force | Out-Null
                }
            } else {
                $pastaDestino = $pastaTemp
            }

            Copy-Item -Path $caminhoCompleto -Destination $pastaDestino -Force
            Write-Host "  [OK] $item" -ForegroundColor Gray
            $totalArquivos++
        } else {
            Write-Host "  [SKIP] $item (não encontrado)" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "Total de arquivos copiados: $totalArquivos" -ForegroundColor Green

# Criar arquivo README no ZIP
$readmeContent = @"
================================================================================
WATCHERDB v1.4.8.2 - REGISTRO IGAC
================================================================================

INFORMAÇÕES DO SOFTWARE:
- Nome: WatcherDB
- Versão: 1.4.8.2
- Data: 18/11/2025
- Titular: TAP - Transportes Aéreos Portugueses
- Propósito: Plataforma de Monitoramento de Bases de Dados SQL Server e Oracle

DOCUMENTOS INCLUÍDOS:
1. REGISTRO_IGAC\RESUMO_DESCRITIVO_WATCHERDB.md
   Descrição completa do software (funcionalidades, arquitetura, casos de uso)

2. REGISTRO_IGAC\HASHES_CRIPTOGRAFICOS_WATCHERDB.txt
   Hashes MD5 e SHA256 dos arquivos principais

3. Código-fonte completo do projeto

ESTRUTURA DO PROJETO:
- watcherdb_main.py: Aplicação principal (FastAPI)
- templates/: Interface web (HTML/CSS/JS)
- modules/: Módulos Python (monitoramento, analytics)
- api/: Endpoints REST API
- config/: Arquivos de configuração
- documentacao/: Documentação técnica

TECNOLOGIAS:
- Python 3.13
- FastAPI
- SQL Server (pyodbc)
- Oracle (cx_Oracle)
- Machine Learning (statsmodels, scikit-learn)

CONTATO:
TAP - Transportes Aéreos Portugueses
Departamento de Tecnologias de Informação

================================================================================
Gerado em: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')
================================================================================
"@

$readmeContent | Out-File -FilePath (Join-Path -Path $pastaTemp -ChildPath "LEIA-ME_REGISTRO_IGAC.txt") -Encoding UTF8

# Criar ZIP
Write-Host ""
Write-Host "Criando arquivo ZIP..." -ForegroundColor Cyan

if (Test-Path $caminhoZip) {
    Remove-Item $caminhoZip -Force
    Write-Host "Arquivo ZIP anterior removido" -ForegroundColor Yellow
}

Compress-Archive -Path "$pastaTemp\*" -DestinationPath $caminhoZip -CompressionLevel Optimal

# Limpar pasta temporária
Remove-Item -Path $pastaTemp -Recurse -Force

# Exibir informações do ZIP
$tamanhoZip = (Get-Item $caminhoZip).Length
$tamanhoZipMB = [math]::Round($tamanhoZip / 1MB, 2)

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " ZIP CRIADO COM SUCESSO!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Arquivo: $nomeZip" -ForegroundColor White
Write-Host "Caminho: $caminhoZip" -ForegroundColor White
Write-Host "Tamanho: $tamanhoZipMB MB ($tamanhoZip bytes)" -ForegroundColor White
Write-Host "Arquivos incluídos: $totalArquivos" -ForegroundColor White
Write-Host ""
Write-Host "Este arquivo está pronto para envio ao IGAC" -ForegroundColor Cyan
Write-Host ""

# Gerar hash do ZIP
Write-Host "Gerando hash do arquivo ZIP..." -ForegroundColor Cyan
$hashZip = (Get-FileHash -Path $caminhoZip -Algorithm SHA256).Hash
Write-Host "SHA256 do ZIP: $hashZip" -ForegroundColor Yellow
Write-Host ""

# Salvar informações em arquivo
$infoZip = @"
INFORMAÇÕES DO ARQUIVO ZIP
==========================
Nome do Arquivo: $nomeZip
Data de Criação: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')
Tamanho: $tamanhoZipMB MB ($tamanhoZip bytes)
Arquivos Incluídos: $totalArquivos

HASH SHA256 DO ZIP:
$hashZip

CONTEÚDO:
- Código-fonte completo do WatcherDB v1.4.8.2
- Documentação técnica
- Hashes criptográficos dos arquivos
- Resumo descritivo para IGAC

NOTA: Este arquivo foi criado exclusivamente para registro de propriedade
intelectual no IGAC (Inspeção-Geral das Atividades Culturais) de Portugal.
"@

$infoZip | Out-File -FilePath "INFO_ZIP_IGAC.txt" -Encoding UTF8

Write-Host "Informações salvas em: INFO_ZIP_IGAC.txt" -ForegroundColor Green
Write-Host ""
