# Resposta ao QA — triagem da Ronda 2 e desbloqueio da Ronda 3

Data: 2026-08-18 · Para: QA Sénior externo · De: equipa WatcherDB V3.3

---

## Parte A — As três perguntas que bloqueiam a Ronda 3

Verificadas no código, não inferidas.

### A1. O rate limiter é por IP. Tens razão, e o furo é real.

```python
watcherdb_main.py:344            Limiter(key_func=get_remote_address, default_limits=[...])
api/routers/auth_compat.py:17    Limiter(key_func=get_remote_address)
api/routers/intelligence_kpis.py:269   Limiter(key_func=get_remote_address)
```

As três instâncias usam `get_remote_address`. Um gerador de carga partilha um único
balde de 100 req/min, exactamente como calculaste. **Um token por VU não resolve** —
a chave é o IP, não o token. Restam duas saídas: whitelist do IP do gerador para a
janela, ou distribuir por vários IPs.

O cenário B, como está, mede o `slowapi`. Confirmado.

### A2. As três rotas existem. O teu palpite sobre `server-info` estava invertido.

| Rota do plano | Estado |
|---|---|
| `GET /api/server-info` | **existe** — `watcherdb_main.py:1110`. É esta, não `/api/servers` |
| `GET /api/auth/validate` | **existe** — `api/routers/auth_compat.py:325` |
| `GET /healthz` | **existe** — `watcherdb_main.py:1606`, e está na lista de rotas sem autenticação (`:662`) |

`/api/servers` só aparece em templates legacy e num router HTMX que devolve HTML,
não JSON. Não serve para o harness.

Os endpoints `/api/v1/live/{inst}/...` continuam por confirmar do nosso lado — o
`setup()` que descobre instâncias a partir de `/live/channels` é a abordagem certa.

### A3. O pool não é "8 vs 30". São seis pools distintos, e o do dashboard é 20.

| Ficheiro | Workers | O que serve |
|---|---|---|
| `api/routers/intelligence/helpers.py:34` | **20** | **o dashboard — é este que a Ronda 3 mede** |
| `api/routers/intelligence_kpis.py:33` | 20 | KPIs |
| `api/connection_pool.py:130` | 8 | pool central de ligações (`POOL_MAX_WORKERS`) |
| `api/routers/queries/helpers.py:34` | 8 | queries ad-hoc |
| `api/routers/live_monitoring.py:1200` | 10 | LIVE |
| `api/routers/alwayson.py` (3 sítios) | **1** | AlwaysOn |

`POOL_MAX_WORKERS = 8` não tem override em YAML nem em variável de ambiente —
é literal no ficheiro.

**O `max_workers=1` do AlwaysOn é novo para nós** e não estava no teu plano. É um
ponto de serialização: sob o cenário A pode estrangular antes de qualquer pool maior.
Vale a pena instrumentar `/api/alwayson/*` à parte no harness.

---

## Parte B — Triagem da Ronda 2

### B1. R2-01: acertaste no mecanismo. Duas correcções.

A tua hipótese ("a verificação está dentro da função em vez de num `Depends`") está
**confirmada no código**. O FastAPI resolve as dependências da assinatura antes de
`request_body_to_args`; um gate chamado no corpo da função deixa o Pydantic validar
primeiro. É por isso que os quatro operacionais dão 403 e estes dão 422.

**Correcção 1 — o alcance é maior.** Concluíste "pontual e cirúrgico, não sistémico".
São **oito** endpoints com corpo e gate inline em `auth_compat.py`, não dois — encontraste
dois porque testaste dois:

| Linha | Endpoint | Testaste |
|---|---|---|
| 363 | `POST /users` | não |
| 409 | `POST /users/{u}/toggle` | não |
| 442 | `reset-password` | sim |
| 484 | `admin/users/{u}/update` | não |
| 506 | `admin/session-policy` | não |
| 719 | `admin/ad-config` | não |
| 732 | `admin/ad-domains` | não |
| 744 | `admin/users/{u}/role` | sim |

Os `GET /admin/*` têm o mesmo defeito, mas sem corpo para validar — por isso dão 403
e passaram no teu teste.

**Correcção 2 — a severidade é menor.** Verificámos linha a linha: `_require_admin` é a
**primeira instrução executável** dos oito. Nada corre antes. Com corpo válido a função
é entrada e o gate nega antes de qualquer mutação — **não há escalada**. O
`{"role":"admin"}` que (bem) não disparaste daria 403.

Reclassificámos **GRAVE → MÉDIA**. Continua a valer a correcção: desserializa corpo não
autorizado, revela nomes de campo (o teu R2-06 é o mesmo defeito), e anula a heurística
de detecção de qualquer auditoria futura. Mas um relatório para cliente banking não pode
dizer GRAVE aqui.

Podes fechar o R2-01 sem disparar o payload de escalada — a leitura do código responde.

