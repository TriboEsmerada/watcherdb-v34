# Runbook — Rebuild do runtime para CPython 3.13.15

**Data:** 2026-08-20 · **Autor:** sessão AI (consulta deploy-architect + security-auditor)
**Objetivo:** fechar as 29 CVEs de runtime (Python 3.11.9 + SQLite 3.45.1.0) migrando o
`.venv-build` para CPython 3.13.15 (binário oficial PSF, SQLite 3.50.4).
**Estado:** aguarda resultado do SPIKE (Fase 0) antes de comprometer calendário.

---

## Porque 3.13.15 (e não 3.12 nem 3.11-source)

- **3.11.9** foi a última 3.11 com instalador Windows oficial. 3.11.10+ é source-only.
- **3.12** é beco sem saída: security-only desde 3.12.10, e o CPython **fechou** o PR
  que traria o SQLite 3.50.4 ao 3.12 ("só afeta instaladores, que não construímos para
  ramos security-only"). Nunca fecha a CVE de SQLite num instalador.
- **3.11 compilado do source**: vira a nossa equipa responsável pela cadeia de build do
  interpretador — pior história de proveniência para auditoria bancária.
- **3.13.15** (05/08/2026): binário oficial assinado PSF, SQLite 3.50.4, fecha as 17 CVEs
  incluindo o *bypass* da CVE-2025-4330 (só corrigido no 3.13.15). Runway até 2029-10.

---

## FASE 0 — SPIKE (RESULTADO 2026-08-20: VERDE no ponto crítico)

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
py -3.13 -m venv .venv-build-313-spike
.\.venv-build-313-spike\Scripts\python.exe -m pip install setuptools   # ver PRÉ-REQ 1
.\.venv-build-313-spike\Scripts\python.exe -m pip install -r requirements-build.lock
$env:PATH = "C:\Program Files\LLVM\bin;" + $env:PATH                    # ver PRÉ-REQ 2
.\.venv-build-313-spike\Scripts\python.exe deploy\build.py
```

**Resultados verificados no spike de 2026-08-20:**
- ✅ **Wheels C**: TODAS têm build cp313 (pyodbc 5.3.0, pywin32 312, numpy 2.4.6,
  pandas 3.0.5, cryptography 50.0.0 cp311-abi3, pydantic-core, pyarmor-cli-core 8.1.1).
  Risco de imaturidade de wheels: **descartado**.
- ✅ **PyArmor BCC compila em 3.13.15**: probe direto deu "generate bcc code
  successfully"; build completo protegeu 211 ficheiros (BCC + denylist) sem erro.
  **Este era o maior risco — está resolvido.**
- ✅ **build.py completou (2026-08-21)**: `BUILD COMPLETE` — PyArmor output 396 files
  /39.4 MB, PyInstaller bundle 1312 files/142.0 MB, `dist\watcherdb\watcherdb.exe`,
  secret scan limpo. Os "ERROR: Hidden import not found" do PyInstaller são ruído
  benigno (nomes ao nível de atributo do AST scan + deps opcionais não instaladas);
  o build passa por cima deles — acontece igual no 3.11.
- ✅ **Re-scan CVE do bundle 3.13 (2026-08-21, `grype dir:dist\watcherdb`)**: das 3
  Critical passou a **0 Critical**; High de 55 → **5**. Python detetado 3.13.15, SQLite
  3.50.4.0 — as 29 CVEs antigas (3.11.9 + 3.45.1) DESAPARECERAM. **Tese provada
  end-to-end no venv descartável.**
  - Resíduo a tratar na Fase 1 (nenhuma Critical): 3× starlette 0.50.0 (teto <0.51, já
    parte allowlisted — juntar GHSA-86qp / GHSA-x746 / GHSA-jp82); 3× SQLite 3.50.4
    High (CVE-2025-70873, CVE-2026-11822, CVE-2026-11824 — fix em SQLite 3.51+/3.53,
    acima do 3.13.15; baixa explorab., store é SQL Server); 3× Python 3.13.15
    (CVE-2025-15367, CVE-2024-3220, CVE-2026-4360 — Medium/Low, uma sem fix).
  - **AÇÃO Fase 1 na allowlist**: REMOVER as 29 entradas antigas (deixam de aplicar) e
    ADICIONAR estes resíduos com razão. Só depois do rebuild real gerar o grype report.
- ⏳ **Único pendente do spike**: smoke-boot do `watcherdb.exe` (arranca e serve /healthz
  em TLS?). Opcional aqui; a Fase 1 real corre-o via build_release.ps1.

### PRÉ-REQUISITOS descobertos no spike (obrigatórios no rebuild real)

1. **`setuptools` deixa de vir de fábrica no venv 3.12+**. O lock está em modo hash e o
   pyinstaller puxa `setuptools>=42` sem pin → `--require-hashes` aborta o install
   inteiro. Em 3.11 passava porque o venv trazia setuptools. **Fix no rebuild real:
   pinar `setuptools==<versão>` COM hash na regeneração do lock.** (No spike resolveu-se
   com `pip install setuptools` antes do lock.)
2. **`clang.exe` (BCC) tem de estar no PATH**. O BCC compila para C via clang
   (`C:\Program Files\LLVM\bin`, v22.1.5 na máquina). O `build_release.ps1` já faz o
   prepend; o `build.py` a solo NÃO — daí o `[WinError 2] cannot find clang.exe` no
   primeiro spike. No rebuild via `build_release.ps1` está coberto.

Limpar o spike no fim: `Remove-Item -Recurse -Force .venv-build-313-spike`

---

## FASE 1 — REBUILD REAL (só depois do spike verde)

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"

# 1. BACKUP do venv actual (rollback trivial)
Rename-Item .venv-build .venv-build-311-bak

# 2. novo venv sobre 3.13.15
py -3.13 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install --upgrade pip

# 3. instalar A PARTIR DO LOCK (não resolução livre — o lock é a rede de segurança
#    contra reabrir o incidente do portal 500 de 11/08: fastapi 0.136->starlette 1.0)
.\.venv-build\Scripts\python.exe -m pip install -r requirements-build.lock

# 4. REGENERAR o lock sobre 3.13 (respeitar TODOS os tetos de requirements.txt:
#    fastapi<0.130, starlette<0.51, uvicorn<0.41, bcrypt<4.1)
#    + resolver o drift do sqlparse (lock tem 0.5.5, requirements.txt pede >=0.6.0)
#    Comparar item a item, NÃO aceitar cegamente.
```

### Validação obrigatória (por ordem; parar ao primeiro vermelho)

1. **pytest gate** — re-baseline: podem surgir falhas NOVAS de 3.13 (dict ordering,
   deprecations viradas erro). Reavaliar `KnownBaselineFailures`, não assumir os 5 conhecidos.
2. **smoke-boot** (PASSO 3.5 do `build_release.ps1`) — apanhou os 4 incidentes históricos
   de import do bundle; é o que apanha qualquer `ImportError` novo do bundle 3.13.
3. **pipeline completo** com assinatura + CVE gate — só com 1 e 2 verdes.
4. **CVE gate**: as 29 CVEs Python/SQLite devem **DESAPARECER** do relatório grype.
   Qualquer que sobreviva é falha da migração, não CVE nova. Depois, **remover** essas 29
   entradas da `cve_allowlist.json` (deixam de ser aplicáveis).

### Pontos de falha (ordem de probabilidade)
1. PyArmor BCC codegen num módulo novo (já mitigado por `BCC_DENYLIST`, mas imprevisível).
2. `pip install` de dep C sem wheel p/ a minor exacta.
3. `deploy/watcherdb.spec` AST scan (~L138-140) — hiddenimports dependentes de stdlib.
4. Baseline de testes precisa de re-baseline sob 3.13.

**Rollback:** `Remove-Item -Recurse -Force .venv-build; Rename-Item .venv-build-311-bak .venv-build`

---

## Follow-ups independentes deste rebuild
- **Drift do lock**: `requirements.txt` pede `sqlparse>=0.6.0` (bump de hoje) mas
  `requirements-build.lock` ainda tem `0.5.5`. Resolver na regeneração do lock (passo 4).
- **ecdsa (GHSA-wj6h)**: sem fix; caminho é migrar `python-jose`→`joserfc` (TODO no requirements).
- **starlette (GHSA-82w8/wqp7)**: fix acima do teto `<0.51`; caminho é resolver o shim
  `TemplateResponse` antes de subir o teto.
