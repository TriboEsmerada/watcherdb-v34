# -*- coding: utf-8 -*-
"""B3 (2026-09-15) -- errorlog antes da falha, no ecra de servidor offline.

Plano: PLANO_EXECUCAO_ALERTAS_ERRORLOG_2026-09-14.md. Quando o ping ao servidor falha, o portal mostrava so
"offline" e o diagnostico de rede. O errorlog das horas anteriores ja esta na Intelligence (B1b e B2a-1), por isso
responde mesmo com o alvo mudo.

Parecer da persona DBA cliente (incorporado):
  - Distintivo "Sinal, nao causa" em cor neutra, nunca vermelho.
  - Falhas de login e outros eventos de seguranca fora da lista: so contagem, com o minuto de pico.
  - Janela de 2 h antes do evento offline por omissao; alargar a 6 h a pedido.
  - Lista vazia sempre explicada (recolha atrasada, instancia sem linhas, janela calma), nunca "sem erros".
  - Ultimo ciclo do recolhedor e ultima linha recebida da instancia sempre visiveis.
Parecer do frontend-specialist (incorporado):
  - createFetchWithAbort com timeout de 8 s (fetchWithTimeout nao existe no ponto do precheck).
  - Contentor role=status, aria-live=polite; cada linha em <details> nativo (teclado sem JS); sem <script> inline.
  - Chaves overview.offline_errorlog_*; o caminho offline nunca grava na cache da aba.
  - Backend com run_in_executor no _query_executor do modulo.

Medido antes (sql_monitoring, so leitura, 15/09): as duas leituras demoram 0,05 a 0,2 s por instancia, incluindo
SQLHDSPRD214 (6,4 milhoes de linhas no log) e uma instancia inexistente.

Limites declarados: so o ecra do precheck (ping falhado). O banner de diagnostico (host responde, SQL mudo) fica
para o B3b, porque passa pela cache da aba. O ultimo ciclo do recolhedor e global (todos os ambientes); a marca por
instancia chega com o B2a-2.

Backend: GET /api/intelligence-kpis/errorlog/recent-signals?instance=&hours=2|6. Sessao obrigatoria. Identidade na
BD: sql_monitoring (pool da Intelligence), so SELECT com parametros. Nao muda a base de dados.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/B3_OFFLINE_ERRORLOG_2026-09-15_apply.py --check
  py docs/context/B3_OFFLINE_ERRORLOG_2026-09-15_apply.py
  py -m pytest tests/unit/test_b3_offline_errorlog_20260915.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "kpis": Path("api/routers/intelligence_kpis.py"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "ptbr": Path("static/i18n/pt-BR.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_b3_offline_errorlog_20260915.py"),
}
MARK = "_errorlog_signals_payload"

# ---------------------------------------------------------------- backend
BACKEND = r'''# ---------------------------------------------------------------------------------------------------------------
# B3 2026-09-15: errorlog antes da falha, no ecra de servidor offline. Identidade na BD: sql_monitoring (pool da
# Intelligence), so SELECT com parametros. Le a Intelligence, nunca a instancia monitorizada: responde com o alvo mudo.
# Persona DBA: sinal, nao causa; Security so em contagem com pico; lista vazia sempre explicada; idade da recolha
# sempre visivel. So ha linhas ate a ultima leitura bem sucedida desta instancia (dito no ecra).
# ---------------------------------------------------------------------------------------------------------------
_ERRORLOG_SIGNALS_INSTANCE_RE = re.compile(r"^[A-Za-z0-9_$.\-]{1,128}$")
_ERRORLOG_SIGNALS_STALE_MIN = 15

_ERRORLOG_SIGNALS_CONTEXT_SQL = """
SET NOCOUNT ON;
DECLARE @inst VARCHAR(128) = ?;
SELECT GETDATE() AS agora,
       (SELECT TOP 1 ISNULL(e.First_Event_Time, e.Event_Time) FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS e WITH (NOLOCK)
        WHERE e.Server_Name = @inst AND e.Is_Resolved = 0 ORDER BY e.Event_Time DESC) AS ancora,
       (SELECT m.Last_Success_TS FROM dbo.WDB_COLLECTION_SCHEDULE_META m WITH (NOLOCK)
        WHERE m.Table_Name = 'KPI_MSSQL_ERRORLOG_STG') AS ciclo_recolhedor,
       (SELECT MAX(x.Update_TS) FROM (
            SELECT h.Update_TS FROM dbo.KPI_MSSQL_ERRORLOG_HIST h WITH (NOLOCK)
            WHERE h.Instance = @inst AND h.Log_Date >= DATEADD(DAY, -7, GETDATE())
            UNION ALL
            SELECT s.Update_TS FROM dbo.KPI_MSSQL_ERRORLOG_STG s WITH (NOLOCK) WHERE s.Instance = @inst) x) AS ultima_linha_instancia;
