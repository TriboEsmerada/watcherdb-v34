# Comandos Uteis — Infra Local WatcherDB

> **Actualizado:** 2026-07-29
> **Maquina:** portatil do owner (servicos WatcherDB correm aqui)
> **Shell:** PowerShell **como Administrador**
> **Origem:** incidente 2026-07-29 — pico de 43 instancias OFFLINE, falsos positivos
> causados por degradacao do cliente DNS local (`Dnscache`), nao por rede nem AD.
> **Resolvido** no mesmo dia sem reboot, via toggle de placa de rede (seccao 2.3).

## Desfecho do incidente 2026-07-29

| | Manha (10:05) | Tarde (14:00) |
|---|---|---|
| Instancias OFFLINE no portal | 51 | **0** |
| `sql_down` PRD | 38 (falsos) | 0 |
| `sql_down_skipped` (FPs apanhados) | 0 | 41 |
| Resolucao DNS (nome fresco) | > 120 000 ms | **8–33 ms** |
| Instancias no dataset | 44 de 107 | reposto |

Cadeia de causa completa — um problema local atravessou quatro camadas sem que
nenhuma o travasse:

```
Dnscache encravado
  -> resolucao de nomes falha/lenta
  -> collectors falham e nao escrevem KPI_MSSQL_INST_AVAILABILITY_STG
  -> filtro anti-falso-positivo fica sem dados e abre
  -> falsos SQL_DOWN por cima dos falsos OFFLINE
  -> recolha parcial (44 de 107 instancias)
  -> dashboard reporta 100% disponibilidade sobre 41% do parque
```

Hipoteses testadas e **eliminadas com prova**: lockout/expiracao da conta AD,
tunel VPN, rotas do encryption domain, servidores DNS, lista de sufixos,
metrica de interface, carga do Collector.

## Convencoes

- Correr como Administrador (servicos e DNS exigem elevacao).
- Todos os blocos comecam com `cd` — anti-drift de cwd.
- Nada aqui toca em BD. Leitura e gestao de servicos locais apenas.
- Linhas com `#` sao notas, nao comandos.

## Regras de ouro deste ficheiro

1. **Medir antes e depois.** Sem baseline nao se sabe se a reparacao resolveu.
2. **Nomes frescos nas medicoes.** Repetir um nome ja resolvido mede a cache, nao o resolver.
   Um host que resolveu em 18 ms pode estar a 8000 ms se nunca tivesse sido consultado.
3. **`08001` e rede; `18456` e autenticacao.** Ver seccao 4.3. Foi esta distincao
   que ilibou a conta AD em 2 minutos a 29/07.
4. **Ping nao autentica.** Se o portal diz `N offline, 0 sql_down`, a regra que
   disparou foi ping. Conta bloqueada em AD e incapaz de fazer um ping falhar.

---

## 1. Servicos WatcherDB

### 1.1 Listar todos (estado, arranque, conta)

```powershell
cd "C:\Windows\System32"
Get-CimInstance Win32_Service |
    Where-Object { $_.Name -like '*Watcher*' -or $_.DisplayName -like '*WatcherDB*' } |
    Select-Object DisplayName,Name,State,StartMode,StartName |
    Sort-Object DisplayName | Format-Table -AutoSize -Wrap
```

Esperado apos a limpeza de 2026-07-29 + servico V3.4 de 2026-09-03 — **5 servicos**:

| Serviço | Porta | Pasta | Estado | Conta |
|---|---|---|---|---|
| `WatcherDBCollector` | — | WATCHERDB INTELLIGENCE V1 | Running | `ue_e-snetto@tapnet.tap.pt` |
| `WatcherDBWebServiceV33` | 8433 | WATCHERDB_V3.3 (`.venv-build`) | Running | `ue_e-snetto@tapnet.tap.pt` |
| `WatcherDBWebServiceV34` | 8434 | WATCHERDB_V3.4 (`.venv-build`) | Running | `ue_e-snetto@tapnet.tap.pt` |
| `WatcherDBWebServiceV6` | 8660 | WATCHERDB_V6 | Running | `TAPNET\ue_e-snetto` |
| `WatcherDBSSIS` | — | — | Stopped (Auto) | `ue_e-snetto@tapnet.tap.pt` |

