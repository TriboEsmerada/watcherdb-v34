# RUNBOOK — Azure Artifact Signing (ex-Trusted Signing) para o veículo ZIP

Data: 2026-07-04 | Etapa 3a (frente signing) | Decisão base: FASE3 (D2 aprovado)
Fontes web (verificadas 2026-07-04): learn.microsoft.com/azure/artifact-signing/faq
(ms.date 2026-05-14), azure.microsoft.com/pricing/details/artifact-signing/

## 0. Mudança de nome e factos que alteram o plano FASE3

- O serviço foi **rebrandado**: Azure Trusted Signing → **Azure Artifact Signing**.
  Funcionalidade igual; docs e roles usam o nome novo. O resource provider
  continua a ser `Microsoft.CodeSigning`.
- Preço confirmado: **Basic $9.99/mês** (até 5.000 assinaturas/mês; $0.005 por
  assinatura extra). Cobrança do mês é INTEIRA independentemente do dia de
  criação (não pro-rata) — criar a conta quando formos mesmo usar.
- Elegibilidade Public Trust: organizações em **USA, Canadá, UE e UK** —
  Portugal elegível. Requisito de histórico: **~3 anos de registo fiscal**
  da entidade legal.
- **Não emite EV** (nem vai emitir). Irrelevante para nós: desde 2024 EV já
  não dá reputação SmartScreen instantânea (racional FASE3 mantém-se);
  reputação constrói-se automaticamente por hash + histórico de downloads.
- **O certificado NUNCA é entregue ao cliente do serviço** — chave privada
  fica no HSM do serviço (FIPS 140-2 Level 3). Certificados de vida curta
  (~3 dias) ⇒ **timestamp RFC 3161 é obrigatório** em TODAS as assinaturas,
  senão a assinatura "morre" com o certificado.
- Timestamp server do serviço: `http://timestamp.acs.microsoft.com`
  (health-check: `curl http://timestamp.acs.microsoft.com` → 200).

## 1. CHECKLIST DE ONBOARDING (owner executa, portal Azure)

