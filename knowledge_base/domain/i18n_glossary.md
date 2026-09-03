# Glossário i18n — WatcherDB V3.4

Fonte para `v33-i18n-linguist` e `v33-i18n-coverage`. Decisões do owner 2026-09-03:
`pt.json` = pt-PT pós-AO90 (default); `pt-BR.json` = overlay esparso (só o que difere);
`en.json` = en-US; `es.json` = espanhol neutro (sem vosotros, sem léxico só ibérico).
Acentuação rigorosa em pt / pt-BR / es é exigência explícita (finding P1 quando falta).

## 1. Termos que ficam em inglês em TODOS os locales

| Termo | Nota |
|---|---|
| AlwaysOn / Always On, Availability Group (AG), listener, réplica → **replica** só em en | pt/es podem dizer "réplica" |
| backup, backupset, FULL / DIFF / LOG, restore, RPO, RTO | nunca "cópia de segurança" na UI |
| tempdb / TempDB, filegroup / FileGroup, data file, log file, transaction log | "T-Log" aceitável |
| job, SQL Agent / Agent, schedule (quando é `msdb.dbo.sysschedules`) | "agendamento" = a acção, ok em pt |
| DMV, XE (Extended Events), wait stats, plan cache, parameter sniffing | |
| failover, mirroring, linked server, snapshot, collation, recovery model | |
| CPU, RAM, IOPS, KPI, SLA, TDE, DBCC, DNS, TCP, ODBC, AD, LDAP/LDAPS | |
| Max Server Memory, STATISTICS IO/TIME, Actual Execution Plan, query hash | nomes de opções/artefactos |
| drive, label, database (quando nome de objecto ou coluna), instance name | "base de dados" quando é prosa em pt |
| dashboard, login, logout, timeout, cluster, deadlock, lock, latch, spill | |

## 2. Pares pt-PT ↔ pt-BR recorrentes (o overlay só existe para estes)

| pt-PT (pt.json) | pt-BR (pt-BR.json) |
|---|---|
| utilizador(es) | usuário(s) |
| ficheiro(s) | arquivo(s) |
| Definições (menu Settings) | Configurações |
| registo | registro |
| A carregar… | Carregando… |
| recolha (de dados) | coleta |
| monitorização | monitoramento |
| Base de Dados | Banco de Dados |
| relacionados com | relacionados a |
| Estado | Status |
| Pesquisar | Buscar |
| ecrã | tela |
| gerir / gestão | gerenciar / gerenciamento |
| guardar | salvar |
| equipa, controlo, planeamento | equipe, controle, planejamento |

Grafia comum pós-AO90 (não é marcador de variante): atualizar, ativo, direto, ótimo, coleção.

## 3. Espanhol neutro — evitar

ordenador → equipo/servidor; fichero → archivo; vosotros/vuestro → ustedes/su;
coger → tomar/obtener; "ordenar" ok; "vale" → "aceptar".

## 4. en-US — evitar en-GB

colour, optimise, analyse, licence (subst.), catalogue, behaviour, centre.