> **8434** deixou de estar livre nesta maquina (2026-09-03). O INSTALL_GUIDE cliente
> (`docs/external/standard/INSTALL_GUIDE.md:469`) usa 8434 como *exemplo* de porta
> alternativa — valido no cliente, nao aqui; e o runbook de auditoria de 04/07
> (`AUDITORIA_EMPACOTAMENTO_2026-07-04_RUNBOOK_ETAPA2.md`) criava um servico efemero
> na 8434 — se for re-corrido, usar 8435. Instalacao/rollback do V34:
> `SERVICO_V34_8434_RUNBOOK_2026-09-03.md`.

> **Nota de risco:** todos correm com a conta pessoal do owner, e
> `api/connection_pool.py:694` usa `Trusted_Connection=yes`. Logo **todas** as
> ligacoes as 107 instancias sao Kerberos com essa identidade. Bloqueio ou
> expiracao de password derruba o produto inteiro. Desconformidade conhecida com
> a Regra de Ouro #2, assumida em comentario no codigo (linha 670) como temporaria.
> Correccao de fundo: conta de servico AD dedicada (idealmente gMSA).

### 1.2 Reiniciar os dois activos

```powershell
cd "C:\Windows\System32"
Restart-Service -Name WatcherDBCollector,WatcherDBWebServiceV33 -Force
Start-Sleep -Seconds 30
Get-Service WatcherDBCollector,WatcherDBWebServiceV33 |
    Select-Object Name,Status,StartType | Format-Table -AutoSize
```

- Varios nomes levam **virgula**. `-Name A B` da erro de parametro posicional.
- Impacto: portal fora ~15 s; ciclo de recolha em curso aborta e recomeca.
- **Pre-requisito:** so reiniciar **depois** do DNS estar bom (seccao 2). Com
  varios segundos por nome e 107 instancias, o collector volta a encravar.

### 1.3 Saude do portal

```powershell
cd "C:\Windows\System32"
Invoke-RestMethod -Uri "http://localhost:8433/health/live"        -TimeoutSec 10
Invoke-RestMethod -Uri "http://localhost:8433/health/ready"       -TimeoutSec 10
Invoke-RestMethod -Uri "http://localhost:8433/health/web-service" -TimeoutSec 10
```

Endpoints reais sao `/health/*`. **Nao existe `/healthz`.**

### 1.4 Porta a escuta

```powershell
cd "C:\Windows\System32"
Get-NetTCPConnection -LocalPort 8433 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
```

Portal: `http://localhost:8433/watcherdb` — usar **localhost**. O IP da VPN muda
a cada reconnect e parte bookmarks (a 29/07 passou de `10.88.23.201` para `10.88.24.65`).

---

## 2. DNS — diagnostico e reparacao

### 2.1 MEDIR primeiro (nunca reparar as cegas)

```powershell
cd "C:\Windows\System32"
# Usar hosts NUNCA resolvidos nesta sessao. Repetir um nome mede a cache.
foreach ($n in 'SQLHDSPRD211','SQLHDSPRD402','SQLRPAPRD02','SQLHDSPRD024') {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $r  = Resolve-DnsName $n -Type A -QuickTimeout -ErrorAction SilentlyContinue
    $sw.Stop()
    "{0,-20} {1,-16} {2}ms" -f $n, $(if($r){(($r|Where-Object Type -eq 'A').IPAddress -join ',')}else{'(nada)'}), $sw.ElapsedMilliseconds
}
```

Escala de leitura:

| Tempo | Estado |
|---|---|
| < 100 ms | saudavel |
| ~1700 ms | degradado |
| > 20000 ms | severo |

Referencia: o servidor DNS responde a query identica em **~20–40 ms** (seccao 3.1).
Toda a diferenca acima disso e overhead do cliente local.

### 2.2 Flush + tentativa de restart

```powershell
cd "C:\Windows\System32"
ipconfig /flushdns
try { Restart-Service -Name Dnscache -Force -ErrorAction Stop; 'OK via Restart-Service' }
catch { "falhou: $($_.Exception.Message)"; net stop dnscache; net start dnscache }
Start-Sleep -Seconds 3
Get-Service Dnscache | Select-Object Name,Status,StartType | Format-Table -AutoSize
```

