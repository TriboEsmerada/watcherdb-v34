# Self-Hosted Windows Runner Setup — WatcherDB V3.3 Build Pipeline

## Purpose

GitHub Actions workflow `.github/workflows/build-release.yml` requires a
self-hosted Windows runner because:

- **PyArmor Pro licence** is machine-bound (cannot activate on github-hosted)
- **DigiCert KeyLocker EV signing** uses local client certificate
- **Determinism** — same machine produces reproducible MSI artefacts

## Runner labels

```
[self-hosted, windows, watcherdb-build]
```

## Hardware minimum

- Windows Server 2019/2022 OR Windows 11 (x64)
- 16 GB RAM (PyInstaller analysis is memory-heavy)
- 50 GB free disk (build artefacts + tools + venv + cache)
- Stable network (PyArmor licence validates online during build)

---

## Pre-install software

### 1. Python 3.11

Download python-3.11.x amd64 installer from <https://www.python.org/downloads/release/>

Install com flags:
- "Add python.exe to PATH" ✓
- "Install for all users" ✓ (path under `C:\Python311` ou similar)

Verify:
```powershell
py -3.11 --version
```

### 2. PyArmor Pro reg 011618

PyArmor Pro licence é **machine-bound**.

1. Copy registration file `pyarmor-regfile-011618.zip` to runner (out-of-band, NOT git)
2. Install pyarmor:
   ```powershell
   py -3.11 -m pip install pyarmor==9.2.4
   ```
3. Activate licence:
   ```powershell
   py -3.11 -m pyarmor.cli reg pyarmor-regfile-011618.zip
   ```
4. Verify Pro + BCC + RFT activated:
   ```powershell
   py -3.11 -m pyarmor.cli --version
   # Expected output:
   #   Pyarmor 9.2.4 (pro), 011618, WatcherDB
   #   BCC Mode: Yes / RFT Mode: Yes
   ```

### 3. LLVM/Clang (required by PyArmor BCC)

```powershell
winget install LLVM.LLVM
```

Adicionar ao PATH manualmente (winget não auto-adds):
- Path: `C:\Program Files\LLVM\bin`
- System Properties → Environment Variables → Path → Add

Verify:
```powershell
clang.exe --version
```

### 4. WiX Toolset v3.14

```powershell
# REQUER ADMIN
winget install WiXToolset.WiXToolset
```

Pode pedir activar .NET Framework 3.5 (NetFx3). Aceitar.

Adicionar ao PATH:
- Path: `C:\Program Files (x86)\WiX Toolset v3.14\bin`

Verify:
```powershell
candle.exe -? | Select-String -Pattern "version" | Select-Object -First 1
light.exe -? | Select-String -Pattern "version" | Select-Object -First 1
heat.exe -? | Select-String -Pattern "version" | Select-Object -First 1
```

### 5. Syft (SBOM generator)

```powershell
winget install --id Anchore.Syft --scope user
```

Verify:
```powershell
syft version
```

### 6. signtool.exe (Windows SDK Code Signing Tools)

Install via Visual Studio Build Tools 2022 + "Windows 11 SDK" component
OR download Windows SDK Signing Tools standalone:
<https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool>

Verify:
```powershell
signtool.exe /? | Select-String -Pattern "version" | Select-Object -First 1
```

### 7. DigiCert KeyLocker Client Tools

Download `smctl` from DigiCert documentation:
<https://docs.digicert.com/en/digicert-keylocker.html>

Configure environment variables (or use GitHub Actions secrets injection — preferred):
- `SM_HOST` — e.g. `https://clientauth.one.digicert.com`
- `SM_API_KEY` — from DigiCert console
- `SM_CLIENT_CERT_FILE` — absolute path to client.p12 on runner
- `SM_CLIENT_CERT_PASSWORD` — p12 password
- `SM_CERT_ALIAS` — alias from console

### 8. Python venv for build (`.venv-build`)

After cloning repo to runner workspace, setup venv:

```powershell
cd <workspace>\WATCHERDB_V3.3
py -3.11 -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install --upgrade pip
.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
```

Verify:
```powershell
.venv-build\Scripts\python.exe -m pyarmor.cli --version
.venv-build\Scripts\python.exe -m PyInstaller --version
```

---

## GitHub Actions runner registration

