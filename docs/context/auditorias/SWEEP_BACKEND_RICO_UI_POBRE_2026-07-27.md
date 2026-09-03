# Sweep "backend rico, UI pobre" — 2026-07-27

Pergunta do owner: "temos mais coisas que o backend já classifica ou traz, onde o
trabalho grosso já está feito, e falta só expor na UI?"
Método: 2 explorers em paralelo. Vertente A = campos devolvidos no JSON e nunca
renderizados (cruzamento response dict ↔ portal HTML, com validação de contexto
anti falso-positivo). Vertente B = inventário de ~250 rotas ↔ call-sites reais
no portal + static/js.

Precedente da classe: modal Backup Failed descartava Job_Name/Message que a API
já enviava (diagnosticado 2026-07-15, corrigido). Exemplo-gatilho: aba Log
descarta category/event_type/categories_found (levou à feature chips, sessão de hoje).

---

## BUGS (agir primeiro)

1. **`?includeSystem=` ignorado silenciosamente** — portal envia o param para
   `/api/monitoring/backup/server/{id}/summary` e `/summary.csv`
   (portal:19612, 20448) mas `api_backup_summary(server_id, days)`
   (watcherdb_main.py:2222) não o aceita. O filtro "incluir bases de sistema"
   da UI **não tem efeito nenhum**. Fix: adicionar param no backend ou remover o
   controlo da UI. Candidato a FIND.
2. **Router Cluster morto em absoluto** — `api/routers/cluster.py` (WSFC
   health/events/summary, 3 rotas) tem código + testes + docs mas **nunca é
   incluído** em watcherdb_main.py nem watcherdb_intelligence.py. Funcionalidade
   cluster sobrevive só via `categories=cluster` do windows-events (que a UI
   também não chama — ver chips Log). Decisão: registar router ou remover código.
3. **Categoria MEMORY nunca coletada** (achado dos specialists dos chips,
   corroborado 2×): `MEMORY_EVENT_IDS` existe e é classificado
   (logs_collector.py:739) mas não há entry `memory` no `category_map`
   (logs_collector.py:637-647) — zero permanente disfarçado de "sem problema".

## Vertente A — campos coletados e nunca renderizados (top, por valor DBA)

| # | Campo(s) | Endpoint | Backend | Valor |
|---|----------|----------|---------|-------|
| 1 | `bad_logon_count`, `last_bad_password` | AD user details | users.py:798-799 | Sinais de brute-force/conta sob ataque — modal AD não mostra |
| 2 | `password_expired`, `password_never_expires`, `account_expires` | AD user details | users.py:787,796-797 | Findings clássicos de hardening |
| 3 | `calculation_method` | memory pressure | watcherdb_main.py:4511 | O MESMO "80%" significa coisas opostas conforme o método — sem isto o DBA pode misinterpretar |
| 4 | `available/total_physical_memory_mb` | memory pressure | :4516-4517 | Distingue "SQL consome tudo" de "SO sob pressão externa" |
| 5 | `os_page_reads_per_sec` | memory server | :3615,3650 | HARD paging (muito mais forte que pages/sec, que já é mostrado) |
| 6 | `session_status`, `last_request_start` | active-sessions | queries/performance.py:106,108 | Identifica sessões idle c/ transação aberta (coma de bloqueio + crescimento de log) |
| 7 | `next_expected`, `hours_since_last`, `last_backup` | backup patterns | watcherdb_main.py:2752-2754 | Previsão proativa ("próximo backup esperado às HH:MM") vs só retrospetiva |
| 8 | `hour_range`, `days_missing`, `expected_interval_days` | backup patterns | :2744-2751 | Janela real de execução + magnitude do atraso |
| 9 | `expected_datetime`, `actual_datetime` | backup gaps | backup_pattern_analysis.py:65-66 | Timestamp exato esperado vs real, em vez de só "N horas" |
| 10 | `min_duration_seconds`, `most_recent/oldest_days_ago` | jobs trends | jobs.py:838-840 | Variância min-max = jobs instáveis |
| 11 | `date_modified` | jobs list | jobs.py:280 | "Job alterado em X" — investigação de regressões |
| 12 | `member_type` em critical_roles | users | users.py:334-336 | Membro de sysadmin é grupo AD (privilégio indireto) vs login direto |

Nota do explorer: engines Security/Space/AlwaysOn/CPU não foram cruzados
exaustivamente — vertente A-bis se quisermos cobertura total.

## Vertente B — capacidades dormentes

### Params opcionais nunca passados (endpoint É chamado)
- `windows-events`: `categories` (canais cluster/csv/backup/service_broker),
  `levels` (Warning/Information), `max_events` (teto 200) — 3 params mortos.
  (Chips Log fase 1 resolve `categories`.)
- `backup gaps`: `severity` (low/medium/high/critical).
- Filtro `database` em 4 endpoints de queries (missing-index, file-growth,
  filegroup-growth history+forecast) — drill por DB específica.
- `jobs`: paginação server-side existente e nunca usada.

### Áreas inteiras de backend sem UI (Tier A)
- **`/api/os/*`** (12 rotas: memória/CPU/disco por drive, correlação
  CPU×mem×IO, servers-attention, dashboard summary) — monitorização host-level
  completa sem superfície no portal. O maior buraco.
- **`/api/sqlserver-kpis/*`** (17 rotas) — motor de KPIs REDUNDANTE ao
  intelligence-kpis, nunca invocado. Candidato a decisão: deprecar ou migrar.
- **`/api/v1/overview/*`** — dashboard de frota (problems, health-distribution,
  drill por instância); portal só usa os-boot.
- **`/api/discover/*`** — descoberta de bases sem gatilho na UI.
- **`/api/v3/alerts/*`** — despacho de alertas (canais) pronto, sem UI.
- **`/api/copilot/*`** — include comentado (Pro — correto estar fora do Std).

### Endpoints avulsos de alto valor DBA (Tier B)
- `why-log-not-run` (watcherdb_main.py:825) — diagnóstico "porque não correu o
  log backup"; alto valor, sem botão.
- `memory/recommendations` + `memory/report` (:4658, :4742) — recomendações de
  Max Server Memory por frota.
- `backup/server/{id}/health` (:2505) — health score de backup por servidor.
- `tempdb-villains` + `tempdb-growth-culprits` — quem enche o tempdb.
- `disk-unallocated/expansion-opportunities` — espaço para expandir.

(Lista completa Tier C no output do explorer — rotas diagnósticas secundárias.)

---

## Leitura do orquestrador (proposta de priorização)

Quick wins UI-only (campo já chega, é só renderizar): A1-A2 (AD security),
A3 (calculation_method), A6 (Sessions idle c/ transação), A5 (hard paging).
Bugs a corrigir já: includeSystem + decisão cluster.py + category_map memory.
Decisões de produto (não são só UI): /api/os/*, sqlserver-kpis redundante,
overview de frota, alert routing — cada um merece avaliação tier + ROI antes
de ganhar UI. NÃO transformar isto numa wave única gigante; consumir por waves
pequenas temáticas.

Estado: relatório de sweep, NADA aplicado. Decisões owner pendentes.