- `Dnscache` e **servico protegido** no Win11. Espera-se falhar com
  `Cannot open Dnscache service` / `The requested pause, continue, or stop is not
  valid for this service`. Nesse caso ir a **2.3 (toggle de placa — foi o que
  funcionou)**; so depois 2.4 (matar o processo) e, em ultimo, reboot.
- `Status: Running` **nao prova** que esta bom — ele penduraba com Running.
  A prova e a medicao de 2.1.
- O flush **destapa mas nao cura**. Pior: esvazia a cache que mascarava o
  problema, pelo que a medicao logo a seguir parece pior. E' honestidade, nao regressao.

### 2.3 Toggle de placa de rede — O REINICIO QUE FUNCIONA

> **Foi isto que resolveu o incidente de 2026-07-29.** Nao foi o flush, nao foi a
> metrica, nao foi parar o Collector.

O `Dnscache` e servico protegido e recusa `Restart-Service` / `net stop`. Mas
desactivar e reactivar **qualquer** adaptador de rede forca o cliente DNS a
reconstruir do zero a lista de interfaces e de servidores — que e, na pratica, o
reinicio de estado que o SCM nao deixa fazer. Porta lateral que o Windows permite.

```powershell
cd "C:\Windows\System32"
# Usar um adaptador SEM ligacao activa (aqui a placa fisica sem cabo).
# NUNCA usar a "Ethernet 2" da VPN — derruba o tunel.
Disable-NetAdapter -Name 'Ethernet' -Confirm:$false
Start-Sleep -Seconds 5
Enable-NetAdapter -Name 'Ethernet'
Start-Sleep -Seconds 5
ipconfig /flushdns
foreach ($n in 'SQLHDSPRD214','SQLHDSPRD404','SQLMDMPRD02','OATXP01') {
    $sw=[Diagnostics.Stopwatch]::StartNew()
    $r=Resolve-DnsName $n -Type A -QuickTimeout -ErrorAction SilentlyContinue
    $sw.Stop()
    "{0,-20} {1,-16} {2}ms" -f $n,$(if($r){(($r|Where-Object Type -eq 'A').IPAddress -join ',')}else{'(nada)'}),$sw.ElapsedMilliseconds
}
```

- **A primeira consulta apos o toggle e sempre lenta** (1–22 s medidos) — e o custo
  da reconstrucao, nao regressao. As seguintes e que contam.
- Confirmar no fim que a placa ficou `Disconnected` (normal sem cabo) e **nao**
  `Disabled`, senao o cabo deixa de funcionar quando for preciso:
  `Get-NetAdapter -Name 'Ethernet' | Select-Object Name,Status`
- Resultado a 2026-07-29: `>120000 ms` → **8 ms**.

### 2.4 Matar o processo do Dnscache (quando o restart e recusado)

```powershell
cd "C:\Windows\System32"
$svcPid = (Get-CimInstance Win32_Service -Filter "Name='Dnscache'").ProcessId
"PID actual: $svcPid"
$partilha = Get-CimInstance Win32_Service | Where-Object ProcessId -eq $svcPid
$partilha | Select-Object Name,DisplayName,State | Format-Table -AutoSize
if ($partilha.Count -gt 1) { Write-Host 'PARA: svchost partilhado. NAO matar.' -ForegroundColor Red } else { Write-Host "Isolado. Seguro:  taskkill /PID $svcPid /F" -ForegroundColor Yellow }
```

- **`if`/`else` tem de ficar na MESMA linha.** `else` numa linha nova rebenta em
  consola interactiva com `CommandNotFoundException`.
- **Nao usar `Win32_Process.CommandLine`** para testar isolamento — vem vazio em
  processos protegidos e da falso alarme de "partilhado". A verificacao correcta
  e por `ProcessId`, como acima.
- O PID **muda a cada arranque**. Ler sempre na hora, nunca fixar.
- Se nao voltar sozinho: `Start-Service Dnscache`.

### 2.5 Inspeccionar a configuracao de resolucao

