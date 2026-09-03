# Propagação V6 — lote 2026-07-28 (Wave A Resiliência de Rede + KPI Backups + UX)

> Repo V6 é **próprio** (`WATCHERDB_V6`, git local-only — o parent `projetosPython`
> NÃO o segue). `git status` por repo antes de commitar.
> Portal V6 **não é superset** do V3.3 — grep os anchors antes de assumir que existe.
> Commits de origem: `b73aaa8` e `aa686d5` (branch `wave-y/sessao-2026-07-21-22`).

---

## 0. Contrato dos dados novos — LER ANTES DE CONSUMIR

Três tabelas novas na BD partilhada (SECAO 19 do canonical). O V6 lê a mesma BD,
portanto **herda os dados sem código** — mas quem os consumir tem de conhecer duas
armadilhas, ambas confirmadas contra servidor real em 2026-07-28.

### `WDB_INSTANCE_TCP_PORT` — porta TCP aprendida
`Instance` (server_id, forma underscore) · `Host` · `Tcp_Port` · `First_Seen` · `Port_Last_Seen`

**Armadilha 1 — uma instância pode escutar em VÁRIAS portas TSQL.**
`SQLHDSTST505\I01` tem quatro: `49919`, `50760`, `50761` (só localhost) e `64195`.
Ler `sys.dm_tcp_listener_states` e escolher por `ORDER BY port` dá a **errada**.
A regra é: usar `CONNECTIONPROPERTY('local_tcp_port')` — a porta por onde a ligação
entrou, a única com prova de que funciona. A DMV serve só de fallback para ligações
que não sejam TCP (named pipes / shared memory), onde essa propriedade vem `NULL`.

**Armadilha 2 — overflow com sinal acima de 32767.**
`local_tcp_port` devolve `50760` como **`-14776`** (= 50760 − 65536). Somar 65536
quando negativo. Vale para **qualquer** consumidor deste valor, não só o collector.

> A coluna `Tcp_Port` da tabela **já vem corrigida** — quem lê a tabela não precisa
> de fazer nada. As armadilhas aplicam-se a quem for buscar a porta ao SQL Server
> outra vez (ex.: um diagnóstico novo, ou o collector V6 se algum dia o fizer).

### `WDB_HOST_IP_CACHE` — IPv4 e FQDN aprendidos
`Host` · `Ipv4` · `Fqdn` (pode ser `NULL`) · `First_Seen` · `Last_Resolved`

`Fqdn` é **sticky**: o MERGE nunca o sobrepõe com `NULL`. Serve para montar
`ServerSPN=MSSQLSvc/{fqdn}:{porta}`, que é o que **preserva Kerberos** ao ligar por IP.
Sem FQDN, liga-se à mesma por IP mas o SSPI cai para NTLM — aceitável como fallback,
não como norma. Confirmado a 2026-07-28: com `ServerSPN`, uma instância default
autenticou em **KERBEROS**.

### `WDB_PING_RESOLVER_BREAKER` — estado do breaker, por ambiente
Só o collector de ping escreve. Um consumidor de leitura deve interpretar
`Breaker_Open = 1` como **"os alarmes de offline deste ciclo foram suprimidos"** —
não como "a frota está bem". `Cycles_Open` tem tecto 3: ao fim disso os alarmes
voltam a fluir mesmo com o resolver doente.

### Regra transversal
Todas as leituras destas tabelas são **fail-open**: se a tabela não existir (DDL por
aplicar), o `GRANT` faltar, ou vierem vazias, o consumidor tem de cair no comportamento
anterior sem erro. Nunca tornar a ligação dependente delas.

---

## A. HERDA VIA BD — verificar apenas, zero código

O collector V1 é partilhado e a BD `WatcherDB_Intelligence` também. Portanto **nada**
disto precisa de código em V6:

| O quê | Porquê herda |
|---|---|
| 3 tabelas da SECAO 19 (`WDB_INSTANCE_TCP_PORT`, `WDB_HOST_IP_CACHE`, `WDB_PING_RESOLVER_BREAKER`) | DDL corre uma vez na BD partilhada |
| Captura de porta/IP no `collect_inst_availability` | Collector único |
| Cross-check + breaker no `collect_server_ping` | Collector único; menos falsos-offline beneficia V6 automaticamente |
| Contagens separadas de backup (`full/diff/other/is_damaged`) **se** V6 ler o mesmo `helpers.py` | Confirmar — ver secção B |

**Verificação sugerida (read-only, após o DDL + restart do collector):**
```sql
SELECT TOP 20 * FROM dbo.WDB_INSTANCE_TCP_PORT ORDER BY Port_Last_Seen DESC;
SELECT TOP 20 * FROM dbo.WDB_HOST_IP_CACHE     ORDER BY Last_Resolved DESC;
SELECT * FROM dbo.WDB_PING_RESOLVER_BREAKER;
```

