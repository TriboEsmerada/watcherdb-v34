# PROMPT: WatcherDB Web Service - Acesso Remoto via Browser






---

# CONTEXTO DO PROJETO

## Estrutura Existente

Existem **dois projetos relacionados** em diretórios diferentes:

### 1. WATCHERDB INTELLIGENCE V1 (Collector Service)
```
C:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1\
│
├── services/                          
│   └── collector_service/             # ✅ Serviço de coleta (já funciona)
│       ├── service.py                 # Windows Service (800+ linhas)
│       ├── collectors_base.py         # Framework (300+ linhas)
│       ├── config.yaml                
│       ├── install.py                 
│       └── ...
│
└── [resto do projeto Intelligence]
```

### 2. WATCHERDB_DEV (Web Service) ← FOCO DESTE PROMPT
```
C:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV\
│
├── watcherdb_main.py                  # FastAPI principal (7.9K linhas) ✅
├── watcherdb_intelligence.py          # Intelligence module (7.6K linhas)
├── api/                               # 15+ routers, 50+ endpoints
├── modules/                           # 22 módulos de monitoramento
├── templates/                         # HTML (portal, dashboards)
├── static/                            # JS, CSS, assets
├── config/                            # servers.json, sql_servers.json
└── database/                          # 20 SQL scripts, stored procs
```

## Collector Service - Comandos de Referência

```powershell
# Navegação (outro projeto)
cd "C:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1\services\collector_service"

# Comandos (padrão a seguir para o web_service)
python install.py install     # Instalar
python install.py start       # Iniciar
python install.py stop        # Parar
python install.py restart     # Reiniciar
python install.py status      # Status
python install.py validate    # Validar config
python install.py remove      # Remover

# Logs
Get-Content logs\service.log -Wait -Tail 20
```

---

# OBJETIVO

Criar um **segundo Windows Service** chamado `web_service` que:

1. **Exponha o WatcherDB via HTTP/HTTPS** para acesso remoto via browser
2. **Siga exatamente a mesma estrutura** do `collector_service`
3. **Execute o FastAPI/Uvicorn** como Windows Service
4. **Implemente autenticação** para controle de acesso
5. **Seja independente** do collector_service (podem rodar juntos ou separados)
6. **Mantenha consistência** nos comandos (`install.py install/start/stop/etc`)

---

# ESTRUTURA ESPERADA (WATCHERDB_DEV com Web Service)

```
C:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV\
│
├── watcherdb_main.py                  # FastAPI app (já existe) ✅
├── watcherdb_intelligence.py          # Intelligence module ✅
├── api/                               # Routers existentes ✅
├── modules/                           # Módulos existentes ✅
├── templates/                         # HTML existente ✅
├── static/                            # Assets existentes ✅
├── config/                            # Config existente ✅
├── database/                          # SQL scripts existentes ✅
│
└── services/                          # 🆕 NOVO DIRETÓRIO
    └── web_service/                   # 🆕 SERVIÇO WEB A CRIAR
        ├── __init__.py                # Package marker
        ├── service.py                 # Windows Service (Uvicorn wrapper)
        ├── server.py                  # FastAPI bootstrap (importa watcherdb_main)
        ├── config.yaml                # Configuração do web service
        ├── install.py                 # Gerenciamento (mesmo padrão collector)
        ├── requirements.txt           # Dependências específicas
        ├── install_and_start.bat      # Quick install
        │
        ├── README.md                  # Overview rápido
        ├── CHANGELOG.md               # Histórico de mudanças
        │
        ├── auth/                      # Módulo de autenticação
        │   ├── __init__.py
        │   ├── middleware.py          # FastAPI middleware
        │   ├── jwt_handler.py         # Tokens JWT
        │   ├── windows_auth.py        # AD integration (opcional)
        │   ├── models.py              # User, Session, Role
        │   └── routes.py              # /login, /logout, /me
        │
        ├── security/                  # Segurança
        │   ├── __init__.py
        │   ├── cors.py                # CORS config
        │   ├── rate_limiter.py        # Rate limiting
        │   ├── headers.py             # Security headers
        │   └── audit.py               # Logging de auditoria
        │
        ├── certs/                     # Certificados SSL (gitignore)
        │   ├── .gitkeep
        │   └── README.md              # Instruções de geração
        │
        ├── scripts/                   # Scripts auxiliares
        │   ├── generate_certs.ps1     # Gerar cert auto-assinado
        │   ├── configure_firewall.ps1 # Abrir portas
        │   └── test_connection.ps1    # Testar conectividade
        │
        ├── docs/                      # Documentação
        │   ├── README.md              # Doc técnica completa
        │   ├── QUICKSTART.md          # Setup em 5 minutos
        │   ├── AUTHENTICATION.md      # Guia de autenticação
        │   ├── SECURITY.md            # Considerações de segurança
        │   └── TROUBLESHOOTING.md     # Resolução de problemas
        │
        └── logs/                      # (auto-criado em runtime)
            ├── access.log             # Acessos HTTP
            ├── service.log            # Logs do serviço
            └── errors.log             # Erros
```