```powershell
cd "C:\Windows\System32"
$g = Get-DnsClientGlobalSetting
"SuffixSearchList : $($g.SuffixSearchList -join ', ')"
Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } |
    Select-Object InterfaceAlias,InterfaceIndex,ServerAddresses | Format-Table -AutoSize
Get-NetAdapter | Select-Object Name,InterfaceIndex,Status,LinkSpeed |
    Sort-Object InterfaceIndex | Format-Table -AutoSize
Get-NetIPInterface -AddressFamily IPv4 | Where-Object ConnectionState -eq 'Connected' |
    Select-Object InterfaceAlias,InterfaceMetric,AutomaticMetric | Sort-Object InterfaceMetric | Format-Table -AutoSize
```

Baseline 2026-07-29:

- Sufixos: `tapnet.tap.pt`, `tap.pt`, `gestao`, `pga.pt`, `groundforce.pt` (5 — o
  primeiro e o que resolve; os restantes so acrescentam latencia em nomes curtos)
- DNS internos `10.128.0.100` / `10.128.0.101` em **Ethernet 2** (VPN Check Point, idx 22)
  e em **Ethernet** (idx 16, **Disconnected** — config DHCP orfa)
- Wi-Fi (idx 7) com `192.168.1.1` (router de casa)
- `Ethernet 2`: `InterfaceMetric` **vazio** + `AutomaticMetric: Disabled`

### 2.6 Metrica de interface — ARMADILHA

> **Nao repetir sem medir.** A 2026-07-29 tentou-se `Set-NetIPInterface -InterfaceIndex 22
> -InterfaceMetric 1` para dar prioridade a interface da VPN. Resultado: a resolucao
> **piorou de 1,6–8,4 s para 19–32 s**. Revertido.

Rollback:

```powershell
cd "C:\Windows\System32"
Set-NetIPInterface -InterfaceIndex 22 -AddressFamily IPv4 -AutomaticMetric Enabled
ipconfig /flushdns
```

Depois **remedir com 2.1 e nomes frescos**.

### 2.7 Hipotese REFUTADA: tempestade de resolucao do Collector

> **Nao voltar a perseguir esta pista.** Levantou-se a hipotese de que o Collector
> saturava a fila do cliente DNS (107 resolucoes por ciclo, com retry a alimentar a
> saturacao). **Testada e refutada duas vezes:**
>
> 1. Com o Collector **parado**, o DNS continuou mau (1377–1880 ms) e o
>    `ipconfig /flushdns` chegou a pendurar por completo. Um flush e um pedido RPC
>    local: se bloqueia com **zero carga**, nao ha fila para saturar.
> 2. Com o Collector a correr apos a reparacao, o DNS manteve-se a **13–33 ms**.
>
> A degradacao progressiva era a avaria do `Dnscache` a agravar-se sozinha, mais o
> ruido da alteracao de metrica. **O Collector nao degrada o resolver.**

O teste de isolamento abaixo continua util para eliminar carga como variavel em
incidentes futuros (parar, **nao** reiniciar):

```powershell
cd "C:\Windows\System32"
Stop-Service -Name WatcherDBCollector -Force
Start-Sleep -Seconds 20
ipconfig /flushdns
foreach ($n in 'SQLHDSPRD406','SQLHDSPRD412','SQLMDMPRD04','SQLIJSPRD03') {
    $sw=[Diagnostics.Stopwatch]::StartNew()
    $r=Resolve-DnsName $n -Type A -QuickTimeout -ErrorAction SilentlyContinue
    $sw.Stop()
    "{0,-20} {1,-16} {2}ms" -f $n,$(if($r){(($r|Where-Object Type -eq 'A').IPAddress -join ',')}else{'(nada)'}),$sw.ElapsedMilliseconds
}
```

- **Interpretacao:** se cair para dezenas/centenas de ms, a causa e o Collector.
  Se ficar em segundos, a causa e o `Dnscache` em si → seccao 2.3, depois reboot.
- Repor sempre no fim: `Start-Service -Name WatcherDBCollector`

---

## 3. Diagnostico que IGNORA o resolver

