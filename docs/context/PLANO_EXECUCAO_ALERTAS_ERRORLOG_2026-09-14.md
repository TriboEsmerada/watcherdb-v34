# Plano de execução — alertas críticos, histórico de errorlog e dívida do LIVE

> Origem: sessão de 11–14/09 (LIVE 4 canais, F9, F9b, salto AG) e os dois pedidos do owner a 14/09:
> (1) o ecrã de instância offline mostrar o errorlog à volta da queda; (2) qualquer KPI crítico novo
> gerar um aviso no ecrã. Tudo o que segue foi verificado no código ou medido na frota; onde é
> suposição, está escrito que é.

## 0. Estado à entrada (não repetir)

Fechado nesta sessão e em produção: os 4 canais do LIVE que davam 503/500 (`33a8c98`), os 5 acertos
de UX do teste completo (`ca0a77d`), nomes e tooltips do Fleet (`dca254e`), o salto do canal AlwaysOn
para a primária (`185a4ff`, teste corrigido em `8f9f995`).

Pendente de outra sessão, já pronto a aplicar: `docs/context/FIX_API500_PASSO1_apply.py`
(achados 1–4 de `FINDINGS_TESTSUKITA_2026-09-11`).

Item que sai da fila por estar resolvido: o lag do painel LIVE medido por `DATEDIFF` até `GETDATE()`.
Ficou corrigido em `33a8c98`; os `DATEDIFF` que restam no router medem tempo decorrido de pedidos
activos, que é o uso correcto.

---

## Bloco A — o aviso de KPI crítico (pedido 2 do owner)

**Facto de partida.** O mecanismo já existe. `TOAST_CRITICAL_CHECKS` tem 7 entradas:
`instances_offline`, `blocked_sessions`, `db_unavailable`, `alwayson_unhealthy`, `disk_critical`,
`tlog_critical`, `filegroup_critical`. Não é preciso construir popup novo. O owner só vê o de
blocking porque é o único cujo contador se mexe.

### A1 — o contador de instâncias offline (bloqueia tudo o resto) — **FECHADO 14/09**

> **Estado:** aplicado na base viva e provado com evento sintético. A medição corrigiu o diagnóstico: o
> contador não estava estruturalmente a zero; o defeito só aparece quando há servidor em baixo e o
> recolhedor salta ciclos. Havia 5 órfãos que tornavam obrigatório fechá-los antes de retirar a janela, e
> uma quinta causa (Env por host contra inventário por instância). Detalhe no CONTEXT.md de 14/09 e na
> migration 010 do V1. Pendentes em lote próprio: P1b (auto-resolve de órfãos no recolhedor) e P4.

- **Porquê primeiro:** o alerta de offline está ligado e nunca disparou, porque lê `off_count` da
  Disponibilidade, que é estruturalmente 0. Ligar mais avisos a contadores mortos não produz avisos.
- **As quatro causas medidas a 10/09:** a vista agrupa eventos numa janela de 15 minutos; o MERGE
  reescreve `Event_Time` a cada ciclo, logo o evento rejuvenesce e nunca envelhece; o travão do ping
  e o ambiente `Undefined` tiram a instância da conta; não existe a linha "sem recolha".
- **Toca em:** vista da família `SERVER_OFFLINE_EVENTS` (base partilhada), recolhedor de ping,
  backend do KPI de disponibilidade, portal.
- **Gate:** guardião do recolhedor (veto), porque mexe em família partilhada. Canónico + docs no
  mesmo commit (regra 2).
- **Prova:** com uma instância comprovadamente em baixo, o cartão passa a dizer o número certo e o
  aviso dispara. Sem instância em baixo, provar em ambiente de teste desligando a recolha de uma.
- **Esforço:** meio dia, com a medição prévia das quatro causas na base viva.

### A2 — disciplina dos avisos — **PRONTO 14/09 (aguarda aplicação)**

Sem isto, ligar 15 KPI transforma uma manhã má numa parede de avisos, e o DBA aprende a ignorar o
vermelho. É a mesma doutrina que levou o alarme de backup de 469 para 75.

- **Primeira observação também dispara.** Hoje só dispara em subida face à leitura anterior; quem
  abre o portal com 8 instâncias já em baixo não vê nada.
