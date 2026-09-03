# PROMPT: WatcherDB Web Service - Acesso Remoto via Browser (V2.1 - ATUALIZADO)

**⚠️ VERSÃO ATUALIZADA COM LIÇÕES APRENDIDAS DO COLLECTOR SERVICE**

Você é um engenheiro de software sênior especializado em:
- Arquitetura de aplicações web enterprise (FastAPI, Uvicorn, Gunicorn)
- Deploy de serviços Python em ambiente Windows Server
- Segurança de aplicações web (autenticação, HTTPS, CORS)
- Configuração de rede e firewall para exposição de serviços
- Alta disponibilidade e load balancing para aplicações internas

Responda de forma técnica, direta e com código production-ready.

---

# 🎯 CONTEXTO: LIÇÕES APRENDIDAS DO COLLECTOR SERVICE

Antes de criar o Web Service, foram aplicadas correções críticas no **Collector Service** que devem ser incorporadas desde o início no Web Service:

## ✅ Lição 1: Shutdown Events (CRÍTICO)
**Problema:** Serviço não respondia a shutdown do Windows, impedindo auto-start após reboot.

**Solução Aplicada:**
```python
class WatcherDBWebService(win32serviceutil.ServiceFramework):
    _svc_name_ = "WatcherDBWebService"
    _svc_display_name_ = "WatcherDB Web Service"
    _svc_description_ = "..."

    # CRÍTICO: Aceitar eventos de shutdown
    _exe_args_ = "-v"  # Permite verbosidade e resposta a shutdown

    def SvcShutdown(self):
        """Chamado quando sistema está sendo desligado"""
        self.SvcStop()  # Redireciona para SvcStop

    def SvcStop(self):
        """Graceful shutdown"""
        # Implementação de parada graceful
```

**Impacto:** Sem isso, o serviço:
- Aparece como "IGNORES_SHUTDOWN" no `sc query`
- Pode não iniciar automaticamente após reboot
- Não faz cleanup adequado ao desligar o sistema

## ✅ Lição 2: Python Cache Clearing
**Problema:** Após mudanças no código, o serviço continuava executando versões antigas devido ao cache `.pyc`.

**Solução:**
- Sempre limpar `__pycache__` antes de reinstalar:
```powershell
Remove-Item -Recurse -Force .\__pycache__
Remove-Item -Recurse -Force .\auth\__pycache__
Remove-Item -Recurse -Force .\security\__pycache__
```

**Implementar em `install.py`:**
```python
def clear_cache():
    """Limpa cache Python antes de reinstalar"""
    import shutil
    for cache_dir in Path('.').rglob('__pycache__'):
        shutil.rmtree(cache_dir, ignore_errors=True)
        print(f"✓ Cache removido: {cache_dir}")
```

## ✅ Lição 3: Logging Estruturado Detalhado
**O que funcionou bem no Collector:**
```python
# Formato estruturado com colunas alinhadas
formatter = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-25s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Múltiplos handlers com rotação
service_handler = RotatingFileHandler(
    'logs/service.log',
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=10
)
```

## ✅ Lição 4: Validação de Configuração
**Implementar comando `validate` em `install.py`:**
```python
def validate_config():
    """Valida config.yaml antes de iniciar"""
    - Verificar se todos os campos obrigatórios existem
    - Validar tipos de dados
    - Checar se portas estão disponíveis
    - Validar paths de certificados SSL (se habilitado)
    - Testar conexão com banco de dados
    - Verificar se watcherdb_main.py pode ser importado
```

## ✅ Lição 5: Health Monitoring
**Implementar arquivo de status:**
```python
# Atualizar a cada 30 segundos
def _heartbeat_monitor():
    status = {
        'service_name': 'WatcherDBWebService',
        'status': 'running',
        'start_time': start_time.isoformat(),
        'last_heartbeat': datetime.now().isoformat(),
        'uptime_seconds': uptime,
        'requests_handled': request_count,
        'active_connections': active_conn_count,
        'errors_count': error_count
    }

    with open('service_health.txt', 'w') as f:
        yaml.dump(status, f)
```

---

# 📂 ESTRUTURA COMPLETA DO WEB SERVICE

