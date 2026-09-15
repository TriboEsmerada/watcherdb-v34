# -*- coding: utf-8 -*-
"""A3 (2026-09-15) -- ligar os KPI criticos que faltam ao aviso e ao sino, com a classificacao aprovada.

Classificacao aprovada pelo owner a 15/09 ("concordo com as recomendacoes"), do parecer da persona DBA
cliente, revista pelo watcherdb-frontend-specialist (consenso com tres ajustes, incorporados):

  LIGAR sem condicao       backup_status.failed_count, mirroring_status.unhealthy_count
  LIGAR com duracao        cpu_critical (10 min), memory_critical (5 min; a view ja e' tendencia de 30 min),
                           disk_latency.critical_count (10 min), tempdb_status.critical_count (10 min);
                           histerese de 15 min: voltar a 0 e reaparecer antes disso e' o mesmo episodio
  LIGAR so' os criticos    jobs_status: Job_Type DBCC, Replication, AlwaysOn. Backup e Log ficam de fora
                           porque ja sao o aviso de backup; Index, Statistics, Shrink, Cleanup e Other nao
                           acordam ninguem
  AGRUPAR                  lock_count e blocked_users na familia das sessoes bloqueadas; processes_alarm na
                           familia do CPU. Ajuste do especialista: sao fontes independentes, portanto o valor
                           da familia e' o MAXIMO das fontes (um lock longo sem sessao bloqueada nao fica mudo)
  NAO LIGAR                deadlocks (sem baseline), error_log (18456 contamina), service_status (recolha
                           parada desde 13/05). A linha de servicos deixa de mostrar 0 verde: fica cinzenta,
                           sem numero, com "sem recolha desde 13/05".

Duracao em TEMPO DE RELOGIO: a resposta do dashboard nao traz carimbo do instantaneo, portanto contar
leituras media o polling, nao o problema. Ajustes do especialista: o relogio de duracao persiste em
localStorage (um F5 a meio de um incidente ja nao reinicia a prova) e reinicia quando passam mais de
15 min sem leitura fresca (dados stale, portal fechado, separador parado), para nao disparar com base
em estado anterior ao buraco.

Defeito encontrado no caminho: os 7 avisos ja ligados liam i.instance, mas o backend devolve Instance
com maiuscula. O detalhe saia sempre vazio (e "undefined: undefined" nas bases indisponiveis). Corrigido
com um leitor unico de nome. O detalhe passa tambem por escape antes de entrar no HTML.

Backend: collect_service_status devolve collector_last_update e collector_stale (ultima escrita em
KPI_MSSQL_SERVICE_STATUS_STG ha mais de 60 min). Identidade: sql_monitoring, so leitura, ligacao ja
existente da Intelligence. None quando nao foi possivel medir: o portal so muda a linha com true.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/A3_KPIS_CRITICOS_2026-09-15_apply.py --check
  py docs/context/A3_KPIS_CRITICOS_2026-09-15_apply.py
  py -m pytest tests/unit/test_a3_kpis_criticos_20260915.py tests/unit/test_a2_avisos_criticos_20260914.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "helpers": Path("api/routers/intelligence/helpers.py"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "ptbr": Path("static/i18n/pt-BR.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test_a2": Path("tests/unit/test_a2_avisos_criticos_20260914.py"),
    "test": Path("tests/unit/test_a3_kpis_criticos_20260915.py"),
}
MARK = "TOAST_JOB_TYPES_CRITICOS"

# ---------------------------------------------------------------- portal
ARRAY_START = "        const TOAST_CRITICAL_CHECKS = [\n"
ARRAY_END = "        ];\n\n        function startCriticalNotifications() {"
ARRAY_SHA = "c8ec3868e32476af35f6a5fe543103424ec6ee874e237dd99e8bcac15228c33d"   # array A2 medido a 15/09

ESTADO_JS = r"""        const TOAST_AUTO_DISMISS = 15000;  // 15s
        // A3 2026-09-15: duracao minima (sustainMs) e histerese (holdMs) por condicao, em TEMPO DE RELOGIO.
        // A resposta do dashboard nao traz carimbo do instantaneo, portanto contar leituras media o polling.
        const TOAST_MIN = 60 * 1000;
        const TOAST_GAP_MS = 15 * TOAST_MIN;          // sem leitura fresca ha mais do que isto: a prova reinicia
        const TOAST_SINCE_KEY = 'watcherdb-crit-since-v1';
        let _toastSince = _toastSinceLoad();          // { key: { since, seen } } persiste entre F5 (especialista)
        let _toastZeroSince = {};
        // Backup e Log ficam de fora (sao o aviso backup_failed); Index/Statistics/Shrink/Cleanup/Other nao acordam ninguem
        const TOAST_JOB_TYPES_CRITICOS = ['DBCC', 'Replication', 'AlwaysOn'];

        function _toastSinceLoad() {
            try {
                const v = JSON.parse(localStorage.getItem(TOAST_SINCE_KEY) || '{}');
                return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {};
            } catch (e) { return {}; }
        }
        function _toastSinceSave() {
            try { localStorage.setItem(TOAST_SINCE_KEY, JSON.stringify(_toastSince)); } catch (e) { /* modo privado ou quota */ }
        }
        // O backend devolve Instance/Server_Name com maiuscula; ate' 15/09 o detalhe lia i.instance e saia vazio
        function _toastNome(i) {
            return (i && (i.Instance || i.instance || i.Server_Name || i.server_name || i.ag_name || i.Hostname)) || '';
        }
        function _toastNomes(listas, filtro) {
            const vistos = [];
            [].concat(listas || []).forEach(lista => (lista || []).forEach(i => {
                if (filtro && !filtro(i)) return;
                const n = _toastNome(i);
                if (n && !vistos.includes(n)) vistos.push(n);
            }));
            return vistos.slice(0, 3).join(', ') + (vistos.length > 3 ? '…' : '');
        }
        function _toastExtras(base, partes) {
            // contadores agrupados entram no detalhe da familia, so' quando acima de zero
            const extra = partes.filter(p => (+p.n || 0) > 0).map(p => _kpiTp(p.chave, p.fb, { n: p.n }));
            return [base].concat(extra).filter(Boolean).join(' · ');
        }
        function _toastSustentado(check, valor, agora) {
            const k = check.key;
            if (valor > 0) {
                delete _toastZeroSince[k];
                const e = _toastSince[k];
                if (!e || (agora - (e.seen || 0)) > TOAST_GAP_MS) _toastSince[k] = { since: agora, seen: agora };
                else e.seen = agora;
                if (check.sustainMs) _toastSinceSave();
                return !check.sustainMs || (agora - _toastSince[k].since) >= check.sustainMs;
            }
            if (_toastSince[k]) { delete _toastSince[k]; if (check.sustainMs) _toastSinceSave(); }
            if (_toastZeroSince[k] === undefined) _toastZeroSince[k] = agora;
            return false;
        }
        function _toastEpisodioAcabou(check, agora) {
            // sem holdMs voltar a 0 fecha o episodio logo (regra A2); com holdMs so' depois de estavel a 0
            return !check.holdMs || (agora - _toastZeroSince[check.key]) >= check.holdMs;
        }
