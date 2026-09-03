# Auditoria Empacotamento + Instalador Windows — FASE 1 (Pressupostos de ambiente)

Data: 2026-07-03 | Agentes: python-packaging-architect + watcherdb-deploy-architect
(paralelo, âmbitos disjuntos código/instalador) + orquestrador (verificação build venv)
Fase 0: auditorias/AUDITORIA_EMPACOTAMENTO_2026-07-03_FASE0.md
Gate Fase 1: AGUARDA revisão do owner.

Severidades: B0=não funciona fora da dev machine; B1=quebra em cenário comum;
B2=viola boas práticas Windows; B3=polimento.

## ACHADOS B0 (bloqueiam empacotamento)

### B0-1. Serviço Windows nunca arranca — entry point sem protocolo SCM
Evidência: deploy/watcherdb.spec:29 (ENTRY_POINT=watcherdb_main.py);
watcherdb_main.py:5086-5141 (só uvicorn.run, zero win32serviceutil);
deploy/msi/Product.wxs:159-180 (ServiceInstall nativo sobre watcherdb.exe).
A classe ServiceFramework real (services/web_service/service.py:28) NÃO é o
entry point e serve outra app (services.web_service.server:app). O teste
tests/unit/test_pyinstaller_boot.py:80-86 só spawna subprocess — nunca testou SCM.
Quebra: sc start → Erro 1053 em QUALQUER máquina; invalida install.ps1 Phase 5/6.
Correção: (a) fundir ServiceFramework no entry point frozen (sys.frozen +
StartServiceCtrlDispatcher, uvicorn em thread) OU (b) wrapper WinSW/NSSM no MSI.
Nota WiX: KeyPath do componente ServiceInstall é RegistryValue, não o File do exe
— validar convenção. Esforço: L (a) / S-M (b). DESTRAVA TUDO O RESTO.

### B0-2. Identidade SQL: Trusted_Connection hardcoded + NetworkService sem GRANT
Evidência: api/connection_pool.py:458-488 (sempre Trusted_Connection=yes;
_build_connection_string_sql_auth :490-501 é código morto); settings.py:48
intelligence_use_windows_auth=True default; Product.wxs:83 SERVICEACCOUNT default
NT AUTHORITY\NetworkService; preflight_target.ps1 Phase 5 testa sql_monitoring
como identidade do OPERADOR (sqlcmd -E), não a do serviço.
Quebra: serviço autentica como DOMAIN\MACHINE$ — zero GRANTs em lado nenhum →
"Login failed" em todos os servers. Preflight passa, runtime falha. Viola Regra
de Ouro #2. Correção: inverter prioridade p/ SQL-auth sql_monitoring como default
de produção; preflight testar a identidade real do serviço; docs de GRANT.
Liga ao handoff 0.3 já aberto (revisão 2026-07-02). Esforço: M + coord. V1.

### B0-3. Inventário de produção real do vendor embebido em todos os builds
Evidência: deploy/build.py:80-85 (COPY_DIRS inclui "config" verbatim);
config/servers.json com 99 entradas reais *.tap.pt + passwords Fernet do vendor +
descrições internas; confirmado no artefacto: dist/watcherdb/_internal/config/
servers.json presente no build de maio. deploy/watcherdb.spec:74-82 idem.
Quebra: cliente banking recebe a topologia SQL interna do vendor dentro do
instalador — leak de confidencialidade + onboarding quebrado (UI mostra a lista
do vendor). Correção: excluir os JSON "vivos" do build; usar *.json.template
vazios + bootstrap first-run. Esforço: M. Handoff security-auditor (peso GDPR/DORA).

