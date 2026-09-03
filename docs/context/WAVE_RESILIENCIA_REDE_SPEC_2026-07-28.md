# WAVE — Resiliência de Rede (self-heal DNS / IPv6 / porta dinâmica)

> Spec executável. Base: `DESIGN_RESILIENCIA_REDE_2026-07-23.md` + parecer
> v1-intel port-discovery (2026-07-28, já GO-com-condições). Estado: aguarda
> gate v1-intel sobre as peças NOVAS (C1/C3/C4/C5) antes de qualquer código.
> Infra partilhada (coletor V1 + BD `WatcherDB_Intelligence` + V3.3). Modo consultor.

## 1. Motivação (incidente 2026-07-28)

Sobre VPN, com o host a saltar de IP (10.88.15.165→5.0→8.117→9.198):
- **`getaddrinfo` IPv6-first pendura** — `ping <nome>` e `pyodbc` por nome travam
  no AAAA/IPv6, apesar de `Resolve-DnsName -Type A` + `ping <IPv4>` funcionarem
  (16-26ms, 0% loss). Prova: `ping -4` responde; `ping` (default) pendura.
  Efeito: **40 falsos-offline** (coletor pinga por nome) + **Space lento**
  (ligações ODBC por nome esperam pelo IPv6).
- **SQL Browser (UDP 1434) bloqueado pela VPN** → instância nomeada não resolve
  porta dinâmica → cai em 1433 (errado) → ODBC Named Pipes 233.
- Ambos são **ambiente, não código**. Mas o produto deve **virar-se sozinho**
  (pedido explícito do owner 2026-07-28).

## 2. Objetivo

A monitoria passa a operar sobre **IP + porta APRENDIDOS e CACHEADOS** na BD,
com cadeia de fallback, **sem depender** de (a) resolução de nome do OS a cada
ligação nem (b) SQL Browser — e **SEM partir Windows-auth (Kerberos)**.

## 3. Componentes

### C2 — Descoberta de PORTA (`WDB_INSTANCE_TCP_PORT`) — JÁ APROVADO (parecer v1-intel 2026-07-28)
Tabela dedicada FORA do BLUE/GREEN, MERGE sticky (nunca truncate — senão a porta
some no outage que o feature serve para mitigar). DMV `sys.dm_tcp_listener_states`
(type=0, state Online — **confirmar enum real em DEV**), captura em
`collect_inst_availability.py` (só no DataFrame + `_sync_discovered_ports` MERGE
à BD central, NÃO coluna da TARGET_TABLE). GRANT SELECT `sql_monitoring`. DDL +
query + código de integração já emitidos no parecer — reproduzir tal-e-qual.

### C1 — Resolvedor IPv4-prefer + cache de IP (`WDB_HOST_IP_CACHE`) — NOVO (gate)
- Helper `resolve_ipv4(host, timeout=2.0) -> Optional[str]`:
  `socket.getaddrinfo(host, None, family=socket.AF_INET)` com timeout próprio
  (nunca pendura minutos como o default). Devolve 1º IPv4 ou `None` (**fail-open**).
- Cache TTL em memória + persistência **sticky** em `WDB_HOST_IP_CACHE`
  (`Host`, `Ipv4`, `Fqdn`, `Last_Resolved`) — MERGE, padrão `WDB_KPI_MUTE`.
- Descoberta: o coletor que já resolve/liga por ciclo grava o IPv4 observado
  (mesmo hook do C2, mesma ida-e-volta — zero ligação extra).

### C3 — Connection building: IP+porta + `ServerSPN` (preserva Kerberos) — NOVO (gate)
- Quando IPv4 (C1) **e** porta (C2/config) conhecidos:
  `SERVER={ipv4},{port};Trusted_Connection=yes;ServerSPN=MSSQLSvc/{fqdn}:{port}`.
  O `ServerSPN` mantém **Kerberos** mesmo ligando por IP (evita o NTLM-forçado
  que partiria servidores Kerberos-only).
- **Fail-open:** se falta IPv4 OU porta → comportamento ATUAL
  (`host\instance` / `host`). **Zero regressão** se a cache estiver vazia/fria.
- Toca DOIS caminhos de ligação (o gate confirma ambos — ver R7):
  `api/connection_pool.py::_build_server_target`/`_build_connection_string`
  (auth/Intelligence + endpoints) **E** `SQLServerMonitoring` (usado pelo Space
  via `app.state.sql_monitoring`).

