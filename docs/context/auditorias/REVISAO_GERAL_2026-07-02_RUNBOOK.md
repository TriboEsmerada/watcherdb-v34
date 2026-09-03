# Runbook de execução — Correções revisão geral V3.3

> Data: 2026-07-02 | Companion de `REVISAO_GERAL_2026-07-02_PLANO_REMEDIACAO.md`.
> Este runbook é a **ordem de execução commit-a-commit**. O plano tem o *porquê* e o
> código; este tem o *como e quando*. Modo Consultor: **owner executa cada bloco**.
>
> Regras de commit (memória): PowerShell, `cd` no início de cada bloco, múltiplos `-m`
> single-quote, SEM `->` / `[[...]]` / `"` no argv. Antes de cada commit V3.3: passar
> `v33-feature-matrix-checker` (dispatch modo B).

## Convenções

- **[EDIT]** = alteração manual num ficheiro (bloco no plano de remediação).
- **[RUN]** = comando a correr.
- **[VERIFY]** = validação antes de avançar.
- Identidade: domain user para git/ficheiros; `sql_monitoring` só se houver query DB
  (nenhum commit abaixo toca DB, exceto o levantamento opcional do C7).

---

## C0 — Checkpoint (antes de tudo)

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git status
git checkout -b fix/revisao-geral-2026-07
```

[VERIFY] `git status` limpo (ou stash do que não pertence). Branch nova ativa.
Rollback global desta remediação: `git checkout main` + `git branch -D fix/revisao-geral-2026-07`.

---

## C1 — Fecha injeção SQL + teste de regressão

Itens do plano: **0.1** + **1.4**.

[EDIT] `api/routers/queries/_diagnostics_legacy.py` — inserir as 6 linhas de sanitização
após a linha 1041 (bloco 0.1 do plano).

[EDIT] Criar `tests/unit/test_diagnose_query_injection.py` (bloco 1.4 do plano).

[RUN]
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
python -m pytest tests\unit\test_diagnose_query_injection.py -q
```
[VERIFY] Todos os testes passam (rejeita injeção, aceita válidos).

[RUN] commit:
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git add api/routers/queries/_diagnostics_legacy.py tests/unit/test_diagnose_query_injection.py
git commit -m 'fix(V3.3/security): sanitiza identifiers em diagnose_slow_query' -m 'Query colada pelo utilizador interpolava schema/obj_name/target_database direto em SQL dinamico e USE. Aplica _sanitize_sql_identifier (fail-closed 400) no topo do loop; cobre todas as interpolacoes a jusante. Regressao em test_diagnose_query_injection.' -m 'Ref: auditorias/REVISAO_GERAL_2026-07-02 item 0.1'
```

Impacto: fecha o único vetor de injeção sério. Rollback: `git revert HEAD`.

---

## C2 — Destranca o CI + quarentena de testes de produção

Itens do plano: **1.1** + **1.2** + **1.3**.

[EDIT] `requirements.txt` linhas 57-59: adicionar `; sys_platform == 'win32'` a
`pywin32` e `wmi` (bloco 1.1).

[EDIT] `requirements-dev.txt`: acrescentar `pytest-timeout>=2.2.0` na secção Testing.

[EDIT] `pyproject.toml` `addopts` (linha 106): acrescentar `--timeout=60`.

[EDIT] `.pre-commit-config.yaml`: adicionar hook `pytest-collect-only` no bloco
`- repo: local` (bloco 1.3).

[RUN] quarentena (bloco 1.2 — **revê cada ficheiro antes**):
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
New-Item -ItemType Directory -Force scripts\manual_debug | Out-Null
$perigosos = @(
  'tests\integration\test_cluster_api.py',
  'tests\integration\test_cluster_com.py',
  'tests\integration\test_cluster_events.py',
  'tests\integration\test_cluster_fast.py',
  'tests\integration\test_cluster_python_vs_powershell.py',
  'tests\integration\test_cluster_timeout_15s.py',
  'tests\integration\test_backend_connection.py',
  'tests\integration\test_sqlhdsprd014.py',
  'tests\integration\test_memory_integration.py',
  'tests\integration\test_os_memory_api.py',
  'tests\integration\test_os_memory_scenarios.py',
  'tests\integration\test_favicon.py',
  'tests\integration\test_admin_auth.py'
)
foreach ($f in $perigosos) { if (Test-Path $f) { git mv $f 'scripts\manual_debug\' } }
```

