# Runbook — Missing Indexes

## Passo 1: Validar priority_score
Priority = avg_total_user_cost * avg_user_impact * (user_seeks + user_scans).
Focar apenas em scores > 100k. Scores < 10k raramente compensam o overhead
de escrita do novo indice.

## Passo 2: Verificar sobreposicao com indices existentes
Antes de criar, executar:
  EXEC sp_helpindex '<tabela>'
Se ja existe indice parcialmente util, considerar INCLUDE de colunas em
vez de criar novo.

## Passo 3: Testar o indice em TST
CREATE INDEX com ONLINE=ON (Enterprise Edition) em TST. Medir:
- Tempo de criacao
- Espaco em disco ocupado
- Impacto em INSERTs/UPDATEs ja a executar

## Passo 4: Submeter para aprovacao em PRD
NUNCA criar indice directamente em PRD sem aprovacao. Abrir ticket/CR com:
- Script CREATE INDEX (do L3 do modal)
- Output de testes em TST (tempo antes/depois)
- Janela de manutencao proposta (fora de pico)

## Passo 5: Registar em action_history
Apos aplicacao, chamar POST /api/v1/performance/action-history com
outcome_before/outcome_after para feedback ao sistema e futura referencia.

## Referencias
- sys.dm_db_missing_index_details: o que o optimizer gostaria de ter
- sys.dm_db_missing_index_group_stats: impacto acumulado
- Recomendacoes sao hints, nao ordens — validar sempre manualmente
