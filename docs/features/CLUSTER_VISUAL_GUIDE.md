# Guia Visual: Onde Encontrar Informações de Cluster

## 🚀 Acesso Rápido

### URL Base
```
http://127.0.0.1:8000/watcherdb
```

---

## 📍 Navegação Passo a Passo

### Passo 1: Selecionar Servidor
```
┌────────────────────────────────────────────────┐
│  WatcherDB - Lista de Servidores              │
├────────────────────────────────────────────────┤
│  🔍 Buscar: [________________]                 │
│                                                │
│  📁 Produção                                   │
│    ┌──────────────────────────────────────┐   │
│    │ 🟢 SQLHDSPRD407\I01                  │◄─ CLICAR AQUI
│    │    Always On: PRIMARY                 │   │
│    │    CPU: 31% | Memory: 45 GB          │   │
│    └──────────────────────────────────────┘   │
│                                                │
│    ┌──────────────────────────────────────┐   │
│    │ 🟢 SQLHDSPRD408\I01                  │   │
│    └──────────────────────────────────────┘   │
└────────────────────────────────────────────────┘
```

---

### Passo 2: Dashboard do Servidor (Overview)
```
┌──────────────────────────────────────────────────────────────────────────┐
│  SQLHDSPRD407\I01                                  [⟳ Refresh] [⚙ Config]│
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Navegação:                                                              │
│  ┌──────────┬──────────┬────────────┬────────────┬──────────┬─────────┐ │
│  │ Overview │   CPU    │ Always On  │  Cluster   │  Memory  │  Space  │ │
│  │   ●      │          │            │     ●      │          │         │ │
│  └──────────┴──────────┴────────────┴────────────┴──────────┴─────────┘ │
│     ▲                        ▲            ▲                              │
│     │                        │            │                              │
│   Atual              Alerta aparece aqui │                              │
│                      quando SQL falha     │                              │
│                                           │                              │
│                                    Dashboard completo                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Opção 1: Ver Alerta de Cluster (quando SQL falha)

### Navegação
```
Overview → Always On
```

### Visual (Timeout + Cluster Alert)
```
┌──────────────────────────────────────────────────────────────────────────┐
│  📊 Always On Availability Groups                                        │
│  SQLHDSPRD407\I01                                                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  ⏱ Timeout ao Carregar Always On                                  │ │
│  ├────────────────────────────────────────────────────────────────────┤ │
│  │  A conexão ao SQL Server está demorando mais que 30 segundos...   │ │
│  │                                                                    │ │
│  │  ⚠️ Possíveis causas:                                              │ │
│  │  • Servidor lento ou sobrecarregado                               │ │
│  │  • Problemas de rede ou autenticação (SSPI)                       │ │
│  │  • Instância SQL Server pode estar indisponível                   │ │
│  │                                                                    │ │
│  │  ┌────────────────────────────────────────────────────────────┐   │ │
│  │  │  🖥 Problema Detectado no Cluster                          │◄─ AQUI!
│  │  ├────────────────────────────────────────────────────────────┤   │ │
│  │  │                                                            │   │ │
│  │  │  1 AG resource(s) com problema no cluster                 │   │ │
│  │  │                                                            │   │ │
│  │  │  Detalhes:                                                 │   │ │
│  │  │  • Resource 'SQLAGSPRD407' is Failed (expected Online)    │   │ │
│  │  │                                                            │   │ │
│  │  │  ℹ Cluster: SQLCDSPRD407                                   │   │ │
│  │  │                                                            │   │ │
│  │  └────────────────────────────────────────────────────────────┘   │ │
│  │                                                                    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Quando Aparece?
- ✅ Conexão SQL **falha** (SSPI error, timeout, credential issue)
- ✅ PowerShell cluster check **tem sucesso**
- ✅ Cluster **tem problemas** (recursos Failed/Offline)

