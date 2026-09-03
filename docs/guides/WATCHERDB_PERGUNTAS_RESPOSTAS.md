# WatcherDB — Catalogo Completo de Perguntas e Respostas

> Documento gerado em 2026-03-08
> Versao: DEV (aplicavel a DEV_V4 e V4)

---

## COMO LER ESTE DOCUMENTO

- **Caminho**: Indica o percurso no programa para obter a resposta (Portal > Tab > Seccao)
- **Endpoint**: API REST que fornece os dados
- **Importancia**: CRITICA | ALTA | MEDIA | BAIXA
- **Secao A**: Perguntas que o sistema CONSEGUE responder
- **Secao B**: Perguntas que o sistema NAO consegue responder (e o que fazer)

---

# SECAO A — PERGUNTAS QUE O WATCHERDB RESPONDE

---

## 1. DISPONIBILIDADE & ALWAYS ON

### IMPORTANCIA CRITICA

**P: As replicas do AlwaysOn estao saudaveis?**
- Caminho: Portal > Seleccionar servidor > Tab "AlwaysOn" > Seccao "Replicas"
- Endpoint: `GET /api/alwayson/server/{server_id}/overview`
- Dados: Nome da replica, role (PRIMARY/SECONDARY), sync_health (HEALTHY/NOT_HEALTHY), connected_state, availability_mode (SYNC/ASYNC)

**P: Alguma database esta fora de sincronizacao no AG?**
- Caminho: Portal > Tab "AlwaysOn" > Seccao "Databases"
- Endpoint: `GET /api/alwayson/server/{server_id}/overview`
- Dados: database_name, synchronization_state_desc (SYNCHRONIZED/SYNCHRONIZING/NOT_SYNCHRONIZING), is_failover_ready

**P: Qual o historico de failovers recentes?**
- Caminho: Portal > Tab "AlwaysOn" > Seccao "Eventos"
- Endpoint: `GET /api/alwayson/events/{server_name}`
- Dados: Timestamp do evento, tipo (FAILOVER, STATE_CHANGE), severity, descricao

**P: O Listener do AG esta online?**
- Caminho: Portal > Tab "AlwaysOn" > Seccao "Listener"
- Endpoint: `GET /api/alwayson/server/{server_id}/overview`
- Dados: dns_name, porta, ip_address, state (Online/Offline)

### IMPORTANCIA ALTA

**P: Existe lag de replicacao entre replicas?**
- Caminho: Portal > Tab "AlwaysOn" > Overview
- Endpoint: `GET /api/alwayson/server/{server_id}/overview`
- Dados: Metricas de sincronizacao, redo_queue_size, log_send_queue_size

**P: Quais eventos AlwaysOn ocorreram nas ultimas horas?**
- Caminho: Portal > Tab "AlwaysOn" > Seccao "Eventos" > Filtro temporal
- Endpoint: `GET /api/alwayson/events/{server_name}`
- Dados: Lista cronologica de eventos com severity e descricao

**P: Qual o diagnostico completo do AG?**
- Caminho: Portal > Tab "AlwaysOn" > Botao "Diagnosticar"
- Endpoint: `GET /api/alwayson/diagnose/{server_name}`
- Dados: Analise automatica de problemas, recomendacoes, padroes detectados

### IMPORTANCIA MEDIA

**P: Quais instancias pertencem a cada AG?**
- Caminho: Portal > Tab "AlwaysOn" > Overview geral
- Endpoint: `GET /api/alwayson/instance-by-ag/{ag_name}`
- Dados: Lista de instancias por AG, role de cada uma

---

## 2. BACKUP & RECUPERACAO

### IMPORTANCIA CRITICA

**P: Qual o ultimo backup completo (Full) de cada database?**
- Caminho: Portal > Seleccionar servidor > Tab "Backup" > Tabela de databases
- Endpoint: `GET /api/monitoring/backup/server/{server_id}/summary`
- Dados: database_name, last_full_backup, last_full_backup_age_hours, backup_size_mb

**P: Existem bases de dados SEM backup?**
- Caminho: Portal > Tab "Backup" > Filtrar por "Never Backed Up"
- Endpoint: `GET /api/monitoring/backup/server/{server_id}/issues`
- Dados: Lista de databases sem backup, tipo de issue, severity

**P: Ha gaps de backup (Full, Diff ou Log)?**
- Caminho: Portal > Tab "Backup" > Seccao "Gaps"
- Endpoint: `GET /api/monitoring/backup/server/{server_id}/gaps`
- Dados: Tipo de gap (Full/Diff/Log), duracao do gap, database afectada, ultimo backup conhecido

**P: O backup esta a falhar em alguma database?**
- Caminho: Portal > Tab "Backup" > Seccao "Issues" > Filtrar severidade
- Endpoint: `GET /api/monitoring/backup/server/{server_id}/issues`
- Dados: database_name, issue_type, severity (CRITICAL/WARNING), descricao, recomendacao

### IMPORTANCIA ALTA

**P: Qual o padrao de backups (frequencia, horarios)?**
- Caminho: Portal > Tab "Backup" > Seccao "Padroes"
- Endpoint: `GET /api/monitoring/backup/server/{server_id}/patterns-advanced`
- Dados: Frequencia por tipo (Full/Diff/Log), horarios mais comuns, aderencia ao schedule

**P: Qual o historico de backup de uma database especifica?**
- Caminho: Portal > Tab "Backup" > Clicar na database > Historico
- Endpoint: `GET /api/monitoring/backup/server/{server_id}/database/{db}/history`
- Dados: Lista cronologica de backups, tipo, tamanho, duracao, status

**P: Qual o health score de backup do servidor?**
- Caminho: Portal > Tab "Backup" > KPI no topo
- Endpoint: `GET /api/monitoring/backup/server/{server_id}/health`
- Dados: Score 0-100, factores de risco, recomendacoes

### IMPORTANCIA MEDIA

**P: Qual a distribuicao de backups por tipo?**
- Caminho: Portal > Tab "Backup" > Grafico de distribuicao
- Endpoint: `GET /api/monitoring/backup/server/{server_id}/summary`
- Dados: Contagem Full/Diff/Log, tamanho total por tipo

**P: Posso exportar os dados de backup em CSV?**
- Caminho: Portal > Tab "Backup" > Botao "Exportar CSV"
- Endpoint: `GET /api/monitoring/backup/server/{server_id}/summary.csv`
- Dados: Ficheiro CSV com todas as metricas de backup

---

## 3. DISCO & ARMAZENAMENTO

### IMPORTANCIA CRITICA