---

# ARQUITETURA DE REDE

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              REDE CORPORATIVA                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                   │
│   │  DBA Workst. │     │  DBA Workst. │     │  DBA Workst. │                   │
│   │  (Browser)   │     │  (Browser)   │     │  (Browser)   │                   │
│   └──────┬───────┘     └──────┬───────┘     └──────┬───────┘                   │
│          │                    │                    │                           │
│          └────────────────────┼────────────────────┘                           │
│                               │                                                 │
│                    ┌──────────▼──────────┐                                     │
│                    │  https://10.x.x.x   │                                     │
│                    │     Port 8443       │                                     │
│                    └──────────┬──────────┘                                     │
│                               │                                                 │
│                    ┌──────────▼───────────────────────────────┐                │
│                    │           SERVER-WATCHERDB               │                │
│                    │                                          │                │
│                    │  ┌─────────────────────────────────────┐ │                │
│                    │  │  🌐 WatcherDB Web Service           │ │                │
│                    │  │  (WATCHERDB_DEV/services/web_service)│ │                │
│                    │  │  ├─ Uvicorn (0.0.0.0:8443)         │ │                │
│                    │  │  ├─ SSL/TLS                         │ │                │
│                    │  │  ├─ Auth Middleware                 │ │                │
│                    │  │  └─ Importa watcherdb_main.py       │ │                │
│                    │  └──────────────┬──────────────────────┘ │                │
│                    │                 │                        │                │
│                    │  ┌──────────────▼──────────────────────┐ │                │
│                    │  │  📡 WatcherDB Collector Service     │ │                │
│                    │  │  (INTELLIGENCE V1/.../collector)    │ │                │
│                    │  │  └─ Coleta em background            │ │                │
│                    │  └──────────────┬──────────────────────┘ │                │
│                    │                 │                        │                │
│                    │  ┌──────────────▼──────────────────────┐ │                │
│                    │  │  💾 SQL Server (WatcherDB)          │ │                │
│                    │  │  └─ Dados de monitoramento          │ │                │
│                    │  └─────────────────────────────────────┘ │                │
│                    └──────────────────────────────────────────┘                │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

# REQUISITOS TÉCNICOS

## 1. service.py - Windows Service