```
WATCHERDB_DEV/services/web_service/
│
├── service.py                    # Windows Service (com SvcShutdown!)
├── server.py                     # FastAPI bootstrap
├── config.yaml                   # Configuração
├── install.py                    # Gerenciamento (com validate e clear-cache)
├── requirements.txt
├── install_and_start.bat
├── __init__.py
├── README.md
├── CHANGELOG.md
│
├── auth/                         # 🆕 IMPLEMENTAR COMPLETO
│   ├── __init__.py
│   ├── middleware.py             # JWT validation middleware
│   ├── jwt_handler.py            # Create/validate/refresh tokens
│   ├── windows_auth.py           # AD integration (opcional)
│   ├── models.py                 # User, Session, Role
│   └── routes.py                 # /login, /logout, /me, /refresh
│
├── security/                     # 🆕 IMPLEMENTAR COMPLETO
│   ├── __init__.py
│   ├── cors.py                   # get_cors_config() from config.yaml
│   ├── rate_limiter.py           # RateLimitMiddleware
│   ├── headers.py                # SecurityHeadersMiddleware
│   └── audit.py                  # AuditMiddleware (log acessos)
│
├── certs/
│   ├── .gitkeep
│   └── README.md                 # Instruções de geração
│
├── scripts/
│   ├── generate_certs.ps1        # Gerar cert auto-assinado
│   ├── configure_firewall.ps1    # Abrir portas
│   ├── test_connection.ps1       # Testar conectividade
│   └── clear_cache.ps1           # Limpar __pycache__
│
├── docs/
│   ├── README.md
│   ├── QUICKSTART.md
│   ├── AUTHENTICATION.md
│   ├── SECURITY.md
│   ├── TROUBLESHOOTING.md
│   └── LESSONS_LEARNED.md        # 🆕 Lições do Collector Service
│
└── logs/                         # (auto-criado)
    ├── access.log                # Todos os requests HTTP
    ├── service.log               # Logs do serviço Windows
    ├── errors.log                # Somente erros
    └── audit.log                 # Auditoria (quem fez o quê)
```

---

# 🔒 IMPLEMENTAÇÃO: auth/ (PRIORIDADE ALTA)

## auth/middleware.py
```python
"""
FastAPI Middleware para validação JWT
Protege todos os endpoints exceto os listados em config.yaml:public_endpoints
"""

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import yaml
from pathlib import Path
from .jwt_handler import JWTHandler

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

        # Carregar config
        config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.jwt_handler = JWTHandler()
        self.public_endpoints = self.config.get('authorization', {}).get('public_endpoints', [])

    async def dispatch(self, request: Request, call_next):
        """Valida JWT antes de processar request"""

        # Endpoints públicos passam sem validação
        if request.url.path in self.public_endpoints:
            return await call_next(request)

        # Verificar se tem token JWT
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Missing or invalid authorization header"}
            )

        # Extrair token
        token = auth_header.replace('Bearer ', '')

        # Validar token
        payload = self.jwt_handler.validate_token(token)
        if not payload:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid or expired token"}
            )

        # Adicionar user info ao request.state
        request.state.user = payload

        # Processar request
        response = await call_next(request)
        return response
```

## auth/jwt_handler.py
```python
"""
JWT Token Handler - Criar, validar e refresh de tokens
"""

import jwt
import os
from datetime import datetime, timedelta
from typing import Optional, Dict
import yaml
from pathlib import Path

class JWTHandler:
    def __init__(self):
        # Carregar config
        config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        jwt_config = config.get('auth', {}).get('jwt', {})

        # Secret da variável de ambiente
        secret_env = jwt_config.get('secret_env', 'WATCHERDB_JWT_SECRET')
        self.secret = os.getenv(secret_env)

        if not self.secret:
            raise ValueError(f"JWT secret não encontrado na variável de ambiente: {secret_env}")

        self.algorithm = jwt_config.get('algorithm', 'HS256')
        self.expire_minutes = jwt_config.get('expire_minutes', 480)
        self.refresh_expire_days = jwt_config.get('refresh_expire_days', 7)

    def create_token(self, user_data: Dict) -> str:
        """Cria token JWT"""
        payload = {
            'username': user_data['username'],
            'role': user_data['role'],
            'exp': datetime.utcnow() + timedelta(minutes=self.expire_minutes),
            'iat': datetime.utcnow()
        }

        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def validate_token(self, token: str) -> Optional[Dict]:
        """Valida token JWT e retorna payload"""
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def create_refresh_token(self, user_data: Dict) -> str:
        """Cria refresh token (validade longa)"""
        payload = {
            'username': user_data['username'],
            'type': 'refresh',
            'exp': datetime.utcnow() + timedelta(days=self.refresh_expire_days),
            'iat': datetime.utcnow()
        }

        return jwt.encode(payload, self.secret, algorithm=self.algorithm)
```

