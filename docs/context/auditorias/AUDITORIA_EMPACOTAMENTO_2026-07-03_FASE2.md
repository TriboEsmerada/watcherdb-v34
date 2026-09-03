# Auditoria Empacotamento — FASE 2 (Arquitetura de instalação alvo)

Data: 2026-07-03 | Agente: orquestrador (design), sobre evidência das Fases 0-1
Fases anteriores: FASE0.md (raio-X), FASE1.md (21 achados, 5×B0)
Gate Fase 2: AGUARDA revisão do owner.

Princípio orientador: reutilizar padrões que JÁ existem no repo e estão certos
(licensing 3-tier crl.py:140; secrets DPAPI services/secrets.py; MajorUpgrade/
perMachine/preservação ProgramData do Product.wxs) e alinhar o resto a eles.

## 1. Layout — onde vai o quê (e porquê)

%ProgramFiles%\WatcherDB\V3.3\          [READ-ONLY, componentes MSI]
├─ watcherdb.exe + _internal\           bundle PyInstaller onedir
├─ templates\  static\                  assets imutáveis
└─ keys\ed25519_public.pem              chave pública licensing (imutável)
Justificação: código imutável em Program Files com ACL default (Users=RX) é
exatamente o que se quer em banking — integridade por ACL, substituição só via
MSI. NADA de escrita aqui (corrige B0-4).

C:\ProgramData\WatcherDB\               [DATAFOLDER — já criado pelo MSI]
├─ license.dat, revoked_licenses.json, install_marker.json   (como hoje)
├─ config\    sql_servers.json, servers.json, custom_queries.json,
│             alerts.json, config.yaml, .env        [editável DBA + serviço]
├─ data\      watcherdb_cache.db, tap_servers.db, dashboard_snapshot.json
├─ logs\      service.log, errors.log, stdout.log, stderr.log, audit.log
└─ secrets\   jwt_signing.key.dpapi, fernet_master.key.dpapi
Justificação ProgramData (não AppData): a app corre como SERVIÇO machine-wide
sem perfil interativo; quem edita config (DBA admin) não é a conta que executa.
AppData é per-user — errado por definição para serviço. ProgramData é a
convenção Windows para estado machine-wide de serviços.

ACLs (definidas no MSI, herdadas):
- ProgramData\WatcherDB raiz: SYSTEM + Administrators Full (como hoje).
- config\, data\, logs\: + conta do serviço Modify (via ServiceAccount property
  → ACE no MSI; NetworkService por SID bem conhecido S-1-5-20).
- secrets\: SYSTEM + Administrators + conta do serviço APENAS. Sem Users.
Resolução no código: novo watcherdb/core/paths.py com resolver 3-tier
(WATCHERDB_DATA_DIR env → C:\ProgramData\WatcherDB → _PROJECT_ROOT p/ dev),
espelhando crl.py:140. Todos os ~15+ call-sites da Fase 1 migram para ele.

## 2. Segredos (ficheiro plano = B0; decisão: DPAPI machine-scope)

Reutilizar services/secrets.py (Tier 2 DPAPI-wrapped Fernet) com 2 correções:
1. MACHINE-SCOPE (CRYPTPROTECT_LOCAL_MACHINE) em vez de user-scope: o blob é
   criado pelo Admin no install/first-run mas desencriptado pela conta do
   serviço — user-scope DPAPI quebraria (contas diferentes). Proteção de
   confidencialidade passa a ser a ACL de secrets\ (por isso ela é restrita).
2. Blob em FICHEIRO ACL'd (secrets\*.dpapi), NÃO em env var de sistema: env
   vars machine ficam no registry legível por Users — pior que ficheiro ACL'd.
Segredos cobertos: JWT signing key (gerada no first-run se ausente — fecha
B1-8, sessões sobrevivem a restart); Fernet master key (passwords SQL nos
JSONs mantêm o prefixo "encrypted:" atual); credenciais SMTP/webhooks.
Alternativa descartada — Windows Credential Manager: store é per-user (gestão
sob NetworkService é opaca p/ DBA), sem vantagem sobre DPAPI+ACL, e DPAPI já
está implementado e testado no repo. Menos peças novas.

## 3. Modelo de execução

- UM serviço Windows (mantém): WatcherDBWebServiceV33, processo único
  (uvicorn 1 worker + APScheduler in-process + asyncio tasks). Sem Task
  Scheduler, sem segundo processo — nada na Fase 0/1 justifica separar.
- Mecanismo (decisão B0-1) — RECOMENDAÇÃO: opção (a) fundir ServiceFramework
  no entry point frozen (sys.frozen + StartServiceCtrlDispatcher; uvicorn em
  thread; SvcStop gracioso; redirect stdout/stderr para logs\ — padrão já
  escrito em services/web_service/service.py, é migração, não invenção).
  Porquê não wrapper WinSW/NSSM (b): é mais um exe de terceiro para assinar,
  whitelistar no EDR do cliente e auditar em supply-chain banking; pywin32 já
  está no bundle (spec já declara os hidden imports). (b) fica como plano B
  documentado se (a) emperrar em PyArmor/PyInstaller no rebuild.
- Conta de execução — RECOMENDAÇÃO: NetworkService (default) + SQL-auth
  sql_monitoring (identity flip B0-2). Least privilege, zero dependência de
  AD para instalar, alinha Regra de Ouro #2. Conta AD dedicada = OPCIONAL
  documentado (property SERVICEACCOUNT já existe), só para desbloquear
  WinRM/WMI remoto (B1-10) — feature opt-in, não requisito de instalação.
