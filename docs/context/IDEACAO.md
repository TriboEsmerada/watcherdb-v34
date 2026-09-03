# IDEACAO.md — Ciclos de ideação do WatcherDB

> Cada ciclo: Rodada 1 (propostas) → Rodada 2 (críticas) →
> Rodada 3 (pre-mortem) → Síntese. Nada aqui é decisão; decisão é humana.

---

## 2026-06-12 — Consumo dos baselines S+1 (Wave V) no portal V3.3 Standard

> Status: ciclo em curso. R1 propostas → R2 críticas → R3 pre-mortem → síntese.

### Rodada 1 — propostas (architecture-advisor)

Estado verificado no repo: `WDB_KPI_BASELINE` shipped (PK Kpi_Type+Instance+
Sub_Dimension; Metric_Mean/Std, Sample_Count, Confidence_Pct, Last_Computed;
GRANT sql_monitoring) + `usp_compute_kpi_baseline` (CPU + Memory_PLE apenas)
+ Task Scheduler 03h00. AlwaysOn EXCLUÍDO até Phase 1c. Portal não consome nada.

**I1 — Baseline Read API (fundação)** — subsistema: API/backend
- Premissa: nenhum endpoint V3.3 lê `WDB_KPI_BASELINE`; sem camada de leitura
  única, cada feature de UI vai duplicar SQL e regras de confiança (<70% →
  fall-through camada 4, per Q3 do design Wave V).
- Proposta: endpoint read-only `GET /api/intelligence-kpis/baselines`
  (+ filtro kpi_type/instance) em `intelligence_kpis.py`, query única
  `SELECT ... FROM dbo.WDB_KPI_BASELINE WITH (NOLOCK)`, cache em memória TTL
  alinhado ao dashboard cache; graceful degradation: tabela ausente/erro →
  `{baselines: [], engine_available: false}` (portal funciona como hoje).
- Valor: 1 ponto de verdade para I2–I5; mensurável: 0 queries duplicadas de
  baseline fora deste módulo; latência alvo <50ms (tabela ~centenas de rows, PK seek).
- Custo: S (1 endpoint + cache). Impacto on-prem: 1 query leve/TTL; IO desprezível.
- Assunções: GRANT sql_monitoring já aplicado (confirmado no script Phase 1a);
  Confidence_Pct e Last_Computed são suficientes para o contrato (sem DDL novo → sem veto V1).

**I2 — Banda de normalidade nos trend charts** — subsistema: charts/visualização
- Premissa: os trend charts (ex.: memória via `vw_OS_Memory_Trend_30Min`)
  mostram a curva sem referência — o operador não sabe se 78% é normal PARA
  AQUELA instância; threshold global gera falso conforto/alarme.
- Proposta: overlay vanilla JS (canvas/SVG já usado nos charts) com banda
  `mean ± 2σ` do baseline da instância; banda só desenhada se
  Confidence_Pct ≥ 70; abaixo disso, nota "baseline em maturação" (i18n PT/EN/ES).
- Valor: tempo-até-diagnóstico em drill-down reduzido (alvo: operador
  distingue "alto mas normal" vs "anómalo" sem consultar histórico); mensurável
  em sessões de design-review.
- Custo: M (render + i18n + WCAG contraste da banda). Impacto on-prem: zero
  queries extra (consome I1 cacheado); render client-side.
- Assunções: charts atuais expõem hook de overlay; mean/std do baseline 30d é
  comparável à janela exibida no chart (validar agregação 30min vs samples raw).

**I3 — Chip z-score + badge maturidade nos KPI tiles** — subsistema: dashboard tiles/UX
- Premissa: tiles CPU/Memory mostram valor absoluto vs threshold fixo; um
  servidor batch com CPU 85% "normal" alarma sempre (noise estrutural — viola
  Smart Defaults Principle de SIGNAL acionável).
- Proposta: nos metric-cards CPU/Memory, chip discreto com z-score atual
  (`z = (atual − mean)/std`, computado client-side a partir de I1); estados:
  normal (|z|<2), atenção (2–3), anómalo (>3); badge "baseline maturing" se
  Confidence_Pct < 70 (cumpre decisão Q3 do design). Sem alterar cor/semântica
  dos thresholds atuais — aditivo, nunca substitui (backward compat).
