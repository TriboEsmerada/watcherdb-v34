# RUNBOOK Etapa 0 — Fundações do empacotamento (commit-a-commit)

Data: 2026-07-03 | Modo consultor: owner executa cada bloco manualmente.
Origem: AUDITORIA_EMPACOTAMENTO_2026-07-03_FASE4.md (roadmap aprovado, D1-D4).
Identidade: TUDO nesta etapa corre na workstation dev, SEM tocar em DB nenhuma,
SEM admin. Rollback global: git (branch dedicada, C0).
ERRATA: item 0.5 (string V32 em setup_database.ps1) CAI — verificação nas
linhas reais mostra que setup_database.ps1:143 JÁ diz WatcherDBWebServiceV33.
Achado B2-16 da Fase 1 marcado inválido.

## C0 — Checkpoint (obrigatório antes de qualquer edição)

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git status
git checkout -b wave-packaging-etapa0
```
Impacto: nenhum. Rollback: `git checkout fix/v33-portal-abort-cache-serverlist`.
Nota: estás em `fix/v33-portal-abort-cache-serverlist` — se tiver trabalho
uncommitted alheio a isto, commit/stash primeiro.

## C1 — encoding utf-8 na leitura de sql_servers.json (B1-9)

Ficheiro: watcherdb_main.py, linha 153.
ANTES:
```python
        with open(config_path, 'r') as f:
```
DEPOIS:
```python
        with open(config_path, 'r', encoding='utf-8') as f:
```
Impacto: leitura correta em máquina com codepage ANSI (cp1252); zero mudança
em dev. Teste: `python -c "import json; json.load(open('config/sql_servers.json', encoding='utf-8'))"`.
Rollback: git restore.

## C2 — custom_queries.json ancorado a _PROJECT_ROOT (B1-7)

Ficheiro: watcherdb_main.py, linha 1322.
ANTES:
```python
        config_path = Path("config/custom_queries.json")
```
DEPOIS:
```python
        config_path = _PROJECT_ROOT / "config" / "custom_queries.json"
```
(_PROJECT_ROOT já é Path — watcherdb_main.py:85.)
Impacto: endpoint admin de custom queries deixa de depender do CWD do processo.
Teste: arrancar dev + gravar custom query pela UI (ou POST ao endpoint).
Rollback: git restore.

## C3 — Versão: alinhar com a SOT release_vars.psd1 (B2-15)

3a. watcherdb/core/settings.py, linha 29.
ANTES:
```python
    app_version: str = "3.2.0"
```
DEPOIS:
```python
    # SOT de versão: deploy/release_vars.psd1 (ProductVersion). Manter em sync
    # manualmente até o build_release.ps1 (Fase 4 §4.2 passo 2) automatizar.
    app_version: str = "3.3.0"
```
3b. pyproject.toml, linha 7.
ANTES:
```toml
version = "1.0.0"
```
DEPOIS:
```toml
version = "3.3.0"
```
Impacto: /health e metadados passam a reportar a versão real. Os endpoints do
código morto services/web_service/server.py ficam como estão (morrem na
Etapa 2). Teste: `pytest tests -k version` (se existir) + arranque dev.
Rollback: git restore.

## C4 — build.py: PyArmor fail-loud + remover EXCLUDE morto (B2-17, B2-18)

4a. Topo do deploy/build.py (junto aos imports/constantes), ADICIONAR:
```python
# Fail-loud: por default o build ABORTA se algum ficheiro ficar sem proteção
# PyArmor (caso real 2026-05-13: dashboard_api.py shipado unprotected via
# fallback silencioso — pyarmor.bug.log). Override consciente: --allow-unprotected.
ALLOW_UNPROTECTED = "--allow-unprotected" in sys.argv
```
4b. deploy/build.py linhas 245-247.
ANTES:
```python
                if r2.returncode != 0:
                    log(f"  Failed: {rel_path} — copying unprotected as fallback", "WARN")
                    shutil.copy2(py_file, target_dir / py_file.name)
```
DEPOIS:
```python
                if r2.returncode != 0:
                    if ALLOW_UNPROTECTED:
                        log(f"  Failed: {rel_path} — copying UNPROTECTED (--allow-unprotected)", "WARN")
                        shutil.copy2(py_file, target_dir / py_file.name)
                    else:
                        log(f"  PyArmor failed on {rel_path}: {r2.stderr[:300]}", "ERROR")
                        log("  BUILD ABORTED: file would ship unprotected. Fix the cause or re-run with --allow-unprotected.", "ERROR")
                        return False