## auth/models.py
```python
"""
Models para autenticação
"""

from pydantic import BaseModel
from typing import Optional, List

class User(BaseModel):
    username: str
    role: str
    permissions: Optional[List[str]] = []

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos
    user: User

class RefreshRequest(BaseModel):
    refresh_token: str
```

## auth/routes.py
```python
"""
Rotas de autenticação
"""

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer
import bcrypt
import yaml
from pathlib import Path
from .models import LoginRequest, LoginResponse, RefreshRequest, User
from .jwt_handler import JWTHandler

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
security = HTTPBearer()

# Carregar config
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
with open(CONFIG_PATH, 'r') as f:
    CONFIG = yaml.safe_load(f)

jwt_handler = JWTHandler()

def get_user_from_config(username: str) -> Optional[dict]:
    """Busca usuário no config.yaml"""
    users = CONFIG.get('auth', {}).get('local_users', [])
    for user in users:
        if user['username'] == username:
            return user
    return None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica senha com bcrypt"""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )

@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    """Endpoint de login"""

    # Buscar usuário
    user_data = get_user_from_config(credentials.username)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    # Verificar senha
    if not verify_password(credentials.password, user_data['password_hash']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    # Criar tokens
    access_token = jwt_handler.create_token(user_data)
    refresh_token = jwt_handler.create_refresh_token(user_data)

    # Buscar permissões do role
    role = user_data['role']
    permissions = CONFIG.get('authorization', {}).get('roles', {}).get(role, [])

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=jwt_handler.expire_minutes * 60,
        user=User(
            username=user_data['username'],
            role=role,
            permissions=permissions
        )
    )

@router.post("/refresh")
async def refresh_token(request: RefreshRequest):
    """Refresh access token usando refresh token"""

    payload = jwt_handler.validate_token(request.refresh_token)
    if not payload or payload.get('type') != 'refresh':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    # Buscar usuário
    user_data = get_user_from_config(payload['username'])
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Criar novo access token
    new_access_token = jwt_handler.create_token(user_data)

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": jwt_handler.expire_minutes * 60
    }

@router.get("/me", response_model=User)
async def get_current_user(token: str = Depends(security)):
    """Retorna informações do usuário autenticado"""

    payload = jwt_handler.validate_token(token.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user_data = get_user_from_config(payload['username'])
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    role = user_data['role']
    permissions = CONFIG.get('authorization', {}).get('roles', {}).get(role, [])

    return User(
        username=user_data['username'],
        role=role,
        permissions=permissions
    )

@router.post("/logout")
async def logout():
    """Logout (client deve descartar token)"""
    return {"message": "Logout successful"}
```

---

# 🛡️ IMPLEMENTAÇÃO: security/ (PRIORIDADE ALTA)

## security/cors.py
```python
"""
CORS Configuration - baseado em config.yaml
"""

import yaml
from pathlib import Path

def get_cors_config() -> dict:
    """Retorna configuração CORS do config.yaml"""

    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    cors_config = config.get('cors', {})

    return {
        'allow_origins': cors_config.get('allowed_origins', ['*']),
        'allow_credentials': cors_config.get('allow_credentials', True),
        'allow_methods': cors_config.get('allowed_methods', ['*']),
        'allow_headers': cors_config.get('allowed_headers', ['*']),
        'max_age': cors_config.get('max_age', 600)
    }
```