- Valor: mensurável via redução de cliques em instances-modal para instâncias
  cronicamente "vermelhas mas normais"; alvo: −30% drill-downs sem ação.
- Custo: S/M (UI + i18n + tooltip explicativo). Impacto on-prem: zero (dados de I1).
- Assunções: std > 0 (guard divisão por zero); apenas kpi_type cpu/memory_ple
  (AlwaysOn fica fora até Phase 1c — declarar explicitamente na UI? não: omitir).

**I4 — Contexto de baseline no payload de alerta** — subsistema: alerting/events
- Premissa: alertas via `alert_routing.py` saem sem contexto de normalidade
  ("CPU 92%") — o destinatário não consegue triar por email/canal sem abrir o portal.
- Proposta: enriquecer (aditivo, campo opcional) o payload de `/api/alerts/send`
  e o histórico de eventos com linha de contexto quando baseline confiável
  existir: "92% vs baseline 45±8 (z=5.9, 30d)"; sem baseline → payload idêntico
  ao atual (backward compat com canais existentes).
- Valor: triagem remota mais rápida; mensurável: % de alertas com contexto
  (alvo ≥60% após 14 dias de maturação) e feedback de pilot customer.
- Custo: S (lookup no cache I1 no momento do dispatch + template i18n).
  Impacto on-prem: zero query extra por alerta (cache); +~80 bytes por mensagem.
- Assunções: dispatch corre no mesmo processo FastAPI (acesso ao cache);
  formatos de canal toleram campo extra (verificar contrato AlertDispatcher).

**I5 — Baseline Explorer (página admin/diagnóstico)** — subsistema: navegação/admin
- Premissa: o engine corre às 03h00 invisível; admin não tem como verificar
  cobertura, baselines stale (Last_Computed velho) ou confiança baixa —
  confiança no engine é pré-requisito para I2–I4 serem aceites pelo cliente.
- Proposta: secção read-only (tab dinâmica ou bloco em diagnostics/settings)
  listando WDB_KPI_BASELINE completo: instance, kpi, mean±std, samples,
  confidence, last_computed com flag "stale >48h"; filtro client-side +
  export CSV client-side (vanilla JS, sem libs).
- Valor: detecção de falha silenciosa do Task Scheduler (Phase 1d) em <1 dia;
  mensurável: stale baselines visíveis vs hoje (invisíveis); suporte/ops
  ganha ferramenta de health-check do engine.
- Custo: S/M (tabela + sort/filtro reutilizando padrões do portal + i18n).
  Impacto on-prem: 1 query on-demand (NOLOCK, tabela pequena) — só ao abrir a página.
- Assunções: padrão de tabs dinâmicas existente comporta nova tab sem
  refactor; nenhum dado sensível na tabela (só métricas agregadas — OK soberania).

Notas transversais R1: tudo aditivo e reversível (remover UI/endpoint não
quebra nada); zero DDL novo (sem handoff V1 obrigatório, só leitura);
AlwaysOn fora de escopo até Phase 1c; tier Standard confirmado — z-score é
estatística descritiva, não ML (CHANGELOG Wave V já marca [tier: Std]).
Ordem sugerida: I1 é pré-requisito de I2–I4; I5 independente (query própria aceitável).

### Rodada 2 — críticas (sql-deep-reviewer)

