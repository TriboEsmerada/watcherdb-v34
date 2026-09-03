# Plano — FRENTE 2: migrar o collector_service para servidor sempre ligado

**Data:** 2026-08-04 · **Estado:** PROPOSTA / documento de decisão (nada aplicado)
**Autor:** watcherdb-deploy-architect (gate) + orquestrador · **Input:**
[PROPOSTA_MIGRACAO_WORKSTATION_SERVIDOR_2026-08-04.md](PROPOSTA_MIGRACAO_WORKSTATION_SERVIDOR_2026-08-04.md)

A Frente 1 (baseline → SQL Agent job) está fechada. Esta é a Frente 2: mover o
`collector_service` (serviço Windows pywin32 + APScheduler, ~118 tasks, fonte de
TODOS os KPIs) + o `Liveness_Watchdog` do workstation do dev para um servidor
Windows sempre ligado. O collector NÃO pode virar SQL Agent job (precisa de
Python real). Move-se tal-e-qual, muda só o host.

---

## 0. BLOQUEADOR encontrado no gate (tem de sair primeiro)

**`service.py:519-527` — o manual run poller ("Run now" do portal) tem a
connection string hardcoded com `Trusted_Connection=yes; SERVER=SQLHDSTST505\I01`.**
Verificado no código (linhas 521-527) + confirmado que `service.py` **não
importa `ServerManager`** (grep zero) — logo esta é a única via de ligação do
serviço que ignora o `sql_monitoring`/`ServerManager`. Dois problemas num só:

1. **Viola a Regra de Ouro #2** — liga à BD por Windows Auth (a identidade do
   serviço), não por `sql_monitoring`. Hoje "funciona" porque a identidade
   Windows do serviço tem acesso acidental à BD.
2. **Bloqueia a Frente 2** — se dermos ao serviço uma conta AD dedicada, o
   poller passa a ligar-se à BD **com esse domain user nomeado**, que é
   exactamente o que a Regra de Ouro #2 proíbe (pior que hoje).
3. **Bónus:** liga por nome de instância (`SQLHDSTST505\I01`) → sujeito ao
   mesmo 08001 do SQL Browser/firewall que aflige o baseline.