## security/headers.py
```python
"""
Security Headers Middleware
Adiciona headers de segurança em todas as respostas
"""

from starlette.middleware.base import BaseHTTPMiddleware
import yaml
from pathlib import Path

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

        # Carregar config
        config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        self.headers_config = config.get('security', {}).get('headers', {})

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # HSTS
        if self.headers_config.get('hsts', True):
            max_age = self.headers_config.get('hsts_max_age', 31536000)
            response.headers['Strict-Transport-Security'] = f'max-age={max_age}; includeSubDomains'

        # X-Frame-Options
        frame_options = self.headers_config.get('x_frame_options', 'DENY')
        response.headers['X-Frame-Options'] = frame_options

        # X-Content-Type-Options
        if self.headers_config.get('x_content_type_options', 'nosniff'):
            response.headers['X-Content-Type-Options'] = 'nosniff'

        # X-XSS-Protection
        if self.headers_config.get('x_xss_protection', '1; mode=block'):
            response.headers['X-XSS-Protection'] = '1; mode=block'

        # Referrer-Policy
        referrer_policy = self.headers_config.get('referrer_policy', 'strict-origin-when-cross-origin')
        response.headers['Referrer-Policy'] = referrer_policy

        # Content-Security-Policy (opcional, pode quebrar coisas)
        # response.headers['Content-Security-Policy'] = "default-src 'self'"

        return response
```

## security/rate_limiter.py
```python
"""
Rate Limiting Middleware
Previne abuse e DOS attacks
"""

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
import time
from collections import defaultdict
import threading
import yaml
from pathlib import Path

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

        # Carregar config
        config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        rate_limit_config = config.get('security', {}).get('rate_limit', {})

        self.enabled = rate_limit_config.get('enabled', True)
        self.requests_per_minute = rate_limit_config.get('requests_per_minute', 100)
        self.burst = rate_limit_config.get('burst', 20)

        # Storage: {ip: [(timestamp, count), ...]}
        self.requests = defaultdict(list)
        self.lock = threading.Lock()

        # Cleanup thread (limpa entradas antigas a cada minuto)
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

    def _cleanup_loop(self):
        """Remove entradas antigas do storage"""
        while True:
            time.sleep(60)
            with self.lock:
                now = time.time()
                for ip in list(self.requests.keys()):
                    # Remove requests com mais de 1 minuto
                    self.requests[ip] = [
                        (ts, count) for ts, count in self.requests[ip]
                        if now - ts < 60
                    ]

                    # Remove IP se não tem mais requests
                    if not self.requests[ip]:
                        del self.requests[ip]

    async def dispatch(self, request, call_next):
        if not self.enabled:
            return await call_next(request)

        # Identificar cliente (IP)
        client_ip = request.client.host

        with self.lock:
            now = time.time()

            # Limpar requests antigos deste IP
            self.requests[client_ip] = [
                (ts, count) for ts, count in self.requests[client_ip]
                if now - ts < 60
            ]

            # Contar requests no último minuto
            total_requests = sum(count for ts, count in self.requests[client_ip])

            # Verificar limite
            if total_requests >= self.requests_per_minute:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too Many Requests",
                        "message": f"Rate limit exceeded. Max {self.requests_per_minute} requests per minute.",
                        "retry_after": 60
                    },
                    headers={"Retry-After": "60"}
                )

            # Adicionar este request
            self.requests[client_ip].append((now, 1))

        # Processar request
        response = await call_next(request)

        # Adicionar headers informativos
        response.headers['X-RateLimit-Limit'] = str(self.requests_per_minute)
        response.headers['X-RateLimit-Remaining'] = str(self.requests_per_minute - total_requests - 1)
        response.headers['X-RateLimit-Reset'] = str(int(now + 60))

        return response
```

