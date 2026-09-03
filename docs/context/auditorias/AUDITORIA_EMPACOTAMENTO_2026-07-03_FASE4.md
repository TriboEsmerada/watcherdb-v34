# Auditoria Empacotamento — FASE 4 (Plano de execução + steelman)

Data: 2026-07-03 | Agentes: orquestrador + challenger (steelman adversarial)
Fases: FASE0/1/2/3.md | FECHO DA AUDITORIA — decisão final é do owner.

## 4.4 STEELMAN (primeiro, porque altera o roadmap)

Veredito do challenger: VENCE PARCIALMENTE — contra o MSI-agora, não contra o
trabalho. Pontos que sobrevivem ao contraditório:
1. Dos 5 B0, quatro (SCM, identidade SQL, sanitização do bundle, ProgramData)
   são defeitos do PRODUTO — obrigatórios em QUALQUER veículo de entrega.
   O custo MSI-específico real é só o delta WiX/heat/ICE/properties (S-M).
2. Unit of deployment: o cliente compra "monitoring a funcionar" = V1+V3.3.
   O V1 nunca será MSI (GRANTs+tasks em 22+ servers = runbook por natureza).
   A experiência de onboarding é dominada pela parte não-MSI-ável → falta um
   RUNBOOK UNIFICADO V1+V3.3, que nenhum MSI substitui.
3. Timing: com zero clientes, o polish WiX não acumula valor parado; os B0 de
   produto acumulam em qualquer cenário. Assimetria: fazer MSI cedo custa
   3-5 semanas de founder-time; fazê-lo sob pressão de piloto custa 1-2
   (se os B0 já estiverem fechados).