**P: Quanto espaco livre tem cada volume/drive?**
- Caminho: Portal > Seleccionar servidor > Tab "Disk" > Tabela de volumes
- Endpoint: `GET /api/monitoring/space/server/{server_id}`
- Dados: drive_letter, total_gb, free_gb, used_percent, filegroups associados

**P: Algum disco esta criticamente cheio (>= 95%)?**
- Caminho: Portal > Tab "Disk" > Volumes com indicador vermelho
- Endpoint: `GET /api/monitoring/space/alerts`
- Dados: volume, used_percent, severity (CRITICAL se >= 95%, WARNING se >= 90%)

**P: Quanto espaco e recuperavel em cada drive (sem shrink)?**
- Caminho: Portal > Tab "Disk" > Seccao "Espaco Recuperavel por Database" > Cards "Recuperavel por Drive"
- Endpoint: `GET /api/queries/log-space/{server_id}`
- Dados: drive_letter, total recuperavel (MB), breakdown DATA/LOG, numero de databases

**P: Quanto espaco e recuperavel por database?**
- Caminho: Portal > Tab "Disk" > Seccao "Espaco Recuperavel por Database" > Tabela
- Endpoint: `GET /api/queries/log-space/{server_id}`
- Dados: database_name, drive_letter, file_type (DATA/LOG), total_mb, used_mb, free_mb, free_pct, recovery_model, log_reuse_wait, shrink_recommendation

**P: Qual o detalhe por ficheiro individual (SIZE, MAXSIZE, sugestao)?**
- Caminho: Portal > Tab "Disk" > Card de drive > Botao "Analisar" > Modal de Redimensionamento
- Endpoint: `GET /api/queries/file-space-detail/{server_id}`
- Dados: database_name, logical_name, physical_name, drive_letter, size_mb, used_mb, free_mb, max_size_mb, growth_value, is_percent_growth, suggested_size_mb, saveable_mb, recovery_model

**P: Quais ficheiros posso redimensionar SEM fazer shrink?**
- Caminho: Portal > Tab "Disk" > Card de drive > "Analisar" > Tabela com coluna "Accao" = "REDUZIR SIZE"
- Endpoint: `GET /api/queries/file-space-detail/{server_id}`
- Dados: Ficheiros onde saveable_mb > 0, com SQL de ALTER DATABASE MODIFY FILE gerado automaticamente

### IMPORTANCIA ALTA

**P: Qual a latencia de I/O por drive/ficheiro?**
- Caminho: Portal > Tab "Disk" > Seccao "Disk I/O"
- Endpoint: `GET /api/queries/disk-io-diagnostics/{server_id}`
- Dados: database_name, physical_name, avg_read_latency_ms, avg_write_latency_ms, read_bytes, write_bytes

**P: Quanto espaco nao alocado existe nos discos?**
- Caminho: Portal > Tab "Disk" > Seccao "Espaco Nao Alocado"
- Endpoint: `GET /disk-unallocated/server/{server_id}`
- Dados: volume, total_size, allocated, unallocated, expansion_opportunity

**P: Qual o historico de crescimento dos discos?**
- Caminho: Portal > Tab "Disk" > Seccao "Historico" (grafico)
- Endpoint: Dados em `historyData` carregados automaticamente
- Dados: Tendencia de crescimento por volume ao longo do tempo

**P: Quais ficheiros tem MAXSIZE = UNLIMITED?**
- Caminho: Portal > Tab "Disk" > Card de drive > "Analisar" > KPI card "MAXSIZE Unlimited"
- Endpoint: `GET /api/queries/file-space-detail/{server_id}`
- Dados: Contagem e lista de ficheiros com max_size_mb = -1

**P: Quais databases sao candidatas a shrink?**
- Caminho: Portal > Tab "Disk" > Seccao "Espaco Recuperavel" > KPI card "Candidatos Shrink" (> 50% livre)
- Endpoint: `GET /api/queries/log-space/{server_id}`
- Dados: Databases com shrink_recommendation = 'HIGH' (> 50% livre)

**P: Qual o SQL necessario para redimensionar os ficheiros?**
- Caminho: Portal > Tab "Disk" > Card de drive > "Analisar" > Botao "Copiar SQL Completo" ou "Copiar so Resize"
- Endpoint: Gerado no frontend com base nos dados de `/api/queries/file-space-detail/{server_id}`
- Dados: Script SQL com ALTER DATABASE MODIFY FILE (SIZE), DBCC SHRINKFILE, comentarios e prioridades

### IMPORTANCIA MEDIA

**P: Quais oportunidades de expansao existem?**
- Caminho: Portal > Consultando endpoint directamente
- Endpoint: `GET /disk-unallocated/expansion-opportunities`
- Dados: Volumes com espaco nao alocado que pode ser atribuido a filegroups

**P: Qual a previsao de crescimento dos filegroups?**
- Caminho: Portal > Tab "Disk" > Dados de forecast
- Endpoint: `GET /api/queries/filegroup-growth-forecast/{server_id}`
- Dados: Forecast com intervalo de confianca, dias ate ficar cheio

---

## 4. FILEGROUPS

### IMPORTANCIA CRITICA

**P: Quais filegroups estao criticamente cheios?**
- Caminho: Portal > KPI Dashboard > Card "FileGroups" (vermelho) > Clicar para ver detalhes
- Endpoint: `GET /api/sqlserver-kpis/filegroup-usage`
- Dados: Instancias com filegroups > 95% uso, lista de filegroups afectados

**P: Qual o espaco disponivel por filegroup e database?**
- Caminho: Portal > Seleccionar servidor > Tab "Space" > Tabela de filegroups
- Endpoint: `GET /api/monitoring/space/database/{server_id}/{db}/filegroups`
- Dados: FileGroupName, FilePath, CurrentGB, FreeGB, FreePercent, Volume

### IMPORTANCIA ALTA

**P: Qual o historico de crescimento de cada filegroup?**
- Caminho: Portal > Tab "Space" > Seleccionar filegroup > Grafico historico
- Endpoint: `GET /api/queries/filegroup-growth-history/{server_id}`
- Dados: Dados historicos de tamanho por filegroup ao longo do tempo

**P: Posso gerar um relatorio de filegroup com forecast?**
- Caminho: Portal > Tab "Space" > Botao "Gerar Relatorio"
- Endpoint: `POST /api/monitoring/space/filegroup/generate-report`
- Dados: Relatorio HTML/CSV com forecast, graficos, recomendacoes

---

## 5. MEMORIA

### IMPORTANCIA CRITICA

