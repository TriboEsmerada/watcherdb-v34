# Auditoria Empacotamento — FASE 3 (Estratégia de empacotamento)

Data: 2026-07-03 | Agente: orquestrador, com WebSearch (estado da arte 2026)
Fases: FASE0/1/2.md | Gate Fase 3: AGUARDA revisão do owner.
Critério AV/EDR com PESO DOBRADO conforme prompt mestre.

## DECISÃO RECOMENDADA (uma linha)

Manter PyInstaller onedir + PyArmor BCC/RFT com o bundle INTEIRAMENTE assinado
(Azure Trusted Signing como 1ª opção, DigiCert OV fallback) + WiX MSI
per-machine com serviço nativo; update por MSI MajorUpgrade SEM auto-updater;
gate de validação EDR em piloto antes de GA — se o PyArmor chumbar no EDR do
piloto, a rota de saída é Nuitka.

## 1. Congelamento do runtime

| Critério (AV/EDR ×2) | PyInstaller onedir (atual) | PyInstaller onefile | Nuitka standalone | Py embeddable + deps |
|---|---|---|---|---|
| Tamanho | ~83 MB (medido, build maio) | ~similar comprimido | similar/maior | maior (site-packages) |
| Startup | rápido (sem extração) | LENTO (extrai p/ temp) | rápido | rápido |
| Patch/upgrade | substituição total do onedir (simples) | pior | recompilação total (builds lentos) | MELHOR (substituir ficheiros) |
| AV/EDR ×2 | médio — padrão conhecido; onedir MUITO melhor que onefile; assinatura mitiga | PIOR — padrão packer/self-extract = heurística de malware | MELHOR — comporta-se como app C nativa, taxa FP drasticamente menor | python.exe assinado PSF = confiável; .py expostos |
| Proteção IP | requer PyArmor por cima | idem | compilação C = proteção inerente (dispensaria PyArmor) | fraca; PyArmor script-mode possível |
| Risco migração | ZERO (funciona hoje) | n/a | ALTO (validar fastapi/pydantic/pyodbc/pywin32; perde invest. PyArmor; builds 10-30min+) | MÉDIO (novo pipeline) |

Veredito: onedir mantém-se (onefile excluído em definitivo). ALERTA PyArmor:
malware real usa PyArmor para evasão (VVS Stealer, Unit42/SANS 2025) e há FP
documentado no pyarmor_runtime.pyd legítimo (Malwarebytes) → a reputação do
runtime PyArmor está a degradar nos EDRs. Mitigação OBRIGATÓRIA: assinar TODOS
os PE do bundle (watcherdb.exe + pyarmor_runtime.pyd + *.pyd), não só o MSI;
checklist EDR com SHA-256 por release; piloto com o EDR real do cliente como
gate de GA. Nuitka fica como plano B documentado (resolve AV e IP de uma vez,
mas migração é projeto próprio e o pyarmor.bug.log do V5 já mostra fragilidade
PyArmor — monitorizar).

## 2. Tecnologia de instalador

| Critério | WiX/MSI (atual) | Inno Setup | MSIX | NSIS |
|---|---|---|---|---|
| Silent corporativo | /qn + properties = padrão SCCM/Intune/GPO | /VERYSILENT ok mas detection methods manuais | Add-AppxPackage sempre silent | /S, idem Inno |
| Serviço Windows | ServiceInstall nativo + ServiceConfig | via [Run] scripts (frágil) | suportado MAS: per-machine only, sem deps fora do pacote, update bloqueado com serviço a correr | scripts |
| Upgrade in-place | MajorUpgrade transacional (já implementado) | manual | bom mas restrições de serviço | manual |
| Rollback | transação MSI nativa | não | sim | não |
| Assinatura | Authenticode MSI | Authenticode EXE | OBRIGATÓRIA (cert trusted) | Authenticode EXE |
| Curva manutenção | XML verboso (JÁ PAGO — pipeline existe e builda) | baixa | média-alta | baixa |
| Nota AV | formato de sistema, confiável | ok | ok | stub NSIS historicamente abusado por malware |