> Quando o `Dnscache` esta degradado, **tudo o que usa nomes mente** — incluindo
> `ping`, `Test-NetConnection`, SSMS, RDP e o proprio Collector. Estes comandos
> falam UDP:53 directo ao servidor e ICMP por IP. Foi esta seccao que resolveu
> o incidente de 29/07.

### 3.1 Funcao: resolver A record por UDP directo

Colar uma vez por sessao.

```powershell
function Resolve-Raw($srv,$name,$to=2500){
  $b=New-Object System.Collections.Generic.List[byte]
  $b.AddRange([byte[]](0xAB,0xCD,0x01,0x00,0x00,0x01,0x00,0x00,0x00,0x00,0x00,0x00))
  foreach($l in $name.Split('.')){ $b.Add([byte]$l.Length); $b.AddRange([System.Text.Encoding]::ASCII.GetBytes($l)) }
  $b.Add(0); $b.AddRange([byte[]](0x00,0x01,0x00,0x01)); $q=$b.ToArray()
  try{ $u=New-Object System.Net.Sockets.UdpClient; $u.Client.ReceiveTimeout=$to
       $u.Connect($srv,53); $null=$u.Send($q,$q.Length)
       $ep=New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any,0)
       $r=$u.Receive([ref]$ep); $u.Close() } catch { return $null }
  $an=($r[6]*256)+$r[7]; if($an -eq 0){ return $null }
  $p=12; while($r[$p] -ne 0){ $p += 1+$r[$p] }; $p += 5
  for($i=0;$i -lt $an;$i++){
    if(($r[$p] -band 0xC0) -eq 0xC0){ $p+=2 } else { while($r[$p] -ne 0){ $p+=1+$r[$p] }; $p+=1 }
    $t=($r[$p]*256)+$r[$p+1]; $rdl=($r[$p+8]*256)+$r[$p+9]; $p+=10
    if($t -eq 1 -and $rdl -eq 4){ return "$($r[$p]).$($r[$p+1]).$($r[$p+2]).$($r[$p+3])" }
    $p+=$rdl }
  return $null }

# Uso — devolve o IP em ~20-40ms mesmo com o resolver do Windows encravado:
Resolve-Raw '10.128.0.100' 'SQLHDSPRD013.tapnet.tap.pt'
```

### 3.2 Varrer hosts: resolve + ping, sem tocar no resolver

Prova se um pico de OFFLINE e real ou falso positivo.

```powershell
$hosts = @('SQLHDSPRD013','SQLMDMPRD01','SQLIDSPRD03')   # <-- editar
$ping  = New-Object System.Net.NetworkInformation.Ping
$res = foreach($h in $hosts){
    $ip = Resolve-Raw '10.128.0.100' "$h.tapnet.tap.pt"
    if(-not $ip){ [pscustomobject]@{Host=$h;IP='(sem A record)';Ping='-';RTT=''} }
    else { $r=$ping.Send($ip,1500)
           [pscustomobject]@{Host=$h;IP=$ip;Ping=$r.Status;RTT=$(if($r.Status -eq 'Success'){"$($r.RoundtripTime)ms"}else{''})} } }
$res | Format-Table -AutoSize
"Vivos: $(($res | Where-Object Ping -eq 'Success').Count) / $($res.Count)"
```

A 2026-07-29 este comando deu **43/43 vivos** enquanto o dashboard mostrava 43 offline.

### 3.3 Extrair do log os hosts que o portal diz estarem offline

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\services\web_service\logs"
Select-String -Path .\stdout.log -Pattern 'Offline hosts para filtro' | Select-Object -Last 1 -ExpandProperty Line
Select-String -Path .\stdout.log -Pattern 'Server Offline \(rule'      | Select-Object -Last 3 -ExpandProperty Line
```

A regra e `ping_ok`. `N offline, 0 sql_down` significa problema de **rede ou nome**,
nunca de autenticacao.

### 3.4 Testar porta TCP com timeout real

`Test-NetConnection` pendura quando o DNS esta mau; isto nao.

```powershell
$alvo='172.17.152.101'; $porta=50175
$c=New-Object System.Net.Sockets.TcpClient
$a=$c.BeginConnect($alvo,$porta,$null,$null)
$ok=$a.AsyncWaitHandle.WaitOne(3000) -and $c.Connected
"{0}:{1} -> {2}" -f $alvo,$porta,$(if($ok){'ABERTO'}else{'fechado/timeout'}); $c.Close()
```

### 3.5 Descobrir a porta REAL de instancia nomeada (SQL Browser UDP 1434)

```powershell
$alvo='172.17.152.101'
try{ $u=New-Object System.Net.Sockets.UdpClient; $u.Client.ReceiveTimeout=2500
     $u.Connect($alvo,1434); $null=$u.Send([byte[]](0x02),1)
     $ep=New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any,0)
     $r=$u.Receive([ref]$ep); $u.Close()
     [System.Text.Encoding]::ASCII.GetString($r,3,$r.Length-3) }
