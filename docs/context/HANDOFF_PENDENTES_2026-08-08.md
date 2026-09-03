# HANDOFF — o que falta implementar (sessão de 08/08 em diante)

Para a sessão seguinte, V3.3 e V6. Origem: ciclo de 03–07/08.
Escrito como **regras e contratos**, não como lista de diffs — âncoras vão
como **strings de pesquisa**, nunca números de linha (o portal V6 tem ~50k
linhas e os números movem-se a cada commit).

---

## 0. LER PRIMEIRO — as regras que ficam deste ciclo

Estas não são história; são o contrato com que o resto do documento se lê.

**R1 — Ausência de dado não é ausência de problema.** Um cartão só fica verde
quando a leitura teve **sucesso** e o resultado foi zero. Leitura falhada mostra
`N/D` em cinzento neutro. No V6 o cinzento é `var(--color-text-disabled)`, que
os cartões irmãos já usam — **não** o `#6b7280`, que só existe hardcoded no
caminho de refresh manual.

**R2 — O ambiente vem da `KPI_MSSQL_INST_ENVS`, nunca do nome da instância.**
`LIKE '%PRD%'` classifica mal e em silêncio. Medição real: o LIKE dava
37/14/7 + 3 `Undefined`; a `INST_ENVS` dá 40/15/6. Excepção: só se aplica onde
a chave é `Instance`. Onde a chave é `Hostname` ou `Server_Name`, um JOIN cego
falha em silêncio nas instâncias nomeadas (ver §5).

**R3 — Cartão e drill-down são par inseparável.** Se o cartão e a modal que ele
abre calculam a mesma dimensão por caminhos diferentes, corrigir um só faz o
produto contradizer-se no mesmo ecrã. Procurar sempre o par antes de aplicar.

**R4 — O lado vazio da réplica AlwaysOn é NORMAL.** O primário preenche `Pri_*`
e deixa `Sec_*` vazio; o secundário faz o inverso. Qualquer filtro de "não
saudável" tem de incluir `<> ''` além do `IS NOT NULL`. **Sem o `<> ''` o
produto reporta a frota inteira como não saudável.**

**R5 — Consultar o specialist ANTES de aplicar**, com perguntas concretas e
pedido de veredicto explícito. Neste ciclo os pareceres apanharam duas premissas
erradas que não teriam sido descobertas de outra forma: o token de cinzento (R1)
e a existência de uma segunda camada de i18n no V6 (`nytLocalize` + `NYT_TR`,
que faz substituição de substring sobre o HTML já renderizado — o `_kpiT` é
no-op, mas a tradução acontece na mesma).

---

## 1. Estado no fecho

| Repo | Branch | HEAD | Notas |
|---|---|---|---|
| V3.3 (monorepo) | `wave-b-indexacao-dmv` | `88afb29` | lote 07/08 em `9029a42` |
| V6 (git próprio, sem remote) | `wave-propagacao-v33-20260807` | `dd9d232` | 3 commits do lote + `db_by_env` |

O serviço V6 (porta 8660) está a correr com este código, validado ao vivo:
cartão de ambientes 40/15/6 = 61 linhas na modal; `db_by_env` 786/505/167 = 1458
sem bucket `Undefined`; drill-down AlwaysOn vazio (correcto com frota saudável)
e sem consumir a coluna crua.

Artifact de progresso actualizado (mesmo URL, separador Git com os 14 commits V6).

---

## 2. Browser test — bloqueia declarar o lote shipped

Nada disto foi visto em ecrã. É rápido e é o único sítio onde se apanha o que a
validação por API não vê.

- Servidor **sem dados recolhidos** → cartões de Backup e Backup Gaps em `N/D`
  cinzento, nunca verde. Confirmar que o `N/D` não se confunde com um zero.
- Cartão de **Serviços** com leitura falhada → cinzento, **não vermelho**
  (era o defeito que o specialist apanhou).
- Cartão **Por Ambiente** → conta instâncias, título sem "(Críticos)", clicar
  filtra o relatório.
- Mudar idioma para **EN** → o card diz "By Environment", sem português pelo
  meio (havia leak antes deste lote).
- Modal **AlwaysOn** → com frota saudável vem **vazio, e isso é o correcto**.
  Só é validável a sério quando houver uma base fora de estado.

---

## 3. DDL do `Problem_Reason` — execução do owner, tudo o resto pronto

**As quatro perguntas bloqueantes estão respondidas:**

1. Não interage com o swap BLUE/GREEN — o AlwaysOn Status não participa dele.
   As tabelas `_STG_BLUE`/`_STG_GREEN` existem mas estão órfãs.
2. Ninguém depende do texto exacto — todos os consumidores testam presença.
3. Impacto de escrita desprezável (~405 linhas/ciclo).
4. **Não há escritor a partir**: a lista de colunas do colector é explícita e
   não a inclui, não há trigger, e a única escrita SQL é um backfill de
   29/12/2025. A coluna é física (`is_computed = 0`, confirmado na BD viva).

**Consequência apurada:** os valores estão **congelados** há mais de sete meses.
O DDL não corrige apenas a lógica — torna a coluna viva.

Script: `WATCHERDB INTELLIGENCE V1/database/FIX_ALWAYSON_PROBLEM_REASON_LOGIC.sql`,
secção 2. **Enviar antes o aviso** já escrito em
`docs/context/AVISO_V6_DDL_PROBLEM_REASON_2026-08-07.md` — o
`_tool_failover_history` do assistente de IA do V6 usa a presença da coluna como
proxy de failover, e os alarmes vão cair a pique. Isso é a correcção, não uma
regressão, mas sem aviso alguém gasta uma sessão a investigar um bug inexistente.

