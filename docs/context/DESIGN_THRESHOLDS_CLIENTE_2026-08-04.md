# DESIGN — Thresholds de KPI configuráveis pelo cliente

Data: 2026-08-04 · Owner + Claude (OODA + painel de 3 specialists)
Checkpoint de rollback: tag git `checkpoint-pre-thresholds-20260804` (= `226ace5`)
Estado: **FASE 0 IMPLEMENTADA (2026-08-04, mesma sessão).** Owner decidiu
"seguir a recomendação": (1) F1 fica GATED a pedido escrito de cliente;
(2) schema scope-ready com código Std global-only quando F1 abrir;
(3) tier da F3 escala como item próprio. Fase 0 entregue: registry
central (`api/kpi_thresholds_registry.py`, 14 KPIs), backend refactorizado
(helpers + intelligence_kpis, incl. WHERE da latência), endpoint
GET `/api/intelligence-kpis/thresholds`, ecrã read-only "Thresholds em
vigor" nas Configurações, manual corrigido (FIND-20260804-101 fixed),
testes 4/4 (golden de valores + anti-regressão de literais). Pendente:
0.4 verificação GRANT MUTE (rede — FIND-20260804-102).

---

## 1. Pergunta original e OODA

Owner: "cada cliente pode querer definir o seu threshold, ou programar
exceções para instâncias/databases — vale a pena em V3.3, só V6, ou ambas?"

OODA inicial (orquestrador): valia a pena, faseado — F1 global em V3.3 Std,
F2 exceções por âmbito em Pro/V6, F3 baseline engine a sugerir. **O painel
alterou esta conclusão** (secção 3): há um passo 0 obrigatório antes de
qualquer tabela, e F1 ganhou um gate de entrada.

## 2. Pareceres do painel (2026-08-04)

### 2.1 `challenger` — veredicto: **Opção E primeiro; F1 só com pedido escrito**
- Thresholds vivem em **5 camadas** (colector V1 persiste Severity na row;
  16 ficheiros SQL com CASE; backend Python; **WHERE clauses de fetch**;
  frontend com cores E textos de ajuda hardcoded). Override só no backend
  produz superfícies inconsistentes — e no caso do WHERE (helpers.py:2299),
  baixar um threshold **não mostra nada, silenciosamente**.
- `SMART_DEFAULTS_PRINCIPLE.md` (25/05) foi escrito **a antecipar o cliente
  banking** ("support nightmare", "audit trail"), não apesar dele.
- **Não existe pedido escrito de cliente.** O que existe é pior: o
  `MANUAL_SIMPLIFICADO_PT.md:106-117` promete um ecrã de thresholds **que
  não existe** e lista defaults **errados** (CPU 70/85 vs código 80/60;
  backup FULL 24/48h vs código 120/168h) — defeito real hoje.
- Fasquia para F1: teste de paridade de superfícies por KPI + golden test
  "tabela vazia ⇒ respostas byte-idênticas a hoje" + <5ms p95.
- Ordem: **E (centralizar registry + ecrã read-only + corrigir manual) >
  A (nada) > B/F1 (gated) > C/F2 > D/baseline**.

### 2.2 `watcherdb-v1-intel-specialist` — veredicto: **GO-com-condições** (tabela)
1. Nome de coluna `Kpi_Type` (não `Kpi_Key`) — alinhar com
   `WDB_KPI_MUTE`/`WDB_KPI_BASELINE`.
2. Escrita por `sql_monitoring`: aceitável como excepção Rule #8 **escrita e
   datada** (precedentes: Token_Blacklist, tribunal, MUTE), verbos mínimos,
   risco de login partilhada nomeado explicitamente.
3. **[HIGH — bloqueia o padrão de escrita]** o canonical só tem
   `GRANT SELECT` na `WDB_KPI_MUTE` (linha ~2011) mas `kpi_mute.py:139-181`
   faz MERGE/DELETE — drift (grant fora-de-banda) ou partido em fresh
   install. Resolver ANTES de replicar o padrão. → verificação: secção 5.1.
4. Scope `DATABASE` (F2) precisa de convenção composta `Instance\Database`
   no `Scope_Value` — documentar no DDL desde o dia 1.
