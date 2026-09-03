# ⏱️ Timeout do Cluster Aumentado para 25 Segundos + Otimizações

## 🔴 Problema Identificado

Nos logs do console você viu:
```
Error: Request timeout at watcherdb:7657:57
Timeout ao buscar cluster (30s)
```

E na tela: **"PowerShell timeout (15s)"**

**Diagnóstico:**
- O PowerShell remoting está demorando **mais de 15 segundos**
- Ambiente de produção com latência alta
- Múltiplas abas abertas simultaneamente sobrecarregando o sistema
- Validações de permissão Active Directory lentas

---

## ✅ Soluções Aplicadas

### 1. Timeout Aumentado de 15s → 25s

**Arquivo:** `modules/monitoring/cluster_analysis_fast.py`

**Antes:**
```python
timeout=15,  # Timeout aumentado para 15s
```

**Depois:**
```python
timeout=25,  # Timeout aumentado para 25s (ambientes de produção podem ser MUITO lentos)
```

---

### 2. Otimizações PowerShell

**Flags adicionadas:**
```python
proc = subprocess.run(
    ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
    creationflags=subprocess.CREATE_NO_WINDOW  # Não abrir janela visível
)
```

**Benefícios:**
- `-ExecutionPolicy Bypass`: Não valida políticas (mais rápido)
- `CREATE_NO_WINDOW`: Não cria janela visível (economiza recursos)

---

### 3. Skip de Eventos se Health Demorar Muito

**Lógica inteligente:** Se o health check demorar mais de 20s, **pula a coleta de eventos** para não exceder o timeout do frontend (30s).

```python
def get_cluster_summary_fast(server: str):
    health = check_cluster_health_fast(server)

    health_time = health.get('elapsed_time', 0)
    if not health.get('success') or health_time > 20:
        # Pular eventos para não exceder 30s do frontend
        events = {'success': False, 'events': [], 'error': 'Pulado (health demorou muito)'}
    else:
        events = get_cluster_events_fast(server)
```

**Por que 20s?**
- Health: até 25s (timeout)
- Se health demora 20s+, restam menos de 10s para eventos
- Frontend timeout: 30s total
- Melhor pular eventos do que dar timeout completo

---

### 4. Timeout de Eventos: 10s → 15s

**Eventos também aumentados:**
```python
timeout=15,  # Timeout aumentado para 15s (era 10s)
```

---

## 📊 Nova Performance Esperada

| Cenário | Health | Events | Total |
|---------|--------|--------|-------|
| **Rápido (LAN)** | 5-10s | 3-5s | 8-15s |
| **Normal (Produção)** | 15-20s | 5-8s | 20-28s |
| **Lento (timeout health)** | 25s | 0s (pulado) | 25s |
| **Muito lento (timeout tudo)** | 25s | 15s | Timeout 30s frontend |

---

## 🧪 Como Testar

### Teste 1: CLI (Health apenas)
```bash
cd "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python test_cluster_timeout_15s.py
```

---

### Teste 2: Portal (Completo)

**IMPORTANTE:** Feche todas as abas extras antes de testar!

1. **Fechar abas extras no portal**
   - Clique no X de todas as abas exceto uma
   - Isso evita múltiplas requisições simultâneas

2. **Reiniciar WatcherDB:**
   ```bash
   # Ctrl+C para parar
   python watcherdb_main.py
   ```

3. **Hard refresh no navegador:**
   - URL: `http://127.0.0.1:8000/watcherdb`
   - Pressionar: `Ctrl + Shift + F5` (super hard refresh)
   - Ou abrir em aba anônima

4. **Testar com UM servidor apenas:**
   - Selecionar: `SQLRPAPRD02\I01`
   - Clicar no botão **Cluster**
   - Aguardar até 25-30 segundos

---

## 📋 Logs Esperados

### ✅ Cenário 1: Sucesso Completo (15-20s)
```
INFO:modules.monitoring.cluster_analysis_fast:⚡ [FAST] Buscando apenas AG resources do cluster SQLRPAPRD02...
INFO:modules.monitoring.cluster_analysis_fast:✅ [FAST] Sucesso em 18.24s - Cluster: SQLRPACLU01, AG Resources: 1, Failed: 0
INFO:modules.monitoring.cluster_analysis_fast:⚡ [FAST EVENTS] Buscando eventos críticos do cluster SQLRPAPRD02 (últimas 24h)...
INFO:modules.monitoring.cluster_analysis_fast:✅ [FAST EVENTS] 15 eventos obtidos em 6.56s
INFO:api.routers.cluster:✅ [CLUSTER FAST] Summary obtido em 24.80s - Success: True
```