Veredito: WiX/MSI mantém-se — é o que o parque SCCM/Intune de um banco espera,
o investimento já existe e builda, e MSIX está descartado (restrições de
serviço + a própria Microsoft recuou no MSIX para o Office). Inno/NSIS só
fariam sentido em produto consumer.

## 3. Code signing

MUDANÇA DE PAISAGEM: desde 2024 o EV JÁ NÃO dá reputação SmartScreen
instantânea (Microsoft Learn/Q&A) — reputação constrói-se por hash+volume,
igual para OV e EV. EV mantém valor só para procurement/políticas internas
("EV-only") de alguns clientes.
Custos 2026: OV ~$219-400/ano (Sectigo/Comodo em baixo, DigiCert ~$400);
EV ~$290-685/ano. NOVIDADE: Azure Trusted Signing (agora "Artifact Signing")
$9.99/mês (5k assinaturas), HSM FIPS 140-2 L3, certs 72h rotativos,
disponível para ORGANIZAÇÕES na UE — candidata forte para vendor PT
(~$120/ano vs $400-700 DigiCert). Verificar elegibilidade (histórico
verificável da organização) antes de decidir.
Nota: sign_msi.ps1 atual assume DigiCert KeyLocker (sem credenciais nunca
configuradas) — suporta backend `pfx`/`store`, portanto adaptar a Trusted
Signing (signtool + dlib) é mudança pequena.
PLANO B (não assinar agora): inaceitável para GA banking — SmartScreen
"Unknown publisher" + EDR default-deny transferem o custo para CADA cliente
(exceções manuais, hashes por release). Aceitável APENAS para lab/QLT interno.
Assinar é mais barato que o atrito de não assinar.

## 4. Update strategy

Recomendação: INSTALADOR NOVO POR VERSÃO (MSI MajorUpgrade), SEM auto-updater
embutido. Razões: (a) cliente banking opera change management/CAB — auto-update
é anti-feature que bypassa controlo de mudança; (b) MSI via SCCM/Intune é o
canal que o cliente já domina, com auditabilidade (assinatura + SBOM por
release); (c) o updater cliente nem existe (Fase 0) — construí-lo agora é
maquinaria sem cliente a pedir (subtrair é a maestria). O produtor de update
packages Ed25519 (deploy/updater/build_update_package.py) fica como roadmap
Pro se um cliente exigir patching offline assinado.

## Fontes

- PyInstaller FP onefile/onedir: github.com/pyinstaller/pyinstaller/issues/6754;
  pythonguis.com/faq/problems-with-antivirus-software-and-pyinstaller;
  coderslegacy.com/pyinstaller-exe-detected-as-virus-solutions
- Nuitka vs PyInstaller AV: dev.to/weisshufer (from-pyinstaller-to-nuitka);
  coderslegacy.com/nuitka-vs-pyinstaller; ahmedsyntax.com (2026 showdown)
- PyArmor abuse/FP: unit42.paloaltonetworks.com/vvs-stealer;
  isc.sans.edu/diary/31840; forums.malwarebytes.com/topic/335406;
  infosecurity-magazine.com (vvs-stealer-advanced-obfuscation)
- Signing/SmartScreen: learn.microsoft.com/windows/apps/package-and-deploy/
  smartscreen-reputation e code-signing-options; learn.microsoft.com/answers/
  questions/417016; azure.microsoft.com/pricing/details/artifact-signing;
  gdgsoft.com/faq/azure-trusted-signing-cost-effective-exe-code-signing;
  ssldragon.com/ssl-certificates/code-signing; ssl.com/faqs/which-code-signing-
  certificate-do-i-need-ev-or-ov
- Instalador/MSIX: learn.microsoft.com/windows/msix/supported-platforms;
  advancedinstaller.com/msix-migration-limitations-and-solutions;
  turbo.net/blog (msix-limitations); github.com/offlineinstallersetup/
  silent-install-cheatsheet; advancedinstaller.com/msix-installer-for-office-
  discontinued
- Update strategy: apptimized.com/en/news/how-update-mechanisms-differ-across-
  applications; advancedinstaller.com (msi-upgrades-and-patches ebook);
  learn.microsoft.com/answers/questions/1078404