### Cores do Card
| Estado | Cor de Fundo | Borda | Ícone |
|--------|-------------|-------|-------|
| **Problema** (Failed/Offline) | `#7f1d1d` (vermelho escuro) | `#ef4444` (vermelho) | 🖥 |
| **OK** (todos Online) | `#064e3b` (verde escuro) | `#10b981` (verde) | ✓ |

---

## 🎯 Opção 2: Ver Dashboard Completo do Cluster

### Navegação
```
Overview → Cluster
```

### Visual (Dashboard Completo)
```
┌──────────────────────────────────────────────────────────────────────────┐
│  🌐 Windows Failover Cluster                                             │
│  SQLHDSPRD407\I01                                                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  🌐 Cluster: SQLCDSPRD407                                          │ │
│  │  Domínio: tapnet.tap.pt                                            │ │
│  │  Nodes: 2 | Recursos: 15 | AG Resources: 1                         │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  ⚠ Recursos com Problema (1)                                      │ │
│  ├────────────────────────────────────────────────────────────────────┤ │
│  │  Nome: SQLAGSPRD407                                                │ │
│  │  Tipo: SQL Server Availability Group                               │ │
│  │  Estado: ❌ Failed                                                  │ │
│  │  Node: SQLHDSPRD407                                                │ │
│  │  Grupo: SQLAGSPRD407                                               │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  🖥 Cluster Nodes (2)                                              │ │
│  ├────────────────────────────────────────────────────────────────────┤ │
│  │  ✓ SQLHDSPRD407 - Up                                               │ │
│  │    Status: Normal                                                  │ │
│  │                                                                    │ │
│  │  ✓ SQLHDSPRD408 - Up                                               │ │
│  │    Status: Normal                                                  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  ⚙ Configuração de Quorum                                          │ │
│  ├────────────────────────────────────────────────────────────────────┤ │
│  │  Tipo: NodeAndFileShareMajority                                    │ │
│  │  Recurso: File Share Witness                                       │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  📝 Eventos Recentes (Últimas 24 horas)                            │ │
│  ├────────────────────────────────────────────────────────────────────┤ │
│  │  Critical: 2 | Errors: 5 | Warnings: 12                            │ │
│  │                                                                    │ │
│  │  🔴 [Error] 2026-01-14 12:25:30                                    │ │
│  │     Event ID: 1069                                                 │ │
│  │     Cluster resource 'SQLAGSPRD407' of type 'SQL Server            │ │
│  │     Availability Group' in clustered role 'SQLAGSPRD407' failed.   │ │
│  │                                                                    │ │
│  │  ⚠️ [Warning] 2026-01-14 11:15:22                                  │ │
│  │     Event ID: 1230                                                 │ │
│  │     Cluster resource 'SQLAGSPRD407' is attempting to come online.  │ │
│  │                                                                    │ │
│  │  ⚠️ [Warning] 2026-01-14 10:45:10                                  │ │
│  │     Event ID: 1205                                                 │ │
│  │     Network connectivity between cluster nodes is degraded.        │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Quando Aparece?
- ✅ Sempre disponível (não precisa SQL falhar)
- ✅ Qualquer servidor que tenha Windows Failover Cluster
- ✅ PowerShell remoting funcionando

---

## ❌ Onde NÃO Procurar

### Overview (Dashboard Principal)
```
┌──────────────────────────────────────────────────────────────────────────┐
│  📊 Overview - SQLHDSPRD407\I01                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │   CPU    │  │  Memory  │  │ Services │  │  Space   │               │
│  │   31%    │  │  45 GB   │  │ Running  │  │  234 GB  │               │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘               │
│                                                                          │
│  🚫 Cluster NÃO aparece aqui no Overview!                               │
│                                                                          │
│  Para ver cluster:                                                       │
│  → Clique na aba "Always On" (se SQL falhou)                            │
│  → Clique na aba "Cluster" (dashboard completo)                         │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Por que não está no Overview?**
- Overview mostra métricas gerais (CPU, Memory, Services, Space)
- Cluster é específico de servidores com Always On/Failover Cluster
- Nem todos os servidores têm cluster
- Mantém Overview limpo e focado