1. GitHub repo → **Settings → Actions → Runners → New self-hosted runner**
2. Choose **Windows + x64**
3. Follow GitHub instructions to download, configure, install as Windows Service
4. **Add labels** durante `./config.cmd` setup, quando perguntado "additional labels":
   ```
   watcherdb-build
   ```
   (label `self-hosted` e `windows` são auto-added)

Verify no GitHub Actions tab: runner aparece como `Idle` com labels `[self-hosted, windows, watcherdb-build]`.

---

## GitHub repository secrets

Settings → Secrets and variables → Actions → New repository secret:

| Secret name | Value source |
|---|---|
| `SM_HOST` | DigiCert KeyLocker URL |
| `SM_API_KEY` | from DigiCert console |
| `SM_CLIENT_CERT_FILE` | absolute path on runner to `client.p12` |
| `SM_CLIENT_CERT_PASSWORD` | p12 password |
| `SM_CERT_ALIAS` | alias from DigiCert console |

---

## Test pipeline (smoke run)

Antes da primeira tag de release, run manual para validar toolchain:

1. GitHub → Actions tab → **Build Release MSI** workflow
2. **Run workflow** → Branch: `feat/v3.3-ci-build-release` (ou `main` após merge)
3. Inputs:
   - `skip_signing`: `true` (primeiro run sem DigiCert, só validate)
   - `skip_sbom`: `false` (test SBOM generation)
4. Watch logs

Esperado primeiro run com sucesso:
- Toolchain check OK (clang, candle, light, heat, syft, signtool)
- PyArmor licence verified (Pro + BCC + RFT)
- Build E2E (~15 min) → `dist/watcherdb/watcherdb.exe`
- 100% IP protection assert (218/218 obfuscated)
- MSI built (~3 min) → `dist/msi/WatcherDB_V3.3_Standard.msi`
- SBOM generated (~1 min) → CycloneDX JSON
- Artefactos uploaded (retention 90d)

Após primeiro run sem signing, configurar DigiCert secrets e re-run com `skip_signing: false`.

---

## Tag-triggered production release

Quando tudo funciona, release real:

```powershell
git tag -a v3.3.9 -m "release: V3.3 Standard Edition 3.3.9.0"
git push origin v3.3.9
```

Workflow auto-triggers em tag push → MSI signed + SBOM + checksums + draft GitHub Release com artefactos attached.

---

## Troubleshooting

| Sintoma | Causa provável | Resolução |
|---|---|---|
| `PyArmor not Pro` | regfile não activated no runner | Run `pyarmor.cli reg <regfile>.zip` |
| `clang.exe not found` | LLVM PATH não actualizado | Add `C:\Program Files\LLVM\bin` ao PATH |
| `candle.exe not found` | WiX install requer NetFx3 | Install .NET Framework 3.5 feature (admin) |
| `signtool failed exit 1` | DigiCert secrets ausentes/wrong | Verify GitHub secrets + smctl config |
| `PyArmor BCC error` | clang missing OR Python file f-string com backslash | Run `clang --version`; fix f-string per Python 3.11 PEP 701 (extrai expression para var) |
| `MSI signature Invalid` | DigiCert cert expired ou wrong alias | Check DigiCert console, regenerate `client.p12` |
| `Pack size error em push` | gguf/exe legacy reintroduzido | Re-check `.gitignore` (existe regra `*.gguf`?) |

---

## Maintenance schedule

- **PyArmor licence:** check expiry quarterly via `pyarmor.cli --version`
- **Tool updates:** quarterly `winget upgrade --all` em janela de manutenção
- **Disk cleanup:** `_work/_temp/` do runner accumulates — clean monthly
- **Logs:** GitHub Actions runner logs em `<runner>\_diag\`
- **Backup `.venv-build/`:** snapshot antes de major Python/PyInstaller upgrade

---

## References

- PyArmor: <https://pyarmor.readthedocs.io>
- WiX v3: <https://wixtoolset.org>
- Syft: <https://github.com/anchore/syft>
- DigiCert KeyLocker: <https://docs.digicert.com/en/digicert-keylocker.html>
- GitHub self-hosted runners: <https://docs.github.com/actions/hosting-your-own-runners>
- Audits referenced: 2026-05-12 packaging-architect + deploy-architect + security-auditor + qa-specialist
