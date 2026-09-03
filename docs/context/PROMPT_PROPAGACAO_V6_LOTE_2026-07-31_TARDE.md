# PROMPT — Propagação V3.3 → V6 · Lote 2026-07-31 (tarde)

Para a sessão AI do V6. Origem: sessão V3.3 de 31/07 (tarde), commits V3.3
`f57acb5`, `1fb09d8`, `6b06f90`, `db195f2`, `53852d1` + V1 `9a39aaf` (branch
`wave-b-indexacao-dmv`, monorepo projetosPython). Regras aplicáveis:
`v33-v6-propagation-rule` (fixes propagam) e `v6-portal-not-superset`
(**grep anchors no V6 primeiro** — o item pode nem existir lá). V3.3 validado
em browser pelo owner a 31/07. Precedente de adaptação: lote `6bed5df`
(V6 sem `t()` → strings PT hardcoded).

---

## 0. Contrato dos dados — ler ANTES de consumir ou aplicar seja o que for

1. **`KPI_STG_ACTIVE_TABLE` é por (Table_Name, Environment)** desde a Wave C
   (manhã de 31/07). O slot BLUE/GREEN NUNCA se resolve sem filtrar Environment:
   ```sql
   SELECT TOP 1 Active_Slot FROM dbo.KPI_STG_ACTIVE_TABLE
   WHERE Table_Name = '<familia>' AND Environment IN ('<ENV>','ALL')
   ORDER BY CASE Environment WHEN '<ENV>' THEN 0 ELSE 1 END
   ```
   JOIN/subquery por `Table_Name` sozinho devolve 3 linhas e **multiplica os
   dados ×3** — foi exatamente o que aconteceu no ponto 2.

2. **Views `*_ACTIVE` regeneradas.** A camada de abstração `_ACTIVE` (gerada
   por `usp_create_active_view`) ficou FORA da migração da manhã: o CTE lia o
   slot sem Environment e, com 3 linhas na tabela de controlo, o CROSS JOIN
   servia **cada linha em triplicado** (sintomas reais: modal Instances OK com
   cada instância ×3; modal Backup Failed ×3 por arrasto de um LEFT JOIN à
   `INST_AVAILABILITY_ACTIVE`). Corrigido à tarde: gerador reescrito no padrão
   por-ambiente, 14 famílias regeneradas + `MIRRORING_STATUS_ACTIVE`
   (não estava na lista dos 14 EXECs). **Quem lê `_ACTIVE` já recebe dados
   corretos sem mudar código.** MAS: se o repo V6 tiver cópia própria do
   gerador ou de canonical com o CTE antigo, sincronizar — fonte:
   `WATCHERDB INTELLIGENCE V1/database/INSTALACAO_COMPLETA_UNIFICADA.sql`
   (secção 10.1) e `SECAO_VIEWS_ACTIVE.sql`, commit `9a39aaf`.

3. **`KPI_MSSQL_BACKUP_STATUS_ACTIVE` foi REMOVIDA** (view órfã da família
   `KPI_MSSQL_BACKUP_STATUS_STG`, extinta na Migration 004; zero consumidores
   confirmado via `sys.sql_expression_dependencies` antes do DROP). Grep V6
   por `BACKUP_STATUS_ACTIVE` — qualquer referência é código morto a limpar.

4. **Sweep de verificação** (correr na Intelligence após QUALQUER mudança que
   toque resolução de slot; resultado esperado: 0 rows — a
   `COLLECTION_FRESHNESS_VIEW` usa `MAX+GROUP BY Table_Name` de propósito e
   está excluída pelo terceiro LIKE):
   ```sql
   SELECT v.name FROM sys.views v
   CROSS APPLY (SELECT OBJECT_DEFINITION(v.object_id) AS d) x
   WHERE x.d LIKE '%KPI_STG_ACTIVE_TABLE%'
     AND x.d NOT LIKE '%Environment IN%'
     AND x.d NOT LIKE '%GROUP BY Table_Name%';
   ```