5. Rollback limpo exige try/except REAL na leitura e na escrita (não só
   empty-check); cache TTL pode servir override até 60s pós-DROP (autocura).
6. Canonical: secção nova após bloco `WDB_KPI_BASELINE` (~linha 2070).

### 2.3 `v33-feature-matrix-checker` — veredicto: **PASS com ajustes**
- F1 global = table-stakes Std (precedentes: `config/alerts.json` já tem
  thresholds globais em ficheiro; `WDB_KPI_MUTE` é Std com granularidade
  instance-level). F2 scoped = Pro correcto.
- **Guardrail de schema**: a tabela Std não pode ter colunas de scope
  latentes (capacidade Pro em build Std = tier creep). Propõe tabela flat
  Std + tabela separada Pro.
- F3 (baseline como Pro) é mudança face ao roadmap original (S+1 era Std) —
  **NEEDS_DECISION do DBA Lead**, não assumir.
- Propõe texto para a FEATURE_MATRIX (secções 3 e 5) — no parecer completo.

## 3. Conflito entre pareceres e reconciliação proposta

**Schema flat (tier-checker) vs scope-ready (challenger + V1):**
- Tier-checker: colunas de scope na tabela = capacidade Pro latente em Std.
- Challenger/V1: schema sem scope obriga a ALTER coordenado V3.3+V6 na BD
  partilhada quando F2 chegar.
- **Reconciliação recomendada:** o schema pertence à BD partilhada (dono:
  V1 specialist), não ao build Std — nasce scope-ready
  (`Scope_Type DEFAULT 'GLOBAL'`), MAS o código e a UI V3.3 Std só conhecem
  GLOBAL (query com `WHERE Scope_Type = 'GLOBAL'` fixo, sem dropdown, sem
  estado Pro visível). Tier enforcement no código/UI, não no DDL partilhado;
  justificação escrita no próprio DDL. Validar com o checker no diff real.
  → Decisão final: owner (secção 6.2).

## 4. O PLANO COMPLETO (faseado; cada fase com gate e rollback)

### FASE 0 — "Uma só verdade" (recomendada JÁ; sem gate; sem DDL)
O problema real e presente é o drift entre camadas — e centralizar é
pré-requisito técnico de qualquer configurabilidade.
- **0.1 Registry central de thresholds**: módulo único
  (`api/kpi_thresholds_registry.py`) com TODOS os thresholds hoje
  hardcoded no backend (tempdb 60/80, latência 20/50, locks 60/600, CPU 95,
  backup FULL/DIFF/LOG, integrity 30d, …). Backend importa do registry;
  frontend recebe os valores via endpoint bootstrap (cores e textos de
  ajuda deixam de citar números hardcoded onde viável). Views SQL e
  colector V1 NÃO mudam — o registry documenta esses como "fonte:
  view/colector" com valor espelhado + teste anti-drift que alerta se o
  espelho divergir da definição real.
- **0.2 Ecrã read-only "Thresholds em vigor"** no portal (admin) — honra a
  promessa do manual sem DDL; vira argumento de demo.
- **0.3 Corrigir `MANUAL_SIMPLIFICADO_PT.md`** (defaults reais).
- **0.4 Fix do GRANT da `WDB_KPI_MUTE`** conforme 5.1 (bloco DDL para o
  owner + canonical no mesmo commit).
- Esforço: 1–2 sessões. Done = teste "registry ⇔ superfícies backend
  coerentes" verde + manual sem números errados.

### FASE 1 — Overrides globais por KPI (GATED)
- **Gate de entrada:** pedido escrito de cliente (RFP/email) OU decisão
  comercial explícita do owner registada neste doc (secção 6.1).
- Tabela `WDB_KPI_THRESHOLDS` (colunas `Kpi_Type`, `Scope_Type` conforme
  6.2, `Warning_Value`, `Critical_Value`, `Updated_By`, `Updated_At`) +
  GRANT com excepção Rule #8 datada; canonical ~linha 2070; router novo
  `kpi_thresholds.py` decalcado do `kpi_mute.py` (com GRANT correcto desta
  vez); modal admin CRUD global-only com estado visível "default do
  produto" vs "override do cliente".
