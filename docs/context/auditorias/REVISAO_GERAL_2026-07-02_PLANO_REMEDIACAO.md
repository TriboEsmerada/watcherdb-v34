# Revisão geral V3.3 — Plano de remediação executável

> Data: 2026-07-02 | Autor: orquestrador (síntese de 4 specialists: architecture-advisor,
> sql-deep-reviewer, watcherdb-frontend-specialist, watcherdb-qa-specialist).
> Modo Consultor: **cada bloco é para o owner executar manualmente**. A AI não aplica.
> Blocos ordenados por (risco de execução ↑, retorno ↓). Começar pela Fase 0.

## Checkpoint obrigatório antes de qualquer alteração

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git status
git stash list
# branch dedicada para a remediação (não commitar em main):
git checkout -b fix/revisao-geral-2026-07
```

Identidade: domain user (só git, não toca DB). Rollback global: `git checkout main` + apagar branch.

---

# FASE 0 — Fundação de segurança (bloqueante para POC banking)

## 0.1 — [ALTO/ALTO retorno, baixo risco] Sanitizar identifiers em `diagnose_slow_query`

**Problema:** `api/routers/queries/_diagnostics_legacy.py` — o loop na linha 1036 interpola
`schema`, `obj_name` e `target_database` (vindos de texto de query colada pelo utilizador)
diretamente em SQL dinâmico e em `USE [{target_database}]`. O ficheiro já tem
`_sanitize_sql_identifier()` (linha 30) mas não o aplica neste caminho.

**Fix (reject, não escape):** sanitizar UMA vez no topo do loop; todas as interpolações a
jusante passam a usar os valores validados. Falha fechada (HTTP 400) em input suspeito.

Editar `api/routers/queries/_diagnostics_legacy.py`, logo após a linha 1041
(`target_database = obj_database or detected_database`), inserir:

```python
            # SECURITY (revisão 2026-07-02): identifiers vêm de query colada pelo
            # utilizador. Sanitizar/rejeitar ANTES de qualquer interpolação em SQL
            # dinâmico e em USE [...]. Fail-closed: identifier inválido → HTTP 400.
            schema = _sanitize_sql_identifier(schema, "schema name")
            obj_name = _sanitize_sql_identifier(obj_name, "object name")
            if target_database:
                target_database = _sanitize_sql_identifier(target_database, "database name")
```

Identidade: edição de ficheiro (aprovação manual). Onde: editor.
Impacto: fecha o único vetor de injeção sério. Nomes legítimos (alfanum + `_ @ $ #`)
passam; nomes com `[`, `]`, `'`, espaços ou `;` são rejeitados com 400.
Rollback: `git checkout -- api/routers/queries/_diagnostics_legacy.py`.
Aviso: se preferires "saltar objeto inválido" em vez de abortar o request inteiro,
troca o raise por `continue` num try/except à volta dos 3 `_sanitize_sql_identifier`.
Verificação sugerida: teste unitário que faz POST com `database_name="db]; SELECT 1--"`
e espera 400 (ver Fase 1, item 1.4).

## 0.2 — [ALTO retorno, baixo risco] CI guard anti-IP-do-empregador

**Problema:** nomes de infra interna hardcoded no source (settings.py, auth_service.py,
inventory_manager.py, etc.). Descobrível por qualquer cliente que inspecione o build.

**Fix:** teste que falha o build se padrões proibidos reaparecerem. Não corrige os
existentes (isso é 0.4), mas impede regressão e dá-te a lista viva.

Criar `tests/unit/test_no_employer_ip.py`:

```python
"""Guard: nenhuma referência a infra/IP do empregador no source shippável.

Falha o build se padrões proibidos aparecerem em código de produção. Serve de
rede permanente contra regressão de separação de IP (revisão 2026-07-02).
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Padrões proibidos (nomes de rede/domínio internos). Ajustar à realidade.
FORBIDDEN = re.compile(
    r"tapnet|\bTAP\b|SQLHD|SQLAG|SQLRPA|SQLAD|CAGEN|dchqprd|\.tap\.pt",
    re.IGNORECASE,
)

# Só código shippável. Excluir testes, docs, contexto, este próprio guard.
SCAN_DIRS = ["api", "watcherdb", "services", "modules", "collectors"]
ALLOW_SUFFIX = {".py"}


def _iter_source_files():
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            yield p


def test_no_employer_ip_in_source():
    offenders = []
    for path in _iter_source_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()[:120]}")
    assert not offenders, (
        "Referências a IP do empregador no source (separação de IP):\n"
        + "\n".join(offenders)
    )
```

