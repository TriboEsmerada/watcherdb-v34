# Onde Ver Informações do Cluster no WatcherDB

## 🎯 Guia Rápido

### ❌ NÃO está aqui:
- ~~Overview / KPIs~~ → Cluster **não** aparece no Overview

### ✅ SIM está aqui:

#### 1. **Aba "Always On"** (quando SQL falha)
```
Portal → Selecionar Servidor → Clicar em "Always On"
```

**Quando aparece?**
- Quando a conexão SQL **falha** (SSPI error, timeout, etc.)
- O sistema automaticamente tenta PowerShell cluster check
- Se cluster tiver problemas, exibe um **card vermelho** de alerta

**Visual esperado:**
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

---

#### 2. **Aba "Cluster"** (dedicada)
```
Portal → Selecionar Servidor → Clicar em "Cluster"
```

**Sempre disponível** (não precisa SQL falhar)

**Conteúdo completo:**
- Nome do cluster e domínio
- Nodes (Up/Down)
- Recursos (Online/Offline/Failed)
- Recursos de AG especificamente
- Configuração de Quorum
- Eventos recentes (últimas 24h)

**Visual esperado:**
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
└────────────────────────────────────────────────────┘
```

---

## 📋 Passo a Passo para Teste

### Cenário: SQLHDSPRD407 com Cluster Offline

**Passo 1: Reiniciar WatcherDB**
```bash
# Parar servidor (Ctrl+C)
# Iniciar novamente
python watcherdb_main.py
```

**Passo 2: Abrir o Portal**
```
http://127.0.0.1:8000/watcherdb
```

**Passo 3: Selecionar Servidor**
- Na lista de servidores, clicar em `SQLHDSPRD407\I01`

**Passo 4: Testar Always On Tab**
1. Clicar no botão **"Always On"** (terceiro botão na navegação)
2. Aguardar 10-15 segundos
3. Observar se aparece card vermelho com alerta de cluster

**Passo 5: Testar Cluster Tab**
1. Clicar no botão **"Cluster"** (quarto botão na navegação)
2. Aguardar 10-15 segundos
3. Ver dashboard completo do cluster

---

## 🔍 Logs para Acompanhar

### Sucesso (Cluster OK):
```
INFO:api.routers.alwayson:🔍 Verificando Always On para server_id: SQLHDSPRD407_I01
ERROR:modules.monitoring.monitoring:Connection error to SQLHDSPRD407_I01_master: SSPI context error
WARNING:api.routers.alwayson:⚠️ Timeout/erro ao obter status AG de SQLHDSPRD407_I01: Conexão falhou
INFO:api.routers.alwayson:🔄 Tentando fallback via PowerShell para verificar cluster de SQLHDSPRD407...
INFO:modules.monitoring.cluster_analysis:✅ Cluster check: SQLCDSPRD407 - 2 nodes, 15 resources, 1 failed
INFO:api.routers.alwayson:✅ Cluster health via PowerShell OK: 1 recursos com problema
```

### Timeout (ainda não funcionou):
```
WARNING:modules.monitoring.cluster_analysis:⚠️ Cluster health check timeout for SQLHDSPRD407
WARNING:api.routers.alwayson:⚠️ Cluster health via PowerShell falhou: PowerShell timeout (10s)
```

---

## ⚠️ Se Continuar com Timeout

### Opção 1: Aumentar timeout para 15 segundos
Editar [watcherdb_alwayson_check.py:1192](../modules/monitoring/watcherdb_alwayson_check.py#L1192):
```python
# ANTES:
full_result = check_cluster_health(server, timeout=10)

# DEPOIS:
full_result = check_cluster_health(server, timeout=15)
```

### Opção 2: Testar manualmente PowerShell
```powershell
# Teste de conectividade
Test-NetConnection -ComputerName SQLHDSPRD407 -Port 5985

# Teste de comandos cluster
Get-Cluster -Name SQLHDSPRD407
Get-ClusterNode -Cluster SQLHDSPRD407
Get-ClusterResource -Cluster SQLHDSPRD407

# Se funcionar manualmente, o problema é só timeout
# Se falhar, verificar:
# - PowerShell Remoting habilitado
# - Permissões de cluster
# - Firewall
```

---

## 📊 Resumo Visual

| Localização | Quando Aparece | Tipo de Info |
|------------|---------------|-------------|
| **Always On tab** | Quando SQL falha | ⚠️ Alerta de problemas no cluster |
| **Cluster tab** | Sempre | 📊 Dashboard completo do cluster |
| ~~Overview~~ | ~~Nunca~~ | ~~Cluster não está no Overview~~ |

---

## ✅ Implementação Completa

- ✅ Módulo cluster separado ([cluster_analysis.py](../modules/monitoring/cluster_analysis.py))
- ✅ API endpoints ([cluster.py](../api/routers/cluster.py))
- ✅ Fallback no Always On quando SQL falha
- ✅ Aba dedicada "Cluster" no portal
- ✅ Timeout de 10 segundos (era 5s)
- ✅ Documentação de testes ([TESTE_CLUSTER_FALLBACK.md](TESTE_CLUSTER_FALLBACK.md))
- ✅ Documentação do módulo ([CLUSTER_MODULE.md](CLUSTER_MODULE.md))
