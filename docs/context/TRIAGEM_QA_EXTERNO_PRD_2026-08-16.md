# Triagem do relatório QA externo (browser-agent cloud) — WatcherDB V3.3 PRD, 2026-08-16

Fonte: relatório de teste exploratório read-only ao portal em PRD (10.88.10.27:8433), sessão ADMIN, ~20 min, 14 IDs (BUG-001..014; ~50% do texto chegou truncado). Vistoria anterior do mesmo QA (2026-08-14) foi ao SSIS Manager (outro produto; evidências em Downloads/qaevidencias).
Council consultado (5 pareceres, read-only): frontend-specialist, security-auditor, v33-specialist, qa-specialist (meta-review), deploy-architect. Detalhes completos nos pareceres registados em `~/.nestor-vault/session.log` (2026-08-16) e `bulletin/inbox.md`.

## Veredicto por bug (consenso)

| ID | QA | Council | Causa real | Fix | Esf. |
|---|---|---|---|---|---|
| BUG-001 Control "morto" | Alto | **FALSO POSITIVO** + achado colateral Baixo | `portal.html:3986` `window.open('/watcherdb/control','_blank')` correcto; rota `watcherdb_main.py:3265` OK; CSP já corrige inline handlers (`security_headers.py:81-126`, 8309147). Harness headless bloqueia popup → zero request. | Verificar retorno de `window.open` + toast "popup bloqueado" + `noopener` (afecta users reais com popup-blocker) | S |
| BUG-002/010 HTTP sem TLS | Alto+Crítico | **CONFIRMADO, 1 item**, CVSS 5.9 Medium (AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N), remediação HIGH (banking/DORA), CWE-319 | Entry point real `watcherdb_service.py:213` (`deploy/watcherdb.spec:32`) NÃO tem `ssl_*`; o TLS "já feito" está em `services/web_service/service.py:307` = DEPRECATED. HSTS incondicional `watcherdb/core/security_headers.py:54`. | (a) `_tls_kwargs()` env `WATCHERDB_TLS_CERT/KEY` → `ssl_certfile/ssl_keyfile` em `watcherdb_service.py` (fail-open HTTP + log "TLS: ON/OFF"); (b) HSTS só se `request.url.scheme=="https"`; TLS directo uvicorn, cert CA interna→PEM, porta 8433 mantida, HTTP desligado | S código / M operação |
| BUG-003 i18n EN/ES | Médio | CONFIRMADO | pt/en/es têm 1406 chaves IDÊNTICAS — não é dicionário. `KPI_METADATA` (`portal.html:32559-33255`) 24 title+24 subtitle hardcoded; parte dos ~435 strings já mapeados (bulletin 2026-07-21). Troca de idioma faz re-fetch da API (perf colateral). | Quick win: 48 strings → `t('kpi_meta.<id>.*')`; cobertura completa = iniciativa própria (L) | S/L |
| BUG-004 FOUC chaves | Médio | CONFIRMADO (race) | `init()` `portal.html:5621` chama `applyLanguageToUI()` sem guard antes de `_i18nReady`; `applyI18nWhenReady()` (`:46887`) já cobre. Duplo fetch de pt.json (`:4614-4629` + `i18n_v2.js:619`). Mesma família do race DOMContentLoaded 2026-08-12. | Remover a chamada em `init()`; cache-check em `_loadDictionary` | S |
| BUG-005 PT-PT/PT-BR | Médio | CONFIRMADO | HTML estático `lang="pt-PT"` correcto, mas `i18n_v2.js:186,642` `langMap.pt='pt-BR'` sobrescreve; `:26935` export TempDB hardcoded pt-BR. pt.json: Atualizar 12 vs Actualizar 2; Utilizador 8 vs usuário 2. | Norma **PT-PT** (owner decide); langMap→pt-PT; normalizar pt.json com revisão humana; lint tokens BR | M |
| BUG-006 sort empates | Médio | PROVÁVEL (Baixo) | `portal.html:34337,34390` `.sort((a,b)=>b.v-a.v)` sem tie-breaker; parte do sintoma = flutuação real de valores | `|| a.idx - b.idx` (também `:34625`) | S |
| BUG-007 Fleet blocking vs sub-tab | Médio | UX enganadora, dados correctos (Baixo) + achado estrutural | 3 fontes DMV live: fleet drill top-8 (`live_monitoring.py:884-1222`), sub-tab por canal seleccionado (`:417-428`, canal persistido em localStorage), header `Blk: --` esperado em modo Fleet. "Blocked 128" = SPID, não contagem. Duas queries "blocking" sem contrato (`:84` vs `:1044-1215`). | Rotular `Instance X | actualizado HH:MM:SS`; distinguir "sem canal" de "0 confirmado"; teste de contrato | S |
| BUG-008 duração 1.3M s | Baixo | Plausível, não bug de unidade | `RUNNING_QUERIES_SQL` `live_monitoring.py:142` DATEDIFF(SECOND) correcto; sessão sleeping/AWAITING COMMAND com transacção aberta ~15 dias (achado operacional real p/ DBA). `command` vem no payload mas não é mostrado; `>300s` pinta igual. | Mostrar command/status; badge "idle desde"; humanizar "15d 4h" (estender `formatDurationSeconds` `:13357`) | S |
| BUG-009 Ping sem feedback | Baixo | FALSO POSITIVO (existe `alert()` `portal.html:35199`) + UX | Automação auto-dispensa dialogs nativos | Trocar alert por toast aria-live + chave i18n | S |
| BUG-014 card crítico vs WARNING | Cosmético | Semântica correcta (card = ANY-critical, modal = crit+warn `helpers.py:809-816`) + staleness cache 60s vs modal live (censo 2026-08-11) | — | Cabeçalho da modal "N críticas / M avisos"; `snapshot_age_sec` no payload | S |
| BUG-011/012/013 | — | NÃO TRIÁVEIS (texto perdido) | pedir reenvio ao QA | | |