Causa-raiz para quem lá for: `scripts/collectors/collect_alwayson_status.py` faz
`fillna("")` e converte o `NULL` legítimo do lado sem role numa string vazia.

---

## 4. Banner de diagnóstico de rede (U3) — decisão do owner primeiro

**Ausente no V6** — confirmado por grep: `run_diagnostics`, `diag_checks_failed`,
`diag_perspective` dão todos zero. Existe no V3.3.

Não foi construído de propósito: é **feature nova**, não propagação, e tem uma
classificação por resolver. O diagnóstico descritivo (mostra estado e contexto)
é Std; a camada seguinte — emitir o comando de remediação que o DBA deve correr
— **não foi implementada e a classificação Std/Pro está por decidir**. Não
implementar essa camada sem a decisão.

Duas regras de honestidade que o banner do V3.3 respeita e que o V6 tem de
manter se for construído:

1. Distinguir "host responde mas SQL está mudo" de "host inalcançável" — são
   diagnósticos diferentes e levam a acções diferentes (serviço vs rede).
2. **Nomear a perspectiva.** O banner termina sempre com o aviso de que o
   diagnóstico é *do ponto de vista do colector*. Sem isto o produto acusa um
   servidor saudável de estar em baixo, e um DBA que abra um incidente com base
   numa acusação falsa não volta a confiar no produto.

Chaves i18n (V3.3, `overview.*`): `run_diagnostics`, `diag_checks_failed`,
`diag_host_up`, `diag_sql_mute`, `diag_host_unreachable`, `diag_no_event`,
`diag_which`, `diag_perspective`. **No V6 não bastam os ficheiros de locale** —
ver R5: a tradução real passa pela tabela `NYT_TR`.

---

## 5. Dois blocos `LIKE` que exigem desenho próprio

Ficaram por corrigir **deliberadamente**. Pesquisar `LIKE '%PRD%'` em
`api/routers/intelligence_kpis.py` do V6 — restam dois, e a chave em ambos
**não é `Instance`**:

- bloco de **disco** — chave `Hostname` em `KPI_OS_DISK_PERF_STG`
- bloco de **eventos offline** — chave `Server_Name` em
  `KPI_MSSQL_SERVER_OFFLINE_EVENTS`

`INST_ENVS.Instance` guarda identificadores tipo `SQLHDSTST505_I01`
(host + instância nomeada); `Hostname` é só o nome do servidor. Um
`UPPER(Hostname) = UPPER(Instance)` falha **em silêncio** para qualquer host com
FCI ou instância nomeada. Precisa de mapeamento próprio — não é reuso mecânico.

O V3.3 tem o mesmo padrão em blocos equivalentes: confirmar antes de assumir que
só o V6 está afectado.

---

## 6. Arranque do V6 — o incidente está meio fechado

A descoberta de bases saiu do caminho crítico (`92c6dc9` + `43d5ca3`), mas
**três `await` continuam a bloquear o bind da porta** em `watcherdb_main.py`:

- `await app.state.inventory_manager.load_complete_inventory()`
- `await app.state.background_services.start_all_services()`
- `cache_loaded = await preload_kpi_cache()` ← este sozinho leva ~130s

Enquanto isto não mudar, a porta 8660 demora mais de dois minutos a abrir num dia
bom, e num dia de rede degradada repete-se o incidente de 04/08 (duas horas com o
serviço inacessível, dois arranques que nunca chegaram a escutar).

**O V3.3 já resolveu isto** — põe os três em background com `wait_for(timeout=30)`
no inventário. É por isso que o V3.3 responde em 0,2s e o V6 não. Portar, não
reinventar: a primeira tentativa de 04/08 reinventou o padrão e perdeu as duas
lições que lá estavam (atraso de 300s antes de descobrir, e metade da
concorrência).

Consultar `architecture-advisor` antes — foi ele que apanhou que a versão inicial
abria uma janela de corrida no `servers.json` que não existia antes.

---

## 7. Dívida menor, registada

- **Código morto no portal V6**: existe um bloco `if (kpiType === 'always-on')`
  dentro do `else` genérico que é inalcançável — o `else if` anterior intercepta
  o mesmo valor. Candidato a remoção; confunde quem for manter.
- **Modal AlwaysOn fora da cobertura de tradução**: todo o bloco ("Motivo:",
  "AG:", "Ambiente:", e as novas "Database:"/"Estado:") não tem pares em
  `NYT_TR`. Gap pré-existente, mas as strings novas herdaram-no.
- **FIND-106 — disponibilidade pode mentir sob staleness**: o payload já traz
  `data_stale` e `stale_minutes` (visto a 923 minutos numa leitura real), mas a
  UI mostra o último valor conhecido como se fosse actual. O cálculo existe;
  falta a UI usá-lo.
- **Instâncias de PRD oscilaram de 40 para 39** entre duas leituras a uma hora
  de distância. Ou caiu uma instância, ou a coleta dela atrasou — é exactamente
  o que o FIND-106 diz que o produto ainda não distingue.

---

## 8. Ordem sugerida

1. **Browser test** (§2) — barato, e destranca declarar o lote 07/08 fechado.
2. **Aviso + DDL** (§3) — o aviso primeiro, o DDL depois.
3. **Arranque do V6** (§6) — é o que ainda pode voltar a deixar o serviço em baixo.
4. **Banner U3** (§4) — só depois da decisão de tiering.
5. **Blocos `LIKE`** (§5) e **dívida menor** (§7) — quando houver folga.

Antes de qualquer um deles: consultar o specialist da área, com perguntas
concretas e pedido de veredicto (R5).
