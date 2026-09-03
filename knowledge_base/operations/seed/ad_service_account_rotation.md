# AD Service Account Rotation (seed)

Procedimento para rotação periódica da conta de serviço AD usada pelo
`WatcherDBWebServiceV33`.

**Status:** SEED — extraído de `auth_compat.py` + commits Patch A/B/C/D.
**Cadence recomendada:** rotação semestral (180 dias) ou ad-hoc após incidente.

**Owner:** `watcherdb-deploy-architect`
**Reviewers:** `watcherdb-security-auditor`, DBA Lead cliente

---

## 1. Contexto

V3.3 autentica DBAs/admin via AD (LDAPS porta 636 default; LDAP 389 só com flag).
A service account é a identidade que:

1. **Bind LDAP** — V3.3 não usa bind anonymous; `_try_single_domain_bind` requer
   credenciais (`api/routers/auth_compat.py`, função extraída no Patch D)
2. **Run as service** — Windows Service `WatcherDBWebServiceV33` corre como
   esta conta (não LocalSystem)
3. **SQL Server access** — autentica em `WatcherDB_Intelligence` (Windows auth
   ou SQL auth, depende do cliente; Windows auth é preferred)

**Multi-domain (Patch D)**: V3.3 suporta múltiplos domínios; cada domínio pode ter
service account separada se preferred. `WatcherDB_System_Config.ad_domains` JSON
guarda config (sem credenciais — credenciais ficam em DPAPI / env vars).

### 1.1 Bind mode em V3.3 (audit 2026-05-05)

Confirmado por inspeção directa de `WatcherDB_System_Config` durante sweep
post-FIND-001 (DPAPI bind_password fix shipped em commit `1405e16`):

```sql
-- Estado actual ad_domains config:
ad_enabled         = true
ad_bind_user       = (empty)
ad_bind_password   = (empty)
ad_domains[0].domain  = "tapnet.tap.pt"
ad_domains[0].server  = "ldap://dchqprd02.tapnet.tap.pt"
ad_domains[0].bind_password = (empty)
```

Logo: V3.3 está em **modo Kerberos integrated bind** — usa credenciais
kerberos do Service Account Windows (token automatic do logon `ue_e-snetto@
tapnet.tap.pt` neste deploy). LDAP exchange via SASL GSSAPI = kerberos-encrypted
natively (mesmo com `ldap://` plaintext URL — GSSAPI envelope cobre o
exchange independentemente do transport).

**Implicações operacionais:**

- **Rotação**: rota-se a password do Service Account Windows (não há explicit
  bind_password em DB para rotar). Procedimento na secção 3 abaixo aplica-se
  no Active Directory (admin AD), não no Control panel V3.3.
- **DPAPI fix (FIND-001)**: continua valid como **safety net**. Se DBA novo
  no futuro entrar bind_password explicit via Control panel UI, o helper
  `_encrypt_bind_password` em `services/auth_service.py` encripta antes de
  persistir. Migration path automatic.
- **LDAPS (porta 636)**: lower priority em deploy actual porque GSSAPI já
  encripta credentials. LDAPS continua recomendado defense-in-depth (proteger
  search results + queries também), mas não é blocker compliance.
- **Banking audit (DORA/SOC 2)**: Kerberos integrated bind é audit-friendly —
  identidade rastreável via Service Account + AD audit log. Não há service
  password persistida em ficheiro/DB que possa vazar.

**DBA novo que herde este deploy:**

Se vê `bind_password` vazio em `ad_domains` JSON, **NÃO entra password**
preventivamente — o sistema funciona via kerberos. Adicionar password
explicit força o V3.3 a usar SIMPLE bind (em vez de GSSAPI), o que é
**downgrade** de segurança.

Apenas entrar password explicit se:
- DC não suporta GSSAPI (raro — todos os DCs Windows Server desde 2003)
- Service Account não tem permissões kerberos delegation adequadas
- Cliente explicitamente requere SIMPLE bind por policy

## 2. Trigger de rotação

- **Calendar:** 180 dias desde última rotação
- **Incident:** suspeita de compromise da credencial
- **HR event:** colaborador associado à conta saiu da equipa
- **Compliance:** auditor banking requer (SOC 2, ISO 27001 cycles)

## 3. Procedimento

### 3.1. Pré-requisitos

