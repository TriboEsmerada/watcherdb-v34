# Vendor Keypair Rotation Runbook

**Audience:** WatcherDB vendor team (TAP DBA / WatcherDB maintainers)
**Scope:** Rotação do Ed25519 master keypair que assina TODAS as `license.dat`
**Risk level:** **🔴 ALTA** — rotação invalida todas as licenses emitidas. Não fazer casualmente.

---

## TL;DR

```
Manter rotação como exception, não routine.
Se rotacionar:  agenda 60-day grace overlap, comunica clientes ANTES, gera novas licenses, deploya public key novo, monitoriza Event Log 1001.
```

---

## Quando rotacionar

### Razões legítimas (autorizar rotação)

| Razão | Severity | Action |
|---|---|---|
| **Private key comprometida** (vazamento, USB perdida, breach workstation vendor) | 🔴 CRITICAL | Rotação **imediata** + revoke todas + emergency comm clientes |
| **Algoritmo deprecated** (NIST/RFC retira Ed25519 — improvável a curto prazo) | 🟡 PLANNED | Rotação agendada com 6m antecedência |
| **Compliance audit findings** (auditor banking pede rotação periódica) | 🟡 PLANNED | Cycle 24-36 meses (banking típico) |
| **Vendor team change** (key holder sai da empresa, succession plan) | 🟢 MEDIUM | Rotação coordenada com handover |

### Razões NÃO-legítimas

- "Boa prática rotacionar anualmente" — Ed25519 não tem cryptographic decay; rotação anual rotina é tradição RSA antiquada, não aplicável
- "Cliente pediu" — cliente não tem standing para forçar rotação master keypair
- "Vamos limpar testing" — DEV testing usa keypair separado em `tmp_path` (test fixtures); nunca rotaciona o de produção

---

## Pré-requisitos rotação

### 1. Inventário de clientes deployed

Antes de rotacionar, ter lista completa:
- Customer ID
- Servidor cliente (hostname + edition deployed)
- HW fingerprint actual (bios_uuid + cpu_id + hostname + sql_servername)
- Email contacto técnico (DBA Lead cliente)
- Window de manutenção possível (cliente banking típico: madrugada sábado)

Esta lista deve viver em CRM vendor / cliente registry — **não** no repo (PII concerns).

### 2. Backup do private key actual

Antes de qualquer rotação, **CONFIRMA** backup encrypted offline existe:

```powershell
# Verifica backup actual (NUNCA committar este path em git)
Test-Path "$env:USERPROFILE\.watcherdb-council-secrets\ed25519_private.pem"

# Backup adicional para offline media (Yubikey, LUKS USB, vault físico)
$backup_dir = "Z:\WatcherDB-Vendor-Keys-Archive\$(Get-Date -Format 'yyyyMMdd')"
New-Item -ItemType Directory -Path $backup_dir -Force
Copy-Item "$env:USERPROFILE\.watcherdb-council-secrets\ed25519_private.pem" "$backup_dir\"
Write-Host "Backup at: $backup_dir"
```

**Storage:** chave actual NÃO destruir mesmo após rotação — clientes legacy podem precisar re-emit (especialmente se emergency rotation).

### 3. Comm plan (announce 30 dias antes)

Email a TODOS os clientes deployed:
- Subject: "WatcherDB License Renewal Required — Keypair Rotation YYYY-MM-DD"
- Razão de rotação (sem detalhes de breach se aplicável — só "scheduled key refresh")
- Action required: novo `.lic` file + novo `ed25519_public.pem` para deploy
- Timeline: data rotação + 60-day grace overlap (FIND-005 grace_period.py protect against outage)
- Contacto técnico vendor

---

## Procedimento rotação

### Step 1 — Generate new keypair

```powershell
cd C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3
python deploy\generate_license_keys.py --force
```

⚠️ `--force` é **destrutivo** — sobrescreve `ed25519_private.pem` existente.

Resultado:
- `%USERPROFILE%\.watcherdb-council-secrets\ed25519_private.pem` (NEW)
- `deploy\keys\ed25519_public.pem` (NEW)

### Step 2 — Re-issue licenses para clientes activos

Para cada cliente do inventário (Step 1.1 do prep):

```powershell
python deploy\license_cli.py issue `
    --customer-id <existing-uuid> `
    --customer-name "<existing-name>" `
    --edition <existing-edition> `
    --industry <existing-industry> `
    --regimes <existing-regimes> `
    --bios-uuid <CLIENT-HW> --cpu-id <CLIENT-HW> --hostname <CLIENT-HW> `
    --sql-servername <CLIENT-SQL-SERVERNAME-IF-BANKING> `
    --expires <new-expiry-date> `
    --license-id <NEW-UUID-PER-EMISSION> `
    --out .\rotation_<YYYYMMDD>\<customer-id>.lic
```

**Use batch mode para >5 clientes:**

```powershell
# customers_rotation.csv prepared from inventory
python deploy\license_cli.py batch `
    --input customers_rotation.csv `
    --output-dir .\rotation_<YYYYMMDD>\
```

### Step 3 — Distribute novas licenses + public key

Para cada cliente:

1. **Email seguro** (or vendor portal, signed channel):
   - Attach: `<customer-id>.lic` (new license)
   - Attach: `ed25519_public.pem` (new public key)
   - Instructions PowerShell para deploy (ver Step 4 cliente-side)