[VERIFY] **Crítico** — confirmar que a colecção já não toca produção:
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
python -m pytest --collect-only -q 2>&1 | Select-String -Pattern 'Error|Connection|SQLHD|SQLAD' 
```
Se aparecer alguma ligação/erro de import com nome de servidor, ainda há um ficheiro
perigoso por mover — repetir até a lista sair vazia.

[RUN] commit:
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git add requirements.txt requirements-dev.txt pyproject.toml .pre-commit-config.yaml
git add tests/integration scripts/manual_debug
git commit -m 'fix(V3.3/ci): destranca CI Linux e isola testes que tocam producao' -m 'pywin32/wmi ganham marker sys_platform win32 (install Linux falhava antes do pytest). Move 13 scripts de tests/integration que faziam SQL/WMI de producao a nivel de modulo para scripts/manual_debug (fora de testpaths). Adiciona pytest-timeout 60s e hook pre-commit collect-only.' -m 'Ref: auditorias/REVISAO_GERAL_2026-07-02 itens 1.1 1.2 1.3'
```

Impacto: CI passa a correr testes; `pytest` deixa de poder disparar rede de produção.
Rollback: `git revert HEAD` (repõe os ficheiros nas pastas originais).

---

## C3 — Guard anti-IP + tier discipline no build

Itens do plano: **0.2** + **1.5**. (A limpeza 0.4 fica para C4, separada, por ser a de
maior risco de partir imports.)

[EDIT] Criar `tests/unit/test_no_employer_ip.py` (bloco 0.2). Marcar
`@pytest.mark.xfail(reason="limpeza IP pendente - item 0.4")` na função de teste por
agora — vai passar a green só depois de C4.

[VERIFY] confirmar que `watcherdb_intelligence.py` não é importado (arquitetura já
confirmou zero imports reversos):
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
Select-String -Path (Get-ChildItem -Recurse -Filter *.py -Path api,services,modules,watcherdb,collectors).FullName -Pattern 'import watcherdb_intelligence|from watcherdb_intelligence' | Select-Object -First 5
```
Esperado: zero resultados. Se aparecer algum, NÃO remover de PROTECT_FILES ainda.

[EDIT] `deploy/build.py:76`: remover `"watcherdb_intelligence.py",` de `PROTECT_FILES`
(bloco 1.5).

[RUN] dispatch tier-checker (modo B):
```
# dispatchar v33-feature-matrix-checker sobre o diff de deploy/build.py
# esperar PASS antes de commitar
```

[RUN] commit:
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git add tests/unit/test_no_employer_ip.py deploy/build.py
git commit -m 'chore(V3.3/build): guard anti-IP e remove monolito morto do artefacto' -m 'Novo teste (xfail ate limpeza 0.4) que falha o build se nomes de infra interna reaparecerem no source. Remove watcherdb_intelligence.py (6390 linhas, zero imports) de PROTECT_FILES: reduz superficie de ataque e IP no artefacto Standard.' -m 'Ref: auditorias/REVISAO_GERAL_2026-07-02 itens 0.2 1.5'
```

Impacto: regressão de IP passa a falhar o build; artefacto Std mais magro.
Rollback: `git revert HEAD`.

---

## C4 — Limpeza do IP do empregador (maior risco de imports)

Item do plano: **0.4**. Depende da lista de offenders que C3 (test_no_employer_ip) produz.

[RUN] obter a lista exata:
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
python -m pytest tests\unit\test_no_employer_ip.py -q 2>&1 | Select-String ':'
```

[EDIT] por offender:
- `watcherdb/core/settings.py:46`: `intelligence_server: str = ""` (forçar via .env).
- Renomear `SmartTapInventoryManager` -> `SmartInventoryManager` em bloco (mapear
  call-sites primeiro — `watcherdb_main.py:102` e outros; usar `code-explorer`).
- `services/auth_service.py`: purgar domínios/emails/strings de exemplo.
- Restantes ficheiros da lista (backup_analysis, alwayson, scripts/...).

[EDIT] `tests/unit/test_no_employer_ip.py`: remover o `xfail` (agora deve passar green).

[VERIFY]
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
python -m pytest tests\unit\test_no_employer_ip.py -q
python -c "import watcherdb_main"   # smoke: imports nao partiram
```