### B2. R2-02: já está corrigido, atrás de uma flag desligada por decisão.

`watcherdb_main.py:3358-3374` já tem o gate. Está atrás de
`security.rbac_live_admin_only`, que ficou a `false` por decisão do owner a 16/08.
Ligar a flag fecha a página a viewer **e** a dba. É config, não código.

Nota lateral: esse gate tem um `except Exception: pass` deliberado — falha aberta se a
config não carregar. Defensável num shell sem dados, mas fica registado.

### B3. R2-07: era regressão nossa, e tu só viste metade.

Reportaste "o dba não recebe os botões". A realidade: **ninguém os recebia, admin
incluído.** Os dois botões tinham `display:none` inline e nenhum atributo de gate.

Causa, por `git show`: um commit nosso removeu `data-dba-gated="1"` dos dois botões
para os tornar visíveis a toda a gente — mas o `display:none` ficou, e era o atributo
que servia de interruptor.

**Corrigido** (`7ba4da1`), com decisão do owner: visíveis a `dba` e `admin`. O viewer
deixa de ter caminho para o ecrã de Collectors — sabemos que argumentaste o contrário
("é o que garante que ninguém repara nos 129 dias") e o argumento foi ouvido; a decisão
foi do owner.

O teu método de repetir numa aba carregada de raiz evitou um falso positivo. Registámos.

---

## Parte C — O que mudou no código desde que testaste

**Importante para a próxima ronda: testaste código que já não é o que está a correr.**

| Achado teu | Estado |
|---|---|
| B-03 frescura fabricada (`last_update` = `datetime.now()`) | corrigido — `d64ce2a` |
| B-01 ratchet de disponibilidade + ambiente por `LIKE` | corrigido — `d64ce2a` |
| B-05 TDE "0 certificados" | corrigido — `858efe5`: query falhada dá 503, não lista vazia |
| DSK005 "Discos OK" com I/O não lido | corrigido — `25ca9ec`: estado por fonte |
| Race de abas, fuga de tooltips, `aria-live` | corrigido — `4a8e4b0` |
| R2-07 botões mortos | corrigido — `7ba4da1` |
| B-06/07 backup "0 issues" | **fechado — ver C1** |

### C1. B-06/07: a API estava certa. O ecrã é que mentia.

Levantaste a hipótese de o `BackupAnalysisEngine` ler o `msdb` da réplica errada.
**Refutada com dados.** Em `SQLHDSPRD013\I03`: é PRIMARY, `automated_backup_preference`
= `primary`, e os 30 registos de `msdb.dbo.backupset` têm `server_name` = o próprio
servidor.

O horário real, extraído de `backupset`:

| Dia | 22:00 |
|---|---|
| 13/08 | FULL |
| 14–16/08 | DIFF |
| 17/08 | FULL |

Há backup **todos os dias às 22:00, sem falhar**. FULL de 4 em 4 dias, DIFF nos
restantes. As "36h sem DIFF" eram o FULL de 17/08 a ocupar o lugar do DIFF desse dia,
por desenho.

O defeito estava no cliente, em dois pontos: media desde o último DIFF em vez do último
backup que substitui um DIFF, e usava um limiar de 12h incompatível com um horário
diário — numa base saudável passam sempre mais de 12h desde a véspera a partir do
meio-dia, logo acusava issue todas as tardes. Corrigido em `f15bfb8`: mede desde o mais
recente de FULL ou DIFF, com limiar de 26h.

As 32 bases com "DIFF >1D" eram falso positivo. O teu B-07 ("Overview diz Backup OK")
resolve-se sozinho — consumia a API, que estava certa.

### C2. Uma correcção à tua previsão da Ronda 3

Ligaste o "100% verde com collectors parados há 129 dias" ao teste de queda de instância.
São coisas distintas: o verde vinha da frescura fabricada, já corrigida em `d64ce2a`.

A previsão sobre o pool esgotar continua boa — mas o argumento que a sustentava já não
se aplica. Vale a pena ainda ser a primeira falha a induzir.

---

## Parte D — O que continua do nosso lado

| | |
|---|---|
| `qa_viewer` provisionado com role `dba` | **invalida a coluna viewer da tua Ronda 2** — a corrigir antes de qualquer reteste |
| Rodar a password do `qa_viewer` | o teu lembrete, aceite |
| Host instável (IP mudou 4× em 24h) | três observações independentes no mesmo dia, incluindo uma medição nossa: `/healthz` — que não faz I/O — responde 200 mas em ~8,2 s sob uso concorrente normal. Não é o serviço a cair, é o event loop congestionado |
| Whitelist do IP do gerador de carga | pré-requisito da Ronda 3, ver A1 |

**Sobre o host:** a medição do `/healthz` reforça a tua leitura e é argumento para a
Ronda 3 ser a próxima. Uma ronda funcional contra um alvo a oscilar produz falsos
negativos — foi o que comeu metade da tua Ronda 2.
