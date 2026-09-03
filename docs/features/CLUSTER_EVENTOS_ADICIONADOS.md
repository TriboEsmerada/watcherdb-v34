# 📋 Eventos do Cluster Adicionados ao Modo FAST

## 🎯 Problema

No modo FAST, os eventos do cluster **não eram coletados**:
```python
'events': {'success': False, 'events': [], 'error': 'Events not collected in FAST mode'}
```

Resultado: A seção de eventos no portal ficava vazia.

---

## ✅ Solução Implementada

### Nova Função: `get_cluster_events_fast()`

**Arquivo:** `modules/monitoring/cluster_analysis_fast.py` (linha ~131)

**Características:**
- ✅ Coleta apenas eventos **Error** e **Warning** (não Info/Verbose)
- ✅ Apenas das **últimas 24 horas**
- ✅ Máximo de **50 eventos** (configurável)
- ✅ Timeout de **10 segundos**
- ✅ Log: `Microsoft-Windows-FailoverClustering/Operational`

**Campos coletados por evento:**
- `timestamp`: Data/hora do evento
- `event_id`: ID do evento
- `level`: Nível (Error, Warning)
- `message`: Mensagem do evento

---

## 🔧 Alterações no Código

### Antes:
```python
def get_cluster_summary_fast(server: str) -> Dict[str, Any]:
    health = check_cluster_health_fast(server)

    return {
        'health': health,
        'events': {'success': False, 'events': [], 'error': 'Events not collected in FAST mode'},
        'timestamp': datetime.now().isoformat()
    }
```

### Depois:
```python
def get_cluster_events_fast(server: str, max_events: int = 50) -> Dict[str, Any]:
    """Coleta eventos críticos (Error + Warning) das últimas 24h"""
    # ... implementação com Get-WinEvent ...

def get_cluster_summary_fast(server: str) -> Dict[str, Any]:
    health = check_cluster_health_fast(server)
    events = get_cluster_events_fast(server, max_events=50)  # ✅ AGORA COLETA EVENTOS

    return {
        'health': health,
        'events': events,  # ✅ Eventos reais
        'timestamp': datetime.now().isoformat()
    }
```

---

## 📊 Performance

| Operação | Tempo Esperado |
|----------|----------------|
| **Health (cluster + AG resources)** | 10-15s |
| **Events (últimas 24h)** | 3-5s |
| **Total (health + events)** | 13-20s |

**Nota:** As chamadas são **sequenciais** (não paralelas) para evitar sobrecarregar o servidor remoto.

---

## 🧪 Como Testar

### Teste 1: Script CLI (Apenas eventos)
```bash
cd "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python test_cluster_events.py
```

**Resultado esperado:**
```
✅ [FAST EVENTS] 15 eventos obtidos em 4.23s
```

---

### Teste 2: Portal Web

1. **Reiniciar WatcherDB:**
   ```bash
   # Ctrl+C para parar
   python watcherdb_main.py
   ```

2. **Abrir portal e hard refresh:**
   - URL: `http://127.0.0.1:8000/watcherdb`
   - Pressionar: `Ctrl + Shift + R`

3. **Clicar em servidor com cluster:**
   - Exemplo: `SQLRPAPRD02\I01`

4. **Clicar no botão "Cluster"**

5. **Aguardar 15-20 segundos** (health + events)

**Logs esperados:**
```
INFO:api.routers.cluster:📡 [CLUSTER FAST] Iniciando get_cluster_summary para SQLRPAPRD02
INFO:modules.monitoring.cluster_analysis_fast:⚡ [FAST] Buscando apenas AG resources do cluster SQLRPAPRD02...
INFO:modules.monitoring.cluster_analysis_fast:✅ [FAST] Sucesso em 12.34s - Cluster: SQLRPAPRD02, AG Resources: 1, Failed: 0
INFO:modules.monitoring.cluster_analysis_fast:⚡ [FAST EVENTS] Buscando eventos críticos do cluster SQLRPAPRD02 (últimas 24h)...
INFO:modules.monitoring.cluster_analysis_fast:✅ [FAST EVENTS] 15 eventos obtidos em 4.56s
INFO:api.routers.cluster:✅ [CLUSTER FAST] Summary obtido em 16.90s - Success: True
```

**Na tela do portal:**
- ✅ Seção "Cluster Events" agora mostra eventos
- ✅ Tabela com: Data, Event ID, Level, Message
- ✅ Filtrado apenas Error e Warning

---

## 🔍 Script PowerShell Utilizado

```powershell
$after = (Get-Date).AddHours(-24)
$events = Get-WinEvent -ComputerName SQLADSPRD002 -FilterHashtable @{
    LogName = 'Microsoft-Windows-FailoverClustering/Operational'
    Level = @(2, 3)  # 2=Error, 3=Warning
    StartTime = $after
} -MaxEvents 50 -ErrorAction SilentlyContinue
```

**Por que é rápido:**
- `FilterHashtable` é mais rápido que `-FilterXPath`
- Apenas 2 níveis (Error + Warning)
- Apenas 24 horas (não todo o log)
- Máximo 50 eventos (não milhares)
- Timeout de 10s

---

## ⚠️ Possíveis Erros

### Erro 1: "Access Denied"
**Causa:** Usuário não tem permissão para ler Event Log remoto
**Solução:** Adicionar usuário ao grupo "Event Log Readers" no servidor cluster

### Erro 2: "Timeout (10s)"
**Causa:** Servidor remoto muito lento ou Event Log muito grande
**Solução:** Aumentar timeout em `cluster_analysis_fast.py:178`:
```python
timeout=15,  # Aumentar de 10 para 15
```

### Erro 3: "Log não encontrado"
**Causa:** Log `Microsoft-Windows-FailoverClustering/Operational` não existe
**Solução:** Verificar se o servidor tem Failover Clustering instalado

---

## 📈 Comparação Modo FAST vs FULL

| Feature | FAST Mode | FULL Mode |
|---------|-----------|-----------|
| **Cluster Name** | ✅ | ✅ |
| **Cluster Domain** | ✅ | ✅ |
| **Nodes** | ❌ | ✅ |
| **All Resources** | ❌ | ✅ |
| **AG Resources** | ✅ | ✅ |
| **Quorum** | ❌ | ✅ |
| **Events (24h)** | ✅ **NOVO!** | ✅ (7 dias) |
| **Tempo** | 13-20s | 25-40s |

---

## ✅ Resumo

- ✅ **Eventos agora são coletados no modo FAST**
- ✅ **Apenas eventos críticos** (Error + Warning)
- ✅ **Últimas 24 horas** (não sobrecarrega)
- ✅ **Timeout de 10s** (rápido)
- ✅ **Máximo 50 eventos** (não trava o frontend)

**Próximo passo:** Reinicie o WatcherDB e teste no portal!