**P: O servidor esta com pressao de memoria?**
- Caminho: Portal > Seleccionar servidor > Tab "Memory"
- Endpoint: `GET /api/monitoring/memory/server/{server_id}`
- Dados: memory_pressure_index, total_server_memory_mb, available_memory_mb, pressure_classification

**P: Qual o Page Life Expectancy (PLE)?**
- Caminho: Portal > Tab "Memory" > KPI card "PLE"
- Endpoint: `GET /api/monitoring/memory/server/{server_id}`
- Dados: page_life_expectancy (segundos). < 300s = problema critico

**P: O SQL Server tem memoria suficiente configurada?**
- Caminho: Portal > Tab "Memory" > Seccao "Configuracao"
- Endpoint: `GET /api/monitoring/memory/server/{server_id}`
- Dados: max_server_memory_mb (configurado), total_physical_memory_mb, recommended_max_memory

### IMPORTANCIA ALTA

**P: Quais databases consomem mais memoria (buffer pool)?**
- Caminho: Portal > Tab "Memory" > Seccao "Buffer Pool por Database"
- Endpoint: `GET /api/monitoring/memory/server/{server_id}`
- Dados: database_name, pages_in_buffer, buffer_size_mb, percentage_of_total

**P: Ha memory grants em espera?**
- Caminho: Portal > Tab "Memory" > KPI card "Memory Grants"
- Endpoint: `GET /api/monitoring/memory/server/{server_id}`
- Dados: pending_memory_grants, granted_memory_mb, max_memory_grant_mb

**P: Qual a recomendacao de MAX Server Memory?**
- Caminho: Portal > Tab "Memory" > Seccao "Recomendacoes"
- Endpoint: `GET /api/monitoring/memory/recommendations`
- Dados: Valor recomendado com base no total fisico, outros servicos, e carga actual

### IMPORTANCIA MEDIA

**P: Qual o consumo de memoria por tipo de clerk?**
- Caminho: Portal > Tab "Memory" > Seccao detalhada
- Endpoint: `GET /api/monitoring/memory/server/{server_id}`
- Dados: clerk_type, pages_kb, percentage

**P: Qual a comparacao de memoria entre replicas do AG?**
- Caminho: Portal > Tab "Memory" > Seleccionar AG
- Endpoint: `GET /api/monitoring/memory/alwayson/{ag_name}`
- Dados: Comparacao lado-a-lado de memoria entre PRIMARY e SECONDARY

---

## 6. CPU

### IMPORTANCIA CRITICA

**P: Qual o uso actual de CPU (OS e SQL Server)?**
- Caminho: Portal > Seleccionar servidor > Tab "CPU"
- Endpoint: `GET /api/monitoring/cpu/server/{server_id}`
- Dados: os_cpu_percent, sql_cpu_percent, idle_percent

**P: Ha pressao de CPU (runnable tasks)?**
- Caminho: Portal > Tab "CPU" > KPI card "Runnable Tasks"
- Endpoint: `GET /api/monitoring/cpu/server/{server_id}`
- Dados: runnable_tasks_count, signal_wait_pct. > 0 runnable = pressao

### IMPORTANCIA ALTA

**P: Quais queries consomem mais CPU?**
- Caminho: Portal > Tab "CPU" > Seccao "Top CPU Queries"
- Endpoint: `GET /api/monitoring/cpu/server/{server_id}`
- Dados: query_text (truncado), total_cpu_time_ms, execution_count, avg_cpu_time_ms

**P: O MAXDOP esta configurado correctamente?**
- Caminho: Portal > Tab "CPU" > Seccao "Recomendacoes"
- Endpoint: `GET /api/monitoring/cpu/server/{server_id}`
- Dados: current_maxdop, recommended_maxdop, cpu_count, numa_nodes

**P: Quais sao as wait stats mais significativas?**
- Caminho: Portal > Tab "CPU" > Seccao "Wait Statistics"
- Endpoint: `GET /api/monitoring/cpu/server/{server_id}`
- Dados: wait_type, wait_time_ms, percentage, signal_wait_pct

### IMPORTANCIA MEDIA

**P: Os schedulers estao saturados?**
- Caminho: Portal > Tab "CPU" > Seccao detalhada
- Endpoint: `GET /api/monitoring/cpu/server/{server_id}`
- Dados: scheduler_id, current_tasks, runnable_tasks, active_workers

---

## 7. BLOQUEIOS & SESSOES

### IMPORTANCIA CRITICA

**P: Existem sessoes bloqueadas neste momento?**
- Caminho: Portal > KPI Dashboard > Card "Blocked Sessions" > Clicar para ver instancias
- Endpoint: `GET /api/sqlserver-kpis/blocked-sessions`
- Dados: Contagem de instancias com bloqueios, lista de instancias afectadas

**P: Qual a cadeia de bloqueio (quem bloqueia quem)?**
- Caminho: Portal > Seleccionar servidor > Tab "SQL Diagnostics" > "Blocking"
- Endpoint: `GET /api/queries/blocking/{server_id}`
- Dados: blocking_session_id, blocked_session_id, wait_type, wait_time, blocking_query, blocked_query, database_name

**P: O bloqueio ainda esta activo (verificacao real-time)?**
- Caminho: Portal > KPI Dashboard > Card "Blocked Sessions" > Modal > Botao "Verificar Agora"
- Endpoint: `GET /api/queries/blocking/{server_id}` (chamado em real-time)
- Dados: Se retornar vazio = bloqueio resolvido (card actualiza automaticamente para 0)

### IMPORTANCIA ALTA

**P: Ha deadlocks?**
- Caminho: Portal > Tab "SQL Diagnostics" > "Deadlocks"
- Endpoint: `GET /api/queries/deadlocks/{server_id}`
- Dados: Participantes do deadlock, queries envolvidas, recursos disputados

**P: Quais sessoes sao problematicas?**
- Caminho: Portal > Tab "SQL Diagnostics" > "Sessions"
- Endpoint: `GET /api/queries/sessions/{server_id}`
- Dados: session_id, login_name, host_name, program_name, cpu_time, reads, writes, status, blocking_info

---

## 8. TEMPDB

### IMPORTANCIA CRITICA

**P: O TempDB esta cheio ou sob pressao?**
- Caminho: Portal > Seleccionar servidor > Tab "SQL Diagnostics" > "TempDB"
- Endpoint: `GET /api/queries/tempdb/{server_id}`
- Dados: total_size_mb, used_mb, free_mb, free_percent, file_count

**P: Quais sessoes estao a consumir mais TempDB (villains)?**
- Caminho: Portal > Tab "SQL Diagnostics" > "TempDB" > Seccao "Villains"
- Endpoint: `GET /api/queries/tempdb-villains/{server_id}`
- Dados: session_id, login_name, tempdb_usage_mb, query_text, host_name