- Só KPIs cujo threshold vive no registry (Fase 0) entram na lista
  configurável — lista fechada, nada "meio-configurável".
- Golden test: tabela vazia ⇒ byte-idêntico a hoje. Teste de paridade de
  superfícies por KPI configurável (incl. WHERE refactorizado da latência).
- Esforço: 2–3 sessões sobre a Fase 0.

### FASE 2 — Exceções por âmbito (Pro/V6; GATED por pedido escrito de scoping)
- ENV → INSTANCE → DATABASE com precedência em código; `Scope_Value`
  composto `Instance\Database`; audit trail com HISTÓRICO (quem, de quê,
  para quê, quando) — requisito banking que F1 não cobre.
- UI apenas Pro/V6. FEATURE_MATRIX actualizada ANTES do código.

### FASE 3 — Baseline engine sugere thresholds (Wave V, já desenhado)
- Tier: **NEEDS_DECISION** (6.3). Bloqueado também por
  `collect_alwayson_status.py:52` (Commit_Diff_Secs=0 hardcoded).

## 5. GARANTIA DE ROLLBACK (pedido explícito do owner)

**Princípio: cada fase reverte para o estado de
`checkpoint-pre-thresholds-20260804` sem resíduos.**

| Camada | Mecanismo | Prova |
|---|---|---|
| Código (V3.3+V1) | `git revert` até à tag; mudanças desta wave em commits próprios, nunca misturados com outras | tag criada 2026-08-04 em `226ace5` |
| BD — Fase 0 | **zero DDL** (única excepção: fix de GRANT da MUTE, reversível com `REVOKE` — bloco de rollback incluído no bloco de aplicação) | n/a |
| BD — Fase 1 | DDL **aditivo-apenas** (CREATE TABLE novo; nenhum ALTER a objectos existentes). Rollback = `DROP TABLE dbo.WDB_KPI_THRESHOLDS` + revert de código. Resíduo: cache TTL ≤60s (autocura); overrides do cliente perdem-se no DROP — por design, comunicado antes | golden test "tabela vazia = hoje" prova que o caminho default nunca deixa de existir |
| Comportamento | Leitura E escrita com try/except real: tabela ausente ⇒ defaults, sem erro ao utilizador (condição 5 do V1) | teste automático corre com a tabela dropada |
| Canonical/docs | Mudança de canonical no MESMO commit do DDL; revert do commit reverte ambos | convenção 5-surfaces |

### 5.1 Verificação do GRANT da WDB_KPI_MUTE — RESOLVIDA (04/08 tarde)

**Resultado:** a escrita funciona porque `sql_monitoring` é membro de
**db_owner + db_datareader + db_datawriter** (verificado em
`sys.database_role_members` e `fn_my_permissions`). Não é um grant
fora-de-banda pontual — é um modelo de permissões que torna os GRANTs
granulares do canonical irrelevantes e viola a Regra de Ouro #2.
Registado como **FIND-20260804-104 (P1 security)** com proposta de wave
de separação de identidades; o FIND-20260804-102 fica absorvido.
**Implicação para a Fase 1:** a tabela de thresholds não deve nascer
assumindo este modelo sem o nomear; idealmente a wave de identidades
corre antes ou em paralelo. Query original mantida abaixo para histórico:
A 04/08 de manhã a ligação à Intelligence começou a falhar com
`08001 delay in opening server connection` (hiccup VPN/DNS conhecido) —
a verificação fica pronta a correr no regresso da rede (ou em SSMS):

```sql
-- Read-only. Esperado se drift: permissoes INSERT/UPDATE/DELETE presentes
-- na BD viva mas ausentes do canonical (so GRANT SELECT na linha ~2011).
SELECT pr.name, pe.permission_name, pe.state_desc
FROM sys.database_permissions pe
JOIN sys.database_principals pr ON pr.principal_id = pe.grantee_principal_id
WHERE pe.major_id = OBJECT_ID('dbo.WDB_KPI_MUTE');
SELECT r.name AS role_name FROM sys.database_role_members m
JOIN sys.database_principals r ON r.principal_id = m.role_principal_id
JOIN sys.database_principals u ON u.principal_id = m.member_principal_id
WHERE u.name = 'sql_monitoring';
```
Interpretação: se aparecer INSERT/UPDATE/DELETE (ou role db_datawriter) →
drift a corrigir no canonical; se NÃO aparecer → a mute está partida em
fresh install E provavelmente também na BD viva (testar um mute no portal).

