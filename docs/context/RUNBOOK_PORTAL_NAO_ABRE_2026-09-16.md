# Runbook — o portal não abre ou está muito lento

Criado a 16/09/2026, depois do episódio da manhã (portal a estourar aos 90 s; era rede da máquina, não código).
Objectivo: em dois minutos, separar **problema de rede** de **defeito nosso**, antes de reiniciar seja o que for.

## Sintomas que levam a este runbook

- O portal (8434) não abre, ou demora dezenas de segundos.
- Pedidos leves (uma página estática, um endpoint sem base de dados) também demoram.
- Nos registos aparecem `08001`, `Login timeout expired`, `Error Locating Server/Instance Specified` ou
  `TCP Provider: The wait operation timed out`.

## Os cinco testes, por ordem

Todos são de leitura e não alteram nada. Correr na máquina do serviço.

**1. O serviço está de pé e o processo está a trabalhar ou parado?**
```powershell
$s = Get-CimInstance Win32_Service -Filter "Name='WatcherDBWebServiceV34'"
"{0} PID {1}" -f $s.State, $s.ProcessId
Get-Process -Id $s.ProcessId | Select-Object @{n='CPU_s';e={[math]::Round($_.CPU)}}, @{n='Threads';e={$_.Threads.Count}}
```
- **CPU perto de 0 e sem responder:** está bloqueado à espera de rede ou de bloqueios. Segue para o teste 2.
- **CPU alta e sem responder:** aí sim, suspeitar de código (ciclo, render pesado, consulta a arder).

**2. Os registos dizem ligação ou processamento?**
```powershell
Get-Content 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4\logs\service_stderr.log' -Tail 30
```
`08001`, `Login timeout`, `Error Locating Server/Instance Specified`, `Retrying ... _create_connection` são **falhas de
ligação**, antes de qualquer lógica nossa. Um traceback de Python, um 500 com nome de função ou um erro de SQL (207, 8115,
451) são **defeito nosso**.

**3. A base de dados da Intelligence responde a outro processo?**
```powershell
cd C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4
py -c "import os,sys,time;sys.path.insert(0,'.');[os.environ.setdefault(*l.strip().split('=',1)) for l in open('.env',encoding='utf-8',errors='replace') if '=' in l and not l.startswith('#')];from api.connection_pool import get_intelligence_pool as g;p=g();t=time.time();c=p.get_connection();c.cursor().execute('SELECT 1').fetchone();p.return_connection(c);print(f'{time.time()-t:.2f}s')"
```
- **Menos de 3 s:** a base está bem. O problema está entre o serviço e a rede, ou é saturação do próprio serviço.
- **Falha ou demora:** é rede ou o servidor da Intelligence. Segue para o teste 4.

**4. A resolução de nomes está sã?**
```powershell
Measure-Command { Resolve-DnsName SQLHDSTST505 -QuickTimeout } | Select-Object TotalSeconds
Measure-Command { Test-Connection SQLHDSPRD406 -Count 2 -TimeoutSeconds 2 } | Select-Object TotalSeconds
```
Normal é menos de 2 s. A 15/09 chegou a 700 a 750 s por nome, e nesse estado tudo o que fala com servidores bloqueia.
Se estiver lenta, o problema é de rede, VPN ou DNS, e não vale a pena mexer no produto.

**5. O recolhedor, que é outro processo, está a trabalhar?**
```powershell
Get-Content 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1\logs\watchdog\liveness_20260916.jsonl' -Tail 2
```
Se o recolhedor também está a falhar ligações, são dois processos independentes com o mesmo sintoma: é rede.
Se o recolhedor está bem e só o portal está parado, procura no portal.

## Como confirmar que não foi uma alteração recente

Três perguntas, por esta ordem:

1. **O que falha é ligar ou processar?** Se o erro aparece antes de haver resposta da base, o código novo nem chegou a correr.
2. **O que mudou no último lote?** Um lote de portal (JavaScript, textos) ou um endpoint de leitura não afecta o arranque
   nem o pool de ligações.
3. **O mesmo código estava bom há pouco?** Comparar o tempo de arranque do cache no registo:
   ```powershell
   Select-String -Path 'C:\...\logs\service_stderr.log*' -Pattern 'CACHE\] === TOTAL' | Select-Object -Last 8
   ```
   A 15/09 dava 14 a 21 s. A 16/09, com a rede má, deu 152 s, sem qualquer alteração pelo meio.

## Episódios já vistos (ver SOLUCOES.md)

| Data | O que era |
|---|---|
| 16/09 | Ligação ao servidor da Intelligence a falhar com `Error Locating Server/Instance Specified`; resolvido ao trocar o caminho de rede |
| 15/09 | Resolução de nomes a 700 a 750 s por nome; todos os recolhedores a falhar na frota PRD durante duas horas e meia |
| 02/09 | VPN em baixo: três serviços recusaram o logon por a conta estar registada em formato UPN |

## Defeitos nossos encontrados durante este episódio (por corrigir)

1. ~~**`config/servers.json` lido por caminho relativo** em `api/connection_pool.py`~~ — **resolvido a 16/09**
   (`CONFIG_ABSOLUTO_2026-09-16_apply.py`): os dois ficheiros do pool (`servers.json` e a allowlist do SQL Auth)
   passam por `config_dir()`. O arranque escreve agora `[CONFIG] servers.json=... (existe)` no registo — se disser
   `NAO EXISTE`, a instalação está sem configuração e é isso que explica as ligações pelo SQL Browser. Enquanto
   esteve por corrigir, a frota inteira ligou por identidade de Windows e o rollout do SQL Auth de 09/09 não chegou
   a acontecer — ver `SOLUCOES.md`, linha de 16/09.
2. ~~**`Invalid column name 'must_change_password'`** numa consulta de autenticação~~ — **resolvido a 16/09**: a
   coluna nunca tinha sido criada porque o script 07 abortava com o erro 207; ver `database/14_ADD_MUST_CHANGE_PASSWORD.sql`
   e a linha de 16/09 em `SOLUCOES.md`. Se esta mensagem voltar a aparecer, a base foi reposta de uma cópia anterior a essa
   data — correr o script 14 outra vez (é idempotente).

Ambos resolvidos a 16/09. Depois de um reinício, confirmar no registo a linha `[CONFIG]` e a linha
`SQL Auth rollout allowlist: N servidor(es)`; sem elas, o pool não encontrou a configuração.