### IMPORTANCIA ALTA

**P: Os ficheiros do TempDB estao balanceados?**
- Caminho: Portal > Tab "SQL Diagnostics" > "TempDB" > Seccao de ficheiros
- Endpoint: `GET /api/queries/tempdb-space/{server_id}`
- Dados: file_name, size_mb, used_mb, free_mb — comparacao entre ficheiros

**P: Qual o crescimento do TempDB?**
- Caminho: Portal > Tab "SQL Diagnostics" > "TempDB" > Analise de crescimento
- Endpoint: `GET /api/queries/tempdb-growth-analysis/{server_id}`
- Dados: growth_rate, autogrow_events, current_size, recommended_size

---

## 9. QUERIES & PERFORMANCE

### IMPORTANCIA CRITICA

**P: Quais sao as queries mais lentas?**
- Caminho: Portal > Seleccionar servidor > Tab "SQL Diagnostics" > "Slow Queries"
- Endpoint: `GET /api/queries/slow-queries/{server_id}`
- Dados: query_text, total_elapsed_time_ms, execution_count, avg_elapsed_time, cpu_time, logical_reads

### IMPORTANCIA ALTA

**P: Existem indices em falta (missing indexes)?**
- Caminho: Portal > Tab "SQL Diagnostics" > "Missing Indexes"
- Endpoint: `GET /api/queries/missing-index-analysis/{server_id}`
- Dados: table_name, equality_columns, inequality_columns, included_columns, improvement_measure, user_seeks, CREATE INDEX statement

**P: Quais indices estao fragmentados?**
- Caminho: Portal > Tab "SQL Diagnostics" > "Index Fragmentation"
- Endpoint: `GET /api/queries/index-fragmentation/{server_id}`
- Dados: table_name, index_name, fragmentation_percent, page_count, recommendation (REBUILD/REORGANIZE)

**P: As estatisticas estao actualizadas?**
- Caminho: Portal > Tab "SQL Diagnostics" > "Statistics"
- Endpoint: `GET /api/queries/statistics/{server_id}`
- Dados: table_name, stats_name, last_updated, rows_sampled, modification_counter

**P: Posso diagnosticar uma query especifica?**
- Caminho: Portal > Tab "SQL Diagnostics" > Caixa "Diagnosticar Query" > Colar query
- Endpoint: `POST /api/queries/diagnose-query/{server_id}`
- Dados: Analise de indices relevantes, estatisticas, plano de execucao sugerido

### IMPORTANCIA MEDIA

**P: Qual o I/O por database?**
- Caminho: Portal > Tab "SQL Diagnostics" > "Database I/O"
- Endpoint: `GET /api/queries/database-io-stats/{server_id}`
- Dados: database_name, reads, writes, read_latency_ms, write_latency_ms

**P: Quantas conexoes activas existem por database?**
- Caminho: Portal > Tab "SQL Diagnostics" > "Connections"
- Endpoint: `GET /api/queries/database-connections/{server_id}`
- Dados: database_name, connection_count, active_sessions, idle_sessions

---

## 10. SERVICES & WINDOWS

### IMPORTANCIA CRITICA

**P: Os servicos do SQL Server estao a correr?**
- Caminho: Portal > Seleccionar servidor > Tab "Services"
- Endpoint: `GET /api/services/server/{server_id}`
- Dados: service_name (SQL Server, SQL Agent, SSRS, etc.), state (Running/Stopped), startup_type

**P: Algum servico parou inesperadamente?**
- Caminho: Portal > Tab "Services" > Verificar estado + logs
- Endpoint: `GET /api/services/server/{server_id}/logs/{service_name}`
- Dados: event_time, event_level, message, event_id

### IMPORTANCIA ALTA

**P: Qual o overview de servicos de todos os servidores?**
- Caminho: Portal > KPI Dashboard > Card "Services"
- Endpoint: `GET /api/services/overview`
- Dados: Por servidor: lista de servicos, estado, conta de servico

### IMPORTANCIA MEDIA

**P: Que eventos do Windows Event Log sao relevantes?**
- Caminho: Portal > Tab "Services" > Expandir logs
- Endpoint: `GET /api/monitoring/windows-events/{server_id}`
- Dados: event_id, source, level, timestamp, message

---

## 11. SECURITY & ENCRIPTACAO

### IMPORTANCIA CRITICA

**P: Quais databases estao encriptadas com TDE?**
- Caminho: Portal > Seleccionar servidor > Tab "Encrypted (TDE)"
- Endpoint: `GET /api/queries/tde-status/{server_id}`
- Dados: database_name, encryption_state, certificate_name, algorithm, key_length

**P: Os certificados TDE estao a expirar?**
- Caminho: Portal > Tab "Encrypted" > Coluna "Expiration"
- Endpoint: `GET /api/queries/tde-status/{server_id}`
- Dados: certificate_name, expiry_date, days_until_expiry

### IMPORTANCIA ALTA

**P: Existem problemas de seguranca na configuracao?**
- Caminho: Portal > Seleccionar servidor > Tab "Security"
- Endpoint: `GET /api/monitoring/security/server/{server_id}`
- Dados: Checks de autenticacao, permissoes excessivas, passwords fracas, orphaned users, modo de autenticacao

**P: Ha utilizadores orfaos (orphaned users)?**
- Caminho: Portal > Tab "Security" > Seccao "Orphaned Users"
- Endpoint: `GET /api/monitoring/security/server/{server_id}`
- Dados: user_name, database_name, tipo de orfandade

### IMPORTANCIA MEDIA

**P: Qual o modo de autenticacao do SQL Server?**
- Caminho: Portal > Tab "Security" > Seccao "Configuracao"
- Endpoint: `GET /api/monitoring/security/server/{server_id}`
- Dados: authentication_mode (Windows Only / Mixed Mode)

---

## 12. TRANSACTION LOGS

### IMPORTANCIA CRITICA

**P: Alguma database tem o log cheio (> 90%)?**
- Caminho: Portal > KPI Dashboard > Card "Transaction Logs" (vermelho)
- Endpoint: `GET /api/sqlserver-kpis/tlog-usage`
- Dados: Contagem de instancias com logs criticos, lista de databases afectadas

**P: O que esta a impedir o log de ser reutilizado (Log Reuse Wait)?**
- Caminho: Portal > Tab "Disk" > Seccao "Espaco Recuperavel" > Coluna "Log Reuse Wait"
- Endpoint: `GET /api/queries/log-space/{server_id}`
- Dados: database_name, log_reuse_wait (NOTHING, LOG_BACKUP, ACTIVE_TRANSACTION, REPLICATION, etc.)

