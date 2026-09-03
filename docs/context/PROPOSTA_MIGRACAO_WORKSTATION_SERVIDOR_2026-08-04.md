# Proposta — tirar os motores de produto do workstation

**Data:** 2026-08-04 · **Estado:** proposta para decisão (não implementado)
**Motivo:** o motor de baselines parou **3 vezes** (03/06, 12/06, 24/07→04/08, esta
última 11 dias) sempre pela mesma causa-raiz — corre no **workstation do owner**,
que está desligado à noite e atrás de uma firewall que corta o SQL Browser.

---

## O problema em uma frase

Componentes de **produto** vivem no **posto de trabalho de desenvolvimento**. Herdam
as duas fragilidades do posto: **desligado fora de horas** e **atrás da firewall
corporativa** (que bloqueia UDP 1434 / SQL Browser → `08001`). Num cliente real,
isto correria num servidor sempre ligado, na rede da base de dados.

## Inventário — o que corre onde, e como aguenta

| Componente | Onde | Robustez | Porquê |
|---|---|---|---|
| **17 jobs SQL Agent** (purge, cleanup, anomaly, verify Fase 1…) | **Servidor** SQLHDSTST505 | **robusto** | corre no servidor, sempre ligado, sem firewall (localhost), sem Python |
| `collect_scheduled_tasks_audit` (verify Fase 2) | Workstation (collector_service) | frágil | PC + firewall |
| **BaselineCompute** | Workstation (Task Scheduler) | **frágil — parou 3×** | PC + firewall + wrapper S4U + Python |
| Liveness_Watchdog | Workstation (Task Scheduler) | frágil (mas externo, ok) | vigia o collector local — faz sentido ser local |
| collector_service (118 tasks) | Workstation (serviço Windows) | frágil | PC + firewall |
| DORA audit archive (V6) | *nenhures* (atestado, não instalado) | ausente | — |

**A lição está na primeira linha:** o que já vive no servidor (SQL Agent) nunca
falhou por estas causas. O que vive no workstation falha repetidamente.

## Duas frentes — uma barata e imediata, outra estrutural

### FRENTE 1 (quick win, alto valor) — baseline → SQL Agent job no servidor

**Descoberta:** o `compute_baseline.py` não precisa de Python. Faz três coisas:
ligar, `EXEC dbo.usp_compute_kpi_baseline @Force_Full=?, @Debug=?`, e ler um
`SELECT` de stats. **Tudo T-SQL.** O Python é conveniência (logging, formato dos
stats), não necessidade.

O `WatcherDB_Anomaly_Detection` — que também é só `EXEC dbo.usp_...` — **já é** um
SQL Agent job e é robusto. O baseline devia ser o mesmo padrão.

**Proposta:** criar o job `WatcherDB_Baseline_Compute`:
```sql
-- passo TSQL, database WatcherDB_Intelligence, diario 03:00 (janela silenciosa,
-- e agora REAL porque o servidor esta sempre ligado):
SET QUOTED_IDENTIFIER ON; SET ANSI_NULLS ON;   -- WDB_KPI_BASELINE nao tem indice
                                               -- filtrado, mas e' higiene (licao 1934)
EXEC dbo.usp_compute_kpi_baseline @Force_Full = 0, @Debug = 1;
```
Resolve as **3 camadas de uma vez**: corre no servidor (PC sempre ligado), por
localhost (sem firewall/Browser), em T-SQL (sem wrapper Python nem conta S4U).

**O que muda no manifest da Wave D:** `WatcherDB_Intelligence_BaselineCompute_PRD`
(SCHEDULED_TASK) sai; entra `WatcherDB_Baseline_Compute` (AGENT_JOB). O
verificador passa a vigiá-lo pela via robusta (Fase 1, no servidor).
**O que fica:** a tarefa Task Scheduler do workstation pode ser desactivada
(o `compute_baseline.py` e o wrapper ficam como ferramenta manual de recurso —
o override `BASELINE_MASTER_SERVER` que criámos hoje continua útil para correr à mão).

**Custo:** 1 job SQL + 1 linha no manifest. **Ganho:** o motor de baselines nunca
mais depende do PC do owner. Recomendo fazer isto **primeiro**, independente da Frente 2.

*Nota de política:* o job correria como a conta do SQL Agent (não `sql_monitoring`),
que já executa as outras procs de escrita. O `GRANT EXECUTE` em
`usp_compute_kpi_baseline` já existe (o baseline corria com `sql_monitoring`).

### FRENTE 2 (estrutural) — collector_service → servidor Windows sempre ligado

O `collector_service` **não** pode virar SQL Agent: precisa de Python real
(pandas, PowerShell para o audit de Task Scheduler, e o roadmap AI/Ollama dos
tiers Pro). A resposta é movê-lo, tal como está (pywin32 + APScheduler), para um
**servidor Windows sempre ligado** — idealmente o próprio SQLHDSTST505 ou um
member server na mesma rede da BD.

Ganhos: PC sempre ligado (fim da camada 1); se co-localizado com o SQL, liga por
localhost/rede interna (fim da camada firewall). O código não muda — só o host.

Requisitos (do `requirements.txt`): pyodbc, pandas, cryptography, APScheduler,
pywin32. Todos servem num Windows Server. O `install.py` (pywin32 ServiceFramework)
regista o serviço igual.

**Decisões que precisam do owner / deploy-architect:**
1. Qual servidor? (SQLHDSTST505 co-localizado = também mata a firewall; ou member
   server dedicado = mais limpo mas mantém a questão da porta até haver estática.)
2. Identidade do serviço (conta AD de serviço least-privilege vs. a actual).
3. Janela de migração + rollback (o collector é a fonte de todos os KPIs).

O `Liveness_Watchdog` (Camada 0, vigia externo do collector) **fica onde o
collector estiver** — segue-o para o servidor.

## Ordem recomendada

1. **Frente 1 já** — baseline → SQL Agent job. Barato, e fecha o item mais
   sério (motor parado 3×). Não espera pela Frente 2.
2. **Pedido de porta estática** (já escrito) — mitiga a firewall para tudo o
   que ficar no workstation entretanto.
3. **Frente 2** — planear com `watcherdb-deploy-architect` (é a casa dele:
   Windows services, contas AD, deploy). Wave própria.

## O que NÃO fazer

- Não converter o collector_service em SQL Agent (precisa de Python).
- Não deixar o baseline como Task Scheduler "com wake-on-missed" — é penso sobre
  penso; a Frente 1 é mais simples e definitiva.