---

## 🔍 Comparação: Always On vs Cluster

| Característica | Always On Tab | Cluster Tab |
|---------------|---------------|-------------|
| **Quando usar** | Monitorar SQL Server AG | Monitorar infraestrutura Windows |
| **Fonte de dados** | SQL Server DMVs | PowerShell / Cluster API |
| **Requer SQL online** | ✅ Sim (com fallback) | ❌ Não |
| **Mostra replicas** | ✅ Sim | ❌ Não |
| **Mostra databases** | ✅ Sim | ❌ Não |
| **Mostra cluster nodes** | ❌ Não (só via fallback) | ✅ Sim |
| **Mostra todos recursos** | ❌ Não | ✅ Sim (15 recursos) |
| **Mostra eventos cluster** | ❌ Não | ✅ Sim (24h) |
| **Mostra quorum** | ❌ Não | ✅ Sim |

### Resumo
- **Always On tab**: Foco em SQL Server Availability Groups
- **Cluster tab**: Foco em Windows Failover Cluster (infraestrutura)
- **Fallback**: Quando SQL falha, Always On mostra alerta com info do cluster

---

## 🧪 Teste Rápido

### Passo 1: Verificar se WatcherDB está rodando
```bash
# Terminal onde iniciou o servidor deve mostrar:
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Passo 2: Abrir no navegador
```
http://127.0.0.1:8000/watcherdb
```

### Passo 3: Selecionar servidor cluster
```
Na lista → Clicar em SQLHDSPRD407\I01
```

### Passo 4: Testar Always On
```
Clicar em botão "Always On" → Aguardar 10-15s → Ver card vermelho/verde
```

### Passo 5: Testar Cluster
```
Clicar em botão "Cluster" → Aguardar 10-15s → Ver dashboard completo
```

---

## 📊 Ícones de Referência

| Ícone | Significado | Onde Aparece |
|-------|-------------|--------------|
| 🖥 | Problema no cluster | Always On tab (card vermelho) |
| ✓ | Cluster OK | Always On tab (card verde) |
| 🌐 | Windows Failover Cluster | Cluster tab (título) |
| ⚠ | Recursos com problema | Cluster tab (seção) |
| 🖥 | Cluster nodes | Cluster tab (seção) |
| ⚙ | Configuração quorum | Cluster tab (seção) |
| 📝 | Eventos recentes | Cluster tab (seção) |
| 🔴 | Error level | Cluster events |
| ⚠️ | Warning level | Cluster events |
| ℹ️ | Info level | Cluster events |

---

## 📞 Troubleshooting Visual

### Problema: "Não vejo o card de cluster"

**Verificar:**
```
1. Está na aba CORRETA?
   ✓ Always On → Card aparece quando SQL falha
   ✓ Cluster → Dashboard sempre disponível
   ✗ Overview → Cluster NÃO aparece aqui

2. Aguardou tempo suficiente?
   ✓ Aguarde 10-15 segundos após clicar na aba

3. Logs mostram sucesso?
   ✓ Verificar console: "✅ Cluster check: SQLCDSPRD407..."
   ✗ Se timeout: Aumentar timeout ou verificar rede
```

### Problema: "Card não tem dados"

**Verificar PowerShell manualmente:**
```powershell
# No servidor WatcherDB
Get-Cluster -Name SQLHDSPRD407

# Se funcionar → Timeout muito curto (aumentar)
# Se falhar → Problema de rede/permissões
```

---

## ✅ Checklist de Verificação

- [ ] WatcherDB iniciado e rodando
- [ ] Abriu `http://127.0.0.1:8000/watcherdb`
- [ ] Selecionou servidor `SQLHDSPRD407\I01`
- [ ] Clicou na aba **"Always On"** (não Overview)
- [ ] Aguardou 10-15 segundos
- [ ] Viu card de cluster (vermelho ou verde)
- [ ] Clicou na aba **"Cluster"**
- [ ] Viu dashboard completo do cluster

---

**Última atualização:** 2026-01-14