## 5-bis. ESTADO (fecho 04/08)

- **F0 (registry/ecrã/manual): FEITA** — commits 3cb0cb0/66d28c0/571c19d.
- **F1 (overrides globais editáveis): FEITA e VALIDADA pelo owner no
  browser** — commits 3cb0cb0/faf3ab4; DDL aplicado; edição testada OK.
- **F2 (scoped) + F3 (baseline): tier = Pro/V6** (decisão owner 04/08 via
  AskUserQuestion — mantém a recomendação do painel; Std não comoditiza).
  A camada de dados partilhada (schema scope-ready + precedência no
  `resolve()`) já as serve; falta a parte Pro (UI de scope, audit trail,
  sugestão do baseline). Handoff para o V6:
  `PROMPT_PROPAGACAO_V6_THRESHOLDS_2026-08-04.md`.

## 5-bis-b. CORRECÇÃO AO ESTADO DA F1 (descoberto 2026-08-13)

O "DDL aplicado" do fecho de 04/08 **não sobreviveu** na
WatcherDB_Intelligence do SQLHDSTST505\I01: a primeira escrita real
(owner, 13/08) devolveu 42S02 `Invalid object name 'WDB_KPI_THRESHOLDS'`
— o fallback de leitura (por design) escondeu a ausência durante 9 dias.
E a condição 6 do gate v1-intel ("canonical no MESMO commit do DDL")
ficou por cumprir: o canonical nunca recebeu a secção. Fechado a 13/08:
owner recriou as 2 tabelas na BD viva (CREATE_WDB_KPI_THRESHOLDS.sql,
verificação 0/0 rows) e a secção entrou no canonical
INSTALACAO_COMPLETA_UNIFICADA.sql (~linha 2074, após WDB_KPI_BASELINE,
com nota de histórico). O router passou a devolver 503 accionável
quando a tabela falta (o safe_http_error genérico escondia a causa).

## 5-ter. FASE 1.5 — espelhos a migrar para configuráveis (aberta 2026-08-13)

