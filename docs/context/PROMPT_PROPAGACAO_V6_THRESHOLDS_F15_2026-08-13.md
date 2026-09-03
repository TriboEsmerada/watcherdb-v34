# PROPAGAÇÃO V6 — Fase 1.5 thresholds (filegroups) + fix modal filegroups

Data: 2026-08-13 · Origem: V3.3 commits `b57112a` (modal) + `091557a` (F1.5)
Para: AI do WATCHERDB_V6. Regra da casa: V6 = V3.3 + extras, mas o portal
V6 NÃO é superset — **grep de âncoras PRIMEIRO**, não apliques diffs cegos.

## Lote 1 — Modal "FileGroups Usage" (layout do drilldown)

**Problema que corrigimos:** a lista "Filegroups com problema" (lazy no
card-expand) usava grid `max-content 1fr max-content max-content`. Em modal
maximizada a coluna `1fr` esticava e empurrava %/badge para a borda direita
(~900px de vazio); em modal reduzida as colunas `max-content` esmagavam a
`1fr` para ~2ch e o `word-break:break-word` quebrava o nome letra-a-letra
na vertical.

**Contrato da solução (aplica o MECANISMO, não o copy-paste):**
1. Grid pai `.fg-problem-grid` com `width:max-content; max-width:100%` —
   as colunas abraçam o conteúdo (mata o vazio em ecrã largo).
2. Cada linha embrulhada em `.fg-row` com `display:contents` no modo largo
   (células alinham no grid pai; hover pinta via `.fg-row:hover > div`
   porque display:contents não pinta background próprio).
3. `@container (max-width:640px)`: a row vira grid próprio — db + % +
   badge na linha 1, nome do filegroup em linha própria (`order:5` +
   `grid-column:1/-1`, indent 14px). O host do painel leva
   `container-type:inline-size`.
4. `overflow-wrap:break-word` (NUNCA `word-break`) + `tabular-nums` nos
   percents + tooltip `title` no nome da db truncada (ellipsis 340px).
5. `column-gap: 28px` (owner validou; 12px ficou "colado").
6. Empty-state suprimido (owner 13/08): `_buildCardExpandHtml(inst,
   suppressEmpty)` — nos cards com secção lazy própria (kpiType
   `filegroup-usage*`) o expand NÃO mostra "Sem campos adicionais neste
   registo." por cima da lista útil; nos restantes KPIs mantém-se (aí o
   empty-state é informação honesta). Se aplicares no V6, cuidado com a
   declaração de `kt`: passou para o topo do bloco (redeclarar const no
   mesmo scope é SyntaxError que mata o script inteiro).

**ARMADILHA que o specialist original propôs e está ERRADA:** usar `order`
nas células dentro de um grid ÚNICO de N linhas — o `order` reordena a
auto-colocação globalmente (todas as dbs primeiro, depois todos os %...)
e baralha as linhas. O `order` só é seguro DENTRO do row-grid próprio
(modo estreito). Se o portal V6 tiver o mesmo padrão de grid, verifica
isto antes de aceitar qualquer proposta com `order` global.

**Âncoras V6 a grep:** `Filegroups com problema`, `filegroup-usage`,
`toggleCardExpand`, `grid-template-columns:max-content 1fr`. Se o portal
V6 não tiver este drilldown, o lote 1 NÃO se aplica (não inventar).

## Lote 2 — Fase 1.5: filegroups configuráveis (backend)

**O que muda conceptualmente:** `filegroup_usage` deixa de ser espelho
("camada de recolha") e passa a DOIS KPIs configuráveis globais no
registry — o card filegroups tem dois modelos de problema distintos
(decisão owner 27/07) e cada um ganha o seu par:
- `filegroup_free_pct` — FGs limitados, % livre efectivo, defaults
  warning=5 / critical=2, unit "% livre".
- `filegroup_unlimited_free_gb` — FGs UNLIMITED disk-bound, GB livres no
  volume, defaults warning=10 / critical=5.

**Contratos novos no registry/router (V6 herda o mecanismo):**
1. `higher_is_worse: False` nas duas entradas — são KPIs "menor=pior".
   O router de escrita (POST /api/v1/kpi-thresholds) valida a direcção
   com esta flag (default True). SEM a flag, gravar os próprios defaults
   (w=5 > c=2) devolve 400 — foi o 1º bug que o painel apanhou.
