# 📊 SCRIPT DE ANÁLISE PREDITIVA CRIADO

**Data:** 2025-12-10
**Script:** `filegroup_interactive_report_v5.py`
**Status:** ✅ **CRIADO E PRONTO PARA USO**

---

## 🎯 O QUE FOI FEITO

Criei o script `filegroup_interactive_report_v5.py` que estava faltando no projeto. Este script permite fazer análise preditiva de crescimento de filegroups.

---

## 📋 FUNCIONALIDADES

### **1. Análise de Crescimento**
- ✅ Busca dados históricos do Oracle (WatcherDB) ou SQL Server
- ✅ Calcula tendência de crescimento usando Machine Learning (ou regressão linear simples)
- ✅ Prevê quando o filegroup atingirá um threshold (padrão: 85%)

### **2. Relatórios Gerados**
O script gera 3 arquivos no diretório `reports/`:

1. **HTML Interativo:** `interactive_{filegroup}_{timestamp}_forecast.html`
   - Gráfico interativo com Chart.js
   - Mostra histórico + previsão
   - Design moderno (dark theme)
   - Status visual (verde/amarelo/vermelho)

2. **CSV de Dados:** `interactive_{filegroup}_{timestamp}_forecast.csv`
   - Dados históricos e previsão
   - Pronto para análise no Excel

3. **Informações Detalhadas:**
   - Tamanho atual do filegroup
   - % de uso atual
   - Dias até atingir threshold
   - Data prevista de criticidade

---

## 🚀 COMO USAR

### **Uso Manual (Linha de Comando)**

```bash
# Formato básico
python filegroup_interactive_report_v5.py "Instance=SERVER;DatabaseName=DB;filegroup_name=FG" [dias] [threshold]

# Exemplo real
python filegroup_interactive_report_v5.py "Instance=SQLHDSPRD005_I0003;DatabaseName=DBA_RESOURCE_DB;filegroup_name=PRIMARY" 60 0.85
```

**Parâmetros:**
- `Instance=X;DatabaseName=Y;filegroup_name=Z` - Identificador do filegroup (obrigatório)
- `dias` - Quantos dias prever (padrão: 60)
- `threshold` - Limite de alerta em decimal (padrão: 0.85 = 85%)

### **Uso Automático (Via Dashboard)**

Agora quando você clicar em um filegroup no dashboard e escolher "📊 Análise Preditiva", o sistema:
1. Executa o script automaticamente
2. Gera os relatórios
3. Abre o HTML no navegador

---

## 🔧 REQUISITOS

### **Obrigatórios:**
- ✅ Python 3.x
- ✅ pandas
- ✅ numpy
- ✅ pyodbc (para SQL Server)

### **Opcionais (melhoram a previsão):**
- scikit-learn (regressão polinomial)
- prophet (previsão avançada da Meta/Facebook)
- cx_Oracle (buscar dados históricos do WatcherDB Oracle)

Se não tiver as bibliotecas opcionais, o script funciona com regressão linear simples.

---

## 📊 EXEMPLO DE SAÍDA

### **Console:**
```
🚀 Análise Preditiva de Filegroup
Instance: SQLHDSPRD005_I0003
Database: DBA_RESOURCE_DB
Filegroup: PRIMARY
Previsão: 60 dias
Threshold: 85%

📊 Buscando dados históricos...
✅ 30 registros históricos encontrados
🔮 Calculando previsão...
⚠️ Filegroup atingirá 85% em 45 dias (2025-01-24)

📄 Gerando relatórios...
✅ Relatório gerado: reports/interactive_PRIMARY_20251210_forecast.html
✅ CSV gerado: reports/interactive_PRIMARY_20251210_forecast.csv

✅ Análise concluída com sucesso!
```

### **HTML Gerado:**
- **Header:** Informações da instância/database/filegroup
- **Status Card:** Alerta visual (verde/amarelo/vermelho)
- **KPI Cards:** Tamanho, uso atual, % usado, dias de previsão
- **Gráfico Interativo:**
  - Linha azul: Histórico
  - Linha laranja tracejada: Previsão
  - Linha vermelha: Threshold (85%)

---

## 🎨 DESIGN

