# PROMPT — Propagação V6 do lote 2026-07-28 (V3.3 → V6)

Cola isto numa sessão no repo WATCHERDB_V6 (repo git PRÓPRIO). Executa em OODA,
modo consultor + GO por lote. REGRAS: portal V6 NÃO é superset do V3.3 — **grep
anchors primeiro**; adaptar, não colar (V6 sem t()/i18n em partes; strings PT
hardcoded). Validação: script blocks node (baseline V6 = 10/10) + py ast.
NOTA: o lote 27/07 tem prompt PRÓPRIO (PROMPT_PROPAGACAO_V6_LOTE_2026-07-27.md)
— confirmar primeiro se já foi executado; este cobre SÓ o lote 28/07.

## Origem (commits V3.3, branch wave-y/sessao-2026-07-21-22 do monorepo)
- f0cdd79 — pacote Space + portal extras + diag 15s
- 92c6c60 — fase B resiliência (connection_pool IPv4+ServerSPN)
- (+ commit dos docs/fecho, ver git log 2026-07-28)

## Itens a propagar (por prioridade)

1. **Pacote Space (drilldown Databases→FileGroups→DATAFILES)** — 6 sub-itens:
   (a) helper global `sortNestedTable` par-aware (linhas de dados arrastam
   containers `fg-row-*`/`files-row-*`) + onclick nas 3 theads + CSS afordância
   `th[onclick*="sortNestedTable"]::after` ⇅ + classe `lc-active-sort`;
   (b) Free MB/% EFETIVO na tabela FileGroups (matriz growth: growth ativo+max
   finito = Σmax−usado; growth=0 = alocado−usado; unlimited = disk-bound →
   display alocado + tooltip `*`), reclassify display=veredicto;
   (c) Status FULL (vermelho, used≥99.5% current && !canGrow) / MAXED (âmbar,
   atCap com espaço interno) nos datafiles, precedência OVERFLOW mantida;
   (d) coluna Used MB nos datafiles (— em AG secondary);
   (e) Logical Name sem truncagem (min-width 420, word-break);
   (f) backend `modules/monitoring/space_analysis.py`: query principal de files
   reescrita `USE [db]` + `sys.database_files` + `FILEPROPERTY SpaceUsed` +
   `GrowthRaw`/`IsPercentGrowth` + volume stats; `query_ag_secondary` SEM USE
   (mantém sem Used); `query_precisa` +GrowthEnabledFiles/UnlimitedGrowableFiles/
   EffCapGB/EffCapMB; mappings +used_size_mb/+growth_raw/+eff_cap_*.
   V6: verificar se o space_analysis.py do V6 divergiu antes de portar (diff).

2. **Perf Space**: `_SPACE_ANALYSIS_CACHE` TTL 120s por servidor (revisitas
   instantâneas, chave server_id, `cached:true` no payload) + BATCH_SIZE 5→12
   (verificar max_connections do pool V6 antes — V3.3 tem 30).

3. **Fix checklist de loading (bug-raiz)**: `startLoadingChecklist` com
   `_lcInstanceSeq` global + keys/elementos scoped por instance
   (`data-lc-inst`) — sem isto, loads sobrepostos da mesma tab colidem na key
   `lc-item-1` e o abort de um remove/marca-X o item do outro ("só segundos").
   + `lc.track` remove item em ABORT (isAbort/AbortError) em vez de X falso.
   V6: verificar se o V6 tem o helper (foi wired 16/07 no V3.3; grep
   `startLoadingChecklist` no portal V6 — pode não existir → N/A).

4. **Deep-link Space**: `navigateToSpaceFilegroup` budget 15s→60s (db) e
   10s→20s (fg) — servers 90+ DBs excediam 15s a frio e o deep-link desistia.

5. **Portal extras**: label card Backups `Falharam`→`Full/Diff Falhou`
   (_advRow display-only, keys intocadas); seletor de janela nos logs de
   serviço 6h/24h/3d/7d (`serviceLogsCtx`+`changeServiceLogsWindow`+
   `serviceLogsWindowSelectorHtml`, visível também no estado vazio; backend já
   aceita hours≤168); rodapés `_advFoot` removidos (Erros log no Performance;
   PAGE_VERIFY!=CHECKSUM + DBs avaliadas no Integridade).

6. **Diagnóstico de rede**: `_query_sql_browser` timeout default 3.0→15.0s
   (api/routers/network_diagnostics.py — VPN lenta fazia UDP 1434 parecer morto;
   call-site rápido com timeout=2.0 explícito fica).

7. **Fase B resiliência (api/connection_pool.py)** — AVALIAR antes de portar:
   `resolve_ipv4_cached` (daemon thread bounded 2s + semáforo cap 4 +
   AI_CANONNAME — NUNCA getfqdn/PTR, pendura em resolver partido; NUNCA
   ThreadPoolExecutor — bloqueia exit/service stop) + `_build_server_target_ex`
   (default instances → `IP,1433` + `ServerSPN=MSSQLSvc/fqdn:1433`; nomeadas e
   porta manual inalteradas; fail-open total; rollback
   `IPV4_DIRECT_DEFAULT_INSTANCES=False`). CONDIÇÃO 5 do gate v1-intel:
   validar `auth_scheme=KERBEROS` pós-deploy — se no V3.3 ainda não estiver
   validada, NÃO portar ainda. V6: confirmar se o connection_pool do V6 é o
   mesmo consolidado (grep `_build_server_target`).

## Fora de scope deste prompt
- Wave A resiliência (WDB_INSTANCE_TCP_PORT + WDB_HOST_IP_CACHE + cross-check
  offline + circuit breaker) — é V1/BD partilhada, V6 herda via BD quando
  shipada; parecer v1-intel fases 1+2 já emitido (GO-com-condições).
- Fix FileGroups 27/07 (intelligence/helpers.py + intelligence_kpis.py) —
  coberto pelo prompt do lote 27/07.

## Validação V6
- node script blocks (baseline 10/10) + py ast dos .py tocados.
- Browser: caso FG real (SQLIDSPRD03/DW_ODS_TAP se visível no V6): Free
  efetivo ≈0.7% CRITICAL + datafile FULL; sort move containers junto;
  checklist sem X falso.
- Tier: tudo Std/core (V6 herda); sem creep.
