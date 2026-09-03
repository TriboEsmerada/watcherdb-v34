$server = 'SQLHDSPRD212'
$instanceName = 'I01'

try {
    $result = Invoke-Command -ComputerName $server -ScriptBlock {
        param($instName)
        $instProp = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL' -ErrorAction Stop
        $instanceId = $instProp.$instName
        if ($instanceId) {
            $path = "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\$instanceId\MSSQLServer\SuperSocketNetLib\Tcp\IPAll"
            $tcp = Get-ItemProperty $path -ErrorAction Stop
            Write-Output "InstanceId: $instanceId"
            Write-Output "TcpPort: $($tcp.TcpPort)"
            Write-Output "TcpDynamicPorts: $($tcp.TcpDynamicPorts)"
        } else {
            Write-Output "Instance $instName not found. Available:"
            $instProp | Format-List | Out-String | Write-Output
        }
    } -ArgumentList $instanceName -ErrorAction Stop
    $result
} catch {
    Write-Host "WinRM failed: $($_.Exception.Message)"
    Write-Host "Trying reg query..."
    reg query "\\$server\HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL" 2>&1
}