"""

# HIST e STG juntas: o arquivo (B2a-1) copia eventos da STG para a HIST, por isso a mesma linha pode estar nas duas.
# Deduplicacao pela regra do guardiao (Log_Date e CHECKSUM do texto). Grupos: E = listadas; S = Security (so contagem);
# O = Repetitive e Info (so contagem).
_ERRORLOG_SIGNALS_ROWS_SQL = """
SET NOCOUNT ON;
DECLARE @inst VARCHAR(128) = ?, @desde DATETIME2 = ?;
WITH u AS (
    SELECT h.Log_Date, h.Log_Type, h.Error_Number, h.Severity, h.Log_Text, CHECKSUM(h.Log_Text) AS hsh, h.Update_TS
    FROM dbo.KPI_MSSQL_ERRORLOG_HIST h WITH (NOLOCK) WHERE h.Instance = @inst AND h.Log_Date >= @desde
    UNION ALL
    SELECT s.Log_Date, s.Log_Type, s.Error_Number, s.Severity, s.Log_Text, CHECKSUM(s.Log_Text), s.Update_TS
    FROM dbo.KPI_MSSQL_ERRORLOG_STG s WITH (NOLOCK) WHERE s.Instance = @inst AND s.Log_Date >= @desde
), d AS (
    SELECT Log_Date, ISNULL(Log_Type, '') AS Tipo, Error_Number, Severity, Log_Text,
           CASE WHEN ISNULL(Log_Type, '') = 'Security' THEN 'S'
                WHEN ISNULL(Log_Type, '') IN ('Repetitive', 'Info') THEN 'O' ELSE 'E' END AS Grupo,
           ROW_NUMBER() OVER (PARTITION BY Log_Date, hsh ORDER BY Update_TS) AS rn
    FROM u
)
SELECT 'E' AS Linha, Log_Date, Tipo, Error_Number, Severity, Log_Text, CAST(NULL AS INT) AS n
FROM (SELECT TOP (15) Log_Date, Tipo, Error_Number, Severity, LEFT(Log_Text, 1000) AS Log_Text
      FROM d WHERE rn = 1 AND Grupo = 'E' ORDER BY Log_Date DESC) ev
UNION ALL
SELECT 'C', MAX(Log_Date), Grupo, NULL, NULL, NULL, COUNT(*) FROM d WHERE rn = 1 GROUP BY Grupo
UNION ALL
SELECT 'P', Minuto, 'Security', NULL, NULL, NULL, n
FROM (SELECT TOP (1) DATEADD(MINUTE, DATEDIFF(MINUTE, 0, Log_Date), 0) AS Minuto, COUNT(*) AS n
      FROM d WHERE rn = 1 AND Grupo = 'S'
      GROUP BY DATEADD(MINUTE, DATEDIFF(MINUTE, 0, Log_Date), 0) ORDER BY COUNT(*) DESC, Minuto DESC) pk;
