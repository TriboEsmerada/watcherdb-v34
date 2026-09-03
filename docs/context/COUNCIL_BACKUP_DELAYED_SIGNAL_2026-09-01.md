# COUNCIL — Backup Delayed signal-vs-noise (2026-09-01)

Convocado pelo owner. 4 vozes (v33-specialist, customer-success-persona,
challenger, v1-intel-specialist) + 4 medições pré-decisão na BD viva (M1-M4,
propostas pelo challenger e corridas antes do voto). Decisão final: OWNER.

## Medições que arbitraram o debate

- **M1 (chain-reset)**: dos DIFF com FULL mais fresco, **88% têm DIFF ≤3 dias**
  (transitório — cadeia recomeça por rotina) e 33 têm DIFF >7d (schedules
  realmente partidos, classe TAON). → o filtro é maioritariamente correcto,
  MAS o predicado cru cegava os 33: a semântica certa é a do precedente
  f15bfb8 (18/08): *perdão limitado pela frescura do FULL*, nunca perpétuo.
- **M2 (system DBs nós AG)**: 47/103 tiveram backup ≤14d (rotina EXISTE,
  cadência semanal vs threshold de 5d — mismatch, não ausência); 51 em
  14-60d; 5 >60d. → tratamento condicional, não filtro cego.
- **M3 (fósseis)**: **17/21 têm o FULL da mesma base também crítico** — são
  tipos-extra de bases já alarmadas → o dedupe absorve-os; cap de idade
  morre (era o bug "limpar por velhice" de 21/08 ao contrário).
- **M4 (dedupe FIND-101)**: 461 linhas → 362 bases (-21%). Necessário mas
  insuficiente sozinho.

## Convergências (unânimes)

1. O diagnóstico é real: ~70% do número executivo não pede acção operacional.
2. **Nada desaparece** — tudo o que sai do número crítico fica contado,
   rotulado e navegável (persona: banner de reconciliação cujas parcelas
   somam ao total antigo; challenger: rasto auditável da reversão parcial
   de 06/08).
3. Fix vive no **consumidor Python** (helpers.py) — zero DDL, zero infra
   partilhada (v1-intel GO; v33 confirma ficheiro não partilhado).
4. Dedupe por base PRIMEIRO na sequência (doutrina R+11.2), tudo numa wave só.
5. `requires_approval` + tabela antes/depois por classe + teste de contrato +
   CHANGELOG explícito + propagação V6 no MESMO lote (a cópia V6 já diverge
   nos thresholds — finding registado).

## Recomendação sintetizada (por classe)

**R1 — Dedupe (FIND-101)**: número executivo passa a contar BASES com
protecção degradada (pior severidade da base); breakdown por tipo no modal.

**R2 — Chain-reset DIFF**: reclassificar com semântica f15bfb8 (DIFF não
conta enquanto o FULL da base está fresco; se o FULL envelhecer, volta a
contar) — rótulo persona: "Cadeia reiniciada — FULL mais recente já cobre".
Os ~33 schedules DIFF parados (>7d) ganham banda própria visível
"agendamento DIFF parado" (aviso, contado). CONDIÇÃO TÉCNICA v1-intel: a
correlação FULL↔DIFF nas linhas AG_CONSOLIDATED usa chave **(AgName,
Database)** — nunca (Instance, Database): o Instance da view é o
representante POR TIPO e diverge entre tipos pós-failover. Mapa AgName via
segunda query a ALWAYSON_STATUS_STG (padrão já em helpers.py:895-930).

**R3 — System DBs de nós AG**: NÃO filtrar (unânime: exposição real
possível). Descoberta do v1-intel: **a superfície certa JÁ EXISTE** —
`vw_KPI_MSSQL_BACKUPS_AG_SYSTEM_GAP` + kpi_type `backup-ag-system-gap`
(Wave M.4.a, 2026-05-29), subaproveitada. Rotear o cohort para lá com
contador visível no executivo ("N nós sem rotina de system DBs"), rótulo
"Sem backup próprio — política por-nó do AG" e runbook de escalamento
próprio (persona: o DBA às 3am não pode escalar ao dono errado). DBA_*/
TLS_* ficam FORA da classe system (challenger: são user DBs). Confirmar a
lista com SELECT DISTINCT do cohort no dia do ship (v1-intel).

**R4 — Fósseis: classe MORTA como regra autónoma** — absorvidos por R1
(17/21) e R2-banda (restantes). Sem cap de idade.

**R5 — Guard-rails de ship**: banner de reconciliação in-product; drilldowns
das classes preservados; invariante testável "nenhuma base com restore
point mais velho que o critical de FULL sem alarme em superfície nenhuma";
coerência aplicada nos DOIS sítios (helpers.py + intelligence_kpis.py — o
bug de 31/08 não se repete); medição pós-30d: zero incidentes "backup
parado descoberto fora do painel" (classe 30/07).

## Impacto estimado no executivo
387-461 linhas → ~106 accionáveis + banda "DIFF parado" (~33) + contador
system-DBs (visível) — com todas as parcelas navegáveis.

## Divergências registadas (resolvidas pelos dados)
- Challenger defendia que os 157 eram schedules partidos → M1 desmentiu para
  88% e confirmou para 33 → R2 acomoda ambos.
- Proposta original filtrava system DBs → 3 vozes contra + M2 → R3.
- Proposta original tinha cap de fósseis → challenger + M3 → R4.

## Estado
ANÁLISE COMPLETA — implementação AGUARDA GO do owner. Owner da implementação:
v33-specialist (handoff dele); gates: sql-deep-reviewer (semântica de restore
em R2), tier checker, browser test, propagação V6 no lote.
