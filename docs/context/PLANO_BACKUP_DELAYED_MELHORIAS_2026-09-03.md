# PLANO — Backup Delayed: melhorias pós-council (2026-09-03)

Origem: revisão do owner sobre o painel Backups (Delayed aviso/crítico, Log
Falhou, Agendamento DIFF parado). Debatido em 2 rondas com
`watcherdb-v33-specialist` (consenso, 1 discordância integrada em A3).
Precedentes: `COUNCIL_BACKUP_DELAYED_SIGNAL_2026-09-01.md` (R1-R5), Fase 2
recuperação job-level (2026-08-21), gates C1/C2 sql-deep (01/09).
Estado: **AGUARDA GO do owner** por lote. Nada alterado.

## 1. Diagnóstico (factos, ficheiro:linha)

| # | Facto | Onde |
|---|---|---|
| D1 | "Esperado" = `Last_Backup_Date + warning_h` = instante em que o aviso disparou; por construção SEMPRE no passado numa linha em atraso. Valor certo, rótulo errado. | `backup_delayed_classes.py:168`; portal `39461` |
| D2 | "Recuperado" no Delayed não se aplica: Delayed é ESTADO (snapshot da view), Failed é EVENTO (`Resolved_By_Success_TS` do collector). Episódios de atraso não são persistidos → exigiria DDL partilhado (veto v1-intel). | `helpers.py:1700-1770` |
| D3 | "Recuperado" no Log Falhou JÁ EXISTE (mesmo ramo que backup-failed; portal chama `_kpiBackupRecoveredHtml` para ambos). Desde **02/09 (decisão do owner)** as recuperadas ficam ESCONDIDAS por omissão atrás do chip mostrar/ocultar — é por isso que não aparecem. Se com o chip ligado continuarem a 0, aí é dado (M7). | `intelligence_kpis.py:1629-1776`; portal `39481`; CONTEXT 2026-09-02 (modais DIFF/LOG) |
| D4 | "Agendamento DIFF parado" é subproduto do perdão chain-reset (R2); FULL parado == em atraso (já contado). Detecção "agendamento parado" por tipo pertence a jobs-overdue / jobs-no-schedule / jobs_disabled (per-job, não per-database). | `backup_delayed_classes.py:189-203`; portal `18400-18417` |
| D5 | `Hours_Since_Backup` é INT — collector V1 `DATEDIFF(HOUR)`. LOG crítico 2h só dispara aos 3h reais (2h59m → 2 → não > 2). | V1 `collect_backups.py:34,92`; canonical `:885` |
| D6 | `av.Recovery_Model` já está no INNER JOIN da query delayed mas não é seleccionado. | `helpers.py:1717`; canonical `:1110` |
| D7 | **Três conjuntos de thresholds divergentes** para "backup overdue": registry Wave D (FULL 120/168h, DIFF 24/30h, LOG 1/2h) · SP do Overview `OVERVIEW_INSTANCE_SNAPSHOT` (FULL >48h, LOG >24h, hardcoded em SQL) · help do card Overview ("FULL <= 7 dias, DIFF <= 24h, LOG <= 8h"). Nenhum bate com nenhum. | canonical `:9647`; `overview_dashboard.py:711-712`; portal `18234` |

## 2. Medições prévias (owner corre — `sql_monitoring`, read-only, WatcherDB_Intelligence)

```sql
-- M5: LOG em atraso por Recovery_Model (decide B2a)
SELECT av.Recovery_Model, COUNT(*) AS linhas_log_em_atraso
FROM dbo.vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE b WITH (NOLOCK)
JOIN dbo.KPI_MSSQL_DB_AVAILABILITY_STG av WITH (NOLOCK)
  ON av.Instance = b.Instance AND av.[Database] = b.[Database]
WHERE b.Backup_Type IN ('L','LOG') AND b.Hours_Since_Backup > 1
  AND b.Update_TS >= DATEADD(DAY,-2,GETDATE())
GROUP BY av.Recovery_Model;

-- M6: efeito de B1 (horas fraccionárias) no crítico LOG — tabela antes/depois
SELECT
  SUM(CASE WHEN Hours_Since_Backup > 2 THEN 1 ELSE 0 END) AS log_critico_hoje_INT,
  SUM(CASE WHEN DATEDIFF(MINUTE, Last_Backup_Date, GETDATE()) > 120 THEN 1 ELSE 0 END) AS log_critico_com_B1
FROM dbo.vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE WITH (NOLOCK)
WHERE Backup_Type IN ('L','LOG') AND Update_TS >= DATEADD(DAY,-2,GETDATE());

-- M7: LOG recuperado existe? (decide Lote C)
SELECT CASE WHEN Job_Name LIKE '%LOG%' THEN 'LOG' ELSE 'FULL/DIFF/OTHER' END AS Tipo,
       COUNT(*) AS Total,
       SUM(CASE WHEN Resolved_By_Success_TS IS NOT NULL THEN 1 ELSE 0 END) AS Recuperados
FROM dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG WITH (NOLOCK)
WHERE Failure_Source = 'sysjobhistory'
GROUP BY CASE WHEN Job_Name LIKE '%LOG%' THEN 'LOG' ELSE 'FULL/DIFF/OTHER' END;
```

