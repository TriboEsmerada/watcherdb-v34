"""
Security Headers Middleware — wrapper that reads from config/config.yaml

Adds HTTP security headers (HSTS, X-Frame-Options, CSP, etc.) to all responses.
"""

import logging
import secrets
from pathlib import Path
from typing import Callable

import yaml
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all HTTP responses.

    Reads configuration from config/config.yaml -> security.headers section.
    Falls back to secure defaults if config is missing.
    """

    def __init__(self, app):
        super().__init__(app)
        self.config = self._load_config()
        self.headers_config = self.config.get("security", {}).get("headers", {})
        logger.info("SecurityHeadersMiddleware initialized (config/config.yaml)")

    def _load_config(self) -> dict:
        if not _CONFIG_PATH.exists():
            return {}
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    async def dispatch(self, request: Request, call_next: Callable):
        # Generate per-request CSP nonce
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)

        # HSTS — force HTTPS on future visits. SO sobre HTTPS real: sobre HTTP
        # o browser ignora (RFC 6797) mas o header fica "armado" — no dia em
        # que TLS ligar, includeSubDomains prende *.<dominio> por 1 ano em
        # qualquer browser que visite uma vez. Apanhado pelo QA externo
        # 2026-08-16 (BUG-010). request.url.scheme reflecte a ligacao real
        # negociada pelo uvicorn (TLS directo, sem proxy) — sem X-Forwarded.
        if request.url.scheme == "https" and self.headers_config.get("hsts", True):
            max_age = self.headers_config.get("hsts_max_age", 31536000)
            response.headers["Strict-Transport-Security"] = (
                f"max-age={max_age}; includeSubDomains"
            )

        # X-Frame-Options — prevent clickjacking
        x_frame = self.headers_config.get("x_frame_options", "DENY")
        if x_frame:
            response.headers["X-Frame-Options"] = x_frame

        # X-Content-Type-Options — prevent MIME sniffing
        if self.headers_config.get("x_content_type_options", "nosniff"):
            response.headers["X-Content-Type-Options"] = "nosniff"

        # X-XSS-Protection — legacy browser XSS filter
        xss_protection = self.headers_config.get("x_xss_protection", "1; mode=block")
        if xss_protection:
            response.headers["X-XSS-Protection"] = xss_protection

        # Referrer-Policy
        referrer_policy = self.headers_config.get(
            "referrer_policy", "strict-origin-when-cross-origin"
        )
        if referrer_policy:
            response.headers["Referrer-Policy"] = referrer_policy

        # Content-Security-Policy.
        #
        # 2026-08-12 (consenso security-auditor + frontend-specialist, apos a
        # 1a instalacao real): o default anterior era nonce-only em script-src
        # e style-src. Nonces NAO se aplicam a handlers inline nem a atributos
        # style -- so' a blocos <script>/<style> -- portanto essa politica
        # bloqueava os 1034 handlers (778 onclick + 226 hover + ...) e os 6840
        # style="" do portal: 941 erros de consola e zero cliques funcionais.
        # Nunca foi detectado porque dev empilhava um segundo middleware
        # permissivo por cima (ver services/web_service/server.py).
        #
        # A separacao CSP3 -elem/-attr resolve sem abdicar do que interessa:
        # 'unsafe-inline' fica activo SO para atributos, enquanto script-src /
        # style-src (que governam -elem) mantem o nonce -- logo a injeccao de
        # um <script> inteiro, que e' o XSS de maior impacto, continua
        # bloqueada. Directiva -attr declarada em separado DE PROPOSITO: se
        # levasse o nonce dentro, o browser ignorava o 'unsafe-inline'.
        # Browser antigo que nao conheca -attr degrada FECHADO (cai em
        # script-src com nonce, handlers bloqueados) -- UI parte, seguranca
        # nao abre.
        #
        # Sem CDNs: o portal auto-hospeda tudo em /static/vendor/ (o jsdelivr
        # so' servia o Swagger em /docs -- desligar com WATCHERDB_DISABLE_DOCS
        # em instalacao de cliente). Sem 'unsafe-eval': o unico eval() do
        # template usa catalogo estatico de KPIs.
        #
        # DEBITO ASSUMIDO, com prazo: -attr 'unsafe-inline' sai quando a
        # migracao dos handlers para delegacao por data-action estiver feita
        # (plano em 5 fases no blackboard, 2026-08-12).
        csp = self.headers_config.get("content_security_policy")
        if csp:
            response.headers["Content-Security-Policy"] = csp
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}'; "
                "script-src-attr 'unsafe-inline'; "
                f"style-src 'self' 'nonce-{nonce}'; "
                "style-src-attr 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self' ws: wss:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "object-src 'none'"
            )

        # Permissions-Policy — disable sensitive browser features
        permissions_policy = self.headers_config.get("permissions_policy")
        if permissions_policy:
            response.headers["Permissions-Policy"] = permissions_policy
        else:
            response.headers["Permissions-Policy"] = (
                "geolocation=(), "
                "microphone=(), "
                "camera=(), "
                "payment=(), "
                "usb=(), "
                "magnetometer=(), "
                "gyroscope=(), "
                "accelerometer=()"
            )

        # Mask server header
        if "Server" in response.headers:
            response.headers["Server"] = "WatcherDB"
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]

        return response
