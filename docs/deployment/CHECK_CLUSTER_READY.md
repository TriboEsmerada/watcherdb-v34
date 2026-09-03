# ✅ Checklist: Cluster FAST Mode Pronto

## 🔄 PASSO 1: Reiniciar WatcherDB

### Parar o servidor atual
No terminal do WatcherDB:
```
Ctrl+C
```

### Iniciar novamente
```bash
cd "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python watcherdb_main.py
```

### ✅ Verificar logs de inicialização
Procure por:
```
✅ Router Cluster carregado: /api/cluster com 3 rotas
```

---

## 🧪 PASSO 2: Testar API Diretamente

### Teste 1: Verificar endpoint existe
```bash
curl http://127.0.0.1:8000/api/cluster/server/SQLRPAPRD02_I01/summary?mode=fast
```

**Resultado esperado:** JSON com dados do cluster (ou erro explicando o problema)
**Não esperado:** `{"detail":"Not Found"}`

### Teste 2: Verificar modo FAST funciona
```bash
cd "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python test_cluster_fast.py
```

**Tempo esperado:** ~8-10 segundos
**Resultado esperado:** `Success: True` ou timeout explicado

---

## 🌐 PASSO 3: Testar no Portal

### 3.1 Abrir portal
```
http://127.0.0.1:8000/watcherdb
```

### 3.2 Selecionar servidor
- Clicar em `SQLRPAPRD02\I01` (ou outro com cluster)

### 3.3 Abrir aba Cluster
- Clicar no botão **"Cluster"** na navegação
- **Aguardar 8-10 segundos** (não vai mais travar indefinidamente!)

### 3.4 Verificar resultado

#### ✅ SUCESSO:
```
┌─────────────────────────────────────────┐
│ 🌐 Windows Failover Cluster             │
│ SQLRPAPRD02\I01                         │
├─────────────────────────────────────────┤
│ ℹ️ Modo FAST (apenas AG resources)     │
├─────────────────────────────────────────┤
│ Cluster: SQLCRPAPRD02                   │
│ AG Resources: 1                         │
└─────────────────────────────────────────┘
```

#### ⏱ TIMEOUT (esperado em ambiente lento):
```
┌─────────────────────────────────────────┐
│ ⏱ Timeout ao carregar cluster (30s)    │
│                                         │
│ O servidor está demorando muito...      │
└─────────────────────────────────────────┘
```

---

## 📊 PASSO 4: Verificar Logs no Terminal

### Logs esperados (SUCESSO COM EVENTOS):
```
INFO:api.routers.cluster:📡 [CLUSTER FAST] Iniciando get_cluster_summary para SQLRPAPRD02
INFO:modules.monitoring.cluster_analysis_fast:⚡ [FAST] Buscando apenas AG resources do cluster SQLRPAPRD02...
INFO:modules.monitoring.cluster_analysis_fast:✅ [FAST] Sucesso em 12.24s - Cluster: SQLRPAPRD02, AG Resources: 1, Failed: 0
INFO:modules.monitoring.cluster_analysis_fast:⚡ [FAST EVENTS] Buscando eventos críticos do cluster SQLRPAPRD02 (últimas 24h)...
INFO:modules.monitoring.cluster_analysis_fast:✅ [FAST EVENTS] 15 eventos obtidos em 4.56s
INFO:api.routers.cluster:✅ [CLUSTER FAST] Summary obtido em 16.80s - Success: True
```

### Logs esperados (TIMEOUT):
```
INFO:api.routers.cluster:📡 [CLUSTER FAST] Iniciando get_cluster_summary para SQLRPAPRD02
INFO:modules.monitoring.cluster_analysis_fast:⚡ [FAST] Buscando apenas AG resources do cluster SQLRPAPRD02...
WARNING:modules.monitoring.cluster_analysis_fast:⏱ [FAST] Timeout after 8.00s
INFO:api.routers.cluster:✅ [CLUSTER FAST] Summary obtido em 8.01s - Success: False
```

---

## 🐛 Troubleshooting

### Problema 1: `{"detail":"Not Found"}`
**Causa:** Servidor não foi reiniciado ou router não carregou
**Solução:**
1. Parar WatcherDB (Ctrl+C)
2. Iniciar novamente
3. Verificar logs de inicialização

### Problema 2: Ainda trava indefinidamente
**Causa:** Frontend não foi recarregado com as mudanças
**Solução:**
1. No navegador, pressionar `Ctrl+Shift+R` (hard refresh)
2. Ou abrir em aba anônima

### Problema 3: Timeout após 8s
**Causa:** PowerShell remoting é lento neste ambiente (normal)
**Solução:**
- **Aceitar os 8-10s** (é o melhor que conseguimos com PowerShell remoto)
- Cache de 5 minutos vai evitar recarregar frequentemente
- Após primeira carga, dados ficam em cache

### Problema 4: Erro de permissão PowerShell
**Causa:** Usuário não tem acesso ao cluster remoto
**Solução:**
1. Testar manualmente: `Get-Cluster -Name SQLRPAPRD02`
2. Se falhar, problema de permissões/rede
3. Verificar com administrador de sistemas

---

## 📈 Performance Esperada

| Métrica | Valor |
|---------|-------|
| **Health check (cluster + AG)** | 10-15 segundos |
| **Events (últimas 24h)** | 3-5 segundos |
| **Total (primeira carga)** | 13-20 segundos |
| **Cargas seguintes (cache)** | Instantâneo (<100ms) |
| **Cache expira** | Após 5 minutos |
| **Timeout frontend** | 30 segundos (não trava mais!) |

---

## ✅ Conclusão

Se após reiniciar você ver:
- ✅ Logs `[CLUSTER FAST]` e `[FAST EVENTS]` no terminal
- ✅ Dados do cluster aparecem em 13-20s no portal
- ✅ **Eventos do cluster aparecem na seção "Cluster Events"**
- ✅ Indicador "Modo FAST" visível
- ✅ Cache funciona (segunda carga instantânea)

**Então está tudo funcionando corretamente!** 🎉

Os 13-20 segundos são **normais** para PowerShell remoting em ambientes de produção:
- 10-15s para health check (cluster + AG resources)
- 3-5s para eventos (últimas 24h, apenas Error e Warning)