catch { "Browser UDP1434 sem resposta: $($_.Exception.Message)" }
```

> **As instancias usam portas DINAMICAS.** Testar `1433` as cegas da falso negativo:
> a 29/07 todas as 5 instancias testadas tinham 1433 fechado e estavam perfeitamente
> acessiveis nas portas reais.

Devolve `ServerName;...;InstanceName;I03;...;tcp;50175;...` → SSMS liga a `172.17.152.101,50175`.

Exemplos confirmados a 2026-07-29:

| Instancia | Endereco |
|---|---|
| `SQLHDSPRD013\I03` | `172.17.152.101,50175` |
| `SQLMDMPRD01\I01` | `172.17.152.59,49819` |

### 3.6 ICMP por IP com timeout curto

```powershell
$p = New-Object System.Net.NetworkInformation.Ping
foreach ($ip in '10.128.0.100','10.128.0.101','172.17.152.101') {
    $r = $p.Send($ip, 2000)
    "{0,-16} {1} {2}" -f $ip,$r.Status,$(if($r.Status -eq 'Success'){"$($r.RoundtripTime)ms"})
}
```

### 3.7 RDP e SSMS por IP (contorno imediato)

```
SSMS:  172.17.152.101,50175
RDP:   mstsc /v:172.17.152.101
```

Desbloqueia trabalho sem esperar por reparacao do DNS.

---

## 4. Logs

### 4.1 Portal V3.3

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\services\web_service\logs"
Get-ChildItem | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
Get-Content .\service.log -Tail 40      # ciclo de vida do servico
Get-Content .\errors.log  -Tail 40      # tracebacks
Get-Content .\stderr.log  -Tail 40      # runtime ao vivo — e' aqui que esta o util
```

> `stdout.log`, `stderr.log` e `audit.log` passam dos **400 MB**. Usar **sempre**
> `-Tail`, nunca abrir inteiro.

### 4.2 Collector V1 Intelligence (arvore diferente)

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1\services\collector_service\logs"
Get-ChildItem | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
Get-Content .\service.log       -Tail 40
Get-Content .\collectors.log    -Tail 40
Get-Content .\errors.log        -Tail 40
Get-Content .\faulthandler.log  -Tail 20   # crashes de baixo nivel
```

### 4.3 Distinguir falha de REDE de falha de AUTENTICACAO

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\services\web_service\logs"
Select-String -Path .\stderr.log -Pattern '08001|Login timeout|Error Locating Server' | Select-Object -Last 5
Select-String -Path .\stderr.log -Pattern '28000|Login failed for user|18456'         | Select-Object -Last 5
```

| Assinatura | Significado |
|---|---|
| `08001`, `Login timeout expired`, `Error Locating Server/Instance` | **rede ou DNS** |
| `28000`, `Login failed for user`, `18456` | **autenticacao** — so aqui suspeitar de AD |

---

## 5. Gestao de servicos (pywin32)

### 5.1 Ver a que codigo um servico aponta (revela orfaos)

```powershell
cd "C:\Windows\System32"
foreach($s in 'WatcherDBWebServiceV33','WatcherDBCollector','WatcherDBSSIS','WatcherDBWebServiceV6'){
  $pc=(Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\$s\PythonClass" -ErrorAction SilentlyContinue).'(default)'
  "--- $s ---"; "  $pc" }
```

> O `PathName` do `Win32_Service` so mostra `pythonservice.exe` e nao diz nada.
> A verdade esta no registo, em `PythonClass`.

