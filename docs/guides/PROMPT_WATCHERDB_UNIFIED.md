# PROMPT UNIFICADO - WATCHERDB (Standard, Enterprise, Professional)

## CONTEXTO GERAL

Existem 3 versões do WatcherDB, um sistema de monitoramento de SQL Server. Cada versão herda da anterior e adiciona funcionalidades:

```
STANDARD (base) --> ENTERPRISE (+ IA) --> PROFESSIONAL (+ Execução)
```

### Diretórios dos Projetos

| Versão | Diretório | Status |
|--------|-----------|--------|
| **Standard** | `C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV` | FONTE PRINCIPAL |
| **Enterprise** | `C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1` | Herda do Standard |
| **Professional** | `C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WatcherDB_Professional` | Herda do Enterprise |

---

## HIERARQUIA DE FUNCIONALIDADES

### 1. STANDARD (WATCHERDB_DEV)
**Características:** Monitoramento READ-ONLY

**Módulos incluídos:**
- `modules/monitoring/` (exceto predictive_*, trends_*)
  - monitoring.py
  - queries.py
  - space_analysis.py
  - backup_analysis.py
  - cpu_analysis.py
  - memory_analysis.py
  - dashboard_api.py
  - service_monitor.py
  - logs_collector.py
  - watcherdb_alwayson_check.py
- `api/routers/`
  - sqlserver_kpis.py
  - oracle_kpis.py
  - jobs.py
  - alwayson.py
  - diagnostics_overview.py
  - service_status.py
  - sql_queries.py
  - users.py
- `templates/watcherdb_portal.html` (versão básica)
- `database/` (scripts SQL de infraestrutura)

**NÃO deve ter:**
- predictive_analysis.py
- predictive_alerts.py
- trends_analysis.py
- intelligence_kpis.py
- innovative_features.js/css
- Copilot
- Módulos de execução DML

---

### 2. ENTERPRISE (WATCHERDB INTELLIGENCE V1)
**Características:** Standard + IA + Análise Preditiva

**Adiciona ao Standard:**
- `modules/analytics/predictive_analysis.py`
- `modules/monitoring/predictive_alerts.py`
- `modules/monitoring/trends_analysis.py`
- `api/routers/intelligence_kpis.py`
- `static/js/innovative_features.js`
- `static/css/innovative_features.css`
- `templates/innovative_sections.html`
- Copilot/Assistente IA
- Detecção de anomalias
- Recomendações inteligentes

**NÃO deve ter:**
- Módulos de execução DML
- User management
- Storage actions
- Audit logger

---

### 3. PROFESSIONAL (WatcherDB_Professional)
**Características:** Enterprise + Execução + Auditoria

**Adiciona ao Enterprise:**
- `execution/dml_executor.py` - SELECT, INSERT, UPDATE, DELETE
- `execution/storage_actions.py` - Add datafiles, shrink, resize
- `execution/job_executor.py` - Start/Stop SQL Agent Jobs
- `execution/user_management.py` - Create/Drop logins, users, permissions
- `execution/procedure_runner.py` - Execute stored procedures
- `security/audit_logger.py` - Log completo de todas ações
- Workflow de aprovação para operações críticas
- Avaliação de risco (LOW/MEDIUM/HIGH/CRITICAL)

---

## REGRAS DE DESENVOLVIMENTO

### Regra 1: Fluxo de Mudanças
```
Mudança no STANDARD --> Testar --> Replicar para ENTERPRISE --> Replicar para PROFESSIONAL
```

**NUNCA fazer mudanças diretamente no Enterprise ou Professional que afetem a base comum.**

### Regra 2: Identificação do Projeto
Quando abrir um Cursor, identifique qual projeto está aberto verificando:
- O diretório de trabalho
- A presença de arquivos específicos:
  - Standard: `watcherdb_main.py` (sem `execution/`)
  - Enterprise: `watcherdb_intelligence/` (pasta) ou `predictive_analysis.py`
  - Professional: `watcherdb_professional/execution/`

### Regra 3: Escopo de Alterações

| Se estiver em | Pode alterar | NÃO pode alterar |
|---------------|--------------|------------------|
| Standard | Tudo exceto módulos Enterprise/Professional | predictive_*, trends_*, execution/* |
| Enterprise | Módulos Enterprise + Standard (com cuidado) | execution/*, audit_logger |
| Professional | Tudo (mas propagar base para baixo) | - |

### Regra 4: Sincronização
Após validar mudanças no Standard:
1. Copiar módulos alterados para Enterprise
2. Copiar módulos alterados para Professional
3. Testar em cada versão

---

## COMANDOS PARA INICIAR CADA VERSÃO

### Standard
```powershell
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python -m uvicorn watcherdb_main:app --reload --port 8000
```

### Enterprise
```powershell
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1"
python -m uvicorn watcherdb_intelligence.main:app --reload --port 8001
```

### Professional
```powershell
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WatcherDB_Professional"
python -m uvicorn watcherdb_professional.main:app --reload --port 8002
```

---

## PERGUNTAS PARA FAZER AO USUÁRIO

Quando abrir uma sessão, pergunte:
1. "Qual versão estamos trabalhando? (Standard/Enterprise/Professional)"
2. "É uma mudança na BASE (afeta todos) ou ESPECÍFICA desta versão?"

---

## CHECKLIST DE VALIDAÇÃO

### Antes de replicar do Standard para Enterprise/Professional:

- [ ] watcherdb_main.py inicia sem erros
- [ ] Portal carrega corretamente (http://localhost:8000/watcherdb)
- [ ] KPIs são coletados e exibidos
- [ ] Jobs são listados
- [ ] AlwaysOn/AG mostra status
- [ ] Space analysis funciona
- [ ] Sem erros no console do navegador (F12)

### Para Enterprise (além do Standard):
- [ ] Análise preditiva funciona
- [ ] Copilot responde
- [ ] Intelligence KPIs carregam

### Para Professional (além do Enterprise):
- [ ] Audit logger registra ações
- [ ] DML executor funciona
- [ ] Jobs podem ser iniciados/parados
- [ ] Operações críticas pedem aprovação

---

## ARQUIVOS IMPORTANTES

### Configuração
- `config/sql_servers.json` - Lista de servidores monitorados
- `config/config.yaml` - Configurações gerais
- `.env` - Variáveis de ambiente

### Entry Points
- Standard: `watcherdb_main.py`
- Enterprise: `watcherdb_intelligence/main.py`
- Professional: `watcherdb_professional/main.py`

### Templates
- `templates/watcherdb_portal.html` - Portal principal

---

## NOTAS IMPORTANTES

1. **O Standard é a FONTE DA VERDADE** para a base comum
2. **Sempre teste no Standard primeiro** antes de replicar
3. **Mudanças específicas de Enterprise** ficam apenas no Enterprise
4. **Mudanças específicas de Professional** ficam apenas no Professional
5. **Use portas diferentes** para rodar múltiplas versões simultaneamente (8000, 8001, 8002)

---

## ÚLTIMA ATUALIZAÇÃO
Data: 2025-12-15
Status: Standard em validação, Enterprise e Professional aguardando sincronização
