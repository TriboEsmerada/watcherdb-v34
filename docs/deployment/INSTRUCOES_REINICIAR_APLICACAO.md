# INSTRUCOES: REINICIAR APLICACAO

**Data:** 2025-12-10
**Status:** ✅ Scripts criados e testados - AGUARDANDO REINICIO

---

## POR QUE PRECISA REINICIAR?

A aplicacao uvicorn esta rodando mas nao carregou os novos scripts:
- `filegroup_interactive_report_v5_watcherdb.py` ✅ Criado e testado
- `filegroup_interactive_report_v5_lite.py` ✅ Criado
- `filegroup_interactive_report_v5.py` ✅ Criado
- `modules/analytics/predictive_analysis.py` ✅ Modificado

**Sintoma:** Dashboard ainda mostra erro `{"success":false,"error":"Falha na execucao: "}`

---

## PASSO 1: PARAR APLICACAO ATUAL

### Opcao A: Via Terminal (RECOMENDADO)

Se voce tiver o terminal onde o uvicorn esta rodando:

1. Va ate o terminal/cmd onde esta rodando `uvicorn`
2. Pressione `Ctrl+C`
3. Aguarde a mensagem: `Shutting down` ou `Application shutdown complete`

### Opcao B: Via Processo (se nao encontrar o terminal)

```bash
# Matar processo pela porta
taskkill /F /PID 45356
```

**OU** use o Task Manager (Gerenciador de Tarefas):
1. Abra Task Manager (`Ctrl+Shift+Esc`)
2. Aba "Details" ou "Detalhes"
3. Procure processo Python com PID `45356`
4. Clique com botao direito → "End Task" ou "Finalizar Tarefa"

---

## PASSO 2: REINICIAR APLICACAO

### Abrir Terminal

1. Pressione `Win+R`
2. Digite: `cmd`
3. Pressione Enter

### Navegar ate Diretorio

```bash
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
```

### Iniciar Uvicorn

```bash
python -m uvicorn watcherdb_intelligence:app --reload --port 8000
```

### Aguardar Mensagens

Voce deve ver algo como:

```
INFO:     Will watch for changes in these directories: ['C:\\Users\\...\\WATCHERDB_DEV']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [XXXX] using WatchFiles
INFO:     Started server process [YYYY]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Script de analise preditiva carregado: filegroup_interactive_report_v5_watcherdb.py
```

**IMPORTANTE:** A ultima linha deve mostrar: `filegroup_interactive_report_v5_watcherdb.py`

---

## PASSO 3: TESTAR NO DASHBOARD

### Acessar Dashboard

URL: **http://127.0.0.1:8000/watcherdb**

### Navegar ate Filegroup com Dados

**IMPORTANTE:** Use apenas filegroups que tem dados no WatcherDB!

**Servidor Testado com Sucesso:**
- Instance: `SQLHDSTST505_I01`
- Database: `master`
- Filegroup: `PRIMARY`

**Servidores que TEM dados** (exemplos do WatcherDB):
- `SQLHDSPRD001_I0001` → master → PRIMARY
- `SQLHDSPRD002_I0001` → master → PRIMARY
- `SQLHDSPRD003_I0002` → master → PRIMARY
- `SQLHDSPRD004_I0002` → master → PRIMARY

**Servidor que NAO TEM dados:**
- ❌ `SQLHDSPRD213_J01` (nao esta no WatcherDB)

### Passos no Dashboard:

1. Clique na instance (ex: `SQLHDSPRD001_I0001`)
2. Clique no database (ex: `master`)
3. Clique no filegroup (ex: `PRIMARY`)
4. Clique no botao **"Analise Preditiva"**

### Resultado Esperado:

✅ Modal de progresso aparece
✅ Relatorio HTML gerado e aberto no navegador
✅ Arquivo CSV criado em `reports/`
✅ Sem erros

---

## PASSO 4: VERIFICAR RELATORIOS GERADOS

```bash
# Listar relatorios gerados (últimos 5)
dir reports\*.html /O-D /B | head -5

# OU no PowerShell
Get-ChildItem reports\*.html | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

**Arquivos esperados:**
- `interactive_{FILEGROUP}_{TIMESTAMP}_forecast.html`
- `interactive_{FILEGROUP}_{TIMESTAMP}_forecast.csv`

---

## TROUBLESHOOTING

### Erro: "Address already in use"

**Causa:** Porta 8000 ainda esta em uso
**Solucao:** Matar processo:
```bash
netstat -ano | findstr ":8000"
# Pegar PID da primeira linha (coluna final)
taskkill /F /PID <PID>
```

### Erro: "ModuleNotFoundError: No module named 'uvicorn'"

**Causa:** uvicorn nao instalado
**Solucao:**
```bash
pip install uvicorn
```

### Erro: "Script nao encontrado" ainda aparece

**Causa:** Aplicacao nao reiniciou ou arquivo nao existe
**Solucao:**
1. Verificar se arquivo existe:
   ```bash
   dir filegroup_interactive_report_v5_watcherdb.py
   ```
2. Se existir, reiniciar aplicacao novamente

### Erro: "Nao foi possivel obter dados do filegroup no WatcherDB"

**Causa:** Servidor/database/filegroup escolhido nao tem dados no WatcherDB
**Solucao:** Escolher outro filegroup que tem dados (ver lista acima)

---

## VERIFICACAO FINAL

Apos reiniciar, verificar logs do uvicorn:

```
✅ INFO: Application startup complete.
✅ INFO: Script de analise preditiva carregado: filegroup_interactive_report_v5_watcherdb.py
```

Se nao aparecer a segunda linha, verificar:
1. Arquivo `filegroup_interactive_report_v5_watcherdb.py` existe no diretorio raiz?
2. `modules/analytics/predictive_analysis.py` foi modificado corretamente?

---

## RESUMO RAPIDO

```bash
# 1. Parar aplicacao
Ctrl+C (no terminal do uvicorn)

# 2. Navegar
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"

# 3. Iniciar
python -m uvicorn watcherdb_intelligence:app --reload --port 8000

# 4. Aguardar mensagem:
# "Script de analise preditiva carregado: filegroup_interactive_report_v5_watcherdb.py"

# 5. Testar no dashboard:
# http://127.0.0.1:8000/watcherdb
# Usar: SQLHDSPRD001_I0001 > master > PRIMARY
```

---

## PROXIMOS TESTES

Apos analise preditiva funcionar, testar outras correcoes do dashboard:

1. ✅ DB Not Availability (deve mostrar ≈0 ao inves de 189)
2. ✅ Processes Alarm (modal deve mostrar 6 instancias)
3. ✅ Contagem de ambientes (soma deve bater com total do card)
4. ✅ Tooltips nao duplicados

Referencia: [CHECKLIST_TESTES_FINAL.md](CHECKLIST_TESTES_FINAL.md)

---

**Status:** ⏳ **AGUARDANDO REINICIO DA APLICACAO**
**Proxima Acao:** Parar uvicorn (Ctrl+C) e reiniciar com comando acima