2. **Vendor commits** novo `ed25519_public.pem` ao repo:
   ```bash
   git add deploy/keys/ed25519_public.pem
   git commit -m "rotate(licensing): Ed25519 public key rotation YYYY-MM-DD

   Reason: <legitimate reason — see KEYPAIR_ROTATION_RUNBOOK.md>
   Old key fingerprint: <SHA256 of old public key>
   New key fingerprint: <SHA256 of new public key>
   All deployed customers re-issued individually.
   "
   ```

   Em next product build (MSI rebuild), bundle vai shippar com nova public key.

### Step 4 — Cliente deploy (instructions a enviar ao cliente)

```powershell
# Instructions cliente — copiar para email comm

# 1. Backup actual (precaution)
Copy-Item "C:\ProgramData\WatcherDB\license.dat" "C:\ProgramData\WatcherDB\license.dat.bak.$(Get-Date -Format 'yyyyMMdd')"
Copy-Item "C:\ProgramData\WatcherDB\ed25519_public.pem" "C:\ProgramData\WatcherDB\ed25519_public.pem.bak.$(Get-Date -Format 'yyyyMMdd')"

# 2. Replace com novos files (vendor enviou)
Copy-Item "<path-to-new-license>.lic" "C:\ProgramData\WatcherDB\license.dat" -Force
Copy-Item "<path-to-new-pem>.pem" "C:\ProgramData\WatcherDB\ed25519_public.pem" -Force

# 3. Restart services
$services = @(
    "WatcherDBWebServiceV33",
    "WatcherDBV5WebService",
    "WatcherDBWebServiceV55",
    "WatcherDBWebServiceV6",
    "WatcherDB-V6-Hybrid"
)
foreach ($svc in $services) {
    if (Get-Service $svc -ErrorAction SilentlyContinue) {
        Restart-Service $svc -Force
        Write-Host "Restarted: $svc"
    }
}

# 4. Validate Event Log
Get-EventLog -LogName Application -Source WatcherDB -Newest 5 |
    Where-Object { $_.EventID -in @(1000, 1001) } |
    Format-List Source, EventID, Message
# Esperado: 1000 LICENSE_VALIDATION_OK
```

### Step 5 — Vendor monitoring (post-rotation)

Durante 7 dias após rotação, monitorizar:
- Event Log clientes (se acesso remoto autorizado) — procurar **1001 LICENSE_VALIDATION_FAILED**
- Customer support tickets (clientes que não rolled over)
- Grace period expiry: clientes que falham updates ainda têm 60d até strict fail

---

## Rollback (em caso de problema)

Se rotação introduz bug (signature validation breaking, etc.):

1. **Stop comunicação** — não enviar mais licenses novas
2. **Restore old keypair** do backup Step 1.2
3. **Rebuild + redeploy** com old public key
4. **Re-emit licenses** antigas para clientes que já fizeram update (com old key)
5. **Post-mortem** — porque é que rotação falhou

⚠️ Rollback **só funciona** se old `ed25519_public.pem` ainda for válido em runtime (i.e., `validator.py` aceita a old public key). Se key foi destroyed após rotação completar, rollback é **impossível**.

**Best practice:** keep old keypair em "deprecation mode" 6 meses pós-rotação antes de destroy permanente.

---

## Compliance / Audit trail

Cada rotação produz audit artefactos:

| Artefacto | Localização | Retenção |
|---|---|---|
| Old `ed25519_private.pem` | offline encrypted media (Yubikey/LUKS USB) | 6m pós-rotação min |
| New `ed25519_private.pem` | `%USERPROFILE%\.watcherdb-council-secrets\` | até next rotation |
| `ed25519_public.pem` history | git log do repo deploy/keys/ | indefinido (audit trail) |
| Inventário rotação | CRM vendor + email comms | 7 anos (SOC 2) |
| Customer ack confirmations | Email signed responses | 7 anos |

Para banking clients (DORA art. 16), incluir rotation events em "SBOM updates" + "Critical incident log" do cliente.

---

## Anti-patterns

❌ **Rotacionar anualmente "por hábito"** — Ed25519 não decay; rotação rotina = traição operacional sem benefício
❌ **Não testar dry-run primeiro** — sempre fazer rotação numa instância DEV antes de PRD
❌ **Destroy old key imediatamente** — perde ability de rollback + re-emit clientes ainda com old key
❌ **Anunciar pós-rotação** — cliente fica em outage até receber novos files; sempre announce 30 dias antes
❌ **Skipping public key git commit** — sem isso, próximo MSI build ainda tem old key embedded
❌ **Reusar UUID license_id** entre rotações — sempre `--license-id` novo para CRL futuro funcionar

---

## Cross-reference

- Generator: `WATCHERDB_V3.3/deploy/generate_license_keys.py`
- License CLI: `WATCHERDB_V3.3/deploy/license_cli.py`
- Runtime validator: `WATCHERDB_V3.3/watcherdb/licensing/validator.py`
- Public key resolution: `WATCHERDB_V3.3/watcherdb/licensing/startup_guard.py:_resolve_public_key_path`
- Grace period (protege rotação): `WATCHERDB_V3.3/watcherdb/licensing/grace_period.py`
- Findings: `watcherdb-council/findings-inbox.md` FIND-20260424-005, FIND-20260424-004

---

## Changelog

- **2026-04-25** — Initial runbook (FIND-20260424-005 follow-up). Pre-CRL.
- **TBD** — Update após CRL implementation (B5.2) — rotação não vai dispensar CRL para revogar licenses específicas sem rotacionar master.
