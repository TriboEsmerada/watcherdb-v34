# PROMPT DE SESSÃO — Mini-wave "Verdade da Cobertura" (pós-wave servers.json)

GO do owner: 2026-08-20 ("siga", após o fecho da wave servers.json a 100 %).
Contexto herdado: `PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19.md` (fechado) +
`knowledge_base/architecture/cross_cutting/inventario_servers_json_fonte_unica.md` +
CONTEXT.md entradas 19-20/08. Correr `/recall cobertura silencio verde` antes de começar.

## Motivação (episódio real 20/08)

O owner olhou para "SERVIDORES (62) · Online 61 · Offline 0" e não conseguiu saber
porquê. A resposta existia (2 servidores configurados sem coleta) mas só no log
interno (`usp_check_availability_coverage_gap`, decisão "zero superfície" de 05/08).
O silêncio voltou a ler-se como saúde — o padrão que o produto anda a eliminar.

## Âmbito (4 peças, por ordem)

### E6c — PRIMEIRO: matar o `sql_servers.json` no V3.3 (dívida da wave, parecer V6 21/08)

A sessão de propagação V6 verificou na fonte que 5 itens do plano da wave ficaram
por fazer no V3.3 (detalhe: bloco CORRECÇÃO 21/08 no PLANO_SERVERS_JSON). Fechar
ANTES das peças novas — é a mesma doença que a wave tratou, viva no realtime:

1. Boot `SQLServerMonitoring` (`watcherdb_main.py:107,172-188`) → `inventory_repo`
   (hoje abre `config/sql_servers.json`: 95 servidores do Excel 2025-11 a alimentar
   monitor_all/alertas críticos/Space Analysis/tempo real — 32 fantasmas + OATXP01 ausente).
   Atenção ao shape esperado por `SQLServerMonitoring` e aos consumidores de
   `app.state.sql_servers_config` (`:1909,2262,2297,2430`).
2. `alwayson.py:756-885` — fallback de resolução de AG passa do ficheiro para os
   campos `has_alwayson/ag_name/ag_listener` de `metadata.monitored_server` (via repo).
3. `POST /api/config/sql-servers` + GET (`watcherdb/api/routers/config.py:25-66`) —
   descontinuar (410 com mensagem "inventário é o servers.json canónico do V1");
   parecer `v33-feature-matrix-checker` antes (Std não edita inventário).
4. Listas hardcoded de 3 instâncias (`watcherdb_main.py:4450-4451,4690-4906`) e
   endpoint Excel → repo.
5. Job de sombra 7 dias: DISPENSAR com justificação escrita no plano (diff E4c
   0-diffs + sync de 10 min cobrem o objectivo) — não escrever código novo.
6. SÓ NO FIM: arquivar `config/sql_servers.json` + backups V3.3 (`_archive/`),
   grep de regressão (zero leitores), Restart + validação em produção.

Gate: browser test dos ecrãs realtime/space pós-restart; os fantasmas desaparecem
do monitor_all (esperado: 63 alvos, não 95).

### B — Superfície "configurados sem coleta" (REVERTE decisão owner 05/08 — confirmar no arranque)
- Cartão Disponibilidade ganha linha "Configurados sem coleta: N" (cinzento N/D-style,
  nunca vermelho — ausência ≠ avaria) com drill-down (instância, desde quando, último erro).
- Fonte: `metadata.monitored_server (is_active=1 AND enabled=1)` LEFT JOIN availability
  ACTIVE — 1 SELECT; a sproc coverage_gap continua como detector horário no log.
- Backend em `intelligence_kpis`/helpers + modal; i18n PT/EN/ES; teste de contrato.

### Nível 2 — Versão capturada + "suporte parcial"
- `metadata.monitored_server` ganha `sql_version VARCHAR(32)` + `sql_version_seen_at`
  (**DDL novo → SECÇÃO 34 do canonical + standalone + handoff v1-intel — regra 2**).
- Escrita: `collect_inst_availability` já devolve `Version` — o sync/um adapter grava.
- Portal: badge "Suporte parcial (SQL 2005)" quando versão < 2012 (piso pleno);
  tooltip explica que availability funciona e KPIs avançados não. Caso vivo: OATXP01.
- Doc: matriz de compatibilidade por família de KPI (docs/guides ou FEATURE_MATRIX anexo).

### C — Quarentena proposta (nunca automática)
- Tarefa diária (ou passo na sync full das 03h) marca `collection_status`
  (`NEVER_COLLECTED` / `UNREACHABLE_<n>d`) em `monitored_server`;
  &gt;30 d com erro estável → log `[INVENTORY_QUARANTINE_SUGGESTED]` + linha no
  relatório; **a decisão enabled:false é sempre do owner** (anti-acidente).

## Regras/gates

- Consultar v1-intel ANTES do DDL (SECÇÃO 34 alterada) e v33/feature-matrix para o
  badge (Std). Reviews bounded (≤6 tool calls) — os agentes sem limite bloquearam 2× a 19/08.
- Zero vermelho por ausência; paleta N/D cinzenta (contrato "verde só com leitura OK").
- Commits owner; blocos SSMS para DDL; Restart-Service após edits Python (class cache).
- Fecho: 5 surfaces (wave-close) + linha SOLUCOES.md + propagação V6 explicada.

## Pendentes herdados a fechar nesta sessão (2 min)

- FECHADOS a 20/08 (não repetir): DELETE dos 21 órfãos (verificação pós = 0 rows);
  OATXP01 provisionado no V3.3 → sidebar 63 = painel 63; runbook
  `docs/guides/RUNBOOK_ADICIONAR_REMOVER_SERVIDOR.md` commitado (9fe3c38).
- ÚNICO pendente: verificar a 1.ª full-run 03h da sync (@Purge):
  `SELECT TOP 3 * FROM metadata.server_sync_run ORDER BY run_id DESC;`
  — esperado run ~03:0x SUCCESS, 63 processados, purge sem sustos.
  (Nota: runs com colunas NULL = interrompidas por restart; benigno, guard trata.)
- A propagação V6 corre em sessão PRÓPRIA no repo V6 com
  `PROMPT_PROPAGACAO_V6_INVENTARIO_SERVERS_JSON_2026-08-20.md` — não é trabalho desta.
