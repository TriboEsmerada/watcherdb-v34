# Wave DS-Reconcile — Tracking

> Living doc. Reconciliacao do export do **Claude Design** (claude.ai) contra o
> frontend vanilla de producao do **WatcherDB V3.3**.
> Mantido pela AI por pedido explicito do owner (2026-06-08).
> Escopo: **V3.3 apenas**. Propagacao a V6 so APOS V3.3 validado (decisao owner).

---

## V6 PROPAGATION CHECKLIST (consolidado — propagar APOS validar tudo em V3.3)

> Regra v33->v6, MAS V6 portal e' subset (nao superset) -> grep anchors em V6 ANTES de aplicar.
> Estado: PENDENTE (so' depois de V3.3 estavel + validado pelo owner).

### Backend (alta probabilidade de existir igual em V6)
- [ ] **Security Mock -> real** (`watcherdb/api/routers/security.py`): eliminar MockSQLMonitoring,
      injetar app.state.sql_monitoring via Request. V6 tem o mesmo router (confirmado specialist).
- [ ] **Parsing** `replace('_','\\')` em main (memory/cpu/pressure) + routers V6 (memory.py/cpu.py).
      V6 tem MAIS ocorrencias dispersas (specialist) — grep todas.
- [ ] **Fix B + diag** `security_analysis.py`: _make_unknown_check + loop agregacao + guarda config.
- [ ] **#1+#3+F5 KPI**: _collect_and_cache_dashboard (sem request) + preload corrigido +
      jobs Phase3 wait_for(10) + re-warm loop 50s no lifespan. V6 tem mesmo lifespan/preload (V1-spec).
- [ ] **#2 defer discovery** (sleep 300 + max_concurrent 5) no _background_prewarm V6.

### Frontend (V6 portal e' SUBSET — verificar cada anchor antes)
- [ ] **Token extensions** no :root inline V6 (--color-border, --color-bg-hover, --sev-*, etc.).
- [ ] **T-tabs tokens** (--color-accent, --card-bg) se V6 os usa.
- [ ] **Sidebar P-C** (dot+chip env) se o render V6 for equivalente.
- [ ] **search autocomplete=off** no input de busca V6.
- [ ] **#4 fetch timeout** (90s) + remover probe extra, se V6 tiver detectKpiEndpoint.

### Ficheiros externos (V6 pode nem usar)
- [ ] T1 design-system.css / T3 portal_fix_styles.css / T4 space_dashboard.html — confirmar se V6
      os carrega antes de propagar (em V3.3 estao parcialmente mortos/legacy).

### Achados a tratar (nao so propagar)
- [ ] config.yaml passwords default em texto-claro (HIGH) — V3.3 E V6.
- [ ] `_require_admin` ausente em endpoints security/dashboard + NameError em generate_predictive_report
      (main:4914) — verificar em V6.

---

## 0. CORRECAO CRITICA (2026-06-08, descoberta na validacao browser)

**Os ficheiros CSS externos NAO sao carregados pelo portal vivo.**

- `watcherdb_portal.html` (servido em `/watcherdb`) **nao linka** `watcherdb-design-system.css`
  nem `portal_fix_styles.css`. So linka FontAwesome, CodeMirror, `i18n_selector.css`.
- Todo o styling do portal vivo esta **inline** num `<style>` (`:root` na linha ~47),
  com a sua propria copia dos tokens. `design-system.css` e' uma copia EXTRAIDA
  (derivada) do portal -> editar nao reflui para producao.
- `portal_fix_styles.css` so e' linkado pelo template **legacy**
  `templates/legacy/watcherdb_portal_legacy_corrected.html` (rotas legacy separadas).

**Impacto nos fixes ja aplicados:**
- **T1** (editado em `design-system.css`) -> NAO afeta o portal vivo. Bug real
  (`--color-border` usado 21x / definido 0x INLINE) continua em producao.
- **T3** (editado em `portal_fix_styles.css`) -> so afeta a rota legacy. O "tema claro"
  do audit era artefacto legacy; a vista de Filegroups viva (modal) ja e' dark via
  CSS inline da SPA. Sem impacto visivel em producao.
- **T4** (`space_dashboard.html`) -> CONFIRMADO live (rota propria). Continua valido.

**Conclusao:** o audit Claude Design trabalhou sobre ficheiros externos parcialmente
mortos/legacy. O fix real do T1/T2 tem de ir para o `<style>` INLINE de
`watcherdb_portal.html`. Edits T1/T3 nos ficheiros externos: manter (corrigem
legacy + copia modular, inofensivo) mas NAO contam como fix de producao.

---

## 1. Contexto & origem

- Corrido o Claude Design sobre o frontend V3.3 -> export em `Claude Design/`
  (nomes de ficheiro vieram baralhados: `.css` com JSX, audit-canvas dentro de
  `severity.css`). Export = kit React/JSX + canvas de auditoria.
- **Constrangimento de arquitetura:** o portal de producao e vanilla single-file
  SPA por decisao deliberada (footprint on-prem banking, **sem React, sem CDN
  externo**). O export NAO e deployavel -> "implementar" = **traduzir** as
  decisoes para o CSS/HTML vanilla existente, nao importar ficheiros.
- **Principio de tokens:** estender o namespace DS existente
  (`--color-bg-*`, `--color-text-*`) e NAO importar o namespace do kit
  (`--surface-*`, `--text-*`). Evitar a 5a palette (o pecado que o audit denuncia).
- Tier: `Filegroup Usage` esta em "Core monitoring KPIs" no `FEATURE_MATRIX.md`
  -> **Std**. Logo `space_dashboard.html` pertence ao V3.3 e o T4 justifica-se.

## 2. Descobertas verificadas (contra codigo real, nao mocks)

| # | Descoberta | Confirmacao no codigo real | Impacto |
|---|---|---|---|
| **T1** | `var(--color-border)` usado mas nunca definido (cai em `currentColor`) | 0 definicoes / 38 usos no repo. Extra: `--color-bg-hover` tambem undefined (`watcherdb-design-system.css:346`) | Alto |
| **T2** | Severidade codificada so por cor (border-left) -> falha WCAG 1.4.1 | stat-card/kpi-card border-left hue-only; badges sem icone | Medio-Alto |
| **T3** | `portal_fix_styles.css` tema CLARO (cards brancos + cream) sobre portal escuro `#0a0f1a` | `background:white` x6 + `#fef3c7`/`#92400e`/`#78350f` | Alto |
| **T4** | `space_dashboard.html` usa **Tailwind + Alpine.js + Chart.js via CDN** | linhas 7-10; markup todo em classes Tailwind | Alto |

## 3. Estado das tarefas

| Tarefa | Estado | Prioridade | Esforco | Ficheiro alvo |
|---|---|---|---|---|
| **T1** — tokens em `design-system.css` | ⚠️ aplicado em ficheiro NAO-LIVE (ver sec.0) | P0 | `static/css/watcherdb-design-system.css` |
| **T1-LIVE** — mesmos tokens no `:root` INLINE | ✅ **APLICADO** 2026-06-08 (fix real) | P0 | `templates/watcherdb_portal.html` |
| **T3** — re-skin tema claro | ⚠️ aplicado, so afeta rota legacy (ver sec.0) | P3 | `static/css/portal_fix_styles.css` |
| **T4** — remover CDN, reescrever vanilla | ✅ **APLICADO** 2026-06-08 (live) | P1 | `templates/space_dashboard.html` |
| **T2** — classes `.sev-badge`/`.alert-row` | ⏳ pendente (depende i18n) — alvo = inline portal | P2 | `templates/watcherdb_portal.html` |
| **i18n** — 5 chaves sev_* em pt/en/es | ⏳ pendente | — | `static/i18n/{pt,en,es}.json` |
| **V6 propagation** | ⏸️ DEFERIDO ate V3.3 validado | — | repo V6 |

## 4. Log de implementacao

### T1 — APLICADO 2026-06-08
- **Ficheiro:** `static/css/watcherdb-design-system.css`
- **Mudanca:** bloco `:root` ADITIVO inserido apos linha 132 (fim do `:root`
  principal). Zero alteracoes a tokens existentes.
- **Tokens adicionados:**
  - `--color-border: #334155` (+ `--color-border-strong`, `--color-border-subtle`)
    -> resolve as 38 refs que caiam em `currentColor`.
  - `--color-bg-hover: var(--color-bg-tertiary)` (#243447) -> resolve ref undefined
    em `:346`, reusa valor existente (nao duplica).
  - `--color-bg-panel: #1e293b`, `--color-bg-sunken: #0f172a`, `--color-text-link: #60a5fa`.
  - Escala severidade 5-niveis `--sev-{ok,info,warning,critical,overflow}-{text,tint,border,solid,on}`
    (preparacao T2; inerte ate ser usada).
- **Waiver:** `[WAIVER aplicado 2026-06-08 | regra: edicao ficheiro producao sem
  aprovacao manual | scope: T1 token fix only]` registado no comentario do bloco.
- **Verificacao:** CSS estatico -> hard-refresh (Ctrl+F5) no portal. Sem restart
  de servico (so necessario para `.py`).
- **Status validacao browser:** ⏳ pendente confirmacao visual do owner.

### T3 — APLICADO 2026-06-08
- **Ficheiro:** `static/css/portal_fix_styles.css`
- **Mudancas (13 edits):**
  - `:root` neutros remapeados: `--color-dark` -> `var(--color-text-primary)`,
    `--color-gray` -> `var(--color-text-tertiary)`, `--color-light` -> `var(--color-border)`.
  - **Armadilha resolvida:** `--color-dark` estava sobrecarregado (texto E fundo).
    `.filegroup-type-badge` background mudado para `var(--color-bg-elevated)` para
    nao ficar texto branco sobre fundo claro apos o remap.
  - Fundos brancos -> tokens dark: `.summary-card`, `.filegroup-card`,
    `.filegroup-header`, `.health-score-card` -> `--color-bg-secondary`;
    `.metric` -> `--color-bg-panel`; `.logical-name-tag` -> `--color-bg-tertiary`;
    `.details-content` (#f9fafb) -> `--color-bg-primary`;
    `.btn-details:hover` (#e5e7eb) -> `--color-bg-tertiary`.
  - `.risk-factors` cream: `#fef3c7` -> `--sev-warning-tint`,
    `#92400e` -> `--sev-warning-text`, `#78350f` -> `--color-text-secondary`.
  - Bloco `@media (prefers-color-scheme: dark)` removido (contraditorio; dark e default).
- **Waiver:** `[WAIVER aplicado 2026-06-08 | scope: T3]` no comentario do `:root`.
- **Verificacao read-only:** 0 `background:white`/cream restantes; 9 `color:white`
  legitimos (texto sobre cor solida); chavetas 91/91. CSS estatico -> Ctrl+F5.
- **Fora de scope (registado, nao tocado):** o `:root` ainda redefine `--radius-*`,
  `--shadow-*`, `--font-mono` que colidem com globais DS -> cleanup futuro.
- **Status validacao browser:** ⏳ pendente confirmacao visual do owner.

## 5. Flags transversais (antes de qualquer ship)

- **i18n (T2):** faltam chaves `sev_ok`, `sev_info`, `sev_warning`, `sev_critical`,
  `sev_overflow` em `pt.json`/`en.json`/`es.json`. Badges devem usar `data-i18n=...`,
  nao texto hardcoded.
  - PT: Saudavel / Info / Aviso / Critico / Esgotado
  - EN: Healthy / Info / Warning / Critical / Breached
  - ES: Saludable / Info / Advertencia / Critico / Superado
- **Browser test (T4):** handler `copySQL` passa de Alpine `@click` para
  `onclick="copySQL(this)"` com `data-sql`. SQL com aspas pode partir o atributo
  -> `escapeAttr()` obrigatorio + teste browser manual (precedente: incidente
  Wave S 2026-06-01, JSON em onclick double-quoted).
- **Chart.js (T4):** confirmar path local (`static/js/Chart.min.js`?) antes de
  remover o CDN.

## 6. Plano de propagacao V6 (DEFERIDO)

> So executar APOS T1-T4 validados em V3.3 (decisao owner 2026-06-08).
> Regra v33->v6, mas V6 portal pode ser subset -> grep anchors primeiro.

- **T1:** grep V6 `var(--color-border)` para confirmar mesmo bug antes de propagar.
- **T2:** classes CSS aditivas; grep V6 `.sev-badge` (pode ja existir em overlays Pro).
- **T3:** confirmar se `portal_fix_styles.css` existe em V6 (feature pode ter sido
  reimplementada).
- **T4:** confirmar se `space_dashboard.html` existe em V6 com a mesma implementacao.

## 7. Governanca / log de waivers

| Data | Operacao | Mecanismo | Scope |
|---|---|---|---|
| 2026-06-08 | Edit `watcherdb-design-system.css` (T1) | Handshake (All the time / god is good) | T1 token fix, 1 bloco aditivo |
| 2026-06-08 | Criar/manter este tracking `.md` | Aprovacao explicita do owner ("salve em .md") | Documentacao, nao-producao |
| 2026-06-08 | Edit `portal_fix_styles.css` (T3) | Handshake (All the time / god is good) | T3 re-skin tema claro -> tokens dark |
| 2026-06-08 | Edit `watcherdb_portal.html` (T1-LIVE) | Handshake (All the time / god is good) | T1-LIVE tokens no :root inline (fix real producao) |
| 2026-06-08 | Rewrite `space_dashboard.html` (T4) | Handshake (All the time / god is good) | T4 remover CDNs Tailwind/Alpine/Chart.js -> vanilla + DS local |
| 2026-06-08 | Edit `watcherdb_portal.html` (T-tabs) | Handshake (All the time / god is good) | 2 tokens partidos --color-accent + --card-bg no :root inline |
| 2026-06-09 | Edit `security.py` + `watcherdb_main.py` (Fix1+Fix2) | Handshake (All the time / god is good) | Backend: Security Mock->real sql_monitoring + remover replace('_','\\') parsing |
| 2026-06-09 | Edit `watcherdb_main.py` + `watcherdb_portal.html` (#2+#4) | Handshake (All the time / god is good) | Perf arranque KPIs: adiar discovery 5min + max_concurrent 10->5; frontend remover probe + timeout 20s no fetch |
| 2026-06-09 | Edit `security_analysis.py` (Fix B) | Handshake (All the time / god is good) | Security: categorias que falham/vazias surfacadas como UNKNOWN (transparencia cobertura) |
| 2026-06-09 | Edit `watcherdb_portal.html` + `security_analysis.py` (search + config diag) | Handshake (All the time / God is good) | search autocomplete=off (caixa nativa tapava conteudo); guarda no _check_sql_configurations surfaca erro real |
| 2026-06-09 | Edit `watcherdb_portal.html` (P-C sidebar) | Handshake (All the time / god is good) | Redesign sidebar: dot por ambiente + chip PRD/QLT/TST (estilo mockup). Owner gostou. |
| 2026-06-09 | Edit `watcherdb_portal.html` (timeout 20s->90s) | Handshake (All the time / god is good) | #4 timeout 20s era curto p/ gather frio (~60s) -> erro; subido p/ 90s ate #1+#3 tornar rapido. |
| 2026-06-09 | Edit `intelligence_kpis.py` + `watcherdb_main.py` (#1+#3+F5) | Handshake (All the time / god is good) | _collect_and_cache_dashboard (sem request) + preload corrigido + jobs Phase3 wait_for(10) + re-warm loop 50s. Cache sempre quente. |
| 2026-06-09 | Edit `intelligence_kpis.py` (single-flight) | Handshake (All the time / god is good) | Lock single-flight: 1 gather de cada vez (re-warm 50s + gather 150s causavam espiral de pool). |
| 2026-06-09 | Edit `connection_pool.py` (pool 10->20) | Handshake (All the time / god is good) | IntelligenceConnectionPool 10->20 p/ igualar executor (20 workers); ~18 queries deixam de ficar em fila. |

## 8. Dados sensiveis

Auditados `Claude Design/`, `static/css/`, `templates/space_dashboard.html`:
nenhum dado real de cliente. Mocks (`SRV-PRD-01`, `FIN_LEDGER`) sao ficticios;
endpoints sao URLs relativas; nenhuma credencial/connection string.

---

## 9. Auditoria tab-a-tab + bugs descobertos (2026-06-08)

Auditoria estatica do portal vivo (validacao "todas as tabs"). Resultados:

### Tokens partidos (CSS class do bug --color-border) — RESOLVIDO
- `--color-accent` (6x, metric-card CSS) usado/nunca definido -> barra de selecao +
  bordas hover INVISIVEIS em CPU/Memory/Overview. Fix: `--color-accent: #3b82f6`.
- `--card-bg` (3x, AlwaysOn details) -> fundos transparentes. Fix: `--card-bg: var(--color-bg-panel)`.
- Aplicados no :root inline (linhas 89-90). Scan pos-fix: ZERO tokens partidos.

### Estado por tab (estatico)
- PARTIDO (pre-fix): CPU, Memory, Overview. SUSPEITO: AlwaysOn (--card-bg), KPI Dashboard +
  SQL Diag (eval). OK: Performance, Backup, Space, Disk, Encrypted, Services, Log, Security,
  Users, Jobs + top-level.

### Bugs BACKEND descobertos (NAO sao do redesign — pre-existentes)
- **Bug Security:** ✅ APLICADO 2026-06-09. `watcherdb/api/routers/security.py` — MockSQLMonitoring
  eliminado; injeta `app.state.sql_monitoring` real via `Request` nos 3 endpoints
  (server/summary/critical). Shadow endpoint main:2336 deixado (router ganha; cleanup opcional).
- **Bug parsing:** ✅ APLICADO 2026-06-09. `watcherdb_main.py` 3 pontos (memory ~3469, cpu ~3701,
  pressure ~4354) — removido `replace('_','\\')`, passa server_id direto. Verificado seguro:
  cpu_analysis/memory_analysis usam `_server_id_from_name` (pass-through underscore) -> match exato;
  caminho direto memory:139 so' corre com sql_monitoring=None (nunca nos endpoints live).
- **REQUER RESTART** do WatcherDBWebServiceV33 para entrar em vigor.
- **eval() risk:** main:31845 `eval(handler.onClick)` com modalTitle interpolado -> apostrofo parte
  handlers silenciosamente (reliability high). Follow-up separado (refactor eval->lookup). PENDENTE.
- **Fix3 timeout 300s** (monitoring.py:985): smell, decisao a' parte. PENDENTE.
- **Propagacao V6:** ambos os bugs existem em V6 (security.py + replace em routers V6). PENDENTE.

### Executor = ThreadPool (correcao de hipotese)
`SQLServerExecutor` usa `ThreadPoolExecutor` + `run_in_executor` (monitoring.py:182,198) — queries
NAO bloqueiam o event-loop. Cascata de 504 e' por saturacao threadpool/connection-pool + teto 300s,
NAO event-loop bloqueado. 504 em servidor de ID normal (SQLIDSPRD03) = saturacao ou SQL lento,
nao o bug de parsing (esse ID com 1 underscore parseava correto).

---

## 10. Performance arranque KPIs (investigacao 3-specialist 2026-06-09)

Causa-raiz em 4 camadas: (1) cache RAM TTL 60s SEM re-warm + preload PARTIDO
(`preload_kpi_cache` chama `get_kpi_dashboard()` sem `request` obrigatorio -> TypeError ->
cache nunca pre-aquecido); (2) `collect_jobs_status` dentro da Phase 1 com fan-out 30s (x2)
bloqueia o dashboard; (3) discovery satura threadpool partilhado no arranque; (4) frontend
sem timeout (spinner infinito) + probe extra.

### Aplicado 2026-06-09 (#2+#4, handshake)
- **#2** `watcherdb_main.py` _background_prewarm: `await _aio.sleep(300)` antes do discovery +
  `discover_all(max_concurrent=5)` (era 10). Mata saturacao pos-restart.
- **#4** `watcherdb_portal.html`: removido probe-fetch extra em detectKpiEndpoint; `AbortSignal.
  timeout(20000)` nos 2 sites de fetch do dashboard. Fim do spinner infinito.
- REQUER RESTART.

### Pendente revisao do owner (#1+#3+F5 refactor)
- Extrair `_collect_and_cache_dashboard()` (sem request/limiter) chamavel por handler/preload/re-warm.
- Corrige preload partido; jobs movido p/ Phase 3 com timeout 10s; re-warm loop a cada 50s (< TTL 60s).
- PONTO ABERTO: `format_dashboard_response` (helpers.py ~2278) faz 2a query de jobs (timeout 30s)
  quando collision_count==0 — precisa de guarda tambem antes de aplicar.

### Achado seguranca (HIGH, separado)
- `services/web_service/config.yaml:56-61` tem passwords default em texto-claro em comentario
  (admin123/viewer123). Remover + forcar troca no 1o login.

### Outros findings (pendentes)
- `_require_admin` ausente em endpoints security + dashboard KPIs.
- IntelligenceConnectionPool max_connections=10 vs executores 20-30, `get_connection()` sem timeout.
- `/health/ready` e stub (nao valida cache quente).
- max_connections=30 no monitoring ignorado (pool real=20).

---

### Security coverage (Fix B aplicado 2026-06-09)
- Sintoma: aba Security mostrava poucos checks (7) — categorias inteiras (Configuracoes SQL) +
  sub-checks (auth-001 modo auth, encrypt-001 TDE) desapareciam em SILENCIO quando a query
  devolvia success=False/vazio (sem else, sem log).
- Fix B: `_make_unknown_check` + loop de agregacao surfaca categorias que falham/vazias como
  UNKNOWN com a razao (revela se e permissao vs query). REQUER RESTART.
- Follow-up: sub-checks parciais (auth-001/encrypt-001 em funcoes que sobrevivem) precisam de
  `else` por funcao — adiar ate o UNKNOWN dizer a causa (permissao -> GRANT; bug -> fix query).
- Dados sensiveis: a resposta de security tem nomes reais de contas/AD/sa/DB — NAO reproduzir.

---

_Ultima atualizacao: 2026-06-09 (#2+#4 perf + Fix B security aplicados; #1+#3+F5 refactor aguarda revisao; requer restart; V6 pendente)._