Identidade: novo ficheiro (aprovação manual). Onde: editor.
Impacto: torna a regressão de IP impossível de passar despercebida. Corre com
`pytest tests/unit/test_no_employer_ip.py -q`.
Aviso: este teste vai **falhar já** (os offenders existentes), o que é o comportamento
correto — dá-te a lista exata a limpar em 0.4. Se quiseres landá-lo antes da limpeza,
marca-o `@pytest.mark.xfail(reason="limpeza IP pendente — item 0.4")` temporariamente.
Rollback: apagar o ficheiro.

## 0.3 — [DECISÃO tua, toca infra partilhada] Identity flip para `sql_monitoring`

**Problema (CRÍTICO):** `api/connection_pool.py:458` usa SEMPRE `Trusted_Connection=yes`;
a variante SQL Auth (linha 490) nunca é chamada. `settings.py:48`
`intelligence_use_windows_auth=True` por default. Viola a Regra de Ouro #2.

**Isto NÃO é um diff simples** — é uma mudança de modelo de segurança com pré-requisito
operacional (GRANTs para `sql_monitoring` nos servidores). O próprio docstring de
`connection_pool.py:467-472` já descreve o que falta:

> "precisaremos de um GRANT EXECUTE em xp_readerrorlog para sql_monitoring em todos os
> servidores, OU manter o Trusted mas com uma conta dedicada de service"

**Caminho proposto (faseado, requer handoff ao V1 specialist por causa da BD partilhada):**

1. Levantar o inventário de permissões que `sql_monitoring` precisa além de `datareader`
   (xp_readerrorlog e afins usados pelos diagnósticos). Query read-only via `sql_monitoring`.
2. Preparar script de GRANTs idempotente (owner executa nos servidores — NÃO a AI).
3. Só depois: flip do default `intelligence_use_windows_auth=False` em `settings.py:48`
   e fazer `_build_connection_string` respeitar a flag (hoje ignora-a).
4. Trusted passa a exigir flag `dev` explícita (nunca default de produção).

**Recomendação:** NÃO tocar código aqui até 1-2 estarem feitos. Abrir handoff formal ao
`watcherdb-v1-intel-specialist` (direito de veto) + `watcherdb-deploy-architect` para o
plano de GRANTs. Este é o item de maior impacto estratégico mas o de maior risco
operacional — merece a sua própria mini-wave, não um commit apressado.

Identidade quando executar: GRANTs = owner nos servidores (não `sql_monitoring`, que é
SELECT-only); código = edição manual. Rollback: reverter a flag repõe Trusted.

## 0.4 — [MÉDIO risco] Limpar IP do empregador do source

Depende de 0.2 (a lista de offenders). Substituir nomes hardcoded por:
- Defaults neutros/vazios em `settings.py:46` (`intelligence_server: str = ""` + validação
  que exige `.env`), forçando configuração no deploy em vez de default shippado.
- Renomear `SmartTapInventoryManager` → `SmartInventoryManager` (grep os importadores:
  `watcherdb_main.py:102` e outros; renomear em bloco).
- Purgar strings de exemplo em `auth_service.py` (domínios, emails, "deploy actual TAP").

Fazer só depois de 0.2 verde como xfail→pass. Owner executa; requer varredura cuidadosa
para não partir imports. Candidato a dispatch do `docs-writer`/`code-explorer` para
mapear todos os call-sites antes de renomear.

---

# FASE 1 — Higiene e CI que realmente corre

## 1.1 — [BAIXO risco, destranca CI] Marker de plataforma no pywin32

**Problema:** `requirements.txt:58` `pywin32>=306` sem marker → `pip install` falha sempre
no runner Linux do CI, antes do pytest. O gate `--cov-fail-under=10` nunca foi avaliado.