- **Um aviso por condição, com arrefecimento.** Hoje um valor que oscila entre 3 e 4 dispara em cada
  subida. A chave de deduplicação passa a ser a condição, não o valor.
- **Sino com histórico.** Nenhum aviso desaparece em silêncio, incluindo os suprimidos enquanto o
  utilizador está no ecrã de KPIs. Regra de 21/08 aplicada aos avisos.
- **Toca em:** só portal. **Gate:** frontend-specialist. **Esforço:** 2 a 3 horas.

### A3 — ligar os KPI críticos que faltam — **classificação aprovada 15/09, lote em preparação**

- Passar dos 7 actuais aos restantes críticos do registo, com o mesmo contrato: valor, valor
  anterior, tipo de KPI para o clique abrir a modal certa.
- **Pré-condição:** cada contador que se ligue tem de ter prova de que se mexe. Um contador que
  ninguém verificou entra com nota, não com aviso.
- **Toca em:** só portal. **Esforço:** 1 a 2 horas depois de A2.
- **Classificação aprovada pelo owner a 15/09**, do parecer da persona DBA cliente: ligar backup e
  mirroring sem condição; CPU, memória, latência de disco e tempdb só com duração mínima e
  histerese; jobs só os críticos; locks longos e utilizadores bloqueados dentro do aviso de sessões
  bloqueadas, processos em espera dentro do de CPU; não ligar deadlocks, errorlog nem serviços.
  A linha de serviços deixa de mostrar 0 verde, porque a recolha está parada desde 13/05.

---

## Bloco B — histórico de errorlog (pedido 1 do owner)

**Factos medidos hoje, que mudam o desenho:**

| Facto | Onde | Consequência |
|---|---|---|
| `cutoff = now - 60 min` | `collect_errorlog.py` | a tabela só tem a última hora |
| `TRUNCATE TABLE` por ciclo (5 min) | `store_data` | uma instância que cai desaparece da tabela em menos de 5 min |
| `xp_readerrorlog 0, 1, N'Error'` | leitura | reboots e shutdowns nunca são capturados; das duas linhas de um erro só sobra a do número |
| `Log_Type='Error'`, `Severity=None` | escrita | não há por onde filtrar gravidade: as colunas existem e estão sempre vazias |
| `abs(hash(texto))` | escrita | hash aleatorizado por processo: a mesma linha muda de chave a cada reinício do serviço |

Volume actual, da consulta do owner a 14/09: 19.510 linhas, 33 instâncias, janela de 70 minutos,
cerca de 590 linhas por instância por hora.

**Factos medidos a 15/09 na base viva (corrigem este plano):**

| Facto | Medida | Consequência |
|---|---|---|
| `KPI_MSSQL_ERRORLOG_HIST` está viva | 2,7 milhões de linhas, 59 instâncias, desde 24/06 | não há nada a "ressuscitar"; o canónico é que a dá como descontinuada |
| Quem escreve é `usp_archive_errorlog`, chamada por `usp_archive_all_kpis` no job diário das 05:00 | 14/09 tem só a hora 18 (20.357 linhas); 11/09 tem as horas 3, 4 e 20 | o histórico é uma fotografia por dia da janela que estiver na STG às 05:00; o resto do dia perde-se |
| As duas procedures não existem no canónico nem no código do V1 | procura no repositório sem resultados | desvio da base viva face ao canónico, a resolver no mesmo lote de B2 (regra 2) |
| O job `WatcherDB_Collect_ErrorLogs` corre de 5 em 5 min e diz "sucesso" | escreve em `raw.sql_error_logs`, que tem 0 linhas; o TRY/CATCH só faz PRINT | falso verde no SQL Agent; o canónico ainda o cria. Decisão do owner em D |
| Conteúdo do HIST | `Log_Type` sempre 'Error', gravidade e número sempre nulos, 0 mensagens de arranque ou encerramento em 30 dias | confirma B1: reboots e shutdowns nunca chegam ao histórico |
| Quatro erros dominam o volume em 30 dias | 1105: 491 mil; 18456: 511 mil somando estados; 33208: 267 mil; 9002: 90 mil | a retenção tem de agregar repetições, não guardar cada linha |
| Duplicados | 0 grupos em 10 e 11/09 | a deduplicação da procedure já ignora o carimbo de recolha |

