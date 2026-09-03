// =====================================================================
// WatcherDB V3.3 — Catalogo curado de eventos Windows (tab Log)
// Conteudo estatico e offline por design: clientes banking sem rede
// externa; explicacao AI e' Pro-only (FEATURE_MATRIX) e nao entra aqui.
// Lookup: "fonte:id" primeiro, depois "fonte" (fallback generico).
// Fontes por-instancia (MSSQL$I01, SQLAgent$I01) normalizam para a
// fonte base antes do lookup. Evento desconhecido = sem icone (smart
// default: o catalogo cresce organicamente, sem tabela de config).
// =====================================================================

window.WIN_EVENTS_CATALOG = {
    // ---- Storage / virtualizacao -----------------------------------
    'storvsc:129': {
        titulo: 'Reset ao adaptador de storage virtual (Hyper-V)',
        indica: 'Um I/O ficou pendurado >30s sem resposta do storage do host; o Windows emitiu reset ao RaidPort. Repetido a cada minuto = episodio continuo de storage nao responsivo.',
        acao: 'Escalar a virtualizacao/storage: latencia do CSV/LUN do host e backups/checkpoints da VM na janela. Cruzar com errorlog SQL (I/O >15s) e KPI de latencia de disco.'
    },
    'storvsc': {
        titulo: 'Driver de storage sintetico Hyper-V (VM)',
        indica: 'Eventos desta fonte reportam o caminho de disco entre a VM e o host Hyper-V.',
        acao: 'Avaliar em conjunto com a equipa de virtualizacao.'
    },
    'vmbus': {
        titulo: 'Canal de comunicacao VM <-> host Hyper-V',
        indica: 'Problemas neste canal afectam todos os dispositivos sinteticos da VM.',
        acao: 'Verificar integration services e estado do host.'
    },
    'disk:153': {
        titulo: 'I/O repetido com sucesso apos retry',
        indica: 'O SO teve de repetir uma operacao de disco. Sinal precoce de storage instavel (caminho, controladora ou disco).',
        acao: 'Monitorizar frequencia; se recorrente, envolver storage. Verificar MPIO/caminhos.'
    },
    'disk:157': {
        titulo: 'Disco removido inesperadamente',
        indica: 'O SO perdeu acesso ao disco (LUN desapareceu). Tipico de falha de caminho SAN ou rescan.',
        acao: 'Urgente se o disco tem dados SQL: validar SAN/MPIO com storage.'
    },
    'disk:7': {
        titulo: 'Bloco defeituoso (bad block)',
        indica: 'O dispositivo tem um bloco danificado. Risco de corrupcao em ficheiros que o usem.',
        acao: 'Envolver storage/hardware; correr DBCC CHECKDB nas bases do volume.'
    },
    'disk:11': {
        titulo: 'Erro de controladora',
        indica: 'A controladora reportou erro no driver. Pode preceder falhas maiores.',
        acao: 'Verificar firmware/drivers e saude fisica com a equipa de hardware.'
    },
    'ntfs:55': {
        titulo: 'Corrupcao na estrutura do NTFS',
        indica: 'O sistema de ficheiros detectou corrupcao no volume. Risco directo para ficheiros de dados/log.',
        acao: 'Agendar chkdsk; identificar bases no volume e correr DBCC CHECKDB. Envolver Windows/storage.'
    },
    'ntfs:98': {
        titulo: 'Estado de saude do volume (informativo)',
        indica: 'Reporte de saude emitido durante operacoes VSS/snapshot. Informativo, mas monitorizado de proposito.',
        acao: 'Sem acao se isolado; observar se acompanhado de eventos 55/137.'
    },
    'ntfs:137': {
        titulo: 'Log de transacoes do NTFS falhou',
        indica: 'Tipicamente durante snapshots VSS (backup): o log transacional do filesystem nao conseguiu escrever.',
        acao: 'Correlacionar com janela de backup/VSS; se recorrente, rever espaco e saude do volume.'
    },
    'iscsiprt:9': {
        titulo: 'Target iSCSI nao respondeu no tempo',
        indica: 'Timeout na ligacao iSCSI ao storage. Latencia ou perda de pacotes na rede de storage.',
        acao: 'Verificar rede iSCSI (switches, MTU, congestao) com storage/rede.'
    },
    'iscsiprt:20': {
        titulo: 'Ligacao ao target iSCSI perdida',
        indica: 'A sessao iSCSI caiu. Discos podem ter ficado indisponiveis momentaneamente.',
        acao: 'Validar redundancia MPIO e estabilidade da rede de storage.'
    },
    'volsnap:25': {
        titulo: 'Snapshots eliminados (diff area cheia)',
        indica: 'O espaco reservado para shadow copies esgotou e o Windows apagou snapshots. Backups baseados em VSS podem ter falhado.',
        acao: 'Rever espaco da shadow storage (vssadmin) e janela de backups.'
    },
    'vss:8193': {
        titulo: 'Erro interno do VSS',
        indica: 'Falha numa rotina do Volume Shadow Copy Service. Backups por snapshot podem falhar.',
        acao: 'Ver detalhe do erro; validar writers (vssadmin list writers) e reiniciar servico VSS se degradado.'
    },
    'vss:12292': {
        titulo: 'Falha ao criar shadow copy',
        indica: 'O VSS nao conseguiu criar o snapshot. Backup dessa janela provavelmente falhou.',
        acao: 'Cruzar com jobs de backup na mesma hora; verificar writers e espaco.'
    },
    // ---- Sistema / energia / servicos ------------------------------
    'service control manager:7000': {
        titulo: 'Servico falhou o arranque',
        indica: 'O servico nao arrancou (dependencia, credencial, timeout ou binario em falta).',
        acao: 'Ver mensagem do servico em causa; se for SQL/Agent, prioridade maxima.'
    },
    'service control manager:7011': {
        titulo: 'Timeout a aguardar resposta de servico',
        indica: 'Um servico nao respondeu em 30s. Em servidores sob pressao de CPU/disco surge em cascata.',
        acao: 'Correlacionar com CPU/disco no periodo; se recorrente no mesmo servico, investigar esse servico.'
    },
    'service control manager:7031': {
        titulo: 'Servico terminou inesperadamente (com recovery)',
        indica: 'O processo do servico morreu; o SCM vai aplicar a accao de recuperacao configurada.',
        acao: 'Identificar o servico e a causa da morte (crash no Application log a mesma hora).'
    },
    'service control manager:7034': {
        titulo: 'Servico terminou inesperadamente (sem recovery)',
        indica: 'O processo morreu e NAO ha accao de recuperacao: o servico ficou parado.',
        acao: 'Arrancar o servico apos diagnostico; se for critico, configurar recovery.'
    },
    'microsoft-windows-kernel-power:41': {
        titulo: 'Reboot sem shutdown limpo',
        indica: 'O sistema reiniciou sem desligar corretamente: crash (bugcheck), corte de energia ou reset do host/hardware.',
        acao: 'Verificar minidumps/BSOD e, em VM, eventos do host. Validar recovery das bases SQL apos o arranque.'
    },
    'eventlog:6008': {
        titulo: 'Shutdown inesperado anterior',
        indica: 'O ultimo desligar nao foi limpo. Regista a hora do incidente.',
        acao: 'Usar a hora registada para correlacionar com crash/energia; validar consistencia das bases.'
    },
    'user32:1074': {
        titulo: 'Shutdown/restart iniciado (quem e porque)',
        indica: 'Regista o processo e utilizador que pediram o reboot (ex: windows update, admin).',
        acao: 'Informativo: usar para atribuir a causa de um reboot planeado.'
    },
    'microsoft-windows-whea-logger:47': {
        titulo: 'Erro de hardware corrigido (WHEA)',
        indica: 'A plataforma corrigiu um erro de hardware (memoria/CPU/PCIe). Recorrencia indica componente a degradar.',
        acao: 'Se frequente, envolver hardware: memoria ECC ou CPU podem estar a falhar.'
    },
    'microsoft-windows-resource-exhaustion-detector:2004': {
        titulo: 'Esgotamento de memoria virtual',
        indica: 'O Windows esgotou a memoria virtual e nomeia os processos que mais consomem.',
        acao: 'Ver processos nomeados; em servidor SQL, rever max server memory e outros consumidores.'
    },
    // ---- Aplicacao / crash -----------------------------------------
    'application error:1000': {
        titulo: 'Crash de aplicacao',
        indica: 'Um processo terminou com excecao. O evento nomeia o modulo em falta (faulting module).',
        acao: 'Identificar o processo/modulo; se for sqlservr.exe, tratar como incidente critico.'
    },
    'application hang:1002': {
        titulo: 'Aplicacao bloqueada (hang)',
        indica: 'Um processo deixou de responder e foi terminado.',
        acao: 'Verificar recursos (CPU/memoria/disco) no periodo e recorrencia do mesmo processo.'
    },
    '.net runtime:1026': {
        titulo: 'Excecao .NET nao tratada',
        indica: 'Aplicacao .NET terminou com excecao. Normalmente acompanhada de Application Error 1000.',
        acao: 'Ver stack no evento; encaminhar a equipa da aplicacao em causa.'
    },
    'windows error reporting:1001': {
        titulo: 'Relatorio de erro gerado',
        indica: 'Registo do Windows Error Reporting apos um crash/hang. Complementa o evento 1000/1002.',
        acao: 'Usar os detalhes (bucket) para diagnostico do crash associado.'
    },
    // ---- SQL Server ------------------------------------------------
    'mssqlserver:823': {
        titulo: 'SQL: erro de I/O do sistema operativo',
        indica: 'O SO devolveu erro numa leitura/escrita de pagina. Forte indicador de problema de storage; risco de corrupcao.',
        acao: 'CRITICO: DBCC CHECKDB na base afectada; envolver storage. Nao ignorar mesmo se pontual.'
    },
    'mssqlserver:824': {
        titulo: 'SQL: erro de consistencia logica (checksum/torn page)',
        indica: 'A pagina foi lida mas falhou a validacao logica: corrupcao ja materializada em disco.',
        acao: 'CRITICO: DBCC CHECKDB imediato; preparar restore/page restore. A causa-raiz costuma ser storage.'
    },
    'mssqlserver:825': {
        titulo: 'SQL: leitura passou apos retry (aviso precoce)',
        indica: 'Uma leitura falhou e passou a segunda tentativa. Antecamara dos erros 823/824.',
        acao: 'Tratar como aviso serio de storage: verificar discos antes que evolua para corrupcao.'
    },
    'mssqlserver:833': {
        titulo: 'SQL: I/O a demorar mais de 15 segundos',
        indica: 'Pedidos de I/O pendurados >15s no ficheiro indicado. Storage lento ou congelado.',
        acao: 'Correlacionar com eventos storvsc/disk na mesma janela; escalar a storage com o ficheiro/base nomeados.'
    },
    'mssqlserver:1205': {
        titulo: 'SQL: deadlock',
        indica: 'Transacoes em impasse; uma foi escolhida como vitima.',
        acao: 'Analisar no modulo de Deadlocks do WatcherDB (grafo, vitima, queries).'
    },
    'mssqlserver:18456': {
        titulo: 'SQL: login falhou',
        indica: 'Tentativa de autenticacao rejeitada. O "state" no texto indica a razao (password, base default, conta desativada).',
        acao: 'Se em massa, pode ser aplicacao com credencial errada ou tentativa de acesso indevido; ver origem (IP/host).'
    },
    'mssqlserver:3041': {
        titulo: 'SQL: BACKUP falhou',
        indica: 'Um comando de backup nao completou. A mensagem detalhada aparece imediatamente antes no errorlog.',
        acao: 'Ver modulo Backup do WatcherDB para o job e causa; validar destino/espaco/VSS.'
    },
    'mssqlserver:17063': {
        titulo: 'SQL: erro reportado pelo motor',
        indica: 'Mensagem generica do motor SQL registada no Application log.',
        acao: 'Ler o texto completo do evento; consultar o errorlog SQL da mesma hora.'
    },
    'mssqlserver': {
        titulo: 'Evento do motor SQL Server',
        indica: 'Mensagem emitida pelo servico SQL Server desta instancia.',
        acao: 'Consultar o errorlog SQL (tab Log > SQL) da mesma janela temporal para o contexto completo.'
    },
    'sqlserveragent': {
        titulo: 'Evento do SQL Server Agent',
        indica: 'Mensagem do servico Agent (jobs, alertas, arranque/paragem).',
        acao: 'Cruzar com o modulo Jobs do WatcherDB.'
    },
    'sqlbrowser': {
        titulo: 'Evento do SQL Browser',
        indica: 'O SQL Browser resolve instancias nomeadas para portas dinamicas. Falhas afectam ligacoes por nome\\instancia.',
        acao: 'Se parado, ligacoes a instancias nomeadas sem porta explicita falham; validar servico.'
    },
    'mssql$': {
        titulo: 'Evento do motor SQL Server (instancia nomeada)',
        indica: 'Mensagem emitida pelo servico SQL Server desta instancia.',
        acao: 'Consultar o errorlog SQL da mesma janela para o contexto completo.'
    },
    // ---- Rede / seguranca ------------------------------------------
    'schannel:36887': {
        titulo: 'Alerta TLS fatal recebido',
        indica: 'O peer terminou o handshake TLS com alerta fatal (versao/cipher incompativel ou certificado).',
        acao: 'Se em massa, identificar a aplicacao cliente com TLS antigo; rever protocolos ativos.'
    },
    'schannel:36874': {
        titulo: 'Handshake TLS sem cipher em comum',
        indica: 'Cliente e servidor nao partilham cipher suite. Ligacao rejeitada.',
        acao: 'Alinhar configuracao TLS entre cliente e servidor (tipicamente cliente legado).'
    },
    'netlogon:5719': {
        titulo: 'Sem Domain Controller disponivel',
        indica: 'A maquina nao contactou nenhum DC. Autenticacoes AD (incl. logins Windows no SQL) podem falhar.',
        acao: 'Verificar rede/DNS para os DCs; comum durante arranque ou problemas de rede.'
    },
    'tcpip:4227': {
        titulo: 'Esgotamento de portas efemeras TCP',
        indica: 'A maquina esgotou portas de saida: aplicacoes com fugas de ligacoes ou carga anormal.',
        acao: 'Identificar processo com muitas ligacoes (netstat); rever pooling de ligacoes das aplicacoes.'
    },
    'dns client events:1014': {
        titulo: 'Timeout na resolucao DNS',
        indica: 'Resolucao de um nome demorou/falhou. Pode causar lentidao em ligacoes por hostname.',
        acao: 'Se recorrente, reportar a equipa de rede/DNS com os nomes afectados.'
    },
    'srv:2013': {
        titulo: 'Disco proximo do limite',
        indica: 'O SO avisa que um disco esta quase cheio.',
        acao: 'Ver modulo Disk do WatcherDB; libertar espaco antes de afectar ficheiros SQL.'
    },
    // ---- Diagnostico / ruido conhecido -----------------------------
    'perflib:1008': {
        titulo: 'Falha ao abrir contador de performance',
        indica: 'Um provider de perf counters falhou. Normalmente ruido pos-instalacao/patch, nao afecta o servico.',
        acao: 'Sem acao se isolado; se monitorizacao de contadores falhar, reconstruir contadores (lodctr /R).'
    },
    'wmi:10': {
        titulo: 'Filtro WMI invalido',
        indica: 'Query WMI registada por software antigo ficou orfa apos patch. Ruido benigno conhecido.',
        acao: 'Ignorar salvo investigacao de WMI; fix documentado da Microsoft se quiser silenciar.'
    }
};

// Lookup com normalizacao de fonte: minusculas + instancias nomeadas
// (MSSQL$I01 -> mssql$ ; SQLAgent$I01 -> sqlserveragent).
window.winEventCatalogLookup = function (source, eventId) {
    if (!source) return null;
    let src = String(source).toLowerCase().trim();
    if (src.startsWith('mssql$')) src = 'mssql$';
    else if (src.startsWith('sqlagent$') || src.startsWith('sqlserveragent')) src = 'sqlserveragent';
    const cat = window.WIN_EVENTS_CATALOG;
    return cat[src + ':' + String(eventId)] || cat[src] || null;
};