## security/audit.py
```python
"""
Audit Middleware
Loga todos os acessos para auditoria
"""

from starlette.middleware.base import BaseHTTPMiddleware
import logging
import time
import yaml
from pathlib import Path
from datetime import datetime

class AuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

        # Carregar config
        config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        audit_config = config.get('security', {}).get('audit', {})

        self.enabled = audit_config.get('enabled', True)
        self.log_requests = audit_config.get('log_requests', True)
        self.log_responses = audit_config.get('log_responses', False)
        self.log_auth_failures = audit_config.get('log_auth_failures', True)
        self.log_successful_auth = audit_config.get('log_successful_auth', True)

        # Setup logger
        self.logger = logging.getLogger('WatcherDBWebService.Audit')
        handler = logging.FileHandler('logs/audit.log', encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    async def dispatch(self, request, call_next):
        if not self.enabled:
            return await call_next(request)

        start_time = time.time()

        # Informações do request
        client_ip = request.client.host
        method = request.method
        path = request.url.path
        user_agent = request.headers.get('User-Agent', 'Unknown')

        # Usuário (se autenticado)
        username = getattr(request.state, 'user', {}).get('username', 'anonymous')

        # Log do request
        if self.log_requests:
            self.logger.info(
                f"REQUEST | {client_ip} | {username} | {method} {path} | UA: {user_agent}"
            )

        # Processar request
        response = await call_next(request)

        # Tempo de resposta
        duration = (time.time() - start_time) * 1000  # ms

        # Log da resposta
        status_code = response.status_code

        log_message = (
            f"RESPONSE | {client_ip} | {username} | {method} {path} | "
            f"Status: {status_code} | Duration: {duration:.2f}ms"
        )

        if status_code >= 500:
            self.logger.error(log_message)
        elif status_code >= 400:
            if status_code == 401 and self.log_auth_failures:
                self.logger.warning(f"AUTH FAILURE | {log_message}")
            else:
                self.logger.warning(log_message)
        else:
            if path.startswith('/api/v1/auth/login') and self.log_successful_auth:
                self.logger.info(f"AUTH SUCCESS | {log_message}")
            elif self.log_responses:
                self.logger.info(log_message)

        return response
```

---

# 🔧 IMPLEMENTAÇÃO: service.py (ATUALIZADO)

