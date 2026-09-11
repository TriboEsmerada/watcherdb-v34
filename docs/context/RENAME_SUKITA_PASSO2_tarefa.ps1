# RENAME - PASSO 2: tarefa agendada WatcherDB-TestGrapete -> WatcherDB-TestSukita. PS7 como ADMIN. Corre TU.
# Remove a antiga e regista a nova pelo script ja renomeado (mesmo horario 02:00, S4U, bateria permitida).
#Requires -Version 7
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
if (-not (Test-Path (Join-Path $repo 'scripts\qa\nightly_testsukita.ps1'))) { throw "PASSO 1 nao aplicado (nightly_testsukita.ps1 nao existe). ABORT." }
$antiga = Get-ScheduledTask -TaskName 'WatcherDB-TestGrapete' -ErrorAction SilentlyContinue
if ($antiga) {
    if ($antiga.State -eq 'Running') { throw "a tarefa antiga esta' a correr; espera que termine. ABORT." }
    Unregister-ScheduledTask -TaskName 'WatcherDB-TestGrapete' -Confirm:$false
    Write-Host "Tarefa WatcherDB-TestGrapete removida."
} else { Write-Host "Tarefa antiga ja nao existe." }
& pwsh (Join-Path $repo 'docs\context\TG2_TAREFA_AGENDADA.ps1')
Get-ScheduledTask -TaskName 'WatcherDB-TestSukita' | Select-Object TaskName, State | Format-Table
