# PROMPT PROPAGACAO V6 — KPI Mirror: triagem + tendencia + drill (2026-09-01)

Colar numa sessao V6, DEPOIS da propagacao de 31/08
(PROMPT_PROPAGACAO_V6_MIRRORING_2026-08-31.md — pre-requisito). Portal V6 NAO
e' superset: grep anchors primeiro; sem anchor = "nao aplicavel", reportar.

## O que mudou em V3.3 (por consenso: v1-intel GO A/B + VETO C)

1. **Triagem RESUME-vs-REBUILD** (heuristica: fila_kb > data_mb*1024 =>
   REBUILD; validada ao vivo — fila 101 GB vs dados 6,8 GB). Duas superficies:
   modal (JOIN normalizado LTRIM/RTRIM/UPPER ao DATAFILES agregado, campos
   Data_MB/Data_TS) e drill live (mirroring_diagnosis.py, campo raw.triage).
   So em SUSPENDED/DISCONNECTED; fail-open sem Data_MB; numeros por extenso.
2. **WDB_MIRRORING_QUEUE_HIST** (BD partilhada — o V6 herda a tabela): serie
   7d das filas, escrita pelo collector V1. "Suspenso desde" honesto ("ha
   pelo menos" quando o inicio saiu da retencao) + taxa MB/h (>=2 pontos,
   senao "a monitorizar"). RETENCAO E' LOCAL AO COLLECTOR (nao esta na
   usp_purge_kpi_history — desvio aceite pelo v1-intel; nao "corrigir" isso).
3. **Drill de diagnostico**: volumes tambem no PRINCIPAL (alarme critico <15%
   livre no volume do LOG), linha "Dados vs fila", next step abre com a
   triagem.

## Contratos para a AI de la'

- Filas e Data_MB: NULL = sem dado, NUNCA 0 (`|| 0` proibido nestes campos).
- Verificacao bloqueante ANTES de replicar o JOIN do veredito no V6: confirmar
  que o objecto DATAFILES que o V6 le e' VIEW viva (type_desc + MAX(Update_TS)
  — o v1-intel apanhou que o canonical nao regista DATAFILES nas listas de
  alias; na BD viva e' VIEW por migracao fora-de-banda). Se no V6 for tabela
  morta, o veredito daria numero errado com cara de real — nao publicar.
- Datas honestas: nunca apresentar o limite da retencao como data de inicio.
- Canonical V6: sincronizar SECAO 35 (WDB_MIRRORING_QUEUE_HIST) com o commit
  V1 desta wave (regra 2 do owner).

## Adenda 269a0c6 (retoques de legibilidade — levar juntos)

Se o V6 replicar o drill, incluir os 3 retoques do commit `269a0c6`:
1. CSS `.stat-card .value { overflow-wrap:anywhere; word-break:break-word; }`
   — valores longos (DATABASE_MIRRORING) quebram dentro do card.
2. `.diag-next` com `white-space: pre-line` + `\n` entre os itens numerados do
   next_step no backend — passos em linhas proprias.
3. Side row "Dados vs fila" renomeada "Base da triagem" com os dois custos por
   extenso ("copiar a base (re-seed) = X GB · drenar a fila de log (RESUME) =
   Y GB — fila e' Nx a base") — regra rotulos-dizem-o-que-o-valor-e.

## Passos

1. Pre-requisito: propagacao de 31/08 aplicada (colunas Witness/filas no V6).
2. grep no V6: "mirroring-diagnosis" / "Data_MB" / "backup-delayed"... anchors
   do modal e drill de mirroring. Sem modal/drill de mirroring no V6 =
   reportar "nao aplicavel no portal" (a BD ja' da' tudo).
3. Replicar por anchors (nao copiar cego); validacao = caso vivo SharePoint
   (triagem REBUILD com numeros) enquanto o incidente durar.