**Critério do owner, aceite:** guardar só erros, eventos críticos, reboots e shutdowns. Fora
avisos e informativos. Filtrar na origem é a doutrina que em 30/07 cortou 142 mil linhas por ciclo
para 1.400.

### B0 — medir antes de desenhar (leitura pura) — **FECHADO 15/09**

- **Resultado** em `B0_MEDICAO_ERRORLOG_2026-09-15.md`: 14 instâncias PRD, cerca de 724 linhas por dia com a
  política (336 guardadas, 388 agregadas) contra 71.508 com o filtro de hoje. O erro 33208 (severidade 17)
  domina, portanto a severidade sozinha não filtra. Nove instâncias PRD reiniciaram na madrugada de 15/09.

- Ler o errorlog de uma instância de produção **sem** o filtro por palavra, durante um período, e
  contar por categoria: erros por gravidade, ciclo de vida (arranque, encerramento, recuperação,
  failover), tentativas de login, ruído informativo.
- **Sem esta medição, qualquer política de retenção é um palpite.** É o passo que decide o volume
  de B2.
- **Identidade:** `sql_monitoring`, leitura. **Esforço:** 1 hora. **Corre:** a AI.

### B1 — recolhedor: classificar em vez de filtrar por palavra — **B1a FECHADO, B1b PRONTO 15/09**

- **B1b pronto em três lotes, consenso do guardião na revisão final:** leitor do V3.4 conta pelo Log_Type (aplicar
  primeiro, senão o 33208 de severidade 17 pinta cerca de dez instâncias de vermelho), recolhedor por janela de 65 min
  com timeout de consulta e classificação, e migration 011 que desabilita o job WatcherDB_Collect_ErrorLogs e põe o
  manifesto da Wave D a 0. Prova real com ligações sql_monitoring em 5 PRD: 1 a 1.140 linhas por janela, 0,10 a 0,73 s.
- **Condição para o B2b (guardião):** a deduplicação da HIST por CHECKSUM(Log_Text), sem Update_TS, passa a ser
  pré-condição de correcção. Com rotação na janela o log anterior é relido em ciclos seguidos; nunca incluir o
  Update_TS na chave de deduplicação.

- **Parecer do guardião do recolhedor (15/09, sem veto).** Ordem: B1a classificador puro, B1b janela temporal e
  timeout de consulta, B2a marca de água por instância e MERGE por ciclo na HIST, B2b colunas de agregação só na
  HIST (nunca nas STG BLUE/GREEN), B3. Segurança (18456) na coluna Log_Type, sem tabela nova.
- **Condição do guardião resolvida por medição:** nas 8 STG BLUE/GREEN o Log_Text_Hash é int normal sem chave
  primária; na HIST é calculado (CHECKSUM) e a proc de arquivo recalcula-o.
- **Janela temporal provada** em SQL 2012, 2016, 2019 e 2022: SQLRPAPRD02 passa de 261.843 linhas em 20,9 s para
  2.150 em 0,31 s. Datas em texto; resultado vazio não é conjunto de resultados; usar o relógio do servidor.
- **B1a provado em dados reais:** 12 h de 6 instâncias PRD, 38.045 linhas dão 77 eventos guardados e 84 grupos
  horários; os três arranques da madrugada apanhados. Lote `B1A_CLASSIFICADOR_ERRORLOG_2026-09-15_apply.py`.

- Ler sem o filtro `N'Error'`; classificar cada linha por número de erro, gravidade, estado e padrão
  de ciclo de vida; juntar as duas linhas do mesmo erro; hash determinístico em vez do `hash()` do
  Python.
- **Verificar antes:** o canónico declara a coluna de hash como calculada e o recolhedor insere-a
  explicitamente. Se a base viva a tiver como coluna normal, é desvio a corrigir no canónico.
- **Gate:** guardião do recolhedor, com veto. **Esforço:** meio dia.

### B2 — tabela de histórico com retenção

- **Revisto a 15/09:** a tabela vive e tem deduplicação correcta. O defeito é o momento do arquivo:
  uma vez por dia, às 05:00, só apanha o que estiver na STG, que é truncada a cada ciclo. Passar o
  arquivo para cada ciclo do recolhedor, ou gravar o histórico directamente no recolhedor, com os
  critérios de B0 e B1.