**Gate da §6.1 satisfeito:** decisão comercial explícita do owner
(2026-08-13, por escrito no chat: "poder ajustar os thresholds com a
métrica que eu quiser") — regista-se aqui conforme o próprio doc exige.

**Item 1 (filegroups): FEITO — commit 091557a, testes 7/7.** Painel:
v1-intel GO-com-condições + challenger (pareceres na sessão 13/08).
- Registry: espelho `filegroup_usage` substituído por `filegroup_free_pct`
  (5/2 "% livre", `higher_is_worse=False`, `warning_cap=10`) +
  `filegroup_unlimited_free_gb` (10/5 GB, `higher_is_worse=False`).
  REGISTRY_VERSION `2026-08-13.f15`.
- Router: validação direction-aware (menor=pior inverte a comparação
  w/c) + cap do warning — sem isto o POST dos próprios defaults dava 400.
- **6 queries** migradas para `_th()` (o painel só tinha mapeado 3; o
  teste anti-regressão apanhou a 4ª superfície): helpers.py card CTE +
  disk_query; intelligence_kpis.py detail (2 ramos) + lista de
  instâncias da modal (2 queries). Attention (5-10% livre) FIXO nesta
  fase (schema partilhado sem 3º nível; ALTER = veto V1).
- Condição 4 do v1-intel verificada pelo owner na BD viva (SSMS 13/08):
  DATAFILES_STG registada em KPI_STG_ACTIVE_TABLE e fresca — mas só
  fora-de-banda ⇒ drift do canonical = **FIND-20260813-101** (P1, V1).
- Superfícies do portal com números hardcoded = **FIND-20260813-102**
  (P2, follow-up de paridade — help texts, i18n 3 locales, Space Health).

**Lotes 2+3 (mesma sessão, 13/08): DEADLOCKS + TLOG + PROCESSES +
INTEGRITY FEITOS** — técnica "mover o cálculo para o backend, view
partilhada intacta" (recomendação v1-intel), cada um com a sua variação:
- DEADLOCKS: State/Severity reescritos pós-fetch sobre `Deadlock_Count`;
  sort da modal saiu do SQL (ordenava pela verdade velha da view).
- TLOG: a AGG só expõe contagens já classificadas — o backend agrega
  directamente da `KPI_MSSQL_TLOG_USAGE_ACTIVE` com forma de colunas
  idêntica à view (consumidores intactos). DET_VIEW não é consumida
  pelo Std.
- PROCESSES: WHERE dinâmico sobre `Runnable_Count` (o WHERE por State
  da view esconderia linhas com warning abaixo de 20) + State reescrito;
  comparação estrita `>` preservada.
- INTEGRITY: fronteira P4/P5 recalculada sobre `Days_Since_CheckDB`
  (card em Python, modal em SQL CASE incl. Verdict_Reason e ORDER BY);
  P1/P3/higiene/unmeasurable continuam da view; só o warning (dias) é
  cutoff, critical N/A.

**Estado final:** 13 KPIs configuráveis (7 F1 + 6 F1.5). Ficam
não-configuráveis POR DESIGN: DISK_USAGE (regra por-drive/tiers, não é
par w/c — modelo de regra classe-F2 se um cliente trouxer política
concreta) e MEMORY (Severity persistida na recolha pelo collector V1 —
seria wave de collector com paridade sync/async e histórico misto
assumido). Condição transversal em aberto: V6 migrar o read-path das
4 views no mesmo lote (handoff F15) senão Std e Pro divergem com
override activo.

## 6. DECISÕES PENDENTES DO OWNER

1. **Gate da Fase 1**: esperar pedido escrito do cliente, ou decisão
   comercial tua agora? (Challenger recomenda esperar; custo de esperar ≈ 0
   porque a Fase 0 já entrega o ecrã e mata o drift.)
2. **Schema F1**: flat (tier-checker) vs scope-ready com código Std
   global-only (reconciliação §3 — recomendada).
3. **Tier da Fase 3** (baseline): Std (roadmap original S+1) vs Pro
   (analytics) — item próprio a escalar.

## 7. Findings a registar quando a Fase 0 abrir

- Manual promete ecrã inexistente + defaults errados (P1 docs/ux).
- GRANT drift `WDB_KPI_MUTE` (HIGH — após verificação 5.1).
- Inventário de drift de thresholds por camada (Anexo A).

## Anexo A — Inventário de thresholds (backend verificado a 04/08; views: sweep pendente de rede)

| KPI | Warning / Critical | Camada onde vive | Configurável em F1? |
|---|---|---|---|
| TempDB usage | 60 / 80 % | backend (`helpers.py:1987`, `intelligence_kpis.py`) | SIM |
| Disk latency | 20 / 50 ms | backend query **incl. WHERE** (`helpers.py:2288-2299`) + V1 `os_performance.py:260-273` + frontend cores/help | SIM (com refactor do WHERE) |
| Long locks | 60 / 600 s | backend (`helpers.py:1113-1114`) | SIM |
| CPU crítico | ≥95% (+Severity do colector) | backend WHERE (`helpers.py:2161`) + colector | PARCIAL |
| Memória | Severity='CRITICAL' do colector | colector V1 | NÃO em F1; registry espelha |
| Backup delayed | FULL 120/168h · DIFF 24/30h · LOG 1/2h | backend dict (`helpers.py:1572-1574`) | SIM |
| Integrity P4 | CHECKDB >30d | view (Wave X) | NÃO em F1 |
| Processos | >20 / >50 runnable | **SQL view** `PROCESSES_AGG_VIEW` | NÃO em F1; registry espelha |
| Disco/TLOG/FG Crit-Warn | nas views AGG / colector | SQL views + colector | NÃO em F1; registry espelha |
| Deadlocks State | na view AGG | SQL view | NÃO em F1 |