```python
"""
WatcherDB Web Service - Windows Service Wrapper

✅ INCLUI LIÇÕES APRENDIDAS DO COLLECTOR SERVICE:
- SvcShutdown() para responder a eventos de sistema
- _exe_args_ para aceitar shutdown events
- Logging estruturado detalhado
- Health monitoring com heartbeat
"""

import win32serviceutil
import win32service
import win32event
import servicemanager
import sys
import os
import threading
import time
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
import yaml
import uvicorn
from logging.handlers import RotatingFileHandler


class WatcherDBWebService(win32serviceutil.ServiceFramework):
    """Windows Service para o WatcherDB Web"""

    _svc_name_ = "WatcherDBWebService"
    _svc_display_name_ = "WatcherDB Web Service"
    _svc_description_ = "Serviço web de monitoramento SQL Server - Acesso via browser"

    # ✅ CRÍTICO: Aceitar shutdown events
    _exe_args_ = "-v"

    def __init__(self, args):
        """Inicializa o serviço"""
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.is_running = False
        self.server = None
        self.server_thread = None

        # Diretórios
        self.service_dir = Path(__file__).parent
        self.project_root = self.service_dir.parent.parent
        self.logs_dir = self.service_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)

        # Configuração
        self.config = self._load_config()
        self._setup_logging()

        # Health monitoring
        self.health = {
            'start_time': None,
            'last_heartbeat': None,
            'requests_handled': 0,
            'errors_count': 0
        }

    def _load_config(self) -> dict:
        """Carrega configuração do config.yaml"""
        config_path = self.service_dir / "config.yaml"

        if not config_path.exists():
            return self._default_config()

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            servicemanager.LogErrorMsg(f"Erro ao carregar config.yaml: {e}")
            return self._default_config()

    def _default_config(self) -> dict:
        """Configuração padrão"""
        return {
            'server': {
                'host': '0.0.0.0',
                'port': 8443,
                'workers': 1,
                'timeout_keep_alive': 30
            },
            'ssl': {'enabled': False},
            'logging': {'level': 'INFO'}
        }

    def _setup_logging(self):
        """✅ Logging estruturado detalhado (padrão Collector Service)"""
        log_level = self.config.get('logging', {}).get('level', 'INFO')

        # Logger principal
        self.logger = logging.getLogger('WatcherDBWebService')
        self.logger.setLevel(getattr(logging, log_level))
        self.logger.propagate = False
        self.logger.handlers.clear()

        # Formato estruturado
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-25s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Handler 1: Service log
        service_handler = RotatingFileHandler(
            self.logs_dir / "service.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=10,
            encoding='utf-8'
        )
        service_handler.setLevel(logging.DEBUG)
        service_handler.setFormatter(formatter)
        self.logger.addHandler(service_handler)

        # Handler 2: Error log
        error_handler = RotatingFileHandler(
            self.logs_dir / "errors.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        self.logger.addHandler(error_handler)

        # Handler 3: Console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def _start_heartbeat_monitor(self):
        """✅ Health monitoring com heartbeat (padrão Collector Service)"""
        def heartbeat_loop():
            heartbeat_file = self.service_dir / "service_health.txt"

            while self.is_running:
                try:
                    status = {
                        'service_name': self._svc_name_,
                        'status': 'running',
                        'start_time': self.health['start_time'].isoformat() if self.health['start_time'] else None,
                        'last_heartbeat': datetime.now().isoformat(),
                        'uptime_seconds': (datetime.now() - self.health['start_time']).total_seconds() if self.health['start_time'] else 0,
                        'requests_handled': self.health['requests_handled'],
                        'errors_count': self.health['errors_count']
                    }

                    with open(heartbeat_file, 'w', encoding='utf-8') as f:
                        yaml.dump(status, f, default_flow_style=False)

                except Exception as e:
                    self.logger.warning(f"Heartbeat monitor error: {e}")

                time.sleep(30)

        # Iniciar thread
        heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        heartbeat_thread.start()
        self.logger.info("Heartbeat monitor started")

    def SvcShutdown(self):
        """✅ Responde a shutdown do Windows (LIÇÃO CRÍTICA)"""
        self.logger.info("Recebido evento de SHUTDOWN do sistema")
        self.SvcStop()

    def SvcStop(self):
        """Para o serviço (chamado pelo Windows)"""
        self.logger.info("=" * 80)
        self.logger.info("SERVICE STOP REQUESTED")
        self.logger.info("=" * 80)

        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)

        # Sinalizar parada
        self.is_running = False
        win32event.SetEvent(self.stop_event)

        # Aguardar servidor finalizar gracefully
        if self.server_thread and self.server_thread.is_alive():
            self.logger.info("Aguardando servidor Uvicorn finalizar...")
            self.server_thread.join(timeout=10)

        self.logger.info("=" * 80)
        self.logger.info("SERVICE STOPPED")
        self.logger.info(f"Total requests handled: {self.health['requests_handled']}")
        self.logger.info(f"Total errors: {self.health['errors_count']}")
        self.logger.info("=" * 80)

    def SvcDoRun(self):
        """Inicia o serviço (chamado pelo Windows)"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )

        self.logger.info("=" * 80)
        self.logger.info("SERVICE STARTING")
        self.logger.info("=" * 80)
        self.logger.info(f"Diretório do serviço: {self.service_dir}")
        self.logger.info(f"Diretório do projeto: {self.project_root}")

        try:
            self.main()
        except Exception as e:
            self.logger.error(f"Erro fatal no serviço: {e}", exc_info=True)
            servicemanager.LogErrorMsg(f"Erro fatal: {e}")

    def main(self):
        """Loop principal do serviço"""
        self.is_running = True
        self.health['start_time'] = datetime.now()

        # Adicionar project root ao sys.path
        if str(self.project_root) not in sys.path:
            sys.path.insert(0, str(self.project_root))
            self.logger.info(f"Adicionado ao sys.path: {self.project_root}")

        # Configuração do servidor
        server_config = self.config.get('server', {})
        ssl_config = self.config.get('ssl', {})

        host = server_config.get('host', '0.0.0.0')
        port = server_config.get('port', 8443)
        workers = server_config.get('workers', 1)

        # Configuração Uvicorn
        uvicorn_config = {
            'app': 'services.web_service.server:app',
            'host': host,
            'port': port,
            'workers': workers,
            'log_level': self.config.get('logging', {}).get('level', 'info').lower(),
            'access_log': True,
            'reload': False,
            'timeout_keep_alive': server_config.get('timeout_keep_alive', 30)
        }

        # SSL/TLS
        if ssl_config.get('enabled', False):
            cert_file = self.service_dir / ssl_config.get('cert_file', 'certs/watcherdb.crt')
            key_file = self.service_dir / ssl_config.get('key_file', 'certs/watcherdb.key')

            if cert_file.exists() and key_file.exists():
                uvicorn_config['ssl_keyfile'] = str(key_file)
                uvicorn_config['ssl_certfile'] = str(cert_file)
                self.logger.info(f"✅ SSL habilitado: {cert_file}")
            else:
                self.logger.warning(f"⚠ SSL configurado mas certificados não encontrados")

        self.logger.info(f"Iniciando servidor Uvicorn em {host}:{port}")
        self.logger.info(f"Workers: {workers}")

        # Iniciar heartbeat monitor
        self._start_heartbeat_monitor()

        # Iniciar servidor em thread separada
        self.server_thread = threading.Thread(
            target=self._run_server,
            args=(uvicorn_config,),
            daemon=False
        )
        self.server_thread.start()

        self.logger.info("=" * 80)
        self.logger.info("SERVICE RUNNING")
        self.logger.info("=" * 80)

        # Aguardar sinal de parada
        while self.is_running:
            rc = win32event.WaitForSingleObject(self.stop_event, 5000)
            if rc == win32event.WAIT_OBJECT_0:
                break

        self.logger.info("Loop principal finalizado")

    def _run_server(self, config: dict):
        """Executa o servidor Uvicorn"""
        try:
            self.logger.info("Thread do servidor iniciada")

            # Criar servidor
            uvicorn_server = uvicorn.Server(uvicorn.Config(**config))
            self.server = uvicorn_server

            # Executar servidor (bloqueia até shutdown)
            uvicorn_server.run()

            self.logger.info("Servidor Uvicorn finalizado")

        except Exception as e:
            self.logger.error(f"Erro ao executar servidor: {e}", exc_info=True)
            self.health['errors_count'] += 1
            self.is_running = False


def main():
    """Ponto de entrada"""
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(WatcherDBWebService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(WatcherDBWebService)


if __name__ == '__main__':
    main()
```

