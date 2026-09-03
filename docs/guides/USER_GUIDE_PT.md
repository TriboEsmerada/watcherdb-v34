# WatcherDB V3.3 Standard Edition - Guia do Utilizador

**Plataforma de Monitorizacao SQL Server Banking-Grade, On-Premise**

---

| Campo | Valor |
|-------|-------|
| Versao | 3.3 (Standard Edition) |
| Data | 22 de Abril de 2026 |
| Edition | Standard (core monitoring). Ver [FEATURE_MATRIX.md] para tier Pro (AI stack, anomaly detection, autonomous agent). |
| Audiencia | DBAs, Administradores de Sistemas, Equipas de Operacoes, IT Directors / CISO (Anexo Security) |
| Idiomas do Portal | Portugues (PT), Ingles (EN), Espanhol (ES) -- 3 linguas distintas. Ground truth runtime: `static/js/watcherdb_i18n_v2.js`. |
| Porta por defeito | **8433** (definida em `services/web_service/config.yaml` e no MSI installer) |
| Servico Windows | **WatcherDBWebServiceV33** |
| Deploy artefacts | MSI signed (Authenticode EV KeyLocker) + SBOM CycloneDX + update-package signed (Ed25519) |

---

## Porque WatcherDB V3.3 Standard?

Sao 03h14. O SQL Agent alertou para um blocking chain com 47 sessoes em espera. Sem ferramenta consolidada, o DBA de turno passa 20 minutos a correlacionar `sys.dm_exec_requests`, `sys.dm_os_waiting_tasks` e errorlog manualmente. Com o WatcherDB, o Performance Intelligence Module detecta o head blocker, expoe o lock type e gera o ticket estruturado em menos de 2 minutos.

WatcherDB V3.3 Standard Edition e uma ferramenta de monitorizacao SQL Server desenhada para o DBA operacional em ambiente mid-market bancario / seguros / saude on-premise. Diferenciadores:

1. **Performance Intelligence de 8 investigators com ticket generator** — deadlocks, blocking chains, CPU/memory/slow/heavy queries, missing indexes, problematic sessions. Output accionavel + historico. Nenhum concorrente neste tier oferece diagnosis guiada estruturada.
2. **Deploy banking-grade fora da caixa** — MSI signed com certificado EV, SBOM CycloneDX, update-package signed com Ed25519, PyArmor Pro obfuscation, AD hybrid + bcrypt break-glass, least-privilege SQL account. Passa security review de CISO sem iteracao extra.
3. **Zero external dependency, 100% on-premise** — sem phone-home, sem cloud telemetry, sem subscription SaaS. Relevante para compliance DORA, SOX, dados de performance nao saem do perimetro.

**Upgrade path documentado:** quando a equipa estiver pronta para AI local soberana (Ollama, RAG, anomaly detection, autonomous agent, executive reports com Health Score Engine), WatcherDB Pro (V5/V5.5) e um upgrade de installer, nao uma migracao. Ver [FEATURE_MATRIX.md](../../../watcherdb-council/docs/FEATURE_MATRIX.md).

---

## Indice