Estado verificado no repo antes da crítica: (a) `WDB_KPI_BASELINE` é tabela
plana, NÃO `_STG` → **fora do ciclo de swap BLUE/GREEN** (`usp_swap_kpi_stg_tables`
só toca `KPI_MSSQL_*_STG`); leituras do portal não interagem com o swap — risco
de contenção limita-se ao MERGE das 03h00 (applock, janela de segundos).
(b) `usp_compute_kpi_baseline`: kpi `memory_ple` é na verdade **Available_MB**
(proxy em MB absolutos, anomalia INVERTIDA z<-3; CPU é Processor_Pct, z>+3);
`ISNULL(STDEV,0)` permite Metric_Std=0; mean/std agregam 30d de TODAS as horas
(sem separação dia/noite/dia-da-semana). (c) `vw_OS_Memory_Trend_30Min` devolve
**1 linha agregada por instância** (últimos 30 min, Min/Avg/Max) — não é série
temporal (uso real: modal memory-critical, `intelligence_kpis.py:2022-2064`).
(d) Cache do dashboard: `TTLCache(maxsize=10, ttl=30s)` (`intelligence_kpis.py:39`).
(e) `AlertPayload` (`alert_routing.py:37-44`) é texto livre (title/body), sem
campo estruturado de kpi_type/valor atual. (f) Nenhum código V3.3 lê
`WDB_KPI_BASELINE` hoje (grep: só docs/changelog).

**I1 — Baseline Read API** — veredicto: **AVANÇA COM MUDANÇA**
- Problema 1 (sério): contrato semântico ausente. Dump cru da tabela exporta o
  misnomer `memory_ple` (que é Available_MB em MB) sem unidade nem direção da
  anomalia (CPU: alto=mau; memória: BAIXO=mau). Sem campos `unit` + `direction`
  no response, I2–I4 reimplementam a interpretação cada um à sua maneira — e
  pelo menos um vai errar a direção invertida da memória. Mudança exigida:
  endpoint enriquece cada row com `unit`/`direction`/`display_label` (mapa
  estático server-side, sem DDL).
- Problema 2 (contornável): TTL 30s "alinhado ao dashboard" para dados que
  mudam 1×/dia às 03h00 = ~2.880 queries/dia sem razão. IO desprezível, mas o
  alinhamento certo é TTL longo (≥1h) — baseline não é dado quente.
- Problema 3 (contornável): GRANT do script Phase 1a é condicional à existência
  do principal `sql_monitoring` no momento da instalação — ordem errada de
  install = grant silenciosamente omitido. O `engine_available:false` proposto
  mascara isto para sempre; o endpoint deve distinguir "tabela ausente" de
  "permission denied" no log (mesmo que o portal degrade igual).
- Problema 4 (contornável): NOLOCK durante o MERGE das 03h00 pode devolver mix
  de baselines novos/velhos entre KPIs (janela de segundos; aceitável, documentar).

**I2 — Banda de normalidade nos trend charts** — veredicto: **MORRE**
- Problema 1 (bloqueante): premissa factual errada. `vw_OS_Memory_Trend_30Min`
  não produz curva — é agregado único por instância. Os únicos time-series
  renderizados no portal são sparklines SVG de disco (portal ~linha 9186/9297),
  sem eixos nem escala exposta. Não existe "hook de overlay"; o custo real é
  construir um chart engine com eixos primeiro — isso não é custo M, é projeto.
- Problema 2 (bloqueante para memória): mismatch de unidades — baseline de
  memória em Available_MB absoluto vs portal exibindo Percent_Used; banda em MB
  não se desenha sobre %, exigiria Total_Physical_MB por instância na conversão.
- Problema 3 (sério): mean±2σ de 30d todas-as-horas sobre carga com ciclo
  dia/noite é distribuição bimodal com std inflado — a banda pode cobrir quase
  todo o range visível, virando decoração que transmite falsa confiança
  (produto banking: pior que ausência de banda).
- Condição de reentrada: existir série temporal real com eixos no portal + I1
  shipped com contrato de unidade/direção.

**I3 — Chip z-score + badge maturidade nos KPI tiles** — veredicto: **AVANÇA COM MUDANÇA**
- Problema 1 (sério): guard ÷0 não chega. `ISNULL(STDEV,0)` produz std=0 em VMs
  idle (z=∞), e std minúsculo (ex.: 0.3pp num servidor flat) faz desvio trivial
  de 1pp virar "anómalo z>3" — o chip torna-se gerador de noise, violando o
  próprio Smart Defaults Principle que invoca. Mudança exigida: floor de std
  efetivo por kpi (ex.: `std_eff = MAX(std, piso_absoluto_por_kpi)`) definido
  no I1/server-side, não em cada consumidor.