### IMPORTANCIA ALTA

**P: Qual o tamanho e uso do transaction log por database?**
- Caminho: Portal > Tab "Disk" > Seccao "Espaco Recuperavel" > Tabela (filtrar por tipo LOG)
- Endpoint: `GET /api/queries/log-space/{server_id}`
- Dados: database_name, total_mb, used_mb, free_mb, free_pct, recovery_model

---

## 13. JOBS (SQL Agent)

### IMPORTANCIA CRITICA

**P: Quais jobs estao a falhar?**
- Caminho: Portal > Seleccionar servidor > Tab "Jobs"
- Endpoint: `GET /api/jobs/server/{server_id}`
- Dados: job_name, last_run_status (Failed/Succeeded), last_run_time, failure_message, step_name

**P: O SQL Agent esta a correr?**
- Caminho: Portal > Tab "Services" > Verificar "SQL Server Agent"
- Endpoint: `GET /api/services/server/{server_id}`
- Dados: SQL Server Agent state (Running/Stopped)

### IMPORTANCIA ALTA

**P: Qual a tendencia de falhas de jobs ao longo do tempo?**
- Caminho: Portal > Tab "Jobs" > Seccao "Tendencias"
- Endpoint: `GET /api/jobs/server/{server_id}/trends`
- Dados: Grafico temporal de success_rate, failure_count por dia/semana

**P: Quais jobs estao desabilitados?**
- Caminho: Portal > Tab "Jobs" > Filtrar por "Disabled"
- Endpoint: `GET /api/jobs/server/{server_id}`
- Dados: job_name, enabled (0/1), last_run_time

### IMPORTANCIA MEDIA

**P: Qual a duracao media de cada job?**
- Caminho: Portal > Tab "Jobs" > Coluna "Duration"
- Endpoint: `GET /api/jobs/server/{server_id}`
- Dados: job_name, last_run_duration, avg_duration

---

## 14. REDE & CONECTIVIDADE

### IMPORTANCIA CRITICA

**P: O servidor responde a ping (ICMP)?**
- Caminho: Portal > Network Diagnostics > Teste "ICMP Ping"
- Endpoint: `GET /api/network-diagnostics/network-test/{server_id}`
- Dados: ping_status (reachable/unreachable), response_time_ms, ttl

**P: A porta SQL esta acessivel (TCP)?**
- Caminho: Portal > Network Diagnostics > Teste "TCP Port"
- Endpoint: `GET /api/network-diagnostics/network-test/{server_id}`
- Dados: tcp_status, port_number, response_time

**P: A conexao ODBC funciona?**
- Caminho: Portal > Network Diagnostics > Teste "ODBC"
- Endpoint: `GET /api/network-diagnostics/network-test/{server_id}`
- Dados: odbc_status, error_message (se falhar), driver_version

### IMPORTANCIA ALTA

**P: O DNS resolve correctamente?**
- Caminho: Portal > Network Diagnostics > Teste "DNS Resolution"
- Endpoint: `GET /api/network-diagnostics/network-test/{server_id}`
- Dados: dns_status, resolved_ip, hostname

**P: Qual a latencia da conexao SQL?**
- Caminho: Portal > Network Diagnostics > Teste "Latency"
- Endpoint: `GET /api/network-diagnostics/network-test/{server_id}`
- Dados: query_latency_ms, connection_time_ms

**P: Posso fazer um teste rapido de rede?**
- Caminho: Portal > Network Diagnostics > Botao "Quick Test"
- Endpoint: `GET /api/network-diagnostics/network-test-quick/{server_id}`
- Dados: Resultado resumido dos 8 testes em camadas

---

## 15. KPI DASHBOARD (Visao Global)

### IMPORTANCIA CRITICA

**P: Qual o estado geral de todas as instancias?**
- Caminho: Portal > KPI Dashboard (pagina inicial)
- Endpoint: `GET /api/sqlserver-kpis/dashboard`
- Dados: Cards com contagem de problemas por tipo: Disk, T-Log, FileGroups, TempDB, Blocked Sessions, Backup, AlwaysOn, Services, Jobs, Index Fragmentation

**P: Quais instancias estao offline?**
- Caminho: Portal > KPI Dashboard > Card "Instances Off"
- Endpoint: `GET /api/sqlserver-kpis/instance-availability`
- Dados: Instancias que nao respondem a ping nos ultimos 15 minutos

**P: Quantas instancias tem problemas criticos em cada categoria?**
- Caminho: Portal > KPI Dashboard > Cards vermelhos (Critical)
- Endpoint: `GET /api/sqlserver-kpis/dashboard`
- Dados: critical_count e warning_count por KPI type, com breakdown por ambiente (PRD/QLT/TST/DEV)

### IMPORTANCIA ALTA

**P: Quais instancias especificas tem problemas num KPI?**
- Caminho: Portal > KPI Dashboard > Clicar num card > Modal com lista de instancias
- Endpoint: `GET /api/sqlserver-kpis/{kpi-type}` (ex: disk-usage, tlog-usage)
- Dados: Lista de instancias com detalhes por KPI, severity, metricas especificas

---

## 16. OVERVIEW & INVENTARIO

### IMPORTANCIA ALTA

**P: Quantos servidores/instancias estao configurados?**
- Caminho: Portal > Overview (pagina inicial apos login)
- Endpoint: `GET /api/overview-dashboard/summary`
- Dados: total_instances, healthy, warning, critical, distribuicao por ambiente

**P: Quais databases existem em cada instancia?**
- Caminho: Portal > Seleccionar servidor > Overview > Lista de databases
- Endpoint: `GET /api/overview-dashboard/instance/{instance_name}/databases`
- Dados: database_name, size_mb, recovery_model, state (ONLINE/OFFLINE)

**P: Como esta distribuida a saude das instancias?**
- Caminho: Portal > Overview > Grafico de distribuicao
- Endpoint: `GET /api/overview-dashboard/health-distribution`
- Dados: healthy_count, warning_count, critical_count, percentagens

### IMPORTANCIA MEDIA

**P: Posso pesquisar servidores e databases?**
- Caminho: Portal > Barra de pesquisa no topo
- Endpoint: `GET /api/v3/search?q={termo}`
- Dados: Resultados de servidores e databases que correspondem ao termo

**P: Qual o estado do cache do sistema?**
- Caminho: Endpoint directo
- Endpoint: `GET /api/v3/cache/stats`
- Dados: cache_hits, cache_misses, hit_rate, items_cached

---

## 17. RELATORIOS