---

# 🛠️ IMPLEMENTAÇÃO: install.py (ATUALIZADO)

Adicionar ao `install.py` existente:

```python
def clear_cache():
    """✅ Limpa cache Python (LIÇÃO DO COLLECTOR SERVICE)"""
    import shutil

    print("\n" + "="*60)
    print("Limpando cache Python...")
    print("="*60)

    cache_dirs = list(Path('.').rglob('__pycache__'))

    if not cache_dirs:
        print("✓ Nenhum cache encontrado")
        return

    for cache_dir in cache_dirs:
        try:
            shutil.rmtree(cache_dir)
            print(f"✓ Removido: {cache_dir}")
        except Exception as e:
            print(f"⚠ Erro ao remover {cache_dir}: {e}")

    print(f"\n✓ Total de {len(cache_dirs)} caches removidos")

def validate_config():
    """✅ Valida configuração antes de instalar (NOVA FUNCIONALIDADE)"""
    print("\n" + "="*60)
    print("Validando configuração...")
    print("="*60)

    config_path = Path("config.yaml")

    # Verificar se existe
    if not config_path.exists():
        print("❌ config.yaml não encontrado!")
        return False

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Erro ao ler config.yaml: {e}")
        return False

    # Validar campos obrigatórios
    required_fields = [
        ('server', 'host'),
        ('server', 'port'),
        ('logging', 'level')
    ]

    for section, field in required_fields:
        if section not in config or field not in config[section]:
            print(f"❌ Campo obrigatório faltando: {section}.{field}")
            return False

    # Verificar se porta está disponível
    port = config['server']['port']
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', port))
        sock.close()

        if result == 0:
            print(f"⚠ Porta {port} já está em uso!")
            # Não é erro fatal, pode ser o próprio serviço rodando
        else:
            print(f"✓ Porta {port} disponível")
    except Exception as e:
        print(f"⚠ Não foi possível verificar porta: {e}")

    # Verificar SSL (se habilitado)
    if config.get('ssl', {}).get('enabled', False):
        cert_file = Path(config['ssl'].get('cert_file', 'certs/watcherdb.crt'))
        key_file = Path(config['ssl'].get('key_file', 'certs/watcherdb.key'))

        if not cert_file.exists():
            print(f"❌ Certificado SSL não encontrado: {cert_file}")
            print("   Execute: python install.py gen-cert")
            return False

        if not key_file.exists():
            print(f"❌ Chave SSL não encontrada: {key_file}")
            return False

        print("✓ Certificados SSL encontrados")

    # Verificar JWT secret
    jwt_secret_env = config.get('auth', {}).get('jwt', {}).get('secret_env', 'WATCHERDB_JWT_SECRET')
    if not os.getenv(jwt_secret_env):
        print(f"⚠ Variável de ambiente não definida: {jwt_secret_env}")
        print("   Execute: python install.py gen-secret")
        print("   Depois: setx WATCHERDB_JWT_SECRET \"<secret_gerado>\"")
    else:
        print(f"✓ JWT secret configurado: {jwt_secret_env}")

    # Verificar se watcherdb_main.py existe
    project_root = Path(__file__).parent.parent.parent
    main_app = project_root / "watcherdb_main.py"

    if not main_app.exists():
        print(f"❌ Aplicação principal não encontrada: {main_app}")
        return False

    print(f"✓ Aplicação principal encontrada: {main_app}")

    print("\n✅ Validação concluída com sucesso!")
    return True

# Adicionar ao argparse:
parser.add_argument('command', help='...')
# ...
# Adicionar:
# validate  - Validar configuração
# clear-cache - Limpar cache Python

# No main():
if args.command == 'validate':
    validate_config()
elif args.command == 'clear-cache':
    clear_cache()
elif args.command == 'install':
    # Validar antes de instalar
    if not validate_config():
        print("\n❌ Validação falhou. Corrija os problemas antes de instalar.")
        sys.exit(1)

    # Limpar cache
    clear_cache()

    # Prosseguir com instalação...
```

