# Ronda 4 — Instalação limpa, upgrade e rollback (WatcherDB V3.3)

**Numa VM virgem, não na máquina de produção.** É a ronda que replica o que o piloto banking vai
fazer antes de qualquer outra coisa. Já existe muito material — esta ronda **testa-o e apanha o que
falha**, não parte do zero. Copia a partir do `---`.

**Notas para nós:**
- **VM Windows Server 2016+ limpa** (snapshot antes de começar, para reverter entre tentativas).
- **Material que já existe e é o alvo do teste:** `deploy/INSTALL_TEST.md` (guia de teste interno),
  `deploy/preflight_target.ps1` (validação de pré-requisitos, 10 fases), `docs/external/standard/
  INSTALL_GUIDE.md` (guia cliente), `docs/RUNBOOK_CONTA_SERVICO.md` (conta de serviço). O MSI sai em
  `dist/msi/WatcherDB_V3.3_Standard.msi` (~37,6 MB) após `python deploy/build.py` +
  `pwsh deploy/build_msi.ps1 -Clean`.
- **Avisos conhecidos** (`INSTALL_TEST.md`): MSI ainda **unsigned**, EULA por rever, licença de teste.
  O piloto real precisa de MSI assinado — não é falha desta ronda, mas confirma que o unsigned instala.
- **Precedente a re-testar:** em 2026-08-12 o MSI fazia rollback silencioso na 1ª instalação (KeyPath
  vazio no componente do serviço). Foi corrigido e validado ponta-a-ponta a 12/08 numa máquina real.
  Esta ronda confirma que continua a instalar limpo numa VM virgem.

---

## Objetivo

Provar que um sysadmin que nunca viu o produto consegue instalá-lo, configurá-lo e pô-lo a servir,
**seguindo só a documentação** — e apanhar cada ponto onde a documentação mente, falta ou confunde.

O teste real desta ronda não é "o MSI corre?". É **"a documentação chega?"**. Segue o
`INSTALL_GUIDE.md` (o guia do cliente) à risca, como se não pudesses perguntar a ninguém, e regista
cada vez que tiveste de adivinhar, procurar noutro sítio, ou fazer algo que o guia não diz.

## 1. Pré-requisitos e preflight

1. VM limpa. Corre `deploy/preflight_target.ps1` **antes** de instalar. Regista o que ele verifica e
   o que passa/falha. Um preflight que diz "tudo OK" e depois a instalação falha é achado.
2. Confirma os pré-requisitos do `INSTALL_TEST.md` à mão (ODBC 17/18, .NET 4.7.2+, porta 8433 livre,
   SQL acessível). Algum pré-requisito real que o guia **não** liste? (ex.: o guia assume ODBC mas
   não diz como instalar; ou não menciona a CA interna para o cert.)

## 2. Instalação limpa

1. Instala o MSI. Cronometra. Regista cada prompt/decisão que aparece.
2. **Verifica, sem confiar no "concluído":**
   - o serviço `WatcherDBWebServiceV33` existe, está `Running`, `StartType=Automatic`?
   - a porta está à escuta? (nota: TLS exige config/cert — ver secção 4)
   - a regra de firewall foi criada? (em 2026-08-12 o MSI **não** a criava — o `install.ps1` criava.
     Confirma qual é o caso do MSI atual: `Get-NetFirewallRule -DisplayName "*8433*","*WatcherDB*"`)
   - a pasta de dados (`C:\ProgramData\WatcherDB`) existe com a ACL certa para a conta de serviço?
   - o `.env` / config foi escrito, ou fica por fazer manualmente?
3. A primeira configuração: como se aponta o produto ao SQL Server? Wizard? Edição de ficheiro? O
   guia diz onde? (o `install_wizard.py` existe — é usado, ou o cliente edita à mão?)

## 3. Conta de serviço (Regra de Ouro #2)

Segue `RUNBOOK_CONTA_SERVICO.md`. O produto liga ao SQL só com `sql_monitoring`, nunca Trusted
Connection do utilizador. Confirma:
- com que identidade o serviço corre depois de instalado (default vs o que o runbook manda pôr)?
- a troca de conta de serviço reaplica a ACL da pasta de dados? (em 2026-08-12, trocar a conta **sem**
  reinstalar não reaplicava a ACL — o serviço arrancava cego. `icacls /T` resolvia.)
- **achado aberto conhecido:** o serviço em produção corre hoje com `WINDOWS_AUTH=True` na ligação à
  Intelligence — confirma o que o instalador limpo configura por defeito. Se for Windows Auth, é
  violação da Regra de Ouro #2 a corrigir.

## 4. TLS na instalação

O produto suporta TLS (`config.yaml` `ssl.enabled`, cert em PEM). Numa instalação limpa:
- TLS vem ligado ou desligado por defeito?
- o guia explica como obter e colocar o certificado da CA interna? (o `INSTALL_GUIDE.md` §10.3-bis foi
  acrescentado a 2026-08-16 — confirma que está lá e que é seguível.)
- se ligares TLS seguindo só o guia, funciona? o serviço arranca em https?

## 5. Upgrade

1. Com o produto instalado e configurado (servidores, um utilizador extra, um mute), instala uma
   versão "nova" por cima (mesmo MSI serve para o teste).
2. Confirma que **sobrevivem**: configuração de servidores, utilizadores criados, mutes, thresholds
   ajustados, o `.env`. Um upgrade que apaga a config do cliente é achado crítico.
3. As sessões abertas: o upgrade invalida-as (esperado) ou deixa tokens órfãos?

## 6. Rollback / desinstalação

1. Desinstala. Confirma: serviço removido, porta libertada, regra de firewall removida (o
   `WixFirewallExtension` devia removê-la no uninstall).
2. **Fica lixo?** Pasta de dados com segredos, certificados, logs — o uninstall limpa ou deixa? (é
   decisão de produto se deixa os dados; o que interessa é se é **intencional e documentado**, não
   acidental.)
3. Reinstala por cima do estado desinstalado — instala limpo ou tropeça em restos?

## 7. Entregável

- Cronologia da instalação limpa: cada passo, cada prompt, cada vez que tiveste de sair do guia.
- **Lista de lacunas do `INSTALL_GUIDE.md`**: o que falta, o que está errado, o que confunde. É o
  entregável mais valioso — o piloto vai seguir este guia.
- Checklist verificado (serviço, porta, firewall, ACL, config, TLS) com o resultado real de cada um.
- Resultado do upgrade: o que sobreviveu, o que se perdeu.
- Resultado do rollback: o que ficou para trás.
- Severidade pela ótica do piloto: um passo que falha silenciosamente na instalação é crítico; um
  texto confuso no guia é médio.