"""

ARRAY_NOVO = r"""        const TOAST_CRITICAL_CHECKS = [
            {
                key: 'instances_offline',
                label: 'Instancias Offline',
                icon: 'fa-server',
                // FIND-20260811-105: 'instance-availability-off' nao existe no backend
                // (HTTP 400 ao clicar). 'instance-availability' sem ok=true devolve a
                // lista de offline — o mesmo caminho do card Disponibilidade.
                kpiType: 'instance-availability',
                modalTitle: 'Instances Off',
                getValue: (d) => d.instance_availability?.off_count || 0,
                getDetail: (d) => _toastNomes([d.instance_availability?.instances], i => i.ping_ok === 0 || i.status === 'OFFLINE')
            },
            {
                key: 'blocked_sessions',
                label: 'Blocked Sessions',
                icon: 'fa-lock',
                kpiType: 'blocked-sessions',
                modalTitle: 'Blocked Sessions',
                // A3 2026-09-15: familia do bloqueio. Locks longos e utilizadores bloqueados sao fontes
                // independentes (views proprias): o valor e' o maximo, para um lock longo sem sessao bloqueada
                // nao ficar mudo, e o detalhe mostra de onde veio.
                getValue: (d) => Math.max(d.blocked_sessions?.count || 0, d.lock_count?.critical_count || 0, d.blocked_users?.count || 0),
                getDetail: (d) => _toastExtras(_toastNomes([d.blocked_sessions?.instances, d.lock_count?.instances, d.blocked_users?.instances]), [
                    { n: d.lock_count?.critical_count, chave: 'toast.detail_long_locks', fb: '{n} locks longos' },
                    { n: d.blocked_users?.count, chave: 'toast.detail_blocked_users', fb: '{n} utilizadores bloqueados' }
                ])
            },
            {
                key: 'db_unavailable',
                label: 'Databases Indisponiveis',
                icon: 'fa-database',
                kpiType: 'db-availability',
                modalTitle: 'DB Not Availability',
                getValue: (d) => d.db_availability?.abnormal_count || 0,
                getDetail: (d) => _toastNomes([d.db_availability?.instances])
            },
            {
                key: 'alwayson_unhealthy',
                label: 'AlwaysOn Unhealthy',
                icon: 'fa-sync-alt',
                kpiType: 'always-on',
                modalTitle: 'DB Always On - Não Saudável',
                getValue: (d) => d.always_on?.unhealthy_count || 0,
                getDetail: (d) => _toastNomes([d.always_on?.instances])
            },
            {
                key: 'disk_critical',
                label: 'Disco Critico',
                icon: 'fa-hdd',
                kpiType: 'disk-file-system-critical',
                modalTitle: 'DB Disk File System - Crítico',
                getValue: (d) => d.db_disk_file_system?.critical_count || 0,
                getDetail: (d) => _toastNomes([d.db_disk_file_system?.instances], i => (i.Critical || 0) > 0)
            },
            {
                key: 'tlog_critical',
                label: 'Transaction Log Critico',
                icon: 'fa-file-alt',
                kpiType: 'transaction-logs-critical',
                modalTitle: 'DB Transaction Logs - Crítico',
                getValue: (d) => d.db_transaction_logs?.critical_count || 0,
                getDetail: (d) => _toastNomes([d.db_transaction_logs?.instances], i => (i.Critical || 0) > 0)
            },
            {
                key: 'filegroup_critical',
                label: 'Filegroup Critico',
                icon: 'fa-layer-group',
                kpiType: 'filegroup-usage-critical',
                modalTitle: 'FileGroups Usage - Critical',
                getValue: (d) => d.filegroup_usage?.critical_count || 0,
                getDetail: (d) => _toastNomes([d.filegroup_usage?.instances], i => (i.Critical || 0) > 0)
            },
            // ---- A3 2026-09-15: classificacao aprovada pelo owner (parecer da persona DBA cliente) ----
            {
                key: 'backup_failed',
                label: 'Backup Failed',
                icon: 'fa-database',
                kpiType: 'backup-failed',
                get modalTitle() { return _kpiT('kpi_meta.backup-failed.modal_title', 'Backup Failed'); },
                getValue: (d) => d.backup_status?.failed_count || 0,
                getDetail: (d) => _toastNomes([d.backup_status?.failed_instances])
            },
            {
                key: 'mirroring_unhealthy',
                label: 'Mirroring Unhealthy',
                icon: 'fa-clone',
                kpiType: 'mirroring',
                get modalTitle() { return _kpiT('kpi_meta.mirroring-unhealthy.modal_title', 'DB Mirroring - Não Saudável'); },
                getValue: (d) => d.mirroring_status?.unhealthy_count || 0,
                getDetail: (d) => _toastNomes([d.mirroring_status?.instances])
            },
            {
                key: 'cpu_critical',
                label: 'CPU Critical',
                icon: 'fa-microchip',
                kpiType: 'cpu-critical',
                get modalTitle() { return t('kpi.cpu_critical_modal'); },
                sustainMs: 10 * TOAST_MIN,
                holdMs: 15 * TOAST_MIN,
                // processos em fila de CPU sao a mesma familia: entram no valor (maximo) e no detalhe
                getValue: (d) => Math.max(d.cpu_critical?.count || 0, d.processes_alarm?.count || 0),
                getDetail: (d) => _toastExtras(_toastNomes([d.cpu_critical?.instances, d.processes_alarm?.instances]), [
                    { n: d.processes_alarm?.count, chave: 'toast.detail_runnable', fb: '{n} com fila de CPU' }
                ])
            },
            {
                key: 'memory_critical',
                label: 'Memory Critical',
                icon: 'fa-memory',
                kpiType: 'memory-critical',
                get modalTitle() { return t('kpi.memory_critical_modal'); },
                sustainMs: 5 * TOAST_MIN,      // a view ja e' tendencia de 30 min
                holdMs: 15 * TOAST_MIN,
                getValue: (d) => d.memory_critical?.count || 0,
                getDetail: (d) => _toastNomes([d.memory_critical?.instances])
            },
            {
                key: 'disk_latency_critical',
                label: 'Disk Latency Critical',
                icon: 'fa-tachometer-alt',
                kpiType: 'disk-latency-critical',
                get modalTitle() { return _kpiT('kpi_meta.disk-latency-critical.modal_title', 'Disk Latency Critical'); },
                sustainMs: 10 * TOAST_MIN,     // checkpoint e backup fazem picos
                holdMs: 15 * TOAST_MIN,
                getValue: (d) => d.disk_latency?.critical_count || 0,
                getDetail: (d) => _toastNomes([(d.disk_latency?.instances || [])
                    .filter(i => i.Latency_Status === 'CRITICAL')
                    .map(i => ({ Instance: [i.Hostname, i.Drive].filter(Boolean).join(' ') }))])
            },
            {
                key: 'tempdb_critical',
                label: 'TempDB Critical',
                icon: 'fa-database',
                kpiType: 'tempdb-status-critical',
                get modalTitle() { return _kpiT('kpi_meta.tempdb-critical.modal_title', 'TempDB - Disco Crítico'); },
                sustainMs: 10 * TOAST_MIN,     // um spill pontual nao e' incidente
                holdMs: 15 * TOAST_MIN,
                getValue: (d) => d.tempdb_status?.critical_count || 0,
                getDetail: (d) => _toastNomes([d.tempdb_status?.instances], i => (i.Critical || 0) > 0 || i.status === 'CRITICAL')
            },
            {
                key: 'jobs_critical_failed',
                label: 'Critical Jobs Failed',
                icon: 'fa-exclamation-circle',
                kpiType: 'jobs-failed',
                get modalTitle() { return t('kpi.jobs_failed_modal'); },
                getValue: (d) => (d.jobs_status?.instances || []).filter(i => TOAST_JOB_TYPES_CRITICOS.includes(i.Job_Type)).length,
                getDetail: (d) => _toastNomes([d.jobs_status?.instances], i => TOAST_JOB_TYPES_CRITICOS.includes(i.Job_Type))
            }
        ];