- Janela de manutenção declarada (V3.3 estará down ~5 min)
- Backup da config actual: `Copy-Item services/web_service/config.yaml config.yaml.bak.YYYYMMDD`
- DBA Lead avisado

### 3.2. Criar nova credencial

1. **Ao admin AD do cliente** (não V3.3 team):
   - Criar nova password forte (≥ 20 chars, alphanumeric + symbols)
   - Validar que conta tem `Log on as a service` policy + read no AD + (se SQL Server
     Windows auth) `db_datareader` em `WatcherDB_Intelligence` + `EXEC` em
     `usp_swap_kpi_stg_tables`
   - **Não desactivar a conta antiga ainda** (rollback path)

### 3.3. Update no V3.3

```powershell
# Como Administrator local na máquina V3.3
# 1. Stop service
Stop-Service WatcherDBWebServiceV33

# 2. Update credencial via services.msc
#    Services.msc > WatcherDBWebServiceV33 > Properties > Log On
#    Account: <new-domain>\<svc-account>
#    Password: <new-password>

# 3. Update env var ou config secret store (se aplicável)
#    DPAPI-encrypted credentials em config secrets:
#    deploy/install_production.ps1 tem helper Set-WatcherDBSecret

# 4. Start service
Start-Service WatcherDBWebServiceV33

# 5. Smoke test
Invoke-WebRequest http://localhost:8433/health
# Login com user AD do cliente — verificar log Patch C diagnostic
#   (commit 7c95c53: AD startup diag agora loga binding success/fail)
```

### 3.4. Validação

- [ ] Service activo (`Get-Service`)
- [ ] Health endpoint OK
- [ ] Login DBA cliente OK (single domain)
- [ ] Se multi-domain: login user de domínio adicional OK (Patch D, commit `691a529`)
- [ ] SQL Server access OK (verificar log de `_validate_database_health`)
- [ ] Logs de `service_health.txt` sem erros AD bind

### 3.5. Cleanup

Após 7 dias de runtime estável:

1. Admin AD desactiva conta antiga
2. Eliminar `config.yaml.bak.YYYYMMDD` (foi para backup off-host se aplicável)
3. Update `findings-inbox.md` se algum incident surgiu

## 4. Rollback

Se algo falhar nas primeiras 24h:

```powershell
Stop-Service WatcherDBWebServiceV33
# Reverter credencial via services.msc (conta antiga ainda activa, ver 3.5)
Copy-Item config.yaml.bak.YYYYMMDD services/web_service/config.yaml -Force
Start-Service WatcherDBWebServiceV33
```

Postar em `.nestor/bulletin/inbox.md` para `watcherdb-security-auditor` revisar.

## 5. Troubleshooting

| Sintoma | Causa provável | Fix |
|---|---|---|
| 401 AD bind após rotação | Password mal copiada | Re-set via services.msc (cuidado com auto-paste a inserir espaços) |
| Service start falha "logon failure" | Service account sem `Log on as a service` policy | Admin AD: Local Security Policy > User Rights Assignment |
| Login user OK mas dashboard vazio | SQL Server permissions revogadas | Re-grant `db_datareader` + EXEC `usp_swap_kpi_stg_tables` |
| Multi-domain user falha | `ad_domains` JSON com FQDN errado | Control panel UI > update config; ver commit `691a529` rationale |

## 6. Sensitivity gates aplicáveis

- **Não logar password** em qualquer ficheiro (incluindo session.log, bulletin)
- **Não commitar** `config.yaml` com credenciais reais (`.gitignore` cobre isto;
  validar antes de cada commit)
- **Não pôr este runbook customizado** (com nomes reais cliente) na KB local —
  fica em `deploy/customer-<nome>/` ou off-host

## References

- `api/routers/auth_compat.py` — auth pipeline (multi-domain Patch D)
- `services/web_service/config.yaml` — config template
- `deploy/install_production.ps1` — installer com Set-WatcherDBSecret helper
- `deploy/KEYPAIR_ROTATION_RUNBOOK.md` — rotação separada (Ed25519 license keys, scope diferente)
- Commit `691a529` — Patch D multi-domain
- Commit `7c95c53` — Patch A/B/C URI sanitize + silent-fail + diag
- ~/.nestor-library/shared/owasp_cwe/ — CWE-287 (auth), CWE-522 (creds), CWE-798 (hardcoded creds)