### B0-4. Escrita runtime no diretório de instalação + upgrade clobber
Evidência: watcherdb_main.py:85-89,1177,1266 (config JSONs em _PROJECT_ROOT);
api/routers/intelligence/helpers.py:70 (snapshot); Product.wxs:90-99 (INSTALLFOLDER
sem <Permission> custom — ACL default Program Files nega escrita a NetworkService);
DataFolderComp :101-131 tem ACL correta mas NENHUM código de app usa ProgramData
(só licensing). E build_msi.ps1:99-113: heat.exe harvest sem exclusões → cada
config/*.json é componente MSI; MajorUpgrade reinstala e SOBRESCREVE edições do
cliente em cada upgrade. Quebra: PermissionError em runtime + perda do inventário
do cliente a cada release. Correção: resolver central WATCHERDB_DATA_DIR
(default %ProgramData%\WatcherDB\) e migrar call-sites; config fora do harvest.
Esforço: M-L.

### B0-5. Porta 8000 real vs 8433 assumida em toda a stack de deploy
Evidência: watcherdb_main.py:5130-5135 (WATCHERDB_PORT default 8000);
Variables.wxi:58, preflight_target.ps1:182-186, install.ps1:198 assumem 8433;
Product.wxs sem elemento <Environment> (verificado, 220 linhas).
Quebra: serviço (pós B0-1) escuta em 8000; smoke test/preflight/firewall/docs
apontam 8433 — falso negativo permanente. Correção: <Environment
WATCHERDB_PORT=8433> no componente do serviço, ou porta fixada no wrapper.
Esforço: S (após B0-1).

## ACHADOS B1

- B1-6. `watcherdb_cache.db` literal relativo ao CWD em ~15 call-sites
  (watcherdb_intelligence.py:1154 +13, inventory_manager.py:44, cache_factory.py:14,
  routers backup/memory/cpu, dashboard_api.py:31). CWD de serviço SCM =
  System32 (os.chdir só existe no código morto server.py:26) → escrita em
  C:\Windows\System32 negada. Resolve com WATCHERDB_DATA_DIR (B0-4). S.
- B1-7. `Path("config/custom_queries.json")` relativo (watcherdb_main.py:1322),
  inconsistente com o padrão _PROJECT_ROOT do próprio ficheiro. S.
- B1-8. `.env`: código lê de INSTALLFOLDER (watcherdb_main.py:22-28) mas o
  installer documenta C:\ProgramData\WatcherDB\.env (install.ps1:236) — edição do
  DBA não tem efeito; e .env NÃO entra no bundle (watcherdb.spec DATAS sem .env;
  hipótese alta confiança, confirmar com Test-Path no rebuild) → JWT cai em chave
  efémera (watcherdb/core/auth.py:23-36), sessões invalidadas a cada restart.
  Correção: resolução 3-tier ProgramData-first (padrão licensing/crl.py) +
  JWT secret como env de sistema definida pelo MSI, nunca no bundle. S.
- B1-9. `open(config_path,'r')` sem encoding (watcherdb_main.py:153) → cp1252 em
  Windows regional vs ficheiro UTF-8 com acentos ("infogestão") → mojibake/
  UnicodeDecodeError engolido por try/except → sql_monitoring nunca inicializa,
  silenciosamente. Fix 1 linha; follow-up: grep repo por open( sem encoding. S.
- B1-10. WinRM/WMI remoto (watcherdb_main.py:2911-2920,3858,4090,4142) falha
  silenciosamente sob NetworkService (double-hop Kerberos, Remote Management
  Users) — erro genérico não distingue identidade de rede. S-M.
- B1-11. Zero regra de firewall no caminho de instalação (Product.wxs sem;
  install.ps1 não chama configure_firewall.ps1 — script existe só no legacy).
  Precedente: incidente 2026-06-12 (perfil da interface, gotcha #6 deploy-architect).
  Correção: New-NetFirewallRule idempotente no install.ps1, perfil parametrizável. S.
- B1-12. Build não reprodutível — sem lockfile (verificação orquestrador):
  requirements.txt só tem mínimos; .venv-build real (pip freeze, 91 pkgs) flutuou
  para fastapi 0.136.1, pandas 3.0.3 (major!), numpy 2.4.4, starlette 1.0.0,
  bcrypt 5.0.0 (+passlib 1.7.4 = incompatibilidade conhecida). Cada rebuild
  congela um conjunto diferente. Correção: lockfile (pip-tools/uv) + build de
  clone limpo em CI. S-M.

## ACHADOS B2

- B2-13. MSI NotSigned + PyArmor BCC (código nativo) = fricção EDR/SmartScreen
  esperada em banking (install.ps1:149-150 admite; KeyLocker sem credenciais).
  Hipótese p/ EDR específico, não verificado — exige teste QLT com EDR real +
  checklist de exclusão com SHA-256. M (processo externo) + S (checklist).
- B2-14. Silent install SCCM/Intune incompleto: fases 3-4 do install_orchestrator
  exigem python.exe externo (subprocess sys.executable :132-148,:182-199); outputs
  do industry_wizard (client_context.yaml/compliance_rules.yaml) NÃO são
  consumidos por nenhum código de runtime (grep zero). Faltam MSI properties
  (INTELLIGENCE_SERVER etc.). L (decisão) / S (marcar roadmap).
- B2-15. Drift de versão em 4 sítios: pyproject 1.0.0 / settings.py:29 "3.2.0" /
  release_vars.psd1 3.3.0.0 (SOT declarado) / server.py 1.0.0. S.
- B2-16. setup_database.ps1:143 referencia WatcherDBWebServiceV32 (regressão
  conhecida desde 2026-04-24, ainda presente). S.
- B2-17. EXCLUDE list morto em build.py:105-127 (definido, nunca aplicado) —
  falsa confiança. Remover ou aplicar como validação pós-copy. S.
- B2-18. Fallback PyArmor silencioso shipa módulo SEM obfuscação (build.py:245-247;
  caso real: dashboard_api.py, pyarmor.bug.log). Corrigir causa + fazer o build
  FALHAR (ou avisar alto) quando cair no fallback. S.

## ACHADOS B3

- B3-19. Preflight exige .NET 4.7.2+ (preflight_target.ps1:201-206) sem consumidor
  identificado no MSI WiX puro — pode bloquear Server Core sem razão. S.
- B3-20. Colisão de nome SCM: installer legacy pywin32 e MSI registam ambos
  WatcherDBWebServiceV33 apontando para apps/portas diferentes — sobrescrita
  silenciosa de ImagePath. Marcar legacy como deprecated/dev-only. S.
- B3-21. Timezone Europe/Lisbon default em scripts de forecast
  (filegroup_forecast.py:24,50 e afins). S.

## Áreas verificadas limpas (com método)

- Imports dinâmicos próprios: só __import__('datetime') trivial (3 sítios). OK.
- Relative imports profundos (padrão do bug PyArmor): zero `from ..` no código
  próprio; dashboard_api.py usa 1 nível. Causa exata do overflow histórico não
  reconfirmável sem rebuild (hipótese declarada).
- _PROJECT_ROOT (watcherdb_main.py:85) e parents[3] (helpers.py:70): aritmética
  CORRETA contra o layout onedir _internal (verificado no dist/ de maio) — o
  problema é ONDE apontam (Program Files), não o cálculo.
- MajorUpgrade/UpgradeCode, preservação de ProgramData, perMachine, ausência de
  custom actions, SBOM: corretos (deploy-architect).
- Oracle: inexistente. Redis/LDAP/SMTP: opcionais com degradação verificada.

## MUDANÇAS OBRIGATÓRIAS ANTES DE EMPACOTAR (ordenadas por dependência)

1. [L] B0-1 mecanismo de serviço real (decisão a+b na Fase 2) — destrava tudo.
2. [M-L] B0-4/B1-6/B1-7/B1-8 resolver central WATCHERDB_DATA_DIR (ProgramData)
   + migração de call-sites + config fora do harvest MSI.
3. [M] B0-2 identity flip sql_monitoring (liga ao handoff 0.3 aberto) + preflight
   testar identidade real.
4. [M] B0-3 sanitizar build (templates vazios + first-run bootstrap).
5. [S] B0-5 porta via <Environment> ou wrapper (depende de 1).
6. [S] B1-8 JWT secret persistente via MSI (depende de 2 p/ .env path).
7. [S-M] B1-12 lockfile + build reprodutível de clone limpo.
8. [S] B1-9 encoding; B1-11 firewall no install.ps1; B2-15 versão SOT única;
   B2-16 V32 string; B2-17 EXCLUDE morto; B2-18 PyArmor fail-loud. (paralelo)
9. [M] B2-13 signing (processo DigiCert, externo ao código).

Handoffs propostos: security-auditor (B0-3 peso compliance; least-privilege
SERVICEACCOUNT), v1-intel-specialist (GRANTs, veto infra partilhada — já em 0.3),
v33-specialist (implementação dos diffs). Bloco Nestor session.log preparado
pelo deploy-architect — owner cola manualmente (escrita AI restrita a docs/context/).
