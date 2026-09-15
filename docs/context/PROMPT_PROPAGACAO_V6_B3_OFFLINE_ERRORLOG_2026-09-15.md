# PROPAGAÇÃO V6 — ecrã de servidor offline: errorlog antes da falha (B3)

> Para a AI do V6. **Verificar primeiro, assumir nunca.** Origem: `docs/context/B3_OFFLINE_ERRORLOG_2026-09-15_apply.py`
> (código integral e testes). Sem mudança de base de dados. **Depende de** o V6 ler a mesma Intelligence com o
> recolhedor B1b (Log_Type classificado) e o arquivo B2a-1 (eventos na HIST): sem isso o bloco nasce quase sempre vazio.

## O que faltava (verificar se o V6 tem o mesmo buraco)

Quando o ping falha, o ecrã de visão geral mostrava só "offline" e o diagnóstico de rede. O errorlog das horas
anteriores já está na Intelligence e responde com o alvo mudo. Grep no V6: o cartão do precheck
(`overview.server_offline_title`) e se chama algum endpoint de errorlog antes de `return`.

## Endpoint

`GET /api/intelligence-kpis/errorlog/recent-signals?instance=&hours=2|6`
- Sessão obrigatória (`_require_auth`) **antes** de validar a entrada. Instância por regex; horas só 2 ou 6.
- Identidade na BD: sql_monitoring pelo pool da Intelligence, só SELECT com parâmetros (`DECLARE @inst VARCHAR(128) = ?`,
  para não converter o parâmetro nvarchar contra a coluna varchar). `run_in_executor` no executor do módulo.
- Âncora: `First_Event_Time` do evento offline activo; sem evento, agora. Janela: âncora menos 2 h (ou 6 h) até agora.
- HIST e STG juntas, deduplicadas por `Log_Date` e `CHECKSUM(Log_Text)` (o arquivo copia eventos da STG para a HIST).
- Até 15 linhas de Critical, Error, AvailabilityGroup, Lifecycle e tipo vazio; Security só em contagem com o minuto de
  pico; Repetitive e Info só em contagem.
- Devolve sempre o último ciclo do recolhedor (`WDB_COLLECTION_SCHEDULE_META`, global) e a última linha recebida da
  instância (7 dias), e `empty_reason`: `collector_stale` (ciclo com mais de 15 min), `instance_never`, `window_quiet`.
- Medido no V3.4: 0,05 a 0,2 s por instância, incluindo SQLHDSPRD214 (6,4 milhões de linhas no log).

## Ecrã (pareceres da persona DBA e do frontend)

- Título "Errorlog antes da falha" e distintivo "Sinal, não causa" em cor neutra, nunca vermelho.
- Lista vazia sempre explicada pelos 3 motivos; nunca "sem erros".
- `createFetchWithAbort` com 8 s (no precheck do V3.4 não existe `fetchWithTimeout`: confirmar o escopo no V6).
- Contentor `role="status" aria-live="polite"`; cada linha em `<details>` nativo; botão real para alargar a 6 h.
- O caminho offline não grava na cache da aba. Chaves `overview.offline_errorlog_*` (23 em pt/en/es, 11 em pt-BR).

## Fora deste lote (não portar como feito)

B3b: o mesmo bloco no banner de diagnóstico (host responde, SQL mudo), que passa pela cache da aba. Marca de água
por instância no recolhedor: B2a-2.

## Testes a portar

`tests/unit/test_b3_offline_errorlog_20260915.py` (6: resposta montada com linhas simuladas, os 3 motivos de vazio,
consultas só de leitura e deduplicadas, sessão antes da validação, ligação no precheck, chaves nos idiomas).