Editar `requirements.txt` linhas 57-59:

```diff
 # Windows Management (OS memory/CPU counters via WMI)
-pywin32>=306
-wmi>=1.5.1
+pywin32>=306; sys_platform == 'win32'
+wmi>=1.5.1; sys_platform == 'win32'
```

Impacto: CI Linux passa a instalar e a correr testes. Rollback: reverter linha.
Aviso: `wmi` também é Windows-only — mesmo tratamento. Verificar `winkerberos` (linha 63)
e outras deps Windows-only no mesmo ficheiro e aplicar o marker onde fizer sentido.

## 1.2 — [BAIXO risco, CRÍTICO de segurança de testes] Quarentena de testes que tocam produção

**Problema:** 7+ ficheiros em `tests/integration/` chamam SQL/WMI de produção a nível de
módulo, sem asserts, colecionáveis por `pytest`. Um `pytest tests/integration` dispara
rede real contra servidores de produção.

Mover para fora de `testpaths`. Ficheiros confirmados perigosos:

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
foreach ($f in $perigosos) { if (Test-Path $f) { git mv $f "scripts\manual_debug\" } }
```

Identidade: git mv (aprovação manual). Impacto: `pytest` deixa de poder tocar produção.
Rollback: `git mv` de volta. Aviso: **revê cada ficheiro antes** — alguns podem ter
lógica reaproveitável; ao mover, renomeia sem prefixo `test_` para o pytest nunca os
apanhar mesmo que fiquem noutra pasta scaneada. Confirma com `pytest --collect-only -q`
que nenhuma chamada de rede real aparece na colecção.

## 1.3 — [BAIXO risco] Pre-commit hooks: collect-only + timeout

Adicionar `pytest-timeout` a `requirements-dev.txt` (rede contra o hang determinístico) e
um hook local de colecção. Em `.pre-commit-config.yaml`, dentro do bloco `- repo: local`
(após linha 116), acrescentar:

```yaml
      - id: pytest-collect-only
        name: Pytest collection sanity (no import-time side effects)
        entry: python -m pytest --collect-only -q
        language: system
        pass_filenames: false
        always_run: true
```

E em `requirements-dev.txt`, adicionar `pytest-timeout>=2.2.0`; depois em
`pyproject.toml [tool.pytest.ini_options] addopts` acrescentar `--timeout=60`.
Impacto: qualquer teste com side-effect de import ou hang é apanhado no commit/CI.
Rollback: reverter os 3 ficheiros.

## 1.4 — [BAIXO risco] Teste de regressão para a injeção 0.1

Criar `tests/unit/test_diagnose_query_injection.py` (mockando a execução):

```python
"""Regressão: identifiers de query colada não podem injetar SQL (item 0.1)."""
import pytest
from fastapi import HTTPException
from api.routers.queries._diagnostics_legacy import _sanitize_sql_identifier


@pytest.mark.parametrize("evil", [
    "db]; SELECT 1--",
    "x'; DROP TABLE t--",
    "sch]ema",
    "a b",
    "",
])
def test_sanitize_rejects_injection(evil):
    with pytest.raises(HTTPException) as exc:
        _sanitize_sql_identifier(evil, "test field")
    assert exc.value.status_code == 400


@pytest.mark.parametrize("ok", ["dbo", "MyTable", "col_1", "tmp$x", "a@b", "_x"])
def test_sanitize_accepts_valid(ok):
    assert _sanitize_sql_identifier(ok, "test field") == ok
```

Impacto: cimenta o fix 0.1. Rollback: apagar ficheiro.

## 1.5 — [BAIXO risco] Tier discipline no build (remover código Pro/morto do artefacto)

**Problema:** `deploy/build.py:74-77` protege e shippa `watcherdb_intelligence.py`
(6.390 linhas, zero imports) e o build inclui `copilot*`, `llm_client`, `predictive_alerts*`
(código Pro). Tier discipline está em comentários, não no packaging.

Duas frentes:
1. Remover `watcherdb_intelligence.py` de `PROTECT_FILES` em `deploy/build.py:76`
   (confirmar antes com `grep -rn "import watcherdb_intelligence\|from watcherdb_intelligence" .`
   que nada o importa — a arquitetura já confirmou zero imports).
2. Adicionar exclusão explícita de módulos Pro no build (copilot, llm_client,
   predictive_alerts) — ou um manifest de exclusão tier-aware.

```diff
 PROTECT_FILES = [
     "watcherdb_main.py",
-    "watcherdb_intelligence.py",
 ]
```

Impacto: reduz superfície de ataque + remove IP e código Pro do artefacto Standard.
Rollback: reverter. Aviso: garante que `watcherdb_intelligence.py` não é entry point de
nenhum script de deploy antes de o excluir (o Dockerfile e o .bat usam
`watcherdb_main:app` — confirmado pela arquitetura). Passar `v33-feature-matrix-checker`
sobre o diff antes de commit (regra force-tier-checker).

## 1.6 — [BAIXO risco] Untrack de artefactos e venv

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git rm -r --cached .venv-build 2>$null
# confirmar que .venv-build/ está no .gitignore; se não:
Add-Content .gitignore "`n.venv-build/"
```

Impacto: remove venv commitado por acidente. Rollback: `git reset`.
Aviso: `.nestor/session.log` é tracked por exceção deliberada — decidir se um log de
sessão de AI deve viver no repo comercial (recomendo mover para fora e gitignore).

---

# FASE 2 — XSS e dívida estrutural (esforço M-L)

## 2.1 — [ALTO retorno] Ligar `safeHTML()` aos innerHTML com dados de servidor/erro

**Problema:** `static/js/security_utils.js` expõe `window.safeHTML()` (DOMPurify) mas tem
ZERO call-sites no portal. 482 `.innerHTML=` vs 43 `escapeHtml()`. XSS confirmado em
`templates/watcherdb_portal.html:5763` (`server.name`), `:7013` (`data.server_name`,
`data.summary`), `:7037` (`err.message`).

Abordagem incremental (não precisa framework):
1. Prioridade P0: os sites que interpolam dados de origem servidor ou mensagens de erro.
   Substituir `el.innerHTML = \`...${x}...\`` por construção via `textContent` para os
   pedaços dinâmicos, OU `el.innerHTML = window.safeHTML(\`...\`)` quando precisas de markup.
2. Gate de code-review: proibir `innerHTML =` com template literal interpolado sem passar
   por `safeHTML`/`escapeHtml`. Pode ser um grep-check em CI.

Exemplo (`:5763-5768`, ilustrativo — validar o contexto real):

```js
// ANTES (vulnerável):
item.innerHTML = `<span class="srv-name">${server.name}</span> ...`;
// DEPOIS (opção A — escape do valor):
item.innerHTML = `<span class="srv-name">${escapeHtml(server.name)}</span> ...`;
// DEPOIS (opção B — sanitizar o bloco inteiro):
item.innerHTML = window.safeHTML(`<span class="srv-name">${server.name}</span> ...`);
```

Esforço: M (find/replace disciplinado, começar pelos ~10-15 sites P0). Rollback: git.
Aviso: 482 sites — NÃO fazer tudo de uma vez. Faseamento por origem do dado
(servidor/erro primeiro, estáticos por último). Precisa browser test por lote.

## 2.2 — [BAIXO risco, alta suspeita] Nonce no script anti-FOUC

**Problema:** `templates/watcherdb_portal.html:6` — script inline anti-FOUC sem
`nonce`, enquanto o CSP ativo é `script-src 'self' 'nonce-{nonce}'`
(`watcherdb/core/security_headers.py:88`). Sob CSP estrito o browser bloqueia-o → falha na
sua própria função (flash de tema) — provável causa raiz residual dos bugs de theming.

```diff
-    <script>/* anti-FOUC: aplica o tema antes do paint ... */(function(){...})();</script>
+    <script nonce="{{ csp_nonce }}">/* anti-FOUC ... */(function(){...})();</script>
```

**Verificar PRIMEIRO** (não assumir): confirmar que o portal é servido via Jinja com
`csp_nonce` no contexto do template (grep pela renderização e pelo nome exato da variável
de nonce que o middleware injeta). Se o nome for outro (`nonce`, `request.state.csp_nonce`),
usar esse. Verificação em browser: abrir DevTools → Console e confirmar ausência de
"Refused to execute inline script" após o fix.
Impacto: elimina uma classe inteira de bugs de theme-flash. Rollback: reverter linha.

## 2.3 — [MÉDIO risco] Consolidar acesso a dados

**Problema:** 6 camadas paralelas (mini-pools em `intelligence_kpis.py:286` e
`intelligence/helpers.py:143`, `pyodbc.connect` direto em `jobs.py`, etc.) + config da
Intelligence DB em 4 sítios com precedências diferentes.

Meta-métrica de sucesso: `grep -rn "pyodbc.connect" api/ services/ modules/` fora de
`connection_pool.py` → 0. Fazer por passos, um caller de cada vez, com smoke test de
contrato do endpoint afetado antes e depois. Requer `test-generator` para os smoke tests.
Esforço: M-L. Não fazer sem cobertura de contrato (Fase 1 primeiro).

## 2.4 — [MÉDIO risco] Resolver duplicação `intelligence/`

Decidir: (a) registar o sub-router `api/routers/intelligence/` e apagar os endpoints
duplicados de `intelligence_kpis.py`, OU (b) apagar o pacote `intelligence/`. Hoje há
endpoints vivos e mortos em paralelo → fix aplicado só num lado. Precisa de smoke tests de
contrato por endpoint antes de mexer. Esforço: L.

---

# FASE 3 — Tuning e escala (handoff V1, esforço M)

## 3.1 — Normalizar `Instance` na ingestão (mata scans non-SARGable)

`intelligence_kpis.py:1423,1490,1591,1674,2202` fazem
`LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(f.Instance)))` nos JOINs →
non-SARGable, força scan+hash. Fix real: normalizar `Instance` na escrita (collector V1)
ou computed column persisted+indexed. **Handoff obrigatório ao V1 specialist** (infra
partilhada, direito de veto). Transforma scans em seeks em toda a família de KPIs.

## 3.2 — Guard de corrida BLUE/GREEN sob NOLOCK

View `_STG` (`database/05_WATCHERDB_BLUE_GREEN_ENV.sql:439`) avalia `Active_Slot` por
subquery-por-ramo (6×) sob READ UNCOMMITTED; se o swap commitar a meio → double-count ou
zero. Fix: `KPI_STG_ACTIVE_TABLE WITH (READCOMMITTEDLOCK)` na subquery de slot, ou
snapshot único de `Active_Slot` por query. Handoff V1.

## 3.3 — Paginação real

`api/pagination.py:39` faz fetch-all-then-slice em Python. Migrar para OFFSET/FETCH
(SQL 2012+) ou keyset nos endpoints de listagem grandes. Esforço: M.

---

# Guard-rail transversal (barato, alto valor)

Lint CI grep-based que bloqueia `color:\s*#[0-9a-f]{3,8}` novo em CSS fora de `:root`/tokens
`var(--...)` — mata o whack-a-mole de theming (dezenas de commits `fix(V3.3/UX)`). ~30
linhas de script em CI, sem ferramenta nova. Mesmo padrão para o grep anti-`STRING_AGG`
(guard do piso SQL 2014) e o grep anti-innerHTML-sem-escape (item 2.1).

---

# Ordem recomendada de execução

1. Checkpoint (branch).
2. Fase 0.1 + 1.4 (injeção + teste) — 1 commit.
3. Fase 1.1 + 1.2 + 1.3 (CI destrancado + quarentena) — 1 commit.
4. Fase 0.2 (guard IP xfail) + 0.4 (limpeza) + 1.5 (build) — 1 commit, passar
   `v33-feature-matrix-checker`.
5. Fase 1.6 (untrack) — 1 commit.
6. Fase 2.2 (nonce) — 1 commit + browser test.
7. Fase 2.1 (XSS P0) — lotes com browser test.
8. Fase 0.3 (identity flip) — mini-wave própria com handoff V1 + deploy-architect.
9. Fase 2.3/2.4 + Fase 3 — handoffs V1, com cobertura de contrato primeiro.

Cada commit: PowerShell single-quote, múltiplos `-m`, sem `->`/`[[...]]`/`"` no argv
(ver memória powershell-commit-msg-safe-chars).
