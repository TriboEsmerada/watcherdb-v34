# PROMPT — Próxima sessão V3.3 (pós-sessão 2026-07-28)

Cola isto na sessão nova:

---

Lê docs/context/CONTEXT.md (entradas 2026-07-28) e executa em OODA, modo
consultor + GO por lote, memórias owner activas (panorama sempre;
nome-não-número; validação node 12/12 + py ast; BD⇒canonical+docs; commit
sempre + plano V6; antes/depois no fecho; checkpoint antes de mudanças).

## Itens, por prioridade

1. **WAVE A — Resiliência de Rede (implementação V1 + BD partilhada)** — spec:
   docs/context/WAVE_RESILIENCIA_REDE_SPEC_2026-07-28.md. Gate v1-intel JÁ DADO
   em 2 pareceres (fases 1+2, GO-com-condições; texto integral nos resultados
   dos dispatches de 28/07 — resumo nas entradas CONTEXT). Blocos executáveis
   já emitidos pelo specialist: DDL WDB_INSTANCE_TCP_PORT + WDB_HOST_IP_CACHE
   (tabelas dedicadas, MERGE sticky, NUNCA BLUE/GREEN — porta/IP evaporariam
   no outage) + captura em collect_inst_availability (dm_tcp_listener_states;
   CONFIRMAR enum real de state em DEV antes de fixar 'Online') + resolve_ipv4
   no async_server_collector + cross-check offline em collect_server_ping
   (padrão availability-crossref COM _resolve_events explícito — não repetir
   bug 27/07) + circuit breaker (só timeout, nunca unreachable; teto 3 ciclos;
   estado em BD WDB_PING_RESOLVER_BREAKER) + _load_net_cache TTL 5min no
   connection_pool (nunca query por-connect). Condições 1-9 listadas nos
   pareceres. Incluir fix trivial ping.exe zombie (proc.kill no
   except TimeoutError, collect_server_ping ~184). 5-surface wave-close.
2. **Condição 5 pendente da fase B**: query auth_scheme numa sessão criada pelo
   V33 a instância DEFAULT (ex: SQLHDSPRD013) — KERBEROS=validada;
   NTLM=corrigir Fqdn/SPN antes do rollout wave A. + NTLM PRÉ-EXISTENTE na
   ligação Intelligence (SQLHDSTST505, SPN nome curto) — corrigir na wave A.
3. **Propagação V6**: executar PROMPT_PROPAGACAO_V6_LOTE_2026-07-27.md (se
   ainda não foi) e PROMPT_PROPAGACAO_V6_LOTE_2026-07-28.md, por esta ordem.
   Repo V6 próprio; portal não é superset; grep anchors primeiro.
4. **D3 híbrido sidebar** (gate v1-intel já dado 27/07, GO-com-condições):
   pré-requisitos feitos (SS301 + flip DRY_RUN validado 3 ciclos EXECUTE
   limpos). Falta owner confirmar 2 queries BD (heartbeat INST_ENVS
   NEVER_RAN→idade real; SS301 a convergir — queries na conversa 28/07 e
   deriváveis do CONTEXT). Depois: INST_ENVS=membership+Env, servers.json=
   enrichment, fallback, filtro enabled.
5. **Wave collector V1 (restante)** — findings 27/07 ainda abertos: (a)
   collect_datafiles conflate volume desconhecido com 0 (mount points 408/412
   + SQL antigo; fix CROSS APPLY dm_os_volume_stats por ficheiro + fallback
   xp_fixeddrives + sentinela -1; aceitação: MIN/MAX do owner diverge em hosts
   mount-point); (b) collect_fg_space double-rounding GB→MB; (c) collector
   órfão collect_filegroup_usage (arquivar); (d) opcional Volume_Total_MB na
   DATAFILES_STG. Pode FUNDIR com a wave A (mesmo gate/ficheiros V1).
6. **Pendências leves**: audit "nome, não número" restantes modais (sweep A);
   2ª "sem resposta" no skeleton Overview (~timedFetch 14386, mesma classe do
   fix lc.track); quick wins sweep (?includeSystem= ignorado; cluster.py nunca
   registado); card Instances Off drenado? (verificar auto-resolve pós-rede);
   decisão refactor displayTitle dos 23 KPIs EN nas modais (KPI_METADATA
   title=chave de controlo JS — wave própria).

## Contexto operacional
- Branch: wave-y/sessao-2026-07-21-22 (monorepo). Commits 28/07: f0cdd79
  (lote Space+portal+diag), 92c6c60 (fase B resiliência) + blocos de fecho
  (fix FileGroups 27/07 recuperado, gitignore forecasts, docs) — confirmar
  com git log se o owner executou os 3 blocos finais.
- Serviços: qualquer edit backend exige Restart-Service V33 (class cache).
- REDE: incidente 28/07 (resolver do workstation congelava getaddrinfo;
  VPN mudou IP 5x; adaptadores VBox/WSL desligados pelo owner; estável no
  fecho). Se voltarem falsos-offline em massa: é o resolver LOCAL, não a
  frota — diagnóstico completo no CONTEXT 28/07.
- Artifact de progresso atualizado (28/07 fecho):
  https://claude.ai/code/artifact/7697c3d3-c63d-4b5f-8e7f-82448e1a7460