5. **Armadilha `execute_query` → datas como string.** O executor de queries
   live (`modules/monitoring/monitoring.py:277` no V3.3) serializa `datetime`
   → string ISO. Qualquer consumidor que faça aritmética de datas ou chame
   `.isoformat()` sobre valores de rows TEM de parsear primeiro
   (`datetime.fromisoformat`). Causa real do bug do dia: o caminho standalone
   do backup summary usava o valor cru, o `AttributeError` era engolido por
   `try/except` genérico e TODOS os servidores não-AG mostravam datas N/A
   **e zero issues** (uma base sem backup nenhum aparecia verde).

6. **`FILE_SPACE_DETAIL` exclui databases inacessíveis.** O batch dinâmico
   agora filtra `DATABASEPROPERTYEX(name,'Collation') IS NOT NULL` (cobre AG
   com data movement suspenso, secundário não-legível, restoring). Motivo: o
   erro 976 rebenta na **compilação** do sub-batch pós-`USE`, que o TRY/CATCH
   interno não apanha — uma única DB suspensa (MAP_SampleDB no PRD213)
   derrubava o endpoint inteiro com 500. **Semântica para a UI:** ausência de
   uma DB no resultado ≠ "sem ficheiros" ≠ "saudável" — é "não mensurável
   agora"; não inferir verde do silêncio.

---

## 1. BD partilhada — nada a executar (V6 herda)

Já aplicado na Intelligence pelo owner (SSMS) e canonical V1 sincronizado
(`9a39aaf`). Ações V6: (a) grep no repo V6 por cópias do gerador/CTE antigo
(`CROSS JOIN ActiveSlot`, `usp_create_active_view`) e sincronizar; (b) correr
o sweep do §0.4; (c) limpar referências a `BACKUP_STATUS_ACTIVE`.

## 2. Backend V6 — 2 fixes a aplicar (requer restart do serviço V6)

**2.1 Parse de datas no caminho standalone do backup summary.**
Anchor V3.3: `modules/monitoring/backup_analysis.py`, loop `for row in rows:`
do caminho standalone (o caminho AG já parseia via `parse_backup_date`).
Fix: helper `_parse_dt(value)` — `datetime` passa; `str` →
`datetime.fromisoformat(value.rstrip('Z'))` com log em falha; resto → None —
aplicado a `last_full/last_diff/last_log/last_full_start/last_diff_start`.
Sintoma se faltar no V6: aba Backup com datas N/A + zero issues em servidores
não-AlwaysOn.

**2.2 Guarda de DBs inacessíveis no FILE_SPACE_DETAIL.**
Anchor V3.3: `modules/monitoring/queries.py`, `FROM sys.databases WHERE
state = 0` do batch dinâmico. Fix: `AND DATABASEPROPERTYEX(name,'Collation')
IS NOT NULL` (§0.6). As queries irmãs do V3.3 (LOG_SPACE_USAGE, estatísticas)
já tinham guardas próprias — verificar se as do V6 também.

## 3. Portal V6 — grep anchors primeiro (NÃO é superset)

