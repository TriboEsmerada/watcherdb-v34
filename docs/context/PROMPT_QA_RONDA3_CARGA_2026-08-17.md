# Ronda 3 — Carga e resiliência (WatcherDB V3.3)

**Esta ronda NÃO é para o QA de browser.** É uma ronda técnica, com `k6`/`locust`, conduzida por nós
ou por alguém com esse instrumento. O browser-agent não gera carga concorrente nem simula falha de
infra. Copia a partir do `---` para quem a executar.

**Notas para nós:**
- **Só depois da ronda 1.** Precisamos de saber o que é bug funcional antes de o confundir com
  sintoma de carga.
- **Janela combinada, fora de horas.** É produção; a carga sobe latência para os utilizadores reais.
- **Token, não conta de UI.** Gera um token de sessão (`qa_viewer` chega — a carga é toda GET) e usa-o
  no header `Authorization: Bearer`. Não precisas de escrita.
- **Baseline conhecido:** rate limit **100 req/min, burst 20** (`config.yaml:169-170`); polling da UI
  real = dashboard 30 s, LIVE 5 s (`portal.html:44843`, `:49001`); healthz responde em ~15 ms por IP
  local, portal ~3,5 MB. O incidente de 2026-08-17 mostrou o pool a partir (`Communication link
  failure`) — parte desta ronda é ver como o portal se comporta quando uma instância SQL cai.

---

## Objetivo

Descobrir onde o WatcherDB V3.3 parte sob uso realista de uma sala de operações, e distinguir três
coisas que hoje não sabemos separar: **lento por desenho** (endpoint analítico pesado), **lento por
carga** (contenção) e **partido** (erro/timeout).

## 1. Perfil de carga — modelar uma sala de operações real

O utilizador real não é uma rajada; são N DBAs com o dashboard aberto e polling automático. Modela:

- **Cenário A — estado estável:** 10 sessões, cada uma a repetir o padrão da UI:
  `GET /api/intelligence-kpis/dashboard` a cada 30 s + `GET /api/server-info` + `GET /api/auth/validate`
  + `POST /api/auth/heartbeat`. Duração: 30 min. Isto é o chão — se isto degrada, temos problema.
- **Cenário B — LIVE aberto:** 5 das 10 sessões abrem também o LIVE (`GET /api/v1/live/{inst}/queries`,
  `/blocking`, `/tempdb`, `/waits`) a cada 5 s. É o padrão mais pesado.
- **Cenário C — rajada:** subir de 10 para 40 sessões em 1 min e ver o que acontece ao rate limit e
  às latências. Esperado: 429 a partir de certo ponto (é o limite a funcionar) — o que interessa é
  **se o 429 é limpo** (mensagem clara, sem derrubar a sessão) ou se degrada para timeout/erro.

## 2. Métricas a recolher

Por endpoint e no total: **p50, p95, p99, máximo**, taxa de erro, taxa de 429, throughput. Marca a
fronteira: a partir de quantas sessões concorrentes o p95 do dashboard passa de (defina-se) 3 s.

Separa os endpoints em dois baldes e reporta-os à parte, senão a média mente:
- **Rápidos** (healthz, server-info, validate, heartbeat) — devem ficar em ms mesmo sob carga.
- **Analíticos** (dashboard, live/*, cognitive/*, packages/*) — alguns são legitimamente pesados;
  o que importa é se **degradam** com a carga, não o valor absoluto.

## 3. Resiliência — as falhas que já vimos acontecer

Estas reproduzem incidentes reais. Para cada uma: o portal **degrada com sinal** (diz "sem dados"/erro)
ou **mente** (zero verde / spinner eterno / timeout do portal inteiro)?

| Falha | Como induzir (com quem tem acesso) | O que observar |
|---|---|---|
| **Uma instância SQL cai** | tirar uma instância monitorizada da rede, ou apontar para um host morto | o dashboard das outras 60 continua? ou o pool esgota e trava tudo? (incidente 2026-08-17) |
| **DB Intelligence indisponível** | parar/bloquear a ligação à `WatcherDB_Intelligence` | portal dá erro claro ou spinner eterno? |
| **Restart do serviço a meio da carga** | `Restart-Service` durante o cenário A | quantos pedidos falham? recupera sozinho? quanto tempo? (shutdown demora ~15 s — achado conhecido) |
| **DNS/IP muda** | (não induzir de propósito; já aconteceu 2x) | documentar que o acesso por hostname sobrevive, por IP não |

## 4. Fugas sob duração

Deixa o cenário A a correr 30 min e mede no servidor (com quem tem acesso à máquina):
- RAM do processo do serviço ao longo do tempo — sobe e estabiliza, ou só sobe? (o
  `WatcherDBCollector` tinha 2,1 GB há 7 dias — ver se o serviço web tem o mesmo padrão)
- Contagem de threads, handles, ligações no pool SQL.
- Tamanho dos logs (a rotação a 10 MB deve segurar `audit`/`stdout`/`stderr`).

## 5. Entregável

- Tabela de latências (p50/p95/p99/máx) por endpoint e por cenário.
- A fronteira de sessões concorrentes onde o p95 degrada.
- Comportamento do 429 sob rajada (limpo vs degradado).
- Para cada falha da secção 3: degradou com sinal ou mentiu?
- Curva de RAM/threads/pool ao longo dos 30 min.
- Recomendação: mexer no rate limit? no polling (WebSocket vs poll — `connect-src` já permite `ws:`)?
  no tamanho do pool (`POOL_MAX_WORKERS=8` vs `max_workers=30` — há duas configs, resolver qual serve
  o portal)?

Não é preciso redigir dados sensíveis aqui — a carga é sintética, não lê conteúdo de produção além
dos números agregados. Mas não guardes tokens.