### 5.2 Backup antes de apagar (parametrizado)

```powershell
$servicos = @('NomeDoServico1','NomeDoServico2')   # <-- editar
$bkp = "C:\Users\ue_e-snetto\Documents\backup_servicos_$(Get-Date -Format 'yyyyMMdd')"
New-Item -ItemType Directory -Path $bkp -Force | Out-Null
foreach ($s in $servicos) { reg.exe export "HKLM\SYSTEM\CurrentControlSet\Services\$s" "$bkp\$s.reg" /y }
Get-ChildItem $bkp | Select-Object Name,Length | Format-Table -AutoSize
```

Confirmar **1 ficheiro por servico** antes de avancar para 5.3.

### 5.3 Apagar (destrutivo — exige o backup de 5.2 feito)

```powershell
cd "C:\Windows\System32"
foreach ($s in $servicos) { "--- $s ---"; sc.exe delete $s }
```

- Tem de ser **`sc.exe`**. Em PowerShell, `sc` e alias de `Set-Content`.
- Apagar o servico **nao apaga codigo**. So remove a inscricao no SCM.
- Rollback: `reg.exe import "$bkp\<nome>.reg"` + reboot; ou re-registar via
  `python service.py install` no projecto (mais limpo).

Executado a 2026-07-29 — 4 orfaos removidos, backup em
`C:\Users\ue_e-snetto\Documents\backup_servicos_20260729`:

| Serviço | Apontava para | Estado do alvo |
|---|---|---|
| `WatcherDBWebService` | `C:\BKP PC TAP - 21012026\...\WATCHERDB_DEV\...` | ausente |
| `WatcherDBV5WebService` | `C:\BKP PC TAP - 21012026\...\WATCHERDB_V5\...` | ausente |
| `WatcherDBWebServiceV31` | `projetosPython\WATCHERDB_V3.1\...` | presente (legacy) |
| `WatcherDBWebServiceV32` | `projetosPython\WATCHERDB_V3.2\...` | presente (legacy) |

---

## 6. VPN / rede

```powershell
cd "C:\Windows\System32"
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' } |
    Select-Object IPAddress,InterfaceAlias,PrefixLength | Format-Table -AutoSize
Get-NetRoute -AddressFamily IPv4 |
    Where-Object { $_.DestinationPrefix -like '172.17.*' -or $_.DestinationPrefix -like '10.128.*' } |
    Select-Object DestinationPrefix,NextHop,InterfaceAlias | Format-Table -AutoSize
```

- Se as rotas `172.17.x` e `10.128.x` existirem, o encryption domain esta bom e o
  problema **nao e a VPN** — procurar no DNS (seccao 2) ou nos servicos.
- **`Terminate unauthorized TCP connections`** no log do Check Point e **benigno**:
  derruba de proposito as sessoes TCP pre-tunel para nao contornarem as rotas novas.
  Efeito lateral real: mata os pools de ligacao do WatcherDB a cada reconnect → seccao 1.2.
- O IP da VPN muda a cada reconnect. Usar sempre `localhost` para o portal.

---

## 7. Follow-ups em aberto

