# WatcherDB V3.1 — Relatorio Completo de Testes
## Data: 2026-03-23 | Contexto: Teste autorizado (equipa DBA TAP)

---

## SUMARIO EXECUTIVO

Auditoria completa do sistema de autenticacao e persistencia de sessao do WatcherDB V3.1, executada com 6 personas tecnicas especializadas. Total de **93 findings** identificados.

### Estatisticas Globais

| Persona | Tipo de Teste | Findings |
|---------|--------------|----------|
| Tech Lead (Persona 4) | Code Review | 15 findings |
| Pentester (Persona 2) | Security | 16 findings |
| QA Analyst (Persona 1) | Functional | 25 test cases + 4 bugs |
| Performance Engineer (Persona 3) | Load/Stress | 4 cenarios + scripts Locust |
| DBA (Persona 6) | Data Integrity | 12 findings |
| UX/A11y (Persona 5) | Accessibility | 20 issues WCAG |

### Findings CRITICAL (Accao Imediata Necessaria)

| # | Finding | Fonte | Ficheiro |
|---|---------|-------|----------|
| 1 | JWT Secret hardcoded como default | Security, Code Review, DBA | auth_service.py:15 |
| 2 | SQL Injection sem autenticacao em custom queries | Security | watcherdb_main.py:3164 |
| 3 | Default users com password admin123 em fallback | Security, Code Review, DBA | auth_service.py:346-350 |
| 4 | SHA-256 sem salt como fallback de bcrypt | Security, Code Review | auth_service.py:94-106 |
| 5 | _execute_query silencia erros e fallback para defaults | Code Review | auth_service.py:55-57,379 |

### Prioridade de Remediacao

```
IMEDIATO (antes de exposicao em rede):
1. Remover _DEFAULT_USERS e fallback para credenciais hardcoded
2. Forcar JWT_SECRET_KEY via env var (fail-fast se nao definido)
3. Adicionar autenticacao ao endpoint custom queries
4. Remover fallback SHA-256 (tornar bcrypt obrigatorio)

CURTO PRAZO (proxima sprint):
5. Validar current_password no change-password
6. CORS: substituir allow_origins=["*"] por dominio especifico
7. MERGE com HOLDLOCK nas preferencias
8. Remover WITH (NOLOCK) das queries de autenticacao
9. Implementar token blacklist no logout

MEDIO PRAZO:
10. Migrar JWT de localStorage para HttpOnly cookie
11. Reduzir JWT expiration de 24h para 60min + refresh token
12. Adicionar FK e CHECK constraints ao schema
13. Job de cleanup do Auth_Log
14. Correcoes de acessibilidade WCAG nivel A
```

---

## PERSONA 4: CODE REVIEW (Tech Lead)

### 15 Findings

**[Critical] JWT Secret hardcoded como fallback em producao**
- **Ficheiro:Linha:** auth_service.py:15
- **Descricao:** `JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'watcherdb-dev-secret-change-in-production')`. Se a env var nao existir, o sistema arranca com chave publica.
- **Sugestao:** Fail-fast no startup se env var nao definida.

**[Critical] SHA-256 fallback para passwords e inseguro**
- **Ficheiro:Linha:** auth_service.py:94-106
- **Descricao:** SHA-256 sem salt activa-se silenciosamente se passlib nao estiver instalado.
- **Sugestao:** Tornar passlib[bcrypt] dependencia obrigatoria.

**[Critical] _execute_query retorna [] em caso de erro em vez de propagar excepcao**
- **Ficheiro:Linha:** auth_service.py:55-57
- **Descricao:** Erro de BD silenciado -> fallback para _DEFAULT_USERS (backdoor).
- **Sugestao:** Propagar excepcao; eliminar fallback para defaults.

**[Critical] Default users com password conhecida em memoria permanentemente**
- **Ficheiro:Linha:** auth_service.py:346-350
- **Descricao:** _DEFAULT_USERS sempre em memoria como backdoor quando BD falha.
- **Sugestao:** Eliminar completamente. Se BD indisponivel, login falha.