### C4 — Cross-check de OFFLINE (mata os 40 falsos-positivos) — NOVO (gate)
- Coletor de ping: se **ping-por-nome** falha, tentar **ping/TCP ao IPv4
  resolvido/cacheado** ANTES de marcar offline. Só marca offline se o IP
  **também** falha. (Não reintroduzir o skip-branch dynamic-port já corrigido
  no auto-resolve 27/07 — ver R4.)
- V3.3 herda via BD (deteção offline lê `INST_AVAILABILITY`).

### C5 — Circuit breaker anti-alarme-em-massa (do design 23/07) — NOVO (gate)
- Se >N instâncias "offline" no MESMO ciclo **e** o resolver local está a pendurar
  (sinal: resoluções a exceder o timeout em massa) → **suprimir** o alarme de
  frota (provável problema LOCAL do host, não da frota). Reconciliação quando o
  resolver recupera. Evita 40 alarmes por um flap de IPv6 no workstation.

## 4. Cadeia de resolução integrada (precedência)
```
SERVER target =
  1. servers.json porta manual explícita (!= 1433)   -> ganha sempre (intenção admin)
  2. WDB_INSTANCE_TCP_PORT (porta descoberta, BD)     -> IP (C1) + porta (C2) + ServerSPN
  3. SQL Browser (live, UDP 1434)                     -> se disponível
  4. host\instance (nome) / host,1433                 -> fallback atual (comportamento de hoje)
Resolução de HOST em cada passo: WDB_HOST_IP_CACHE -> resolve_ipv4() -> nome cru (fail-open).
```

## 5. Perguntas de gate (v1-intel) — só as peças NOVAS (C2 já respondido)
- **R1.** `WDB_HOST_IP_CACHE`: schema + MERGE + identidade de escrita (central
  collector, NÃO `sql_monitoring`) + GRANT SELECT `sql_monitoring`. Fora BLUE/GREEN? Canonical?
- **R2.** Ponto de captura do IPv4 no coletor — mesmo hook do C2
  (`collect_inst_availability`) ou outro? Como obter o IPv4 efetivo da ligação
  bem-sucedida (`sys.dm_exec_connections.client_net_address` é do cliente; o IP
  do SERVIDOR vem de onde de forma fiável?).
- **R3.** `ServerSPN`: formato correto para **default** (`MSSQLSvc/fqdn:1433`) vs
  **named instance** (`MSSQLSvc/fqdn:port`); confirmar que `Trusted + IP + ServerSPN`
  mantém Kerberos no piso suportado; qual o risco residual de NTLM/duplo-hop.
- **R4.** Cross-check offline: onde em `collect_server_ping.py`; garantir que NÃO
  reintroduz o skip-branch dynamic-port corrigido no auto-resolve 27/07
  (`Resolved_By icmp/tcp/availability-crossref`).
- **R5.** Circuit breaker: threshold (N), onde vive o estado (adapter? tabela?),
  como distinguir "resolver local a pendurar" de "frota mesmo em baixo".
- **R6.** Precedência integrada (secção 4) — validar ordem + coexistência com o
  sync diário `servers.json -> server_config` (que já exclui `port`).
- **R7.** **Cobertura dos DOIS caminhos de ligação:** `SQLServerMonitoring` (Space)
  **E** `connection_pool` (auth/endpoints) — ambos têm de aprender IP+porta+SPN?
  Confirmar que não fica um caminho por curar (senão o Space continua a pender).

## 6. Surfaces (5-surface wave-close, desde o início)
canonical `INSTALACAO_COMPLETA_UNIFICADA.sql` (DDL das 2 tabelas) + memória schema
catalog + CHANGELOG V1 + V3.3 (SemVer + tier) + specialists `.md` (v1-intel + v33) +
bibliotecas (`knowledge_base/` + Nestor). Não repetir o gap retroativo `WDB_KPI_MUTE` R+10.

## 7. Condições herdadas do parecer port-discovery (bloqueantes)
1. Porta em tabela dedicada `WDB_INSTANCE_TCP_PORT` (nunca BLUE/GREEN nem `server_config.port`).
2. Confirmar valor real de `state` em `sys.dm_tcp_listener_states` num DEV antes de fixar `'Online'`.
3. Identidades: escrita = collector central; leitura V3.3 = `sql_monitoring` com fail-open.
4. 5-surface wave-close desde o início.

## 8. Tier
Std puro (core monitoring / conectividade). Sem features Pro. Gate v33-feature-matrix-checker no diff final.