2. `warning_cap: 10` no free_pct — o tier ATTENTION (5-10% livre) fica
   FIXO nesta fase (a WDB_KPI_THRESHOLDS partilhada só tem
   Warning/Critical; ALTER = veto v1-intel). O cap impede a banda
   Warning de engolir a Attention e mantém válidos os pré-filtros WHERE
   estáticos (`Percent_Used > 80` no card, `> 90` no detail).
3. O ramo UNLIMITED exige WHERE **dinâmico** derivado do warning
   (`warning_gb*1024`) — não há tier de folga acima dele; subir o aviso
   sem mover o WHERE esconde linhas EM SILÊNCIO. É o risco silent-hiding
   do challenger (04/08) confirmado obrigatório aqui.
4. Conversões nos consumidores: % livre → `Percent_Used` é `100 - x`;
   GB → MB é `*1024`. Cada derivação é ponto de drift — os testes golden
   de literais protegem (ver 6).
5. `REGISTRY_VERSION` bump (V3.3: `2026-08-13.f15`).

**Superfícies V3.3 migradas (V6: grep equivalentes, a contagem PODE
diferir):** 6 queries — helpers card CTE + disk_query UNLIMITED;
endpoint detail da modal (2 ramos UNION); endpoint da lista de instâncias
da modal (2 queries). NOTA: o painel só tinha mapeado 3; a 4ª superfície
foi apanhada pelo teste anti-regressão — corre o grep por
`5120|10240|Percent_Used >  9|Eff_Free_Pct >=` no V6 ANTES de declarar
o lote fechado.

**Testes (contrato de qualidade a replicar):** goldens dos defaults das
2 chaves; needles anti-regressão dos literais removidos; asserts de
`higher_is_worse`/`warning_cap`/ausência do espelho antigo. V3.3:
`tests/test_kpi_thresholds_registry.py` (7/7 verdes).

**Infra partilhada (afecta-vos directamente):**
- A BD `WDB_KPI_THRESHOLDS` é a MESMA — overrides gravados pelo Std
  aplicam-se ao que o V6 ler via `threshold_overrides.resolve()`. Se o
  V6 classificar filegroups com literais próprios, as duas edições
  mostram cores diferentes sobre os mesmos dados: migrem o read-path
  no mesmo lote.
- FIND-20260813-101 (P1, lado V1): `KPI_MSSQL_DATAFILES_STG` não está
  em `KPI_STG_ACTIVE_TABLE` no canonical (só na BD viva, fora-de-banda).
  Fresh install parte o swap desta família. Não é fix V6, mas o vosso
  ramo UNLIMITED depende desta fonte — acompanhem o lote fresh-install
  (FIND-20260805-109/110).

## Lote 3 — Deadlocks configurável (backend, mesmo dia)

`deadlocks_state` deixou de ser espelho: o V3.3 classifica no backend via
`_th()` sobre `Deadlock_Count` (warning 10 / critical 20 configuráveis;
INFO fixo ≥1) e **reescreve `State`/`Severity` nas rows** vindas da
`KPI_MSSQL_DEADLOCKS_AGG_VIEW` — a coluna State da view continua a existir
mas já não é a verdade para o Std. A ordenação da modal saiu do SQL
(`ORDER BY d.State` ordenava pela verdade velha) para Python.

**CRÍTICO para o V6:** a view é partilhada e o V6 consome deadlocks em ~8
sítios (censo 11/08). Se o V6 continuar a ler o State da view enquanto o
Std reclassifica, um override do cliente faz as duas edições mostrar
severidades diferentes sobre os mesmos dados — migrem o read-path no MESMO
lote (padrão: reescrever State/Severity pós-fetch + sort em Python).

## Lote 4 — TLOG + PROCESSES + INTEGRITY configuráveis (mesmo dia)

Mesma doutrina do lote 3 (backend reclassifica, view partilhada intacta),
com três variações que o V6 tem de replicar com cuidado:

- **TLOG (`tlog_usage` 85/95):** a AGG_VIEW só expõe contagens JÁ
  classificadas — não há valor bruto nela. O Std agrega directamente da
  `KPI_MSSQL_TLOG_USAGE_ACTIVE` com um sub-select de forma IDÊNTICA à
  view (Instance/Env/Total_Databases/Critical/Warning/Normal/Last_Check),
  nas duas pontas (card + modal). Se o V6 consome a AGG_VIEW ou a
  DET_VIEW (report TLOG!), essas continuam a 85/95 fixos — decidir
  migrar ou aceitar divergência documentada.