### IMPORTANCIA ALTA

**P: Posso gerar um relatorio completo de disco?**
- Caminho: Portal > Tab "Disk" > Botao "Relatorio"
- Dados incluidos: Volumes, Latencia I/O, Espaco Recuperavel por Drive, Espaco Recuperavel por Database (Top 20), Findings e Recomendacoes

**P: Posso gerar um relatorio de backup?**
- Caminho: Portal > Tab "Backup" > Botao "Relatorio"
- Dados incluidos: Gaps, Health Score, Database status, Recomendacoes

**P: Posso gerar um relatorio de AlwaysOn?**
- Caminho: Portal > Tab "AlwaysOn" > Botao "Relatorio"
- Dados incluidos: Estado das replicas, databases, listener, findings

**P: Posso gerar um relatorio de Jobs?**
- Caminho: Portal > Tab "Jobs" > Botao "Relatorio"
- Dados incluidos: Jobs falhando, tendencias, recomendacoes

**P: Posso gerar um relatorio de Logs?**
- Caminho: Portal > Tab "Log" > Botao "Relatorio"
- Dados incluidos: Erros criticos, warnings, padroes

**P: Posso gerar um relatorio de Security?**
- Caminho: Portal > Tab "Security" > Botao "Relatorio"
- Dados incluidos: TDE status, orphaned users, permissoes, configuracao

### IMPORTANCIA MEDIA

**P: Posso exportar dados para CSV?**
- Caminho: Disponivel em varios modulos (Backup, Disk, Log Space, etc.) via botao "Exportar CSV"
- Dados: Ficheiro CSV com todas as metricas do modulo

---

## 18. USUARIOS & PERMISSOES

### IMPORTANCIA ALTA

**P: Quais utilizadores existem na instancia?**
- Caminho: Portal > Seleccionar servidor > Tab "Users"
- Endpoint: `GET /api/tab/users/{server_id}`
- Dados: login_name, type (SQL/Windows), default_database, create_date

### IMPORTANCIA MEDIA

**P: Quais permissoes tem cada utilizador?**
- Caminho: Portal > Tab "Users" > Expandir utilizador
- Endpoint: `GET /api/tab/users/{server_id}`
- Dados: Permissoes por database, roles de servidor

---

## 19. MIRRORING / LOG SHIPPING (Legacy)

### IMPORTANCIA MEDIA

**P: Qual o estado do mirroring?**
- Caminho: Portal > Tab "SQL Diagnostics"
- Endpoint: `GET /api/queries/mirroring/{server_id}`
- Dados: mirroring_state, principal_server, mirror_server, safety_level

---

# SECAO B — PERGUNTAS QUE O WATCHERDB NAO RESPONDE

---

## 1. DISPONIBILIDADE & HIGH AVAILABILITY

### IMPORTANCIA CRITICA

**P: Quando vai ocorrer o proximo failover?**
- Porque nao: Nao existe modelo preditivo de ML para failovers. O sistema so detecta eventos passados.
- O que fazer: Implementar analise de tendencias nos indicadores pre-failover (redo queue crescente, latencia de rede aumentando, disk I/O degradando) com modelo de previsao baseado em historico.

**P: Qual o RPO/RTO real se fizermos failover agora?**
- Porque nao: O sistema mostra estado de sincronizacao mas nao calcula o RPO (dados perdidos) nem RTO (tempo de recuperacao) real.
- O que fazer: Implementar calculo de RPO baseado em redo_queue_size × taxa de transaccao, e RTO baseado em tempo historico de failover + redo time.

### IMPORTANCIA ALTA

**P: Quanto tempo demorou o ultimo failover?**
- Porque nao: Os eventos de AG registam que houve failover mas nao a duracao exacta (tempo entre inicio e fim do processo).
- O que fazer: Correlacionar timestamps de eventos AG_STATE_CHANGE com DMVs de latencia para calcular duracao total.

---

## 2. BACKUP & RECUPERACAO

### IMPORTANCIA CRITICA

**P: Os backups sao restauraveis (integrity check)?**
- Porque nao: O sistema verifica se o backup existe mas NAO testa se pode ser restaurado com sucesso. Um backup corrompido passa despercebido.
- O que fazer: Implementar scheduled RESTORE VERIFYONLY automatico ou DBCC CHECKDB nos backups, com registo de resultado.

**P: Qual o tamanho estimado do restore e quanto tempo demoraria?**
- Porque nao: Nao existe calculo de tempo estimado de restore baseado em tamanho × velocidade I/O.
- O que fazer: Guardar metricas de restore time de testes anteriores, usar tamanho do backup × throughput medio para estimar.

### IMPORTANCIA ALTA

**P: Os backups estao a ser copiados para offsite/cloud?**
- Porque nao: O sistema so ve backups locais no SQL Server (MSDB). Nao tem visibilidade sobre copias externas (tape, Azure, S3).
- O que fazer: Integrar com agentes de backup enterprise (Veeam, CommVault, Azure Backup) via API ou verificar existencia de ficheiros em paths remotos.

**P: Qual a politica de retencao de backups?**
- Porque nao: O sistema mostra historico de backups mas nao conhece a politica definida (ex: manter 30 dias Full, 7 dias Diff).
- O que fazer: Permitir configurar politicas de retencao por servidor/database e alertar quando a realidade diverge da politica.

---

## 3. DISCO & ARMAZENAMENTO

### IMPORTANCIA ALTA

**P: Quando exactamente vai encher cada disco (com confianca estatistica)?**
- Porque nao: Ha forecast basico por filegroup mas nao existe predicao por volume com intervalos de confianca e sazonalidade.
- O que fazer: Implementar Prophet ou modelo ARIMA com dados historicos de espaco por volume, incluindo sazonalidade (ex: final de mes = mais dados).

**P: Qual o custo de adicionar mais disco?**
- Porque nao: O sistema nao tem integracao com informacoes de infraestrutura/custos (SAN, cloud storage pricing).
- O que fazer: Integrar com CMDB ou catalogo de storage para calcular custo por GB adicional.

**P: Ha ficheiros que podem ser movidos para outro disco?**
- Porque nao: O sistema mostra onde os ficheiros estao mas nao analisa se mover ficheiros entre drives melhoraria o balanceamento.
- O que fazer: Implementar analise de balanceamento: comparar I/O por drive com capacidade, sugerir relocacao de ficheiros menos activos para drives menos utilizados.

### IMPORTANCIA MEDIA