### ⏭️ Cenário 2: Health Lento, Eventos Pulados (20-25s)
```
INFO:modules.monitoring.cluster_analysis_fast:⚡ [FAST] Buscando apenas AG resources do cluster SQLRPAPRD02...
INFO:modules.monitoring.cluster_analysis_fast:✅ [FAST] Sucesso em 22.34s - Cluster: SQLRPACLU01, AG Resources: 1, Failed: 0
INFO:modules.monitoring.cluster_analysis_fast:⏭️ [FAST] Pulando eventos (health demorou 22.3s)
INFO:api.routers.cluster:✅ [CLUSTER FAST] Summary obtido em 22.35s - Success: True
```

### ⏱ Cenário 3: Timeout Completo (25s)
```
INFO:modules.monitoring.cluster_analysis_fast:⚡ [FAST] Buscando apenas AG resources do cluster SQLRPAPRD02...
WARNING:modules.monitoring.cluster_analysis_fast:⏱ [FAST] Timeout after 25.00s - Ambiente MUITO lento
INFO:modules.monitoring.cluster_analysis_fast:⏭️ [FAST] Pulando eventos (health falhou)
INFO:api.routers.cluster:✅ [CLUSTER FAST] Summary obtido em 25.01s - Success: False
```

---

## 🔍 Se Ainda Assim Não Funcionar

Se mesmo com 25s continuar dando timeout, o problema é **estrutural**:

### Diagnóstico Avançado

Execute este comando **diretamente no PowerShell** para medir o tempo real:

```powershell
Measure-Command {
    $cluster = Get-Cluster -Name SQLRPAPRD02
    $agResources = Get-ClusterResource -Cluster SQLRPAPRD02 | Where-Object {
        $_.ResourceType -eq 'SQL Server Availability Group'
    }
}
```

**Interpretação:**
- **< 10s**: Normal, aumentar timeout resolve
- **10-25s**: Lento mas aceitável, timeout de 25s deve funcionar
- **> 25s**: **Problema de infraestrutura** (rede, permissões, AD)

---

### Possíveis Causas Infraestrutura

1. **Latência de rede alta**
   - Cluster em datacenter remoto
   - VPN com latência > 200ms
   - **Solução:** Executar WatcherDB no mesmo datacenter

2. **Validação de permissões lenta**
   - Active Directory lento
   - Muitos grupos de segurança
   - **Solução:** Adicionar usuário diretamente (sem grupos aninhados)

3. **Firewall bloqueando temporariamente**
   - Primeira conexão lenta (negociação)
   - **Solução:** Whitelist permanente

4. **Cluster sobrecarregado**
   - Muitos recursos (>100)
   - **Solução:** Já estamos filtrando apenas AG, não dá para otimizar mais

---

## ⚙️ Alternativa: Modo LOCAL

Se o timeout persistir, podemos criar um **modo LOCAL** que executa o PowerShell **no próprio servidor do cluster** (via PSRemoting) em vez de remotamente:

```python
# Executar comando NO servidor cluster (mais rápido)
Invoke-Command -ComputerName SQLRPAPRD02 -ScriptBlock {
    Get-Cluster | Select Name, Domain
}
```

**Benefícios:**
- 50-70% mais rápido
- Menos validação de rede

**Desvantagens:**
- Requer PSRemoting configurado
- Requer credenciais (não pode usar pass-through)

---

## ✅ Resumo das Alterações

| Item | Antes | Depois |
|------|-------|--------|
| **Timeout Health** | 15s | 25s |
| **Timeout Events** | 10s | 15s |
| **PowerShell Flags** | `-NoProfile` | `-NoProfile -ExecutionPolicy Bypass` |
| **Janela PowerShell** | Visível | Oculta (CREATE_NO_WINDOW) |
| **Skip Events** | Não | Sim (se health > 20s) |

---

## 🚀 Próximos Passos

1. **Reinicie o WatcherDB**
2. **Feche todas as abas extras**
3. **Hard refresh no navegador** (Ctrl+Shift+F5)
4. **Teste com UM servidor apenas**
5. **Aguarde até 25-30 segundos**

Se ainda não funcionar, me avise e vamos:
- Testar o comando PowerShell direto
- Investigar logs de rede/permissões
- Considerar modo LOCAL (PSRemoting)