"""

LOOP_VELHO = """                _toastStaleStreak = 0;
                const _activosNoArranque = [];
                TOAST_CRITICAL_CHECKS.forEach(check => {
                    const currentValue = check.getValue(data);
                    const previousValue = _toastPreviousState[check.key] || 0;

                    // A2 2026-09-14: estado por CONDICAO. Limpa SEMPRE que volta a 0 (fora do ramo de
                    // disparo), para a proxima subida disparar. So' dispara se agravou face ao ultimo
                    // valor que JA disparou: 3->4->3->4 dispara uma vez, nao a cada subida.
                    if (currentValue === 0) {
                        delete _toastLastFired[check.key];
                    } else if (currentValue > (_toastLastFired[check.key] || 0)) {
"""
LOOP_NOVO = """                _toastStaleStreak = 0;
                const _activosNoArranque = [];
                const _agora = Date.now();
                TOAST_CRITICAL_CHECKS.forEach(check => {
                    const currentValue = check.getValue(data);
                    // A3 2026-09-15: nos avisos com duracao o "anterior" do texto e' o ultimo valor que disparou;
                    // a leitura anterior daria "3 -> 3" ao fim dos 10 minutos
                    const previousValue = check.sustainMs ? (_toastLastFired[check.key] || 0) : (_toastPreviousState[check.key] || 0);
                    const _sustentado = _toastSustentado(check, currentValue, _agora);

                    // A2 2026-09-14: estado por CONDICAO. So' dispara se agravou face ao ultimo valor que JA
                    // disparou: 3->4->3->4 dispara uma vez. A3 2026-09-15: com holdMs, voltar a 0 so' fecha o
                    // episodio depois de 15 min estavel a 0; sem holdMs fecha logo, como no A2.
                    if (currentValue === 0) {
                        if (_toastEpisodioAcabou(check, _agora)) delete _toastLastFired[check.key];
                    } else if (_sustentado && currentValue > (_toastLastFired[check.key] || 0)) {
"""

DETALHE_VELHO = "                ${detail ? `<div class=\"toast-detail\">${detail}</div>` : ''}\n"
DETALHE_NOVO = "                ${detail ? `<div class=\"toast-detail\">${_bellEsc(detail)}</div>` : ''}\n"

SERV_VELHO = ("                _advRow(ev(ss, 'down_count') > 0 ? C.crit : C.ok, _kpiT('kpi_adv.services_down_label', 'Instâncias c/ serviços em baixo'), "
              "ev(ss, 'down_count'), '', 'service-status', _kpiT('kpi_adv.services_down_modal_title', 'Serviços SQL em Baixo')) + `</div>`));\n")
SERV_NOVO = ("                // A3 2026-09-15: recolha de servicos parada (ultima escrita 13/05). O 0 verde era falso verde:\n"
             "                // a linha fica cinzenta, sem numero, com a data da ultima recolha. So' com collector_stale === true.\n"
             "                (ss.collector_stale === true\n"
             "                    ? _advRow(C.gray, _kpiT('kpi_adv.services_down_label', 'Instâncias c/ serviços em baixo'), '—', _svcSemRecolha(ss), 'service-status', _kpiT('kpi_adv.services_down_modal_title', 'Serviços SQL em Baixo'))\n"
             "                    : _advRow(ev(ss, 'down_count') > 0 ? C.crit : C.ok, _kpiT('kpi_adv.services_down_label', 'Instâncias c/ serviços em baixo'), "
             "ev(ss, 'down_count'), '', 'service-status', _kpiT('kpi_adv.services_down_modal_title', 'Serviços SQL em Baixo'))) + `</div>`));\n")

ADVROW_ANCORA = "        function _advRow(color, lbl, val, badge, kpi, title) {\n"
SVC_FN = r"""        function _svcSemRecolha(ss) {
            // A3 2026-09-15: badge honesto quando a recolha de servicos esta parada
            const dt = ss && ss.collector_last_update ? new Date(ss.collector_last_update) : null;
            if (!dt || isNaN(dt.getTime())) return _kpiT('kpi_adv.services_no_collection_never', 'sem recolha');
            const quando = dt.toLocaleDateString(document.documentElement.lang || undefined, { day: '2-digit', month: '2-digit' });
            return _kpiTp('kpi_adv.services_no_collection', 'sem recolha desde {d}', { d: quando });
        }
"""

PORTAL_EDITS = [
    ("        const TOAST_AUTO_DISMISS = 15000;  // 15s\n", ESTADO_JS, 1),
    (LOOP_VELHO, LOOP_NOVO, 1),
    (DETALHE_VELHO, DETALHE_NOVO, 1),
    (SERV_VELHO, SERV_NOVO, 1),
    (ADVROW_ANCORA, SVC_FN + ADVROW_ANCORA, 1),
]

# ---------------------------------------------------------------- backend
HELP_DEFAULT_VELHO = '        "service_status": {\n            "down_count": 0,\n            "instances": []\n        },\n'
HELP_DEFAULT_NOVO = ('        "service_status": {\n            "down_count": 0,\n            "instances": [],\n'
                     '            "collector_last_update": None,\n            "collector_stale": None\n        },\n')
HELP_FN_ANCORA = "async def collect_service_status(results: Dict[str, Any]) -> None:\n"
HELP_FN = '''# A3 2026-09-15: a recolha de servicos pode estar parada (ultima escrita a 13/05) e, sem este sinal,
# "0 instancias com servicos em baixo" era indistinguivel de saudavel.
SERVICE_COLLECTOR_STALE_MINUTES = 60


async def _service_collector_freshness(results: Dict[str, Any]) -> None:
    """Ultima escrita da recolha de servicos. Identidade: sql_monitoring (ligacao da Intelligence), so leitura.

    collector_stale: True sem escrita ha mais de SERVICE_COLLECTOR_STALE_MINUTES ou tabela vazia;
    False com escrita recente; None quando nao foi possivel medir (o portal so reage a True).
    """
    svc = results.setdefault("service_status", {})
    svc["collector_last_update"] = None
    svc["collector_stale"] = None
    try:
        rows = await execute_intelligence_query_async(
            f"SELECT MAX(Update_TS) AS last_update FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVICE_STATUS_STG WITH (NOLOCK)",
            raise_on_error=False,
        )
        if rows is None:
            return
        last = rows[0].get("last_update") if rows else None
        if last is None:
            svc["collector_stale"] = True
            return
        if isinstance(last, str):
            last = datetime.fromisoformat(last)
        svc["collector_last_update"] = last.isoformat(timespec="seconds")
        svc["collector_stale"] = (datetime.now() - last) > timedelta(minutes=SERVICE_COLLECTOR_STALE_MINUTES)
    except Exception as e:
        logger.warning(f"Service Status: nao foi possivel medir a ultima recolha: {e}")


'''
HELP_CALL_VELHO = '        results["service_status"]["down_by_env"] = results["service_status"]["by_env"]\n'
HELP_CALL_NOVO = (HELP_CALL_VELHO +
                  "        await _service_collector_freshness(results)   # A3 2026-09-15: sinal de recolha parada\n")

HELPERS_EDITS = [
    (HELP_DEFAULT_VELHO, HELP_DEFAULT_NOVO, 1),
    (HELP_FN_ANCORA, HELP_FN + HELP_FN_ANCORA, 1),
    (HELP_CALL_VELHO, HELP_CALL_NOVO, 1),
]

# ---------------------------------------------------------------- i18n
TOAST_I18N = {
    "pt": {"backup_failed": "Backups Falhados", "mirroring_unhealthy": "Mirroring Não Saudável",
           "cpu_critical": "CPU Crítico (sustentado)", "memory_critical": "Memória Crítica (sustentada)",
           "disk_latency_critical": "Latência de Disco Crítica", "tempdb_critical": "TempDB Crítico",
           "jobs_critical_failed": "Jobs Críticos Falhados",
           "detail_long_locks": "{n} locks longos", "detail_blocked_users": "{n} utilizadores bloqueados",
           "detail_runnable": "{n} com fila de CPU"},
    "en": {"backup_failed": "Failed Backups", "mirroring_unhealthy": "Mirroring Unhealthy",
           "cpu_critical": "Critical CPU (sustained)", "memory_critical": "Critical Memory (sustained)",
           "disk_latency_critical": "Critical Disk Latency", "tempdb_critical": "Critical TempDB",
           "jobs_critical_failed": "Critical Jobs Failed",
           "detail_long_locks": "{n} long locks", "detail_blocked_users": "{n} blocked users",
           "detail_runnable": "{n} with CPU queue"},
    "es": {"backup_failed": "Backups Fallidos", "mirroring_unhealthy": "Mirroring No Saludable",
           "cpu_critical": "CPU Crítica (sostenida)", "memory_critical": "Memoria Crítica (sostenida)",
           "disk_latency_critical": "Latencia de Disco Crítica", "tempdb_critical": "TempDB Crítico",
           "jobs_critical_failed": "Jobs Críticos Fallidos",
           "detail_long_locks": "{n} bloqueos largos", "detail_blocked_users": "{n} usuarios bloqueados",
           "detail_runnable": "{n} con cola de CPU"},
}
ADV_I18N = {
    "pt": {"services_no_collection": "sem recolha desde {d}", "services_no_collection_never": "sem recolha"},
    "en": {"services_no_collection": "no collection since {d}", "services_no_collection_never": "no collection"},
    "es": {"services_no_collection": "sin recolección desde {d}", "services_no_collection_never": "sin recolección"},
}
PTBR_ADV = {"services_no_collection": "sem coleta desde {d}", "services_no_collection_never": "sem coleta"}
PTBR_TOAST = {"detail_blocked_users": "{n} usuários bloqueados"}


def _chaves(d):
    return "".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)},\n' for k, v in d.items())


# ---------------------------------------------------------------- changelog e testes
CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **Mais sete condições críticas no aviso e no sino, com a classificação aprovada** (A3, owner 15/09).\n"
                  "  Backups falhados e mirroring não saudável avisam logo. CPU, memória, latência de disco e tempdb só avisam\n"
                  "  depois de sustentados (10 min, memória 5), e voltar a zero por menos de 15 min conta como o mesmo\n"
                  "  episódio; o relógio sobrevive a um F5 e reinicia depois de 15 min sem dados frescos. Jobs só avisam para\n"
                  "  DBCC, replicação e AlwaysOn. Locks longos e utilizadores bloqueados juntam-se ao aviso de sessões\n"
                  "  bloqueadas, e a fila de CPU ao de CPU. Deadlocks, errorlog e serviços ficam de fora. O detalhe dos avisos\n"
                  "  vinha sempre vazio (lia o nome da instância com minúscula) e agora mostra as instâncias, com escape. A\n"
                  "  linha de serviços em baixo deixa de mostrar 0 verde quando a recolha está parada. [tier: Std]\n"
                  "\n", 1)

A2_TEST_EDIT = ('    assert "if (currentValue === 0) {\\n                        delete _toastLastFired[check.key];" in POLL\n',
                '    # A3 2026-09-15: o fecho do episodio passou a respeitar a histerese (holdMs); sem holdMs fecha logo\n'
                '    assert "if (currentValue === 0) {\\n                        if (_toastEpisodioAcabou(check, _agora)) delete _toastLastFired[check.key];" in POLL\n'
                '    assert "return !check.holdMs ||" in PORTAL\n', 1)

TEST_SRC = r'''"""
2026-09-15 -- A3: KPI criticos ligados ao aviso e ao sino com a classificacao aprovada pelo owner.
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
CHECKS = PORTAL[PORTAL.index("const TOAST_CRITICAL_CHECKS = ["):PORTAL.index("function startCriticalNotifications()")]
POLL = PORTAL[PORTAL.index("async function pollCriticalKPIs()"):PORTAL.index("function isOnDashboardKPIs()")]
HELPERS = (ROOT / "api" / "routers" / "intelligence" / "helpers.py").read_text(encoding="utf-8")


def _bloco(key):
    i = CHECKS.index(f"key: '{key}'")
    j = CHECKS.find("key: '", i + 5)
    return CHECKS[i:j if j > 0 else len(CHECKS)]


def test_classificacao_aprovada():
    ligados = re.findall(r"key: '([a-z_]+)'", CHECKS)
    assert ligados == ["instances_offline", "blocked_sessions", "db_unavailable", "alwayson_unhealthy",
                       "disk_critical", "tlog_critical", "filegroup_critical", "backup_failed",
                       "mirroring_unhealthy", "cpu_critical", "memory_critical", "disk_latency_critical",
                       "tempdb_critical", "jobs_critical_failed"]
    # nao ligar: sem baseline, contaminado por 18456, recolha parada
    for fora in ("d.deadlocks", "d.error_log", "d.service_status"):
        assert fora not in CHECKS, fora


def test_duracao_e_histerese_so_nos_quatro():
    for key, minutos in (("cpu_critical", 10), ("memory_critical", 5), ("disk_latency_critical", 10), ("tempdb_critical", 10)):
        b = _bloco(key)
        assert f"sustainMs: {minutos} * TOAST_MIN" in b, key
        assert "holdMs: 15 * TOAST_MIN" in b, key
    for key in ("backup_failed", "mirroring_unhealthy", "jobs_critical_failed", "blocked_sessions"):
        assert "sustainMs" not in _bloco(key), key
    assert "const _sustentado = _toastSustentado(check, currentValue, _agora);" in POLL
    assert "} else if (_sustentado && currentValue > (_toastLastFired[check.key] || 0)) {" in POLL


def test_relogio_persiste_e_reinicia_depois_de_buraco():
    assert "const TOAST_GAP_MS = 15 * TOAST_MIN;" in PORTAL
    assert "(agora - (e.seen || 0)) > TOAST_GAP_MS" in PORTAL
    assert "try { localStorage.setItem(TOAST_SINCE_KEY" in PORTAL
    assert "const v = JSON.parse(localStorage.getItem(TOAST_SINCE_KEY)" in PORTAL


def test_jobs_so_os_criticos():
    assert "const TOAST_JOB_TYPES_CRITICOS = ['DBCC', 'Replication', 'AlwaysOn'];" in PORTAL
    assert "TOAST_JOB_TYPES_CRITICOS.includes(i.Job_Type)" in _bloco("jobs_critical_failed")


def test_familias_agrupadas_pelo_maximo():
    b = _bloco("blocked_sessions")
    assert "Math.max(d.blocked_sessions?.count || 0, d.lock_count?.critical_count || 0, d.blocked_users?.count || 0)" in b
    assert "toast.detail_long_locks" in b and "toast.detail_blocked_users" in b
    c = _bloco("cpu_critical")
    assert "Math.max(d.cpu_critical?.count || 0, d.processes_alarm?.count || 0)" in c
    assert "toast.detail_runnable" in c


def test_detalhe_le_o_nome_com_maiuscula_e_sai_escapado():
    assert "i.instance)" not in CHECKS and "${i.instance}" not in CHECKS
    assert "i.Instance || i.instance" in PORTAL
    assert '<div class="toast-detail">${_bellEsc(detail)}</div>' in PORTAL


def test_linha_de_servicos_sem_falso_verde():
    assert "(ss.collector_stale === true" in PORTAL
    assert "function _svcSemRecolha(ss)" in PORTAL
    assert "MAX(Update_TS) AS last_update FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVICE_STATUS_STG" in HELPERS
    assert "await _service_collector_freshness(results)" in HELPERS
    assert "Trusted_Connection" not in HELPERS[HELPERS.index("async def _service_collector_freshness"):]


def test_frescura_da_recolha_de_servicos_comportamento(monkeypatch):
    from api.routers.intelligence import helpers as h
    agora = datetime.now()
    casos = [
        ([{"last_update": agora - timedelta(days=125)}], True, True),
        ([{"last_update": agora - timedelta(minutes=5)}], False, True),
        ([{"last_update": None}], True, False),
        (None, None, False),
    ]
    for rows, stale, tem_data in casos:
        async def fake(query, raise_on_error=True, _rows=rows):
            assert "KPI_MSSQL_SERVICE_STATUS_STG" in query and "MAX(Update_TS)" in query
            return _rows
        monkeypatch.setattr(h, "execute_intelligence_query_async", fake)
        res = {"service_status": {"down_count": 0}}
        asyncio.run(h._service_collector_freshness(res))
        assert res["service_status"]["collector_stale"] is stale, rows
        assert (res["service_status"]["collector_last_update"] is not None) is tem_data, rows


def test_chaves_nos_tres_idiomas():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for k in ("backup_failed", "mirroring_unhealthy", "cpu_critical", "memory_critical",
                  "disk_latency_critical", "tempdb_critical", "jobs_critical_failed"):
            assert d["toast"][k], (loc, k)
        for k in ("detail_long_locks", "detail_blocked_users", "detail_runnable"):
            assert "{n}" in d["toast"][k], (loc, k)
        assert "{d}" in d["kpi_adv"]["services_no_collection"], loc
        assert d["kpi_adv"]["services_no_collection_never"], loc
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:90]!r}")
        text = text.replace(o, n)
    return text


def _troca_array(text):
    eol = "\r\n" if "\r\n" in text else "\n"
    lf = text.replace("\r\n", "\n")
    if lf.count(ARRAY_START) != 1:
        raise SystemExit("[ABORT] portal: inicio do TOAST_CRITICAL_CHECKS nao unico -- nada escrito")
    a = lf.index(ARRAY_START)
    b = lf.index(ARRAY_END, a) + len("        ];\n")
    velho = lf[a:b]
    sha = hashlib.sha256(velho.encode("utf-8")).hexdigest()
    if sha != ARRAY_SHA:
        raise SystemExit(f"[ABORT] portal: o array de avisos mudou desde a medicao (sha {sha[:12]}) -- nada escrito")
    novo = lf[:a] + ARRAY_NOVO + lf[b:]
    return novo.replace("\n", eol)


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    portal_raw = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal_raw:
        print("[ABORT] ja aplicado"); return 1
    out = {}
    portal = _troca_array(portal_raw)
    out["portal"] = _apply(portal, PORTAL_EDITS, "portal")
    out["helpers"] = _apply(src["helpers"].read_bytes().decode("utf-8"), HELPERS_EDITS, "helpers")
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        d = json.loads(raw)
        if set(TOAST_I18N[loc]) & set(d.get("toast", {})) or set(ADV_I18N[loc]) & set(d.get("kpi_adv", {})):
            raise SystemExit(f"[ABORT] {loc}: chaves A3 ja existem")
        txt = _apply(raw, [('\n  "toast": {\n', '\n  "toast": {\n' + _chaves(TOAST_I18N[loc]), 1),
                           ('\n  "kpi_adv": {\n', '\n  "kpi_adv": {\n' + _chaves(ADV_I18N[loc]), 1)], loc)
        json.loads(txt)
        out[loc] = txt
    raw = src["ptbr"].read_bytes().decode("utf-8")
    d = json.loads(raw)
    if "toast" in d:
        raise SystemExit("[ABORT] pt-BR: bloco toast ja existe (o lote assume que nao)")
    corpo_toast = ",\n".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)}' for k, v in PTBR_TOAST.items())
    txt = _apply(raw, [('\n  "kpi_adv": {\n', '\n  "kpi_adv": {\n' + _chaves(PTBR_ADV), 1),
                       ('\n  "kpi_report": {', '\n  "toast": {\n' + corpo_toast + '\n  },\n  "kpi_report": {', 1)], "pt-BR")
    json.loads(txt)
    out["ptbr"] = txt
    if src["changelog"].exists():
        out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    out["test_a2"] = _apply(src["test_a2"].read_bytes().decode("utf-8"), [A2_TEST_EDIT], "test_a2")
    compile(out["helpers"], str(REL["helpers"]), "exec")
    compile(out["test_a2"], str(REL["test_a2"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] portal: array de avisos (7 -> 14, sha confere) + {len(PORTAL_EDITS)} blocos; helpers {len(HELPERS_EDITS)} blocos (compila)")
    print("[ok] i18n: toast 10 + kpi_adv 2 chaves em pt/en/es; pt-BR 3 chaves; JSON valido; changelog; teste A2 ajustado")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_a3_kpis_criticos_20260915.py tests/unit/test_a2_avisos_criticos_20260914.py -q --no-cov ; "
          "py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