**Fix (FASE 0, obrigatório antes de qualquer mudança de host):** substituir a
connection string hardcoded por uma construída via `ServerManager`
(`get_master_server()` + padrão de `base_collector.get_connection_string()`,
que usa `UID=sql_monitoring`), com override `ip,porta` para dodgear o Browser.
Registado como **FIND-20260804-108**. É fix de código → bloco/aprovação do owner
(Regra de Ouro #1).

---

## 1. Qual servidor (DECISÃO DO OWNER)

| Opção | A favor | Contra |
|---|---|---|
| **A — co-localizado em SQLHDSTST505** (o próprio servidor de BD) | Mata a firewall E o Browser para este componente (liga por localhost/named pipe, sem depender da porta estática); precedente robusto (17 SQL Agent jobs já lá) | **Blast radius partilhado**: o crash nativo histórico do collector (`0xc0000005`, FIND-20260702-001, causa-raiz não resolvida) passa a correr na mesma caixa que a BD de produção; 118 tasks + ThreadPool(20)+ProcessPool(5) = ruído de recursos que uma DBA team tipicamente não aceita sem sign-off; patches/reboots acoplados |
| **B — member server dedicado**, mesma VLAN | Separação limpa app vs BD (o padrão que o cliente banking vai exigir); reboot do SQL não arrasta o collector | **Mantém a dependência da porta dinâmica/Browser** até a porta estática ser resolvida (o member server sofre o mesmo 08001); a regra de firewall pedida cobre só a sub-rede dos postos (`172.17.0.0/17`), NÃO um member server novo — teria de ser reescrita; mais um servidor para manter |

**Recomendação:** A só é aceitável se a DBA/infra do cliente aprovar workload
Python num servidor de BD (hoje é TST, risco político menor, mas o padrão
repete-se em PRD banking onde isto costuma ser vetado). Se o objectivo é já
desenhar para banking, **B é o correcto** — mas então reescrever o pedido de
porta estática para cobrir o member server.

## 2. Identidade do serviço (DECISÃO DO OWNER)

Depois do fix do poller (§0), a matriz:

| Superfície | Identidade |
|---|---|
| SQL Server | **`sql_monitoring`** (SQL Auth, já correcto; Fernet portável, não DPAPI) — sem mudança |
| Windows SCM ("Log on as a service") | **Domain User dedicado** `svc_watcherdb_collector@<domínio>` (não LocalSystem, não gMSA por agora) |
| PowerShell (Get-ScheduledTask, audit Fase 2) | leitura de metadados, **não exige admin** |
| Ficheiros (`key.key`, `.enc`, `servers.json`, logs) | ACL NTFS restrita ao service account (read-only no código, read+write em logs/health) |
| Poller (pós-fix) | nenhuma — deixa de usar Windows Auth |

**Regra:** a conta AD nunca aparece numa connection string (garantido pelo fix
do poller). Zero privilégio SQL directo à conta de domínio.

## 3. Instalação no servidor — o que muda

- **Deploy é da árvore INTEIRA do projecto** (não só `services/collector_service/`):
  `service.py` e `base_collector.py` usam `PROJECT_ROOT = parent.parent.parent`
  e importam `watcherdb_intelligence`. Copiar `watcherdb_intelligence/`,
  `scripts/collectors/`, `services/collector_service/`, `config/`.
- **ODBC Driver 17 for SQL Server** instalado à parte (não vem no pip), x64.
- Python 3.11+, venv (`requirements.txt`: pywin32>=305, apscheduler, pyyaml,
  pyodbc>=5, structlog, pandas, numpy, cryptography, psutil, requests).
- `install.py install --account DOMAIN\svc_watcherdb_collector --password ***`
  (como Administrator; `sc config start=auto` já é automático).
- **DÍVIDA a resolver ANTES:** existem **2 cópias divergentes de `servers.json`**
  (`config/` vs `services/collector_service/config/`) — flag `use_windows_auth`
  e `enabled` divergem (Q9 de FIND-20260425-002, aberta desde Abril). Migrar sem
  reconciliar = herdar a dívida para um ambiente mais crítico. **Resolver antes.**

## 4. Cutover — porquê não dual-write, e o plano faseado

**Não correr os dois em paralelo por dias:** `base_collector.store()` faz
TRUNCATE+INSERT inline **sem lock** (o `sp_getapplock` só protege o swap final),
logo dois collectors a escrever na mesma `_STG` para o mesmo KPI/ambiente = corrida
real (linhas perdidas/duplicadas). **Cutover sequencial curto (minutos).**

- **Fase 0 — pré-requisitos (bloqueadores):** fix do poller (§0); reconciliar
  `servers.json` (Q9); decisão servidor+conta; provisionar servidor (Python+ODBC+venv);
  gate `install.py validate` sem arrancar.
- **Fase 1 — deploy a frio:** copiar árvore + secrets; `install.py install`;
  **NÃO iniciar**; validar `STOPPED` + ACLs.
- **Fase 2 — cutover (minutos):** parar no workstation → confirmar STOPPED →
  iniciar no servidor → confirmar RUNNING + health a bater → observar 15-30 min
  (1 ciclo de cada família de tasks curtas grava dados, sem erros). Gap esperado:
  minutos (tolerado por `misfire_grace_time=300`).
- **Fase 3 — observação 24-48h:** Liveness ALIVE estável; sem degradação nova na
  Fase 1 do verificador; sem HUNG/SERVICE_DOWN.
- **Fase 4 — decomissionar workstation:** `install.py remove`; desregistar a task
  do Liveness; confirmar zero `WatcherDB*` no Task Scheduler do workstation.

**Rollback:** o workstation fica instalado-mas-parado até a Fase 3 passar — é o
rollback mais barato (sc stop no servidor + sc start no workstation, minutos). BD
é a fonte de verdade, sem perda de dados.

## 5. O que segue o collector

- **Liveness_Watchdog** (lê sinais locais: SCM + `service_health.txt`) — por
  desenho corre no mesmo host; registar no servidor, desregistar no workstation
  (Fase 4), senão fica watchdog órfão a dar falsos SERVICE_DOWN.
  **Gap sinalizado:** o `setup_watchdog_task.ps1` referenciado no docstring **não
  foi encontrado no repo** (grep zero) — confirmar se existe fora do repo ou se os
  parâmetros da task têm de ser reconstruídos/versionados antes da Fase 1.
- **Fase 2 do verificador** (`collect_scheduled_tasks_audit.py`): o
  `Get-ScheduledTask` corre sempre **local ao host do collector** (sem `-CimSession`).
  Pós-migração passa a auditar o Task Scheduler do **servidor**. O
  `WDB_SCHEDULED_WORK_MANIFEST` **não tem coluna `Host`** → assume implicitamente
  que todo `SCHEDULED_TASK` vive no host do collector. Aceitável com 1 host;
  documentar via `Notes` que o host esperado é o servidor. Coluna `Host` = Wave D
  futura, só se surgir necessidade multi-host.

## 6. Riscos

| Risco | Sev | Mitigação |
|---|---|---|
| Poller `Trusted_Connection` hardcoded | **Alta/bloqueador** | Fix §0 antes de tudo (FIND-108) |
| 2 cópias divergentes de `servers.json` | Média-alta | Reconciliar antes da Fase 1 |
| Crash nativo `0xc0000005` intermitente (causa-raiz aberta) | Média | Servidor novo = SO/hardware diferente; vigiar `faulthandler.log` nas 48h da Fase 3 |
| Windows Server vs Win11 (Server Core?) | Baixa-média | pywin32/apscheduler/pyodbc/pandas todos Server-compatíveis; confirmar módulo `ScheduledTasks` (built-in Server 2012R2+) e post-install do pywin32 sem GUI |
| `setup_watchdog_task.ps1` ausente do repo | Baixa | Confirmar antes da Fase 1 |
| PyArmor | Nenhum | V1 não está obfuscado (grep zero) |

## Decisões que aguardam o owner

1. **Servidor:** A (co-localizado) vs B (member server dedicado) — e se B, hostname/IP.
2. **Conta AD:** nome do service account (condicionado ao fix do poller no mesmo wave).
3. **Reconciliação `servers.json`** (Q9): antes da migração (recomendado) ou aceitar divergência.
4. **Janela de cutover:** disponibilidade para stop/start sequencial (minutos).
5. **`setup_watchdog_task.ps1`:** existe fora do repo ou reconstruir?