BARRA MENSURÁVEL: MSI ganha SE (a) piloto assinado com instalação a <90 dias
E (b) cliente exigir MSI/SCCM por política escrita. Senão: hardening B0 →
ZIP onedir + install.ps1 assinado → white-glove no piloto com runbook
unificado → MSI quando o 2º cliente/SCCM o exigir (Product.wxs não apodrece).
AUTO-ATAQUE do challenger (a levar a sério): MSI pode ser requisito de VENDA
(checkbox RFP banking) antes de ser requisito de instalação; e o gate da
Fase 0 ("DBA do cliente instala") contradiz white-glove — só o owner reabre.
Verificação barata: perguntar ao prospect "política aceita script assinado
acompanhado pelo vendor?" (ou consultar customer-success-persona/marketing).
"Wrong" absoluto em qualquer cenário: shippar antes de B0-2 (Regra Ouro #2)
e B0-3 (leak topologia vendor).

RECOMENDAÇÃO DO ORQUESTRADOR (integra o steelman): adotar o híbrido —
Etapas 0-2 abaixo são incondicionais (produto); Etapa 3a (ZIP+PS1) é o
veículo default; Etapa 3b (delta MSI) fica TRIGGER-BASED (piloto <90d OU
exigência MSI escrita). Comprar signing JÁ (barato, reputação SmartScreen
acumula por hash/volume com o tempo). Acrescentar ao backlog: runbook
unificado V1+V3.3 (fora do scope desta auditoria, mas é o gap real).

## 4.1 ROADMAP SEQUENCIADO (reordenado pós-steelman)

ETAPA 0 — Fundações (paralelo, sem dependências)
  0.1 [S-M] Lockfile (pip-tools/uv) + build só de clone limpo     (B1-12)
  0.2 [S] encoding utf-8 watcherdb_main.py:153                     (B1-9)
  0.3 [S] custom_queries path _PROJECT_ROOT                        (B1-7)
  0.4 [S] versão SOT única (release_vars → pyproject/settings)     (B2-15)
  0.5 [S] string V32 em setup_database.ps1                         (B2-16)
  0.6 [S] EXCLUDE morto build.py: aplicar como validação ou remover(B2-17)
  0.7 [S] PyArmor fallback → FALHAR o build (fail-loud)            (B2-18)
  0.8 [S] deprecar installer legacy pywin32 (aviso no ficheiro)    (B3-20)

ETAPA 1 — Produto: estado e identidade (núcleo; qualquer veículo exige)
  1.1 [M-L] watcherdb/core/paths.py resolver 3-tier + migrar ~15
      call-sites (config/data/logs/secrets → ProgramData)     (B0-4,B1-6/7)
      → destrava 1.4, 1.5, 3a/3b
  1.2 [M] Identity flip sql_monitoring: _build_connection_string
      prioriza SQL-auth; intelligence_use_windows_auth=False em
      produção; preflight testa identidade real (handoff 0.3 +
      veto v1-intel-specialist)                                    (B0-2)
  1.3 [M] Sanitizar build: excluir JSONs vivos; templates vazios +
      first-run bootstrap                                          (B0-3)
  1.4 [S-M] Secrets DPAPI machine-scope em secrets\ + JWT
      persistente (reusa services/secrets.py)                      (B1-8)
  1.5 [S] Named mutex Global\WatcherDBV33 (instância única)
  1.6 [S] .env resolução ProgramData-first (padrão crl.py)         (B1-8)

ETAPA 2 — Produto: serviço (destrava qualquer instalação como serviço)
  2.1 [L] Entry point SCM: fundir ServiceFramework (service.py) em
      watcherdb_main sob sys.frozen; SvcStop gracioso; stdout/
      stderr → logs\; porta da config                          (B0-1,B0-5)
  2.2 [S] Teste de arranque REAL via SCM (sc create/start/stop) —
      manual ou runner Windows; o smoke atual não apanha B0-1

ETAPA 3a — Veículo default: ZIP onedir + install.ps1 assinado [S-M]
  Rebuild (PyArmor+PyInstaller) → assinar TODOS os PE → zip +
  install.ps1 idempotente (dirs+ACLs ProgramData, New-Service ou
  sc create, firewall c/ perfil parametrizável, EventSource,
  preflight integrado) + uninstall.ps1 → SBOM → SHA-256 manifest.
ETAPA 3b — Delta MSI [S-M] — TRIGGER: piloto <90d OU exigência escrita
  Product.wxs: config fora do harvest, <Environment> WEBPORT, ACLs
  por subpasta, EventSource, FirewallExtension, DelayedAutoStart,
  properties silent completas (B2-14) → assinar MSI → matriz 4.3.
ETAPA 4 — Gate de GA (qualquer veículo)
  4a Signing ativo (Trusted Signing; verificar elegibilidade JÁ)   (B2-13)
  4b Piloto com EDR real do cliente = gate (plano B: Nuitka)
  4c Runbook unificado V1+V3.3 (novo item, fora deste scope)

## 4.2 SCRIPT DE BUILD REPRODUTÍVEL (PROPOSTO — não executado)

deploy/build_release.ps1 -Target zip|msi (um comando, clone limpo → artefacto):
  1. git clone <repo> $work; cd $work
  2. $ver = git describe --tags --abbrev=0  # ex: v3.3.1 → 3.3.1.0
     → reescreve release_vars.psd1 ProductVersion (SOT única, Etapa 0.4)
  3. py -3.11 -m venv .venv-build; pip-sync requirements.lock (Etapa 0.1)
  4. pytest -m "not e2e" (gate: falha aborta)
  5. python deploy/build.py --strict  # --strict = PyArmor fallback aborta
  6. signtool sign (Trusted Signing dlib) sobre dist/watcherdb/**/*.{exe,pyd,dll}
  7a. -Target zip: Compress-Archive + install.ps1/uninstall.ps1 assinados
      + preflight_target.ps1 → WatcherDB_V3.3_$ver.zip
  7b. -Target msi: build_msi.ps1 (heat exclui config/) → sign_msi.ps1
  8. build_sbom.ps1 (CycloneDX) + SHA256SUMS.txt
  9. smoke: instalar em sandbox/VM → sc start → GET /health → sc stop
      → uninstall → verificar ProgramData preservado
Pré-requisitos do runner: preflight_runner.ps1 (já existe) + WiX v3 (só 7b).

## 4.3 MATRIZ DE TESTE DE INSTALAÇÃO

Eixos: SO {Srv2016, Srv2019/2022, Win10, Win11} × operador {admin, não-admin}
× cenário. Validação base (TODAS as células): serviço RUNNING via SCM; porta
8433 responde /health; login portal OK; ZERO escrita em Program Files
(Process Monitor filtrado a watcherdb.exe); logs/dados em ProgramData;
Event Log sem erros 7000/7009/1053.
| Cenário | Validar além da base |
|---|---|
| Fresh install default (NetworkService) | ligação SQL via sql_monitoring; first-run cria skeleton; JWT sobrevive restart |
| Não-admin tenta instalar | falha LIMPA com mensagem (UAC), sem instalação parcial |
| Path com espaço+acento (D:\Aplicações Críticas\WatcherDB) | tudo da base; PyArmor runtime carrega; atalhos/serviço apontam certo |
| AV/EDR agressivo (Defender ASR + EDR do piloto) | MSI/PS1 executa; watcherdb.exe + pyarmor_runtime.pyd não quarentenados; registar veredito p/ gate 4b |
| Silent (msiexec /qn + properties | install.ps1 -Silent) | paridade total com interativo; exit codes corretos |
| Upgrade N-1→N | config/inventário do cliente INTACTOS; licença mantida; serviço volta a RUNNING; versão nova reportada |
| Rollback (matar upgrade a meio) | MSI: transação reverte; ZIP: install.ps1 restaura backup |
| Uninstall → reinstall | ProgramData preservado; reinstall recupera config; sem serviço/firewall órfãos |
| Firewall: interface em perfil Public | regra cobre o perfil real (lição 2026-06-12); acesso remoto OK |
| Conta AD dedicada (SERVICEACCOUNT) | serviço arranca; WinRM remoto funciona; ACLs secrets\ corretas |
| 2ª instância manual (exe direto c/ serviço UP) | mutex bloqueia com mensagem clara |
| Relógio/fuso ≠ Lisboa | timestamps coerentes; licença/JWT (UTC) inalterados |

## Decisões pendentes do owner (fecho)

D1. Adotar híbrido do steelman (3a default, 3b trigger-based)? [recomendado]
    OU manter MSI-first (se RFP banking exigir checkbox MSI — verificar com
    prospect/marketing-strategist antes de decidir).
D2. Signing: iniciar elegibilidade Azure Trusted Signing já. [recomendado]
D3. industry_wizard: marcar roadmap (não embutir agora). [recomendado]
D4. Novo workstream: runbook unificado V1+V3.3 (gap real de onboarding).