- Trazer `usp_archive_errorlog` e `usp_archive_all_kpis` para o canónico, com a forma que sair
  daqui, e retirar do canónico o job que escreve em `raw.sql_error_logs`.
- Agregar repetições: os quatro erros que dominam o volume entram como contagem por hora, não
  como meio milhão de linhas.
- **Toca em:** base partilhada. Canónico `INSTALACAO_COMPLETA_UNIFICADA.sql` + documentação no mesmo
  bloco (regra 2). Entrada no purge diário.
- **Corre o DDL:** o owner (regra 5). **Esforço:** 2 a 3 horas de preparação.

### Política de retenção e expurgo (decidida para B2, parecer de conformidade de 15/09)

| Camada | Por omissão | Mínimo | Máximo | Fundamento |
|---|---|---|---|---|
| Texto com login e IP (falhas de login, contas bloqueadas) | 90 dias | 30 dias | 90 dias | RGPD art. 5.º(1)(e), minimização |
| Eventos guardados um a um, sem login e IP depois dos 90 dias | 12 meses | 12 meses | 36 meses | PCI DSS 10.5.1 quando o servidor está no âmbito de cartões; DORA RTS art. 12; ISO 27001 A.8.15 |
| Agregados horários sem texto de exemplo pessoal | 13 meses | 12 meses | decisão do cliente | já não é dado pessoal; comparação ano a ano |
| Legal hold por instância | suspende o expurgo | | | preservação para investigação de incidente |

- Política por cliente numa tabela, com mínimo e máximo, e histórico de alterações (quem, quando).
- Expurgo sobre **Log_Date** (hoje é Update_TS, a data de recolha), em lotes, com registo append-only do que
  apagou e alerta quando o job falha. Até lá, o expurgo actual de 90 dias continua.
- Documentar em contrato e no guia de segurança que o histórico do WatcherDB **não substitui** SQL Server Audit
  nem SIEM: descarta informativos por desenho.
- Estimativa com a política nova, 59 instâncias: cerca de 1,2 milhões de linhas e 320 MB no total. Hoje: 726 MB
  para 83 dias de uma fotografia diária.

### B3 — bloco no ecrã de instância offline

- Endpoint só de leitura com as últimas mensagens da instância, e o bloco no ecrã com o rótulo
  honesto: "últimas mensagens antes de perder contacto", nunca "o que aconteceu".
- Mostra a idade da última recolha e avisa quando está velha.
- **Esforço:** 2 horas. **Depende de:** B1 e B2. Hoje o histórico existe, mas com uma janela por
  dia a hora de uma queda raramente lá está: o bloco nasceria quase sempre vazio.

---

## Bloco C — dívida técnica destapada nesta sessão

| # | Item | Onde | Esforço |
|---|---|---|---|
| C1 | Endpoints do LIVE são `async def` com pyodbc síncrono: bloqueiam o event loop a cada sondagem de 5 s. O canal AlwaysOn já passou a `def`; faltam os outros 13 | `live_monitoring.py` | 2 h + prova de carga |
| C2 | Gauges congelam no último valor bom quando a leitura falha, sem sinal de idade. Mesma classe do carimbo de refresh | portal | 1 h |
| C3 | Mensagens usam a chave interna do programa (`alwayson`, `plancache`) em vez do rótulo visível | portal | 1 h |
| C4 | KPI de serviços estruturalmente 0 desde 13/05 (família de recolha desactivada). Passo A: N/D quando os dados estão velhos, cartão nunca escondido | backend + portal | meio dia |
| C5 | `backup_pattern_analysis` com `params=` inválido: mais de 1.280 ocorrências no log | `modules/monitoring` | 1 h |
| C6 | Resolvedor de AG lê ficheiros JSON legados em vez da base | `api/routers/alwayson.py` | 2 h |
| C7 | Lote i18n F9: literais das tabelas do separador Always On | portal + i18n | 2 h |

---

## Bloco C0 — as classes do LIVE que estão vivas noutros routers

Medido no log do serviço desde o arranque de 14/09, com o ficheiro e a linha tirados dos frames do
traceback, não por adivinhação. São os mesmos defeitos que fechei no LIVE esta semana, noutros sítios.