**P: O storage (SAN/NAS) tem problemas de performance?**
- Porque nao: O sistema ve latencia de I/O ao nivel do SQL Server mas nao tem visibilidade do storage fisico (queue depth, cache hit ratio da SAN).
- O que fazer: Integrar com APIs de storage (EMC, NetApp, Pure Storage) para correlacionar latencia SQL com metricas de storage.

---

## 4. MEMORIA

### IMPORTANCIA ALTA

**P: Ha memory leaks no SQL Server ou aplicacoes?**
- Porque nao: O sistema mostra snapshot actual de memoria mas nao rastreia tendencia ao longo do tempo para detectar leaks (crescimento continuo sem libertacao).
- O que fazer: Guardar historico de metricas de memoria (buffer pool, clerk types) e detectar padroes de crescimento monotono.

**P: Qual a quantidade optima de memoria para este workload?**
- Porque nao: A recomendacao actual e baseada em regra fixa (% do total fisico). Nao analisa o workload real.
- O que fazer: Analisar PLE historico, buffer cache hit ratio, e working set size para recomendar memoria baseada no workload observado.

---

## 5. CPU

### IMPORTANCIA ALTA

**P: Qual a tendencia de uso de CPU ao longo do dia/semana?**
- Porque nao: O sistema mostra CPU instantaneo mas nao guarda historico para tendencias.
- O que fazer: Implementar colecta periodica de CPU e armazenar em tabela historica. Gerar graficos de tendencia e detectar picos recorrentes.

**P: Quando vai ser necessario adicionar mais CPUs/cores?**
- Porque nao: Sem historico de CPU, nao ha como prever necessidade futura.
- O que fazer: Com dados historicos de CPU, implementar forecast de crescimento de carga e alertar quando uso medio ultrapassar threshold (ex: 70% sustentado).

---

## 6. QUERIES & PERFORMANCE

### IMPORTANCIA CRITICA

**P: Qual o plano de execucao completo (XML) de uma query?**
- Porque nao: O sistema mostra informacoes basicas de queries mas nao captura nem exibe o plano de execucao XML completo.
- O que fazer: Implementar captura de actual execution plan via sys.dm_exec_query_plan e renderizar visualmente (ou integrar com Plan Explorer).

### IMPORTANCIA ALTA

**P: Quais queries degradaram de performance recentemente?**
- Porque nao: Nao ha comparacao temporal de performance de queries (regressao de plano).
- O que fazer: Usar Query Store (se activo) para detectar regressoes: comparar avg_duration do ultimo periodo com media historica. Alertar quando degradacao > threshold.

**P: Qual o impacto de uma query no sistema global?**
- Porque nao: Queries sao mostradas individualmente mas nao ha score de impacto global (CPU + I/O + memoria + bloqueio combinado).
- O que fazer: Implementar "query impact score" ponderado: (cpu_time × w1 + reads × w2 + writes × w3 + wait_time × w4) / total_resources.

---

## 7. JOBS

### IMPORTANCIA ALTA

**P: Porque e que este job falhou (root cause)?**
- Porque nao: O sistema mostra a mensagem de erro do job mas nao faz analise de causa raiz (ex: falhou por disco cheio? por timeout? por permissao?).
- O que fazer: Implementar classificacao automatica de erros de jobs: parsear mensagem de erro, categorizar (space, permission, timeout, dependency), sugerir resolucao.

**P: Ha conflitos de schedule entre jobs?**
- Porque nao: O sistema mostra schedules individuais mas nao detecta overlaps ou conflitos de recursos entre jobs.
- O que fazer: Analisar schedules de todos os jobs, detectar sobreposicoes temporais, e identificar jobs que competem por recursos (CPU, I/O) no mesmo periodo.

---

## 8. SEGURANCA

### IMPORTANCIA CRITICA

**P: O servidor esta em conformidade com CIS Benchmarks / STIG?**
- Porque nao: Os checks de seguranca sao basicos (modo auth, orphaned users, TDE). Nao cobrem o CIS Benchmark completo para SQL Server (~200 controlos).
- O que fazer: Implementar os controlos do CIS SQL Server Benchmark como regras de verificacao, gerar relatorio de compliance com score e desvios.

### IMPORTANCIA ALTA

**P: Quem acedeu a que dados (audit trail)?**
- Porque nao: O sistema nao tem acesso a SQL Audit ou Extended Events de auditoria. Nao regista quem consultou/modificou dados.
- O que fazer: Integrar com SQL Server Audit (C2 audit trace ou Extended Events), recolher eventos de acesso e apresentar timeline de actividade.

**P: Ha actividade SQL injection ou tentativas de intrusao?**
- Porque nao: O sistema nao analisa padroes de acesso para detectar anomalias ou ataques.
- O que fazer: Implementar analise de padroes de login (falhas repetidas, horarios anomalos, IPs desconhecidos) e queries suspeitas (UNION SELECT, xp_cmdshell).

---

## 9. OPERACOES & AUTOMACAO

### IMPORTANCIA ALTA

**P: Posso executar accoes correctivas directamente do WatcherDB?**
- Porque nao: O sistema e 100% read-only. Nao executa operacoes de escrita (shrink, rebuild, kill session, restart service).
- O que fazer: Implementar modulo de accoes controladas com aprovacao, audit trail, e rollback. Ex: "Aprovar REBUILD INDEX X" → executa e regista resultado.

**P: Posso agendar tarefas de manutencao?**
- Porque nao: O sistema nao tem scheduler proprio. Depende de SQL Agent jobs configurados externamente.
- O que fazer: Implementar scheduler interno para tarefas comuns: index rebuild, statistics update, backup verification, com janela de manutencao configuravel.

**P: Posso receber alertas por email/Teams quando algo critico acontece?**
- Porque nao: O sistema mostra alertas no portal mas nao envia notificacoes push (email, SMS, Teams, Slack).
- O que fazer: Implementar servico de notificacoes com integracao SMTP (email), webhook (Teams/Slack), e configuracao de thresholds por tipo de alerta.

---

## 10. HISTORICO & TENDENCIAS

### IMPORTANCIA CRITICA

**P: Como evoluiu a saude do servidor nas ultimas semanas/meses?**
- Porque nao: A maioria dos dados sao snapshots instantaneos. Nao ha armazenamento historico sistematico de todas as metricas.
- O que fazer: Implementar servico de colecta periodica que armazena metricas-chave (CPU, memoria, disco, PLE, bloqueios) numa base de dados historica. Gerar dashboards de tendencia.

### IMPORTANCIA ALTA

**P: Quais foram os incidentes dos ultimos 30 dias?**
- Porque nao: Nao existe registo de incidentes. O sistema mostra estado actual mas nao guarda historico de eventos criticos.
- O que fazer: Implementar "incident log" automatico: quando um threshold critico e ultrapassado, registar evento com timestamp, metricas, duracao ate resolucao.

