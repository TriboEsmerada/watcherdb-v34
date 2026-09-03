# Auditoria Empacotamento — RUNBOOK Etapa 3a (ZIP + install.ps1 assinado)

Data: 2026-07-04 | Agentes: orquestrador + python-packaging-architect (drafts) +
watcherdb-deploy-architect (spec adversarial) | Owner: executa e comita.
Antecedentes: FASE4.md (roadmap/matriz), RUNBOOK_ETAPA2.md (errata 8 achados).

## 1. Entregáveis desta sessão

3 scripts desenhados, cross-checked e validados (parse PS + ASCII puro):

| Ficheiro | Destino | Função |
|---|---|---|
| build_release.ps1 | deploy\ | Orquestra release: gate pytest → build.py → sign PE+scripts → check MAX_PATH → stage → zip → SBOM → SHA256SUMS |
| install.ps1 | deploy\ (entra no ZIP) | Instalação idempotente no cliente: elevação, preflight, dirs+ACLs, bundle, wrap-master-key, license, EventSources, serviço, firewall, health, HKLM |
| uninstall.ps1 | deploy\ (entra no ZIP) | Stop+delete serviço, firewall, InstallDir; PRESERVA ProgramData sempre; EventSource preservada por default (-PurgeEventSource) |

Origem: drafts do packaging-architect corrigidos com 8 fixes do cross-check
contra a spec do deploy-architect (secção 3). Owner copia do scratchpad da
sessão para deploy\ (bloco de aplicação entregue em chat).

## 2. Decisões de design seladas