```python
"""
WatcherDB Web Service - Windows Service Wrapper

Executa o FastAPI/Uvicorn como Windows Service, permitindo:
- Acesso remoto via browser
- Execução sem usuário logado
- Start/Stop via services.msc
"""

import win32serviceutil
import win32service
import win32event
import servicemanager
import uvicorn
import threading
import sys
from pathlib import Path

class WatcherDBWebService(win32serviceutil.ServiceFramework):
    _svc_name_ = "WatcherDBWebService"
    _svc_display_name_ = "WatcherDB Web Service"
    _svc_description_ = "Serviço web de monitoramento SQL Server - Acesso via browser"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.server = None
        self.server_thread = None
        
    def SvcStop(self):
        """Graceful shutdown do Uvicorn"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        # Sinalizar shutdown
        # Aguardar threads finalizarem
        win32event.SetEvent(self.stop_event)
        
    def SvcDoRun(self):
        """Inicia o servidor Uvicorn"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()
        
    def main(self):
        """Loop principal - executa Uvicorn"""
        # Carregar configuração
        # Iniciar Uvicorn com config:
        #   - host: 0.0.0.0 (aceitar conexões externas)
        #   - port: config.yaml
        #   - ssl_keyfile / ssl_certfile (se HTTPS direto)
        #   - workers: config.yaml
        pass

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(WatcherDBWebService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(WatcherDBWebService)
```

## 2. server.py - FastAPI Bootstrap

```python
"""
Bootstrap do FastAPI para o Web Service

Este módulo:
1. Importa o app existente de watcherdb_main.py (no diretório pai)
2. Adiciona middlewares de segurança
3. Configura autenticação
4. Adiciona health endpoints específicos do serviço
"""

import sys
from pathlib import Path

# Adicionar root do projeto ao path (WATCHERDB_DEV/)
# web_service está em: WATCHERDB_DEV/services/web_service/
ROOT_DIR = Path(__file__).parent.parent.parent  # Sobe 2 níveis: web_service -> services -> WATCHERDB_DEV
sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importar app existente do watcherdb_main.py
from watcherdb_main import app as watcherdb_app

# Importar módulos de segurança locais
from auth.middleware import AuthMiddleware
from security.cors import get_cors_config
from security.rate_limiter import RateLimitMiddleware
from security.headers import SecurityHeadersMiddleware
from security.audit import AuditMiddleware

def create_app() -> FastAPI:
    """Factory function para criar app configurado"""
    
    # Usar app existente ou criar wrapper
    app = watcherdb_app
    
    # Adicionar middlewares (ordem importa!)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        **get_cors_config()
    )
    
    # Health endpoints específicos do web service
    @app.get("/health/web-service", tags=["Health"])
    async def web_service_health():
        return {
            "service": "web_service",
            "status": "healthy",
            "version": "1.0.0"
        }
    
    return app

# Para uso com uvicorn
app = create_app()
```

## 3. config.yaml - Configuração

