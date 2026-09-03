# PROPAGAÇÃO V6 — Inventário servers.json fonte única (wave 19-20/08/2026)

Para a AI do V6. Regra da casa: mudanças explicadas (regras + contratos), não só diff.
Fonte: `WATCHERDB_V3.3/docs/context/PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19.md` +
CHANGELOG V1 2.28.0 + `knowledge_base/architecture/cross_cutting/inventario_servers_json_fonte_unica.md`.

## O que o V6 HERDA de graça (via BD partilhada — nada a fazer, só saber)

A BD `WatcherDB_Intelligence` tem desde 19/08 o inventário canónico sincronizado do
`servers.json` do collector V1:
- `metadata.monitored_server` — 1 row/instância; `instance_id VARCHAR(64)`;
  **`is_active`** (presente na fonte) e **`enabled`** (flag do JSON) são coisas
  diferentes; `removed_at`; **sem password** (nunca haverá).
- `metadata.monitored_server_database` — catálogo de databases (PK `server_id, database_name`).
  **CONTRATO (veto v1-intel): é catálogo do que existe, NUNCA scope de coleta.**
- `metadata.server_sync_run` / `server_sync_audit` — auditoria completa; pergunta
  "porque desapareceu o servidor X?" responde-se com `SELECT * FROM server_sync_audit
  WHERE entity_key='X' ORDER BY logged_at DESC` (`changed_cols` por UPDATE).
- `KPI_MSSQL_INST_ENVS` e `metadata.server_config` (row base) continuam como projecções —
  os leitores actuais do V6 (`api/routers/servers_inventory.py` incluído) **não partem**.
  Mas o drift-check próprio do V6 contra `server_config` ficou redundante: a fonte com
  auditoria é `server_sync_run`/`monitored_server`.

## O que o V6 DEVE fazer (trabalho de propagação)

1. **Portal V6 a ler a BD** (equivalente do E6 V3.3): criar um `inventory_repo`
   (copiar `WATCHERDB_V3.3/services/inventory_repo.py` — é autónomo: 2 SELECTs,
   cache 60 s, `inventory_source db|file`, fallback ficheiro, `has_credentials`
   cruzado com o `config/servers.json` LOCAL do V6). Ligar os endpoints de
   servidores do V6 a este repo. Regra: o ficheiro local do V6 passa a ser **mirror
   de credenciais** (cifra própria do V6), não inventário.
2. **`servers_inventory.py` (drift-check)**: substituir a comparação própria por
   leitura de `server_sync_run` (última run, status, contadores) — ou remover.
3. **Se o V6 tiver collectors próprios** que leiam listas de servidores de ficheiros:
   migrar para `InventoryProvider` (V1) ou para SELECT à `monitored_server`
   (membership = `is_active=1 AND enabled=1`). Proibido: `Trusted_Connection` a
   monitorizados; `env_map` local (usar `ENV_ALIASES`/`environment` da BD).
4. **Números do painel**: universo configurado = `monitored_server is_active+enabled`;
   quem reporta = availability. Diferença ≠ 0 significa servidor cego — a superfície
   disso ("configurados sem coleta: N") tem GO no V3.3 (mini-wave "Verdade da
   Cobertura", 20/08) mas ainda NÃO está implementada: o V6 **espera a propagação**
   dessa mini-wave em vez de inventar comportamento próprio.

## Adenda 21/08 — parecer da sessão V6 CONFIRMADO (não copiar o buraco)

O parecer que a sessão V6 emitiu está CERTO e foi verificado na fonte V3.3 a 21/08:
5 itens do plano ficaram por fazer no V3.3 (boot `SQLServerMonitoring` ainda no
`sql_servers.json` de 95/Excel-2025-11, alwayson fallback heurístico, POST
/api/config/sql-servers vivo, hardcoded, sombra nunca escrita). Consequências para o V6:
- **Não seguir o V3.3 à letra nestes 5 pontos** — nos equivalentes V6, ligar
  DIRECTO ao repo/BD (`metadata.monitored_server`), sem fallback a `sql_servers.json`.
- O V3.3 fecha esta dívida como **E6c** (1.º item da mini-wave "Verdade da
  Cobertura"; âmbito detalhado no prompt dessa sessão e no bloco CORRECÇÃO 21/08
  do PLANO_SERVERS_JSON). Se o V6 precisar de paridade, esperar o fecho de E6c.
- Lição de processo (vale para o V6): "fecho de wave" declara-se com grep de
  leitores remanescentes do ficheiro legado, não com a checklist do plano — o
  ficheiro só se arquiva quando o grep devolve zero consumidores.

## Adenda 20/08 (pós-fecho da wave)

- **Runbook de operação** criado a pedido do owner:
  `WATCHERDB_V3.3/docs/guides/RUNBOOK_ADICIONAR_REMOVER_SERVIDOR.md` (adicionar /
  pausar / remover servidor editando só o canónico; diagnóstico rápido via audit).
  O V6 deve adaptá-lo: o passo 4 (sidebar) é específico do V3.3 — a versão V6
  referencia o mirror local de creds do V6 e o restart do serviço V6.
- **Padrão de provisão de credenciais** (usado para pôr o OATXP01 na sidebar V3.3,
  validado em produção): ler a password decifrada do canónico V1 (`ServerManager`),
  re-cifrar com a cifra do próprio tier, append ao ficheiro local com backup +
  escrita atómica. ARMADILHA real apanhada à primeira execução: o V3.3 tem um
  FICHEIRO `watcherdb_intelligence.py` (entry-point) que faz sombra ao PACOTE do V1,
  e ambos os projectos têm pacote `services` — o script tem de isolar `sys.path`
  por fase (fase A só V1 → ler; purge de sys.modules; fase B só o próprio tier →
  re-cifrar). Se o V6 tiver colisões de nomes análogas, mesmo tratamento.
- **OATXP01 (SQL 2005)** está agora TAMBÉM na sidebar do V3.3 (63 = 63 em todas as
  superfícies). Suporte parcial por versão continua: availability funciona,
  drill-downs avançados podem vir vazios — comportamento esperado, não é bug.

## Regras/contratos que a AI do V6 tem de respeitar

- `databases: []` explícito ≡ ausente na sync (nunca desactiva DBs).
- Desactivação de servidor: só por ausência da run; guarda de frota 20 %; nunca por idade.
- Suporte por versão: pleno 2012+, parcial 2005/2008 (availability funciona — uptime via
  tempdb `create_date`; NUNCA `sqlserver_start_time`/`CONNECTIONPROPERTY` sem version-gate).
- Porta dinâmica: `WDB_INSTANCE_TCP_PORT` + auto-heal (falha na aprendida → Browser → re-aprende).
- OATXP01 (SQL 2005) e SQLHDSPRD214 voltaram ao universo (63); PRD502 e TST014 fora por decisão.
- `sql_servers.json` está ARQUIVADO — nenhum código novo pode lê-lo.

## Verificação de fecho no V6

`/api/...(servers do V6)` devolve o mesmo conjunto que
`SELECT instance_id FROM metadata.monitored_server WHERE is_active=1 AND enabled=1`;
grep no repo V6: zero leituras de `sql_servers.json` e zero `Trusted_Connection` para
monitorizados; browser test da lista de servidores.