"""


def _errorlog_signals_iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _errorlog_signals_payload(instance, hours, agora, ancora, ciclo, ultima_linha, rows):
    """Monta a resposta a partir das duas leituras. Sem BD (testada em unidade)."""
    iso = _errorlog_signals_iso
    eventos, contagem, pico = [], {"E": 0, "S": 0, "O": 0}, None
    for r in rows:
        if r[0] == "E":
            eventos.append({"log_date": iso(r[1]), "log_type": r[2] or "", "error_number": r[3],
                            "severity": r[4], "text": (r[5] or "").strip()})
        elif r[0] == "C" and r[2] in contagem:
            contagem[r[2]] = int(r[6] or 0)
        elif r[0] == "P" and r[6]:
            pico = {"minute": iso(r[1]), "count": int(r[6])}
    ciclo_min = None if ciclo is None else max(0, int((agora - ciclo).total_seconds() // 60))
    if ciclo_min is None or ciclo_min > _ERRORLOG_SIGNALS_STALE_MIN:
        vazio = "collector_stale"
    elif ultima_linha is None:
        vazio = "instance_never"
    else:
        vazio = "window_quiet"
    return {
        "success": True,
        "instance": instance,
        "hours": hours,
        "anchor": iso(ancora),
        "anchor_source": "offline_event" if ancora is not None else "now",
        "since": iso((ancora or agora) - timedelta(hours=hours)),
        "now": iso(agora),
        "events": eventos,
        "events_total": max(contagem["E"], len(eventos)),
        "security": {"count": contagem["S"], "peak": pico},
        "omitted_count": contagem["O"],
        "collector_last_cycle": iso(ciclo),
        "collector_cycle_minutes": ciclo_min,
        "collector_stale": vazio == "collector_stale",
        "instance_last_row": iso(ultima_linha),
        "empty_reason": None if eventos else vazio,
    }


def _errorlog_recent_signals_sync(instance: str, hours: int) -> dict:
    conn = get_intelligence_connection()
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(_ERRORLOG_SIGNALS_CONTEXT_SQL, instance)
        agora, ancora, ciclo, ultima_linha = cur.fetchone()
        cur.execute(_ERRORLOG_SIGNALS_ROWS_SQL, instance, (ancora or agora) - timedelta(hours=hours))
        rows = cur.fetchall()
        return _errorlog_signals_payload(instance, hours, agora, ancora, ciclo, ultima_linha, rows)
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        try:
            get_intelligence_pool().return_connection(conn)
        except Exception:
            pass


@router.get("/errorlog/recent-signals", response_model=GenericResponse)
async def get_errorlog_recent_signals(request: Request, instance: str = Query(...), hours: int = Query(2)):
    """Linhas classificadas do errorlog antes do evento offline activo (ou das ultimas horas, sem evento).

    B3 2026-09-15. Janela de 2 h por omissao, 6 h a pedido (so estes dois valores). Security e Repetitive/Info
    so em contagem. Sinal, nao causa.
    """
    await _require_auth(request)
    if not _ERRORLOG_SIGNALS_INSTANCE_RE.match(instance or ""):
        raise HTTPException(status_code=400, detail="Nome de instancia invalido")
    if hours not in (2, 6):
        raise HTTPException(status_code=400, detail="hours tem de ser 2 ou 6")
    try:
        loop = asyncio.get_event_loop()
        payload = await loop.run_in_executor(_query_executor, _errorlog_recent_signals_sync, instance, hours)
        return JSONResponse(content=payload)
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, "fetching recent errorlog signals")


'''
KPIS_ANCHOR = '@router.get("/server-offline/summary", response_model=GenericResponse)\n'
KPIS_EDITS = [(KPIS_ANCHOR, BACKEND + KPIS_ANCHOR, 1)]

# ---------------------------------------------------------------- portal
JS = r"""        // B3 2026-09-15: errorlog antes da falha, no ecra de servidor offline (precheck de renderOverview).
        // Le o que ja esta na Intelligence (o alvo pode estar mudo). Persona DBA: sinal, nao causa, em cor neutra;
        // Security so em contagem com pico; lista vazia sempre explicada, nunca "sem erros"; idade da recolha sempre
        // visivel. Frontend: createFetchWithAbort (fetchWithTimeout nao existe no precheck), role=status, <details>.
        function _oelEsc(s) {
            return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
        }
        function _oelHora(iso, comData) {
            if (!iso) return '';
            const d = new Date(iso);
            if (isNaN(d.getTime())) return '';
            const lang = document.documentElement.lang || undefined;
            return comData
                ? d.toLocaleString(lang, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
                : d.toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit' });
        }
        function _oelT(k, fb, p) { return _oelEsc(_kpiTp('overview.offline_errorlog_' + k, fb, p || {})); }
        function offlineErrorlogId(instance) {
            return 'offline-errorlog-' + String(instance || '').replace(/[^A-Za-z0-9_-]/g, '_');
        }
        function _oelLoading() {
            return `<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> ${_oelT('loading', 'A ler o errorlog guardado na Intelligence…')}`;
        }
        function offlineErrorlogBlock(instance) {
            const inst = String(instance || '').replace(/\\/g, '_');
            return `<div id="${offlineErrorlogId(inst)}" data-inst="${_oelEsc(inst)}" role="status" aria-live="polite" aria-atomic="true"
                         style="background: var(--color-bg-sunken); border: 1px solid var(--color-border); border-radius: 12px; padding: 16px 20px; margin-bottom: 20px; text-align: left; color: var(--color-text-secondary);">${_oelLoading()}</div>`;
        }
        const _OEL_BTN = 'background: transparent; color: var(--color-text-secondary); border: 1px solid var(--color-border); padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px;';
        async function loadOfflineErrorlog(elId, hours) {
            const el = document.getElementById(elId);
            if (!el) return;
            const h = hours === 6 ? 6 : 2;
            el.setAttribute('aria-busy', 'true');
            el.innerHTML = _oelLoading();
            let d = null;
            try {
                const r = await createFetchWithAbort(
                    `/api/intelligence-kpis/errorlog/recent-signals?instance=${encodeURIComponent(el.dataset.inst || '')}&hours=${h}`, { timeout: 8000 });
                d = (r && r.ok) ? await r.json() : null;
            } catch (e) { d = null; /* fail-open: o ecra de offline continua valido */ }
            if (!el.isConnected) return;
            el.removeAttribute('aria-busy');
            el.innerHTML = (d && d.success) ? _oelRender(elId, d)
                : `<i class="fas fa-circle-info" aria-hidden="true"></i> ${_oelT('failed', 'Não foi possível ler o errorlog na Intelligence. O diagnóstico acima continua válido.')}
                   <button type="button" onclick="loadOfflineErrorlog('${elId}', ${h})" style="${_OEL_BTN} margin-left: 10px;">${_oelT('retry', 'Tentar outra vez')}</button>`;
        }
        function _oelRender(elId, d) {
            const neutro = 'var(--color-text-secondary)';
            const suave = 'var(--color-text-tertiary)';
            const h = d.hours === 6 ? 6 : 2;
            const tipoCor = tp => tp === 'Critical' ? getSevTokens('CRITICAL') : tp === 'Error' ? getSevTokens('WARNING')
                : (tp === 'AvailabilityGroup' || tp === 'Lifecycle') ? getSevTokens('INFO') : null;
            const janela = d.anchor_source === 'offline_event'
                ? _oelT('window_event', 'Linhas desde {since}: {h} h antes do evento offline das {anchor}.', { since: _oelHora(d.since, true), h, anchor: _oelHora(d.anchor, true) })
                : _oelT('window_now', 'Linhas das últimas {h} h (sem evento offline ativo registado).', { h });
            const ciclo = d.collector_cycle_minutes == null
                ? _kpiTp('overview.offline_errorlog_collector_never', 'sem registo', {})
                : _kpiTp('overview.offline_errorlog_collector_ago', 'há {n} min ({time})', { n: d.collector_cycle_minutes, time: _oelHora(d.collector_last_cycle) });
            const ultima = d.instance_last_row ? _oelHora(d.instance_last_row, true)
                : _kpiTp('overview.offline_errorlog_instance_none', 'nenhuma nos últimos 7 dias', {});
            let html = `
                <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 6px;">
                    <i class="fas fa-file-lines" aria-hidden="true" style="color: ${neutro};"></i>
                    <strong style="color: var(--color-text-primary); font-size: 15px;">${_oelT('title', 'Errorlog antes da falha')}</strong>
                    <span style="border: 1px solid var(--color-border); color: ${neutro}; border-radius: 999px; padding: 1px 10px; font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase;">${_oelT('badge', 'Sinal, não causa')}</span>
                </div>
                <div style="font-size: 13px; color: ${neutro};">${janela}</div>
                <div style="font-size: 12px; color: ${d.collector_stale ? getSevTokens('WARNING').text : suave}; margin-top: 4px;">
                    ${_oelT('collector', 'Último ciclo do recolhedor do errorlog: {when}', { when: ciclo })}${d.collector_stale ? ' · ' + _oelT('collector_stale', 'recolha atrasada') : ''}
                    · ${_oelT('instance_last', 'Última linha recebida desta instância: {when}', { when: ultima })}
                </div>`;
            const sec = d.security || {};
            if (+sec.count > 0) {
                html += `<div style="font-size: 13px; color: ${neutro}; margin-top: 10px;"><i class="fas fa-user-lock" aria-hidden="true"></i>
                    ${_oelT('security', 'Falhas de login e outros eventos de segurança: {n}, com pico de {p} às {time}. Não são listados aqui.',
                            { n: sec.count, p: sec.peak ? sec.peak.count : sec.count, time: sec.peak ? _oelHora(sec.peak.minute) : '' })}</div>`;
            }
            const ev = Array.isArray(d.events) ? d.events : [];
            if (ev.length) {
                const itens = ev.map(e => {
                    const tk = tipoCor(e.log_type);
                    const chip = tk ? `background: ${tk.bg}; color: ${tk.text};` : `border: 1px solid var(--color-border); color: ${neutro};`;
                    const num = e.error_number != null
                        ? _oelT('error_sev', 'Erro {n}, severidade {s}', { n: e.error_number, s: e.severity == null ? '—' : e.severity }) + ' · ' : '';
                    const texto = String(e.text || '');
                    const resumo = texto.length > 140 ? texto.slice(0, 140) + '…' : texto;
                    return `<li style="border-top: 1px solid var(--color-border); padding: 6px 0;">
                        <details>
                            <summary style="cursor: pointer; font-size: 13px; color: ${neutro};">
                                <span style="font-variant-numeric: tabular-nums;">${_oelEsc(_oelHora(e.log_date, true))}</span>
                                <span style="${chip} border-radius: 4px; padding: 0 6px; font-size: 11px; margin: 0 6px;">${_oelEsc(e.log_type || '—')}</span>
                                <span style="color: ${suave}; font-size: 12px;">${num}</span>${_oelEsc(resumo)}
                            </summary>
                            <pre style="white-space: pre-wrap; word-break: break-word; font-size: 12px; margin: 6px 0 0; padding: 8px; background: var(--color-bg-primary); border-radius: 6px; color: ${neutro};">${_oelEsc(texto)}</pre>
                        </details>
                    </li>`;
                }).join('');
                html += `<div style="font-size: 12px; color: ${suave}; margin-top: 10px;">${_oelT('shown', '{shown} de {total} linhas, da mais recente para a mais antiga.', { shown: ev.length, total: Math.max(+d.events_total || 0, ev.length) })}</div>
                    <ul aria-label="${_oelT('list_label', 'Linhas do errorlog')}" style="list-style: none; margin: 6px 0 0; padding: 0;">${itens}</ul>`;
            } else {
                const motivo = d.empty_reason === 'collector_stale'
                    ? ['empty_collector_stale', 'Nenhuma linha nesta janela, mas a recolha do errorlog está atrasada: a ausência de linhas não diz nada sobre o servidor.']
                    : d.empty_reason === 'instance_never'
                    ? ['empty_instance_never', 'Esta instância não enviou linhas do errorlog nos últimos 7 dias. O recolhedor pode não a ler, ou não conseguir ligar-se a ela.']
                    : ['empty_window_quiet', 'Nenhuma linha classificada nesta janela. Isto não prova que não houve problemas: a instância pode ter parado antes de o recolhedor voltar a ler o log.'];
                html += `<div style="font-size: 13px; color: ${neutro}; margin-top: 10px;"><i class="fas fa-circle-info" aria-hidden="true"></i> ${_oelT(motivo[0], motivo[1])}</div>`;
            }
            if (+d.omitted_count > 0) {
                html += `<div style="font-size: 12px; color: ${suave}; margin-top: 6px;">${_oelT('omitted', '{n} linhas repetitivas ou informativas não listadas.', { n: d.omitted_count })}</div>`;
            }
            html += `<div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 12px;">
                    ${h === 2 ? `<button type="button" onclick="loadOfflineErrorlog('${elId}', 6)" style="${_OEL_BTN}">${_oelT('widen', 'Alargar para 6 h')}</button>` : ''}
                    <span style="font-size: 11px; font-style: italic; color: ${suave};">${_oelT('footnote', 'O recolhedor só vê o que conseguiu ler antes de perder a ligação à instância. Use estas linhas como pista para investigar, não como causa confirmada.')}</span>
                </div>`;
            return html;
        }

"""

PRECHECK_OLD = ("                                            <i class=\"fas fa-stethoscope\"></i> ${t('overview.run_diagnostics')}\n"
                "                                        </button>\n"
                "                                    </div>\n"
                "                                </div>\n"
                "                            </div>\n"
                "                        `;\n"
                "                        return;\n")
PRECHECK_NEW = ("                                            <i class=\"fas fa-stethoscope\"></i> ${t('overview.run_diagnostics')}\n"
                "                                        </button>\n"
                "                                    </div>\n"
                "                                </div>\n"
                "                                ${offlineErrorlogBlock(serverId)}\n"
                "                            </div>\n"
                "                        `;\n"
                "                        // B3 2026-09-15: errorlog antes da falha, lido da Intelligence depois de o cartao estar no ecra\n"
                "                        loadOfflineErrorlog(offlineErrorlogId(serverId), 2);\n"
                "                        return;\n")

PORTAL_EDITS = [
    ("        function extractHostname(serverIdOrName) {\n", JS + "        function extractHostname(serverIdOrName) {\n", 1),
    (PRECHECK_OLD, PRECHECK_NEW, 1),
]

# ---------------------------------------------------------------- i18n (bloco overview)
I18N = {
    "pt": {
        "offline_errorlog_title": "Errorlog antes da falha",
        "offline_errorlog_badge": "Sinal, não causa",
        "offline_errorlog_loading": "A ler o errorlog guardado na Intelligence…",
        "offline_errorlog_window_event": "Linhas desde {since}: {h} h antes do evento offline das {anchor}.",
        "offline_errorlog_window_now": "Linhas das últimas {h} h (sem evento offline ativo registado).",
        "offline_errorlog_collector": "Último ciclo do recolhedor do errorlog: {when}",
        "offline_errorlog_collector_ago": "há {n} min ({time})",
        "offline_errorlog_collector_never": "sem registo",
        "offline_errorlog_collector_stale": "recolha atrasada",
        "offline_errorlog_instance_last": "Última linha recebida desta instância: {when}",
        "offline_errorlog_instance_none": "nenhuma nos últimos 7 dias",
        "offline_errorlog_security": "Falhas de login e outros eventos de segurança: {n}, com pico de {p} às {time}. Não são listados aqui.",
        "offline_errorlog_error_sev": "Erro {n}, severidade {s}",
        "offline_errorlog_shown": "{shown} de {total} linhas, da mais recente para a mais antiga.",
        "offline_errorlog_list_label": "Linhas do errorlog",
        "offline_errorlog_omitted": "{n} linhas repetitivas ou informativas não listadas.",
        "offline_errorlog_empty_collector_stale": "Nenhuma linha nesta janela, mas a recolha do errorlog está atrasada: a ausência de linhas não diz nada sobre o servidor.",
        "offline_errorlog_empty_instance_never": "Esta instância não enviou linhas do errorlog nos últimos 7 dias. O recolhedor pode não a ler, ou não conseguir ligar-se a ela.",
        "offline_errorlog_empty_window_quiet": "Nenhuma linha classificada nesta janela. Isto não prova que não houve problemas: a instância pode ter parado antes de o recolhedor voltar a ler o log.",
        "offline_errorlog_widen": "Alargar para 6 h",
        "offline_errorlog_failed": "Não foi possível ler o errorlog na Intelligence. O diagnóstico acima continua válido.",
        "offline_errorlog_retry": "Tentar outra vez",
        "offline_errorlog_footnote": "O recolhedor só vê o que conseguiu ler antes de perder a ligação à instância. Use estas linhas como pista para investigar, não como causa confirmada.",
    },
    "en": {
        "offline_errorlog_title": "Error log before the failure",
        "offline_errorlog_badge": "Signal, not cause",
        "offline_errorlog_loading": "Reading the error log stored in Intelligence…",
        "offline_errorlog_window_event": "Lines since {since}: {h} h before the offline event at {anchor}.",
        "offline_errorlog_window_now": "Lines from the last {h} h (no active offline event recorded).",
        "offline_errorlog_collector": "Last error log collector cycle: {when}",
        "offline_errorlog_collector_ago": "{n} min ago ({time})",
        "offline_errorlog_collector_never": "not recorded",
        "offline_errorlog_collector_stale": "collection delayed",
        "offline_errorlog_instance_last": "Last line received from this instance: {when}",
        "offline_errorlog_instance_none": "none in the last 7 days",
        "offline_errorlog_security": "Login failures and other security events: {n}, peaking at {p} at {time}. They are not listed here.",
        "offline_errorlog_error_sev": "Error {n}, severity {s}",
        "offline_errorlog_shown": "{shown} of {total} lines, most recent first.",
        "offline_errorlog_list_label": "Error log lines",
        "offline_errorlog_omitted": "{n} repetitive or informational lines not listed.",
        "offline_errorlog_empty_collector_stale": "No lines in this window, but error log collection is delayed: the absence of lines says nothing about the server.",
        "offline_errorlog_empty_instance_never": "This instance has sent no error log lines in the last 7 days. The collector may not read it, or may be unable to connect to it.",
        "offline_errorlog_empty_window_quiet": "No classified lines in this window. That does not prove there were no problems: the instance may have stopped before the collector read the log again.",
        "offline_errorlog_widen": "Widen to 6 h",
        "offline_errorlog_failed": "Could not read the error log from Intelligence. The diagnosis above is still valid.",
        "offline_errorlog_retry": "Try again",
        "offline_errorlog_footnote": "The collector only sees what it read before it lost the connection to the instance. Treat these lines as a lead to investigate, not a confirmed cause.",
    },
    "es": {
        "offline_errorlog_title": "Errorlog antes del fallo",
        "offline_errorlog_badge": "Señal, no causa",
        "offline_errorlog_loading": "Leyendo el errorlog guardado en Intelligence…",
        "offline_errorlog_window_event": "Líneas desde {since}: {h} h antes del evento offline de las {anchor}.",
        "offline_errorlog_window_now": "Líneas de las últimas {h} h (sin evento offline activo registrado).",
        "offline_errorlog_collector": "Último ciclo del colector del errorlog: {when}",
        "offline_errorlog_collector_ago": "hace {n} min ({time})",
        "offline_errorlog_collector_never": "sin registro",
        "offline_errorlog_collector_stale": "recolección atrasada",
        "offline_errorlog_instance_last": "Última línea recibida de esta instancia: {when}",
        "offline_errorlog_instance_none": "ninguna en los últimos 7 días",
        "offline_errorlog_security": "Fallos de inicio de sesión y otros eventos de seguridad: {n}, con pico de {p} a las {time}. No se listan aquí.",
        "offline_errorlog_error_sev": "Error {n}, severidad {s}",
        "offline_errorlog_shown": "{shown} de {total} líneas, de la más reciente a la más antigua.",
        "offline_errorlog_list_label": "Líneas del errorlog",
        "offline_errorlog_omitted": "{n} líneas repetitivas o informativas no listadas.",
        "offline_errorlog_empty_collector_stale": "Ninguna línea en esta ventana, pero la recolección del errorlog está atrasada: la ausencia de líneas no dice nada sobre el servidor.",
        "offline_errorlog_empty_instance_never": "Esta instancia no envió líneas del errorlog en los últimos 7 días. Puede que el colector no la lea o que no consiga conectarse a ella.",
        "offline_errorlog_empty_window_quiet": "Ninguna línea clasificada en esta ventana. Eso no prueba que no hubiera problemas: la instancia pudo detenerse antes de que el colector volviera a leer el log.",
        "offline_errorlog_widen": "Ampliar a 6 h",
        "offline_errorlog_failed": "No fue posible leer el errorlog en Intelligence. El diagnóstico de arriba sigue siendo válido.",
        "offline_errorlog_retry": "Reintentar",
        "offline_errorlog_footnote": "El colector solo ve lo que consiguió leer antes de perder la conexión con la instancia. Use estas líneas como pista para investigar, no como causa confirmada.",
    },
}
PTBR = {
    "offline_errorlog_loading": "Lendo o errorlog salvo na Intelligence…",
    "offline_errorlog_window_now": "Linhas das últimas {h} h (sem evento offline ativo registrado).",
    "offline_errorlog_collector": "Último ciclo do coletor do errorlog: {when}",
    "offline_errorlog_collector_never": "sem registro",
    "offline_errorlog_collector_stale": "coleta atrasada",
    "offline_errorlog_empty_collector_stale": "Nenhuma linha nesta janela, mas a coleta do errorlog está atrasada: a ausência de linhas não diz nada sobre o servidor.",
    "offline_errorlog_empty_instance_never": "Esta instância não enviou linhas do errorlog nos últimos 7 dias. O coletor pode não lê-la, ou não conseguir se conectar a ela.",
    "offline_errorlog_empty_window_quiet": "Nenhuma linha classificada nesta janela. Isso não prova que não houve problemas: a instância pode ter parado antes que o coletor voltasse a ler o log.",
    "offline_errorlog_widen": "Ampliar para 6 h",
    "offline_errorlog_retry": "Tentar novamente",
    "offline_errorlog_footnote": "O coletor só vê o que conseguiu ler antes de perder a conexão com a instância. Use estas linhas como pista para investigar, não como causa confirmada.",
}


def _chaves(d):
    return "".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)},\n' for k, v in d.items())


# ---------------------------------------------------------------- changelog e teste
CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **Ecrã de servidor offline mostra o errorlog antes da falha** (B3, owner 15/09). Quando o ping falha, o\n"
                  "  portal lê da Intelligence até 15 linhas classificadas (Critical, Error, AvailabilityGroup, Lifecycle) das\n"
                  "  2 h antes do evento offline, com opção de alargar a 6 h. Falhas de login e outros eventos de segurança só\n"
                  "  em contagem, com o minuto de pico; linhas repetitivas e informativas só em contagem. Mostra sempre o último\n"
                  "  ciclo do recolhedor e a última linha recebida da instância, e explica a lista vazia em vez de dizer que\n"
                  "  não houve erros. Marcado como sinal, não causa. Endpoint novo GET\n"
                  "  /api/intelligence-kpis/errorlog/recent-signals (sessão obrigatória; leitura na BD como sql_monitoring).\n"
                  "  [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-15 -- B3: errorlog antes da falha, no ecra de servidor offline.
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
KPIS = (ROOT / "api" / "routers" / "intelligence_kpis.py").read_text(encoding="utf-8")
JS = PORTAL[PORTAL.index("// B3 2026-09-15: errorlog antes da falha, no ecra"):PORTAL.index("function extractHostname(serverIdOrName) {")]
PRECHECK = PORTAL[PORTAL.index("updateSkeletonProgress(t('overview.precheck_connectivity'));"):PORTAL.index("[PRECHECK] Erro no ping")]
AGORA = datetime(2026, 9, 15, 15, 0, 0)


def _ik():
    from api.routers import intelligence_kpis as ik
    return ik


def test_payload_listadas_seguranca_e_omitidas():
    ik = _ik()
    ancora = datetime(2026, 9, 15, 12, 53, 14)
    rows = [
        ("E", datetime(2026, 9, 15, 12, 50), "Critical", 17053, 16, "  Stack dump  ", None),
        ("C", datetime(2026, 9, 15, 12, 50), "E", None, None, None, 3),
        ("C", datetime(2026, 9, 15, 12, 51), "S", None, None, None, 40),
        ("C", datetime(2026, 9, 15, 12, 40), "O", None, None, None, 7),
        ("P", datetime(2026, 9, 15, 12, 20), "Security", None, None, None, 12),
    ]
    p = ik._errorlog_signals_payload("SQLX_I01", 2, AGORA, ancora, AGORA - timedelta(minutes=3), AGORA, rows)
    assert p["events"] == [{"log_date": "2026-09-15T12:50:00", "log_type": "Critical", "error_number": 17053,
                            "severity": 16, "text": "Stack dump"}]
    assert p["events_total"] == 3 and p["omitted_count"] == 7
    assert p["security"] == {"count": 40, "peak": {"minute": "2026-09-15T12:20:00", "count": 12}}
    assert p["anchor_source"] == "offline_event" and p["since"] == "2026-09-15T10:53:14"
    assert p["collector_cycle_minutes"] == 3 and p["collector_stale"] is False and p["empty_reason"] is None
    json.dumps(p)


def test_lista_vazia_tem_sempre_motivo():
    ik = _ik()
    fresco = AGORA - timedelta(minutes=5)
    casos = [
        (AGORA - timedelta(minutes=16), AGORA, "collector_stale"),
        (None, AGORA, "collector_stale"),
        (fresco, None, "instance_never"),
        (fresco, AGORA - timedelta(days=1), "window_quiet"),
    ]
    for ciclo, ultima, motivo in casos:
        p = ik._errorlog_signals_payload("SQLX_I01", 6, AGORA, None, ciclo, ultima, [])
        assert p["empty_reason"] == motivo, (ciclo, ultima)
        assert p["collector_stale"] is (motivo == "collector_stale")
        assert p["anchor_source"] == "now" and p["since"] == "2026-09-15T09:00:00"


def test_consultas_so_leitura_parametrizadas_e_deduplicadas():
    ik = _ik()
    for sql in (ik._ERRORLOG_SIGNALS_CONTEXT_SQL, ik._ERRORLOG_SIGNALS_ROWS_SQL):
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|EXEC|CREATE|ALTER|DROP|TRUNCATE)\b", sql)
        assert "DECLARE @inst VARCHAR(128) = ?" in sql
    linhas = ik._ERRORLOG_SIGNALS_ROWS_SQL
    assert linhas.count("WITH (NOLOCK)") == 2 and "PARTITION BY Log_Date, hsh" in linhas
    assert "TOP (15)" in linhas and "Grupo = 'E'" in linhas
    assert "WHEN ISNULL(Log_Type, '') = 'Security' THEN 'S'" in linhas
    bloco = KPIS[KPIS.index("# B3 2026-09-15: errorlog antes da falha"):KPIS.index('@router.get("/server-offline/summary"')]
    assert "get_intelligence_connection()" in bloco and "pyodbc.connect" not in bloco
    assert "Trusted_Connection" not in bloco and "Integrated Security" not in bloco


def test_endpoint_exige_sessao_antes_de_validar(monkeypatch):
    ik = _ik()
    chamadas = []

    async def sem_sessao(request):
        raise HTTPException(status_code=401, detail="Token nao fornecido")

    monkeypatch.setattr(ik, "_require_auth", sem_sessao)
    with pytest.raises(HTTPException) as e:
        asyncio.run(ik.get_errorlog_recent_signals(None, instance="a;b", hours=9))
    assert e.value.status_code == 401

    async def com_sessao(request):
        return {"username": "dba"}

    monkeypatch.setattr(ik, "_require_auth", com_sessao)
    monkeypatch.setattr(ik, "_errorlog_recent_signals_sync", lambda inst, h: chamadas.append((inst, h)) or {"success": True})
    for inst, h in (("SQLX_I01; DROP", 2), ("SQLX\\I01", 2), ("SQLX_I01", 3)):
        with pytest.raises(HTTPException) as e:
            asyncio.run(ik.get_errorlog_recent_signals(None, instance=inst, hours=h))
        assert e.value.status_code == 400
    r = asyncio.run(ik.get_errorlog_recent_signals(None, instance="SQLHDSPRD214_I01", hours=6))
    assert r.status_code == 200 and chamadas == [("SQLHDSPRD214_I01", 6)]


def test_portal_bloco_no_ecra_offline():
    assert "${offlineErrorlogBlock(serverId)}" in PRECHECK
    assert "loadOfflineErrorlog(offlineErrorlogId(serverId), 2);\n                        return;" in PRECHECK.replace("\r\n", "\n")
    assert "createFetchWithAbort(" in JS and "{ timeout: 8000 }" in JS and "fetchWithTimeout(" not in JS
    assert 'role="status" aria-live="polite"' in JS and "<details>" in JS and 'type="button"' in JS
    assert "<script" not in JS and "setTabCache" not in JS
    assert "/api/intelligence-kpis/errorlog/recent-signals?instance=${encodeURIComponent(" in JS
    for motivo in ("empty_collector_stale", "empty_instance_never", "empty_window_quiet"):
        assert f"'{motivo}'" in JS


def test_chaves_nos_idiomas_sem_prometer_ausencia_de_erros():
    chaves = None
    for loc in ("pt", "en", "es"):
        ov = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["overview"]
        novas = {k: v for k, v in ov.items() if k.startswith("offline_errorlog_")}
        chaves = chaves or set(novas)
        assert set(novas) == chaves and len(chaves) == 23, loc
        for k in chaves:
            assert novas[k].strip(), (loc, k)
            curta = k[len("offline_errorlog_"):]
            assert f"'{curta}'" in JS or f"'overview.{k}'" in JS, k
        for k, ph in (("window_event", ("{since}", "{h}", "{anchor}")), ("security", ("{n}", "{p}", "{time}")),
                      ("shown", ("{shown}", "{total}")), ("collector_ago", ("{n}", "{time}"))):
            assert all(x in novas["offline_errorlog_" + k] for x in ph), (loc, k)
        texto = " ".join(novas.values()).lower()
        assert "sem erros" not in texto and "no errors" not in texto and "sin errores" not in texto
    ptbr = json.loads((ROOT / "static" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))["overview"]
    assert {k for k in ptbr if k.startswith("offline_errorlog_")} <= chaves
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


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    kpis_raw = src["kpis"].read_bytes().decode("utf-8")
    if MARK in kpis_raw:
        print("[ABORT] ja aplicado"); return 1
    out = {"kpis": _apply(kpis_raw, KPIS_EDITS, "intelligence_kpis"),
           "portal": _apply(src["portal"].read_bytes().decode("utf-8"), PORTAL_EDITS, "portal")}
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        if set(I18N[loc]) & set(json.loads(raw)["overview"]):
            raise SystemExit(f"[ABORT] {loc}: chaves novas ja existem em overview")
        txt = _apply(raw, [('\n  "overview": {\n', '\n  "overview": {\n' + _chaves(I18N[loc]), 1)], loc)
        json.loads(txt)
        out[loc] = txt
    raw = src["ptbr"].read_bytes().decode("utf-8")
    if not set(PTBR) <= set(I18N["pt"]):
        raise SystemExit("[ABORT] pt-BR: chave sem par em pt")
    txt = _apply(raw, [('\n  "overview": {\n', '\n  "overview": {\n' + _chaves(PTBR), 1)], "pt-BR")
    json.loads(txt)
    out["ptbr"] = txt
    out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    compile(out["kpis"], str(REL["kpis"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] intelligence_kpis.py: endpoint recent-signals (compila); portal {len(PORTAL_EDITS)} blocos (funcoes + precheck)")
    print(f"[ok] i18n overview: {len(I18N['pt'])} chaves em pt/en/es, {len(PTBR)} em pt-BR; JSON valido; changelog")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_b3_offline_errorlog_20260915.py -q --no-cov ; "
          "py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
