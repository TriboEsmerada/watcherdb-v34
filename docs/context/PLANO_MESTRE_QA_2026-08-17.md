# Plano-mestre de QA — WatcherDB V3.3 (5 rondas)

Documento curto para dar ao QA senior a visao completa **sem lhe pedir tudo de uma vez**. Cada ronda
tem prompt proprio, instrumento proprio, conta propria e relatorio proprio. Cada relatorio volta ao
council do V3.3 para triagem com os especialistas da familia respectiva.

Decisao (owner + Claude, 2026-08-17): rondas em serie, nunca um prompt unico — as familias precisam
de instrumentos diferentes, credenciais diferentes e niveis de risco diferentes; um prompt unico
produz cobertura rasa (a 1a passagem de 2026-08-16 provou-o: matriz A–I em 20 min, 2 falsos positivos,
3 diagnosticos errados, metade dos IDs truncados).

## As 5 rondas

| # | Ronda | O que fecha | Instrumento | Conta | Risco em PRD | Prompt | Triagem por |
|---|---|---|---|---|---|---|---|
| 1 | **Varredura funcional** — 16 modulos, coerencia de numeros, estados vazios vs erro, i18n por modulo, a11y instrumental | Cobertura do produto inteiro (ate agora so' Dashboard/LIVE) | browser-agent, leitura | `qa_viewer` | Nenhum (so' GETs + 403s com corpo `{}`) | `PROMPT_QA_VARREDURA_COMPLETA_2026-08-17.md` (v2) | frontend, v33, qa |
| 2 | **Autorizacao e sessao** — matriz por role, escalada, sessao/token, stored XSS, SQLi em parametros, fuga de informacao em erros | O que um cliente banking pergunta primeiro | browser + chamadas directas | `qa_viewer` + `qa_dba` | Baixo com janela combinada (escritas reversiveis, lista fechada) | `PROMPT_QA_RONDA2_AUTORIZACAO_2026-08-17.md` | security-auditor, hacker-team, v33 |
| 3 | **Carga e resiliencia** — 10 sessoes com polling real 30 min, rate limit, latencias p95, instancia SQL em baixo, restart do servico a meio | Se aguenta uma sala de operacoes | `k6`/`locust` — NAO browser | tecnica (token) | Medio (aviso previo, janela fora de horas) | a escrever apos ronda 1 | v33, forensics, sql-deep-reviewer |
| 4 | **Instalacao limpa e upgrade** — MSI numa VM virgem, servico, firewall, cert, 1a config, upgrade sem perder config/users/mutes, rollback | O que o piloto vai fazer antes de qualquer outra coisa | VM + MSI | admin local da VM | Nenhum (VM) | a escrever | deploy-architect, packaging |
| 5 | **Plataforma** — TLS (cifras, HSTS, includeSubDomains), LDAP em claro, CVEs em dependencias, segredos no bundle/logs, firewall por subnet | Postura de seguranca da infra, nao da app | pentest / `watcherdb-hacker-team-specialist` interno | rede | Baixo (passivo) | a escrever; pode ser interna | security-auditor, hacker-team, deploy-architect |

## Ordem e porque

**1 → 2 → 4 → 3 → 5.**

- **1 primeiro**: e' o buraco real — 13 dos 16 modulos nunca foram tocados. Pronto a enviar.
- **2 a seguir**: reutiliza a sessao e o contexto da 1; e' o que o cliente banking pergunta primeiro
  ("quem ve o que, e provam?"). Precisa de `qa_dba` e janela combinada.
- **4 antes de 3**: o piloto instala antes de carregar. Descobrir que o MSI nao cria a regra de
  firewall (ja aconteceu em 2026-08-12) vale mais do que saber o p95 sob carga.
- **3 depois**: carga em PRD exige aviso previo e janela; e' melhor ja com a ronda 1 fechada para
  nao confundir bug funcional com sintoma de carga.
- **5 por ultimo, e provavelmente interna**: e' a familia que menos cabe num QA de browser e mais no
  nosso hacker-team; parte ja esta feita (TLS, HSTS, RBAC).

## Regras que atravessam todas as rondas

- **Hostname, nunca IP.** `https://TI-PF5HQWK4.tapnet.tap.pt:8433` — o IP e' DHCP e mudou 2x em
  2026-08-17. (Pedido de reserva DHCP/IP estatico em curso.)
- **Contas descartaveis por ronda.** `qa_viewer`, `qa_dba` — desactivar ou rodar no fim de cada ronda.
- **Nunca credencial de administrador.**
- **Dados sensiveis redigidos** no relatorio (hostnames, logins, texto SQL). Screenshot e' bitmap:
  preferir evidencia descrita.
- **Sintoma > causa.** Hipotese de causa-raiz sempre marcada como hipotese; 3 diagnosticos errados
  nas passagens anteriores.
- **Instrumento observa a accao?** Popups, dialogos nativos, `#toastContainer` so' nasce no 1o toast.
- **Cada relatorio e' um contrato**: o que foi testado, o que ficou fora e porque, achados.

## O que cada ronda desbloqueia

| Depois da ronda | Podemos |
|---|---|
| 1 | Fechar BUG-003 com o mapa i18n por modulo; corrigir os "zero verde" que aparecerem; ligar `rbac_live_admin_only` se decidirmos |
| 2 | Responder ao CISO do cliente com evidencia; decidir redaccao do SQL text no LIVE com dados |
| 4 | Enviar o MSI ao piloto com confianca; corrigir INSTALL_GUIDE com o que faltar |
| 3 | Dimensionar rate limit e polling; decidir WebSocket vs polling |
| 5 | Fechar `includeSubDomains`, LDAPS, CVEs antes do audit formal |

## Estado

Os 5 prompts estao escritos. As rondas correm em serie; o bloqueio de cada uma e' o pre-requisito
da anterior + a sua conta/ambiente.

- [x] Ronda 1 — `PROMPT_QA_VARREDURA_COMPLETA_2026-08-17.md` (v2). Bloqueado em: criar `qa_viewer`,
      password a parte, combinar quem faz o login (agente nao digita).
- [x] Ronda 2 — `PROMPT_QA_RONDA2_AUTORIZACAO_2026-08-17.md`. Bloqueado em: ronda 1 fechada, criar
      `qa_dba`, janela combinada (4 escritas reversiveis).
- [x] Ronda 3 — `PROMPT_QA_RONDA3_CARGA_2026-08-17.md`. NAO e' browser (k6/locust). Bloqueado em:
      ronda 1 fechada, janela fora de horas, token de sessao.
- [x] Ronda 4 — `PROMPT_QA_RONDA4_INSTALACAO_2026-08-17.md`. Bloqueado em: VM Windows Server limpa
      com snapshot; MSI construido (`dist/msi/`). Decisao owner: qual VM.
- [x] Ronda 5 — `PROMPT_QA_RONDA5_PLATAFORMA_2026-08-17.md`. Provavelmente INTERNA (hacker-team).
      Se externa: autorizacao escrita pelo template do banking_pentest.