```yaml
# WatcherDB Web Service Configuration
# Localização: services/web_service/config.yaml

service:
  name: "WatcherDBWebService"
  display_name: "WatcherDB Web Service"
  description: "Serviço web de monitoramento SQL Server - Acesso via browser"
  
server:
  host: "0.0.0.0"          # Aceitar conexões de qualquer IP
  port: 8443               # Porta HTTPS
  workers: 4               # Número de workers Uvicorn
  timeout_keep_alive: 30   # Keep-alive timeout
  
ssl:
  enabled: true
  cert_file: "certs/watcherdb.crt"
  key_file: "certs/watcherdb.key"
  # Se false, usar proxy reverso (IIS/Nginx) para SSL
  
auth:
  enabled: true
  type: "jwt"              # "jwt" | "windows" | "hybrid" | "none"
  
  jwt:
    secret_env: "WATCHERDB_JWT_SECRET"  # Variável de ambiente
    algorithm: "HS256"
    expire_minutes: 480     # 8 horas
    refresh_expire_days: 7
    
  windows:                  # Se type: "windows" ou "hybrid"
    domain: "TAP"
    allowed_groups:
      - "DBA-Team"
      - "IT-Admins"
      
  # Usuários locais (se type: "jwt")
  local_users:
    - username: "admin"
      password_hash: "${ADMIN_PASSWORD_HASH}"  # bcrypt hash
      role: "admin"
    - username: "viewer"
      password_hash: "${VIEWER_PASSWORD_HASH}"
      role: "viewer"

authorization:
  roles:
    admin:
      - "read"
      - "write"
      - "delete"
      - "manage_users"
      - "manage_config"
      - "view_audit_logs"
    operator:
      - "read"
      - "write"
      - "execute_actions"
    viewer:
      - "read"
      
  # Endpoints públicos (sem auth)
  public_endpoints:
    - "/health"
    - "/health/live"
    - "/health/ready"
    - "/docs"              # Swagger (remover em produção)
    - "/openapi.json"
    
cors:
  enabled: true
  allowed_origins:
    - "https://watcherdb.tap.pt"
    - "https://10.0.0.0/8"  # Rede interna
  allowed_methods:
    - "GET"
    - "POST"
    - "PUT"
    - "DELETE"
  allowed_headers:
    - "*"
  allow_credentials: true
  
security:
  rate_limit:
    enabled: true
    requests_per_minute: 100
    burst: 20
    
  headers:
    hsts: true
    x_frame_options: "DENY"
    x_content_type_options: "nosniff"
    x_xss_protection: "1; mode=block"
    
  audit:
    enabled: true
    log_requests: true
    log_responses: false    # Não logar body de resposta
    log_auth_failures: true
    
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  
  files:
    access: "logs/access.log"
    service: "logs/service.log"
    errors: "logs/errors.log"
    audit: "logs/audit.log"
    
  rotation:
    max_bytes: 10485760     # 10MB
    backup_count: 5

# Path para o projeto principal (relativo ao web_service)
project:
  # WATCHERDB_DEV/services/web_service/ -> WATCHERDB_DEV/
  root: "../.."             
  main_app: "watcherdb_main:app"
  
  # Caminhos absolutos (preenchidos em runtime)
  # root_absolute: "C:\...\WATCHERDB_DEV"
```

## 4. install.py - Gerenciamento (Mesmo Padrão)

```python
"""
WatcherDB Web Service - Gerenciamento

Comandos:
    python install.py install     - Instalar serviço
    python install.py remove      - Remover serviço
    python install.py start       - Iniciar serviço
    python install.py stop        - Parar serviço
    python install.py restart     - Reiniciar serviço
    python install.py status      - Ver status
    python install.py validate    - Validar configuração
    python install.py test-auth   - Testar autenticação
    python install.py gen-cert    - Gerar certificado auto-assinado
    python install.py gen-secret  - Gerar JWT secret
"""

import argparse
import subprocess
import sys
import os
import secrets
from pathlib import Path

# ... implementação seguindo o mesmo padrão do collector_service
```

---

# COMANDOS DE USO (Padrão Consistente)

```powershell
# Navegação para o web_service
cd "C:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV\services\web_service"

# Instalação
python install.py install --auto-install-deps

# Gerar certificado SSL (auto-assinado)
python install.py gen-cert

# Gerar JWT secret
python install.py gen-secret

# Iniciar
python install.py start

# Status
python install.py status

# Testar conexão (de outra máquina)
.\scripts\test_connection.ps1 -Server "SERVER-WATCHERDB" -Port 8443

# Logs em tempo real
Get-Content logs\access.log -Wait -Tail 20
Get-Content logs\service.log -Wait -Tail 20

# Parar
python install.py stop

# Remover
python install.py remove
```

---

# INTEGRAÇÃO COM COLLECTOR SERVICE

Os serviços estão em **projetos diferentes** mas são **complementares**:

