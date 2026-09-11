# PROPAGAÇÃO V6 — drill "Acompanhar resume" do Always On (lote 2026-09-11)

> Para a AI do V6. **Verificar primeiro, assumir nunca.** O V6 não é superset do V3.4: segundo o
> v34-specialist, os drills irmãos de mirroring (`api/routers/queries/mirroring_diagnosis.py`) e de
> T-log (`tlog_diagnosis.py`) ainda **não** têm paridade no V6. Este drill é o 3.º item desse backlog,
> não um item isolado. Origem: `docs/context/AG_RESUME_DRILL_2026-09-11_apply.py` (script de aplicação
> com o código integral: router, JS, CSS, chaves i18n, testes).

## 0. Dois bugs a NÃO herdar (independentes do drill)

1. **Filas em KB comparadas com 1000 e rotuladas "1 GB"** na tabela por base do Always On
   (V3.4 `templates/watcherdb_portal.html` ~31559/31564/31622/31623). `sys.dm_hadr_database_replica_states`
   devolve KB; o aviso disparava a ~1 MB. No V3.4 passou a `window._AG_QUEUE_WARN_KB = 51200` (50 MB).
   Grep no V6: `Filas > 1GB`, `log_send_queue_size) > 1000`.
2. **Lag falso por `DATEDIFF(SECOND, last_commit_time, GETDATE())`** no painel LIVE (V3.4
   `api/routers/live_monitoring.py:784`, portal ~51364): mede tempo desde a última escrita, não atraso.
   Base ociosa fica "vermelha". Correcto: `last_commit_time(primária) − last_commit_time(secundária)`
   ou `secondary_lag_seconds` (2016+). No V3.4 este fica para lote próprio; o V6 que o verifique já.

## 1. Contrato do endpoint

`GET /api/queries/alwayson-resume-sample/{server_id}?ag=&db=` — read-only, sem gate admin (só o
middleware de autenticação, como mirroring/tlog). Regras:
- Validação: `ag`, `db` por regex `^[^\[\]'\";]{1,128}$`; `server_id` `^[A-Za-z0-9_.\-]{1,128}$`.
  Literais `N'...'` com aspas duplicadas; nunca identificador dinâmico. Timeout 5 s por query.
- **Corre na primária.** Se `server_id` for uma secundária, obtém a primária com
  `sys.dm_hadr_availability_group_states.primary_replica` (visível em qualquer nó) e faz UM salto.
  **Facto medido (SQLHDSPRD405):** numa secundária a `dm_hadr_database_replica_states` só devolve a
  linha local — não tentes ler a primária a partir das linhas remotas, não existem.
- **Facto medido (384/384 linhas da família AG_QUEUES):** na primária, as linhas remotas trazem
  `redo_queue_size`/`redo_rate` preenchidos para réplicas ligadas. O comentário "redo vem NULL na
  primária" que existe no código (`watcherdb_alwayson_check.py:545`) vale para `database_state_desc`.
  Fallback à secundária SÓ quando redo vier NULL com a réplica CONNECTED (máx. 2 saltos).
- `secondary_lag_seconds` só em 2016+: detectar via `sys.all_columns` e injectar a coluna no SELECT.
- Devolve **códigos**, não texto. Precedência (função `state_code`):
  `PRIMARY` (papel) → `SUSPENDED` (is_suspended) → `REVERTING` → `INITIALIZING` → `NOT_SYNC`
  (NOT SYNCHRONIZING) → `SYNCED` (SYNCHRONIZED) → em SYNCHRONIZING: `ASYNC_HEALTHY` se modo
  assíncrono e ambas as filas ≤ 64 KB, senão `SYNCING`. **Réplica assíncrona nunca fica SYNCHRONIZED.**
- Resposta: `{success, ag, db, server_id, sampled_on, hops[], server_now, primary, replicas[], defaults, notes[]}`;
  cada réplica: papel, ligação, modo, estados, suspensa+motivo, filas e rates em KB, timestamps,
  `lag_seconds`, `state_code`, `source` (primary | secondary_fallback).
- `defaults` = `{done_queue_kb: 64, done_samples: 3, stall_samples: 18, attention_queue_kb: 51200}`
  (constantes do módulo no V3.4; o owner decide se entram no registo de thresholds).

## 2. Cliente (o cálculo é todo no browser)

- Botão "Acompanhar" por base, nas **duas** tabelas do Always On (vista local e vista "do primário"),
  visível só quando `is_suspended` ou fila > 50 MB ou estado fora de SYNCHRONIZED/SYNCHRONIZING.
- Modal próprio (casca `.inv-modal`, topbar com contagem de amostras e "próxima amostra em 00:10"),
  polling 10 s com `setInterval` guardado no overlay e paragem quando o modal perde a classe `show`.
  Amostras em memória por chave `AG|base` (máx. 720 = 2 h); se a réplica-alvo mudar, recomeça.
- Réplica-alvo: a suspensa; senão a não-primária com maior `envio + redo`.
- Taxa = **declive por mínimos quadrados** das últimas 6 amostras (KB/s), nunca o `rate` da DMV
  (média móvel do motor; ignora a geração de log concorrente). ETA = fila / −declive, só com declive
  negativo. Progresso = `1 − fila / baseline` (baseline = maior fila vista desde a 1.ª amostra).
  Estagnação = 18 amostras (3 min) sem a fila descer 2%. Conclusão = 3 amostras seguidas em
  `SYNCED` (síncrono) ou `ASYNC_HEALTHY` (assíncrono).
- Gráfico: sparkline SVG existente (`createDiskSparklineSVG`), cor por token de severidade. Sem Canvas,
  sem Chart.js (CSP sem CDN).
- Tabela por réplica: papel, modo, ligação, estado (código traduzido), saúde, suspensa+motivo, filas em
  MB, atraso formatado com dias. Asterisco quando o valor veio por fallback da secundária.
- i18n: objecto `alwayson.resume.*` (52 chaves em pt-PT/en-US/es; pt-BR herda). Rejeitada a fórmula
  de "progresso" `100/(1+ETA)` e os textos com emojis em VARCHAR das queries originais do owner.

## 3. Testes a portar

`tests/unit/test_alwayson_resume_20260911.py` (14): precedência de `state_code` (suspensa vence filas a
zero; assíncrona drenada = ASYNC_HEALTHY, com fila = SYNCING); lag por `secondary_lag_seconds` e por
delta de commit; escaping e coluna de lag condicional na query; 400 para nomes inválidos; amostra na
primária com timeout 5 s; re-target de secundária via `primary_replica`; fallback preenche redo nulo;
404/409; portal com botão nas duas tabelas e limiar 51200; chaves i18n nos 3 locales.