---

# 📝 RESUMO DAS MELHORIAS

## ✅ Implementações Completas Necessárias

1. **auth/** (5 arquivos)
   - ✅ middleware.py
   - ✅ jwt_handler.py
   - ✅ models.py
   - ✅ routes.py
   - ⚠️ windows_auth.py (opcional, pode implementar depois)

2. **security/** (4 arquivos)
   - ✅ cors.py
   - ✅ headers.py
   - ✅ rate_limiter.py
   - ✅ audit.py

3. **service.py**
   - ✅ Adicionar `SvcShutdown()`
   - ✅ Adicionar `_exe_args_ = "-v"`
   - ✅ Melhorar logging estruturado
   - ✅ Adicionar heartbeat monitor

4. **install.py**
   - ✅ Adicionar `validate_config()`
   - ✅ Adicionar `clear_cache()`
   - ✅ Validar antes de instalar

5. **server.py**
   - ✅ Já está correto! Só precisa dos módulos implementados
   - ✅ Adicionar rotas de auth ao app

---

# 🎯 ORDEM DE IMPLEMENTAÇÃO RECOMENDADA

1. **Fase 1: Segurança Básica** (1-2 horas)
   ```
   1. security/cors.py
   2. security/headers.py
   3. Atualizar service.py (SvcShutdown + logging)
   4. Testar instalação básica
   ```

2. **Fase 2: Autenticação** (2-3 horas)
   ```
   5. auth/models.py
   6. auth/jwt_handler.py
   7. auth/routes.py
   8. auth/middleware.py
   9. Integrar rotas no server.py
   10. Testar login/logout
   ```

3. **Fase 3: Proteção Avançada** (1-2 horas)
   ```
   11. security/rate_limiter.py
   12. security/audit.py
   13. Atualizar install.py (validate + clear-cache)
   14. Testes finais
   ```

---

# 📋 CHECKLIST FINAL

Antes de considerar completo, verificar:

- [ ] `SvcShutdown()` implementado no service.py
- [ ] `_exe_args_ = "-v"` adicionado
- [ ] Todos os 4 arquivos de `security/` implementados
- [ ] Todos os 4 arquivos principais de `auth/` implementados
- [ ] Rotas de auth adicionadas ao `server.py`
- [ ] `validate_config()` funcionando em `install.py`
- [ ] `clear_cache()` funcionando em `install.py`
- [ ] JWT secret gerado e configurado
- [ ] Certificados SSL gerados (se SSL habilitado)
- [ ] Teste de login com admin/admin123
- [ ] Teste de acesso protegido sem token (deve retornar 401)
- [ ] Teste de acesso protegido com token válido
- [ ] Teste de rate limiting (>100 requests/min)
- [ ] Verificar logs de auditoria (audit.log)
- [ ] Testar shutdown e auto-start após reboot

---

**FIM DO PROMPT ATUALIZADO**

Este prompt incorpora TODAS as lições aprendidas do Collector Service e especifica exatamente o que precisa ser implementado para completar o Web Service.