- [1. Introducao](#1-introducao)
  - [1.1. O que e o WatcherDB](#11-o-que-e-o-watcherdb)
  - [1.2. Arquitectura Geral](#12-arquitectura-geral)
  - [1.3. Componentes do Sistema](#13-componentes-do-sistema)
  - [1.4. Requisitos de Sistema](#14-requisitos-de-sistema)
- [2. Instalacao e Configuracao Inicial](#2-instalacao-e-configuracao-inicial)
  - [2.1. Pre-requisitos](#21-pre-requisitos)
  - [2.2. Instalacao do WatcherDB V3.3](#22-instalacao-do-watcherdb-v32)
  - [2.3. Configuracao do Ficheiro .env](#23-configuracao-do-ficheiro-env)
  - [2.4. Instalacao como Windows Service](#24-instalacao-como-windows-service)
  - [2.5. Verificacao da Instalacao](#25-verificacao-da-instalacao)
- [3. Primeiro Acesso](#3-primeiro-acesso)
  - [3.1. Login Inicial](#31-login-inicial)
  - [3.2. Alterar Senha do Administrador](#32-alterar-senha-do-administrador)
  - [3.3. Navegacao Basica](#33-navegacao-basica)
  - [3.4. Seleccao de Idioma](#34-seleccao-de-idioma)
  - [3.5. Modo Escuro e Modo Claro](#35-modo-escuro-e-modo-claro)
- [4. KPIs](#4-dashboard-de-kpis)
  - [4.1. Visao Geral do Dashboard](#41-visao-geral-do-dashboard)
  - [4.2. Categorias de KPIs](#42-categorias-de-kpis)
  - [4.3. Cartoes de KPI](#43-cartoes-de-kpi)
  - [4.4. Estados dos KPIs](#44-estados-dos-kpis)
  - [4.5. Tempo Medio de Colecta](#45-tempo-medio-de-colecta)
  - [4.6. Filtros e Pesquisa](#46-filtros-e-pesquisa)
- [5. Tabs de Servidor](#5-tabs-de-servidor)
  - [5.1. Overview](#51-overview)
  - [5.2. Always On](#52-always-on)
  - [5.3. Backup](#53-backup)
  - [5.4. Space](#54-space)
  - [5.5. Disk](#55-disk)
  - [5.6. Encrypted](#56-encrypted)
  - [5.7. CPU](#57-cpu)
  - [5.8. Memory](#58-memory)
  - [5.9. Services](#59-services)
  - [5.10. Log](#510-log)
  - [5.11. SQL Diagnostics](#511-sql-diagnostics)
  - [5.12. Security](#512-security)
  - [5.13. Users](#513-users)
  - [5.14. Jobs](#514-jobs)
- [6. Painel de Controlo](#6-painel-de-controlo)
  - [6.1. Aceder ao Painel de Controlo](#61-aceder-ao-painel-de-controlo)
  - [6.2. Gestao de Utilizadores](#62-gestao-de-utilizadores)
  - [6.3. Auth Log](#63-auth-log)
  - [6.4. Sessoes Activas](#64-sessoes-activas)
  - [6.5. Resource Monitor](#65-resource-monitor)
  - [6.6. Configuracoes](#66-configuracoes)
- [7. Active Directory](#7-active-directory)
  - [7.1. Configuracao Multi-Dominio](#71-configuracao-multi-dominio)
  - [7.2. DNS SRV Discovery](#72-dns-srv-discovery)
  - [7.3. Pesquisa LDAP](#73-pesquisa-ldap)
  - [7.4. Auto-Preenchimento de Dados](#74-auto-preenchimento-de-dados)
  - [7.5. Bind e Autenticacao Kerberos](#75-bind-e-autenticacao-kerberos)
- [8. Funcionalidades Adicionais](#8-funcionalidades-adicionais)
  - [8.1. Pesquisa de Servidores](#81-pesquisa-de-servidores)
  - [8.2. Exportacao PDF](#82-exportacao-pdf)
  - [8.3. Network Diagnostics](#83-network-diagnostics)
  - [8.4. Analise Preditiva](#84-analise-preditiva)
  - [8.5. DBA Copilot](#85-dba-copilot)
- [9. Seguranca](#9-seguranca)
  - [9.1. Autenticacao JWT](#91-autenticacao-jwt)
  - [9.2. Politica de Senhas](#92-politica-de-senhas)
  - [9.3. Bloqueio de Conta](#93-bloqueio-de-conta)
  - [9.4. Roles e Permissoes](#94-roles-e-permissoes)
- [10. Administracao do Servico](#10-administracao-do-servico)
  - [10.1. Gestao do Windows Service](#101-gestao-do-windows-service)
  - [10.2. Logs do Sistema](#102-logs-do-sistema)
  - [10.3. Conta de Servico](#103-conta-de-servico)
  - [10.4. Backup da Configuracao](#104-backup-da-configuracao)
- [11. Resolucao de Problemas](#11-resolucao-de-problemas)
  - [11.1. Problemas de Arranque](#111-problemas-de-arranque)
  - [11.2. Problemas de Autenticacao](#112-problemas-de-autenticacao)
  - [11.3. Problemas de Colecta de Dados](#113-problemas-de-colecta-de-dados)
  - [11.4. Problemas de Performance](#114-problemas-de-performance)
  - [11.5. Problemas de Conectividade](#115-problemas-de-conectividade)
  - [11.6. Problemas com Active Directory](#116-problemas-com-active-directory)
  - [11.7. Problemas com o Portal Web](#117-problemas-com-o-portal-web)
- [12. FAQ - Perguntas Frequentes](#12-faq---perguntas-frequentes)
- [13. Glossario](#13-glossario)
- [14. Referencia Rapida](#14-referencia-rapida)

---

---

# 1. Introducao

## 1.1. O que e o WatcherDB

O WatcherDB V3.3 e uma plataforma de monitorizacao centralizada para instancias SQL Server. Permite que equipas de DBA e administradores de sistemas monitorizem mais de 100 instancias SQL Server a partir de um unico portal web, com visibilidade em tempo real sobre disponibilidade, performance, espaco em disco, backups, alta disponibilidade e muito mais.

**Principais capacidades:**

- Monitorizacao centralizada de 100+ instancias SQL Server
- KPIs com 6 categorias de metricas
- 14 tabs de informacao detalhada por servidor
- Painel de controlo com gestao de utilizadores e configuracoes
- Autenticacao hibrida (Local + Active Directory)
- Suporte multi-idioma (Portugues, Ingles, Espanhol)
- Exportacao de relatorios em PDF
- Analise preditiva de crescimento de dados
- DBA Copilot para consultas rapidas
- Windows Service para operacao continua

**Caso de uso tipico:**

Uma equipa de DBA numa companhia aerea necessita de monitorizar dezenas de instancias SQL Server espalhadas por diferentes datacenters. Em vez de se ligar individualmente a cada servidor, a equipa acede ao WatcherDB e obtem uma visao consolidada do estado de toda a infraestrutura SQL Server num unico ecra.

---

## 1.2. Arquitectura Geral

O WatcherDB V3.3 segue uma arquitectura de dois componentes principais:

```
+-------------------+        HTTPS (8433)        +---------------------------+
|                   | <-------------------------> |                           |
|   Browser (UI)    |                             |   WatcherDB V3.3          |
|   - Dashboard     |                             |   (FastAPI + Uvicorn)     |
|   - Tabs servidor |                             |   - API REST              |
|   - Control Panel |                             |   - Frontend HTMX         |
|                   |                             |   - Auth JWT + AD         |
+-------------------+                             +---------------------------+
                                                            |
                                                            | ODBC
                                                            | Windows Auth
                                                            v
                                                  +---------------------------+
                                                  |   SQL Server Instances    |
                                                  |   (100+ servidores)       |
                                                  +---------------------------+
                                                            ^
                                                            | Colecta periodica
                                                            |
                                                  +---------------------------+
                                                  |   Collector Service       |
                                                  |   (Intelligence V1)      |
                                                  |   Porta 8001             |
                                                  +---------------------------+
                                                            |
                                                            | Armazena KPIs
                                                            v
                                                  +---------------------------+
                                                  |   WatcherDB_Intelligence  |
                                                  |   (SQL Server DB)         |
                                                  +---------------------------+
```

**Fluxo de dados:**

1. O **Collector Service** (Intelligence V1, porta 8001) liga-se periodicamente a cada instancia SQL Server monitorizada
2. Colecta metricas de KPIs (disponibilidade, performance, espaco, etc.)
3. Armazena os dados colectados na base de dados **WatcherDB_Intelligence**
4. O **WatcherDB V3.3** (porta 8433) le os dados da Intelligence DB
5. Apresenta as metricas no portal web para os utilizadores

---

## 1.3. Componentes do Sistema

### WatcherDB V3.3 - Portal Web

| Aspecto | Detalhe |
|---------|---------|
| Framework | FastAPI (Python) |
| Servidor | Uvicorn |
| Frontend | HTMX + Jinja2 Templates |
| Porta | 8433 |
| Autenticacao | JWT + Active Directory (LDAP/Kerberos) |
| Execucao | Windows Service |

### Collector Service - Intelligence V1

| Aspecto | Detalhe |
|---------|---------|
| Funcao | Colecta periodica de KPIs |
| Porta | 8001 |
| Conectividade | ODBC com Windows Authentication |
| Armazenamento | WatcherDB_Intelligence (SQL Server) |
| Frequencia | Configuravel por tipo de KPI |

### WatcherDB_Intelligence - Base de Dados

| Aspecto | Detalhe |
|---------|---------|
| Motor | SQL Server 2016+ |
| Funcao | Armazenamento centralizado de metricas |
| Dados | KPIs historicos, configuracoes, utilizadores |
| Acesso | Windows Authentication |

---

## 1.4. Requisitos de Sistema

### Requisitos de Hardware

| Recurso | Minimo | Recomendado |
|---------|--------|-------------|
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| Disco | 50 GB livre | 100 GB livre |
| Rede | 100 Mbps | 1 Gbps |

### Requisitos de Software

| Software | Versao |
|----------|--------|
| Sistema Operativo | Windows Server 2016 ou superior |
| Python | 3.11 ou superior |
| ODBC Driver for SQL Server | 17 ou 18 |
| SQL Server (para Intelligence DB) | 2016 ou superior |
| Browser suportado | Chrome 90+, Firefox 90+, Edge 90+ |

### Requisitos de Rede

| Porta | Protocolo | Funcao |
|-------|-----------|--------|
| 8433 | HTTPS/HTTP | Portal Web WatcherDB V3.3 |
| 8001 | HTTP | Collector Service |
| 1433 | TCP | Conexao SQL Server (por defeito) |
| 389 | TCP/UDP | LDAP (Active Directory) |
| 636 | TCP | LDAPS (Active Directory seguro) |
| 88 | TCP/UDP | Kerberos (Active Directory) |

### Permissoes Necessarias

- A conta de servico do WatcherDB necessita de:
  - Permissao `VIEW SERVER STATE` em cada instancia SQL Server monitorizada
  - Acesso de leitura a DMVs de sistema
  - Conta de dominio (para Windows Authentication)
  - Permissao `Log on as a service` no Windows

---

---

# 2. Instalacao e Configuracao Inicial

## 2.1. Pre-requisitos

Antes de iniciar a instalacao, verifique os seguintes pre-requisitos:

**1. Python 3.11+ instalado:**

```powershell
python --version
# Output esperado: Python 3.11.x ou superior
```

**2. ODBC Driver instalado:**

```powershell
# Verificar drivers ODBC instalados
Get-OdbcDriver | Where-Object {$_.Name -like "*SQL Server*"}
```

O output deve incluir `ODBC Driver 17 for SQL Server` ou `ODBC Driver 18 for SQL Server`.

**3. SQL Server 2016+ disponivel para a Intelligence DB:**

A base de dados WatcherDB_Intelligence deve estar criada e acessivel pela conta de servico.

**4. Conta de servico configurada:**

- Conta de dominio com Windows Authentication
- Permissao `VIEW SERVER STATE` nos SQL Servers monitorizados
- Permissao `Log on as a service` no Windows

---

## 2.2. Instalacao do WatcherDB V3.3

### Passo 1: Copiar os ficheiros

Copie a pasta do WatcherDB para o directorio de instalacao:

```powershell
# Criar directorio de instalacao
New-Item -ItemType Directory -Path "C:\WatcherDB" -Force

# Copiar ficheiros
Copy-Item -Path ".\WATCHERDB_V3.2\*" -Destination "C:\WatcherDB\" -Recurse
```

### Passo 2: Instalar dependencias Python

```powershell
cd C:\WatcherDB

# Criar virtual environment (recomendado)
python -m venv venv

# Activar virtual environment
.\venv\Scripts\Activate.ps1

# Instalar dependencias principais
pip install -r requirements.txt
```

**Dependencias opcionais:**

```powershell
# Para funcionalidades de alerting
pip install -r requirements-alerting.txt

# Para funcionalidades de analytics
pip install -r requirements-analytics.txt

# Para ambiente de desenvolvimento
pip install -r requirements-dev.txt
```

### Passo 3: Verificar instalacao

```powershell
# Testar se o Python encontra todos os modulos necessarios
python -c "import fastapi; import uvicorn; import pyodbc; print('OK')"
```

---

## 2.3. Configuracao do Ficheiro .env

O ficheiro `.env` na raiz do projecto contem as configuracoes essenciais. Crie ou edite o ficheiro com os seguintes parametros:

```ini
# ============================================
# WatcherDB V3.3 - Configuracao
# ============================================

# --- Servidor ---
HOST=0.0.0.0
PORT=8433
WORKERS=4

# --- Base de Dados Intelligence ---
DB_SERVER=servidor-sql.dominio.local
DB_NAME=WatcherDB_Intelligence
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_TRUSTED_CONNECTION=yes

# --- Seguranca ---
SECRET_KEY=gerar-uma-chave-secreta-aleatoria-aqui
JWT_EXPIRATION_MINUTES=480
JWT_ALGORITHM=HS256

# --- Active Directory (opcional) ---
AD_ENABLED=true
AD_DOMAIN=dominio.local
AD_BASE_DN=DC=dominio,DC=local

# --- Logging ---
LOG_LEVEL=INFO
LOG_FILE=logs/watcherdb.log

# --- Collector ---
COLLECTOR_URL=http://localhost:8001
```

**Importante:** Substitua os valores de exemplo pelos valores reais do seu ambiente. A `SECRET_KEY` deve ser uma string aleatoria longa e unica.

Para gerar uma chave secreta:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 2.4. Instalacao como Windows Service

O WatcherDB V3.3 foi concebido para correr como um Windows Service, garantindo que arranca automaticamente com o sistema operativo.

### Instalar o servico

```powershell
cd C:\WatcherDB

# Instalar o servico
python services/web_service/install.py install
```

### Configurar a conta de servico

1. Abrir `services.msc` (Win+R, digitar `services.msc`)
2. Encontrar o servico **WatcherDB V3.3** na lista
3. Clicar com o botao direito e seleccionar **Properties**
4. No separador **Log On**:
   - Seleccionar **This account**
   - Introduzir a conta de dominio (ex: `DOMINIO\svc_watcherdb`)
   - Introduzir a senha
   - Clicar **OK**
5. No separador **General**:
   - Definir **Startup type** como **Automatic**
6. No separador **Recovery**:
   - First failure: **Restart the Service**
   - Second failure: **Restart the Service**
   - Subsequent failures: **Restart the Service**
   - Reset fail count after: **1 day**
   - Restart service after: **60 seconds**

### Iniciar o servico

```powershell
# Via PowerShell
Start-Service "WatcherDB V3.3"

# Ou via services.msc
# Clicar com botao direito no servico → Start
```

### Verificar estado do servico

```powershell
Get-Service "WatcherDB*" | Format-Table Name, Status, StartType
```

### Comandos uteis de gestao do servico

```powershell
# Parar o servico
Stop-Service "WatcherDB V3.3"

# Reiniciar o servico
Restart-Service "WatcherDB V3.3"

# Desinstalar o servico
python services/web_service/install.py remove
```

---

## 2.5. Verificacao da Instalacao

Apos instalar e iniciar o servico, verifique que tudo esta a funcionar:

**1. Verificar que o servico esta a correr:**

```powershell
Get-Service "WatcherDB*"
# Status deve ser "Running"
```

**2. Verificar que a porta esta a escutar:**

```powershell
netstat -an | findstr "8433"
# Deve mostrar "LISTENING"
```

**3. Aceder ao portal via browser:**

Abrir o browser e navegar para:

```
https://servidor:8433/watcherdb/
```

Deve aparecer a pagina de login do WatcherDB.

**4. Verificar os logs:**

```powershell
# Ver ultimas linhas do log
Get-Content "C:\WatcherDB\services\web_service\logs\*.log" -Tail 20
```

O log deve mostrar mensagens de arranque sem erros.

---

---

# 3. Primeiro Acesso

## 3.1. Login Inicial

Apos a instalacao, aceda ao portal WatcherDB pela primeira vez:

1. Abrir o browser (Chrome, Firefox ou Edge)
2. Navegar para `https://servidor:8433/watcherdb/`
3. Na pagina de login, introduzir as credenciais por defeito:

| Campo | Valor |
|-------|-------|
| Username | `admin` |
| Password | `admin123` |

4. Clicar em **Login**

```
+------------------------------------------+
|              WatcherDB V3.3              |
|                                          |
|    +----------------------------------+  |
|    | Username                         |  |
|    | admin                            |  |
|    +----------------------------------+  |
|                                          |
|    +----------------------------------+  |
|    | Password                         |  |
|    | ********                         |  |
|    +----------------------------------+  |
|                                          |
|    [          Login          ]           |
|                                          |
+------------------------------------------+
```

> **AVISO DE SEGURANCA:** A senha por defeito `admin123` DEVE ser alterada imediatamente apos o primeiro login. Manter a senha por defeito constitui um risco de seguranca grave.

---

## 3.2. Alterar Senha do Administrador

Imediatamente apos o primeiro login, altere a senha do administrador:

1. Aceder ao **Painel de Controlo** (`/watcherdb/control`)
2. Ir a seccao **Gestao de Utilizadores**
3. Encontrar o utilizador `admin` na lista
4. Clicar em **Editar** (icone de lapis)
5. Clicar em **Reset Senha**
6. Introduzir uma nova senha que cumpra a politica de seguranca:

**Requisitos da senha:**

| Requisito | Descricao |
|-----------|-----------|
| Comprimento minimo | 8 caracteres |
| Letra maiuscula | Pelo menos 1 (A-Z) |
| Letra minuscula | Pelo menos 1 (a-z) |
| Numero | Pelo menos 1 (0-9) |
| Simbolo | Pelo menos 1 (!@#$%^&*...) |

**Exemplo de senha forte:** `W4tch3r@DB2026`

---

## 3.3. Navegacao Basica

Apos o login, o portal carrega o **KPIs** como pagina inicial.

### Estrutura da Interface

```
+------------------------------------------------------------------+
| [Logo] WatcherDB V3.3    [Pesquisa...]    [PT/EN/ES] [Mode] [User] |
+------------------------------------------------------------------+
|                                                                    |
|   KPIs                                                |
|   +----------+ +----------+ +----------+                          |
|   | Disponib.| | Perform. | | Espaco   |                          |
|   |  98.5%   | |  OK      | |  75%     |                          |
|   +----------+ +----------+ +----------+                          |
|   +----------+ +----------+ +----------+                          |
|   | Disco    | | Backup   | | Alta Disp|                          |
|   |  82%     | |  WARNING | |  OK      |                          |
|   +----------+ +----------+ +----------+                          |
|                                                                    |
|   Lista de Servidores                                              |
|   +-----------------------------------------------------+        |
|   | Servidor         | Status | Health | Ultima Colecta  |        |
|   | SQL-PROD-01      | OK     | 95%    | 2m ago         |        |
|   | SQL-PROD-02      | WARN   | 78%    | 1m ago         |        |
|   | SQL-DEV-01       | OK     | 92%    | 3m ago         |        |
|   +-----------------------------------------------------+        |
|                                                                    |
+------------------------------------------------------------------+
```

### Elementos da Barra Superior

| Elemento | Funcao |
|----------|--------|
| Logo WatcherDB | Clicar para voltar ao Dashboard |
| Barra de Pesquisa | Pesquisar servidores por nome |
| Selector de Idioma | Alternar entre PT/EN/ES |
| Botao de Modo | Alternar entre modo escuro e claro |
| Menu do Utilizador | Perfil, Painel de Controlo, Logout |

### Navegacao por Teclado

| Atalho | Funcao |
|--------|--------|
| `Ctrl+Shift+R` | Hard refresh (recarrega completamente a pagina, abre nos KPIs) |
| `Ctrl+F` | Focar na barra de pesquisa |
| `Esc` | Fechar modais e menus |

---

## 3.4. Seleccao de Idioma

O WatcherDB V3.3 suporta tres idiomas:

| Codigo | Idioma |
|--------|--------|
| PT | Portugues |
| EN | Ingles (English) |
| ES | Espanhol (Espanol) |

Para alterar o idioma:

1. Clicar no selector de idioma na barra superior (mostra o codigo do idioma actual, ex: **PT**)
2. Seleccionar o idioma desejado no dropdown
3. A interface actualiza-se imediatamente (sem recarregar a pagina)

A preferencia de idioma e guardada no browser (localStorage) e persiste entre sessoes.

> **Nota:** A alteracao de idioma e individual por utilizador e por browser. Se utilizar outro browser ou outro computador, o idioma volta ao valor por defeito (Portugues).

---

## 3.5. Modo Escuro e Modo Claro

O portal suporta dois temas visuais:

| Modo | Icone | Descricao |
|------|-------|-----------|
| Modo Claro | Icone de sol | Fundo branco, texto escuro |
| Modo Escuro | Icone de lua | Fundo escuro, texto claro |

Para alternar entre modos:

1. Clicar no icone de lua/sol na barra superior
2. O tema altera-se imediatamente

A preferencia de tema e guardada no browser e persiste entre sessoes.

---

---

# 4. KPIs

## 4.1. Visao Geral do Dashboard

O KPIs e a pagina principal do WatcherDB V3.3. Apresenta uma visao consolidada do estado de toda a infraestrutura SQL Server monitorizada, organizada em seis categorias de metricas.

O dashboard actualiza-se automaticamente e mostra:

- Estado agregado de todas as instancias por categoria de KPI
- Contadores de instancias em estado OK, WARNING e CRITICAL
- Tempo medio de colecta de dados
- Acesso rapido a cada servidor para analise detalhada

---

## 4.2. Categorias de KPIs

O dashboard organiza as metricas em seis categorias principais:

### Disponibilidade

| Aspecto | Detalhe |
|---------|---------|
| O que monitoriza | Estado online/offline de cada instancia SQL Server |
| Metricas | Percentagem de instancias online, tempo de actividade |
| OK | Todas as instancias respondem |
| WARNING | Algumas instancias com latencia elevada |
| CRITICAL | Uma ou mais instancias nao respondem |

### Performance

| Aspecto | Detalhe |
|---------|---------|
| O que monitoriza | Metricas de desempenho do SQL Server |
| Metricas | CPU, waits, batch requests/sec |
| OK | Metricas dentro dos limiares aceitaveis |
| WARNING | Metricas acima dos limiares normais |
| CRITICAL | Metricas em niveis criticos que afectam operacao |

### Espaco

| Aspecto | Detalhe |
|---------|---------|
| O que monitoriza | Espaco em disco utilizado por bases de dados |
| Metricas | Espaco total, usado, livre, percentagem de uso por filegroup |
| OK | Espaco livre acima do limiar |
| WARNING | Espaco livre abaixo do limiar de aviso |
| CRITICAL | Espaco livre critico, risco de base de dados ficar sem espaco |

### Disco

| Aspecto | Detalhe |
|---------|---------|
| O que monitoriza | Volumes e drives do sistema operativo |
| Metricas | Espaco total e livre por volume, espaco recuperavel |
| OK | Todos os volumes com espaco suficiente |
| WARNING | Um ou mais volumes com espaco limitado |
| CRITICAL | Volumes proximos do limite maximo |

### Backup

| Aspecto | Detalhe |
|---------|---------|
| O que monitorisa | Estado das backups de todas as bases de dados |
| Metricas | Ultima backup FULL, DIFF, LOG, gaps de backup |
| OK | Todas as bases de dados com backups recentes |
| WARNING | Algumas bases de dados com backups desactualizadas |
| CRITICAL | Bases de dados sem backup recente (gap critico) |

### Alta Disponibilidade

| Aspecto | Detalhe |
|---------|---------|
| O que monitoriza | Always On Availability Groups |
| Metricas | Estado de sincronizacao, replicas, failover events |
| OK | Todos os AGs sincronizados |
| WARNING | Atraso de sincronizacao detectado |
| CRITICAL | AG com problemas de sincronizacao ou replica em baixo |

---

## 4.3. Cartoes de KPI

Cada categoria de KPI e representada por um cartao (card) no dashboard que mostra:

```
+-----------------------------------+
|   [Icone]  DISPONIBILIDADE        |
|                                   |
|         98.5%                     |
|                                   |
|   Status: OK                      |
|   Tempo medio colecta: 2.3s      |
|   Servidores: 102/104             |
|                                   |
|   [OK: 98] [WARN: 4] [CRIT: 2]  |
+-----------------------------------+
```

**Elementos do cartao:**

| Elemento | Descricao |
|----------|-----------|
| Icone | Icone representativo da categoria |
| Titulo | Nome da categoria de KPI |
| Valor principal | Valor agregado da metrica (percentagem, contagem, etc.) |
| Status | Estado geral: OK (verde), WARNING (amarelo), CRITICAL (vermelho) |
| Tempo medio colecta | Tempo medio que demora a colectar esta metrica de todos os servidores |
| Contadores por estado | Numero de servidores em cada estado |

---

## 4.4. Estados dos KPIs

Os KPIs utilizam um sistema de tres estados com cores associadas:

| Estado | Cor | Significado | Accao necessaria |
|--------|-----|-------------|------------------|
| **OK** | Verde | Tudo normal, dentro dos parametros | Nenhuma accao necessaria |
| **WARNING** | Amarelo/Laranja | Atencao necessaria, fora dos parametros normais | Investigar e planear correcao |
| **CRITICAL** | Vermelho | Problema critico que requer accao imediata | Accao urgente necessaria |

A cor do cartao de KPI reflecte o pior estado entre todos os servidores nessa categoria. Por exemplo, se 100 servidores estao OK mas 1 esta CRITICAL, o cartao mostra vermelho.

---

## 4.5. Tempo Medio de Colecta

Cada cartao de KPI inclui o tempo medio de colecta, que indica quanto tempo o Collector Service demora, em media, a recolher essa metrica de todos os servidores.

| Tempo | Indicacao |
|-------|-----------|
| < 5 segundos | Normal |
| 5-15 segundos | Aceitavel, alguma latencia |
| 15-30 segundos | Lento, verificar rede ou carga dos servidores |
| > 30 segundos | Anormal, investigar causa |

Tempos de colecta elevados podem indicar:

- Problemas de rede entre o WatcherDB e os SQL Servers
- SQL Servers sobrecarregados que demoram a responder
- Queries de colecta pesadas (verificar o Collector Service)

---

## 4.6. Filtros e Pesquisa

No dashboard, pode filtrar e pesquisar servidores:

**Barra de pesquisa (topo):**
- Digitar o nome (ou parte do nome) do servidor
- Os resultados filtram-se em tempo real
- Suporta pesquisa parcial (ex: "PROD" encontra todos os servidores que conteem "PROD")

**Filtros de estado:**
- Clicar nos contadores [OK], [WARN] ou [CRIT] de um cartao para filtrar servidores por estado nessa categoria

---

---

# 5. Tabs de Servidor

Ao seleccionar um servidor no dashboard, abre-se a pagina de detalhe com 14 separadores (tabs) que oferecem informacao completa sobre a instancia SQL Server.

## 5.1. Overview

O tab **Overview** apresenta o estado geral do servidor seleccionado.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| Estado geral | Online/Offline, tempo de actividade (uptime) |
| Health Score | Pontuacao de saude de 0 a 100 |
| Informacao do servidor | Nome, versao SQL Server, edicao, patch level |
| Sistema operativo | Versao do Windows, RAM total, CPU cores |
| Bases de dados | Lista de databases com estado e tamanho |
| Status de servicos | SQL Engine, SQL Agent, etc. |
| Resumo de alertas | Contadores de WARNING e CRITICAL por categoria |

### Health Score

O Health Score e uma pontuacao calculada de 0 a 100 que reflecte o estado geral do servidor:

| Pontuacao | Classificacao | Cor |
|-----------|---------------|-----|
| 90-100 | Excelente | Verde |
| 75-89 | Bom | Verde claro |
| 50-74 | Regular | Amarelo |
| 25-49 | Mau | Laranja |
| 0-24 | Critico | Vermelho |

O Health Score considera todas as metricas do servidor: disponibilidade, performance, espaco, backups, alta disponibilidade e seguranca.

### Lista de Databases

A tabela de databases mostra:

| Coluna | Descricao |
|--------|-----------|
| Nome | Nome da base de dados |
| Estado | ONLINE, OFFLINE, RECOVERING, SUSPECT, etc. |
| Tamanho | Tamanho total em GB |
| Recovery Model | FULL, SIMPLE, BULK_LOGGED |
| Compatibilidade | Nivel de compatibilidade |
| Ultima backup FULL | Data e hora |

---

## 5.2. Always On

O tab **Always On** mostra informacao detalhada sobre Availability Groups configurados no servidor.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| Availability Groups | Lista de AGs com nome e estado |
| Replicas | Servidores que participam em cada AG |
| Estado de sincronizacao | SYNCHRONIZED, SYNCHRONIZING, NOT SYNCHRONIZING |
| Failover Events | Historico de failovers com data/hora e motivo |
| RPO/RTO | Recovery Point Objective e Recovery Time Objective |

### Tabela de Availability Groups

```
+---------------------------------------------------------------+
| AG Name        | Role     | Sync State    | Health | Replicas |
+---------------------------------------------------------------+
| AG_Producao    | PRIMARY  | SYNCHRONIZED  | OK     | 3/3      |
| AG_Reporting   | PRIMARY  | SYNCHRONIZING | WARN   | 2/3      |
+---------------------------------------------------------------+
```

### Detalhe de cada AG

Ao expandir um Availability Group, sao mostradas:

| Informacao | Descricao |
|------------|-----------|
| Replica primaria | Servidor que actualmente e o primario |
| Replicas secundarias | Servidores secundarios com estado de sincronizacao |
| Databases no AG | Lista de bases de dados incluidas no AG |
| Modo de failover | Automatico ou Manual |
| Modo de disponibilidade | Sincrono ou Assincrono |
| Endpoint URL | URL de mirroring de cada replica |
| Atraso de sincronizacao | Lag em segundos/minutos da replica secundaria |

### Failover Events

O historico de failovers mostra:

| Coluna | Descricao |
|--------|-----------|
| Data/Hora | Quando ocorreu o failover |
| AG | Nome do Availability Group |
| De | Replica de origem (antigo primario) |
| Para | Replica de destino (novo primario) |
| Tipo | Automatico ou Manual |
| Motivo | Razao do failover |

### RPO e RTO

| Metrica | Descricao | Significado |
|---------|-----------|-------------|
| RPO (Recovery Point Objective) | Ponto maximo de perda de dados toleravel | Quanto dados se pode perder |
| RTO (Recovery Time Objective) | Tempo maximo para recuperacao | Quanto tempo se pode estar em baixo |

---

## 5.3. Backup

O tab **Backup** fornece uma visao completa do estado das backups de todas as bases de dados do servidor.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| Ultima backup por tipo | FULL, DIFFERENTIAL, LOG |
| Gaps de backup | Bases de dados sem backup recente |
| Tendencias | Evolucao do tamanho das backups ao longo do tempo |
| Deteccao por schedule | Tipo de backup detectado com base no agendamento |

### Tabela de Backups

```
+--------------------------------------------------------------------------+
| Database      | Ultimo FULL      | Ultimo DIFF      | Ultimo LOG        |
+--------------------------------------------------------------------------+
| DB_Producao   | 2026-04-05 02:00 | 2026-04-05 14:00 | 2026-04-06 08:15 |
| DB_Reporting  | 2026-04-05 03:00 | 2026-04-05 15:00 | 2026-04-06 08:10 |
| DB_Staging    | 2026-04-01 02:00 | NUNCA            | NUNCA             |
+--------------------------------------------------------------------------+
```

### Tipos de Backup

| Tipo | Descricao | Frequencia tipica |
|------|-----------|-------------------|
| **FULL** | Backup completa de toda a base de dados | Diaria ou semanal |
| **DIFFERENTIAL** | Apenas as alteracoes desde o ultimo FULL | A cada 4-12 horas |
| **LOG** | Backup do transaction log | A cada 15-60 minutos |

### Gaps de Backup

Um "gap" de backup indica que uma base de dados nao tem backup recente. O WatcherDB classifica os gaps:

| Tipo backup | WARNING | CRITICAL |
|-------------|---------|----------|
| FULL | > 24 horas | > 48 horas |
| DIFF | > 12 horas | > 24 horas |
| LOG | > 1 hora | > 4 horas |

> **Nota:** Bases de dados com Recovery Model = SIMPLE nao necessitam de backup de LOG.

### Tendencias de Backup

O WatcherDB mostra graficos de tendencia que permitem:

- Ver a evolucao do tamanho das backups ao longo do tempo
- Identificar crescimento anormal
- Planear capacidade de armazenamento de backups

### Schedule-Based Detection

O WatcherDB detecta automaticamente o tipo de backup schedule com base no historico de backups:

- Analisa os padroes de frequencia dos ultimos 30 dias
- Classifica automaticamente se o schedule e diario, semanal, etc.
- Alerta quando uma backup esperada nao ocorre dentro da janela normal

---

## 5.4. Space

O tab **Space** monitoriza o espaco utilizado por filegroups em cada base de dados.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| Filegroups | Espaco alocado, usado e livre por filegroup |
| Forecast de crescimento | Previsao de quando o espaco se esgotara |
| Shrink candidates | Ficheiros com espaco livre recuperavel |
| Bases de dados por tamanho | Ranking das maiores bases de dados |

### Tabela de Filegroups

```
+--------------------------------------------------------------------------+
| Database     | Filegroup | Ficheiro     | Alocado  | Usado   | Livre    |
+--------------------------------------------------------------------------+
| DB_Producao  | PRIMARY   | DB_Prod.mdf  | 100 GB   | 82 GB   | 18 GB   |
| DB_Producao  | FG_DATA   | DB_Data.ndf  | 200 GB   | 175 GB  | 25 GB   |
| DB_Producao  | FG_INDEX  | DB_Idx.ndf   | 50 GB    | 35 GB   | 15 GB   |
+--------------------------------------------------------------------------+
```

### Forecast de Crescimento (Analise Preditiva)

O WatcherDB V3.3 inclui analise preditiva de crescimento dos filegroups:

| Informacao | Descricao |
|------------|-----------|
| Taxa de crescimento | GB/dia, GB/semana, GB/mes |
| Previsao de esgotamento | Data estimada em que o espaco se esgotara |
| Tendencia | Crescente, estavel ou decrescente |

A previsao baseia-se nos dados historicos dos ultimos 30/60/90 dias e utiliza regressao linear para projectar o crescimento futuro.

### Shrink Candidates

Lista de ficheiros com espaco livre significativo que podem ser candidatos a operacoes de shrink:

| Coluna | Descricao |
|--------|-----------|
| Database | Nome da base de dados |
| Ficheiro | Nome do ficheiro |
| Espaco livre | Quantidade de espaco livre dentro do ficheiro |
| Percentagem livre | Percentagem de espaco livre |
| Recomendacao | Se e aconselhavel fazer shrink |

> **Importante:** O tab Space exclui automaticamente a TempDB dos candidatos a shrink, pois fazer shrink da TempDB e geralmente contraproducente e pode causar problemas de performance.

---

## 5.5. Disk

O tab **Disk** monitoriza os volumes e drives fisicos do servidor.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| Volumes | Lista de drives com espaco total e livre |
| Uso por drive | Barra de progresso visual por drive |
| Espaco recuperavel | Espaco que pode ser libertado por base de dados |
| Candidatos a shrink | Ficheiros com espaco livre significativo |

### Tabela de Volumes

```
+--------------------------------------------------------------------------+
| Drive  | Label         | Total    | Livre     | Usado    | % Usado      |
+--------------------------------------------------------------------------+
| C:\    | Sistema       | 100 GB   | 35 GB     | 65 GB    | [===== ] 65% |
| D:\    | Dados SQL     | 500 GB   | 125 GB    | 375 GB   | [======] 75% |
| E:\    | Backups       | 1 TB     | 400 GB    | 600 GB   | [===== ] 60% |
| F:\    | TempDB        | 200 GB   | 150 GB    | 50 GB    | [==   ] 25%  |
+--------------------------------------------------------------------------+
```

### Espaco Recuperavel por Database

O WatcherDB calcula quanto espaco pode ser potencialmente recuperado em cada base de dados:

| Coluna | Descricao |
|--------|-----------|
| Database | Nome da base de dados |
| Drive | Volume onde reside |
| Tamanho actual | Tamanho total dos ficheiros |
| Espaco livre interno | Espaco livre dentro dos ficheiros |
| Potencial recuperacao | Espaco que poderia ser devolvido ao drive |

---

## 5.6. Encrypted

O tab **Encrypted** mostra informacao sobre Transparent Data Encryption (TDE) e certificados de encriptacao.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| TDE Status | Estado de encriptacao por base de dados |
| Certificados | Lista de certificados com validade |
| Databases encriptadas | Bases de dados com TDE activo |
| Databases nao encriptadas | Bases de dados sem TDE |

### Tabela TDE

```
+----------------------------------------------------------------------+
| Database     | TDE Status  | Algoritmo | Certificado  | Expira      |
+----------------------------------------------------------------------+
| DB_Producao  | Encrypted   | AES_256   | TDE_Cert_01  | 2027-01-15  |
| DB_Reporting | Encrypted   | AES_256   | TDE_Cert_01  | 2027-01-15  |
| DB_Staging   | Not Encr.   | -         | -            | -           |
+----------------------------------------------------------------------+
```

### Alertas de TDE

| Alerta | Condicao |
|--------|----------|
| Certificado a expirar | Menos de 90 dias para a expiracao |
| Certificado expirado | Certificado ja expirou |
| Base de dados sem TDE | Base de dados de producao sem encriptacao |
| Backup do certificado | Certificado sem backup recente |

---

## 5.7. CPU

O tab **CPU** monitoriza a utilizacao de CPU do processo SQL Server.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| CPU actual | Percentagem de CPU utilizada pelo SQL Server |
| CPU sistema | Percentagem de CPU total do servidor |
| Historico | Grafico de uso de CPU ao longo do tempo |
| Top queries | Queries com maior consumo de CPU (se disponivel) |

### Grafico de CPU

O grafico mostra duas linhas:

- **SQL Server Process** (azul): CPU consumida pelo processo sqlservr.exe
- **System Total** (cinza): CPU total do servidor (todos os processos)

A diferenca entre as duas linhas indica CPU utilizada por outros processos no servidor.

### Limiares de CPU

| Nivel | Valor | Significado |
|-------|-------|-------------|
| Normal | < 60% | Operacao normal |
| Elevado | 60-80% | Atencao, carga significativa |
| Critico | > 80% | Carga excessiva, investigar |
| Saturado | > 95% | Servidor saturado, accao urgente |

---

## 5.8. Memory

O tab **Memory** monitorisa a utilizacao de memoria do SQL Server.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| Memoria SQL Server | RAM utilizada pelo SQL Server |
| Page Life Expectancy | Tempo medio de uma pagina no buffer cache |
| Buffer Cache Hit Ratio | Percentagem de paginas encontradas em cache |
| Memoria do sistema | RAM total e utilizada do servidor |

### Metricas de Memoria

| Metrica | Descricao | Valor ideal |
|---------|-----------|-------------|
| **Page Life Expectancy (PLE)** | Tempo (em segundos) que uma pagina permanece no buffer cache | > 300 segundos |
| **Buffer Cache Hit Ratio** | Percentagem de paginas lidas do cache vs. disco | > 99% |
| **Memory Grants Pending** | Queries a espera de memoria | 0 |
| **Target Server Memory** | Memoria que o SQL Server pretende utilizar | Proximo do Max Server Memory |
| **Total Server Memory** | Memoria actualmente utilizada | Proximo do Target |

### Alertas de Memoria

| Condicao | Nivel | Significado |
|----------|-------|-------------|
| PLE < 300 | WARNING | Buffer cache sob pressao |
| PLE < 60 | CRITICAL | Buffer cache severamente pressionado |
| Cache Hit < 95% | WARNING | Demasiadas leituras de disco |
| Memory Grants Pending > 0 | WARNING | Queries a espera de memoria |

---

## 5.9. Services

O tab **Services** mostra o estado dos servicos SQL Server no servidor.

### Servicos monitorizados

| Servico | Descricao |
|---------|-----------|
| SQL Server (Engine) | Motor principal do SQL Server |
| SQL Server Agent | Servico de agendamento de jobs |
| SQL Server Browser | Servico de descoberta de instancias |
| SQL Server Reporting Services | Servico de relatorios (SSRS) |
| SQL Server Integration Services | Servico de integracao de dados (SSIS) |
| SQL Server Analysis Services | Servico de analise (SSAS) |
| Full-Text Search | Servico de pesquisa full-text |

### Tabela de Servicos

```
+----------------------------------------------------------------------+
| Servico                | Estado   | Startup   | Conta               |
+----------------------------------------------------------------------+
| SQL Server (MSSQLSVR)  | Running  | Automatic | DOMAIN\svc_sql      |
| SQL Server Agent       | Running  | Automatic | DOMAIN\svc_sqlagent |
| SQL Server Browser     | Running  | Automatic | NT AUTHORITY\LOCAL   |
| SSRS                   | Stopped  | Manual    | DOMAIN\svc_ssrs     |
+----------------------------------------------------------------------+
```

### Alertas de Servicos

| Condicao | Nivel |
|----------|-------|
| SQL Server Engine parado | CRITICAL |
| SQL Server Agent parado | WARNING |
| Servico com startup Automatic mas parado | WARNING |
| Servico a correr com conta incorrecta | INFO |

---

## 5.10. Log

O tab **Log** mostra o SQL Server Error Log com capacidade de filtragem por severidade.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| Error Log actual | Entradas do log actual do SQL Server |
| Filtro por severidade | Filtrar por nivel de severidade |
| Pesquisa | Pesquisar texto livre no log |
| Contadores | Numero de eventos por severidade |

### Niveis de Severidade

| Severidade | Descricao | Cor |
|------------|-----------|-----|
| Information | Eventos informativos | Azul |
| Warning | Avisos que necessitam atencao | Amarelo |
| Error | Erros que afectam operacao | Vermelho |

### Exemplo de entradas de log

```
+--------------------------------------------------------------------------+
| Data/Hora            | Severidade  | Mensagem                            |
+--------------------------------------------------------------------------+
| 2026-04-06 08:15:23  | Information | Database 'DB_Prod' backed up.       |
| 2026-04-06 08:10:45  | Warning     | I/O requests taking longer than 15s |
| 2026-04-06 07:55:12  | Error       | Login failed for user 'app_user'    |
+--------------------------------------------------------------------------+
```

### Dicas de utilizacao

- Utilizar o filtro de severidade para focar em erros criticos
- Pesquisar por texto especifico (ex: "deadlock", "backup", "login failed")
- Os logs sao mostrados do mais recente para o mais antigo
- O SQL Server mantém multiplos ficheiros de log; o WatcherDB mostra o log actual

---

## 5.11. SQL Diagnostics

O tab **SQL Diagnostics** e uma ferramenta avancada de diagnostico que revela problemas de performance e concorrencia no SQL Server.

### Seccoes de diagnostico

#### Blocking

| Informacao | Descricao |
|------------|-----------|
| Sessoes bloqueadas | Sessoes que estao a espera de um lock |
| Sessao bloqueadora | A sessao que detém o lock |
| Tempo de espera | Ha quanto tempo esta bloqueado |
| Query bloqueada | O comando SQL que esta bloqueado |
| Query bloqueadora | O comando SQL que esta a causar o bloqueio |

#### Deadlocks

| Informacao | Descricao |
|------------|-----------|
| Deadlocks recentes | Lista de deadlocks detectados |
| Vitima | Sessao que foi terminada (victim) |
| Recursos envolvidos | Tabelas/indices envolvidos no deadlock |
| Queries | Comandos SQL de cada sessao |
| Data/Hora | Quando o deadlock ocorreu |

#### Slow Queries

| Informacao | Descricao |
|------------|-----------|
| Top queries lentas | Queries com maior tempo de execucao |
| Tempo de execucao | Duracao media e maxima |
| Contagem de execucoes | Numero de vezes que a query foi executada |
| Plano de execucao | Indicacao se o plano esta em cache |
| CPU e I/O | Recursos consumidos pela query |

#### Missing Indexes

| Informacao | Descricao |
|------------|-----------|
| Indices sugeridos | Indices que o SQL Server sugere criar |
| Impacto estimado | Melhoria estimada de performance |
| Tabela | Tabela que beneficiaria do indice |
| Colunas | Colunas sugeridas para o indice |
| Seeks/Scans | Numero de seeks e scans que beneficiariam |

#### Sessions

| Informacao | Descricao |
|------------|-----------|
| Sessoes activas | Lista de sessoes abertas no SQL Server |
| SPID | ID da sessao |
| Login | Nome do login |
| Database | Base de dados actual |
| Comando | Comando em execucao |
| Estado | Running, sleeping, etc. |

#### I/O Stats

| Informacao | Descricao |
|------------|-----------|
| I/O por ficheiro | Estatisticas de leitura e escrita por ficheiro |
| Latencia de leitura | Tempo medio de leitura em ms |
| Latencia de escrita | Tempo medio de escrita em ms |
| Stalls | Numero de stalls de I/O |

---

## 5.12. Security

O tab **Security** fornece uma visao da seguranca do SQL Server.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| Logins | Lista de server-level logins |
| Permissoes | Permissoes atribuidas a cada login |
| Auditing | Configuracoes de auditoria |
| Vulnerabilidades | Potenciais problemas de seguranca |

### Tabela de Logins

```
+--------------------------------------------------------------------------+
| Login            | Tipo     | Estado   | Default DB   | Ultimo acesso   |
+--------------------------------------------------------------------------+
| sa               | SQL      | Disabled | master       | 2026-01-15      |
| DOMAIN\svc_sql   | Windows  | Enabled  | master       | 2026-04-06      |
| DOMAIN\DBA_Team  | Windows  | Enabled  | master       | 2026-04-06      |
| app_user         | SQL      | Enabled  | DB_Producao  | 2026-04-06      |
+--------------------------------------------------------------------------+
```

### Verificacoes de seguranca

O WatcherDB verifica e alerta sobre:

| Verificacao | Descricao | Nivel |
|-------------|-----------|-------|
| Conta 'sa' activa | A conta sa deve estar desactivada | WARNING |
| Logins sem senha forte | Logins SQL com senhas fracas | WARNING |
| Permissoes excessivas | Logins com sysadmin desnecessario | WARNING |
| Audit desactivada | SQL Server Audit nao configurada | INFO |
| xp_cmdshell activa | xp_cmdshell nao deve estar activa | WARNING |
| CLR activo | CLR integration deve ser avaliada | INFO |

---

## 5.13. Users

O tab **Users** mostra informacao detalhada sobre logins SQL, utilizadores de bases de dados e roles.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| SQL Logins | Logins de autenticacao SQL Server |
| Database Users | Utilizadores mapeados por base de dados |
| Roles | Server roles e database roles |
| Mapped Databases | Bases de dados mapeadas para cada login |

### SQL Logins

```
+----------------------------------------------------------------------+
| Login       | Tipo   | Policy | Expiration | Check Policy | Enabled  |
+----------------------------------------------------------------------+
| app_user    | SQL    | ON     | OFF        | ON           | Yes      |
| report_user | SQL    | ON     | ON         | ON           | Yes      |
| old_user    | SQL    | OFF    | OFF        | OFF          | No       |
+----------------------------------------------------------------------+
```

### Database Users e Roles

```
+----------------------------------------------------------------------+
| Database     | User          | Role          | Tipo                  |
+----------------------------------------------------------------------+
| DB_Producao  | app_user      | db_datareader | SQL_USER              |
| DB_Producao  | app_user      | db_datawriter | SQL_USER              |
| DB_Producao  | DOMAIN\DBA    | db_owner      | WINDOWS_USER          |
| DB_Reporting | report_user   | db_datareader | SQL_USER              |
+----------------------------------------------------------------------+
```

---

## 5.14. Jobs

O tab **Jobs** monitorisa os SQL Server Agent Jobs.

### Informacao apresentada

| Seccao | Conteudo |
|--------|----------|
| Lista de Jobs | Todos os jobs configurados com estado |
| Jobs falhados | Jobs que falharam na ultima execucao |
| Conflitos de schedule | Jobs agendados para o mesmo horario |
| Tendencias | Evolucao de execucoes e falhas ao longo do tempo |

### Tabela de Jobs

```
+--------------------------------------------------------------------------+
| Job Name            | Estado   | Ultima Exec.     | Duracao | Resultado  |
+--------------------------------------------------------------------------+
| Backup_FULL_Diario  | Enabled  | 2026-04-06 02:00 | 45 min  | Succeeded  |
| Backup_LOG_15min    | Enabled  | 2026-04-06 08:15 | 2 min   | Succeeded  |
| Manutencao_Indices  | Enabled  | 2026-04-06 03:00 | 2h 15m  | Succeeded  |
| ETL_Diario          | Enabled  | 2026-04-06 06:00 | 35 min  | Failed     |
| Limpeza_Historico   | Disabled | 2026-03-15 02:00 | 10 min  | Succeeded  |
+--------------------------------------------------------------------------+
```

### Detalhe de Jobs Falhados

Ao clicar num job falhado, mostra:

| Informacao | Descricao |
|------------|-----------|
| Mensagem de erro | Texto completo do erro |
| Step falhado | Qual step do job falhou |
| Historico | Ultimas N execucoes com resultado |
| Duracoes | Comparacao de duracao entre execucoes |

### Conflitos de Schedule

O WatcherDB detecta automaticamente quando dois ou mais jobs estao agendados para correr ao mesmo tempo ou com sobreposicao:

```
+----------------------------------------------------------------------+
| Conflito                                                              |
+----------------------------------------------------------------------+
| Backup_FULL e Manutencao_Indices ambos agendados para 02:00          |
| ETL_Diario (06:00-06:35) sobrepoe com Stats_Update (06:15-06:45)    |
+----------------------------------------------------------------------+
```

### Tendencias de Jobs

Os graficos de tendencia mostram:

- Percentagem de sucesso/falha ao longo do tempo
- Evolucao da duracao de cada job
- Padrao de falhas (se ha dias/horas com mais falhas)

---

---

# 6. Painel de Controlo

## 6.1. Aceder ao Painel de Controlo

O Painel de Controlo esta disponivel no URL:

```
https://servidor:8433/watcherdb/control
```

Tambem pode ser acedido atraves do menu do utilizador na barra superior do portal.

> **Nota:** O acesso ao Painel de Controlo e restrito a utilizadores com role **admin** ou **operator**. Utilizadores com role **viewer** ou **analyst** nao conseguem aceder.

### Seccoes do Painel de Controlo

```
+------------------------------------------------------------------+
|  Painel de Controlo                                              |
|                                                                  |
|  +-------------------+  +-------------------+                    |
|  | Gestao de         |  | Auth Log          |                    |
|  | Utilizadores      |  | Historico logins   |                    |
|  +-------------------+  +-------------------+                    |
|                                                                  |
|  +-------------------+  +-------------------+                    |
|  | Sessoes Activas   |  | Resource Monitor  |                    |
|  | Users online      |  | CPU/RAM/Disco     |                    |
|  +-------------------+  +-------------------+                    |
|                                                                  |
|  +-------------------+                                           |
|  | Configuracoes     |                                           |
|  | JWT, AD, Politicas|                                           |
|  +-------------------+                                           |
+------------------------------------------------------------------+
```

---

## 6.2. Gestao de Utilizadores

A seccao de Gestao de Utilizadores permite gerir todas as contas do WatcherDB.

### Lista de Utilizadores

```
+--------------------------------------------------------------------------+
| Username   | Nome           | Email              | Role    | Tipo  | Estado |
+--------------------------------------------------------------------------+
| admin      | Administrador  | admin@tap.pt       | admin   | Local | Active |
| joao.silva | Joao Silva     | j.silva@tap.pt     | analyst | AD    | Active |
| maria.dba  | Maria Santos   | m.santos@tap.pt    | operator| AD    | Active |
| viewer01   | Viewer Account | viewer@tap.pt      | viewer  | Local | Locked |
+--------------------------------------------------------------------------+
```

### Criar Utilizador Local

Para criar um novo utilizador local:

1. Clicar em **Novo Utilizador**
2. Seleccionar tipo **Local**
3. Preencher os campos:

| Campo | Obrigatorio | Descricao |
|-------|-------------|-----------|
| Username | Sim | Nome de utilizador unico |
| Nome completo | Sim | Nome para apresentacao |
| Email | Nao | Endereco de email |
| Role | Sim | viewer, analyst, operator, ou admin |
| Senha | Sim | Deve cumprir a politica de senhas |

4. Clicar em **Criar**

**Requisitos da senha:**

```
Minimo 8 caracteres
Pelo menos 1 letra maiuscula (A-Z)
Pelo menos 1 letra minuscula (a-z)
Pelo menos 1 numero (0-9)
Pelo menos 1 simbolo (!@#$%^&*()-_+=[]{}|;:',.<>?/)
```

### Criar Utilizador Active Directory

Para criar um novo utilizador AD:

1. Clicar em **Novo Utilizador**
2. Seleccionar tipo **Active Directory**
3. Seleccionar o **Dominio** no dropdown (se multi-dominio configurado)
4. Digitar o nome do utilizador no campo de pesquisa
5. A pesquisa LDAP e executada automaticamente (pesquisa por sAMAccountName, cn e displayName)
6. Seleccionar o utilizador correcto nos resultados
7. Os campos **Nome** e **Email** sao preenchidos automaticamente (proxyAddresses, UPN, mail)
8. Seleccionar o **Role**
9. Clicar em **Criar**

> **Nota:** Utilizadores AD nao necessitam de senha no WatcherDB. A autenticacao e feita directamente contra o Active Directory.

### Editar Utilizador

Para editar um utilizador existente:

1. Clicar no icone de edicao (lapis) na linha do utilizador
2. Campos editaveis:

| Campo | Descricao |
|-------|-----------|
| Nome completo | Alterar o nome de apresentacao |
| Email | Alterar o endereco de email |
| Role | Alterar a funcao (viewer/analyst/operator/admin) |

3. Clicar em **Guardar**

### Roles de Utilizador

| Role | Descricao | Permissoes |
|------|-----------|------------|
| **viewer** | Visualizacao apenas | Ver dashboard e tabs de servidor (leitura) |
| **analyst** | Analista | Viewer + exportar relatorios PDF + DBA Copilot |
| **operator** | Operador | Analyst + acesso ao Painel de Controlo (gestao parcial) |
| **admin** | Administrador | Acesso total, gestao de utilizadores e configuracoes |

### Reset de Senha

Para fazer reset da senha de um utilizador:

1. Clicar em **Editar** no utilizador
2. Clicar em **Reset Senha**
3. Introduzir a nova senha (deve cumprir a politica)
4. Clicar em **Confirmar**
5. O utilizador recebe o flag `must_change_password` e sera obrigado a alterar a senha no proximo login

> **Nota:** O reset de senha so e aplicavel a utilizadores Locais. Utilizadores AD gerem a senha no Active Directory.

### Eliminar Utilizador

Para eliminar um utilizador:

1. Clicar no icone de eliminacao (lixeira) na linha do utilizador
2. Um dialogo de confirmacao aparece:

```
+------------------------------------------+
|  Confirmar eliminacao                    |
|                                          |
|  Tem a certeza que deseja eliminar o     |
|  utilizador "joao.silva"?                |
|                                          |
|  Esta accao e PERMANENTE e nao pode      |
|  ser revertida.                          |
|                                          |
|  [Cancelar]    [Eliminar]               |
+------------------------------------------+
```

3. Clicar em **Eliminar** para confirmar

> **Aviso:** A eliminacao de um utilizador e permanente. Todas as sessoes activas desse utilizador sao terminadas imediatamente.

### Activar/Desactivar Utilizador

Para desactivar um utilizador sem o eliminar:

1. Clicar no toggle de estado na linha do utilizador
2. O utilizador fica com estado **Inactive**
3. Nao consegue fazer login enquanto estiver inactivo
4. Para reactivar, clicar novamente no toggle

---

## 6.3. Auth Log

O Auth Log mostra o historico completo de tentativas de autenticacao no portal.

### Informacao apresentada

```
+--------------------------------------------------------------------------+
| Data/Hora            | Username   | Resultado | IP           | Detalhes  |
+--------------------------------------------------------------------------+
| 2026-04-06 08:15:23  | admin      | Sucesso   | 10.0.1.50    |           |
| 2026-04-06 08:14:55  | joao.silva | Sucesso   | 10.0.1.51    | AD Login  |
| 2026-04-06 08:10:12  | hacker123  | Falha     | 192.168.1.99 | User not  |
|                      |            |           |              | found     |
| 2026-04-06 08:09:45  | admin      | Falha     | 192.168.1.99 | Wrong     |
|                      |            |           |              | password  |
+--------------------------------------------------------------------------+
```

### Campos do Auth Log

| Campo | Descricao |
|-------|-----------|
| Data/Hora | Timestamp exacto da tentativa |
| Username | Nome de utilizador fornecido |
| Resultado | Sucesso ou Falha |
| IP | Endereco IP de origem |
| Detalhes | Informacao adicional (motivo de falha, tipo de login, etc.) |

### Filtros disponiveis

- **Por resultado:** Sucesso, Falha, Todos
- **Por data:** Intervalo de datas
- **Por username:** Pesquisa por nome de utilizador
- **Por IP:** Pesquisa por endereco IP

### Utilidade do Auth Log

O Auth Log e essencial para:

- **Seguranca:** Detectar tentativas de acesso nao autorizado
- **Auditoria:** Registar quem acedeu ao portal e quando
- **Diagnostico:** Identificar problemas de autenticacao
- **Compliance:** Manter registos de acesso para auditorias

---

## 6.4. Sessoes Activas

A seccao de Sessoes Activas mostra todos os utilizadores actualmente online no portal.

### Informacao apresentada

```
+--------------------------------------------------------------------------+
| Username     | Nome           | Login            | Ultima actividade     |
+--------------------------------------------------------------------------+
| admin        | Administrador  | 2026-04-06 07:30 | 2026-04-06 08:16      |
| joao.silva   | Joao Silva     | 2026-04-06 08:15 | 2026-04-06 08:16      |
| maria.dba    | Maria Santos   | 2026-04-06 08:00 | 2026-04-06 08:14      |
+--------------------------------------------------------------------------+
```

### Mecanismo de Heartbeat

O WatcherDB utiliza um sistema de heartbeat para detectar utilizadores online:

- O browser envia um heartbeat a cada **60 segundos**
- Se o heartbeat nao for recebido durante 2 minutos, o utilizador e considerado offline
- A sessao JWT permanece valida ate expirar, mas o utilizador ja nao aparece na lista de sessoes activas

### Informacao por sessao

| Campo | Descricao |
|-------|-----------|
| Username | Nome de utilizador |
| Nome | Nome completo |
| Hora de login | Quando o utilizador fez login |
| Ultima actividade | Ultimo heartbeat recebido |
| Duracao | Tempo total da sessao |
| IP | Endereco IP do utilizador |
| Browser | Tipo de browser detectado |

---

## 6.5. Resource Monitor

O Resource Monitor mostra metricas em tempo real do processo WatcherDB e do servidor onde corre.

### Metricas do Processo WatcherDB

| Metrica | Descricao |
|---------|-----------|
| CPU do processo | Percentagem de CPU utilizada pelo WatcherDB |
| RAM RSS | Resident Set Size - memoria fisica utilizada |
| RAM VMS | Virtual Memory Size - memoria virtual alocada |
| Threads | Numero de threads do processo |
| Open files | Numero de ficheiros abertos |
| Connections | Numero de conexoes de rede activas |
| Uptime | Tempo desde que o processo arrancou |

### Metricas do Servidor

| Metrica | Descricao |
|---------|-----------|
| Hostname | Nome do servidor |
| Sistema operativo | Versao do Windows |
| CPU total | Numero de cores e utilizacao actual |
| RAM total | RAM instalada |
| RAM utilizada | RAM em uso e percentagem |
| Disco | Espaco utilizado nos volumes |

### Informacao de Runtime

| Metrica | Descricao |
|---------|-----------|
| Python version | Versao do Python em uso |
| Working directory | Directorio de trabalho do WatcherDB |
| Porta | Porta em que o portal esta a escutar |
| PID | Process ID do WatcherDB |
| Workers | Numero de workers Uvicorn |

### Auto-Refresh

O Resource Monitor actualiza automaticamente a cada **10 segundos**, mostrando metricas em tempo real sem necessidade de recarregar a pagina.

### Utilizacao tipica

O Resource Monitor e util para:

- **Verificar saude do WatcherDB:** Se o processo esta a consumir demasiados recursos
- **Diagnostico de performance:** Identificar se o servidor esta sobrecarregado
- **Planeamento de capacidade:** Avaliar se os recursos do servidor sao suficientes
- **Troubleshooting:** Verificar se ha fugas de memoria ou CPU elevada

---

## 6.6. Configuracoes

A seccao de Configuracoes permite ajustar parametros do sistema sem necessidade de editar ficheiros.

### JWT (JSON Web Token)

| Parametro | Descricao | Valor por defeito | Limites |
|-----------|-----------|-------------------|---------|
| JWT Expiration | Tempo de validade do token em minutos | 480 (8 horas) | 60-1440 minutos |

Ao alterar a expiracao JWT:

- Tokens ja emitidos mantém a sua validade original
- Novos tokens utilizam a nova duracao
- Valores mais baixos sao mais seguros mas obrigam a reautenticacao mais frequente

### Lockout

| Parametro | Descricao | Valor por defeito | Opcoes |
|-----------|-----------|-------------------|--------|
| Max failed attempts | Tentativas falhadas antes do bloqueio | 5 | 3, 5, 10 |
| Lockout time | Duracao do bloqueio em minutos | 15 | 5, 10, 15, 30, 60 |

Quando um utilizador excede o numero maximo de tentativas falhadas:

1. A conta e bloqueada automaticamente
2. O Auth Log regista o evento de lockout
3. Apos o periodo de lockout, a conta e desbloqueada automaticamente
4. Um administrador pode desbloquear manualmente antes do tempo

### Active Directory

Configuracao de dominios Active Directory para autenticacao hibrida:

| Parametro | Descricao |
|-----------|-----------|
| Dominios | Lista de dominios AD configurados (cards) |
| Base DN | Distinguished Name base para pesquisas LDAP |
| Service Account | Conta de servico para bind LDAP (opcional) |
| DNS SRV | Activar/desactivar descoberta automatica de DCs |

Para mais detalhes sobre a configuracao AD, ver [Seccao 7 - Active Directory](#7-active-directory).

### Politica de Senhas

| Parametro | Descricao | Valor |
|-----------|-----------|-------|
| Comprimento minimo | Numero minimo de caracteres | 8 |
| Maiuscula obrigatoria | Requer pelo menos 1 letra maiuscula | Sim |
| Minuscula obrigatoria | Requer pelo menos 1 letra minuscula | Sim |
| Digito obrigatorio | Requer pelo menos 1 numero | Sim |
| Simbolo obrigatorio | Requer pelo menos 1 caracter especial | Sim |

### Persistencia de Configuracoes

Todas as configuracoes sao armazenadas na base de dados (WatcherDB_Intelligence) e persistem entre reinicializacoes do servico. Nao e necessario reiniciar o servico apos alterar configuracoes no Painel de Controlo.

---

---

# 7. Active Directory

## 7.1. Configuracao Multi-Dominio

O WatcherDB V3.3 suporta autenticacao contra multiplos dominios Active Directory simultaneamente.

### Apresentacao

Os dominios configurados sao apresentados como **cards** na interface:

```
+-------------------+  +-------------------+  +-------------------+
| DOMINIO-A.LOCAL   |  | DOMINIO-B.LOCAL   |  | DOMINIO-C.LOCAL   |
|                   |  |                   |  |                   |
| Status: OK        |  | Status: OK        |  | Status: Offline   |
| DCs: 3            |  | DCs: 2            |  | DCs: 0            |
| Users: 45         |  | Users: 23         |  | Users: 12         |
|                   |  |                   |  |                   |
| [Editar] [Testar] |  | [Editar] [Testar] |  | [Editar] [Testar] |
+-------------------+  +-------------------+  +-------------------+
```

### Adicionar um novo dominio

1. No Painel de Controlo, ir a **Configuracoes** → **Active Directory**
2. Clicar em **Adicionar Dominio**
3. Preencher:

| Campo | Descricao | Exemplo |
|-------|-----------|---------|
| Nome do dominio | FQDN do dominio AD | dominio-a.local |
| Base DN | Distinguished Name base | DC=dominio-a,DC=local |
| Service Account (opcional) | Conta para bind LDAP | svc_watcherdb@dominio-a.local |
| Senha (se service account) | Senha da conta de servico | ********** |
| DNS SRV | Activar descoberta automatica | Sim |
| Porta LDAP | Porta (389 ou 636 para LDAPS) | 389 |

4. Clicar em **Testar Conexao** para verificar
5. Clicar em **Guardar**

---

## 7.2. DNS SRV Discovery

Quando a opcao DNS SRV esta activa, o WatcherDB descobre automaticamente os Domain Controllers (DCs) disponiveis atraves de registos DNS SRV.

### Como funciona

1. O WatcherDB faz uma query DNS SRV para `_ldap._tcp.dominio.local`
2. Obtem a lista de DCs disponiveis com prioridade e peso
3. Selecciona o DC mais adequado (prioridade mais baixa, peso mais alto)
4. Em caso de falha, tenta automaticamente o proximo DC na lista

### Vantagens do DNS SRV

- Nao e necessario configurar IPs de DCs manualmente
- Failover automatico quando um DC fica indisponivel
- Acompanha alteracoes na infraestrutura AD automaticamente
- Respeita a prioridade e peso configurados no DNS

### Verificar registos DNS SRV

```powershell
# Verificar registos SRV no DNS
nslookup -type=SRV _ldap._tcp.dominio.local
```

---

## 7.3. Pesquisa LDAP

A pesquisa LDAP no WatcherDB e flexivel e suporta wildcards.

### Campos pesquisados

Ao criar um utilizador AD, a pesquisa e feita simultaneamente nos seguintes atributos:

| Atributo LDAP | Descricao |
|---------------|-----------|
| sAMAccountName | Nome de logon (ex: joao.silva) |
| cn | Common Name (ex: Joao Silva) |
| displayName | Nome de apresentacao |

### Funcionamento da pesquisa

1. O administrador digita o texto de pesquisa (ex: "joao")
2. O WatcherDB constroi um filtro LDAP com wildcards:
   ```
   (|(sAMAccountName=*joao*)(cn=*joao*)(displayName=*joao*))
   ```
3. A pesquisa e executada contra o dominio seleccionado
4. Os resultados sao apresentados numa lista

### Exemplo de pesquisa

```
Pesquisa: "silva"

Resultados:
+----------------------------------------------------------------------+
| Username       | Nome            | Email                | Departamento |
+----------------------------------------------------------------------+
| joao.silva     | Joao Silva      | j.silva@tap.pt       | DBA          |
| maria.silva    | Maria Silva     | m.silva@tap.pt       | Infra        |
| pedro.silveira | Pedro Silveira  | p.silveira@tap.pt    | Dev          |
+----------------------------------------------------------------------+
```

---

## 7.4. Auto-Preenchimento de Dados

Ao seleccionar um utilizador AD na pesquisa, o WatcherDB preenche automaticamente os campos do formulario.

### Atributos mapeados

| Campo WatcherDB | Fonte LDAP (prioridade) |
|-----------------|-------------------------|
| Nome | displayName → cn |
| Email | proxyAddresses (SMTP:) → mail → userPrincipalName |

### Logica de email

O email e obtido pela seguinte ordem de prioridade:

1. **proxyAddresses:** Procura o endereco primario (com prefixo `SMTP:` em maiusculas)
2. **mail:** Atributo de email directo
3. **userPrincipalName (UPN):** Utilizado como fallback (ex: joao.silva@dominio.local)

---

## 7.5. Bind e Autenticacao Kerberos

O WatcherDB utiliza uma cadeia de prioridade para se ligar ao LDAP:

### Ordem de prioridade de bind

| Prioridade | Metodo | Descricao |
|------------|--------|-----------|
| 1 | Service Account | Utiliza as credenciais da conta de servico configurada |
| 2 | GSSAPI (Kerberos) | Utiliza o ticket Kerberos do servico Windows |
| 3 | Anonymous | Bind anonimo (funcionalidade limitada) |

### Como funciona

1. **Service Account:** Se uma conta de servico esta configurada para o dominio, e o metodo preferido. Garante acesso consistente.

2. **GSSAPI (Kerberos):** Se nao ha conta de servico, o WatcherDB tenta utilizar o ticket Kerberos da conta Windows sob a qual o servico esta a correr. Requer que o servico corra sob uma conta de dominio.

3. **Anonymous:** Ultimo recurso. Muitos ADs nao permitem bind anonimo, pelo que a funcionalidade pode ser limitada.

### Recomendacao

Configurar uma **conta de servico dedicada** para cada dominio e a opcao mais fiavel e segura:

- Criar uma conta de servico no AD (ex: `svc_watcherdb`)
- Atribuir permissoes de leitura no AD (Read Members, Read All Properties)
- Configurar a conta no WatcherDB com a senha
- A conta nao necessita de permissoes de administrador

---

---

# 8. Funcionalidades Adicionais

## 8.1. Pesquisa de Servidores

A barra de pesquisa no topo do portal permite encontrar servidores rapidamente.

### Utilizacao

1. Clicar na barra de pesquisa (ou pressionar `Ctrl+F`)
2. Digitar o nome (ou parte do nome) do servidor
3. Os resultados aparecem em tempo real enquanto se digita
4. Clicar no servidor desejado para abrir o detalhe

### Funcionalidades da pesquisa

| Funcionalidade | Descricao |
|----------------|-----------|
| Pesquisa parcial | "PROD" encontra "SQL-PROD-01", "SQL-PROD-02", etc. |
| Case insensitive | "prod" e "PROD" dao os mesmos resultados |
| Pesquisa instantanea | Resultados aparecem enquanto se digita |
| Acesso directo | Clicar no resultado abre o servidor |

---

## 8.2. Exportacao PDF

O WatcherDB V3.3 permite exportar relatorios em formato PDF.

### Como exportar

1. Navegar para o servidor ou tab desejado
2. Clicar no botao **Exportar PDF** (icone de documento)
3. O PDF e gerado e descarregado automaticamente

### Conteudo do PDF

| Seccao | Conteudo incluido |
|--------|-------------------|
| Cabecalho | Nome do servidor, data/hora de geracao |
| Resumo | Health Score, estado geral |
| KPIs | Metricas principais |
| Detalhes | Dados do tab activo |
| Rodape | Informacao do WatcherDB, pagina |

### Requisitos

- Role minima: **analyst** (viewers nao podem exportar)
- O PDF e gerado no servidor e enviado ao browser
- Ficheiros grandes (muitos dados) podem demorar alguns segundos

---

## 8.3. Network Diagnostics

A funcionalidade de Network Diagnostics permite verificar a conectividade entre o WatcherDB e as instancias SQL Server.

### Funcionalidades

| Teste | Descricao |
|-------|-----------|
| Ping | Teste ICMP para verificar se o servidor responde |
| Porta SQL | Teste de conexao TCP a porta 1433 |
| Latencia | Medida do tempo de resposta |

### Como utilizar

1. No tab Overview de um servidor, clicar em **Network Diagnostics**
2. O WatcherDB executa os testes automaticamente
3. Os resultados sao apresentados:

```
+----------------------------------------------------------------------+
| Teste          | Resultado | Detalhe                                 |
+----------------------------------------------------------------------+
| Ping           | OK        | Resposta em 2ms                         |
| Porta 1433     | OK        | Conexao TCP estabelecida                |
| Latencia media | OK        | 3.5ms (media de 5 tentativas)          |
+----------------------------------------------------------------------+
```

---

## 8.4. Analise Preditiva

O WatcherDB V3.3 inclui capacidades de analise preditiva para crescimento de dados.

### Previsao de Crescimento de Filegroups

Baseado nos dados historicos colectados pelo Collector Service, o WatcherDB calcula:

| Metrica | Descricao |
|---------|-----------|
| Taxa de crescimento | Ritmo de crescimento por dia/semana/mes |
| Data de esgotamento | Quando o espaco se esgotara ao ritmo actual |
| Tendencia | Se o crescimento e linear, acelerado ou estavel |

### Como funciona

1. O sistema recolhe dados de espaco de cada filegroup ao longo do tempo
2. Aplica regressao linear sobre os dados historicos (30/60/90 dias)
3. Projecta o crescimento futuro
4. Calcula a data estimada de esgotamento do espaco

### Visualizacao

O tab **Space** de cada servidor inclui:

- Grafico de evolucao do espaco utilizado
- Linha de tendencia projectada para o futuro
- Indicador visual da data estimada de esgotamento
- Alerta automatico quando o esgotamento e previsto dentro de 30 dias

### Limitacoes

- A previsao baseia-se em dados historicos e assume crescimento linear
- Eventos extraordinarios (migracao de dados, limpeza, etc.) podem alterar a tendencia
- Quanto mais dados historicos disponiveis, mais precisa e a previsao

---

## 8.5. DBA Copilot

O DBA Copilot e uma funcionalidade de perguntas e respostas baseada em regras que ajuda DBAs com consultas rapidas.

### Funcionalidade

O DBA Copilot responde a perguntas comuns sobre:

| Categoria | Exemplos de perguntas |
|-----------|-----------------------|
| Backup | "Qual a ultima backup da DB_Producao?" |
| Espaco | "Quanto espaco livre tem o servidor SQL-PROD-01?" |
| Performance | "Quais os servidores com CPU acima de 80%?" |
| Jobs | "Quais os jobs que falharam hoje?" |
| Always On | "Quais os AGs com problemas de sincronizacao?" |
| Geral | "Quais os servidores com alertas criticos?" |

### Como utilizar

1. Clicar no icone do DBA Copilot (presente no portal)
2. Digitar a pergunta em linguagem natural
3. O Copilot analisa a pergunta e responde com dados actuais
4. Os resultados incluem links directos para os servidores/tabs relevantes

### Nota tecnica

O DBA Copilot V3.2 e **rule-based** (baseado em regras), nao utiliza IA generativa. As perguntas sao mapeadas para queries pre-definidas sobre os dados da Intelligence DB. Funcionalidades de IA/ML estao previstas para versoes futuras (V5).

---

---

# 9. Seguranca

## 9.1. Autenticacao JWT

O WatcherDB V3.3 utiliza JSON Web Tokens (JWT) para autenticacao.

### Como funciona

```
1. Utilizador envia username + password
2. WatcherDB valida credenciais (Local ou AD)
3. Se valido, gera um JWT assinado com a SECRET_KEY
4. JWT e enviado ao browser e armazenado
5. Cada pedido subsequente inclui o JWT no header
6. WatcherDB valida o JWT em cada pedido
7. Quando o JWT expira, o utilizador precisa de reautenticar
```

### Estrutura do JWT

| Parte | Conteudo |
|-------|----------|
| Header | Algoritmo (HS256), tipo (JWT) |
| Payload | Username, role, emissao (iat), expiracao (exp) |
| Signature | Assinatura com SECRET_KEY |

### Seguranca do JWT

| Medida | Descricao |
|--------|-----------|
| SECRET_KEY | Chave unica e aleatoria para assinar tokens |
| Expiracao | Token expira apos o tempo configurado (60-1440 min) |
| Algoritmo | HS256 (HMAC com SHA-256) |
| Armazenamento | Token armazenado de forma segura no browser |

### Boas praticas

- Definir a SECRET_KEY como uma string aleatoria de pelo menos 64 caracteres
- Configurar a expiracao JWT para o minimo necessario (ex: 480 minutos para um dia de trabalho)
- Alterar a SECRET_KEY periodicamente (invalida todos os tokens existentes)
- Nunca partilhar ou expor a SECRET_KEY

---

## 9.2. Politica de Senhas

O WatcherDB V3.3 impoe uma politica de senhas robusta para utilizadores locais.

### Requisitos obrigatorios

| Requisito | Detalhe |
|-----------|---------|
| Comprimento | Minimo 8 caracteres |
| Maiusculas | Pelo menos 1 letra maiuscula (A-Z) |
| Minusculas | Pelo menos 1 letra minuscula (a-z) |
| Numeros | Pelo menos 1 digito (0-9) |
| Simbolos | Pelo menos 1 caracter especial |

### Exemplos

| Senha | Valida | Motivo |
|-------|--------|--------|
| `W4tch3r@DB` | Sim | Cumpre todos os requisitos |
| `MinhaSenha1!` | Sim | Cumpre todos os requisitos |
| `password` | Nao | Sem maiuscula, numero ou simbolo |
| `Password1` | Nao | Sem simbolo |
| `Ab1!` | Nao | Menos de 8 caracteres |

### Senhas de utilizadores AD

Utilizadores Active Directory nao sao afectados pela politica de senhas do WatcherDB. A gestao de senhas AD e feita pelo Active Directory segundo as politicas GPO do dominio.

---

## 9.3. Bloqueio de Conta

O WatcherDB implementa bloqueio automatico de conta apos tentativas de login falhadas.

### Configuracao

| Parametro | Opcoes | Por defeito |
|-----------|--------|-------------|
| Tentativas maximas | 3, 5, 10 | 5 |
| Tempo de bloqueio | 5, 10, 15, 30, 60 minutos | 15 minutos |

### Comportamento

1. Utilizador falha o login N vezes consecutivas
2. A conta e bloqueada automaticamente
3. O evento e registado no Auth Log
4. Apos o tempo de lockout, a conta e desbloqueada automaticamente
5. O contador de tentativas falhadas e reiniciado

### Desbloqueio manual

Um administrador pode desbloquear uma conta antes do tempo de lockout expirar:

1. Aceder ao **Painel de Controlo** → **Gestao de Utilizadores**
2. Encontrar o utilizador bloqueado (indicado como **Locked**)
3. Clicar em **Desbloquear**

### Nota sobre utilizadores AD

O bloqueio de conta no WatcherDB e independente do bloqueio no Active Directory. Um utilizador AD pode estar bloqueado no WatcherDB mas nao no AD (e vice-versa).

---

## 9.4. Roles e Permissoes

O WatcherDB V3.3 utiliza um sistema de roles para controlar o acesso.

### Tabela de permissoes detalhada

| Funcionalidade | viewer | analyst | operator | admin |
|----------------|--------|---------|----------|-------|
| Ver KPIs | Sim | Sim | Sim | Sim |
| Ver Tabs de Servidor | Sim | Sim | Sim | Sim |
| Pesquisar Servidores | Sim | Sim | Sim | Sim |
| Alterar idioma/tema | Sim | Sim | Sim | Sim |
| Exportar PDF | Nao | Sim | Sim | Sim |
| DBA Copilot | Nao | Sim | Sim | Sim |
| Network Diagnostics | Nao | Nao | Sim | Sim |
| Painel de Controlo | Nao | Nao | Sim | Sim |
| Gestao de utilizadores | Nao | Nao | Parcial | Sim |
| Configuracoes sistema | Nao | Nao | Nao | Sim |
| Gestao AD | Nao | Nao | Nao | Sim |

### Operadores vs Administradores

| Accao | operator | admin |
|-------|----------|-------|
| Ver utilizadores | Sim | Sim |
| Criar utilizador local | Sim | Sim |
| Criar utilizador AD | Nao | Sim |
| Editar role para admin | Nao | Sim |
| Eliminar utilizadores | Nao | Sim |
| Alterar configuracoes JWT | Nao | Sim |
| Alterar configuracoes AD | Nao | Sim |
| Alterar politica de senhas | Nao | Sim |

---

---

# 10. Administracao do Servico

## 10.1. Gestao do Windows Service

### Verificar estado

```powershell
# Ver estado do servico
Get-Service "WatcherDB*"

# Output esperado:
# Status   Name               DisplayName
# ------   ----               -----------
# Running  WatcherDB V3.3     WatcherDB V3.3 - SQL Server Monitor
```

### Operacoes basicas

```powershell
# Iniciar o servico
Start-Service "WatcherDB V3.3"

# Parar o servico
Stop-Service "WatcherDB V3.3"

# Reiniciar o servico
Restart-Service "WatcherDB V3.3"
```

### Verificar porta

```powershell
# Verificar se a porta 8433 esta a escutar
netstat -an | findstr "8433"

# Output esperado:
#   TCP    0.0.0.0:8433    0.0.0.0:0    LISTENING
```

### Script de reinicio

O WatcherDB inclui um script PowerShell para reiniciar o servidor:

```powershell
# Utilizar o script incluido
.\reiniciar_servidor.ps1
```

---

## 10.2. Logs do Sistema

Os logs do WatcherDB estao localizados em:

```
C:\WatcherDB\services\web_service\logs\
```

### Ficheiros de log

| Ficheiro | Conteudo |
|----------|----------|
| `watcherdb.log` | Log principal do portal |
| `service_health.txt` | Estado de saude do servico |

### Niveis de log

| Nivel | Descricao |
|-------|-----------|
| DEBUG | Informacao detalhada para debugging |
| INFO | Eventos normais de operacao |
| WARNING | Situacoes anormais que nao impedem operacao |
| ERROR | Erros que afectam funcionalidade |
| CRITICAL | Erros graves que podem causar paragem |

### Configurar nivel de log

No ficheiro `.env`:

```ini
# Para operacao normal
LOG_LEVEL=INFO

# Para diagnostico de problemas
LOG_LEVEL=DEBUG

# Para producao (apenas avisos e erros)
LOG_LEVEL=WARNING
```

### Rotacao de logs

Os logs sao automaticamente rodados para evitar crescimento excessivo:

- Rotacao por tamanho (quando atinge um limite configurado)
- Retencao de N ficheiros historicos
- Formato: `watcherdb.log`, `watcherdb.log.1`, `watcherdb.log.2`, etc.

### Ver logs em tempo real

```powershell
# Ver as ultimas 50 linhas e acompanhar novas entradas
Get-Content "C:\WatcherDB\services\web_service\logs\watcherdb.log" -Tail 50 -Wait
```

---

## 10.3. Conta de Servico

A conta sob a qual o servico WatcherDB corre e critica para o seu funcionamento.

### Requisitos da conta

| Requisito | Motivo |
|-----------|--------|
| Conta de dominio | Necessaria para Windows Authentication aos SQL Servers |
| Log on as a service | Permissao Windows para correr como servico |
| VIEW SERVER STATE | Permissao SQL Server em cada instancia monitorizada |
| Acesso de rede | Conseguir atingir todos os SQL Servers e Domain Controllers |

### Configurar a conta de servico

1. Abrir `services.msc`
2. Encontrar **WatcherDB V3.3**
3. **Properties** → separador **Log On**
4. Seleccionar **This account**
5. Introduzir `DOMINIO\svc_watcherdb`
6. Introduzir a senha
7. Clicar **OK**

### Verificar permissoes SQL Server

Executar em cada SQL Server monitorizado:

```sql
-- Verificar se a conta de servico tem VIEW SERVER STATE
SELECT 
    p.name AS login_name,
    pe.permission_name,
    pe.state_desc
FROM sys.server_permissions pe
JOIN sys.server_principals p ON pe.grantee_principal_id = p.principal_id
WHERE p.name = 'DOMINIO\svc_watcherdb'
    AND pe.permission_name = 'VIEW SERVER STATE';
```

Se nao tiver a permissao:

```sql
-- Conceder permissao
GRANT VIEW SERVER STATE TO [DOMINIO\svc_watcherdb];
```

### Verificar Log on as a service

```powershell
# Verificar politica local
secedit /export /cfg C:\temp\secpol.cfg
Select-String "SeServiceLogonRight" C:\temp\secpol.cfg
```

---

## 10.4. Backup da Configuracao

### O que fazer backup

| Componente | Localizacao | Importancia |
|------------|-------------|-------------|
| Ficheiro .env | `C:\WatcherDB\.env` | Configuracoes do ambiente |
| Base de dados Intelligence | SQL Server | Dados historicos e configuracoes |
| Certificados (se HTTPS) | `C:\WatcherDB\certs\` | Necessarios para HTTPS |

### Backup da base de dados Intelligence

```sql
-- Backup FULL da Intelligence DB
BACKUP DATABASE [WatcherDB_Intelligence]
TO DISK = N'C:\Backups\WatcherDB_Intelligence_FULL.bak'
WITH COMPRESSION, INIT, STATS = 10;
```

### Backup do ficheiro .env

```powershell
# Copiar .env para localizacao segura
Copy-Item "C:\WatcherDB\.env" "C:\Backups\WatcherDB\.env.$(Get-Date -Format 'yyyyMMdd')"
```

### Restauro

Em caso de necessidade de restauro:

1. Restaurar a base de dados Intelligence
2. Copiar o ficheiro `.env` de volta
3. Reinstalar o servico se necessario
4. Iniciar o servico

---

---

# 11. Resolucao de Problemas

## 11.1. Problemas de Arranque

### Servico nao arranca

**Sintoma:** O servico WatcherDB V3.3 nao inicia ou para imediatamente apos iniciar.

**Diagnostico:**

```powershell
# 1. Verificar estado do servico
Get-Service "WatcherDB*"

# 2. Verificar logs
Get-Content "C:\WatcherDB\services\web_service\logs\watcherdb.log" -Tail 50

# 3. Verificar se a porta esta ocupada
netstat -an | findstr "8433"

# 4. Verificar Event Viewer
Get-EventLog -LogName System -Source "Service Control Manager" -Newest 10
```

**Causas comuns e solucoes:**

| Causa | Solucao |
|-------|---------|
| Porta 8433 ja em uso | Parar o processo que esta a usar a porta ou alterar a porta no .env |
| Ficheiro .env em falta ou corrompido | Verificar e corrigir o ficheiro .env |
| Dependencias Python em falta | Executar `pip install -r requirements.txt` |
| Conta de servico sem permissao | Verificar `Log on as a service` no services.msc |
| Erro de sintaxe na configuracao | Verificar logs para mensagem de erro especifica |
| Base de dados Intelligence inacessivel | Verificar conexao SQL Server |

### Porta ocupada

```powershell
# Encontrar o processo que esta a usar a porta 8433
netstat -ano | findstr "8433"

# O ultimo numero e o PID. Para ver o processo:
Get-Process -Id <PID>

# Para terminar o processo (com cautela):
Stop-Process -Id <PID> -Force
```

---

## 11.2. Problemas de Autenticacao

### Login falha com credenciais correctas

**Diagnostico:**

1. Verificar o **Auth Log** no Painel de Controlo para o motivo exacto da falha
2. Verificar se a conta esta bloqueada (lockout)
3. Para utilizadores AD, verificar se o dominio esta acessivel

**Causas comuns:**

| Causa | Solucao |
|-------|---------|
| Conta bloqueada (lockout) | Esperar o tempo de lockout ou desbloquear no Painel |
| Senha expirada (AD) | Alterar a senha no Active Directory |
| Dominio AD inacessivel | Verificar rede e DNS |
| must_change_password activo | O utilizador deve alterar a senha no login |
| JWT expirado | Fazer logout e login novamente |

### Login AD falha

```powershell
# 1. Verificar se o DC responde
Test-Connection dc01.dominio.local -Count 2

# 2. Verificar DNS SRV
nslookup -type=SRV _ldap._tcp.dominio.local

# 3. Verificar porta LDAP
Test-NetConnection dc01.dominio.local -Port 389

# 4. Verificar ticket Kerberos
klist
```

### Conta de servico do WatcherDB

Se o login falha para todos os utilizadores AD:

1. Abrir `services.msc`
2. Verificar a conta no separador **Log On** do servico WatcherDB
3. Verificar se a senha da conta nao expirou
4. Testar a conta manualmente:
   ```powershell
   runas /user:DOMINIO\svc_watcherdb "cmd /c echo Login OK"
   ```

---

## 11.3. Problemas de Colecta de Dados

### KPIs vazios ou desactualizados

**Sintoma:** O dashboard mostra KPIs sem dados ou com dados antigos.

**Diagnostico:**

```powershell
# 1. Verificar se o Collector Service esta a correr
Get-Service "WatcherDB*Intelligence*"

# 2. Verificar conexao a Intelligence DB
sqlcmd -S servidor-sql -d WatcherDB_Intelligence -Q "SELECT TOP 1 * FROM dbo.kpi_collection_log ORDER BY collection_time DESC"

# 3. Verificar logs do Collector
Get-Content "C:\WatcherDB\services\collector\logs\*.log" -Tail 50
```

**Causas comuns:**

| Causa | Solucao |
|-------|---------|
| Collector Service parado | Iniciar o servico do Collector |
| Intelligence DB inacessivel | Verificar conexao SQL Server |
| Conta de servico sem permissoes | Verificar VIEW SERVER STATE nos SQL Servers |
| SQL Server monitorizado offline | Verificar se o servidor destino esta online |
| Rede entre Collector e SQL Servers | Verificar conectividade (ping, porta 1433) |

### Verificar ultimas colectas

```sql
-- Na Intelligence DB
SELECT TOP 20
    server_name,
    kpi_category,
    collection_time,
    duration_ms,
    status
FROM dbo.kpi_collection_log
ORDER BY collection_time DESC;
```

---

## 11.4. Problemas de Performance

### Portal lento

**Sintoma:** O portal web responde lentamente ou as paginas demoram a carregar.

**Diagnostico:**

1. Verificar o **Resource Monitor** no Painel de Controlo
2. Analisar a carga do servidor

**Causas comuns e solucoes:**

| Causa | Indicador | Solucao |
|-------|-----------|---------|
| CPU elevada do WatcherDB | CPU processo > 80% no Resource Monitor | Verificar queries pesadas, aumentar workers |
| RAM insuficiente | RAM > 90% utilizada | Adicionar RAM ou optimizar |
| Disco lento | I/O wait elevado | Verificar disco, considerar SSD |
| Muitos utilizadores simultaneos | Muitas sessoes activas | Aumentar workers no .env |
| Intelligence DB lenta | Colectas com duracao elevada | Optimizar indices na Intelligence DB |
| Rede lenta | Latencia elevada no Network Diagnostics | Verificar infraestrutura de rede |

### Optimizacao de performance

```ini
# No ficheiro .env, aumentar workers
WORKERS=8  # por defeito 4, aumentar se necessario

# Ou no ficheiro .env, ajustar logging
LOG_LEVEL=WARNING  # reduzir logging em producao
```

---

## 11.5. Problemas de Conectividade

### Servidor SQL nao acessivel

```powershell
# 1. Ping ao servidor
Test-Connection sql-server-01 -Count 4

# 2. Verificar porta SQL Server
Test-NetConnection sql-server-01 -Port 1433

# 3. Verificar DNS
nslookup sql-server-01

# 4. Testar conexao ODBC
sqlcmd -S sql-server-01 -E -Q "SELECT @@SERVERNAME, @@VERSION"
```

### Firewall

Verificar se as portas necessarias estao abertas:

```powershell
# Verificar regras de firewall
Get-NetFirewallRule | Where-Object {$_.DisplayName -like "*SQL*" -or $_.DisplayName -like "*WatcherDB*"}
```

Portas que devem estar abertas:

| Porta | Direccao | Proposito |
|-------|----------|-----------|
| 8433 | Entrada | Portal Web WatcherDB |
| 1433 | Saida | Conexao a SQL Servers |
| 389 | Saida | LDAP para Active Directory |
| 636 | Saida | LDAPS (AD seguro) |
| 88 | Saida | Kerberos |
| 53 | Saida | DNS |

---

## 11.6. Problemas com Active Directory

### Pesquisa LDAP nao retorna resultados

**Causas comuns:**

| Causa | Solucao |
|-------|---------|
| Base DN incorrecta | Verificar o Distinguished Name base (DC=dominio,DC=local) |
| Conta de servico sem permissoes LDAP | Verificar permissoes da conta no AD |
| Firewall a bloquear porta 389/636 | Verificar regras de firewall |
| DC indisponivel | Verificar se o Domain Controller responde |
| DNS SRV nao configurado | Verificar registos DNS SRV ou configurar DC manualmente |

### Testar ligacao LDAP manualmente

```powershell
# Testar com ldapsearch (se disponivel)
# Ou testar no PowerShell:
$domain = "dominio.local"
$searcher = New-Object System.DirectoryServices.DirectorySearcher
$searcher.SearchRoot = "LDAP://DC=$($domain.Replace('.',',DC='))"
$searcher.Filter = "(sAMAccountName=joao.silva)"
$results = $searcher.FindAll()
$results.Count
```

### Kerberos nao funciona

```powershell
# Verificar tickets Kerberos actuais
klist

# Limpar tickets e obter novos
klist purge
```

Se o WatcherDB corre como servico, o ticket Kerberos da conta de servico e utilizado automaticamente. Verificar que a conta de servico e uma conta de dominio valida.

---

## 11.7. Problemas com o Portal Web

### Pagina em branco ou parcialmente carregada

**Solucoes:**

1. **Hard refresh:** Pressionar `Ctrl+Shift+R` para forcar recarregamento completo
2. **Limpar cache:** Limpar cache do browser
3. **Outro browser:** Testar com outro browser para isolar o problema
4. **Console do browser:** Abrir F12 → Console para ver erros JavaScript

### Sessao perdida apos navegar

O WatcherDB utiliza localStorage para isolamento de sessao por utilizador. Se a sessao se perde:

1. Verificar se o JWT nao expirou
2. Verificar se nao ha problemas de armazenamento no browser
3. Limpar o localStorage e fazer login novamente:
   - F12 → Application → Local Storage → Limpar

### Interface nao traduzida

Se alguma parte da interface nao muda de idioma:

1. Fazer hard refresh (`Ctrl+Shift+R`)
2. Alterar o idioma novamente
3. Verificar a consola do browser para erros

---

---

# 12. FAQ - Perguntas Frequentes

### 1. Quantos servidores SQL Server posso monitorizar com o WatcherDB?

O WatcherDB V3.3 foi concebido para monitorizar **100+ instancias SQL Server** a partir de um unico portal. O limite pratico depende dos recursos do servidor onde o WatcherDB esta instalado. Com os requisitos recomendados (8 cores, 16 GB RAM), e possivel monitorizar confortavelmente 150-200 instancias.

---

### 2. O WatcherDB funciona com SQL Server Express?

Sim, o WatcherDB pode monitorizar instancias **SQL Server Express**. No entanto, como o SQL Server Express nao inclui o SQL Server Agent, o tab de **Jobs** mostrara dados vazios para essas instancias. Todas as outras funcionalidades (espaco, backup, CPU, memoria, etc.) funcionam normalmente.

---

### 3. Preciso do Collector Service para o portal funcionar?

Sim e nao. O portal (V3.2) pode arrancar e funcionar sem o Collector Service, mas os **KPIs no dashboard** estarao vazios ou desactualizados, pois sao colectados pelo Collector Service e armazenados na Intelligence DB. Os dados que o portal le em tempo real directamente dos SQL Servers (como tabs de CPU, Memory, etc.) continuarao a funcionar.

---

### 4. Como adiciono um novo SQL Server a monitorizacao?

A adicao de novos servidores e feita na base de dados **WatcherDB_Intelligence**. Consulte o guia de administracao da Intelligence DB ou utilize os scripts disponibilizados na pasta `deploy/` para registar novas instancias. Apos registar, o Collector comeca a recolher dados automaticamente e o servidor aparece no dashboard.

---

### 5. O WatcherDB suporta HTTPS?

O WatcherDB V3.3 pode ser configurado para HTTPS. Para isso, e necessario:

1. Obter um certificado SSL (auto-assinado ou de uma CA)
2. Configurar o caminho do certificado e chave no ficheiro `.env`
3. Reiniciar o servico

Em alternativa, pode utilizar um reverse proxy (IIS, nginx) em frente ao WatcherDB para terminar SSL.

---

### 6. Posso ter multiplos utilizadores com a role admin?

Sim, nao ha limite no numero de administradores. No entanto, por boas praticas de seguranca, recomenda-se:

- Manter o numero minimo de contas admin necessarias
- Utilizar contas nominativas (nao partilhadas)
- Registar quem tem acesso admin e rever periodicamente

---

### 7. O que acontece quando o JWT expira durante uma sessao activa?

Quando o token JWT expira:

1. O proximo pedido ao servidor sera rejeitado com erro de autenticacao
2. O portal redireciona automaticamente para a pagina de login
3. O utilizador precisa de fazer login novamente
4. Nao ha perda de dados; o utilizador simplesmente reautentica

Para evitar expiracoes frequentes durante o horario de trabalho, configure o JWT Expiration para pelo menos 480 minutos (8 horas).

---

### 8. O WatcherDB afecta a performance dos SQL Servers monitorizados?

O impacto e **minimo**. O WatcherDB utiliza:

- **DMVs de sistema** (Dynamic Management Views) que sao queries leves
- **READ UNCOMMITTED** isolation level para nao causar bloqueios
- **Intervalos de colecta configurados** para nao sobrecarregar os servidores
- A permissao `VIEW SERVER STATE` nao permite alteracoes nos servidores

O overhead tipico e inferior a 1% de CPU em cada SQL Server monitorizado.

---

### 9. Posso correr o WatcherDB em Docker?

O projecto inclui `Dockerfile` e `docker-compose.yml` para execucao em container. No entanto, a versao principal e optimizada para **Windows Service** devido a dependencia de Windows Authentication (ODBC com Trusted Connection) para aceder aos SQL Servers. A execucao em Docker pode requerer configuracoes adicionais de Kerberos.

---

### 10. Como faco upgrade de uma versao anterior para a V3.2?

O processo de upgrade tipico e:

1. **Backup:** Fazer backup da base de dados Intelligence e do ficheiro `.env`
2. **Parar o servico:** `Stop-Service "WatcherDB V3.3"`
3. **Substituir ficheiros:** Copiar os novos ficheiros para `C:\WatcherDB\` (preservando o `.env`)
4. **Actualizar dependencias:** `pip install -r requirements.txt`
5. **Migracoes de BD:** Executar `alembic upgrade head` se houver migracoes de base de dados
6. **Iniciar o servico:** `Start-Service "WatcherDB V3.3"`
7. **Verificar:** Aceder ao portal e verificar que tudo funciona

Consulte o `CHANGELOG` na pasta `docs/changelog/` para notas de cada versao.

---

---

# 13. Glossario

| Termo | Definicao |
|-------|-----------|
| **AG** | Availability Group - grupo de alta disponibilidade do SQL Server |
| **Always On** | Tecnologia de alta disponibilidade do SQL Server baseada em AGs |
| **Base DN** | Distinguished Name base para pesquisas LDAP no Active Directory |
| **Buffer Cache** | Area de memoria onde o SQL Server armazena paginas de dados lidas do disco |
| **Collector Service** | Componente que recolhe metricas dos SQL Servers periodicamente |
| **CRITICAL** | Estado de alerta maximo que requer accao imediata |
| **Dashboard** | Pagina principal com visao consolidada dos KPIs |
| **DC** | Domain Controller - servidor que gere o Active Directory |
| **DIFF** | Backup Diferencial - backup apenas das alteracoes desde o ultimo FULL |
| **DMV** | Dynamic Management View - vista de sistema do SQL Server para monitorizar metricas |
| **DNS SRV** | Registo DNS que permite descobrir servicos (como DCs) automaticamente |
| **Failover** | Transferencia automatica ou manual de operacao entre replicas |
| **Filegroup** | Agrupamento logico de ficheiros de dados no SQL Server |
| **FULL** | Backup completa de toda a base de dados |
| **GSSAPI** | Generic Security Services API - interface para autenticacao Kerberos |
| **Health Score** | Pontuacao de 0 a 100 que reflecte a saude geral de um servidor |
| **Heartbeat** | Sinal periodico enviado pelo browser para indicar que o utilizador esta activo |
| **HTMX** | Biblioteca JavaScript para interacoes dinamicas com o servidor |
| **Intelligence DB** | Base de dados WatcherDB_Intelligence que armazena metricas colectadas |
| **JWT** | JSON Web Token - mecanismo de autenticacao baseado em tokens |
| **Kerberos** | Protocolo de autenticacao utilizado pelo Active Directory |
| **KPI** | Key Performance Indicator - indicador chave de performance |
| **LDAP** | Lightweight Directory Access Protocol - protocolo para aceder ao AD |
| **LDAPS** | LDAP sobre SSL/TLS (porta 636) |
| **Lockout** | Bloqueio temporario de conta apos tentativas de login falhadas |
| **LOG** | Backup do transaction log |
| **ODBC** | Open Database Connectivity - interface para aceder a bases de dados |
| **OK** | Estado normal, sem problemas |
| **PLE** | Page Life Expectancy - tempo medio de uma pagina no buffer cache |
| **Replica** | Copia de um Availability Group num servidor secundario |
| **RPO** | Recovery Point Objective - ponto maximo de perda de dados toleravel |
| **RTO** | Recovery Time Objective - tempo maximo para recuperacao |
| **Shrink** | Operacao que reduz o tamanho de ficheiros de base de dados |
| **SPID** | Server Process ID - identificador de sessao no SQL Server |
| **TDE** | Transparent Data Encryption - encriptacao transparente de dados |
| **UPN** | User Principal Name - nome de utilizador no formato user@dominio |
| **WARNING** | Estado de alerta que requer atencao mas nao e urgente |

---

---

# 14. Referencia Rapida

## URLs Principais

| URL | Funcao |
|-----|--------|
| `https://servidor:8433/watcherdb/` | Portal principal (Dashboard) |
| `https://servidor:8433/watcherdb/control` | Painel de Controlo |

## Atalhos de Teclado

| Atalho | Funcao |
|--------|--------|
| `Ctrl+Shift+R` | Hard refresh (recarrega pagina, abre nos KPIs) |
| `Ctrl+F` | Focar na barra de pesquisa |
| `Esc` | Fechar modais e menus |

## Portas

| Porta | Servico |
|-------|---------|
| 8433 | Portal Web WatcherDB V3.3 |
| 8001 | Collector Service |
| 1433 | SQL Server (por defeito) |
| 389 | LDAP |
| 636 | LDAPS |
| 88 | Kerberos |

## Comandos PowerShell Uteis

```powershell
# Estado do servico
Get-Service "WatcherDB*"

# Reiniciar servico
Restart-Service "WatcherDB V3.3"

# Verificar porta
netstat -an | findstr "8433"

# Ver logs (ultimas 50 linhas)
Get-Content "C:\WatcherDB\services\web_service\logs\watcherdb.log" -Tail 50

# Verificar ODBC drivers
Get-OdbcDriver | Where-Object {$_.Name -like "*SQL Server*"}

# Testar conexao a SQL Server
Test-NetConnection sql-server-01 -Port 1433

# Verificar DNS SRV
nslookup -type=SRV _ldap._tcp.dominio.local
```

## Credenciais por Defeito

| Campo | Valor |
|-------|-------|
| Username | `admin` |
| Password | `admin123` |

> **ALTERAR IMEDIATAMENTE apos o primeiro login.**

## Requisitos Minimos

| Recurso | Valor |
|---------|-------|
| OS | Windows Server 2016+ |
| Python | 3.11+ |
| ODBC | Driver 17 ou 18 |
| SQL Server | 2016+ |
| RAM | 8 GB |
| CPU | 4 cores |

## Localizacao de Ficheiros

| Ficheiro | Caminho |
|----------|---------|
| Configuracao | `C:\ProgramData\WatcherDB\.env` |
| Logs | `C:\ProgramData\WatcherDB\logs\` |
| Licenca | `C:\ProgramData\WatcherDB\license.dat` |
| Deploy scripts | `C:\Program Files\WatcherDB\V3.3\deploy\` |
| Binarios + runtime | `C:\Program Files\WatcherDB\V3.3\` |

---

# Anexo A. Security & Compliance Posture (para IT Director / CISO)

Esta seccao e destinada ao decisor IT/CISO que avalia WatcherDB para ambiente regulado. Para detalhe operacional da gestao de seguranca no dia-a-dia, ver [Seccao 9. Seguranca].

## A.1. Cadeia de distribuicao

| Item | Estado V3.3 |
|------|-------------|
| Instalador MSI Authenticode-signed | Sim (EV KeyLocker, timestamp RFC 3161 SHA-256) |
| SBOM CycloneDX JSON publicado com cada release | Sim (gerado por Syft sobre o bundle PyInstaller) |
| Update-package signed manifest | Sim (Ed25519, `min_version` gate impede downgrade) |
| Codigo Python ofuscado | Sim (PyArmor Pro, licenca registada reg 11618) |
| Dependencias com CVE scan automatizado | Parcial (pip-audit/Safety em pre-commit; enforcement em CI a caminho) |
| Phone-home / telemetria cloud | **Nao** (zero egress para fora do perimetro do cliente) |

## A.2. Arquitectura de auth

- **Modo 1 — Local:** utilizadores locais em BD (bcrypt hashing, cost 12), password policy configuravel via `/admin/session-policy`.
- **Modo 2 — AD hybrid:** bind LDAPS contra domain controller do cliente (configurado pelo cliente em `config.yaml`). Auto-discovery DNS SRV, pesquisa LDAP, bind Kerberos onde disponivel.
- **Break-glass:** conta `admin` local mantida mesmo quando AD e autoritativo, para recover de AD outage.
- **Session:** JWT (HS256 por defeito; passar para RS256 recomendado para banking — ver A.6), token blacklist DB-backed, cookie `HttpOnly + Secure + SameSite=Lax`.
- **Rate-limiting:** `/login` limitado a 5 tentativas/minuto por IP (slowapi); outros endpoints de mutacao devem ser rate-limited num proximo sprint.

## A.3. RBAC

Roles suportados: `admin` (gestao completa), `operator` (acoes restritas), `viewer` (leitura). Granularidade por recurso (por exemplo, permitir viewer em instancia X mas nao em Y) esta planeada para V3.3 Sem 5.

## A.4. Secrets management

- `JWT_SECRET_KEY` encriptada com Fernet, master key protegida por DPAPI do Windows (scope User, service account dedicada).
- `INTELLIGENCE_SQL_PASSWORD` em DPAPI-wrapped format dentro do `.env`.
- Nenhum secret em plaintext no `.env` distribuido.
- **Procedimento de rotacao:** ver [Seccao 9.6 — Rotacao de chaves].

## A.5. Audit log

Tabela `WatcherDB_Auth_Log` regista login, logout, falha de auth, lockout, criacao/alteracao/remocao de utilizador, alteracoes de role. Retencao recomendada para banking: 1 ano on-premise + export para SIEM corporativo (sintaxe CEF ou JSON via endpoint de export).

Audit trail cobre:
- Autenticacao e sessao (completo)
- Admin mutations (completo)
- Acesso a dados de monitorizacao por recurso (parcial — enhancement planeado para Sem 5)

## A.6. Recomendacoes de hardening para cliente banking

1. **Configurar TLS** com certificado da CA interna (nao self-signed) na porta 8433. Ver [Seccao 10.5 — Configurar TLS].
2. **Passar JWT para RS256** + KMS/HSM do cliente para custodia da chave privada, se disponivel.
3. **Dedicar service account AD** com "Log on as a service" right e zero permissoes adicionais no host (nao LocalSystem, nao NetworkService com privilegios desnecessarios).
4. **Limitar SQL login** da ferramenta a `db_datareader` + `VIEW SERVER STATE` + `VIEW DATABASE STATE` — nunca sysadmin.
5. **Firewall inbound:** porta 8433 acessivel apenas a IPs internos autorizados. Nao expor a Internet.
6. **Retencao de audit log:** configurar export diario para SIEM corporativo (Splunk, ELK, QRadar) para preservar trail alem da retencao local.

## A.7. Compliance alignment

| Framework | Controles relevantes | Status V3.3 |
|-----------|---------------------|-------------|
| **SOC 2 Type II** | CC6.1 (logical access), CC6.8 (audit), CC7 (system monitoring) | Compatible pos-hardening A.6 |
| **ISO 27001:2022** | A.9 (access control), A.12.4 (logging), A.14.2 (secure development) | Compatible |
| **PCI-DSS v4** (se aplicavel) | Req 7 (access control), Req 8 (authentication), Req 10 (logging) | Compatible pos-hardening A.6 |
| **DORA** (banking EU) | Art. 9 (access + audit), Art. 16 (SBOM / supply chain) | Compatible (SBOM ja shipado) |

---

# Anexo B. Upgrade Path WatcherDB Pro

Quando a equipa estiver pronta para automacao avancada de diagnostico, os seguintes capabilities estao disponiveis em WatcherDB Pro (V5/V5.5) como upgrade de installer:

- **AI Pipeline canonical** — 20-step `ask()` com 14 Expert Agents, RAG cognitivo, Knowledge Graph, SHAP explainability
- **Anomaly Detection Engine** — deteccao automatica de padroes anomalos em CPU, memoria, I/O, wait stats
- **Autonomous Agent** — investigacao automatizada multi-step com raciocinio
- **Health Score Engine** — scoring composto por instancia com ML
- **Capacity Planning** — previsao de crescimento de dados, disco, memoria com horizonte configuravel
- **Executive Reports** — relatorio pronto para CIO com anomaly detection + recomendacoes
- **Sovereign AI (Pro Enhanced)** — Ollama local + QLoRA fine-tuned, zero egress para cloud
- **Tribunal de Agentes (V5.5)** — multi-agent debate com red-team / socratic / temporal specialists para decisoes complexas

Upgrade path: ver [documento de produto Pro]. Sem migracao de dados, sem reinstalacao — o installer Pro reconhece a configuracao Standard existente e activa os modulos adicionais.

---

# Anexo C. Historico de versoes

| Versao | Data | Destaques |
|--------|------|-----------|
| 3.3 | Abril 2026 | Standard Edition comercial. MSI signed, SBOM, update-package signed, PyArmor Pro. Porta 8433, servico `WatcherDBWebServiceV33`. |
| 3.2 | Marco 2026 | Pre-Standard. Porta 8449 (legacy). |
| 3.1 | Janeiro 2026 | Baseline interno TAP. |

---

**WatcherDB V3.3 Standard Edition** — Plataforma de Monitorizacao SQL Server Banking-Grade

Para suporte comercial, licenciamento e upgrade path Pro, contactar o vendor.

Documento publicado em 22 de Abril de 2026. Revisao apos audit paralelo de 8 specialists do WatcherDB Council.