```
4c. deploy/build.py linhas 105-127: APAGAR o bloco `EXCLUDE = [...]` inteiro e
substituir por:
```python
# NOTA: a proteção do que entra no bundle é o modelo ALLOWLIST
# (PROTECT_DIRS/COPY_DIRS/COPY_FILES). Não existe camada de exclusão ativa —
# uma lista EXCLUDE anterior estava definida mas nunca aplicada (removida
# 2026-07-03, auditoria empacotamento B2-17). A sanitização de config/ com
# dados reais é a Etapa 1.3 do roadmap.
```
Impacto: builds futuros falham em vez de vazar código sem obfuscação; zero
efeito em runtime. Teste: `python deploy/build.py --help` não parte (parse de
argv é por `in`, não argparse — sem conflito). Rollback: git restore.

## C5 — Deprecar installer legacy pywin32 (B3-20)

Ficheiro: services/web_service/install.py, docstring (linhas 1-17), ADICIONAR
no topo da docstring:
```
    *** DEPRECATED (2026-07-03, auditoria empacotamento B3-20) ***
    Este instalador dev-only regista o MESMO nome de serviço
    (WatcherDBWebServiceV33) que o caminho canónico de packaging, apontando
    para outra app/porta — usar em máquina com o pacote instalado SOBRESCREVE
    o ImagePath silenciosamente. Uso permitido: APENAS dev local sem pacote.
```
E no início de `main()` (ou do dispatch de comandos), ADICIONAR:
```python
    print("[AVISO] Instalador DEV-ONLY (deprecated 2026-07-03). Nunca usar em maquina com o pacote WatcherDB instalado — sobrescreve o servico do MSI/ZIP.")
```
Impacto: nenhum funcional; atrito deliberado. Rollback: git restore.

## C6 — Lockfile de build (B1-12) — comandos, owner executa

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
py -3.11 -m pip install pip-tools
py -3.11 -m piptools compile requirements.txt -o requirements.lock --strip-extras
git add requirements.lock
```
Depois (mesma sessão), validar que o lock instala limpo num venv descartável:
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
py -3.11 -m venv .venv-locktest
.venv-locktest\Scripts\python -m pip install -r requirements.lock
.venv-locktest\Scripts\python -c "import fastapi, pyodbc, pydantic, win32service; print('lock OK')"
Remove-Item -Recurse -Force .venv-locktest -Confirm:$false
```
ATENÇÃO ao par passlib/bcrypt: se o compile resolver bcrypt>=5 com passlib
1.7.4, PINAR `bcrypt<4.1` no requirements.txt antes de recompilar (incompat.
conhecida — Fase 1 B1-12). Futuro build_release.ps1 usa `pip-sync requirements.lock`.
Impacto: builds reprodutíveis. Rollback: apagar requirements.lock.

## C7 — Validação da etapa

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
python -m pytest -m "not e2e" -q
python watcherdb_main.py   # arranque dev, Ctrl+C após /health responder em :8000
```
Critério: suite no estado baseline (sem novas falhas) + arranque limpo.

## C8 — Commit (mensagens PowerShell-safe: single-quote, sem ">", sem "[[")

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git add watcherdb_main.py watcherdb/core/settings.py pyproject.toml deploy/build.py services/web_service/install.py requirements.lock
git commit -m 'fix(packaging): etapa 0 auditoria empacotamento' -m 'encoding utf-8 sql_servers (B1-9); custom_queries ancorado a PROJECT_ROOT (B1-7); versao alinhada a release_vars 3.3.0 (B2-15); build.py fail-loud PyArmor + remocao EXCLUDE morto (B2-17/18); deprecation installer legacy pywin32 (B3-20); requirements.lock pip-tools (B1-12). Ver docs/context/auditorias/AUDITORIA_EMPACOTAMENTO_2026-07-03_RUNBOOK_ETAPA0.md'
```
Gate tier (feature-matrix-checker): NÃO aplicável — zero superfície de feature
Std/Pro neste diff (só build/paths/versão). Dispatch disponível se quiseres
na mesma.

## D2 em paralelo (processo externo, sem código)

Azure Trusted Signing (Artifact Signing): criar resource no tenant Azure da
organização (região UE), submeter identity validation da empresa (histórico
verificável exigido), criar certificate profile Public Trust, e testar
signtool com o dlib da Microsoft num PE de exemplo. Só depois adaptar
sign_msi.ps1 (Etapa 3). Se a elegibilidade falhar → fallback DigiCert OV (~$400/ano).

## Próximo (após C0-C8 validados)

Etapa 1 — diffs preparados sob pedido, por ordem: 1.1 paths.py resolver 3-tier
(desenho na FASE2 §1), 1.2 identity flip (coordenar com handoff 0.3 + veto
v1-intel), 1.3 sanitização do bundle, 1.4 DPAPI machine-scope, 1.5 mutex,
1.6 .env ProgramData-first.