- Arranque: auto DELAYED (DelayedAutoStart no ServiceConfig) — evita corrida
  com rede/DNS no boot. Dependências declaradas: Tcpip, Dnscache. NÃO declarar
  MSSQLSERVER (o SQL Server é remoto; dependência local seria errada).
- Recovery: manter 30s/60s + reset 24h (já correto no wxs); acrescentar
  fail-loud — Event Log no crash + heartbeat file em logs\.
- Event Log source: registado pelo MSI (componente registry) para os eventos
  1000/1001 do licensing funcionarem sob NetworkService (sem registo, escrita
  de source falha para contas não-admin).
- Firewall: regra inbound TCP 8433 criada no INSTALL e removida no UNINSTALL
  (WiX FirewallExtension ou passo idempotente no install.ps1). Perfis
  parametrizáveis (property FIREWALL_PROFILES, default Domain+Private) —
  lição do incidente 2026-06-12: cobrir o perfil da interface REAL.
- Porta: property MSI WEBPORT (default 8433) → env WATCHERDB_PORT do serviço
  (elemento <Environment>) ou config — fecha B0-5. Preflight lê a mesma SOT.
- Instância única: SCM já garante 1 instância do serviço; acrescentar named
  mutex global (Global\WatcherDBV33) no arranque para impedir exec manual
  paralela contra o mesmo data dir (fecha o gap da Fase 0). Esforço S.

## 4. Ciclo de vida

Primeira instalação:
preflight_target.ps1 → msiexec /i (per-machine; properties: INSTALLFOLDER,
SERVICEACCOUNT/SERVICEPASSWORD, WEBPORT, FIREWALL_PROFILES, INTELLIGENCE_SERVER)
→ MSI: dirs+ACLs, serviço, firewall, EventSource → arranque do serviço.
Silent install SCCM/Intune: msiexec /qn com as mesmas properties — TODAS as
fases num só MSI; sem dependência de python.exe externo (fecha B2-14).

Primeira execução (bootstrap NO CÓDIGO, não wizard Python externo):
- config skeleton criado de templates se ausente (fecha B0-3: bundle leva só
  templates vazios; inventário do cliente nasce vazio);
- JWT signing key gerada e DPAPI-wrapped se ausente;
- licensing grace period como hoje (install_marker.json).
- Configuração guiada: página de setup no PORTAL (admin-gated, aparece quando
  config vazio) em vez de industry_wizard.py CLI — o cliente não tem Python.
  industry_wizard/farm_inventory: ou embutidos como watcherdb.exe --setup, ou
  formalmente marcados roadmap (decisão Fase 4; outputs hoje não são lidos
  por nada — evidência B2-14).

Upgrade (in-place):
- MajorUpgrade como hoje; ProgramData INTOCADO (config/dados/logs/licença
  preservados — fecha B0-4 clobber, porque config sai do harvest do MSI);
- migração de config por config_version + migrator idempotente e ADITIVO no
  arranque (regra: migrações só acrescentam chaves — garante compat N-1);
- binários substituídos por inteiro (onedir favorece substituição atómica).

Rollback de upgrade falhado:
- durante o msiexec: transação MSI reverte sozinha;
- pós-upgrade (serviço não sobe): reinstalar MSI N-1 (vendor guarda sempre o
  instalador anterior; migrações aditivas garantem que o config novo não
  quebra o binário antigo). Runbook documentado no INSTALL_GUIDE.

Uninstall:
- remove: Program Files, serviço, regra de firewall, Event Log source;
- PRESERVA deliberadamente: C:\ProgramData\WatcherDB\ (licença, config,
  histórico, logs) — reinstalação/upgrade recupera o estado; documentar o
  purge manual completo para offboarding definitivo.

Update strategy (instalador novo vs auto-update): decisão fica para a FASE 3
— o updater cliente não existe hoje (Fase 0) e a escolha depende do
comparativo de tecnologias. O layout acima não bloqueia nenhuma das vias.

## 5. Multiusuário

Per-machine, sem alternativa sensata: é um serviço com porta partilhada e
licença por máquina (fingerprint BIOS/CPU/hostname). Per-user install não tem
significado aqui. O multiusuário REAL é o RBAC do portal (auth AD/local por
browser), não o instalador. Já está correto no wxs (InstallScope perMachine +
MSIINSTALLPERUSER=0) — manter.

## Mapa achado→elemento da arquitetura

B0-1→§3 mecanismo (a); B0-2→§3 conta+SQL-auth; B0-3→§4 first-run skeleton;
B0-4→§1 layout+ACL+config fora do harvest; B0-5→§3 WEBPORT; B1-6/7→§1 resolver
paths.py; B1-8→§2 JWT DPAPI + §1 .env em ProgramData\config; B1-9→fix mecânico;
B1-10→§3 conta AD opcional; B1-11→§3 firewall; B1-12→Fase 3/4 (build repro);
B2-13→Fase 3 (signing); B2-14→§4 silent install + wizard embutido/roadmap;
B2-15..18, B3-*→Fase 4 (mecânicos).

## Decisões em aberto que transitam

1. Fase 3: congelamento (manter PyInstaller onedir+PyArmor vs alternativas,
   peso dobrado AV/EDR), tecnologia de instalador (validar WiX vs alternativas),
   signing OV vs EV + plano B, update strategy.
2. Fase 4: destino do industry_wizard (embutir vs roadmap); steelman
   obrigatório contra o instalador (challenger).