**[Major] change_password nao valida a password actual**
- **Ficheiro:Linha:** auth_compat.py:170-177
- **Descricao:** current_password e Optional e nunca verificado.
- **Sugestao:** Tornar obrigatorio e validar antes de alterar.

**[Major] Router importa funcoes internas do service (_execute_query, _execute_update)**
- **Ficheiro:Linha:** auth_compat.py:14
- **Descricao:** Quebra separacao de camadas — router executa SQL directamente.
- **Sugestao:** Mover logica de preferencias para PreferencesService.

**[Major] Logout nao invalida o token**
- **Ficheiro:Linha:** auth_compat.py:147-149
- **Descricao:** JWT permanece valido ate expirar (24h). Sem blacklist.
- **Sugestao:** Implementar blacklist de tokens com TTL.

**[Major] _require_auth e _require_admin deviam ser FastAPI Dependencies**
- **Ficheiro:Linha:** auth_compat.py:60-75
- **Descricao:** Chamadas manuais sao error-prone. Nao aproveita Depends().
- **Sugestao:** Converter para Depends().

**[Major] Heartbeat in-memory nao escala e nao persiste**
- **Ficheiro:Linha:** auth_compat.py:349
- **Descricao:** Dicionario global sem cleanup, perde-se no restart.
- **Sugestao:** Adicionar cleanup e maxlen.

**[Major] system-config expoe configuracao sensivel**
- **Ficheiro:Linha:** auth_compat.py:315-342
- **Descricao:** Nomes de servidores, AD domain, databases na API.
- **Sugestao:** Filtrar campos sensiveis.

**[Minor] Fernet cipher recriado em cada chamada**
- **Ficheiro:Linha:** auth_compat.py:81-89
- **Descricao:** N instanciacoes por request.
- **Sugestao:** Lazy singleton.

**[Minor] datetime.utcnow() deprecated desde Python 3.12**
- **Ficheiro:Linha:** auth_service.py:147-148
- **Sugestao:** Usar datetime.now(timezone.utc).

**[Minor] Auth log query sem limite superior**
- **Ficheiro:Linha:** auth_compat.py:266
- **Sugestao:** Impor limit = min(limit, 1000).

**[Minor] Erro no delete de preferencia silenciado e devolve success: True**
- **Ficheiro:Linha:** auth_compat.py:258-259
- **Sugestao:** Devolver HTTP 500 ou success: False.

**[Suggestion] Schema: Preferences sem FK para Users**
- **Ficheiro:Linha:** CREATE_USER_AUTH_PREFS.sql:51-59
- **Sugestao:** Adicionar FK com ON DELETE CASCADE.

---

## PERSONA 2: SECURITY TESTING (Pentester)

### 16 Findings

| Severidade | Titulo | CWE | Ficheiro |
|-----------|--------|-----|----------|
| CRITICAL | JWT Secret hardcoded | CWE-798 | auth_service.py:15 |
| CRITICAL | SQL Injection sem auth (custom queries) | CWE-89 | watcherdb_main.py:3164 |
| CRITICAL | Credenciais default admin123 | CWE-798 | auth_service.py:346 |
| HIGH | Change password sem verificacao | CWE-620 | auth_compat.py:170 |
| HIGH | SHA-256 fallback sem salt | CWE-916 | auth_service.py:103 |
| HIGH | CORS wildcard com credentials | CWE-942 | watcherdb_main.py:2588 |
| HIGH | JWT em localStorage (XSS vuln) | CWE-922 | portal.html:4031 |
| MEDIUM | DOM XSS via user profile fields | CWE-79 | portal.html:4182 |
| MEDIUM | User enumeration via timing | CWE-203 | auth_service.py:407 |
| MEDIUM | Fernet degrada para plaintext | CWE-311 | auth_compat.py:81 |
| MEDIUM | Heartbeat memory exhaustion | CWE-400 | auth_compat.py:349 |
| MEDIUM | Info disclosure via system-config | CWE-200 | auth_compat.py:315 |
| MEDIUM | Logout nao invalida token | CWE-613 | auth_compat.py:147 |
| LOW | JWT expiration 24h excessiva | CWE-613 | auth_service.py:17 |
| LOW | Sem password complexity | CWE-521 | auth_service.py:474 |
| INFO | Sem rate limiting por IP | CWE-307 | auth_compat.py:119 |