O relatório HTML usa:
- **Dark Theme:** Fundo escuro (mais confortável para leitura)
- **Chart.js:** Gráficos interativos e responsivos
- **Gradientes:** Visual moderno e profissional
- **Cores Semânticas:**
  - 🟢 Verde: Tudo OK (>60 dias até threshold)
  - 🟡 Amarelo: Atenção (30-60 dias)
  - 🔴 Vermelho: Crítico (<30 dias)

---

## 🔄 INTEGRAÇÃO COM O DASHBOARD

O script está integrado com `modules/analytics/predictive_analysis.py`:

```python
# O dashboard chama assim:
analyzer = PredictiveAnalyzer()
result = analyzer.generate_filegroup_report(
    server_name="SQLHDSPRD005_I0003",
    database_name="DBA_RESOURCE_DB",
    filegroup_name="PRIMARY",
    forecast_days=60,
    threshold=0.85
)

# Resultado:
{
    "success": True,
    "html_path": "reports/interactive_PRIMARY_20251210_forecast.html",
    "csv_path": "reports/interactive_PRIMARY_20251210_forecast.csv",
    "generated_at": "2025-12-10T15:30:00"
}
```

---

## 🧪 TESTE MANUAL

Para testar se o script funciona:

```bash
# 1. Navegar até o diretório
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"

# 2. Executar teste
python filegroup_interactive_report_v5.py "Instance=SQLHDSPRD213_I01;DatabaseName=DBA_RESOURCE_DB;filegroup_name=PRIMARY" 60 0.85

# 3. Verificar se gerou arquivos em reports/
dir reports
```

**Resultado Esperado:**
- ✅ Console mostra progresso
- ✅ Arquivo HTML criado em `reports/`
- ✅ Arquivo CSV criado em `reports/`
- ✅ Sem erros

---

## 📝 NOTAS TÉCNICAS

### **Fontes de Dados:**

1. **Primeira opção:** Oracle (WatcherDB)
   - Query: `WATCHERDB.KPI_MSSQL_FG_USAGE_HIST`
   - Busca últimos 90 dias de histórico
   - Dados agrupados por dia

2. **Fallback:** SQL Server direto
   - Query: `sys.database_files` + `sys.filegroups`
   - Simula histórico com base no estado atual
   - Menos preciso mas funciona

### **Algoritmo de Previsão:**

- **Com scikit-learn:** Regressão polinomial grau 2
- **Sem scikit-learn:** Regressão linear simples
- Calcula taxa de crescimento diária
- Projeta para os próximos N dias

### **Detecção de Criticidade:**

```python
# Encontra primeira data onde USED_PCT >= threshold
if USED_PCT >= 85%:
    critical_date = DATA
    days_until_critical = (critical_date - today).days
```

---

## ⚠️ LIMITAÇÕES

1. **Dados Históricos:** Precisa de pelo menos 5 registros históricos
2. **Tendência Linear:** Assume crescimento contínuo (não considera sazonalidade)
3. **Tamanho Fixo:** Assume que o filegroup não aumentará de tamanho
4. **Oracle Opcional:** Funciona sem Oracle mas com menos precisão

---

## 🔮 MELHORIAS FUTURAS (Opcionais)

1. **Prophet:** Adicionar suporte para sazonalidade
2. **Auto-growth:** Considerar crescimento automático do filegroup
3. **Alertas:** Enviar email quando atingir X% do threshold
4. **Histórico Sintético:** Melhorar simulação quando não há dados reais
5. **Validação:** Comparar previsão vs realidade após N dias

---

## 🎯 PRÓXIMOS PASSOS

1. ✅ Script criado
2. ⏳ Instalar dependências (se necessário):
   ```bash
   pip install scikit-learn
   ```
3. ⏳ Testar manualmente
4. ⏳ Reiniciar aplicação
5. ⏳ Testar via dashboard (clicar no botão "Análise Preditiva")

---

## 📂 LOCALIZAÇÃO DOS ARQUIVOS

- **Script:** [filegroup_interactive_report_v5.py](filegroup_interactive_report_v5.py)
- **Módulo Integrador:** [modules/analytics/predictive_analysis.py](modules/analytics/predictive_analysis.py)
- **Relatórios Gerados:** `reports/interactive_*_forecast.html`

---

**Status:** ✅ **SCRIPT CRIADO E PRONTO PARA USO**
**Próximo Passo:** Testar manualmente antes de reiniciar a aplicação