- **Shape**: `build_release.ps1 -Target zip|msi` (FASE4 §4.2); `-Target msi` = stub exit 3 até Etapa 3b. Passos clone-limpo/lockfile = backlog.
- **`start= delayed-auto`** (owner GO 2026-07-04): divergência DELIBERADA do MSI (`Product.wxs:165` usa auto). Evita corrida de arranque contra SQL/rede no boot. Ao fazer a Etapa 3b, decidir se o MSI adota delayed-auto também.
- **SOT**: tudo importa `release_vars.psd1` (`Import-PowerShellDataFile`); o bundle NÃO inclui deploy\, por isso build_release copia o .psd1 para o stage.
- **Failure actions** em paridade MSI: restart 30s / restart 60s / reset 24h (`sc failure ... reset= 86400 actions= restart/30000/restart/60000//0`).
- **`secrets\` ACL**: SYSTEM+Administrators F, conta de serviço **R** (não M). Prova em código: runtime só lê (`try_get_master_key`); a única escrita é `provision_master_key_file` via `wrap-master-key` ELEVADO no install; JWT não vive em secrets\ (`watcherdb/core/auth.py:25-36` — get_secret do .env encriptado ou efémero). `/inheritance:r` obrigatório (senão herda Users:RX de %ProgramData%).
- **DPAPI machine-scope**: `CRYPTPROTECT_LOCAL_MACHINE` = qualquer conta local decifra o blob. A ACL de secrets\ é a ÚNICA barreira intra-máquina; a cifra só protege exfiltração para fora da máquina. Documentar no runbook cliente. Mudar conta de serviço NÃO invalida a master key.
- **Health**: `GET http://localhost:8433/api/v3/health` (path exacto), timeout default **120s** (errata Etapa 2: EDR scan do bundle 147MB no 1º boot; 90s dava falso negativo + rollback desnecessário).
- **Duas EventSources** registadas pelo install: `"WatcherDB"` (licença 1000-1004, `startup_guard.py:29`) + `WatcherDBWebServiceV33` (servicemanager). `sc.exe create` puro NÃO regista nenhuma — sem isto os eventos de licença desaparecem silenciosamente do Event Log (gap SIEM banking). Uninstall preserva ambas por default.
- **HKLM\SOFTWARE\WatcherDB\3.3**: InstalledVersion + ServiceAccount (paridade Product.wxs:152-157). Upgrade com conta diferente → remove ACE da conta antiga automaticamente (registry diz qual era — não é guessing).
- **Assinatura**: signtool em lotes de 40 sobre TODOS os PE + `Set-AuthenticodeSignature` sobre install/uninstall/preflight/psd1. Razão: `ExecutionPolicy AllSigned` por GPO bloqueia scripts FILHO não assinados e `-ExecutionPolicy Bypass` não escapa a GPO. `-SkipSigning` = stub temporário com aviso explícito de que o ZIP não instala em clientes AllSigned.
- **Check MAX_PATH**: build falha (exit 6) se path relativo do bundle + `C:\Program Files\WatcherDB\V3.3\` > 240 chars — `Expand-Archive` sem LongPathsEnabled falha SILENCIOSAMENTE nesses ficheiros (bundle parcial, ImportError obscuro em runtime).
- **Upgrade**: stop (espera STOPPED real) → rename InstallDir para `.bak.<timestamp>` → bundle novo → ACLs → start → health; rollback manual documentado; backups não são purgados automaticamente. ProgramData NUNCA tocado (FIND S2-7).
- **gMSA**: conta termina em `$` → omitir `password=` por completo (passar password a gMSA = falha obscura do sc create).
- **SeServiceLogonRight (conta AD)**: SCM concede automaticamente, MAS GPO central de "Log on as a service" APAGA a concessão no próximo gpupdate → serviço falha dias depois. Install detecta best-effort (secedit /export /areas USER_RIGHTS) e AVISA a pedir inclusão no grupo da GPO; nunca falha o install por isto.
- **Gate pytest do build**: baseline hardcoded de 5 falhas conhecidas (4 hygiene + 1 startup_guard), compara por chave junit; falha só em falhas NOVAS; `-SkipTests` com aviso forte. Mover para ficheiro externo = questão aberta Q5.
- **Firewall**: default `-Profile Domain,Public` (lição 2026-06-12) + `-RemoteSubnet` CIDR (vazio = Any com aviso). NÃO reutilizar `services/web_service/scripts/configure_firewall.ps1` (porta 8443 errada + perfil sem Public).

## 3. Cross-check adversarial — 8 fixes aplicados aos drafts

1. Duas EventSources (risco #1 da spec) — só $ServiceName estava registada.
2. secrets\ conta serviço M→R (verificação de código pelo orquestrador).
3. Health timeout 90→120s (risco #8).
4. Aviso GPO/SeServiceLogonRight + detecção secedit (risco #5).
5. HKLM InstalledVersion+ServiceAccount + auto-cleanup ACE conta antiga (spec E.8, risco #10).
6. Uninstall: EventSource preservada por default, switch -PurgeEventSource (spec F).
7. Assinar .ps1/.psd1 do stage, não só PE (risco #4, AllSigned).
8. Check MAX_PATH 240 pré-zip (risco #9).

Passou à primeira: firewall, gMSA, delayed-auto, failure actions, upgrade path,
preservação ProgramData, sc create/config idempotente, health path, self-delete
guard do uninstall, exit codes documentados.

## 4. Top 10 riscos da spec (grelha de verificação p/ matriz de teste)

1. EventSource não registada (ou só uma) → eventos licença fora do Event Log.
2. secrets\ sem /inheritance:r → Users:RX herdado anula a barreira DPAPI.
3. Firewall copiado do legacy (8443 + sem Public).
4. AllSigned bloqueia install/preflight não assinados (incl. scripts filho).
5. SeServiceLogonRight apagado por GPO refresh → falha dias depois.
6. Upgrade toca ProgramData (repetir FIND S2-7).
7. sc stop sem espera real por STOPPED → corrupção/rollback inválido.
8. Health timeout curto → rollback desnecessário sob EDR scan.
9. MAX_PATH 260 → extracção parcial silenciosa.
10. ACLs não reaplicadas/limpas em upgrade com conta diferente.

## 5. Questões abertas (owner)

- Q1: Elegibilidade Azure Trusted Signing — iniciar JÁ (D2 aprovado; ~$120/ano; até lá, todo o build é -SkipSigning e não entra em cliente AllSigned).
- Q2: Purga automática de backups `.bak.<timestamp>` antigos (proposto: manual).
- Q3: FASE4 §4.2 cita `build.py --strict` que não existe (build.py já é fail-loud desde Etapa 0.7) — corrigir texto quando se tocar no doc.
- Q4: `intelligence_kpis.py` modificado uncommitted no working tree (fora da wave) — decidir destino antes do fecho da wave.
- Q5: Baseline pytest hardcoded no build_release.ps1 vs ficheiro externo versionado.

## 6. Runbook EDR/ASR onboarding (outline — spec J)

2 semanas antes da janela de instalação: (1) confirmar EDR do cliente (regra
ASR 01443614 é Defender-specific; EDR terceiro = pedido separado); (2) pacote:
SHA-256 manifest + thumbprint do cert Authenticode + escopo Program Files;
(3) exclusão POR PUBLISHER, não por hash (hash muda a cada rebuild);
(4) dry-run em não-prod do cliente com EDR real; (5) janela PRD: zero eventos
de bloqueio. A exclusão ASR da workstation de build NÃO transfere p/ cliente.

## 7. Próximos passos

1. Owner: copiar 3 scripts do scratchpad → deploy\, rever, commit (bloco em chat).
2. Owner: primeiro run real `build_release.ps1 -Target zip -SkipSigning` (LLVM no PATH) → valida a cadeia completa + mata os .bak órfãos do dist no rebuild limpo.
3. Sessão seguinte: matriz de teste FASE4 §4.3 em VM/dir limpo (install→health→upgrade→uninstall) usando a grelha da secção 4.
4. Azure Trusted Signing (Q1) em paralelo — desbloqueio do gate 4a.
