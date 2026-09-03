# Runbook — Serviço Windows (Python/pywin32) com conta de serviço dedicada

Origem: migração do serviço **SSIS Manager** (PRD) para a conta
`TAPNET\ua_dbassismngr_svc`, 2026-08-14. O serviço morria no arranque com
«service-specific error code 1» («Incorrect function»). Este guião aplica-se a
qualquer serviço Windows nosso hospedado pelo `pythonservice.exe` do pywin32
(SSIS Manager, Cockpit/COCKPITACCESS, WatcherDB) quando se muda a conta de
serviço ou o Python da máquina.

---

## As cinco causas encontradas (por ordem de importância)

**1. Dependências instaladas com `pip --user` no perfil de quem instalou.**
`pip install` sem elevação cai em `C:\Users\<instalador>\AppData\Roaming\Python\...`.
A conta de serviço **não vê essa pasta** — para ela `fastapi`, `pyodbc`, etc.
não existem, e o `pip` mente («already satisfied») porque olha para o perfil de
quem o corre. Instalar SEMPRE para a máquina:

```powershell
$env:PYTHONNOUSERSITE = '1'          # ignora o site-packages do perfil
& 'C:\Program Files\Python312\python.exe' -m pip install -r requirements.txt
Remove-Item Env:\PYTHONNOUSERSITE
```

**2. Pós-install do pywin32 nunca corrido no Python da máquina.**
Sintoma associado: eventos «Python Service» no Event Log com
«Cannot retrieve event message text». Corrigir:

```powershell
& $Py -m pip install --upgrade pywin32
& $Py 'C:\Program Files\Python312\Scripts\pywin32_postinstall.py' -install
```

Se aparecer «Error installing pywintypesXXX.dll — being used by another
process»: a DLL já existe em `system32` e está carregada por OUTRO serviço
Python da máquina (ex.: COCKPITACCESS). **Ignore é seguro** (a DLL já lá
está). NÃO fazer `Get-Process pythonservice | Stop-Process` às cegas — mata
os serviços Python todos da máquina (aconteceu: derrubou o COCKPITACCESS;
`Restart-Service COCKPITACCESS` repôs).

**3. NTFS: a conta precisa de escrita na pasta da aplicação.**
O wrapper cria `logs\service.log` logo ao importar o módulo — sem escrita, o
processo morre antes de se anunciar ao SCM (= erro 1 sem uma linha de log).
A app também escreve em `database\` (auth SQLite) e `data\`:

```powershell
icacls "<pasta da app>" /grant "TAPNET\<conta>:(OI)(CI)M" /T
```

**4. Registo pywin32: o `PythonClass` vive em `Services\<svc>\Parameters`**,
não na raiz da chave do serviço. Verificação certa e reparação:

```powershell
Get-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Services\<SVC>\Parameters
& $Py "<pasta da app>\watcherdb_ssis_service.py" update   # reescreve o registo
```

Depois do `update`, confirmar em `services.msc` → Log On que a conta não
voltou a LocalSystem.

**5. Python per-user é uma armadilha para serviços.** Se o `ImagePath`
apontar para `C:\Users\<alguém>\AppData\...`, a conta de serviço não lê a
instalação. Remendo: `icacls` RX na árvore do Python; definitivo: Python
«for all users» em `Program Files` e re-registar o serviço.

---

## Diagnóstico rápido (por esta ordem)

```powershell
$Svc = '<NOME_DO_SERVICO>'
# 1. Erro real do SCM
Get-WinEvent -FilterHashtable @{LogName='System'; Id=7000,7009,7024,7034} -MaxEvents 5 | Format-List TimeCreated, Message
# 2. Executavel, conta e registo pywin32
$k = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\$Svc"
$k.ImagePath; $k.ObjectName
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\$Svc\Parameters"
# 3. O log da app ganhou linhas? (sem linhas novas = morreu antes do logging → NTFS/DLL)
Get-Content "<pasta da app>\logs\service.log" -Tail 15
Get-Content "<pasta da app>\logs\stderr.log"  -Tail 15
# 4. O teste que tira o SCM da equacao — o erro real aparece no ecra
& $Py "<pasta da app>\watcherdb_ssis_service.py" debug
```

Notas de leitura do erro:
- «error code 1 / Incorrect function» → o processo Python arrancou e morreu
  cedo (DLL, NTFS, import) — NÃO é password nem firewall.
- «error 1069 / logon failure» → aí sim é a password/direito «Log on as a
  service» (services.msc → Log On → reintroduzir credenciais atribui o direito).

---

## Acessos SQL da conta de serviço (SSIS Manager)

A conta precisa de login em **todas** as instâncias que o portal lê — em
2026-08-14 eram 6: DEV `SQLHDSTST105\I01`, QLT app `CN_SQL_Q01_APP\I01`,
QLT jobs `SQLHDSQLT103\SQLIJSQLT03`, PRD app `CN_SQL_P01_RPT\I01`,
PRD jobs `SQLIJSPRD03\SQLIJSQLP03`, Control-M `SQLAGSPRD405\I01`.

Em todas:

```sql
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'TAPNET\ua_dbassismngr_svc')
    CREATE LOGIN [TAPNET\ua_dbassismngr_svc] FROM WINDOWS;
GRANT VIEW SERVER STATE TO [TAPNET\ua_dbassismngr_svc];
USE msdb;
CREATE USER [TAPNET\ua_dbassismngr_svc] FOR LOGIN [TAPNET\ua_dbassismngr_svc];
ALTER ROLE db_datareader ADD MEMBER [TAPNET\ua_dbassismngr_svc];
```

Só nos servidores de app (DEV/QLT/PRD): `DW_LOGGING_BI` (db_datareader +
`GRANT INSERT, SELECT, ALTER ON SCHEMA::AUDIT` + `GRANT CREATE TABLE`, por
causa da `GHOST_ANALYSIS_HISTORY`), `DW_ORCHESTRATOR` e `DW_ADMIN_BI`
(db_datareader). Só no servidor Control-M: `ctrlmdb920` (db_datareader).

Rede: instâncias nomeadas novas (ex.: `SQLAGSPRD405\I01`) precisam de TCP na
porta da instância **e UDP 1434** (SQL Browser) a partir do servidor da app —
ou porta fixa na configuração, que dispensa o UDP.

---

## Checklist de migração de conta de serviço (resumo)

1. `services.msc` → Log On → conta nova + password (atribui o direito de logon).
2. `icacls` Modify na pasta da app.
3. Dependências no Python da máquina (`PYTHONNOUSERSITE=1` + pip como admin).
4. pywin32 pós-install corrido nesse Python.
5. `watcherdb_ssis_service.py update` + confirmar `Parameters` no registo.
6. Logins SQL da conta em todas as instâncias + grants.
7. `... debug` em consola → depois `Start-Service` → health endpoint.