**Risco Global: CRITICO** — 3 vulns criticas permitem acesso total nao autenticado.

---

## PERSONA 1: FUNCTIONAL TESTING (QA Analyst)

### 25 Test Cases (BDD)

**CRITICAL (TC-01 a TC-08):**
- TC-01: Login com credenciais validas (happy path)
- TC-02: Login com password incorrecta e lockout apos 5 tentativas
- TC-03: Login com conta desactivada
- TC-04: JWT expirado provoca auto-logout
- TC-05: Token JWT com payload manipulado rejeitado
- TC-06: Utilizador desactivado com token ainda valido
- TC-07: Viewer tenta aceder endpoint admin (403)
- TC-08: Isolamento de sessao localStorage com prefixo user-scoped

**HIGH (TC-09 a TC-16):**
- TC-09: Migracao de chaves antigas (sem prefixo)
- TC-10: Persistencia de preferencias apos re-login
- TC-11: Login via Active Directory (LDAP) com auto-provisioning
- TC-12: AD user tenta login local quando AD indisponivel
- TC-13: Admin nao pode desactivar a propria conta
- TC-14: Admin nao pode alterar o proprio role
- TC-15: Sync de preferencias ao logout
- TC-16: Validacao de token no page load (checkAuthOnLoad)

**MEDIUM (TC-17 a TC-22):**
- TC-17: Custom queries persistidas por utilizador
- TC-18: Role invalido rejeitado
- TC-19: Preferencia com chave > 100 chars rejeitada
- TC-20: Comportamento offline (network error)
- TC-21: Encriptacao Fernet round-trip
- TC-22: restoreUserSession restaura servidor e tab

**LOW (TC-23 a TC-25):**
- TC-23: Login com campos vazios
- TC-24: Fallback SHA256 quando bcrypt indisponivel
- TC-25: Heartbeat com janela de 5 minutos

### Bugs Potenciais Identificados
1. **CRITICAL:** change_password ignora current_password
2. **HIGH:** JWT_SECRET_KEY hardcoded em dev
3. **MEDIUM:** syncPreferencesToServer no logout e fire-and-forget (async sem await)
4. **MEDIUM:** _active_heartbeats nao persiste entre restarts

---

## PERSONA 3: PERFORMANCE TESTING (Load/Stress)

### Scripts Locust Criados

Localizacao: `tests/performance/`

| Script | Cenario | Comando |
|--------|---------|---------|
| locustfile_baseline.py | Baseline (1 user) | `locust -f tests/performance/locustfile_baseline.py -u 1 --run-time 2m` |
| locustfile_concurrent.py | 10 users simultaneos | `locust -f tests/performance/locustfile_concurrent.py -u 10 --run-time 5m` |
| locustfile_stress.py | Stress points (bcrypt, pool, prefs) | `locust -f tests/performance/locustfile_stress.py -u 10 --run-time 3m` |
| locustfile_resource_exhaustion.py | Resource leaks (15 min) | `locust -f tests/performance/locustfile_resource_exhaustion.py -u 5 --run-time 15m` |
| run_all_tests.py | Runner master | `python tests/performance/run_all_tests.py` |

### Bottlenecks Identificados
1. **bcrypt CPU-bound:** verify_password e sync, bloqueia event loop (~250ms/call)
2. **Connection pool:** max_connections=10 com threading.Lock
3. **Preferences sem batching:** N MERGEs = N round-trips SQL
4. **_active_heartbeats:** memory leak sem cleanup

