# Handoff V6 — lote "QA externo PRD 2026-08-16" (V3.3 → V6)

Contexto para a AI do V6: um QA externo (browser-agent cloud) testou o V3.3 em PRD e o council V3.3 triou 14 bugs (docs/context/TRIAGEM_QA_EXTERNO_PRD_2026-08-16.md no V3.3). Este lote aplica em V3.3 os fixes S; V6 = V3.3 + extras, MAS o portal V6 NÃO é superset (grep de âncoras feito 2026-08-16 — resultados abaixo). Regras: consultar specialists V6 antes de aplicar; não propagar cego; commit por item; sem `unsafe` novo em CSP; strings JS single-quoted nunca com apóstrofe.

## Âncoras V6 (grep 2026-08-16)
| Item V3.3 | Existe em V6? | Onde | Acção V6 |
|---|---|---|---|
| FOUC: `applyLanguageToUI()` em `init()` | **NÃO** (0 ocorrências) | — | Nada a fazer; confirmar que V6 não tem chamada equivalente antes de `_i18nReady` |
| Tie-break sort `sort((a, b) => b.v - a.v)` | SIM | templates/watcherdb_portal.html | Aplicar `|| (a.idx - b.idx)` nos sorts do card Por Categoria (e no `rowsSorted` se existir) |
| Botão Control `window.open('/watcherdb/control','_blank')` | SIM, mas como **`<a id="userMenuControl">` no menu de utilizador** (:4962), não `controlPanelBtn` | portal | Aplicar o mesmo check: `var _w=window.open(...); if(_w){_w.opener=null}else{toast popup_blocked}` + chave `ui.popup_blocked` nos 3 locales |
| Ping `testServerConnectionFromHeader` com `alert()` | SIM | portal | Trocar `alert` por `showToast(t('ui.no_server_selected'),'warning')` (verificar nome do helper de toast em V6) |
| LIVE `_liveRenderQueries` (command/idle/humanizar) | SIM | portal | Aplicar coluna Command + badge idle (`sleeping`/`AWAITING`/`WAITFOR`) + `elHuman` d/h/m/s + title com start_time |
| LIVE `_liveRenderBlocking` (rótulo instância+timestamp) | SIM | portal | Aplicar `scope` (Instancia X · amostra HH:MM:SS · só esta instância) nos 2 estados + nota no bloco Fleet "BLOCKING ACTIVO" (Blocked/Blocker = SPID) |
| Modal `showProblematicInstances` breakdown crítica/aviso | SIM | portal | Aplicar bloco try/catch após `summaryText` + chaves `kpi_modal.n_critical/n_warning` |
| HSTS só em https | V6 usa **services/web_service/security/headers.py:61** (V6 não tem watcherdb/core/security_headers.py) | headers.py | `if request.url.scheme == 'https' and self.headers_config.get('hsts', True):` — atenção: em V6 este ficheiro é o ACTIVO (em V3.3 é dead code) |
| TLS directo | V6 arranca via **services/web_service/service.py:353** `uvicorn.Server(uvicorn.Config(**config))` e JÁ tem `ssl_certfile` (config.yaml `ssl.enabled`) | service.py | Nada de código; documentar activação no runbook V6 (cert CA interna → PEM; `ssl.enabled: true`) |
| audit.py `logging.FileHandler(audit_log` | SIM (mesmo ficheiro) | services/web_service/security/audit.py | Aplicar `RotatingFileHandler(maxBytes/backupCount de config.yaml logging.rotation)` |
| `GET /api/version` | **NÃO** | — | Adicionar em watcherdb_main V6 (mesmo `_read_version_info`: VERSION.txt ao lado do exe / git sha em fontes) + `Git:` no VERSION.txt do build V6 |
| INSTALL_GUIDE 10.3 porta / 10.3-bis TLS | verificar doc V6 | docs/ | Em V6 a porta vem de config.yaml (caminho activo) — NÃO copiar o texto V3.3 cego; adaptar |

## Diffs de referência (V3.3, para copiar a lógica, não o texto)
- `watcherdb_service.py` `_tls_kwargs()` (env → ssl kwargs, fail-open + log "TLS: ON/OFF")
- `watcherdb/core/security_headers.py:53` gate `request.url.scheme == "https"`
- `services/web_service/security/audit.py:83-97`
- `watcherdb_main.py` `_read_version_info()` + `GET /api/version`
- `templates/watcherdb_portal.html` hunks com comentário "QA externo 2026-08-16" / "QA 2026-08-16"
- `static/i18n/*.json`: `ui.popup_blocked`, `kpi_modal.n_critical`, `kpi_modal.n_warning`
- Testes: `tests/unit/test_security_audit.py` (HSTS https-only; unsafe-inline só em -attr), `tests/unit/test_qa_comprehensive.py`

## Fora deste lote (decisões do owner pendentes; não propagar ainda)
- Norma PT-PT vs PT-BR (`langMap.pt`, normalizar pt.json) — V6 tem o mesmo motor i18n?
- RBAC LIVE (VIEWER vê texto SQL) — decisão de produto
- BUG-003 quick-win (KPI_METADATA title/subtitle via `t('kpi.*')`) — adiado pelo owner em V3.3
