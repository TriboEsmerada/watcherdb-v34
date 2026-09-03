# Teste do Cluster Fallback - SQLHDSPRD407

## Status da Implementação

✅ **Concluído**:
- Módulo de cluster separado ([modules/monitoring/cluster_analysis.py](../modules/monitoring/cluster_analysis.py))
- API endpoints ([api/routers/cluster.py](../api/routers/cluster.py))
- Fallback no Always On quando SQL falha
- Aba dedicada "Cluster" no portal
- Timeout aumentado para 10s (era 5s)

## O que Mudou no Último Teste

**Antes**:
```
WARNING:modules.monitoring.cluster_analysis:⚠️ Cluster health check timeout for SQLHDSPRD407
```
- Timeout: 5 segundos (muito curto para produção)

**Agora**:
- Timeout: **10 segundos** (linha 1192 de watcherdb_alwayson_check.py)
- Melhor chance de sucesso em servidores lentos

---

## Como Testar

### 1. Reinicie o WatcherDB

```bash
# Parar o servidor (Ctrl+C)
# Iniciar novamente
python watcherdb_main.py
```

### 2. Teste Aba "Always On"

1. **Abra o portal**: `http://127.0.0.1:8000/watcherdb`
2. **Selecione** servidor `SQLHDSPRD407\I01`
3. **Clique na aba "Always On"** (não Overview!)
4. **Aguarde** ~10-15 segundos

**Resultado Esperado A - Cluster OK**:
```
┌─────────────────────────────────────────┐
│ ⏱ Timeout ao Carregar Always On        │
├─────────────────────────────────────────┤
│ A conexão está demorando...             │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ ✓ Cluster SQLCDSPRD407              │ │
│ │ 1 AG resource(s) - Todos online     │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**Resultado Esperado B - Cluster com Problema**:
```
┌─────────────────────────────────────────┐
│ ⏱ Timeout ao Carregar Always On        │
├─────────────────────────────────────────┤
│ A conexão está demorando...             │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 🖥 Problema Detectado no Cluster    │ │
│ │                                     │ │
│ │ 1 AG resource(s) com problema       │ │
│ │ • Resource 'SQLAGSPRD407' is Failed │ │
│ │   (expected Online)                 │ │
│ │                                     │ │
│ │ ℹ Cluster: SQLCDSPRD407             │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**Resultado C - Timeout Novamente** (mesmo com 10s):
```
┌─────────────────────────────────────────┐
│ ⏱ Timeout ao Carregar Always On        │
├─────────────────────────────────────────┤
│ A conexão está demorando...             │
│ (sem card de cluster - timeout)         │
└─────────────────────────────────────────┘
```

### 3. Teste Aba "Cluster"

1. **Selecione** servidor `SQLHDSPRD407\I01`
2. **Clique na aba "Cluster"** (novo botão na navegação!)
3. **Aguarde** ~10-15 segundos

**Resultado Esperado - Dashboard Completo**:
```
┌────────────────────────────────────────────────────┐
│ 🌐 Windows Failover Cluster                        │
│ SQLHDSPRD407\I01                                   │
├────────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────────┐ │
│ │ 🌐 Cluster: SQLCDSPRD407                       │ │
│ │ Nodes: 2 | Recursos: 15 | AG Resources: 1     │ │
│ └────────────────────────────────────────────────┘ │
│                                                    │
│ ┌────────────────────────────────────────────────┐ │
│ │ ⚠ Recursos com Problema (1)                   │ │
│ │ • SQLAGSPRD407 (SQL Server Availability Group)│ │
│ │   Estado: Failed | Node: SQLHDSPRD407         │ │
│ └────────────────────────────────────────────────┘ │
│                                                    │
│ ┌────────────────────────────────────────────────┐ │
│ │ 🖥 Cluster Nodes (2)                           │ │
│ │ ✓ SQLHDSPRD407 - Up                            │ │
│ │ ✓ SQLHDSPRD408 - Up                            │ │
│ └────────────────────────────────────────────────┘ │
│                                                    │
│ ┌────────────────────────────────────────────────┐ │
│ │ 📝 Eventos Recentes (24h)                      │ │
│ │ Critical: 2 | Errors: 5 | Warnings: 12        │ │
│ │ • [Error] 14/01/2026 12:25:30                 │ │
│ │   Cluster resource 'SQLAGSPRD407' failed...   │ │
│ └────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

---

## Logs Esperados (Sucesso)

```
INFO:api.routers.alwayson:🔍 Verificando Always On para server_id: SQLHDSPRD407_I01
INFO:api.routers.alwayson:✅ Servidor SQLHDSPRD407_I01 encontrado no inventory Always On
ERROR:modules.monitoring.monitoring:Connection error to SQLHDSPRD407_I01_master: SSPI context error
WARNING:api.routers.alwayson:⚠️ Timeout/erro ao obter status AG de SQLHDSPRD407_I01: Conexão falhou
INFO:api.routers.alwayson:🔄 Tentando fallback via PowerShell para verificar cluster de SQLHDSPRD407...
INFO:modules.monitoring.cluster_analysis:✅ Cluster check: SQLCDSPRD407 - 2 nodes, 15 resources, 1 failed
INFO:api.routers.alwayson:✅ Cluster health via PowerShell OK: 1 recursos com problema
```

**Indicador de Sucesso**: Linha `INFO:modules.monitoring.cluster_analysis:✅ Cluster check:`

---

## Troubleshooting

### Problema 1: Timeout Continua (mesmo com 10s)

**Possíveis Causas**:
1. PowerShell Remoting não habilitado em SQLHDSPRD407
2. Firewall bloqueando
3. Servidor muito lento para responder em 10s

**Solução**:
- Testar manualmente no PowerShell:
```powershell
Get-Cluster -Name SQLHDSPRD407
Get-ClusterResource -Cluster SQLHDSPRD407 | Where-Object {$_.ResourceType -eq 'SQL Server Availability Group'}
```

### Problema 2: Permissões Negadas

**Erro**: `PowerShell error: Access is denied`

**Solução**:
- Usuário precisa ter permissões de Cluster Administrator
- Ou adicionar usuário ao grupo local "Cluster Operators" no servidor

### Problema 3: Cluster Não Encontrado

**Erro**: `PowerShell error: Cluster SQLHDSPRD407 was not found`

**Possível Causa**:
- Servidor não é node de cluster
- Nome do cluster está errado

**Solução**:
- Verificar se servidor realmente tem cluster instalado
- Verificar nome correto: pode ser SQLCDSPRD407, SQLCLUSTERPRD407, etc.

---

## Diagnost de Rede

Para testar manualmente se PowerShell remoting funciona:

```powershell
# Teste 1: Conectividade básica
Test-NetConnection -ComputerName SQLHDSPRD407 -Port 5985

# Teste 2: PowerShell Remoting
Enter-PSSession -ComputerName SQLHDSPRD407

# Teste 3: Cluster cmdlets remotos
Get-Cluster -Name SQLHDSPRD407
```

Se todos funcionarem manualmente, o WatcherDB também deve funcionar.

---

## Próximos Passos (Se Timeout Persistir)

1. **Aumentar timeout ainda mais**: 15s ou 20s
   - Editar `watcherdb_alwayson_check.py` linha 1192
   - Mudar `timeout=10` para `timeout=15` ou `timeout=20`

2. **Cache mais agressivo**: Salvar resultado por 10 minutos
   - Evitar chamadas repetidas que demoram

3. **Modo assíncrono**: Processar em background
   - Não bloquear frontend enquanto aguarda

4. **Fallback para WMI**: Se PowerShell falhar
   - Similar ao que já existe para Services/Memory
