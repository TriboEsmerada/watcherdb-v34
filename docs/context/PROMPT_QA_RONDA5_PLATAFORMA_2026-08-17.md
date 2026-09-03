# Ronda 5 — Segurança de plataforma (WatcherDB V3.3)

**Esta ronda é provavelmente INTERNA** — cabe mais ao nosso `watcherdb-hacker-team-specialist` do que
a um QA de browser, porque exige rede, ferramentas de pentest e leitura da máquina. Só vai a um
pentester externo com **autorização escrita** (o template existe:
`~/.nestor-library/watcherdb-family/offensive_security/banking_pentest_authorization_template.md`).

**Notas para nós:**
- **Escopo AUTORIZADO apenas:** esta máquina/produto, sem tocar em prod cliente, sem DoS, sem
  exfiltração real. O canon do hacker-team já cobre isto (`watcherdb_red_team_runbooks.md`,
  `watcherdb_attack_surface_map.md`, `mssql_offensive_cheatsheet.md`).
- **Muito já está feito** nesta família — esta ronda **valida e fecha**, não abre do zero: TLS
  activado (2026-08-16), HSTS scheme-aware, CSP com nonce sem unsafe-eval, RBAC 3 níveis, auditoria de
  ROLE_CHANGED. O foco são as pontas soltas conhecidas + varredura de dependências.

---

## Objetivo

Fechar a postura de segurança da **infraestrutura** (transporte, autenticação de plataforma,
dependências, segredos, rede) antes de um audit formal de cliente banking. Distinto da ronda 2, que é
autorização **da aplicação**; esta é a camada por baixo.

## 1. Transporte (TLS) — validar o que ligámos

- **Cifras e versões:** varre o endpoint TLS (`testssl.sh`, `sslscan` ou `nmap --script ssl-enum-ciphers`).
  Aceita TLS 1.0/1.1? Cifras fracas? O alvo é TLS 1.2+ só, sem cifras obsoletas.
- **Certificado:** cadeia completa? SAN correcto? (nota: o SAN tinha o IP `10.88.10.27` que já mudou —
  ver se foi reemitido; recomendação: cert sem SAN por IP, só hostname.)
- **HSTS:** confirma que só é emitido sobre https (foi corrigido) e **decide o `includeSubDomains`** —
  hoje prende `*.tapnet.tap.pt` por 1 ano em qualquer browser que visite; se houver sistema vizinho
  em http nesse domínio, parte. Ponta solta aberta.
- **Redirect:** não há http→https na 8433 (socket TLS não fala http). Confirma que isto é aceitável
  ou se precisa de um listener http mínimo só para redirecionar.

## 2. LDAP / autenticação de plataforma

- **LDAP em claro (N-04, ainda aberto):** a config aponta `ldap://dchqprd02.tapnet.tap.pt` (389), não
  `ldaps://` (636). O bind de credenciais viaja em claro na rede interna. O produto **já suporta**
  `ldaps://` (infere 636 do prefixo, `auth_service.py:810`) — falta trocar a config. Confirma o estado
  e, depois de trocado, valida que o canal é cifrado e o cert do DC é validado (`Tls(validate=...)`).
- **NTLM fallback:** está gated por env var e default false (mitiga CVE-2025-54918). Confirma que
  continua desligado.
- **Contas locais privilegiadas:** `salomao`, `admin`, `ricardo`, `rodrigosantos` são contas locais.
  A rotação da password `salomao` estava pendente da ordem TLS→LDAPS→rotação. Confirma o estado.

## 3. Dependências (CVEs)

- `pip-audit` / `safety` sobre `requirements.txt` (122 linhas). Reporta CVEs por severidade.
- Cruza com o SBOM que o build já gera (`dist/msi/*.sbom.cyclonedx.json`) — está actualizado?
- Foco em: FastAPI/Starlette/uvicorn, pyodbc, python-jose/cryptography, pydantic. Uma CVE crítica numa
  destas é bloqueador.

## 4. Segredos

- **No bundle:** o build tem gate anti-segredos (`verify_no_secrets_in_bundle` em `build.py`, apanha
  prefixo Fernet `gAAAAA` e chaves privadas). Confirma que o gate corre e que o MSI não leva segredos.
- **Em logs:** o `[PREFS] ... username` já foi removido. Varre `audit.log`, `stdout.log`, `stderr.log`
  por: passwords, tokens JWT, connection strings com password, chaves. (O `stderr` teve texto SQL e
  logins — mas isso é dado operacional, não segredo de plataforma; distingue.)
- **Em trânsito:** connection strings, tokens — cobertos pelo TLS agora; confirmar que nada os expõe
  fora do canal (ex.: query params, referrer).
- **DPAPI/Fernet:** a master key é machine-scope. Confirma que a ACL dos ficheiros de segredo
  (`C:\ProgramData\WatcherDB\secrets\`, `certs\`) é restrita (SYSTEM+Admins+conta de serviço, sem
  BUILTIN\Users).

## 5. Rede

- **Portas expostas:** `nmap` à máquina — só 8433 devia estar exposto externamente. Alguma porta de
  debug, de outro serviço (8660 V6, collector), aberta indevidamente?
- **Firewall por perfil/subnet:** a regra foi escrita para `10.88.10.x`; a máquina está agora em
  `10.88.18.x` (DHCP mudou). Confirma que a regra acompanha a interface (precedente
  `feedback_firewall_profile_interface`, 2026-06-12: `-Profile Domain,Public -RemoteAddress <subnet>`).
- **Superfície de management:** o endpoint OpenAPI/docs (`/docs`) está exposto? Deve estar desligado em
  produção (`WATCHERDB_DISABLE_DOCS`).

## 6. Entregável

- Findings com **CVSS 3.1 + CWE + OWASP**, PoC reproduzível onde aplicável, e remediação.
- Estado de cada ponta solta conhecida: SAN por IP, `includeSubDomains`, LDAPS, rotação `salomao`,
  firewall por subnet, `WINDOWS_AUTH=True` na Intelligence.
- Tabela de CVEs das dependências por severidade.
- Confirmação (ou não) de que o bundle e os logs estão limpos de segredos.
- Recomendação de prioridade para o audit formal do cliente banking.

Handoff de findings: `watcherdb-security-auditor` para remediação (padrão purple team).
