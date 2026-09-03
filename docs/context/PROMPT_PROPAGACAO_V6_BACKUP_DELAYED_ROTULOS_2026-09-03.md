# PROMPT DE PROPAGAÇÃO → V6 — Backup Delayed: rótulos honestos (Lote A, 2026-09-03)

Para a AI da V6. Origem: WatcherDB V3.4 (Standard), revisão do owner de 03/09
sobre o painel Backups; plano completo em
`docs/context/PLANO_BACKUP_DELAYED_MELHORIAS_2026-09-03.md` (V3.4).

## O que mudou na V3.4 e porquê

1. **Modal `backup-delayed`, bloco de métricas por linha**
   (`templates/watcherdb_portal.html`, ramo `kpiType === 'backup-delayed'`,
   ~linha 39461). O campo `Expected_Backup_Date` vem do backend como
   `Last_Backup_Date + threshold de aviso` (`backup_delayed_classes.py`,
   `classify_delayed`, linha ~168) — é o instante em que a linha passou a
   contar, por construção **sempre no passado**. O rótulo "Esperado:" fazia o
   DBA ler "próximo backup previsto". Novo render:
   `Limite de aviso: dd/mm hh:mm (excedido há Nh)` — o `Nh` é o antigo
   `Gap_Hours_Past_Threshold`, e a linha separada "Gap: Nh atrasado vs
   expected" foi removida (redundante). Chaves i18n novas, bloco `kpi_modal`,
   nos 3 locales (`static/i18n/{pt,en,es}.json`):
   - `delayed_warning_limit`: "Limite de aviso" / "Warning limit" / "Limite de aviso"
   - `delayed_exceeded_by`: "excedido há {n}h" / "exceeded {n}h ago" / "excedido hace {n}h"
   Uso: `t('kpi_modal.delayed_warning_limit')` e
   `t('kpi_modal.delayed_exceeded_by', { n: gapH })`, ambos com fallback PT
   inline (padrão do ficheiro).

2. **Banda `diff_schedule_stopped` renomeada** de "Agendamento DIFF parado"
   para **"Cadeia DIFF parada (FULL a cobrir)"** em 5 sítios: linha do tile
   (`_advRow(... 'CLASS:diff_schedule_stopped')`, também o título da modal
   passado como 6.º argumento), `dcMap` do chip de classe, e as 2 linhas de
   reconciliação do cabeçalho da modal (`_dcCount.diff_schedule_stopped` e
   `_dc.diff_schedule_stopped`). Razão: a banda é subproduto do perdão
   chain-reset (R2 do council 01/09) — só existe DIFF "parado" quando há um
   FULL fresco a cobri-lo; FULL/LOG parados JÁ contam em atraso. O nome antigo
   prometia uma detecção de "agendamento" que os dados de backupset não
   suportam (essa vive nos KPIs de Agent Jobs: jobs-overdue /
   jobs-no-schedule / jobs_disabled).

3. **Help `KPI_DOCUMENTATION['backup-delayed']`**: +2 linhas em `howItWorks`
   (pt inline; en/es em `i18n.en.howItWorks` / `i18n.es.howItWorks`) a
   explicar o "Limite de aviso" e o porquê da banda ser só DIFF.

4. **Council**: `watcherdb-v33-specialist` → `watcherdb-v34-specialist`
   (identidade V3.4). Não afecta a V6.

## O que NÃO mudou (não portar como se tivesse)
- Zero backend, zero números: `classify_delayed`, thresholds, contagens e
  payload são os mesmos.
- Lotes B1 (horas fraccionárias — muda LOG crítico), B2 (`Recovery_Model`),
  D7 (thresholds do Overview SP 48/24h vs registry) **aguardam medições e GO
  do owner** na V3.4. Não portar ainda.

## Aviso para a V6
O council de 01/09 registou que a cópia V6 de `backup_delayed_classes.py` /
thresholds **já diverge** da V3.x. Antes de portar o Lote B1 (quando vier),
alinhar thresholds primeiro — senão o delta de LOG crítico será diferente e
a tabela antes/depois não é comparável. Este Lote A (só rótulos) pode ser
portado sem essa dependência.

## Checklist de porte
- [ ] 2 chaves × 3 locales em `kpi_modal`
- [ ] render da linha "Limite de aviso" + remover linha "Gap"
- [ ] 5 renomes da banda DIFF (tile, título modal, chip, 2 reconciliações)
- [ ] help pt/en/es
- [ ] gate i18n + browser nos 2 temas
