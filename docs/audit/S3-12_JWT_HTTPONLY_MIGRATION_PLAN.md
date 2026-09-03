# S3-12 Follow-up: JWT localStorage → HttpOnly cookie migration plan

**Status:** Deferred from Sprint 3 (22/04/2026).
**Priority:** P1 — não blocker mas compliance finding (frontend-specialist).
**Estimativa:** 1-2 dias de trabalho + E2E testing session.

---

## Contexto

O finding original do audit de 22/04 (FULL_AUDIT_20260422_ORQUESTRADOR.md item #12) era que o JWT está armazenado em `localStorage` do browser, criando vector de XSS caso haja bypass de sanitização.

**Investigação revelou que o backend JA ESTA correcto:**

```python
# api/routers/auth_compat.py:289-295
response.set_cookie(
    key="access_token",
    value=token,
    httponly=True,   # ✓ JavaScript não consegue ler
    secure=True,     # ✓ Só via HTTPS
    samesite="lax",  # ✓ CSRF mitigation
)
```

O cookie HttpOnly é setado em paralelo com o token devolvido no body da resposta de login. O middleware global (`AuthEnforcementMiddleware`, adicionado em P0-3) lê de AMBOS `Authorization` header E `request.cookies.get('access_token')`:

```python
# api/routers/auth_compat.py:180-184 — _get_token_from_request
auth_header = request.headers.get('Authorization', '')
if auth_header.startswith('Bearer '):
    return auth_header[7:]
return request.cookies.get('access_token')
```

Portanto a infraestrutura para HttpOnly-only está completa. O que falta é **remover a dependência do frontend em `localStorage`**.

## Estado actual (2026-04-22)

Frontend `templates/watcherdb_portal.html`:

- **14 localStorage callsites** — leitura (`getItem`), escrita (`setItem`), remoção (`removeItem`) de `watcherdb_token` ou constante `AUTH_TOKEN_KEY`
- **114 chamadas `fetch()`** — a maioria passa `Authorization: Bearer <token>` header com valor lido do localStorage
- **ZERO chamadas com `credentials: 'include'`** — condição necessária para o browser enviar cookie HttpOnly automaticamente em chamadas same-origin

## Migração (plano)

### Fase 1 — backend: redundância no set_cookie

Sem alteração necessária. Já está correcto.

Opcional: devolver o token SÓ no cookie (não no body) para tornar impossível o client-side capture:
```python
# Em auth_compat.py login handler:
response = JSONResponse({"username": user.username, "role": user.role})  # sem token
response.set_cookie(...)  # inalterado
return response
```
Este passo é último, depois da frontend migration validada.

### Fase 2 — frontend: wrapper fetch canónico

Criar helper JS no topo do portal que todos os callsites usam:
```javascript
async function apiFetch(url, options = {}) {
    const opts = { ...options, credentials: 'include' };
    // Remove Authorization header se presente — cookie handles it
    if (opts.headers && opts.headers.Authorization) {
        delete opts.headers.Authorization;
    }
    return fetch(url, opts);
}
```

Search-and-replace os 114 callsites de `fetch(` para `apiFetch(`. Remover a linha `'Authorization': 'Bearer ' + token` onde aparecer.

### Fase 3 — frontend: remover localStorage auth token

Remover as 14 ocorrências de `localStorage.setItem('watcherdb_token'...)`, `getItem`, `removeItem`. A constante `AUTH_TOKEN_KEY` deve ser removida do topo do script.

**Cuidado:** session resumption e multi-tab sync funcionam nativamente via cookie (browser partilha cookies entre tabs mesmo origin). Confirmar empiricamente com teste E2E.

### Fase 4 — validação E2E

Testes manuais obrigatórios:
1. Login → navegar 3 tabs diferentes → confirmar zero 401
2. Refresh (F5) no meio de uma sessão → continuar autenticado
3. Abrir segunda tab do mesmo portal → sessão partilhada
4. Logout → cookie apagado → ecra de login volta
5. Expirar o JWT (esperar TTL) → redirect para login
6. Inspector do browser → confirmar `localStorage['watcherdb_token']` é `null`
7. Inspector → Cookies → confirmar `access_token` com flag `HttpOnly`

### Fase 5 — backend: deixar de devolver token no body (opcional)

Depois da fase 4 validada, pode-se remover o token do body da resposta de login. Torna impossível capture client-side mesmo com XSS.

## Risco se não migrar

- **Baixo-médio.** Se um XSS bypass de DOMPurify ocorrer, attacker lê `localStorage` e exfiltra token. Window até expiry (JWT TTL 1440min = 24h por default).
- Mitigações existentes:
  - CSP headers (via SecurityHeadersMiddleware)
  - DOMPurify obrigatório em `innerHTML`
  - HttpOnly cookie em paralelo (parcialmente reduz o payoff do XSS — cookie ainda é enviado mesmo se localStorage for exfiltrado, mas attacker agora tem o mesmo nivel de acesso do user).

## Fonte

- Frontend-specialist audit 22/04/2026 (finding severidade high — localStorage JWT)
- Security-auditor audit 22/04/2026 (cookie configuração validada como correcta)
- FULL_AUDIT_20260422_ORQUESTRADOR.md item #12

## Entrega esperada

Quando S3-12 for retomado:
1. Commit com fetch wrapper (`apiFetch`) + search-replace dos 114 callsites
2. Commit removendo localStorage auth token (14 callsites)
3. Commit validação manual E2E + screenshot testcases
4. Opcional: commit removendo token do body login response

---

**Documento criado em Sprint 3 (22/04/2026) como handoff explicito** — o trabalho não foi executado para evitar regressão em grande refactor sem E2E test rig dedicado.