- **PROCESSES (`processes_runnable` 20/50):** o WHERE por `[State]` da
  view esconderia linhas se o warning baixar de 20 — passou a
  `Runnable_Count > {warning}` + State reescrito pós-fetch. Comparação
  ESTRITA `>` (como a view), não `>=`.
- **INTEGRITY (`integrity_checkdb_age`, cutoff=warning em dias, critical
  N/A):** fronteira P4/P5 recalculada sobre `Days_Since_CheckDB` — no
  card em Python, na modal via CASE SQL que substitui `v.Verdict`,
  `v.Verdict_Reason` E o `ORDER BY` (os três citavam a verdade velha).
  P1/P3/higiene/unmeasurable continuam a vir da view tal-e-qual. O V6
  consome integridade em vários sítios — grep por `Verdict = 'P4'` e
  `INTEGRITY_VERDICT_VIEW` antes de fechar.

**Estado final Std 13/08:** 13 KPIs configuráveis (7 F1 + 6 F1.5).
DISK (regra por-drive/tiers) e MEMORY (Severity persistida na recolha)
continuam deliberadamente não-configuráveis — fundamentação no design
doc §5-ter.

## Lote 5 — BD partilhada + canonical (13/08, tarde)

- A `WDB_KPI_THRESHOLDS` **não existia** na Intelligence viva (o DDL de
  04/08 não sobreviveu; a primeira escrita denunciou com 42S02). Owner
  recriou as 2 tabelas (thresholds + audit) a 13/08 — como a BD é
  partilhada, os overrides gravados pelo Std passam a existir PARA
  TODOS os consumidores, incluindo o V6.
- O canonical V1 `INSTALACAO_COMPLETA_UNIFICADA.sql` ganhou a secção
  WDB_KPI_THRESHOLDS (~linha 2074, após o bloco WDB_KPI_BASELINE) —
  **replicar na vossa cópia do canonical V6** (mesma posição relativa),
  como nas sincronizações de 10-11/08.
- UX do ecrã Thresholds no Std (avaliar paridade): badge renomeado para
  "nao ajustavel (definido na recolha)" com tooltip explicativo;
  não-ajustáveis ordenados para o fim da lista; erro 503 com mensagem
  accionável quando a tabela falta.

## Lote 6 — CSP: blocos `<script>` sem nonce morrem em silêncio (FIND-20260813-103)

No V3.3, 3 blocos `<script>` sem `nonce="{{ csp_nonce }}"` ficaram mortos
sob a política CSP estrita (em vigor no dev desde o lote de 12/08):
Collectors/Mutes sem clique, help do Performance mudo, flash de tema.
Sintoma engana: `script-src-attr 'unsafe-inline'` deixa o onclick CORRER,
mas a função nunca foi definida → ReferenceError silencioso, "nada
acontece" sem alert. **O V6 tem o mesmo padrão**: verificado 13/08 —
`analytics_dashboard.html` tem 4 blocos `<script>` sem atributos e
`space_dashboard.html` tem 1. Quando a política estrita chegar ao V6
(mesmo middleware partilhado), morrem da mesma forma. Fix: nonce nos
blocos; gate de release: grep por `<script>` (sem nonce) em todos os
templates antes de fechar bundle. Cuidado com falsos positivos: strings
JS com `<\/script>` escapado (janelas de impressão) não são blocos reais.

**2ª metade (descoberta no browser test):** o CSP bloqueia `<style>` sem
nonce tal como `<script>` — a modal Collectors abria mas SEM CSS, e o
módulo Performance inteiro estava sem estilos page-level. No V3.3 foram
9 blocos `<style>`: 2 page-level, 2 injectados via innerHTML e 4 em
popups/Blob (que HERDAM o CSP do opener — o nonce do Jinja é substituído
no render e vale lá também). O grep do gate tem de cobrir `<style>` além
de `<script>`. No V6, façam o sweep dos dois de uma vez.

**Fora deste lote (fica em V3.3 como follow-up, avaliem paridade):**
FIND-20260813-102 — textos de ajuda/i18n/Space Health com números
hardcoded que deixaram de ser verdade fixa.