| Item | Nota |
|---|---|
| **Verde falso sobre dados truncados** | O card mostrou **100% disponibilidade com 44 das 107 instancias**, sem qualquer sinal de que faltavam 63. O falso OFFLINE grita; o verde falso nao. Vale uma Wave propria, nao um finding. |
| **Filtro anti-FP depende do pipeline que falhou** | O supressor de dynamic-port FPs consulta `KPI_MSSQL_INST_AVAILABILITY_STG`. Depois de qualquer interrupcao esses dados estao velhos, o filtro abre e produz uma salva de falsos `SQL_DOWN` (38 em PRD a 13:34) ate recuperar (~3 min). Auto-cura, mas cada incidente e amplificado. |
| **`OATXP01` — `SQL_DOWN` com 1433 aberto** | Collector reporta `TCP 1433 fail: TCP timeout (15.0s)`; teste manual da mesma maquina da **`TCP 1433 ABERTO`**. Nao e da classe dynamic-port (essa foi toda apanhada: 41 skipped). O caminho `ip_rescued` salvou 40 instancias e falhou esta — o `id` nao tem sufixo `_I01` como as restantes. Por confirmar. |
| **Collector marca OFF por falha de nome** | Uma avaria no resolver local produziu **43 falsos criticos**, indistinguiveis de queda real de PRD. Os IPs sao estaveis (`172.17.x`, atribuicao fixa): resolver uma vez, cachear com refresh periodico e fallback para nome elimina a classe inteira. |
| **Servicos com conta pessoal** | Migrar para conta de servico AD dedicada (gMSA). Nao passar para `sql_monitoring`: e' apenas `datareader` na maioria dos servidores e nao tem `EXECUTE` em `xp_readerrorlog` — partiria funcionalidade. |
| **`WatcherDBSSIS`** | `Auto` mas `Stopped`; aponta para `C:\BKP PC TAP - 21012026\...\WATCHERPKG` (pasta de backup de migracao de PC). Decidir: re-registar no caminho actual, ou passar a `Disabled` e apagar. |
| **`Ethernet` idx 16** | Disconnected com `DhcpNameServer` interno orfa. Candidato a contribuir para a latencia de resolucao. `Disable-NetAdapter -Name 'Ethernet' -Confirm:$false` (rollback: `Enable-NetAdapter`). Reactivar se voltar a usar cabo ou dock. |
| **`Ethernet 2` sem metrica** | `AutomaticMetric: Disabled` sem valor. Forcar `-InterfaceMetric 1` **piorou** (ver 2.6). Investigar porque o cliente Check Point deixa a interface neste estado. |

---

## 8. Git com sessoes concorrentes no mesmo working tree

> Incidente 2026-07-29. Os 4 ficheiros foram adicionados **por nome**, um a um, como
> manda a regra anti-`add -A`. Mesmo assim entraram no commit 3 linhas de outra
> sessao, porque estavam **dentro** de um dos ficheiros. Nada se perdeu, mas a
> atribuicao ficou errada no historico.

### 8.1 A regra

`git add <ficheiro>` protege contra apanhar **ficheiros** alheios. **Nao** protege
contra apanhar **linhas** alheias dentro de um ficheiro partilhado.

Ficheiros de escrita partilhada neste repo -- sempre por hunk, nunca inteiros:

- `docs/context/CONTEXT.md` (blackboard, varias sessoes anexam)
- `findings-inbox.md`
- `CHANGELOG.md`

### 8.2 Staging por hunk

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython"
git add -p WATCHERDB_V3.3/docs/context/CONTEXT.md
```

Teclas: `y` inclui o hunk, `n` salta, `s` parte em hunks menores, `e` edita a mao,
`q` sai. Para linhas adjacentes de sessoes diferentes, `s` ate isolar, e `e` quando
`s` ja nao parte mais.

### 8.3 Verificar SEMPRE antes de commitar

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython"
git diff --cached -- WATCHERDB_V3.3/docs/context/CONTEXT.md
```

Ler o diff **ate ao fim**. No incidente de 29/07 as linhas alheias estavam depois
das proprias, no fim de um diff longo. `git reset` desfaz o staging sem tocar nos
ficheiros.

### 8.4 `git switch` move a arvore INTEIRA

So existe um working tree. Criar ou trocar de branch **muda a branch da sessao
paralela tambem**, sem aviso. Antes de `git switch -c`, confirmar que ninguem esta
a meio de trabalho.

### 8.5 Recuperacao: copiar, nunca reescrever

Se um commit levou trabalho de outra sessao, **nao reescrever o historico** --
cirurgia de risco sobre texto que nao e nosso, so para corrigir atribuicao. Copiar
o commit para a branch certa:

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython"
git switch <branch-da-outra-sessao>
git cherry-pick <sha>
```

Fica em ambas as branches, com SHAs diferentes e conteudo identico. Foi o que se
fez a 29/07: `56f3671` em `docs/incidente-dns-passo0-cobertura` e `4829478` em
`wave-b-indexacao-dmv`.

**Nao voltar para a branch antiga sem copiar primeiro**: o ficheiro reverte para a
versao dessa branch e o trabalho da outra sessao desaparece do disco (fica so no
commit), o que parece perda de dados a quem estiver do outro lado.