Sequência com lead time real — o passo 4 (identity validation) é o gargalo
(dias a semanas, sem expedite possível; "identity validation requests can't
be expedited" na FAQ oficial).

- [ ] **1. Subscrição Azure paga** (pay-as-you-go ou EA). Free/trial/sponsored
      são RECUSADAS na criação da conta de signing.
- [ ] **2. Verificar billing account ANTES de tudo**: legal name + morada de
      faturação têm de bater **exatamente** com o que vai aparecer no
      certificado (CN = nome legal validado da entidade; CN/O custom NÃO
      são suportados). Discrepância = certificado com dados errados.
      Nota: billing account de indivíduo NÃO valida identidade de
      organização (e vice-versa).
- [ ] **3. Registar resource provider** `Microsoft.CodeSigning` na
      subscrição (Subscription → Resource providers) e criar o recurso
      **Artifact Signing account** (SKU Basic) numa região suportada
      (usar West Europe se disponível).
- [ ] **4. Identity validation (organização)**:
      a. Atribuir a ti próprio a role **Artifact Signing Identity Verifier**
         (sem ela o botão "New identity validation" fica inativo).
      b. Submeter identity validation tipo Public Trust com o nome legal.
      c. **Email de verificação expira em 7 dias** e não é reenviável no
         mesmo pedido — vigiar spam/filtros; endereço não pode ser
         distribution list. Falhar 3 rondas de documentação extra =
         onboarding recusado.
- [ ] **5. Certificate profile** tipo **Public Trust** associado à identity
      validation completada.
- [ ] **6. Identidade de assinatura para a máquina de build**: criar app
      registration (service principal) OU usar user sign-in interativo;
      atribuir-lhe a role **Artifact Signing Certificate Profile Signer**
      no resource group/conta. Para builds não-interativos: env vars
      `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`
      (EnvironmentCredential do Azure.Identity).
- [ ] **7. Pré-requisitos da máquina de build**: Windows SDK recente
      (signtool atualizado — versões antigas dão `SignerSign() failed
      0x80070032`), .NET runtime compatível com a dlib, VC++
      Redistributables, e o pacote **Azure.CodeSigning dlib**
      (`Azure.CodeSigning.Dlib.dll` — NuGet `Microsoft.Trusted.Signing.Client`
      ou equivalente rebrandado) + `metadata.json` com Endpoint,
      CodeSigningAccountName e CertificateProfileName.
- [ ] **8. Renovação**: identity validation expira — lembretes começam 60
      dias antes. Deixar expirar = renovação de certificados PARA e o
      signing morre. Pôr lembrete de calendário próprio.

## 2. INTEGRAÇÃO NO build_release.ps1 (proposta — owner aplica)

### 2.1 Problema com o desenho atual

`deploy/build_release.ps1` tem 3 backends (`keylocker` default | `pfx` |
`store`). O backend da decisão FASE3 é o Artifact Signing — mecanismo
diferente: `signtool sign /dlib <Azure.CodeSigning.Dlib.dll> /dmdf
<metadata.json>`, autenticação Entra ID. **Dois pontos quebram no desenho
atual:**

1. `SigningMode` default `keylocker` exige env vars DigiCert que nunca
   existirão — precisa do 4º modo `trustedsigning` (e provavelmente passar
   a default, já que é a decisão aprovada).
2. **PASSO 4 (assinatura dos .ps1 do stage) usa `Set-AuthenticodeSignature`
   com objeto de certificado local** (`Get-SigningCertificateObject`).
   Com Artifact Signing NÃO HÁ certificado local — o caminho é inviável
   neste modo. Solução: no modo `trustedsigning`, assinar os .ps1/.psd1
   também via `signtool /dlib` (signtool assina scripts PowerShell através
   do SIP; a FAQ confirma "all file types that SignTool supports").

### 2.2 Diff proposto (bloco para aplicar manualmente)

```powershell
# --- param(): acrescentar o modo e os 3 parâmetros do serviço ---
    [ValidateSet('trustedsigning', 'keylocker', 'pfx', 'store')]
    [string]$SigningMode = 'trustedsigning',

    # Artifact Signing (ex-Trusted Signing) — SigningMode trustedsigning
    [string]$TsEndpoint    = 'https://weu.codesigning.azure.net',  # região da conta
    [string]$TsAccountName,        # nome do Artifact Signing account
    [string]$TsProfileName,        # nome do certificate profile (Public Trust)
    [string]$TsDlibPath,           # caminho de Azure.CodeSigning.Dlib.dll

# --- PASSO 3, switch ($SigningMode): novo ramo ---
        'trustedsigning' {
            foreach ($p in @{TsAccountName=$TsAccountName; TsProfileName=$TsProfileName; TsDlibPath=$TsDlibPath}.GetEnumerator()) {
                if (-not $p.Value) {
                    Write-Fail "-$($p.Key) obrigatorio em SigningMode trustedsigning."
                    exit 5
                }
            }
            if (-not (Test-Path $TsDlibPath)) {
                Write-Fail "Azure.CodeSigning.Dlib.dll nao encontrada em $TsDlibPath (NuGet Microsoft.Trusted.Signing.Client)."
                exit 5
            }
            # metadata.json gerado por-run (nao commitado -- contem nomes do tenant)
            $tsMetadata = Join-Path $env:TEMP 'watcherdb_v33_ts_metadata.json'
            @{
                Endpoint               = $TsEndpoint
                CodeSigningAccountName = $TsAccountName
                CertificateProfileName = $TsProfileName
            } | ConvertTo-Json | Set-Content -Path $tsMetadata -Encoding ascii
            # Timestamp do proprio servico (obrigatorio: certs ~3 dias de vida)
            $TimestampUrl = 'http://timestamp.acs.microsoft.com'
            $common = @('sign', '/fd', 'sha256', '/td', 'sha256', '/tr', $TimestampUrl, '/v')
            $signArgs = $common + @('/dlib', $TsDlibPath, '/dmdf', $tsMetadata)
        }

# --- PASSO 4: os .ps1 do stage NAO podem usar Set-AuthenticodeSignature
#     neste modo (sem certificado local). Substituir o bloco de assinatura
#     de scripts por um branch: ---
    if ($SigningMode -eq 'trustedsigning') {
        # signtool assina .ps1/.psd1 via SIP do PowerShell — mesmo signArgs do PASSO 3
        foreach ($sf in $scriptsToSign) {
            & $signtool @signArgs $sf
            if ($LASTEXITCODE -ne 0) {
                Write-Fail "signtool falhou a assinar script do stage: $sf"
                exit 5
            }
            $st = (Get-AuthenticodeSignature -FilePath $sf).Status
            if ($st -ne 'Valid') {
                Write-Fail "Assinatura de $sf invalida apos signtool (status: $st)."
                exit 5
            }
        }
    } else {
        # caminho existente (Get-SigningCertificateObject + Set-AuthenticodeSignature)
    }
```

Notas de aplicação:
- O comentário de assunção KeyLocker (linhas ~180-198) fica; keylocker passa
  a backend alternativo.
- `$TimestampUrl` default global pode permanecer DigiCert para os modos
  pfx/store; o ramo trustedsigning força o do serviço.
- Autenticação: na 1ª execução interativa, o dlib abre browser (Entra ID).
  Para CI/não-interativo, definir as 3 env vars AZURE_* ANTES do PASSO 3;
  erro 403 = falta a role Certificate Profile Signer (checklist §1.6).
- Erro clássico "No certificates were found that met all the given
  criteria" = signtool a tentar cert local em vez da dlib → verificar
  /dlib path e versão do signtool.
- Validar contra a EDR/ASR da dev machine: bundle assinado deve deixar de
  precisar da exclusão ASR 01443614 (lição Etapa 2) — confirmar e registar.

## 3. Teste de aceitação da frente signing (quando a conta estiver ativa)

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
pwsh deploy\build_release.ps1 -Target zip -SigningMode trustedsigning `
    -TsAccountName <conta> -TsProfileName <perfil> `
    -TsDlibPath <path>\Azure.CodeSigning.Dlib.dll
# Aceitação:
#   1. exit 0; sumario "Assinado: SIM"
#   2. signtool verify /pa dist\watcherdb\watcherdb.exe -> OK, cadeia
#      "Microsoft ID Verified Code Signing PCA 2021"
#   3. Get-AuthenticodeSignature dist\release\<ver>\stage nao existe
#      (transitorio) -> validar extraindo o ZIP: install.ps1 Status=Valid
#   4. timestamp presente (senao a assinatura expira em ~3 dias!)
#   5. VM com ExecutionPolicy AllSigned: install.ps1 corre sem override
```

## 4. Riscos/pendências registadas

- [ ] Confirmar no onboarding real o nome atual do pacote NuGet da dlib
      (rebrand pode tê-lo renomeado de `Microsoft.Trusted.Signing.Client`).
- [ ] Entidade legal: confirmar que a empresa do owner tem ≥3 anos de
      histórico fiscal; senão, caminho alternativo = certificado OV
      clássico (Sectigo/DigiCert) com pipeline pfx/store JÁ suportado
      pelo script (fallback natural).
- [ ] SmartScreen: mesmo assinado, ficheiro novo pode dar prompt até criar
      reputação — opção de submeter o ZIP assinado ao Microsoft Security
      Intelligence para review antecipada (URL na FAQ).
- [ ] Custo: só criar a conta quando a identity validation estiver pronta
      a submeter (cobrança de mês inteiro, não pro-rata).