## 3. Lotes (ordem recomendada)

### Lote A — portal só, zero mudança de número, 1 commit
- **A1** Modal delayed: "Esperado: X" → **"Limite de aviso: X (excedido há Nh)"**; retirar a linha "Gap … vs expected" (redundante). Portal `39461-39462`. Chaves i18n pt/en/es (`static/i18n/*.json`).
- **A2** Renomear "Agendamento DIFF parado" → **"Cadeia DIFF parada (FULL a cobrir)"** nos 5 sítios (portal `36123`, `39722`, `43913`, `44262`, título da modal) + help a explicar porquê só DIFF e a apontar para jobs-overdue / jobs-no-schedule.
- Gates: `v33-i18n-coverage`, browser 8433, regressão modal (combobox, cross-filter, números iguais).

### Lote B1 — horas fraccionárias (ISOLADO: muda o número executivo)
- Em `classify_delayed`, derivar `hours` SEMPRE em float de `now - Last_Backup_Date` quando a data existe (hoje só em C1 NULL e C2 DIFF). Elimina D5 sem tocar no collector. Limpar `cur[1]` de `full_info` (dead weight, nunca lido).
- Risco: clock skew portal↔instância origem (já aceite em C1/C2); contagens LOG crítico SOBEM (M6 dá o delta).
- Exige: M6 antes/depois, `requires_approval`, sign-off do owner citando o delta, teste `test_b1_log_2h59_e_critico`, CHANGELOG explícito, rollback = reverter 1 commit.

### Lote B2 — Recovery_Model (CONDICIONAL a M5 + handoff v1-intel)
- Adicionar `av.Recovery_Model` ao SELECT das 2 queries (`helpers.py:1711`, `intelligence_kpis.py:1801`).
- **B2a** LOG em atraso de base em **SIMPLE** → banda info "LOG n/a (recovery SIMPLE)", NÃO contada. Precedente: modal T-Log por base (02/09) já usa `Recovery_Model` com a regra "SIMPLE nunca vermelho". Falso positivo puro (base que teve LOG backups e passou a SIMPLE fica "em atraso" para sempre). Só existe se M5 mostrar linhas SIMPLE; v1-intel confirma se o collector já as exclui.
- **B2b** LOG >24h com FULL fresco em FULL/BULK_LOGGED → **NÃO despromover** (FULL fresco não cobre point-in-time; invariante RPO R5). Apenas sub-rótulo "Cadeia LOG parada" dentro de actionable. Aí o tile pode passar a "Cadeia parada (DIFF/LOG)".
- Gates: testes contrato, `test_invariante_rpo` continua verde, tier checker (Std), reconciliação soma.

### Lote A3 → D7 — unificar thresholds do Overview (SCOPE PRÓPRIO, canonical)
- Não é portal-only (discordância do especialista, confirmada em canonical `:9647`): o card Overview conta FULL >48h / LOG >24h numa SP, o help diz 7d/8h, o registry diz 120/168 e 1/2.
- Decisão a tomar pelo owner: (i) SP passa a ler os thresholds do registry (DDL na SP → canonical + docs + v1-intel), ou (ii) só corrigir o help para descrever o que a SP faz hoje ("FULL >48h, LOG >24h"), ou (iii) Overview passa a consumir `delayed_*` do `collect_backup_status` (Python, zero DDL, mas Overview deixa de ser SP-driven).
- **Recomendação: (iii)** — mata a divergência na origem e evita DDL; (ii) como paliativo imediato se (iii) não couber agora.

### Lote C — collector V1 (SÓ se M7 der LOG Recuperados = 0 com Total > 0)
- Handoff a `watcherdb-v1-intel-specialist`: OUTER APPLY do `collect_backup_failures.py` (Fase 2) para jobs LOG.

### Lote D — deferido
- "Próximo esperado" real por base via `backup_pattern_analysis.next_expected` em hover/expandir na modal. Custo alto por linha; só com pedido explícito.

## 4. Propagação (regras 2/3/4 da sessão)
- DDL: nenhum em A/B/C. Só D7(i) tocaria canonical `INSTALACAO_COMPLETA_UNIFICADA.sql` + docs.
- Commit por lote (A, B1, B2 separados). CHANGELOG com tier (Std).
- V6: mesmos ficheiros existem na cópia V6 (`backup_delayed_classes.py`, `helpers.py`, portal); a cópia V6 já diverge nos thresholds (finding do council 01/09). Doc de handoff V6 no fecho do lote: o quê mudou, porquê, e que a V6 deve alinhar thresholds ANTES de portar B1 (senão o delta de crítico LOG é diferente).

## 5. Decisões pedidas ao owner
1. GO Lote A (recomendo: sim, hoje).
2. Correr M5/M6/M7 e devolver resultados.
3. GO Lote B1 após ver M6 (recomendo: sim, isolado).
4. Opção para D7: (i)/(ii)/(iii) — recomendo (iii), com (ii) como paliativo.