[RUN] commit (só depois de imports OK):
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git add -A
git commit -m 'refactor(V3.3/ip): remove referencias a infra do empregador do source' -m 'Defaults neutros em settings, rename SmartTapInventoryManager para SmartInventoryManager, purga strings de exemplo em auth_service. test_no_employer_ip passa a green (xfail removido).' -m 'Ref: auditorias/REVISAO_GERAL_2026-07-02 item 0.4'
```

Impacto: separação de IP cumprida no source. Rollback: `git revert HEAD`.
Aviso: este é o commit com mais risco de partir imports — fazer devagar, um ficheiro de
cada vez, correndo `python -c "import watcherdb_main"` entre renomeações.

---

## C5 — Untrack de venv e higiene de repo

Item do plano: **1.6**.

[RUN]
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git rm -r --cached .venv-build
Add-Content .gitignore "`n# venv de build (nao commitar)`n.venv-build/"
```

[VERIFY] `git status` mostra os 20 ficheiros como deleted-from-index (não do disco).

[RUN] commit:
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git add .gitignore
git commit -m 'chore(V3.3/repo): untrack .venv-build commitado por acidente' -m '20 ficheiros de venv estavam tracked. Remove do index e adiciona ao gitignore. Ficheiros permanecem no disco.' -m 'Ref: auditorias/REVISAO_GERAL_2026-07-02 item 1.6'
```

Decisão pendente (não neste commit): `.nestor/session.log` é force-included no
`.gitignore:60` — decidir se um log de sessão de AI deve viver no repo comercial.

---

## C6 — Nonce no anti-FOUC (frontend, precisa browser test)

Item do plano: **2.2**.

[VERIFY primeiro] confirmar o nome da variável de nonce no contexto Jinja:
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
Select-String -Path watcherdb_main.py,watcherdb\core\security_headers.py -Pattern 'nonce'
```
Usar o nome real (`csp_nonce`, `nonce`, `request.state...`) no atributo.

[EDIT] `templates/watcherdb_portal.html:6`: adicionar `nonce="{{ csp_nonce }}"` (ou o
nome confirmado) à tag `<script>` anti-FOUC.

[VERIFY] browser: abrir o portal em DEV, DevTools -> Console, confirmar ausência de
"Refused to execute inline script". Testar troca de tema Claro/Escuro sem flash.

[RUN] commit:
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git add templates/watcherdb_portal.html
git commit -m 'fix(V3.3/UX): nonce no script anti-FOUC para passar CSP estrito' -m 'Script inline de tema era bloqueado pelo CSP script-src self nonce, falhando na sua funcao (flash de tema). Provavel causa raiz residual dos bugs de theming.' -m 'Ref: auditorias/REVISAO_GERAL_2026-07-02 item 2.2'
```

Impacto: elimina classe de bugs de theme-flash. Rollback: `git revert HEAD`.

---

## C7+ — Itens que NÃO entram nesta série (planeamento à parte)

Estes exigem mais do que um commit e/ou handoff — tratar em waves próprias:

- **0.3 Identity flip** (`sql_monitoring`): mini-wave. Pré-requisito = levantamento de
  permissões (query read-only via `sql_monitoring`) + plano de GRANTs (owner executa nos
  servidores) + handoff `watcherdb-v1-intel-specialist` (veto) e `watcherdb-deploy-architect`.
- **2.1 XSS `safeHTML()`**: 482 sites — lotes por origem de dado (servidor/erro primeiro),
  browser test por lote. Wave dedicada de frontend.
- **2.3 Consolidar acesso a dados** e **2.4 duplicação `intelligence/`**: precisam de
  cobertura de contrato por endpoint primeiro (dispatch `test-generator`).
- **Fase 3** (normalizar Instance, guard BLUE/GREEN, paginação): handoff V1.
- **Guard-rail CSS anti-#hex** e grep guards (SQL 2014, innerHTML): 1 commit de CI quando
  houver folga; barato e permanente.

---

## Resumo da série pronta a executar

| Commit | Itens | Risco | Toca DB? | Handoff? |
|--------|-------|-------|----------|----------|
| C0 | checkpoint | — | não | não |
| C1 | 0.1 + 1.4 | baixo | não | não |
| C2 | 1.1 + 1.2 + 1.3 | baixo | não | não |
| C3 | 0.2 + 1.5 | baixo | não | tier-checker |
| C4 | 0.4 | médio | não | code-explorer p/ mapear |
| C5 | 1.6 | baixo | não | não |
| C6 | 2.2 | baixo | não | browser test |
| C7+ | 0.3, 2.1, 2.3, 2.4, F3 | alto | 0.3/F3 sim | V1 + deploy |

C1→C6 são executáveis já, em sequência, sem tocar DB nem infra partilhada.
