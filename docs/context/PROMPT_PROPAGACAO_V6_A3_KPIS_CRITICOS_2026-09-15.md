# PROPAGAÇÃO V6 — A3: mais sete condições críticas no aviso e no sino

> Para a AI do V6. **Verificar primeiro, assumir nunca.** Pressupõe o A2 já propagado
> (`PROMPT_PROPAGACAO_V6_A2_AVISOS_2026-09-14.md`): grep `_toastLastFired` e `critBellRecord`. Sem A2 no V6,
> este prompt fica sem efeito. Origem: `docs/context/A3_KPIS_CRITICOS_2026-09-15_apply.py` (código integral).
> Sem mudança de base de dados: não toca no canónico.

## Decisão de produto (owner, 15/09)

| Contador | Decisão |
|---|---|
| backup_status.failed_count, mirroring_status.unhealthy_count | avisa logo |
| cpu_critical, memory_critical, disk_latency.critical_count, tempdb_status.critical_count | só sustentado: 10 min (memória 5), histerese de 15 min |
| jobs_status | só Job_Type DBCC, Replication, AlwaysOn |
| lock_count, blocked_users | entram na família das sessões bloqueadas, valor = máximo das fontes |
| processes_alarm | entra na família do CPU, valor = máximo |
| deadlocks, error_log, service_status | não avisam |

## O que verificar no V6 antes de portar

1. **Defeito do detalhe.** Se `getDetail` ler `i.instance` com minúscula, o detalhe está vazio: o backend
   devolve `Instance`. No V3.4 afectava os sete avisos já ligados.
2. **Carimbo do instantâneo.** No V3.4 a resposta viva não traz carimbo, por isso a duração mede-se em
   tempo de relógio. Se o V6 trouxer carimbo por instantâneo, é melhor contar instantâneos distintos.
3. **Recolha de serviços.** Medir `MAX(Update_TS)` em `KPI_MSSQL_SERVICE_STATUS_STG` no ambiente do V6.
   A base partilhada está parada desde 13/05; o sinal `collector_stale` só faz sentido se a linha existir.

## Regras de comportamento (as que a prova em Node confirmou)

- Duração por relógio, com o relógio em localStorage (um F5 não reinicia a prova) e reinício quando
  passam mais de 15 min sem leitura fresca.
- Nos avisos com duração o valor anterior do texto é o último que disparou, não a leitura anterior.
- Com histerese, voltar a 0 só fecha o episódio depois de 15 min estável a 0.
- O detalhe passa por escape antes do innerHTML.
- A linha de serviços em baixo fica cinzenta, sem número, com "sem recolha desde dd/mm", só quando
  `collector_stale` é true; None (não medido) mantém o comportamento antigo.

## Testes a portar

`tests/unit/test_a3_kpis_criticos_20260915.py` (9, incluindo um de comportamento do backend com a consulta
simulada) e o ajuste de uma asserção em `test_a2_avisos_criticos_20260914.py`. A prova em Node do V3.4
correu 18 afirmações: duração, histerese, nova ocorrência, jobs, família sem sessão bloqueada, F5, buraco
de dados, stale, escape e badge.
