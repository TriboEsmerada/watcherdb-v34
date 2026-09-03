# Manual do Utilizador -- WatcherDB V3.3 Standard Edition

**Plataforma de Monitorizacao de Bases de Dados SQL Server**
**Banking-grade, on-premise, zero phone-home**
**Documento revisto: 22 de Abril de 2026 (audit S2-9 sweep)**

> ℹ️ Este manual tinha origem num baseline interno V3.1 (Marco 2026) e
> foi actualizado para V3.3 Standard Edition. Para a versao canonica
> actual usar [USER_GUIDE_PT.md](USER_GUIDE_PT.md) (versao completa) ou
> [MANUAL_SIMPLIFICADO_PT.md](MANUAL_SIMPLIFICADO_PT.md) (DBA junior).

---

## Indice

1. [Introducao](#1-introducao)
2. [Primeiro Acesso](#2-primeiro-acesso)
3. [Interface Principal](#3-interface-principal)
4. [Modulos de Monitorizacao](#4-modulos-de-monitorizacao)
   - 4.1 [Overview](#41-overview)
   - 4.2 [Always On](#42-always-on)
   - 4.3 [Backup Analysis](#43-backup-analysis)
   - 4.4 [Space Analysis](#44-space-analysis)
   - 4.5 [Disk Volumes](#45-disk-volumes)
   - 4.6 [TDE Encryption](#46-tde-encryption)
   - 4.7 [CPU Analysis](#47-cpu-analysis)
   - 4.8 [Memory Analysis](#48-memory-analysis)
   - 4.9 [Services](#49-services)
   - 4.10 [Log Analysis](#410-log-analysis)
   - 4.11 [SQL Diagnostics](#411-sql-diagnostics)
   - 4.12 [Security](#412-security)
   - 4.13 [Users Analysis](#413-users-analysis)
   - 4.14 [Jobs Analysis](#414-jobs-analysis)
5. [KPIs](#5-dashboard-de-kpis)
6. [SQL Diagnostics e Custom Queries](#6-sql-diagnostics-e-custom-queries)
7. [Preferencias e Sessao](#7-preferencias-e-sessao)
8. [Configuracoes (Settings)](#8-configuracoes-settings)
9. [Painel de Controlo Admin (WatcherDB Control)](#9-painel-de-controlo-admin-watcherdb-control)
10. [Resolucao de Problemas / FAQ](#10-resolucao-de-problemas--faq)

---

## 1. Introducao

### O que e o WatcherDB

O WatcherDB e uma plataforma web de monitorizacao de bases de dados SQL Server, banking-grade e 100% on-premise. Permite acompanhar em tempo real o estado de dezenas a centenas de instancias SQL Server, centralizando num unico portal toda a informacao necessaria para operacao e troubleshooting.

### Para quem se destina

- **Administradores de Bases de Dados (DBA):** monitorizacao diaria, diagnostico de problemas, analise de performance.
- **Operadores:** verificacao rapida do estado dos servidores e servicos.
- **Analistas:** consulta de metricas, KPIs e relatorios de capacidade.

### Requisitos

- **Navegador web** actualizado (recomendado: Microsoft Edge, Google Chrome ou Mozilla Firefox).
- **Acesso a rede corporativa** da TAP (ou VPN, se aplicavel).
- **Credenciais de acesso** ao WatcherDB (username e password fornecidos pela equipa de DBA).

### Como aceder

1. Abra o navegador web.
2. Introduza o endereco do WatcherDB na barra de enderecos (endereco fornecido pela equipa de DBA).
3. O ecra de login sera apresentado automaticamente.

---

## 2. Primeiro Acesso

### Ecra de Login

Ao aceder ao WatcherDB, e apresentado um ecra de autenticacao com o logotipo da plataforma e dois campos de preenchimento.

**Como iniciar sessao:**

1. Introduza o seu **username** no primeiro campo.
2. Introduza a sua **password** no segundo campo.
3. Clique no botao **Entrar** ou pressione a tecla Enter.
4. Se as credenciais estiverem correctas, o portal principal sera carregado automaticamente.

### Tipos de conta

Existem quatro perfis de utilizador, cada um com diferentes niveis de acesso:

- **Admin:** acesso total, incluindo gestao de utilizadores e configuracoes do sistema.
- **Analyst:** acesso a todas as funcionalidades de monitorizacao e analise.
- **Operator:** acesso as funcionalidades operacionais de monitorizacao.
- **Viewer:** acesso apenas de leitura a informacao de monitorizacao.

### Bloqueio de conta (lockout)

Por razoes de seguranca, a conta e bloqueada temporariamente apos **5 tentativas falhadas** consecutivas de login. O bloqueio dura **15 minutos**, apos os quais pode tentar novamente. Se o problema persistir, contacte um administrador.

### Terminar sessao (logout)

Para terminar a sessao:

1. Clique no seu **nome de utilizador** no canto superior direito do ecra.
2. No menu que aparece, seleccione **Logout**.
3. Sera redireccionado para o ecra de login.

> **Nota:** Se a sessao expirar (apos 24 horas sem renovacao), o ecra de login e apresentado automaticamente.

---

## 3. Interface Principal

A interface do WatcherDB esta organizada em quatro zonas principais: **cabecalho**, **barra lateral**, **area de navegacao por separadores** e **area de conteudo**.

### 3.1 Cabecalho (Header)

A barra superior contem:

- **Logotipo WatcherDB:** identificacao visual da plataforma.
- **Campo de pesquisa de servidores:** permite procurar rapidamente qualquer servidor pelo nome ou identificador. A medida que escreve, e apresentada uma lista de sugestoes (auto-completar).
- **Botao Ping:** testa a conectividade com o servidor seleccionado. Fica activo apenas quando um servidor esta seleccionado.
- **Botao KPIs:** acede ao painel central de indicadores de performance (ver capitulo 5).
- **Botao Control (apenas para Admins):** abre o Painel de Controlo de administracao (ver capitulo 9).
- **Selector de idioma:** permite alternar entre Portugues, Ingles e Espanhol.
- **Badge do utilizador:** mostra o nome e perfil do utilizador com sessao activa. Ao clicar, abre um menu com opcoes de perfil, acesso ao KPIs, Settings, Painel de Controlo (se Admin) e Logout.
- **Botao de Configuracoes (engrenagem):** abre o painel de configuracoes do utilizador (ver capitulo 8).

### 3.2 Barra Lateral (Sidebar)

A barra lateral a esquerda mostra a **lista de servidores monitorizados** com o total de servidores disponiveis entre parenteses.

**Funcionalidades:**

- **Expandir/recolher:** clique no titulo "SERVIDORES" para expandir ou recolher a barra lateral. Por defeito, inicia recolhida.
- **Seleccionar servidor:** clique no nome de um servidor para o seleccionar. O conteudo da area principal sera actualizado com os dados desse servidor.
- **Indicadores de estado:** cada servidor na lista pode apresentar indicadores visuais do seu estado (online, com alertas, offline).

### 3.3 Navegacao por Separadores (Tabs)

Apos seleccionar um servidor, a area de conteudo apresenta:

- **Cabecalho do servidor:** nome, identificador e botoes de navegacao para os diferentes modulos.
- **Botoes de modulo:** organizados em duas linhas, permitem aceder rapidamente a cada modulo de monitorizacao:
  - **Primeira linha:** Overview, Always On, Backup, Space, Disk, Encrypted
  - **Segunda linha:** CPU, Memory, Services, Log, SQL Diag, Security, Users, Jobs
- **Separadores dinamicos:** cada modulo aberto cria um separador no topo da area de conteudo. E possivel ter varios separadores abertos em simultaneo e alternar entre eles.
- **Botao de diagnostico de rede:** permite executar um diagnostico de conectividade detalhado ao servidor seleccionado.
- **Botao de fechar:** fecha todas as abas do servidor actual.

### 3.4 Area de Conteudo

E a zona principal do ecra onde e apresentada a informacao do modulo seleccionado. O conteudo muda conforme o modulo e o servidor escolhidos.

---

## 4. Modulos de Monitorizacao

Cada modulo apresenta informacao especifica sobre um aspecto da monitorizacao do servidor seleccionado. Para aceder a qualquer modulo, seleccione primeiro um servidor na barra lateral e depois clique no botao do modulo pretendido.

### 4.1 Overview

**O que mostra:** Visao geral e consolidada do estado do servidor seleccionado. Apresenta cards resumo com informacao sobre o estado das bases de dados, servicos, backups, espaco em disco e performance.

**Para que serve:** Permite ter uma visao rapida e imediata da saude geral do servidor, identificando rapidamente areas que necessitam de atencao.

**Como utilizar:**

1. Seleccione um servidor na barra lateral.
2. Clique em **Overview** (e o modulo apresentado por defeito ao seleccionar um servidor).
3. Analise os cards de resumo. Indicadores a verde significam estado normal; indicadores a amarelo representam avisos; indicadores a vermelho indicam situacoes criticas.
4. O sistema verifica automaticamente a conectividade com o servidor antes de carregar os dados. Se o servidor estiver offline, e apresentada uma mensagem de erro com detalhes.
5. Na seccao inferior, e apresentada a lista de bases de dados da instancia com o respectivo estado.

**Cards de informacao disponíveis:**

- Estado da instancia e versao do SQL Server
- Estado dos servicos (SQL Server Engine, SQL Agent)
- Resumo de backups
- Utilizacao de disco
- Informacao de CPU e memoria
- Estado do Always On (se aplicavel)
- Lista de bases de dados com estado, recovery model e tamanho

### 4.2 Always On

**O que mostra:** Estado detalhado dos grupos de disponibilidade (Availability Groups) configurados no servidor. Inclui informacao sobre replicas, bases de dados sincronizadas, listeners e eventos de failover.

**Para que serve:** Monitorizar a alta disponibilidade das bases de dados criticas, detectar problemas de sincronizacao e acompanhar eventos de failover.

**Como utilizar:**

1. Seleccione um servidor que participe num grupo de disponibilidade.
2. Clique em **Always On**.
3. Consulte o estado de cada replica (primaria, secundaria) e de cada base de dados no grupo.
4. Verifique o estado de sincronizacao: "SYNCHRONIZED" indica funcionamento normal; qualquer outro estado requer atencao.
5. Consulte o historico de eventos de failover para identificar padroes de instabilidade.

**Informacoes apresentadas:**

- Nome do Availability Group e listener
- Estado de cada replica (papel, modo de sincronizacao, estado de ligacao)
- Estado de cada base de dados no grupo (sincronizada, a sincronizar, em falta)
- Historico de eventos de failover (ultimos 30 dias)
- Padroes de failover detectados automaticamente

### 4.3 Backup Analysis

**O que mostra:** Analise completa dos backups de todas as bases de dados do servidor. Inclui o ultimo backup realizado por tipo (Full, Differential, Transaction Log), lacunas na cadeia de backups e estado geral da cobertura.

**Para que serve:** Garantir que todas as bases de dados possuem backups actualizados e identificar rapidamente bases de dados sem proteccao adequada.

**Como utilizar:**

1. Seleccione um servidor e clique em **Backup**.
2. No topo, consulte os cards de resumo: total de bases de dados, bases com backup recente, bases com backup em falta e cobertura de backup.
3. Na tabela principal, cada linha representa uma base de dados com detalhes sobre o ultimo backup de cada tipo.
4. Bases de dados com backup em falta ou desactualizado sao realcadas a vermelho.
5. Utilize os filtros disponíveis para ajustar o periodo de analise (dias) e para incluir ou excluir bases de dados de sistema.

**Filtros disponíveis (configuraveis nas Settings):**

- Periodo de analise (1 a 90 dias)
- Incluir bases de dados de sistema (master, model, msdb)
- Filtro por tipo de backup
- Filtro por horas desde o ultimo backup
- Deteccao de lacunas na cadeia de backups

### 4.4 Space Analysis

**O que mostra:** Utilizacao detalhada de espaco nas bases de dados, incluindo ficheiros de dados e ficheiros de log. Apresenta informacao sobre tamanho total, espaco utilizado, espaco livre e percentagem de utilizacao por filegroup.

**Para que serve:** Identificar bases de dados com pouco espaco disponivel, prever quando o espaco se esgotara e planear expansoes.

**Como utilizar:**

1. Seleccione um servidor e clique em **Space**.
2. Consulte a lista de bases de dados com a respectiva utilizacao de espaco.
3. Bases de dados com utilizacao elevada (acima de 80%) sao realcadas a amarelo; acima de 90%, a vermelho.
4. Clique numa base de dados para ver os detalhes por filegroup.
5. Se a base de dados for **tempdb**, esta disponivel um botao para diagnosticos adicionais especificos.

**Informacoes adicionais:**

- Previsao de crescimento (quando o espaco se esgotara)
- Historico de crescimento por filegroup
- Identificacao de oportunidades de compactacao

### 4.5 Disk Volumes

**O que mostra:** Informacao sobre os volumes de disco fisico do servidor, incluindo tamanho total, espaco utilizado, espaco livre e percentagem de utilizacao.

**Para que serve:** Monitorizar o espaco fisico disponivel nos discos do servidor, prevenindo situacoes de disco cheio que podem causar falhas nas bases de dados.

**Como utilizar:**

1. Seleccione um servidor e clique em **Disk**.
2. Consulte a lista de volumes com a respectiva utilizacao.
3. Volumes com utilizacao acima de 95% sao realcados como criticos e requerem accao imediata.
4. Volumes com utilizacao entre 80% e 95% sao realcados como avisos.

**Alertas:**

- **Critico (vermelho):** Menos de 10% de espaco livre. Risco de falha iminente.
- **Aviso (amarelo):** Menos de 20% de espaco livre. Planear expansao.

### 4.6 TDE Encryption

**O que mostra:** Estado da encriptacao transparente de dados (Transparent Data Encryption) nas bases de dados do servidor. Identifica quais bases de dados estao encriptadas e o estado dos certificados.

**Para que serve:** Auditar a conformidade de seguranca relativamente a encriptacao de dados em repouso.

**Como utilizar:**

1. Seleccione um servidor e clique em **Encrypted**.
2. Consulte a lista de bases de dados com o respectivo estado de encriptacao.
3. Verifique a validade dos certificados de encriptacao.

### 4.7 CPU Analysis

**O que mostra:** Metricas de utilizacao de CPU do servidor, incluindo carga actual, historico recente e processos que mais consomem CPU.

**Para que serve:** Identificar situacoes de sobrecarga de processamento e os processos responsaveis.

**Como utilizar:**

1. Seleccione um servidor e clique em **CPU**.
2. Consulte a percentagem de utilizacao actual.
3. Analise o historico para identificar padroes de carga.
4. Verifique os wait stats relacionados com CPU para diagnosticar gargalos.

**Indicadores:**

- **Normal (verde):** Utilizacao abaixo de 80%.
- **Aviso (amarelo):** Utilizacao entre 80% e 90%.
- **Critico (vermelho):** Utilizacao acima de 90%.

### 4.8 Memory Analysis

**O que mostra:** Metricas de utilizacao de memoria do servidor, incluindo memoria total, memoria disponivel, page life expectancy e contadores de paginacao.

**Para que serve:** Detectar situacoes de pressao de memoria que podem degradar a performance das bases de dados.

**Como utilizar:**

1. Seleccione um servidor e clique em **Memory**.
2. Consulte a memoria total e disponivel.
3. Analise os contadores de paginacao (pages per second). Valores elevados de "Page Reads per Second" indicam pressao de memoria critica.
4. Verifique o Page Life Expectancy: valores abaixo de 300 segundos indicam pressao de memoria.

**Indicadores:**

- **Normal (verde):** Utilizacao abaixo de 80%.
- **Aviso (amarelo):** Utilizacao entre 80% e 90%.
- **Critico (vermelho):** Utilizacao acima de 90%.

### 4.9 Services

**O que mostra:** Estado de todos os servicos relacionados com o SQL Server no servidor, incluindo o motor de base de dados (SQL Server Engine), o agente de tarefas (SQL Agent) e outros servicos auxiliares.

**Para que serve:** Verificar rapidamente se todos os servicos necessarios estao em execucao.

**Como utilizar:**

1. Seleccione um servidor e clique em **Services**.
2. Consulte a lista de servicos com o respectivo estado (Running, Stopped, etc.).
3. Servicos parados que deveriam estar em execucao sao realcados a vermelho.

### 4.10 Log Analysis

**O que mostra:** Analise dos registos de erro do SQL Server (SQL Server Error Log). Inclui erros de severidade elevada, falhas de login, problemas de I/O e outros eventos relevantes.

**Para que serve:** Investigar problemas, identificar padroes de erros e monitorizar eventos criticos no servidor.

**Como utilizar:**

1. Seleccione um servidor e clique em **Log**.
2. Consulte os eventos registados, organizados por severidade.
3. Utilize os filtros disponiveis para limitar a pesquisa por periodo (horas) e tipo de evento.
4. Eventos de severidade 17 ou superior merecem atencao especial, pois indicam erros graves.

**Filtros disponíveis (configuraveis nas Settings):**

- Periodo de analise (horas)
- Tipo de evento

### 4.11 SQL Diagnostics

**O que mostra:** Painel de diagnostico com queries de troubleshooting predefinidas e personalizadas. Permite executar consultas de diagnostico directamente no servidor seleccionado.

**Para que serve:** Realizar troubleshooting aprofundado, identificar problemas de performance, bloqueios, indices em falta e outras situacoes que requerem analise detalhada.

**Como utilizar:** Ver capitulo 6 para informacao detalhada.

### 4.12 Security

**O que mostra:** Analise de seguranca do servidor, incluindo membros de roles criticos, permissoes excessivas e politicas de palavras-passe.

**Para que serve:** Auditar a seguranca das bases de dados, identificar riscos e garantir conformidade com as politicas de seguranca.

**Como utilizar:**

1. Seleccione um servidor e clique em **Security**.
2. Consulte o resumo de seguranca com os indicadores principais.
3. Analise os membros de roles criticos (sysadmin, etc.).
4. Verifique se existem utilizadores com permissoes excessivas.

### 4.13 Users Analysis

**O que mostra:** Analise detalhada dos utilizadores e logins configurados no servidor, incluindo utilizadores orfaos, politicas de palavras-passe fracas e utilizadores inactivos.

**Para que serve:** Gerir e auditar as contas de acesso as bases de dados, identificar riscos de seguranca relacionados com contas de utilizador.

**Como utilizar:**

1. Seleccione um servidor e clique em **Users**.
2. Consulte o resumo: total de utilizadores, orfaos, com permissoes excessivas, inactivos e com palavras-passe fracas.
3. **Utilizadores orfaos:** contas de base de dados sem login correspondente ao nivel do servidor. Devem ser corrigidas ou removidas.
4. **Palavras-passe fracas:** logins SQL com politicas de complexidade de palavras-passe desactivadas ou expiracao desactivada. Devem ser corrigidos.
5. **Roles criticos:** membros de roles com privilegios elevados que devem ser revistos periodicamente.

### 4.14 Jobs Analysis

**O que mostra:** Analise completa das tarefas agendadas (SQL Agent Jobs) do servidor, incluindo estado actual, historico de execucao, falhas recentes, tendencias de duracao e conflitos de agendamento.

**Para que serve:** Monitorizar a execucao das tarefas de manutencao, identificar falhas recorrentes, detectar tarefas com duracao crescente e conflitos de agendamento entre tarefas.

**Como utilizar:**

1. Seleccione um servidor e clique em **Jobs**.
2. Consulte os cards de resumo: total de jobs, jobs com falha nas ultimas 24 horas e cobertura de manutencao.
3. Na tabela principal, consulte o estado de cada job, ultima execucao e resultado.
4. Jobs com falha sao realcados a vermelho.
5. O sistema analisa automaticamente tendencias de duracao (ultimos 7 e 30 dias) e alerta quando a duracao aumenta mais de 50%.
6. A analise de conflitos de agendamento identifica tarefas que se sobrepoe no tempo.

**Indicadores de cobertura de manutencao:**

- **Excelente (verde):** Cobertura de manutencao acima de 95%.
- **Aviso (amarelo):** Cobertura entre 50% e 80%.
- **Critico (vermelho):** Cobertura abaixo de 50%.

---

## 5. KPIs

### O que e

O KPIs e um painel central que apresenta indicadores-chave de performance (KPIs) de todos os servidores monitorizados, numa unica vista consolidada. Nao requer seleccionar um servidor especifico.

### Para que serve

Permite ter uma visao panoramica do estado de toda a infraestrutura de bases de dados, identificando rapidamente quais servidores ou areas requerem atencao.

### Como aceder

- Clique no botao **KPIs** no cabecalho (barra azul com icone de grafico).
- Ou, atraves do menu do perfil de utilizador, seleccione **KPIs**.

### KPIs disponiveis

O dashboard apresenta cards para diversos indicadores, organizados por categorias:

- **Disponibilidade de bases de dados:** mostra quantas bases de dados estao online/offline.
- **Utilizacao de disco:** utilizacao por volume.
- **Transaction Log:** utilizacao dos ficheiros de log.
- **Always On:** saude dos grupos de disponibilidade.
- **Filegroup Usage:** utilizacao por filegroup.
- **Sessoes bloqueadas:** sessoes actualmente bloqueadas.
- **Disponibilidade de instancias:** instancias online/offline.
- **Estado de backups:** backups em falta ou desactualizados.
- **Falhas de SQL Agent Jobs:** jobs com falha recente.
- **Fragmentacao de indices:** indices com fragmentacao elevada.
- **Estatisticas desactualizadas:** bases de dados com estatisticas desactualizadas.
- **TempDB Usage:** utilizacao do TempDB.

### Como interpretar os cards

Cada card de KPI apresenta:

- **Titulo:** nome do indicador.
- **Valor principal:** numero ou percentagem que resume o estado actual.
- **Indicador visual:** cor do card que reflecte a gravidade (verde = normal, amarelo = aviso, vermelho = critico).
- **Ambiente:** os cards podem apresentar um indicador do ambiente (Producao, Qualidade, Teste).

### Modo compacto

O dashboard oferece um modo compacto para visualizar mais indicadores em simultaneo:

1. Clique no botao de modo compacto (disponivel no topo do dashboard).
2. Os cards sao reduzidos em tamanho, mostrando apenas o titulo e valor principal.
3. Clique novamente para voltar ao modo normal.

### Actualizacao automatica

O dashboard pode ser configurado para se actualizar automaticamente. Os intervalos disponiveis sao: 5 segundos, 15 segundos, 30 segundos e 1 minuto. Esta configuracao e feita nas Settings (ver capitulo 8).

### Personalizar KPIs visiveis

E possivel escolher quais KPIs sao apresentados no dashboard e a sua ordenacao:

1. Abra as **Settings** (icone de engrenagem no cabecalho).
2. Na seccao **KPIs**, seleccione os KPIs que pretende visualizar.
3. Escolha a ordenacao: por categoria, alfabetica ou personalizada.
4. Se escolher ordenacao personalizada, pode arrastar os cards para os reorganizar.
5. Clique em **Salvar** para aplicar.

---

## 6. SQL Diagnostics e Custom Queries

### O que e

O modulo SQL Diagnostics permite executar queries de diagnostico predefinidas e personalizadas directamente nos servidores monitorizados. As queries estao organizadas em tres categorias: **standard**, **analise** e **personalizadas**.

### Queries predefinidas (standard)

Estas queries estao incluidas na plataforma e cobrem os cenarios de troubleshooting mais comuns:

- **Blocking:** hierarquia de bloqueios activos no servidor.
- **Deadlocks:** eventos de deadlock recentes.
- **Database I/O Stats:** estatisticas de entrada/saida por base de dados.
- **Slow Queries:** queries mais lentas em execucao.
- **Log Space:** utilizacao dos ficheiros de transaction log.
- **SQL Agent Jobs:** estado e historico dos jobs agendados.
- **Sessions:** sessoes activas no servidor.
- **Index Fragmentation:** indices com fragmentacao elevada.
- **TempDB:** utilizacao e diagnostico do TempDB.
- **File Growth:** historico de crescimento de ficheiros (requer seleccao de base de dados).
- **Statistics:** estado das estatisticas.
- **Mirroring:** estado do mirroring de bases de dados.
- **Backup:** informacao detalhada de backups.
- **Database Connections:** ligacoes activas por base de dados.

### Queries de analise

Queries mais avancadas para analise detalhada:

- **Filegroup Growth History:** historico de crescimento por filegroup (requer seleccao de base de dados).
- **Filegroup Growth Forecast:** previsao de crescimento por filegroup (requer seleccao de base de dados).
- **Backup History Analysis:** analise do historico de backups.
- **Missing Index Analysis:** indices em falta recomendados pelo SQL Server (requer seleccao de base de dados).
- **Diagnose Slow Query:** ferramenta para diagnosticar uma query especifica.

### Como executar uma query

1. Seleccione um servidor na barra lateral.
2. Clique no botao **SQL Diag** para abrir o modulo.
3. Clique no card da query que pretende executar.
4. Se a query requerer a seleccao de uma base de dados, seleccione-a na lista apresentada.
5. Os resultados sao apresentados em formato de tabela.
6. E possivel consultar o codigo SQL da query clicando no botao de visualizacao de script.

### Queries personalizadas (Custom Queries)

Existem dois tipos de queries personalizadas:

#### Queries globais

- Partilhadas por todos os utilizadores.
- Geridas pela equipa de administracao.
- Apenas de leitura para utilizadores nao-administradores.
- Aparecem na seccao "Custom" do SQL Diagnostics.

#### Queries pessoais ("Minhas Queries")

- Criadas e visiveis apenas para o proprio utilizador.
- Guardadas nas preferencias do utilizador e sincronizadas entre dispositivos.
- Editaveis e removiveis a qualquer momento.

**Como criar uma query pessoal:**

1. No modulo SQL Diagnostics, aceda ao gestor de queries personalizadas.
2. Clique em **Nova Query Pessoal**.
3. Preencha o nome da query.
4. Introduza o codigo SQL (apenas queries de leitura -- o sistema bloqueia comandos perigosos como DELETE, DROP, ALTER, etc.).
5. Guarde a query.
6. A query ficara disponivel na lista de queries do SQL Diagnostics.

**Como configurar quais queries sao visiveis:**

1. Abra as **Settings** (icone de engrenagem).
2. Na seccao **SQL Diagnostics**, marque ou desmarque as queries que pretende visualizar.
3. Clique em **Salvar**.

---

## 7. Preferencias e Sessao

### O que e guardado

O WatcherDB guarda automaticamente as preferencias de cada utilizador, incluindo:

- Configuracao do KPIs (quais KPIs mostrar, ordenacao, modo compacto).
- Configuracao do SQL Diagnostics (queries visiveis).
- Configuracoes de backup (periodo de analise, inclusao de bases de dados de sistema).
- Configuracoes de logs (periodo de analise, tipo de evento).
- Ordenacao da lista de servidores (por frequencia de acesso, alfabetica ou por ambiente).
- Estado da barra lateral (expandida ou recolhida).
- Intervalo de actualizacao automatica do dashboard de KPIs.
- Tempo limite de requisicoes (timeout).
- Modo de depuracao (debug).
- Frequencia de pesquisa de servidores.
- Ultimo separador activo e ultimo servidor seleccionado.
- Queries SQL pessoais.

### Restauracao automatica

Ao iniciar sessao, as preferencias sao restauradas automaticamente a partir do servidor. Isto permite que as suas configuracoes sejam mantidas mesmo que utilize um computador diferente ou limpe os dados do navegador.

### Sincronizacao

As preferencias sao sincronizadas automaticamente com o servidor a cada 5 segundos apos qualquer alteracao. Ao terminar sessao, as preferencias pendentes sao enviadas para o servidor antes da sessao ser encerrada.

### Isolamento por utilizador

Cada utilizador tem as suas preferencias isoladas. As configuracoes de um utilizador nao afectam as de outro. O sistema utiliza um prefixo unico por utilizador para garantir este isolamento.

---

## 8. Configuracoes (Settings)

### Como aceder

Clique no **icone de engrenagem** no canto superior direito do cabecalho, ou aceda atraves do menu do perfil de utilizador.

### Seccoes de configuracao

#### Refresh do KPIs

- **O que faz:** Define o intervalo de actualizacao automatica do KPIs.
- **Opcoes disponiveis:** Sem refresh automatico, 5 segundos, 15 segundos, 30 segundos, 1 minuto.
- **Como configurar:** Seleccione o intervalo pretendido e clique em **Salvar**.

#### Gestao de Servidores

- **O que faz:** Permite visualizar e editar a lista de servidores monitorizados.
- **Para que serve:** Adicionar ou remover servidores da monitorizacao.
- **Como utilizar:** Edite o conteudo apresentado no editor e clique em **Salvar Configuracao**. Para reverter alteracoes, clique em **Recarregar**.
- **Atencao:** Alteracoes requerem recarregar a pagina para serem aplicadas.

#### Analise de Backup

- **Periodo padrao de analise (dias):** Define quantos dias de historico de backup sao analisados (1 a 90 dias).
- **Incluir bases de dados de sistema:** Se activado, inclui master, model e msdb na analise de backup.
- **Como configurar:** Ajuste os valores e clique em **Salvar**.

#### Interface

- **Ordenacao da lista de servidores:** Define como os servidores sao ordenados na barra lateral.
  - *Por frequencia:* os servidores mais acedidos pelo utilizador aparecem primeiro.
  - *Alfabetica:* ordem alfabetica por nome.
  - *Por ambiente:* agrupados por ambiente (Producao, Qualidade, Teste).
- **Barra lateral recolhida por defeito:** Se activado, a barra lateral inicia recolhida ao carregar a pagina.
- **Como configurar:** Seleccione as opcoes pretendidas e clique em **Salvar**.

#### KPIs

- **Ordenacao dos KPIs:** Por categoria, alfabetica ou personalizada (arrastar para reorganizar).
- **KPIs visiveis:** Escolha quais indicadores sao apresentados no dashboard. Pode seleccionar ou desmarcar individualmente, ou utilizar os botoes "Selecionar Todos" e "Desmarcar Todos".
- **Como configurar:** Ajuste as opcoes e clique em **Salvar Configuracao do Dashboard**.

#### Performance

- **Timeout de requisicoes (segundos):** Define o tempo maximo de espera para cada requisicao ao servidor (5 a 300 segundos). O valor por defeito e 30 segundos.
- **Logs de debug:** Se activado, apresenta informacao de depuracao detalhada na consola do navegador. Util para diagnosticar problemas na plataforma.
- **Como configurar:** Ajuste os valores e clique em **Salvar**.

#### SQL Diagnostics

- **Queries visiveis:** Escolha quais queries de diagnostico sao apresentadas no modulo SQL Diagnostics.
- **Como configurar:** Marque ou desmarque as queries pretendidas e clique em **Salvar Configuracao do SQL Diagnostics**.

---

## 9. Painel de Controlo Admin (WatcherDB Control)

### O que e

O WatcherDB Control e o painel de administracao da plataforma. Apenas utilizadores com perfil **Admin** tem acesso.

### Como aceder

- Clique no botao **Control** (botao roxo) no cabecalho do portal principal.
- Ou, atraves do menu do perfil de utilizador, seleccione **Control Panel**.
- O painel abre numa nova aba do navegador.

### Separadores disponiveis

#### 9.1 Utilizadores

**O que mostra:** Lista completa de todos os utilizadores registados no sistema.

**Informacao apresentada por utilizador:**

- Username, nome completo, email
- Perfil (Role): Admin, Analyst, Operator, Viewer
- Tipo de autenticacao: Local (palavras-passe armazenadas no sistema) ou AD (Active Directory)
- Estado: Activo ou Desactivado
- Ultimo login

**Accoes disponiveis:**

- **Criar novo utilizador:** Clique em **Novo User**, preencha os campos (username, password, nome, email, role) e clique em **Criar**.
- **Alterar perfil (role):** Seleccione o novo perfil na coluna "Role" da tabela. A alteracao e aplicada imediatamente.
- **Activar/Desactivar conta:** Clique no botao **Activar** ou **Desactivar** na linha do utilizador.
- **Filtrar utilizadores:** Utilize o campo de pesquisa para filtrar por username ou nome.

**Cards de resumo:**

- Total de utilizadores
- Utilizadores activos
- Numero de administradores
- Utilizadores desactivados

> **Nota:** Nao e possivel alterar o perfil ou desactivar a sua propria conta.

#### 9.2 Auth Log (Registo de Autenticacao)

**O que mostra:** Historico de eventos de autenticacao, incluindo logins com sucesso, logins falhados e alteracoes de palavras-passe.

**Informacao apresentada:**

- Data e hora do evento
- Username
- Tipo de accao (Login Success, Login Failed, Password Change)
- Endereco IP de origem
- Detalhes adicionais

**Filtros disponiveis:**

- Filtro por username
- Filtro por tipo de accao

**Cards de resumo:**

- Total de eventos
- Logins com sucesso
- Logins falhados (realcado a vermelho se o numero for elevado)

#### 9.3 Sessoes Activas

**O que mostra:** Duas seccoes de informacao sobre sessoes de utilizadores.

**"Online Agora":**

- Lista de utilizadores actualmente ligados ao sistema.
- Indicador visual verde para cada utilizador online.
- Username, nome, perfil, endereco IP e tempo desde a ultima actividade.
- Actualiza automaticamente a cada 30 segundos.

**"Sessoes Recentes (24h)":**

- Historico de sessoes das ultimas 24 horas.
- Username, nome, perfil, endereco IP, hora de login e tempo decorrido.
- Indicador visual para utilizadores que ainda estao online.

**Cards de resumo:**

- Numero de utilizadores online neste momento
- Total de sessoes nas ultimas 24 horas

#### 9.4 Configuracoes do Sistema

**O que mostra:** Configuracoes gerais do sistema agrupadas em seccoes.

**Seccoes apresentadas:**

- **Autenticacao:** Tempo de expiracao da sessao, numero maximo de tentativas de login falhadas, duracao do bloqueio de conta.
- **Active Directory:** Se a autenticacao por Active Directory esta activada, dominio, servidor e role por defeito para novos utilizadores AD.
- **Ambiente:** Nome do servidor, servidor de intelligence e base de dados utilizada.

---

## 10. Resolucao de Problemas / FAQ

### "Nao consigo fazer login"

**Possiveis causas e solucoes:**

1. **Username ou password incorrectos:** Verifique as credenciais. O username e sensivel a maiusculas/minusculas.
2. **Conta bloqueada:** Apos 5 tentativas falhadas, a conta e bloqueada durante 15 minutos. Aguarde ou contacte um administrador.
3. **Conta desactivada:** A conta pode ter sido desactivada por um administrador. Contacte a equipa de DBA.
4. **Sessao expirada:** Se estava ligado e recebeu o ecra de login, a sessao expirou apos 24 horas. Faca login novamente.

### "O servidor aparece como offline"

**Possiveis causas e solucoes:**

1. **O servidor esta efectivamente desligado ou inacessivel.** Verifique com a equipa de infraestrutura.
2. **Problema de rede/VPN.** Verifique a sua ligacao a rede corporativa.
3. **Problemas de credenciais ODBC.** As credenciais de acesso ao SQL Server podem ter expirado. Contacte a equipa de DBA.
4. **Utilize o botao Ping** no cabecalho para executar um diagnostico de conectividade detalhado ao servidor.

### "Os dados parecem desactualizados"

**Possiveis causas e solucoes:**

1. **Cache do navegador.** Pressione Ctrl+F5 para forcar o recarregamento completo da pagina.
2. **Intervalo de actualizacao.** Os dados sao obtidos dos servidores com intervalos de cache (entre 30 segundos e 5 minutos, conforme o modulo). Aguarde alguns momentos.
3. **Timeout de requisicao.** Se um servidor for lento a responder, a requisicao pode ter excedido o tempo limite. Aumente o timeout nas Settings (ver capitulo 8).

### "Um modulo nao carrega ou mostra erro"

**Possiveis causas e solucoes:**

1. **Seleccione um servidor primeiro.** Alguns modulos requerem que um servidor esteja seleccionado.
2. **O servidor pode nao suportar a funcionalidade.** Por exemplo, o modulo Always On so funciona em servidores com Availability Groups configurados.
3. **Timeout.** Aumente o timeout nas Settings se os dados demoram a carregar.
4. **Active o modo de debug** nas Settings para obter informacao detalhada na consola do navegador (pressione F12 para abrir).

### "As minhas configuracoes desapareceram"

As preferencias sao sincronizadas automaticamente com o servidor. Se as configuracoes desaparecerem:

1. Verifique se esta ligado com o username correcto.
2. Faca logout e login novamente para forcar a restauracao das preferencias.
3. As preferencias sao isoladas por utilizador -- as configuracoes de outro utilizador nao afectam as suas.

### "Nao vejo o botao Control Panel"

O botao de acesso ao Painel de Controlo (WatcherDB Control) so e visivel para utilizadores com perfil **Admin**. Se necessitar de acesso administrativo, contacte um administrador.

### "A interface esta num idioma diferente"

Utilize o **selector de idioma** no cabecalho (junto ao nome de utilizador) para alternar entre Portugues, Ingles e Espanhol.

### "Como exportar dados ou relatorios?"

[VERIFICAR COM EQUIPA] -- Funcionalidades de exportacao (PDF, CSV) podem estar disponiveis em modulos especificos. Consulte a equipa de DBA para confirmar as opcoes disponiveis na versao actual.

### Contacto para suporte

Para questoes nao cobertas por este manual, contacte o suporte comercial do vendor WatcherDB (ver licenca / documento de compra para contacto).

---

*Manual do Utilizador -- WatcherDB V3.1*
*Ultima actualizacao: 23 de Marco de 2026*