| Erro | Ocorrências | Sítio real | Estado |
|---|---|---|---|
| `Decimal` não serializável | 32 | `api/routers/sqlserver_kpis.py` (5 endpoints) e `service_status.py` (services/overview) | o primeiro está no `FIX_API500`; o segundo não |
| Sintaxe 319 junto a "with" | 8 | `modules/monitoring/queries.py:1605`, hint numa função de tabela | coberto pelo `FIX_API500` |
| `params=` inválido | 679 | `backup_pattern_analysis.py:220` e `:368` | coberto pelo `FIX_API500` |
| `JSONResponse` tratado como dicionário | 4 | `watcherdb/api/routers/security.py:177` | coberto pelo `FIX_API500` |
| Overflow 8115 | 18 | `sqlserver_kpis.py:381 get_filegroup_usage` e `:674 get_statistics_outdated` | **por corrigir** |
| Conflito de collation em UNION ALL, coluna 3 | 16 | `api/routers/queries/space.py:211 get_disk_files` | **por corrigir** |
| Tipo ODBC -16 não suportado | 40 | `security_analysis.py:167` e `:770`, `SERVERPROPERTY` sem `CAST` (devolve `sql_variant`) | **por corrigir** |
| Coluna `encryption_state_desc` inexistente | 20 | `security_analysis.py:581` | **por corrigir** |

**Nota sobre o endpoint de segurança:** `/api/monitoring/security/server/{id}/summary` está partido de
três maneiras ao mesmo tempo. O `FIX_API500` fecha uma. As outras duas, a coluna inexistente e o
`sql_variant` sem conversão, ficam para este lote. Corrigir só uma delas não põe o ecrã a funcionar.

**Detalhe que poupa trabalho:** a coluna `encryption_state_desc` não existe em `sys.databases`, e o
código que a pede nunca a lê, porque só usa `is_encrypted`. Removê-la é a correcção completa.

**Ordem:** aplicar primeiro o `FIX_API500`, que já está preparado e validado, e só depois este lote,
para as provas não se misturarem. Um restart entre os dois.

## Bloco D — infra e decisões que são do owner

- **D1. O recolhedor corre no portátil do owner.** Com a máquina desligada não se recolhe nada, e o
  histórico de B2 terá buracos ao fim de semana. É o mesmo padrão que a 04/08 levou o motor de
  baselines para um trabalho no servidor. **Sem isto, o Bloco B entrega menos do que promete.**
- **D2. Erro 18456 estado 8 no errorlog do 405, vindo de 10.89.0.171.** Parte são as sondas da AI de
  11/09 entre as 18:30 e as 19:10 (o pool do processo carrega a password cifrada). Confirmar se há
  ocorrências fora dessa janela: se houver, há um recolhedor ou script com credencial velha.
- **D3. MYBAGP2 em SQLHDSPRD405.** Redo passou de 65 GB para 111 GB numa hora, sem drenar. O drill
  "Acompanhar" diz em 3 minutos se drena ou estagna. Verificar o espaço livre no volume do t-log da
  primária. Decisão de DBA, não do produto.
- **D4. Repositório público.** Purga do histórico, privacidade e rotação da credencial continuam por
  decidir desde 04/09.
- **D5. Duas decisões de produto em aberto:** os limiares do drill de resume entram no registo de
  thresholds? O relatório preditivo fica com gate de admin ou de dba?

---

## Ordem recomendada

1. **A1** (contador de offline) — desbloqueia o pedido do owner e é o maior ganho isolado.
2. **A2 + A3** (disciplina e cobertura dos avisos) — fecham o pedido 2.
3. **B0** (medição) — pode correr em paralelo com A, é leitura pura.
4. **B1 → B2 → B3** — a wave do errorlog, com o gate do guardião entre B0 e B1.
5. **C1, C4** — a dívida com impacto em produção.
6. **C2, C3, C5, C6, C7** — por ordem de incómodo.

D1 é transversal: enquanto o recolhedor viver no portátil, A1 e B2 entregam menos do que prometem.

## Regras aplicadas a todos os lotes

Script de aplicação em `docs/context/` com `--check` e `--preview`, prova numa cópia isolada antes
de o owner aplicar, testes no mesmo commit, entrada no CHANGELOG, episódio em `SOLUCOES.md` quando
for defeito, prompt de propagação V6 (regra 3), e parecer do especialista antes de escrever código
quando toca em base partilhada ou recolhedor (regra 0).