### Thresholds de Aceitacao
| Metrica | Baseline | Concorrente (10 users) |
|---------|----------|------------------------|
| Login p95 | < 2000ms | < 3000ms |
| Validate p95 | < 100ms | < 200ms |
| Heartbeat p95 | < 100ms | < 200ms |
| Error rate | 0% | < 1% |

---

## PERSONA 6: DATA INTEGRITY TESTING (DBA)

### 12 Findings

| Severidade | Finding | Localizacao |
|-----------|---------|-------------|
| Critical | JWT_SECRET_KEY hardcoded | auth_service.py:15 |
| Critical | Default password admin123 | auth_service.py:346, SQL:72 |
| High | MERGE sem HOLDLOCK (race condition) | auth_compat.py:228 |
| High | WITH (NOLOCK) em queries de auth | auth_service.py:370 |
| High | Fernet decrypt falha -> dados irrecuperaveis | auth_compat.py:103-113 |
| Medium | TOCTOU no lockout counter | auth_service.py:527 |
| Medium | Auth_Log sem cleanup (crescimento ilimitado) | SQL:32-46 |
| Medium | Missing FK em User_Preferences | SQL:51-59 |
| Medium | Missing CHECK constraint no role | SQL:16 |
| Low | Auth_Log silencia erros de INSERT | auth_service.py:555 |
| Low | SELECT * expoe password_hash | auth_service.py:371 |
| Low | NVARCHAR sizes adequados | N/A |

### Queries Corrigidas Propostas
- MERGE com HOLDLOCK para atomicidade
- Remover NOLOCK em queries de autenticacao
- Parametrizar f-strings no increment_failed_attempts
- Job sp_Cleanup_AuthLog com retencao de 90 dias
- FK + CHECK constraints no schema

---

## PERSONA 5: ACCESSIBILITY TESTING (UX/WCAG)

### 20 Issues WCAG 2.1

**Nivel A (13 issues):**
1. Inputs de login sem `<label>` associado (1.3.1)
2. Labels sem atributo `for` no control panel (1.3.1)
3. Modais sem `role="dialog"` e `aria-modal` (4.1.2)
4. Ausencia de focus trap nos modais (2.4.3)
5. Modais nao fecham com Escape (2.1.1)
7. SVG logo sem texto alternativo (1.1.1)
8. Botoes de icone sem `aria-label` (4.1.2)
9. Icones FontAwesome sem `aria-hidden` (1.3.1)
10. Sidebar sem role de navegacao (1.3.1)
11. Items de servidor usam div clicavel (2.1.1)
12. Dropdown de perfil sem ARIA (4.1.2)
13. Tabs no control panel sem ARIA tabs pattern (4.1.2)
20. Layout sem landmarks semanticos (1.3.1)

**Nivel AA (7 issues):**
6. `outline: none` remove indicador de foco (2.4.7)
14. Contraste insuficiente #64748b sobre #1e293b (1.4.3)
15. Contraste insuficiente #475569 (1.4.3)
16. Live region ausente para erros e toasts (4.1.3)
17. Autocomplete sem ARIA combobox pattern (4.1.2)
18. Sem media queries responsivas < 1024px (1.4.10)
19. Tabelas sem scroll horizontal (1.4.10)

---

## CONCLUSAO

O WatcherDB V3.1 tem uma base arquitectural solida (FastAPI, JWT, LDAP hibrido, sync de preferencias com encriptacao), mas precisa de atencao imediata em 5 areas criticas de seguranca antes de qualquer exposicao em rede. As correcoes de maior impacto sao:

1. **Eliminar backdoors** (default users, fallback SHA-256, JWT secret hardcoded)
2. **Proteger custom queries** (autenticacao + whitelist de comandos)
3. **Corrigir change-password** (validar password actual)
4. **Restringir CORS** (dominio especifico)
5. **Sanitizar outputs HTML** (prevenir DOM XSS)

Scripts de teste de performance estao prontos em `tests/performance/` para validacao continua.
