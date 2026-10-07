# -*- coding: utf-8 -*-
"""Lote E do instalador: install.ps1 orquestra os subcomandos; configure escreve o .env explicito (2026-10-07).

Ficheiros do lote em docs/context/lotes/INSTALADOR_ORQUESTRACAO_2026-10-07/:
  watcherdb/install/envfile.py   .env com chaves explicitas, merge idempotente, JWT so' se faltar, passwords cifradas.
  watcherdb/install/cli.py       + configure; setup-database --create-login (password por variavel transitoria
                                 WATCHERDB_LOGIN_PASSWORD, parametrizada no CREATE LOGIN).
  tests/unit/test_instalador_orquestracao_20261007.py
Edicoes:
  watcherdb/install/dbsetup.py   executar(login_password=...) cria o login no servidor da base se faltar.
  deploy/install.ps1             -Database, -SqlLogin, -SqlLoginPassword, -InventoryPath, -ProvisionMode Auto|Manual|Skip,
                                 -SkipDatabaseSetup, -DryRun; PASSOS f1 inventario -> f2 base/schema -> f3 login na frota
                                 -> f4 .env + ACL (condicao 4) antes da licenca; k2 preflight-fleet antes do HKLM (so'
                                 falha em Auto); preflight recebe porta/servico/login do SOT; textos V3.3 fora.
  deploy/preflight_target.ps1    -WebPort/-ServiceName/-SqlLogin; fases 5/7/9 sem 8433, V33 e sql_monitoring fixos.
  deploy/setup_database.ps1      textos V3.3/V33 (wrapper do vendor; o cliente usa o subcomando).
  watcherdb_service.py           dispatcher ganha configure.

Identidade dos passos f2/f3: a sessao Windows de quem corre o instalador (DBA), so' ai, nunca persistida.

Uso: py docs/context/INSTALADOR_ORQUESTRACAO_2026-10-07_apply.py --check | --preview | --repo <copia> | (aplica)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOTE = Path(__file__).resolve().parent / "lotes" / "INSTALADOR_ORQUESTRACAO_2026-10-07"
NOVOS = [Path("watcherdb/install/envfile.py"), Path("tests/unit/test_instalador_orquestracao_20261007.py")]
SUBSTITUIDOS = [Path("watcherdb/install/cli.py")]
DBS = Path("watcherdb/install/dbsetup.py")
INST = Path("deploy/install.ps1")
PRE = Path("deploy/preflight_target.ps1")
SDB = Path("deploy/setup_database.ps1")
SVC = Path("watcherdb_service.py")

# ------------------------------------------------------------------ dbsetup.py
DBS_EDITS = [
    ("    login_existe: Optional[bool] = None\n",
     "    login_existe: Optional[bool] = None\n    login_criado: bool = False\n"),
    ("    relatorio_path: Optional[Path] = None,\n) -> Relatorio:\n",
     "    relatorio_path: Optional[Path] = None,\n    login_password: Optional[str] = None,\n) -> Relatorio:\n"),
    ('            cur.execute("SELECT 1 FROM sys.server_principals WHERE name = ?", login)\n'
     '            rel.login_existe = cur.fetchone() is not None\n',
     '            cur.execute("SELECT 1 FROM sys.server_principals WHERE name = ?", login)\n'
     '            rel.login_existe = cur.fetchone() is not None\n'
     '            if not rel.login_existe and login_password:\n'
     '                # lote E: o instalador cria o login do produto no servidor da base (password parametrizada,\n'
     '                # nunca concatenada nem registada; CHECK_EXPIRATION OFF = login de servico, rotacao por comando)\n'
     '                cur.execute(\n'
     '                    f"DECLARE @s NVARCHAR(MAX) = N\'CREATE LOGIN [{login}] WITH PASSWORD = N\'\'\' + REPLACE(?, \'\'\'\', \'\'\'\'\'\') "\n'
     '                    f"+ N\'\'\', CHECK_POLICY = ON, CHECK_EXPIRATION = OFF, DEFAULT_DATABASE = master;\'; EXEC sp_executesql @s;",\n'
     '                    login_password,\n'
     '                )\n'
     '                cur.execute("SELECT 1 FROM sys.server_principals WHERE name = ?", login)\n'
     '                rel.login_existe = cur.fetchone() is not None\n'
     '                rel.login_criado = rel.login_existe\n'
     '                log(f"  login [{login}] {\'criado\' if rel.login_criado else \'NAO criado\'} em {servidor}")\n'),
]

# ------------------------------------------------------------------ install.ps1
INST_EDITS = [
    ("    Instalador WatcherDB V3.3 Standard Edition (Etapa 3a - veiculo ZIP).\n",
     "    Instalador WatcherDB V3.4 Standard Edition (veiculo ZIP; orquestra os subcomandos do watcherdb.exe).\n"),
    ("    (normalmente C:\\Program Files\\WatcherDB\\V3.3).\n",
     "    (normalmente C:\\Program Files\\WatcherDB\\V3.4).\n"),
    ("    para validar conectividade + login sql_monitoring. Default 'localhost'.\n",
     "    para validar conectividade + login do produto (-SqlLogin). Default 'localhost'.\n"),
    ("    Passa -SkipSqlCheck ao preflight_target.ps1 (sql_monitoring ainda nao\n",
     "    Passa -SkipSqlCheck ao preflight_target.ps1 (login do produto ainda nao\n"),
    ("    [string]$SqlServer = 'localhost',\n    [switch]$SkipSqlCheck,\n\n    [int]$HealthTimeoutSeconds = 120\n)\n",
     "    [string]$SqlServer = 'localhost',\n    [switch]$SkipSqlCheck,\n\n"
     "    # 2026-10-07 (lote E): base, login e frota configuraveis; o utilizador preenche, o instalador orquestra.\n"
     "    [string]$Database = 'WatcherDB',\n"
     "    [string]$SqlLogin = 'watcherdb',\n"
     "    [SecureString]$SqlLoginPassword,\n"
     "    [string]$InventoryPath = '',\n"
     "    [ValidateSet('Auto','Manual','Skip')]\n"
     "    [string]$ProvisionMode = 'Manual',\n"
     "    [switch]$SkipDatabaseSetup,\n"
     "    [switch]$DryRun,\n"
     "    [int]$HealthTimeoutSeconds = 120\n)\n"),
    ("Write-Host '  WatcherDB V3.3 Standard - Instalacao (Etapa 3a: ZIP)' -ForegroundColor Cyan\n",
     "Write-Host '  WatcherDB Standard - Instalacao (ZIP)' -ForegroundColor Cyan\n"),
    ('Write-Host "  Silent:          $Silent"\n',
     'Write-Host "  Silent:          $Silent"\n'
     'Write-Host "  Base/Login:      $Database / $SqlLogin em $SqlServer"\n'
     'Write-Host "  Inventario:      $(if ($InventoryPath) { $InventoryPath } else { \'(sem -InventoryPath: usa servers.json existente)\' })"\n'
     'Write-Host "  ProvisionMode:   $ProvisionMode$(if ($DryRun) { \'  [DRY-RUN]\' })"\n'),
    ("    $preflightArgs = @{ SqlServer = $SqlServer }\n",
     "    $preflightArgs = @{ SqlServer = $SqlServer; WebPort = $WebPort; ServiceName = $ServiceName; SqlLogin = $SqlLogin }\n"),
    ("# =============================================================================\n# PASSO (g) - Licenca\n",
     r'''# =============================================================================
# PASSOS (f1..f4) - Inventario, base e schema, login na frota, .env  (lote E, 2026-10-07)
# Subcomandos do watcherdb.exe (watcherdb/install): a logica vive em Python porque a cifra Fernet, o pyodbc e o
# driver ODBC ja' estao no bundle; o servidor alvo nao tem Python nem sqlcmd garantido. Identidade de f2/f3: a
# sessao Windows de quem corre este instalador (DBA), so' aqui, nunca persistida (decisao do owner 2026-10-07).
# -DryRun: f1 so' escreve ficheiros de inventario, f2/f3 mostram o plano sem executar, f4 mostra o .env; o
# instalador termina antes da licenca.
# =============================================================================
$wdbExe = Join-Path $InstallDir 'watcherdb.exe'
$cfgDir = Join-Path $DataDir 'config'
$serversJson = Join-Path $cfgDir 'servers.json'
$sqlParts = $SqlServer -split '\\', 2
$sqlHost = $sqlParts[0]
$sqlInst = if ($sqlParts.Count -gt 1 -and $sqlParts[1]) { $sqlParts[1] } else { 'MSSQLSERVER' }
$loginPwdPlain = $null
if ($SqlLoginPassword) {
    $bstrL = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SqlLoginPassword)
    $loginPwdPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstrL)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstrL) | Out-Null
}
function Invoke-WdbSub([string[]]$argv) {
    & $wdbExe @argv
    return $LASTEXITCODE
}

Write-Step 'PASSO (f1): inventario da frota (servers.json + scripts de grants por instancia)'
if ($InventoryPath) {
    if (-not (Test-Path $InventoryPath)) { Write-Fail "InventoryPath '$InventoryPath' nao existe."; exit 7 }
    $rc = Invoke-WdbSub @('inventory', '--input', $InventoryPath, '--output-dir', $cfgDir, '--database', $Database, '--login', $SqlLogin, '--master-host', $sqlHost, '--master-instance', $sqlInst)
    if ($rc -ne 0) { Write-Fail "inventory falhou (exit $rc). Corrigir o inventario e repetir."; exit 7 }
    Write-Ok "Inventario processado -> $serversJson (scripts de grants em $cfgDir\grants)."
} elseif (Test-Path $serversJson) {
    Write-Ok "Sem -InventoryPath: a usar o servers.json existente em $cfgDir."
} else {
    Write-Warn "Sem -InventoryPath e sem ${serversJson}: a frota fica vazia ate' correres 'watcherdb.exe inventory'."
}
Write-Host ''

Write-Step "PASSO (f2): base [$Database] e schema em $SqlServer (identidade: a tua sessao Windows, so' neste passo)"
if ($SkipDatabaseSetup) {
    Write-Warn "-SkipDatabaseSetup: base e schema NAO tocados (instalacao a apontar a uma base ja' existente)."
} else {
    $sdArgs = @('setup-database', '--server', $SqlServer, '--database', $Database, '--login', $SqlLogin)
    if ($loginPwdPlain) { $sdArgs += '--create-login' }
    if (-not $DryRun) { $sdArgs += '--execute' }
    try {
        if ($loginPwdPlain) { $env:WATCHERDB_LOGIN_PASSWORD = $loginPwdPlain }
        $rc = Invoke-WdbSub $sdArgs
    } finally {
        Remove-Item Env:WATCHERDB_LOGIN_PASSWORD -ErrorAction SilentlyContinue
    }
    if ($rc -ne 0) { Write-Fail "setup-database falhou (exit $rc). Ver o relatorio em $DataDir\logs."; exit 7 }
    Write-Ok "Base e schema $(if ($DryRun) { 'planeados (dry-run)' } else { 'aplicados' })."
}
Write-Host ''

Write-Step "PASSO (f3): login [$SqlLogin] na frota (ProvisionMode=$ProvisionMode)"
switch ($ProvisionMode) {
    'Skip'   { Write-Warn "ProvisionMode=Skip: o login na frota NAO e' tocado (frota ja' provisionada ou a fazer depois)." }
    'Manual' {
        if (Test-Path $serversJson) {
            $rc = Invoke-WdbSub @('provision-login', '--inventory', $serversJson, '--login', $SqlLogin, '--mode', 'manual')
            if ($rc -ne 0) { Write-Fail "provision-login falhou (exit $rc)."; exit 7 }
        } else { Write-Warn 'Sem servers.json: nada a provisionar.' }
    }
    'Auto'   {
        if (-not (Test-Path $serversJson)) { Write-Fail 'ProvisionMode=Auto exige servers.json (usa -InventoryPath).'; exit 7 }
        $n = @((Get-Content $serversJson -Raw | ConvertFrom-Json).monitored_servers | Where-Object { -not $_.use_windows_auth -and $_.enabled }).Count
        Write-Warn "ProvisionMode=Auto (opt-in): o instalador vai CRIAR o login em $n instancias com a tua identidade DBA."
        $plArgs = @('provision-login', '--inventory', $serversJson, '--login', $SqlLogin, '--mode', 'auto')
        if (-not $DryRun) { $plArgs += @('--execute', '--confirm-count', "$n") }
        $rc = Invoke-WdbSub $plArgs
        if ($rc -ne 0) { Write-Fail "provision-login falhou (exit $rc). Relatorio em $DataDir\logs; rollback: watcherdb.exe provision-rollback --report <ficheiro>."; exit 7 }
    }
}
Write-Host ''

Write-Step 'PASSO (f4): .env do produto (chaves explicitas; password cifrada com a master key) e ACL'
$cfArgs = @('configure', '--data-dir', $DataDir, '--server', $SqlServer, '--database', $Database, '--login', $SqlLogin, '--port', "$WebPort")
if ($DryRun) { $cfArgs += '--preview' }
try {
    if ($loginPwdPlain) { $env:WATCHERDB_LOGIN_PASSWORD = $loginPwdPlain }
    $rc = Invoke-WdbSub $cfArgs
} finally {
    Remove-Item Env:WATCHERDB_LOGIN_PASSWORD -ErrorAction SilentlyContinue
    $loginPwdPlain = $null
}
if ($rc -ne 0) { Write-Fail "configure falhou (exit $rc)."; exit 7 }
if (-not $DryRun) {
    # condicao 4 do parecer de seguranca (2026-10-07): .env e config\ sem leitura para Users/Everyone
    foreach ($p in @((Join-Path $DataDir '.env'), $cfgDir)) {
        if (Test-Path $p) {
            $acl = Get-Acl $p
            $aberto = $acl.Access | Where-Object { $_.IdentityReference -match 'BUILTIN\\Users|\\Users$|Utilizadores|Everyone|Todos' }
            if ($aberto) { Write-Fail "ACL de $p da acesso a Users/Everyone -- corrigir (icacls) antes de continuar."; exit 7 }
        }
    }
    Write-Ok '.env escrito e ACL verificada (sem Users/Everyone).'
}
if ($DryRun) {
    Write-Host ''
    Write-Ok '-DryRun: plano concluido. Nada foi executado na base nem na frota; licenca, servico e firewall ficam por fazer.'
    exit 0
}
Write-Host ''

# =============================================================================
# PASSO (g) - Licenca
'''),
    ("# =============================================================================\n# PASSO (l) - Registo HKLM (paridade Product.wxs InstalledVersion + tracking\n",
     r'''# =============================================================================
# PASSO (k2) - preflight-fleet (lote E): liga com o login do produto a cada instancia, valida grants e escreve
# o sql_auth_rollout.json so' com quem passou. Em Manual o DBA ainda pode nao ter corrido os scripts: avisa.
# =============================================================================
Write-Step "PASSO (k2): preflight-fleet (login [$SqlLogin] contra a frota)"
if ($ProvisionMode -eq 'Skip' -or -not (Test-Path $serversJson)) {
    Write-Warn "preflight-fleet saltado (ProvisionMode=Skip ou sem servers.json). Correr depois: watcherdb.exe preflight-fleet --login $SqlLogin"
} else {
    & $wdbExe preflight-fleet --inventory $serversJson --login $SqlLogin
    $rcPf = $LASTEXITCODE
    if ($rcPf -eq 0) {
        Write-Ok 'preflight-fleet: todas as instancias passaram; sql_auth_rollout.json escrito.'
    } elseif ($ProvisionMode -eq 'Auto' -and $rcPf -eq 1) {
        Write-Fail 'preflight-fleet: login sysadmin ou com permissoes a mais numa instancia, ou nenhuma passou. Corrigir antes de usar o produto.'
        exit 8
    } else {
        Write-Warn "preflight-fleet: exit $rcPf -- so' as instancias que passaram entram no sql_auth_rollout.json. Em Manual: correr os scripts de grants e repetir 'watcherdb.exe preflight-fleet --login $SqlLogin'."
    }
}
Write-Host ''

# =============================================================================
# PASSO (l) - Registo HKLM (paridade Product.wxs InstalledVersion + tracking
'''),
    ("Write-Host '  INSTALACAO CONCLUIDA - WatcherDB V3.3 Standard Edition' -ForegroundColor Cyan\n",
     'Write-Host "  INSTALACAO CONCLUIDA - $($rv.ProductName)" -ForegroundColor Cyan\n'),
    ('Write-Host "  Porta:           $WebPort - http://localhost:$WebPort"\n',
     'Write-Host "  Porta:           $WebPort - http://localhost:$WebPort"\n'
     'Write-Host "  Base/Login:      $Database / $SqlLogin em $SqlServer (ProvisionMode=$ProvisionMode)"\n'),
]

# ------------------------------------------------------------------ preflight_target.ps1
PRE_EDITS = [
    ("    Preflight check no target machine antes de install WatcherDB V3.3 MSI.\n",
     "    Preflight check no target machine antes de instalar o WatcherDB V3.4 (ZIP + install.ps1).\n"),
    ("    Valida pre-requisitos antes de correr msiexec. Falha graciosa com fix hints.\n",
     "    Valida pre-requisitos antes de correr install.ps1. Falha graciosa com fix hints.\n"),
    ("      1. Admin rights (msiexec exige)\n", "      1. Admin rights (install.ps1 exige)\n"),
    ("      5. Login sql_monitoring exists + tem VIEW SERVER STATE (param: -SqlServer)\n",
     "      5. Login do produto existe (informativo; params: -SqlServer, -SqlLogin)\n"),
    ("      7. Porta 8433 livre\n", "      7. Porta do produto livre (param: -WebPort)\n"),
    ("      9. Service WatcherDBWebServiceV33 nao pre-existing (clean install)\n",
     "      9. Servico do produto nao pre-existente (param: -ServiceName)\n"),
    ("    REGRA OURO #2: usar identidade sql_monitoring nas queries.\n",
     "    REGRA OURO #2: o produto so' liga com o seu login SQL (-SqlLogin), nunca Trusted_Connection.\n"),
    ("    Skip Phases 4-5 (SQL connectivity) se sql_monitoring ainda nao foi criado.\n",
     "    Skip Phases 4-5 (SQL connectivity) se o login do produto ainda nao foi criado.\n"),
    ("    # SQL Server skip (sql_monitoring nao criado ainda):\n", "    # SQL Server skip (login do produto nao criado ainda):\n"),
    ('Write-Host "  WatcherDB V3.3 - Target Machine Preflight" -ForegroundColor Cyan\n',
     'Write-Host "  WatcherDB - Target Machine Preflight" -ForegroundColor Cyan\n'),
    ('    Write-Host "[RESULT] PREFLIGHT FAILED - fix above before msiexec /i" -ForegroundColor Red\n',
     '    Write-Host "[RESULT] PREFLIGHT FAILED - fix above before install.ps1" -ForegroundColor Red\n'),
    ('Write-Host "[RESULT] PREFLIGHT PASSED - target ready for msiexec /i" -ForegroundColor Green\n',
     'Write-Host "[RESULT] PREFLIGHT PASSED - target ready for install.ps1" -ForegroundColor Green\n'),
    ("param(\n    [Parameter(Mandatory=$true)]\n    [string]$SqlServer,\n    [string]$ServiceAccount = '',\n    [switch]$SkipSqlCheck\n)\n",
     "param(\n    [Parameter(Mandatory=$true)]\n    [string]$SqlServer,\n    [string]$ServiceAccount = '',\n    [switch]$SkipSqlCheck,\n"
     "    # 2026-10-07 (lote E): vem do release_vars via install.ps1; sem valores fixos de versao.\n"
     "    [int]$WebPort = 8434,\n    [string]$ServiceName = 'WatcherDBWebServiceV34',\n    [string]$SqlLogin = 'watcherdb'\n)\n"),
    ("# === Phase 5: sql_monitoring login + permissions =======================\n"
     "Write-Host \"\"\n"
     "Write-Host \"--- Phase 5: sql_monitoring login + VIEW SERVER STATE ---\" -ForegroundColor Cyan\n",
     "# === Phase 5: login do produto (informativo: o instalador pode cria-lo em f2/f3) ===\n"
     "Write-Host \"\"\n"
     "Write-Host \"--- Phase 5: login '$SqlLogin' (informativo) ---\" -ForegroundColor Cyan\n"),
    ("            # Query VIA sql_monitoring se possivel — se nao tiver password aqui, skip\n"
     "            $query = \"SELECT name FROM sys.server_principals WHERE name = 'sql_monitoring'\"\n"
     "            $output = & sqlcmd -S $SqlServer -E -Q $query -h-1 -W -b 2>&1\n"
     "            $loginExists = $output -match 'sql_monitoring'\n"
     "            Test-Check $loginExists \"Login 'sql_monitoring' exists on $SqlServer\" 'fail' \"DBA: CREATE LOGIN sql_monitoring; GRANT VIEW SERVER STATE TO sql_monitoring; (Regra Ouro #2: identidade DBA confirmada)\"\n",
     "            # So' informativo: o login pode ainda nao existir (o instalador cria-o com -SqlLoginPassword / provision-login).\n"
     "            $query = \"SELECT name FROM sys.server_principals WHERE name = '$($SqlLogin -replace \"'\", \"''\")'\"\n"
     "            $output = & sqlcmd -S $SqlServer -E -Q $query -h-1 -W -b 2>&1\n"
     "            $loginExists = $output -match [regex]::Escape($SqlLogin)\n"
     "            Test-Check $loginExists \"Login '$SqlLogin' exists on $SqlServer\" 'warn' \"Sera' criado pelo instalador (-SqlLoginPassword) ou pelo DBA com os scripts de grants\"\n"),
    ("        Test-Check $false \"sql_monitoring login check (got exception: $($_.Exception.Message))\" 'warn'\n",
     "        Test-Check $false \"login '$SqlLogin' check (got exception: $($_.Exception.Message))\" 'warn'\n"),
    ("# === Phase 7: Porta 8433 livre ==========================================\n"
     "Write-Host \"\"\n"
     "Write-Host \"--- Phase 7: Port 8433 available ---\" -ForegroundColor Cyan\n"
     "$portInUse = (Get-NetTCPConnection -LocalPort 8433 -ErrorAction SilentlyContinue) | Select-Object -First 1\n"
     "Test-Check ($null -eq $portInUse) \"Port 8433 is free\" 'fail' \"Process using 8433: $(if($portInUse){\"PID $($portInUse.OwningProcess)\"})\"\n",
     "# === Phase 7: Porta do produto livre ====================================\n"
     "Write-Host \"\"\n"
     "Write-Host \"--- Phase 7: Port $WebPort available ---\" -ForegroundColor Cyan\n"
     "$portInUse = (Get-NetTCPConnection -LocalPort $WebPort -ErrorAction SilentlyContinue) | Select-Object -First 1\n"
     "Test-Check ($null -eq $portInUse) \"Port $WebPort is free\" 'fail' \"Process using ${WebPort}: $(if($portInUse){\"PID $($portInUse.OwningProcess)\"})\"\n"),
    ("$preSvc = Get-Service WatcherDBWebServiceV33 -ErrorAction SilentlyContinue\n"
     "Test-Check ($null -eq $preSvc) \"WatcherDBWebServiceV33 not pre-existing\" 'warn' \"Uninstall previous install first: msiexec /x <msi> /qn\"\n",
     "$preSvc = Get-Service $ServiceName -ErrorAction SilentlyContinue\n"
     "Test-Check ($null -eq $preSvc) \"$ServiceName not pre-existing\" 'warn' \"Servico ja' existe: o install.ps1 faz upgrade (sc.exe config); para instalacao limpa correr uninstall.ps1 primeiro\"\n"),
]

# ------------------------------------------------------------------ setup_database.ps1 (CRLF)
SDB_EDITS = [
    ("# WatcherDB V3.3 \u2014 Setup da Base de Dados\n",
     "# WatcherDB V3.4 \u2014 Setup da Base de Dados (wrapper do vendor; no cliente: watcherdb.exe setup-database)\n"),
    ('Write-Host "  WatcherDB V3.3 \u2014 Setup da Base de Dados" -ForegroundColor Cyan\n',
     'Write-Host "  WatcherDB V3.4 \u2014 Setup da Base de Dados (wrapper do vendor; o cliente usa: watcherdb.exe setup-database)" -ForegroundColor Cyan\n'),
    ('Write-Host "  3. Reiniciar servico: net stop/start WatcherDBWebServiceV33" -ForegroundColor White\n',
     'Write-Host "  3. Reiniciar servico: Restart-Service WatcherDBWebServiceV34" -ForegroundColor White\n'),
]

SVC_OLD = ('    if sys.argv[1].lower() in ("setup-database", "inventory", "inventory-template", "provision-login", "provision-rollback", "preflight-fleet",\n'
           '                               "bootstrap-admin", "install-help"):\n')
SVC_NEW = ('    if sys.argv[1].lower() in ("setup-database", "inventory", "inventory-template", "provision-login", "provision-rollback", "preflight-fleet",\n'
           '                               "configure", "bootstrap-admin", "install-help"):\n')

EDITS = [(DBS, v, n) for v, n in DBS_EDITS] + [(INST, v, n) for v, n in INST_EDITS] + [(PRE, v, n) for v, n in PRE_EDITS] \
        + [(SDB, v, n) for v, n in SDB_EDITS] + [(SVC, SVC_OLD, SVC_NEW)]


def _read(root: Path, rel: Path) -> str:
    with open(root / rel, encoding="utf-8", newline="") as fh:
        return fh.read()


def check(root: Path) -> list[str]:
    p: list[str] = []
    for rel in NOVOS + SUBSTITUIDOS:
        if not (LOTE / rel).exists():
            p.append(f"fonte do lote em falta: {LOTE / rel}")
    for rel in NOVOS:
        if (root / rel).exists():
            p.append(f"ja existe no destino: {rel}")
    cli_txt = _read(root, Path("watcherdb/install/cli.py")) if (root / "watcherdb/install/cli.py").exists() else ""
    if 'add_parser("provision-login"' not in cli_txt:
        p.append("watcherdb/install/cli.py: aplicar PROVISION_LOGIN primeiro")
    if 'add_parser("configure"' in cli_txt:
        p.append("watcherdb/install/cli.py: ja aplicado")
    for rel, velho, _novo in EDITS:
        t = _read(root, rel).replace("\r\n", "\n")
        c = t.count(velho)
        if c != 1:
            p.append(f"{rel}: ancora esperada 1x, encontrada {c}x: {velho.strip().splitlines()[0][:70]!r}")
    return sorted(set(p))


def apply(root: Path, preview: bool) -> None:
    for rel in NOVOS:
        print(f"{rel}: novo ({(LOTE / rel).read_text(encoding='utf-8').count(chr(10))} linhas)")
    for rel in SUBSTITUIDOS:
        print(f"{rel}: substituido ({(LOTE / rel).read_text(encoding='utf-8').count(chr(10))} linhas)")
    textos: dict[Path, str] = {}
    crlf: dict[Path, bool] = {}
    for rel, velho, novo in EDITS:
        if rel not in textos:
            bruto = _read(root, rel)
            crlf[rel] = "\r\n" in bruto
            textos[rel] = bruto.replace("\r\n", "\n")
        textos[rel] = textos[rel].replace(velho, novo, 1)
    for rel in textos:
        n = sum(1 for r, _, _ in EDITS if r == rel)
        print(f"{rel}: {n} edicao(oes) [{'CRLF' if crlf[rel] else 'LF'} preservado]")
    if preview:
        print("\n--- preview: nada escrito ---")
        return
    for rel in NOVOS + SUBSTITUIDOS:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(LOTE / rel, root / rel)
    for rel, txt in textos.items():
        with open(root / rel, "w", encoding="utf-8", newline="") as fh:
            fh.write(txt.replace("\n", "\r\n") if crlf[rel] else txt)
    print("\naplicado.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--repo", type=Path, default=ROOT)
    a = ap.parse_args()
    root = a.repo.resolve()
    p = check(root)
    if p:
        print("CHECK FALHOU:\n  " + "\n  ".join(p))
        return 1
    print(f"check ok em {root}")
    if a.check:
        return 0
    apply(root, a.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