| # | Item | Anchor V3.3 | Grep no V6 | Nota |
|---|------|-------------|-----------|------|
| P1 | Secção "Ultimos Backups por Database" na aba Backup — colapsável entre "Backups com Issues" e "Analise de Gaps", por base o último Full/Diff/Log com idade (`fmtDateWithAge`), dados do `/summary` existente, cabeçalhos "Full/Diff/Log" | `last-backups-section` (~20418) | secção Backup do portal V6 | Zero backend; carrega com a página; i18n `backup.last_backups_section` (PT "Ultimos Backups por Database") |
| P2 | Modal Instances OK: card ganhou `data-env` + inferência de ambiente por nome (era o único sem; filtro PRD escondia os 109) | `title === 'Instances OK'` (~36641) | idem | Inferência tem de ser IGUAL à do gráfico de ambiente |
| P3 | Tiles Full/Diff/Outros falhou: pré-filtro **por dados** antes do render (filtrar `instances` por `Backup_Type_Classified`, mapa D/I/L→FULL/DIFF/LOG) — não filtro visual (tile 0 mostrava as 6 DIFF); títulos "Full Failed"/"Diff Failed"/"Others Failed"; empty-state `kpiModalEmptyState` quando filtros manuais escondem tudo | `full_failed_count` / `showProblematicInstances` (param `preFilterType`) | `full_failed_count` | i18n novas: `kpi_modal.filter_empty` + `filter_empty_hint` (fallback embutido) |
| P4 | Shrink doctrine (modal Análise de Redimensionamento): opção segura passa de `ALTER MODIFY FILE (SIZE menor)` — que NÃO reduz nada, Msg 5039 — para `DBCC SHRINKFILE (..., TRUNCATEONLY)`; LOGs fora do lote seguro; alvos de SHRINK = usado×1.3 (mín +512MB) com comentário no SQL; notas práticas (teto/LOG-VLF/growth/margem) DENTRO da análise; labels "TruncateOnly" | `genResizeSQL`/`genShrinkSQL`/`openDriveDetailModal` (~9769) | `genResizeSQL` ou equivalente | CRÍTICO se o V6 tiver o gerador — emite T-SQL inválido para clientes |
| P5 | Catálogo eventos Windows: `static/js/win_events_catalog.js` (~45 entradas, copiar 1:1) + `<script src>` + ⓘ com tooltip nativo junto ao Event ID | `winEventCatalogLookup` / `renderWinRows` | tabela de eventos Windows do V6 | Offline por design; explicação AI é Pro — no V6 Pro PODE optar por camada AI, mas o catálogo estático serve de fallback |
| P6 | Space: headers empilhados — thead dos datafiles sem scroll próprio embutido, sticky com `top` = altura REAL do thead dos filegroups medida em runtime (`getBoundingClientRect().height` pós-render); fullscreen mantém scroll próprio | `space-datafiles-scroll` (~3277 CSS + ~27582 + medição pós `filesContent.innerHTML`) | `space-datafiles-scroll` | Corrige o falso "used > max" (linhas de uma tabela sob header da outra) |
| P7 | Modal logs de serviço: ordenação nos 4 headers (Data/Hora desc default; Nível por gravidade) + linha de filtros por coluna (inputs texto p/ Data e Mensagem em `onchange`, selects p/ Nível e Fonte com valores presentes); integra com cards/badges e "Limpar" limpa tudo | `renderServiceLogsTable` / `sortServiceLogs` / `serviceLogsColFilters` | `renderServiceLogsTable` | |
| P8 | Loading da análise de redimensionamento: "Análise de redimensionamento a ser realizada (X:)..." — i18n `log.resize_analysis_loading` | `openDriveDetailModal` loading | idem | Pedido explícito do owner |

## 4. Pendências que o V6 deve CONHECER (não aplicar ainda)

- **Falso-OK estrutural do módulo Backup (aberto também no V3.3):** o frontend
  descarta as issues do backend e recalcula (`recalculateIssues` só avalia
  `hours_since_last_diff != null`) — DB **sem backup nenhum** aparece verde.
  Fix desenhado, por aplicar no V3.3 primeiro. Grep V6 por `recalculateIssues`
  para saber se herda o padrão; aguardar a solução V3.3.
- **Janela de dados inflados:** paineis/históricos V6 que leram views
  `_ACTIVE` entre ~09:30 e ~17:00 de 31/07 apanharam contagens ×3 (janela do
  defeito). Snapshots dessa janela não são comparáveis.
- **Findings operacionais (infra, não código):** AG `SQLAGSPRD213` com data
  movement suspenso (é o que expõe o §0.6); job `DBA_DIFF_BACKUP` do
  SQLMDMQLT03\I01 falha todas as noites às 20:00 (visível desde hoje).

## 5. Verificação pós-aplicação (gate antes de declarar shipped)

1. Sweep §0.4 na Intelligence = 0 rows.
2. Modais Instances OK / Backup Failed: sem duplicados; contagens = tiles;
   tile Full com 0 abre modal coerente (vazio limpo, não "0 de 6").
3. Servidor não-AG: datas de backup preenchidas e issues a disparar.
4. Análise de redimensionamento: SQL gerado começa com `DBCC SHRINKFILE
   (..., TRUNCATEONLY)`; PRD213 (ou qualquer servidor com AG suspenso) abre
   sem 500.
5. Browser test antes de declarar shipped (regra 2026-06-01) + restart do
   serviço V6 para os itens backend.