```
┌─────────────────────────────────────────────────────────────────┐
│            DOIS SERVIÇOS EM PROJETOS DIFERENTES                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📁 WATCHERDB INTELLIGENCE V1/         📁 WATCHERDB_DEV/       │
│  └── services/collector_service/       └── services/web_service/│
│                                                                 │
│  ┌─────────────────────────┐    ┌─────────────────────────┐    │
│  │   Collector Service     │    │    Web Service          │    │
│  │   (coleta de dados)     │    │    (exposição web)      │    │
│  ├─────────────────────────┤    ├─────────────────────────┤    │
│  │ • Roda em background    │    │ • Serve HTTP/HTTPS      │    │
│  │ • Não expõe portas      │    │ • Porta 8443 aberta     │    │
│  │ • Coleta → SQL Server   │    │ • SQL Server → Browser  │    │
│  │ • Sem auth (interno)    │    │ • Com autenticação      │    │
│  │ • Scheduler interno     │    │ • FastAPI + Uvicorn     │    │
│  └───────────┬─────────────┘    └───────────┬─────────────┘    │
│              │                              │                   │
│              │      ┌────────────┐          │                   │
│              └─────►│ SQL Server │◄─────────┘                   │
│                     │ (WatcherDB)│                              │
│                     └────────────┘                              │
│                                                                 │
│  Cenários de deploy:                                           │
│  • Servidor único: ambos os serviços no mesmo servidor         │
│  • Servidor de coleta: apenas collector_service                │
│  • Servidor de apresentação: apenas web_service                │
│  • Distribuído: collector em servidor A, web em servidor B     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

# FLUXO DE ACESSO DO UTILIZADOR

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           FLUXO DE ACESSO - UTILIZADOR                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  1. DBA abre browser e acessa:                                                 │
│     https://10.x.x.x:8443  ou  https://watcherdb.tap.pt                        │
│                                                                                 │
│  2. Sistema verifica autenticação:                                             │
│     ├─ Token JWT presente e válido? → Acesso liberado                          │
│     └─ Sem token ou expirado? → Redireciona para /login                        │
│                                                                                 │
│  3. Página de login:                                                           │
│     ├─ Usuário/senha (auth local)                                              │
│     └─ "Login com Windows" (se AD configurado)                                 │
│                                                                                 │
│  4. Após login bem-sucedido:                                                   │
│     ├─ JWT token gerado (8h validade)                                          │
│     ├─ Cookie httpOnly setado                                                  │
│     └─ Redireciona para dashboard principal                                    │
│                                                                                 │
│  5. Navegação normal:                                                          │
│     ├─ Todos os endpoints do WatcherDB disponíveis                             │
│     ├─ WebSocket para updates real-time                                        │
│     └─ Ações logadas para auditoria                                           │
│                                                                                 │
│  6. Logout / Expiração:                                                        │
│     └─ Redireciona para /login                                                 │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

# ENTREGÁVEIS ESPERADOS

1. **Estrutura completa** do diretório `services/web_service/`
2. **service.py** - Windows Service wrapper para Uvicorn
3. **server.py** - Bootstrap FastAPI com middlewares
4. **config.yaml** - Configuração completa
5. **install.py** - Gerenciamento (mesmo padrão do collector)
6. **Módulo auth/** - Autenticação JWT completa
7. **Módulo security/** - CORS, rate limit, headers, audit
8. **Scripts PowerShell** - Certs, firewall, teste
9. **Documentação** - QUICKSTART, README, TROUBLESHOOTING
10. **install_and_start.bat** - Quick install

---

# CONSIDERAÇÕES DE SEGURANÇA

1. **Rede**: Apenas expor na rede corporativa (não internet)
2. **Firewall**: Abrir porta 8443 apenas para ranges de IP internos
3. **Certificados**: Usar certs da PKI corporativa se disponível
4. **Secrets**: JWT secret em variável de ambiente, não no config
5. **Audit**: Logar todos os acessos e falhas de autenticação
6. **Senhas**: Bcrypt hash, nunca texto plano

---

# AMBIENTE

- **SO**: Windows Server 2019/2022
- **Python**: 3.11+
- **Projeto**: `WATCHERDB_DEV/` (onde está o watcherdb_main.py)
- **Web Service**: `WATCHERDB_DEV/services/web_service/`
- **Collector Service**: `WATCHERDB INTELLIGENCE V1/services/collector_service/` (projeto separado)
- **Consistência**: Mesmos comandos do collector_service, mesma organização de docs/logs

---

*Documento: Prompt para criação do WatcherDB Web Service*
*Versão: 2.1 - Localização em WATCHERDB_DEV*
*Data: 2026-01-26*
