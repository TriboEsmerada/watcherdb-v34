# TestSukita TG-2: regista a tarefa agendada que corre o job noturno na 8434. PS7, como ADMIN local. Corre TU.
# Identidade da tarefa: o teu utilizador (o mesmo que corre o servico V34), logon S4U = corre sem sessao aberta e
# sem guardar password. Se o Playwright falhar em S4U (raro, headless nao precisa de desktop), re-regista com
# -LogonType Interactive (exige sessao aberta) ou com password (schtasks /RU /RP).
# Impacto: uma tarefa nova, 02:00 diario, ~20 min de carga leve na 8434 e num servidor TST. Rollback: Unregister-ScheduledTask.
# Verificar: Get-ScheduledTask -TaskName 'WatcherDB-TestSukita' | Get-ScheduledTaskInfo ; docs\qa\externo\NIGHTLY_LOG.md
#Requires -Version 7
#Requires -RunAsAdministrator

$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
$nome = 'WatcherDB-TestSukita'
$hora = '02:00'
$pwsh = (Get-Command pwsh).Source
$log  = Join-Path $repo 'docs\qa\externo\task_last.log'

if (-not (Test-Path (Join-Path $repo '.env.qa'))) { throw ".env.qa nao existe: a tarefa correria sem credenciais (verde vazio = exit 2). ABORT." }

$cmd = "& '$repo\scripts\qa\nightly_testsukita.ps1' *> '$log'"
$action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$cmd`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At $hora
# 1.a prova (10/09 14:21): ficou "Queued" sem arrancar. Causa: portatil em bateria e a condicao por omissao
# DisallowStartIfOnBatteries. Um portatil corporativo passa horas em bateria; a tarefa corre contra localhost.
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -StartWhenAvailable -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited

if (Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue) {
    Write-Host "Tarefa $nome ja existe: a actualizar."
    Set-ScheduledTask -TaskName $nome -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
} else {
    Register-ScheduledTask -TaskName $nome -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description 'TestSukita: smoke do portal (council) + scripts do qa-externo, contra 8434. Bundle em docs/qa/externo/<dia>/' | Out-Null
    Write-Host "Tarefa $nome registada ($hora diario, S4U, $env:USERDOMAIN\$env:USERNAME)."
}

# Prova imediata (opcional): arranca agora e espera; ~20 min
$go = Read-Host "Arrancar a tarefa agora para provar que corre sem sessao? [s/N]"
if ($go -match '^[sS]') {
    Start-ScheduledTask -TaskName $nome
    Write-Host "Arrancada. Acompanha em: Get-ScheduledTaskInfo -TaskName $nome ; Get-Content '$log' -Tail 5"
}