---

## 11. INTEGRACAO & CORRELACAO

### IMPORTANCIA ALTA

**P: O problema de disco esta a causar lentidao nas queries?**
- Porque nao: Os modulos sao independentes. Disco mostra disco, queries mostra queries. Nao ha correlacao cruzada automatica.
- O que fazer: Implementar "correlation engine": quando disco > 95%, verificar automaticamente se latencia de I/O subiu e se queries ficaram mais lentas. Apresentar visao unificada de causa-efeito.

**P: Qual o impacto do patch/reboot no performance?**
- Porque nao: O sistema nao tem conceito de "eventos de manutencao" para comparar before/after.
- O que fazer: Permitir marcar "janelas de manutencao" e gerar comparacao automatica de metricas antes vs depois do evento.

**P: Como se comparam servidores do mesmo ambiente (benchmarking)?**
- Porque nao: Nao ha comparacao lado-a-lado entre servidores (exceto memoria por AG).
- O que fazer: Implementar comparacao multi-servidor: seleccionar 2+ servidores, ver CPU/memoria/disco/performance em paralelo, identificar outliers.

---

## 12. APLICACAO & NEGOCIO

### IMPORTANCIA ALTA

**P: Qual o impacto no negocio quando este servidor falha?**
- Porque nao: O sistema nao conhece a relacao servidor → aplicacao → processo de negocio.
- O que fazer: Implementar mapeamento servidor-aplicacao-negocio (CMDB integration), com classificacao de criticidade de negocio.

**P: Quais aplicacoes estao a usar cada database?**
- Porque nao: O sistema ve conexoes (hostname, program_name) mas nao mapeia para aplicacoes de negocio.
- O que fazer: Enriquecer dados de sessoes com catalogo de aplicacoes (hostname → app name → owner → SLA).

**P: Qual o SLA actual de cada servico?**
- Porque nao: Nao existe calculo de SLA/uptime baseado em historico de disponibilidade.
- O que fazer: Implementar calculo de uptime: (tempo_total - tempo_indisponivel) / tempo_total × 100. Requere historico de disponibilidade com polling regular.

---

## 13. ORACLE & OUTROS SGBD

### IMPORTANCIA MEDIA

**P: Posso monitorizar bases de dados Oracle?**
- Porque nao: Apesar de existirem vestígios de router Oracle no codigo, o suporte e muito limitado/incompleto.
- O que fazer: Implementar modulos Oracle completos (tablespaces, ASM, RAC, Data Guard, AWR) com driver cx_Oracle/oracledb.

**P: Posso monitorizar PostgreSQL/MySQL?**
- Porque nao: O sistema e exclusivamente focado em SQL Server.
- O que fazer: Abstrair a camada de queries para suportar multiplos SGBD. Implementar drivers e queries especificas para cada motor.

---

# RESUMO QUANTITATIVO

## Perguntas Respondidas (Secao A)

| Categoria | Criticas | Altas | Medias | Baixas | Total |
|-----------|---------|-------|--------|--------|-------|
| AlwaysOn | 4 | 3 | 1 | 0 | 8 |
| Backup | 4 | 3 | 2 | 0 | 9 |
| Disco/Storage | 6 | 5 | 2 | 0 | 13 |
| FileGroups | 1 | 2 | 0 | 0 | 3 |
| Memoria | 3 | 3 | 2 | 0 | 8 |
| CPU | 2 | 3 | 1 | 0 | 6 |
| Bloqueios/Sessoes | 3 | 2 | 0 | 0 | 5 |
| TempDB | 2 | 2 | 0 | 0 | 4 |
| Queries/Performance | 1 | 4 | 2 | 0 | 7 |
| Services | 2 | 1 | 1 | 0 | 4 |
| Security/TDE | 2 | 2 | 1 | 0 | 5 |
| Transaction Logs | 2 | 1 | 0 | 0 | 3 |
| Jobs | 2 | 2 | 1 | 0 | 5 |
| Rede | 3 | 2 | 0 | 0 | 5 |
| KPI Dashboard | 3 | 1 | 0 | 0 | 4 |
| Overview | 0 | 3 | 2 | 0 | 5 |
| Relatorios | 0 | 6 | 1 | 0 | 7 |
| Users | 0 | 1 | 1 | 0 | 2 |
| Mirroring | 0 | 0 | 1 | 0 | 1 |
| **TOTAL** | **40** | **46** | **18** | **0** | **104** |

## Perguntas NAO Respondidas (Secao B)

| Categoria | Criticas | Altas | Medias | Total |
|-----------|---------|-------|--------|-------|
| AlwaysOn/HA | 2 | 1 | 0 | 3 |
| Backup | 2 | 2 | 0 | 4 |
| Disco | 0 | 2 | 1 | 3 |
| Memoria | 0 | 2 | 0 | 2 |
| CPU | 0 | 2 | 0 | 2 |
| Queries | 1 | 2 | 0 | 3 |
| Jobs | 0 | 2 | 0 | 2 |
| Seguranca | 1 | 2 | 0 | 3 |
| Operacoes | 0 | 3 | 0 | 3 |
| Historico | 1 | 1 | 0 | 2 |
| Integracao | 0 | 3 | 0 | 3 |
| Negocio | 0 | 3 | 0 | 3 |
| Outros SGBD | 0 | 0 | 2 | 2 |
| **TOTAL** | **7** | **25** | **3** | **35** |

## Score Global

- **Perguntas respondidas**: 104 (75%)
- **Perguntas nao respondidas**: 35 (25%)
- **Perguntas criticas respondidas**: 40 de 47 (85%)
- **Perguntas criticas nao respondidas**: 7 de 47 (15%)

---

# PROXIMOS PASSOS PRIORITARIOS

Para aumentar a cobertura, por ordem de impacto:

1. **Historico de metricas** — Colecta periodica de CPU, memoria, disco, PLE (desbloqueia tendencias, previsoes, SLA)
2. **Notificacoes** — Email/Teams para alertas criticos (desbloqueia monitoring proactivo)
3. **Verificacao de backup** — RESTORE VERIFYONLY automatico (desbloqueia confianca em DR)
4. **Correlacao cruzada** — Ligar disco ↔ queries ↔ CPU (desbloqueia root cause analysis)
5. **Accoes correctivas** — Modulo de execucao controlada (desbloqueia operacoes)
6. **Compliance** — CIS Benchmark checks (desbloqueia auditoria)
7. **Query regression** — Integracao com Query Store (desbloqueia deteccao de degradacao)