---

## B. PROPAGAR BACKEND — V6 tem cópias próprias

### B1. Consumo de porta/IP no pool de ligações  *(prioridade alta)*

**Anchors a procurar em V6:** `_build_server_target_ex`, `resolve_ipv4_cached`,
`IPV4_DIRECT_DEFAULT_INSTANCES` em `api/connection_pool.py`.

- Se a **fase B** (2026-07-28, IPv4+ServerSPN para instâncias default) ainda não foi
  propagada, propagar **primeiro** — o lote de hoje assenta nela.
- Depois: `NET_CACHE_ENABLED`/`NET_CACHE_TTL`, `_load_net_cache()`, `_learned_target()`
  e a inserção na precedência de `_build_server_target_ex` (porta manual → porta
  aprendida → Browser → nome).
- Rollback de 1 linha (`NET_CACHE_ENABLED = False`) deve viajar junto.

### B2. Caminho de ligação do módulo Space (condição R7)  *(prioridade alta)*

**Anchors:** `class ConnectionInfo`, `get_connection_string`, `SQLServerMonitoring`
em `modules/monitoring/monitoring.py`.

Se V6 tiver esta cópia: adicionar `server_target`/`server_spn` ao dataclass, dar-lhes
precedência em `get_connection_string()` (mais `ServerSPN=` quando presente) e delegar
em `get_sql_server_pool()._build_server_target_ex(server_id)` no `execute_query`, com
import tardio (evita ciclo `api ↔ modules`).

> **Nota que custou tempo em V3.3:** havia uma anotação a dar este ficheiro como
> "código morto". Não era — é o caminho do módulo **Space**. Verificar em V6 com
> `grep -rn "app.state.sql_monitoring"` antes de decidir.

### B3. Contagens de backup separadas

**Anchors:** `no_checksum_count`, `failed_by_source`, `no_checksum_unique_seen` em
`api/routers/intelligence/helpers.py`.

- Dedupe separado para `is_damaged` (set + `by_env` próprios).
- `full_failed_count` / `diff_failed_count` / `other_failed_count`; `failed_count`
  mantém-se como soma (retrocompat).
- **Aviso:** `no_checksum_count` desce em V6 também — documentar, não é quebra de coleta.

---

## C. PORTAL V6 — grep primeiro, pode não existir

V6 pode omitir features V3.3 inteiras. Para cada item: se o anchor não existir, **anotar
como não-aplicável** em vez de criar a feature de raiz.

| Item | Anchor a procurar |
|---|---|
| Tokens de tema no painel DATAFILES (12× `#000`) | `DATAFILES (` , `files-row-` |
| Alturas em vh (70vh/60vh) | `max-height: 400px` no render de filegroups |
| Botão de ecrã inteiro + CSS + 2 chaves i18n | `toggleDatafilesFullscreen`, `space.fg_maximize` |
| `_kpiNoiseFields()` (sweep das modais) | `_buildCardExpandHtml`, `skipKeys` |
| `color: #fff` nos 5 badges | `background: #1e40af`, `#065f46` |
| Card Backups: Full/Diff/Outros + Backup danificado; checksum fora | `Full/Diff Falhou`, `backup-no-checksum`, `KPI_REPORT_GROUPS` |

**Armadilha do sweep das modais:** em V3.3 existiam **dois** renderizadores com listas
de exclusão divergentes (`_buildCardExpandHtml` e o fallback do corpo do card). Foi
assim que o ruído sobreviveu. Se V6 tiver os dois, centralizar igualmente numa função
única — senão volta a divergir.

**Armadilha do card Backups:** tirar a linha "Sem checksum" não chega — é preciso
retirá-la também de `KPI_REPORT_GROUPS.warn`, senão o grupo continua a pesar o volume
de ruído na severidade agregada.

---

## D. Validação antes de declarar propagado

- `node --check` em todos os blocos `<script>` do portal V6 (baseline conhecida: 10/10).
- `python -m ast` nos ficheiros Python tocados.
- Restart do serviço V6 (porta 8660) — cache de classe.
- Browser test nos **dois temas** (o claro é onde os bugs de cor vivem).
- Herança BD: as 3 queries da secção A.

---

## E. Pendentes que NÃO devem ser propagados ainda

- **Drill de "Backup danificado"** — em V3.3 a linha ficou sem clique de propósito
  (falta endpoint filtrado por `Failure_Source='is_damaged'`). Propagar o mesmo estado,
  não inventar um drill em V6 primeiro.
- **Checksum como informação no tab Backups** — enquadramento por decidir (o card é da
  frota, o tab é por servidor).
- **Collector V1 consumir a porta aprendida** — lote próprio, mexe no `ServerManager`
  e afecta todos os collectors de uma vez.