- Problema 2 (sério): direção e unidade. Para memória o z relevante é sobre
  Available_MB (atual disponível via `vw_OS_Memory_Current` já no payload) com
  anomalia em z NEGATIVO; o tile mostra Percent_Used. Computar client-side
  "(valor do tile − mean)/std" está simplesmente errado para memória. Depende
  do contrato I1 (`direction`/`unit`) e de usar o valor certo — declarar
  explicitamente; fallback aceitável: ship CPU primeiro, memória depois.
- Problema 3 (contornável): sazonalidade — z contra média 30d todas-as-horas
  marca pico de horário comercial como "atenção" em servidores com ciclo forte.
  Mitigação: chip só em |z|>3 com Confidence_Pct≥70 + tooltip explicando janela
  30d; estados 2–3 ficam discretos (sem cor de alarme).

**I4 — Contexto de baseline no payload de alerta** — veredicto: **MORRE (nesta forma)**
- Problema 1 (bloqueante como proposto): camada errada. `AlertPayload` é texto
  livre sem kpi_type/valor estruturado — o dispatcher não sabe que "CPU 92%" é
  (cpu, 92). Enriquecer no dispatch exige parsing de texto (frágil) ou mudança
  do contrato AlertPayload em todos os produtores (deixa de ser "aditivo, custo
  S"). O ponto correto é a ORIGEM do alerta (gerador KPI), não o dispatcher.
- Problema 2 (sério, risco de produto): contradição de motores. Alerta de
  threshold fixo com contexto "z=0.4 — normal para esta instância" ensina o
  destinatário a ignorar alertas, minando a confiança nos DOIS motores antes
  do baseline maturar (≥14d). Num pilot banking isto queima credibilidade.
- Problema 3 (contornável): métrica "≥60% alertas com contexto" mede cobertura,
  não utilidade de triagem.
- Condição de reentrada: pós-I3 validado em produção, implementado na origem
  do alerta com regra explícita de concordância/supressão (não no dispatcher).

**I5 — Baseline Explorer (admin/diagnóstico)** — veredicto: **AVANÇA COM MUDANÇA**
- Problema 1 (sério): staleness com timezone errado. `Last_Computed` é
  GETDATE() local do SQL Server; flag "stale >48h" calculada no browser contra
  clock/TZ do cliente gera falsos stale (ou falsos frescos) em deployments
  multi-TZ. Mudança exigida: staleness computado NA QUERY
  (`DATEDIFF(HOUR, Last_Computed, GETDATE())` no mesmo servidor), browser só exibe.
- Problema 2 (contornável): misnomer exposto a admin — listar `memory_ple` com
  mean em MB confunde; rotular via `display_label` do contrato I1 ("Memória —
  Available MB").
- Problema 3 (contornável): scope — começar como bloco na página diagnostics
  existente, não tab nova (menos i18n de navegação, menos superfície); promover
  a tab só se o bloco provar uso.
- A favor (verificado): única ideia que detecta falha silenciosa do Task
  Scheduler Phase 1d; query on-demand sobre tabela pequena, fora do swap —
  custo on-prem efetivamente zero.

**Sobreviventes R2 (3/5):**
1. **I1** — avança com mudança: contrato semântico `unit`/`direction`/
   `display_label` + std-floor server-side + TTL ≥1h + log distinguindo
   tabela-ausente vs permission-denied. Pré-requisito de I3/I5.
2. **I3** — avança com mudança: std floor via I1, direção invertida memória
   tratada (ou CPU-first), chip discreto só |z|>3 com Confidence_Pct≥70.
3. **I5** — avança com mudança: staleness server-side (DATEDIFF no SQL),
   bloco em diagnostics em vez de tab nova.

**Mortas:** I2 (premissa de chart inexistente + mismatch MB vs % + banda
estatisticamente enganosa) e I4 (camada errada no dispatcher + contradição
threshold vs baseline mina confiança em pilot). Ambas com condição de
reentrada declarada acima.

### Rodada 3 — pre-mortem (incident-forensics)

Premissa do exercício: "2027, isto causou incidente grave em produção
bancária — o que aconteceu?" Evidência verificada antes dos cenários:
`usp_compute_kpi_baseline` usa `sp_getapplock @LockOwner='Session',
@LockTimeout=0` com `RETURN` silencioso se lock ocupado; janela 30d
todas-as-horas; `ISNULL(STDEV,0)`; tabela guarda `Last_Computed` (quando
calculou) E `Window_End` (até quando há dados) como colunas distintas;
Phase 1d (`run_baseline_compute_PRD.ps1`) loga exit code mas não alerta em
falha; cache do portal é `TTLCache` in-memory.

**I1 — Baseline Read API**

- **F1.1 — Applock zombie: engine morto a servir baselines stale como
  verdade.** Uma sessão SSMS/script ad-hoc fica pendurada segurando o
  applock (`LockOwner='Session'` só liberta no fim da sessão). Todas as
  execuções diárias seguintes fazem `RETURN` silencioso — exit code 0 no
  log Phase 1d, "sucesso" todos os dias. Semanas depois, durante upgrade de
  RAM da frota, o baseline de memória continua pré-upgrade; a API serve
  esses números como referência atual e a triagem de um incidente real
  compara contra um mundo que já não existe.
  *Sinal precoce:* `MAX(DATEDIFF(HOUR, Last_Computed, GETDATE())) > 26` —
  SLA do engine é 24h+margem. *Mitigação:* API calcula `age_hours` por row
  server-side e devolve `engine_status` global (fresh/stale/dead); WARNING
  estruturado no log V3.3 quando stale; recomendar ao V1 mudar applock para
  `LockOwner='Transaction'` ou logar o `@lock_result<0` como ERRO no log do
  scheduler (hoje é `@Debug` only). Candidato a novo detector/KPI:
  "baseline engine silence".
- **F1.2 — Grant omitido mascarado para sempre.** Reinstalação/migração da
  Intelligence DB recria a tabela antes do principal `sql_monitoring`
  existir → GRANT condicional do script Phase 1a é silenciosamente saltado.
  O endpoint apanha a exceção e devolve `engine_available:false`; chips e
  Explorer simplesmente desaparecem do portal. Operadores que tinham
  aprendido a usar o chip como contexto perdem o instrumento sem aviso;
  meses depois ninguém sabe que a feature "existia".
  *Sinal precoce:* classificação distinta no log — erro pyodbc de permissão
  (ex. 229) ≠ objeto inexistente — com contador. *Mitigação:* self-check no
  startup do serviço com mapeamento explícito do error code, estado exposto
  na página diagnostics ("Baseline API: PERMISSION DENIED — rever GRANT"),
  nunca só log.
- **F1.3 — Contrato fail-open com kpi_type novo.** Phase 1c entra (ou outro
  kpi futuro) e a sproc passa a popular um kpi_type que o mapa estático
  `unit`/`direction` do endpoint não conhece. Endpoint devolve a row com
  default implícito "higher=worse"/sem unidade; consumidores (I3) computam
  direção errada — repetição exata do bug de direção invertida da memória
  que a R2 identificou, agora institucionalizado pela API.
  *Sinal precoce:* nenhum em runtime se fail-open — por isso o gate é
  fail-closed. *Mitigação:* kpi_type sem entrada no mapa é EXCLUÍDO do
  response + ERROR log ("kpi_type desconhecido omitido do contrato");
  pytest de contrato que falha se a tabela tiver kpi_type fora do mapa.

**I3 — Chip z-score nos tiles**

- **F3.1 — Baseline envenenado normaliza o incidente (o mais perigoso do
  ciclo).** Um job batch mal configurado segura CPU ~90% durante 3 semanas;
  ninguém corrige ("é batch, é normal"). A janela 30d absorve o período e o
  baseline vira 82±9. Quando um incidente real (convoy de locks) leva a CPU
  a 97%, o tile fica vermelho pelo threshold MAS o chip diz z≈1.6 "dentro
  do padrão". Operadores treinados durante semanas que "vermelho + chip
  normal = noise estrutural" despriorizam; outage estende-se horas. Num
  banco, o post-incident review encontra o chip verde no screenshot.
  *Sinal precoce:* drift do baseline no recompute — `|mean_novo −
  mean_anterior| / mean_anterior > 20%` em 24h é anómalo por si.
  *Mitigação:* (a) regra de UI inviolável: chip NUNCA aparece em tile já em
  alarme de threshold — vermelho é primário, chip só adiciona contexto em
  tiles não-alarmados; (b) gate server-side: suprimir chip se o próprio
  `Metric_Mean` exceder o threshold fixo do kpi ("baseline em zona crítica
  — referência não confiável"); (c) copy nunca diz "normal" — diz "dentro
  do padrão dos últimos 30 dias" (ancora a referência e os seus limites);
  (d) detector novo: "baseline shift >20%" como evento WatcherDB.
- **F3.2 — Divergência i18n/locale em números estatísticos.** z-score e
  mean±std renderizados client-side; PT/ES usam vírgula decimal. Um export
  /screenshot com "1.024 MB" lido como ~1 MB por equipa ES (ou "z=3,1"
  colado num runbook EN como 31) durante uma bridge de incidente →
  decisão de capacidade errada. WCAG/i18n já é requisito do portal mas
  números estatísticos têm risco de magnitude, não só tradução.
  *Sinal precoce:* não detetável em runtime — o gate é pré-ship.
  *Mitigação:* `Intl.NumberFormat` com o locale ativo do i18n (não o do
  browser), unidade sempre explícita no chip/tooltip, browser-test PT/EN/ES
  dos três formatos antes de declarar shipped (precedente: incidente
  2026-06-01 dos handlers inline).
- **F3.3 — std-floor mal calibrado vira supressor universal.** O piso de
  std (mudança exigida pela R2) é definido alto demais para matar noise de
  VMs idle (ex. floor 10pp em CPU). Num servidor de produção estável (std
  real 1.5pp), um salto de +30pp dá z=3.0 com o floor — abaixo do gate
  |z|>3 — e o chip silencia uma anomalia real que o threshold fixo (75%)
  ainda não apanhou. O early-warning que o cliente comprou não dispara.
  *Sinal precoce:* % de instâncias onde `std_eff != std` (floor aplicado);
  >50% = calibração errada do piso. *Mitigação:* floor conservador
  documentado por kpi no I1; Explorer (I5) expõe coluna `std` vs `std_eff`
  para auditoria; copy do tooltip: "contexto estatístico — não substitui
  os alarmes de threshold".

**I5 — Baseline Explorer (bloco em diagnostics)**

- **F5.1 — Explorer verde com pipeline morto (falso health-check).** O
  collector V1 morre em silêncio (precedente real: gap driver/porta
  dinâmica, FIND-20260507-001). As HIST param de crescer, mas a sproc
  continua a recomputar diariamente sobre a cauda da janela 30d que ainda
  tem amostras: `Last_Computed` fresco, Confidence 100, flag "stale >48h"
  nunca dispara. Durante um incidente, o admin abre o Explorer como
  health-check, vê tudo verde e conclui que a telemetria está saudável —
  quando TODO o portal está a servir dados congelados. O instrumento de
  confiança valida exatamente a falha que devia expor.
  *Sinal precoce:* idade de `Window_End` (frescura dos DADOS) divergente da
  idade de `Last_Computed` (frescura do CÁLCULO): `DATEDIFF(HOUR,
  Window_End, GETDATE()) > 24` com `Last_Computed` fresco = "engine a
  computar sobre dados mortos". *Mitigação:* Explorer mostra as DUAS idades
  server-side (a tabela já tem `Window_End` — custo zero), flag vermelha
  quando divergem >24h, copy explícito "cálculo recente ≠ dados recentes";
  candidato a detector: staleness de coleta já é doutrina V3.3 (silêncio É
  sinal) — aplicá-la ao engine.
- **F5.2 — Explorer durante degradação da própria Intelligence DB.** A BD
  Intelligence está IO-saturada (a causa do incidente). O admin abre o
  Explorer; a query on-demand (sem cache) pendura até ao timeout, prendendo
  uma conexão do pool partilhado e atrasando o dashboard principal — a
  ferramenta de diagnóstico agrava o incidente. Variante 03h0x: NOLOCK
  durante o MERGE devolve metade dos kpi atualizados e metade velhos; o
  admin conclui "o engine partiu a meio" e executa `@Force_Full` manual em
  produção no pico, multiplicando o IO.
  *Sinal precoce:* elapsed da query do Explorer logado (>2s = WARN) +
  contagem de timeouts. *Mitigação:* timeout curto dedicado (~5s) com
  mensagem honesta "BD Intelligence não respondeu — durante degradação da
  própria BD, o Explorer não é evidência fiável"; nota fixa na UI sobre a
  janela de recompute das 03h00 (mix transitório esperado); `TOP` defensivo
  na query.
- **F5.3 — CSV export como evidência de auditoria errada.** Em banking o
  CSV do Explorer acaba anexado a um post-incident review regulatório. O
  export client-side serializa o estado do browser: números formatados por
  locale (vírgulas) e flags de staleness calculadas no snapshot de uma
  página aberta há horas (sem auto-refresh) — evidência incorreta em
  documento auditável.
  *Sinal precoce:* n/a em runtime — gate de design. *Mitigação:* CSV embute
  linha de cabeçalho "snapshot servidor: <timestamp SQL ISO 8601>" vindo da
  própria query; valores raw invariantes no export (ponto decimal, ISO
  dates) independentemente do locale de exibição; export força re-fetch
  antes de serializar.

**Síntese R3 (transversal):** os três sobreviventes mantêm-se viáveis, mas
o pre-mortem converge em 4 guards obrigatórios de implementação:
(1) duas idades server-side (`Last_Computed` E `Window_End`) em I1+I5 —
deteta tanto engine morto como engine-a-computar-sobre-dados-mortos;
(2) chip I3 nunca coexiste com tile em alarme de threshold + supressão se
o próprio baseline estiver em zona crítica (anti-envenenamento);
(3) contrato I1 fail-closed para kpi_type desconhecido + log distinto
permission-denied vs tabela-ausente;
(4) números estatísticos com formatação locale-aware na UI mas invariantes
em exports. Oportunidade de detectores novos: "baseline engine silence"
(Last_Computed >26h), "baseline computing on dead data" (Window_End >24h
com Last_Computed fresco) e "baseline shift >20% em 24h".

### Síntese (orquestrador) — 2026-06-12

**Ranking:**
1. **I1 — Baseline Read API** (vencedora): pré-requisito de tudo; risco
   técnico baixo depois das mudanças da R2 (contrato unit/direction/label,
   std-floor server-side, TTL ≥1h, log permission-denied vs tabela-ausente)
   e dos guards da R3 (duas idades: Last_Computed + Window_End, engine_status).
2. **I5 — Baseline Explorer**: primeira superfície visível; constrói a
   confiança no engine que I3 pressupõe; staleness server-side; quase todo
   o valor de observabilidade do pre-mortem (engine silence / dead data)
   materializa-se aqui.
3. **I3 — Chip z-score nos tiles**: maior valor para o operador, mas maior
   risco de produto (baseline envenenado a suprimir alarme real). Só após
   ≥30 dias de baselines maduros em DEV + guards anti-envenenamento da R3.

**Trade-off central:** valor visível (I3) vs confiança no engine (I1+I5).
Lançar I3 primeiro seria pedir ao operador que confie numa estatística que
ninguém consegue auditar — ordem forçada: I1 → I5 → I3.

**Plano de validação barato (prova ou mata a premissa, sem escrever código
de produto):**
1. SELECT read-only (sql_monitoring, DEV) na WDB_KPI_BASELINE: cobertura
   (instâncias com baseline / instâncias monitorizadas), distribuição de
   Confidence_Pct, contagem de Metric_Std=0, idades Last_Computed vs
   Window_End. Mata I1/I5 se a cobertura ou confiança forem inúteis.
2. Simulação offline de I3: z-scores dos valores atuais contra os baselines
   existentes → quantos tiles mudariam de estado e quantos seriam
   contradições (threshold vermelho + z normal). Mede signal vs noise
   ANTES de qualquer UI. Mata ou calibra I3.

**Decisão:** humana — aguarda GO do owner para a experiência 1 (queries de
validação em bloco para execução manual).
