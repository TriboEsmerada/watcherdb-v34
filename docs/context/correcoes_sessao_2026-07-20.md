# Correções da sessão — 2026-07-20

Registo de correções aplicadas em V3.3 nesta sessão, para **propagação a V6** e histórico.
Convenção: cada correção tem contexto, root-cause, diff, verificação e status de propagação V6.

> Regra do projeto: fixes/improvements V3.3 devem ser validados e propagados a V6
> (V6 = V3.3 + extras). Ver memória `feedback_v33_v6_propagation_rule`.
> Nota: portal V6 é **subset simpler** de V3.3 (não superset) — grep anchors V6 antes
> de assumir que o código existe lá. Ver `feedback_v6_portal_not_superset`.

---

## CORR-2026-07-20-001 — Drilldown de disco aparece vazio quando filtro é um path de drive

**Módulo:** Portal SPA / Disco (Detalhes dos Volumes → drilldown de ficheiros)
**Ficheiro:** `templates/watcherdb_portal.html` (~linha 11254, dentro de `toggleDiskDrillDown`)
**Severidade:** Média (falso "sem dados" — utilizador acha que backend falhou; na verdade backend devolve tudo)
**Tipo:** Frontend-only (nenhum toque em DB, endpoint intacto)

### Sintoma
Ao expandir o drilldown de um volume (ex.: `F:\Data_7\`), a tabela de ficheiros aparecia
vazia — banner "Filtrado por: Texto: f:\ (0 de 78 arquivos)" e "0.00 GB de 2024.86 GB".
Backend (`GET /api/queries/disk-files/{server}?drive=...`) devolvia corretamente os 78
ficheiros / 2024 GB; o problema era puramente de filtragem no cliente.

### Root cause
O input "Filtrar" (`#disk-filter-input`) tem **dupla função** com um único valor:

1. **Tabela externa de volumes** — `filterDiskTable()` compara o texto contra o **caminho
   do drive** (`drive.includes(textFilter)`), label e metadados de ficheiro. Um token como
   `f:\` casa aqui (`f:\data_7\`.includes(`f:\`) → true), logo o drive aparece.
2. **Drilldown de ficheiros** — `toggleDiskDrillDown()` reutilizava o **mesmo** valor mas
   comparava **só** contra `database_name`, `filegroup_name` e `logical_name` — nunca contra
   `physical_path`.

Quando o utilizador clica na barra do drive, `toggleDiskBarHighlight()` faz
`filterInput.value = letter + ':\\'` (ex. `f:\`). Esse token de **path** casa na tabela
externa mas nunca casa num nome lógico/DB/filegroup no drilldown → **0 de 78 ficheiros**,
mesmo com o volume inteiro carregado.

### Correção aplicada
Incluir o caminho físico nos campos pesquisáveis do drilldown. Como todos os ficheiros do
volume começam pelo path do drive, um token de path passa a casar com todos (comportamento
intuitivo), e continua a permitir filtrar por nome/DB/filegroup.

```diff
                 if (activeText) {
                     displayFiles = displayFiles.filter(f =>
                         (f.database_name || '').toLowerCase().includes(activeText)
                         || (f.filegroup_name || '').toLowerCase().includes(activeText)
                         || (f.logical_name || f.name || '').toLowerCase().includes(activeText)
+                        || (f.physical_path || f.physical_name || '').toLowerCase().includes(activeText)
                     );
                 }
```

Confirmado que o endpoint devolve o campo: `space.py:221` seleciona
`mf.physical_name as physical_path` (chave `physical_path`).

### Verificação
- [ ] Hard-refresh (Ctrl+F5) no portal V3.3 (porta 8433).
- [ ] Selecionar servidor → módulo Disco → clicar barra de um drive → expandir drilldown.
- [ ] Confirmar que os ficheiros aparecem (não "0 de N").
- [ ] Confirmar que filtro por nome de DB / logical name continua a funcionar.

### Propagação V6
- [ ] Grep V6 portal por `toggleDiskDrillDown` + bloco `activeText`/`displayFiles.filter`.
      Se existir com a mesma estrutura, aplicar o mesmo `|| physical_path`.
      Se o drilldown de disco não existir em V6 (subset), marcar N/A e registar.
- Status: **PENDENTE**

---

## CORR-2026-07-20-002 — Drilldown de disco sem ordenação nem filtros por coluna

**Módulo:** Portal SPA / Disco (drilldown de ficheiros do volume)
**Ficheiro:** `templates/watcherdb_portal.html` (bloco `toggleDiskDrillDown`, ~11197) +
`static/i18n/{pt,en,es}.json` (novo namespace `disk.drill.*`, 13 chaves × 3 locales)
**Severidade:** Baixa (melhoria de usabilidade, não bug)
**Tipo:** Frontend-only (nenhum toque em `space.py` nem infra partilhada)
**Autoria:** diff produzido por `watcherdb-frontend-specialist`, anchors verificados + aplicado pelo orquestrador.

### Pedido
Na tabela do drilldown: (a) ordenação ao clicar em qualquer das 8 colunas
(Database, Arquivo, Tipo, FileGroup, Tamanho, Max Size, Growth, Path); (b) filtros por
coluna (texto em Database/Arquivo/FileGroup, dropdown Todos/ROWS/LOG em Tipo).

### Implementação
- **Refactor de estado:** `renderDrillDown` era closure dentro de `toggleDiskDrillDown`.
  Passou a `buildDiskDrillHtml(drillId, state, files)` + `renderDiskDrillById(drillId)`
  top-level, com estado isolado por drilldown em `window.diskDrillState[drillId]`
  (`allFiles`, `globalFiltered`, `sortCol`, `sortAsc`, `colFilters`). Permite vários
  drilldowns abertos sem bleed de estado.
- **Sort:** `sortDiskDrillColumn(drillId, col)` alterna asc/desc; ícone `fa-sort`/`fa-sort-up`/`fa-sort-down`
  (mesmo idioma do outer `sortDiskTable`). Colunas string via `localeCompare`; Tamanho via
  `size_gb` numérico.
- **Max Size / Growth (OPÇÃO A, frontend-only):** parse client-side das strings formatadas.
  `parseDiskMaxSizeToGb`: Unlimited→∞, TB/GB/MB/KB→GB. `parseDiskGrowthToComparable`:
  absoluto→MB; percentual (`%`) agrupado via offset +1000000 (convenção, não unidade
  física comparável — documentar ao QA).
- **Filtros de coluna:** `filterDiskDrillColumn(drillId, field, value)`, aplicados DEPOIS
  dos filtros globais existentes (`activeDb`/`activeFg`/`activeText`), sem re-fetch.
- **Gotchas resolvidos:** restauro de foco/cursor no input após rebuild de innerHTML
  (senão perde foco a cada tecla); `escDiskAttr` para escapar o `value` refletido no input.
- **i18n:** namespace `disk.drill.*` (13 chaves) inserido em pt/en/es entre
  `db_latency_details` e `filter_label`. `_flattenDict` (i18n_v2.js) é recursivo → chaves
  dotted nested funcionam. JSON dos 3 validado com `ConvertFrom-Json`.

### Verificação
- [x] Sintaxe dos 3 JSON válida (ConvertFrom-Json OK).
- [ ] **Ctrl+F5** + testar no portal (checklist do specialist):
  - Sort de cada coluna (asc/desc, ícone muda).
  - Max Size "Unlimited" no topo/fundo; "2 TB" acima de "39.77 GB".
  - Growth: valores `%` agrupados; ordem relativa entre `%` correta.
  - Filtro de coluna: cursor NÃO salta para fora do input ao digitar.
  - Múltiplos drilldowns abertos → sem bleed de estado.
  - Trocar idioma PT/EN/ES → placeholders/tooltips/dropdown mudam.

### Débito técnico deixado (follow-up separado, NÃO neste diff)
- Headers de coluna do drilldown continuam hardcoded em PT (namespace `disk.drill.col_*`
  já reservável).
- `<th onclick>` de sort não focável por teclado — padrão herdado em ~8 tabelas do SPA;
  recomendação do specialist: helper `makeSortableHeader` numa wave de a11y dedicada.
- Botão "Limpar" do badge de filtro global fecha o drilldown (UX pré-existente, confirmar
  com customer-success se é intencional).

### Propagação V6
- [ ] Grep V6 portal por `toggleDiskDrillDown`. Se existir com estrutura equivalente,
      aplicar o mesmo refactor + i18n. Se drilldown de disco não existir em V6 (subset),
      marcar N/A.
- Status: **PENDENTE**

---

## CORR-2026-07-20-003 — Modais sem botão maximizar/restaurar (Fase 1: Performance)

**Módulo:** Portal SPA — infra de modais + modal de investigação de Performance
**Ficheiro:** `templates/watcherdb_portal.html` (4 zonas) + `static/i18n/{pt,en,es}.json` (`ui.maximize`, `ui.restore`)
**Severidade:** Baixa (melhoria de usabilidade)
**Tipo:** Frontend-only. **FASE 1 de 2** (rollout faseado).
**Autoria:** diff por `watcherdb-frontend-specialist`, anchors verificados + aplicado pelo orquestrador.

### Pedido
Botão "expandir para tela toda" (fullscreen toggle) nas modais. Começar pela modal de
Performance (investigação L2-L5, sistema `inv-modal-overlay`) e **generalizar a infra** para
o sweep às restantes ~16 modais na Fase 2.

### Implementação (Fase 1)
- **Generalização** de `toggleMaximizeModal(modalId)` ([~23934](../../templates/watcherdb_portal.html)):
  passou a procurar o content em `MAXIMIZABLE_CONTENT_SELECTORS = ['.modal-content', '.inv-modal']`
  (antes só `.modal-content`). Preserva `alertsModal` 1:1. Título/aria dinâmicos (`ui.maximize`↔`ui.restore`)
  só para botões opt-in via `data-i18n-title`.
- **CSS** `.inv-modal.maximized` (98vw/96vh + border-radius:4px, coerente com `.sql-results-modal-content.maximized`;
  `height` fixo p/ o `.inv-body flex:1` manter scroll interno).
- **Botão** maximizar no header `inv-header` (ícone `fa-expand-alt`↔`fa-compress-alt`), + `aria-label` no × de fechar.
- **Reset** do estado `.maximized` em `perfCloseModal` (senão reabria já fullscreen).
- **i18n**: `ui.maximize` / `ui.restore` nas 3 locales. JSON validado (ConvertFrom-Json OK). Motor usa
  `data-i18n-title`/`data-i18n-aria` + MutationObserver → sobrevive a troca de idioma pós-abertura.

### Achado crítico (colisão evitada)
Já existia `toggleModalMaximize()` (sem "s", zero-arg) dedicada ao **SQL Results modal** ([~41961](../../templates/watcherdb_portal.html)).
Usar esse nome para a função genérica teria partido silenciosamente o SQL Results. Mantido o nome
existente `toggleMaximizeModal`. **NÃO usar `toggleModalMaximize` na Fase 2.**

### Inventário Fase 2 (PENDENTE — não implementado)
5 implementações divergentes de maximize no SPA. Modais/sistemas que faltam o botão ou têm versão divergente:
| Sistema | Content | Função atual | Botão hoje? |
|---|---|---|---|
| `.modal` (reportModal, settings, changePassword, serviceLogs, logMessage, memoryPressure) | `.modal-content` | `toggleMaximizeModal` já compatível — só falta o botão no header | Não |
| `.instances-modal` (instances, kpiHelp, cpuHelp, conflitos) | `.instances-modal-content` | `toggleConflictsModalMaximize` (inline styles, sem i18n) / nenhuma | Parcial/divergente |
| `sql-results-modal` | `.sql-results-modal-content` | `toggleModalMaximize()` (nome colidente) | Divergente |
| `report-modal-overlay` | `.report-modal` (falta CSS `.maximized`) | `toggleReportMaximize()` | Divergente |

Decisão Fase 2: consolidar as 3 divergentes em `toggleMaximizeModal` ou mantê-las? (avaliar no sweep).

### Verificação
- [x] JSON 3 locales válidos; `MAXIMIZABLE_CONTENT_SELECTORS` declarado 1×.
- [ ] **Ctrl+F5** + testar: abrir modal Performance → maximizar (98vw/96vh, ícone muda) → restaurar
  → fechar → reabrir (NÃO vem maximizada) → scroll interno em fullscreen → trocar idioma (tooltip muda)
  → **confirmar alertsModal ainda maximiza** (regressão).

### Follow-ups a11y (fora de escopo, registados pelo specialist)
- `inv-modal-overlay` sem `role="dialog"`/`aria-modal` (gap sistémico, não introduzido aqui).
- `<th onclick>` sort não focável por teclado (herdado, ver CORR-002).

### Propagação V6
- [ ] Grep V6 por `toggleMaximizeModal` + `inv-modal-overlay`. Aplicar Fase 1 se existir.
- Status: **PENDENTE**

---

## CORR-2026-07-21-004 — Maximizar/restaurar em todas as modais (Fase 2: sweep)

**Módulo:** Portal SPA — sweep do botão maximizar às modais restantes
**Ficheiro:** `templates/watcherdb_portal.html` (Zonas A-E aplicadas)
**Severidade:** Baixa (usabilidade). **FASE 2 de 2.**
**Autoria:** diff por `watcherdb-frontend-specialist`, anchors re-lidos por texto (line numbers do specialist estavam desatualizados por CORR-002/003) + aplicado pelo orquestrador.

### Aplicado (Zonas A-E)
- **Zona A (JS):** `MAXIMIZABLE_CONTENT_SELECTORS` += `.instances-modal-content`; helper novo `resetModalMaximized(modalId)` (generaliza o reset); `closeAlertsModal` refatorado p/ usar o helper (DRY).
- **Zona B (CSS):** `.instances-modal-content.maximized` (98vw/96vh) + override `#kpiHelpModalBody`.
- **Zona C (`.modal`):** botão maximizar em reportModal, memoryPressureModal, settingsModal, serviceLogsModal, logMessageModal.
- **Zona D (`.instances-modal`):** botão em instancesModal, kpiHelpModal, cpuHelpModal, memoryHelpModal.
- **Zona E (reset no close):** resetModalMaximized adicionado a 7 funções de close (memoryPressure, report, instances, kpiHelp, serviceLogs, logMessage, settings). cpu/memoryHelp resetam inline no onclick.
- **i18n:** reutiliza `ui.maximize`/`ui.restore` (CORR-003). Headers estáticos usam `data-i18n-title`/`data-i18n-aria` (aplicados no boot + MutationObserver).

**Validação:** 10 ids `MaxIcon` únicos; `resetModalMaximized` 1 def + 10 calls; 10 call-sites `toggleMaximizeModal` — todos consistentes (grep).

### DIFERIDO (Zona F — não aplicado)
i18n dos tooltips hardcoded nos **4 divergentes** que já funcionam mas mostram "Maximize"/"Maximizar/Minimizar" fixo: `toggleConflictsModalMaximize` (3 call-sites + função), `toggleReportMaximize`, `toggleDiagnoseModalExpand`, + reset opcional em `closeSQLResultsModal`.
**Motivo do defer:** valor baixo (traduzir tooltip de botão já funcional) vs risco de tocar em código dinâmico funcionante com anchors aproximados, no fim de uma aplicação grande. Follow-up isolado.

### Excluídos por decisão (não são débito)
- `changePasswordModal`, `selectableModal` — diálogos pequenos, maximizar não acrescenta valor.
- `backupGapsModal` — **code-smell pré-existente** (duas implementações para o mesmo ID: `createBackupGapsModal` sem maximize vs outra com maximize inline). Tocar reforçaria a divergência. Resolver a duplicação primeiro (finding do specialist).

### Verificação
- [ ] **Ctrl+F5** + por cada modal: abrir → maximizar (98vw/96vh, ícone→compress) → restaurar → fechar → reabrir (**NÃO vem maximizada**).
- [ ] `kpiHelpModal` (crítico): painel lateral 280px + conteúdo esticam corretamente maximizado.
- [ ] Regressão: `alertsModal` (Fase 1) ainda maximiza após refactor p/ helper.
- [ ] Empilhamento: `logMessageModal` (z-index 10001) sobre `serviceLogsModal`.

### Propagação V6
- [ ] Grep V6 por `toggleMaximizeModal`/`resetModalMaximized`. Aplicar Fase 1+2 se existir.
- Status: **PENDENTE**

---

## CORR-2026-07-21-005 — [KPI Manutenção Idx&Stats] TIER DECIDIDO: Std (design pendente)

**Estado:** DESIGN / não implementado. Registo da decisão de tier + achados para não perder contexto.

- **Tier: Std** (parecer `watcherdb-v33-specialist` vs `FEATURE_MATRIX.md:70` "Backup Status (schedule-based gap detection)"). O motor de cadência auto-calibrado **já é Std** — `BackupPatternAnalyzer` ([backup_pattern_analysis.py](../../modules/monitoring/backup_pattern_analysis.py)) já o faz p/ backups (min 3 amostras, intervalo médio+desvio, confidence, gap severity, fallback nativo backupset Wave R+8, missing-log-chain Wave I, guards AlwaysOn/system DB). **NÃO é tier creep.**
- **Fronteira Std|Pro:** extensão a CHECKDB (`dbi_dbccLastKnownGood`) + Statistics (`STATS_DATE`) reutilizando o motor = **Std**. Reservado a **Pro**: auto-deteção CommandLog/Ola (categoria Integrations), gap forecasting/ML, baseline compare cross-instance.
- **Consequência:** CommandLog → Pro, logo build Std é **native-first** e o probe Ola-vs-nativo **deixa de bloquear**.
- **Wiring:** `BackupPatternAnalyzer` é o vivo (watcherdb_main.py, watcherdb_intelligence.py, backup_service.py). `BackupGapDetector` parece **código morto** (só definição). Base de extensão = `BackupPatternAnalyzer`.
- **Plano:** generalizar/estender `BackupPatternAnalyzer` p/ checkdb+stats → novo endpoint `/maintenance-health/{server_id}` em `performance.py` → tile no Performance. Design SQL: `sql-deep-reviewer`. Paridade V3.3↔V6: `watcherdb-v5-specialist`.
- **Débito relacionado (finding):** 3 módulos de backup sobrepostos em V3.3 (`backup_pattern_analysis.py`, `backup_analysis.py`, `backup_gap_detector.py`) com parsing sysjobs/sysschedules duplicado. Mapear/consolidar antes de criar um 4º.
- Status: **AGUARDA GO para dispatch de design (sql-deep-reviewer + v5 specialist).**

---

<!-- Próximas correções desta sessão (append aqui):
## CORR-2026-07-21-00X — <título>
... mesmo template ...
-->