## Achados novos do council (fora do relatório)
- **RBAC LIVE**: `UserRole` ADMIN/VIEWER existe (`auth.py:48-51`) mas `AuthEnforcementMiddleware` (`watcherdb_main.py:671`) não checa role; `live_monitoring.py:29-31` sem dependency → VIEWER vê texto SQL/xp_cmdshell/logins. Decisão de produto pendente (owner). Sem tier creep (FEATURE_MATRIX não menciona TLS/RBAC/masking).
- **Logs sem rotação**: `services/web_service/security/audit.py:83` `FileHandler` simples apesar de `config.yaml:190-192` declarar rotation — audit.log 322 MB, stdout.log 1.37 GB, stderr 641 MB localmente. Risco disco em cliente. Fix S.
- **Sem endpoint de versão**: `/` devolve `3.0.0-real-data` placeholder; sem GIT_SHA/BUILD_INFO. Evidência circunstancial (zero erros CSP, zero 4xx) sugere PRD ≥ 0b1efe8.
- CSP legado com unsafe-eval (`services/web_service/security/headers.py`) é dead code — recomendar apagar fisicamente.
- `docs/external/standard/INSTALL_GUIDE.md:465` manda editar `services/web_service/config.yaml` (caminho deprecated) para mudar porta — cliente segue e nada muda.
- HSTS `includeSubDomains` + CN `watcherdb.tap.pt` → ao ligar TLS prende `*.tap.pt` 1 ano nos browsers; rever antes de activar.
- Suite QA V3.3 (15 levels) é 100% backend — estruturalmente incapaz de apanhar qualquer bug i18n/sort/FOUC/botão. 5 testes propostos: i18n parity; top-6 tiebreak; blocking contract; security-headers-stack na app real; `test_pyinstaller_boot` + `/watcherdb` + `/watcherdb/control`.

## Meta-review do relatório (qa-specialist): ~5.2/10
Bem: separação evidência/hipótese, selectores, console logs. Mal: severidade mal calibrada (HTTP interno=Crítico; BUG-001 Alto sem considerar limite do harness), duplicado 002/010 contado 2x, cobertura rasa (20 min, só admin, sem payloads no campo de busca, sem varrimento de período dos cards), 50% truncado. BUG-003 causa-raiz do QA errada (não são chaves em falta).
Playbook SSIS a replicar em V3.3: `available:false` mascarado como 0 verde (precedente `intelligence_kpis.py:2501` p3_count / `:1930` is_damaged); leak texto ODBC nos erros; card→modal→API contagens (Integridade/Backup); janela label vs real; XSS no campo de busca (confirmar DOMPurify).

## Governance
Credencial ADMIN pessoal (`salomao`) usada num browser cloud de terceiro sobre HTTP contra PRD → SQL text, logins AD, hostnames PRD saíram da rede do cliente. Recomendado: rotação da password; próximas rondas em ambiente não-PRD (8443/QLT) com TLS + conta viewer dedicada + escopo escrito. Rasto: `services/web_service/logs/audit.log` (JSONL, `username` por request).

## Plano de correcção proposto (lotes `fix(v33): ...`, ordem)
1. **TLS + HSTS gate** — `watcherdb_service.py` (`_tls_kwargs`) + `security_headers.py:54`; validar QLT → PRD (checklist rollout/rollback do deploy-architect: certs em ProgramData\WatcherDB\certs c/ icacls, env no .env, Restart-Service, `https://localhost:8433/api/v3/health`). Bloqueador piloto.
2. **Rotação de logs** audit/stdout/stderr → `RotatingFileHandler`. Urgência operacional.
3. **Frontend lote S** — BUG-004 (remover chamada), BUG-006 (tie-break), BUG-001 (popup check+noopener+toast), BUG-009 (toast), BUG-003 quick-win (48 strings), BUG-008 (command/idle/humanizar), BUG-007 (labels instância+timestamp), BUG-014 (breakdown modal).
4. **BUG-005** após decisão de norma do owner (PT-PT recomendado) + lint.
5. **Decisão RBAC LIVE** (owner) → 1 dependency no router se VIEWER não deve ver LIVE.
6. `/api/version` (git_sha/build_date) + corrigir INSTALL_GUIDE:465 + apagar CSP legado.
7. Responder ao QA: aceitar 003/004/005/006; needs-info 007(detalhe)/008(session)/011-013/014(card exacto); not-reproducible 001/009 (pedir reteste com popup/dialog handlers); 002/010 aceite como 1 item infra.
