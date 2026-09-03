# PROMPT: Estratégia de Versionamento WatcherDB

## Visão Geral das Versões

| Versão | Público | Funcionalidades |
|--------|---------|-----------------|
| **Standard** | DBAs Operacionais | Monitoramento básico, dashboards, alertas |
| **Enterprise** | DBAs Sênior/Arquitetos | Standard + IA + Análise Preditiva + Copilot |
| **Professional** | DBAs com Permissões DML | Enterprise + Execução de Comandos + Ações Diretas |

---

## Estrutura de Diretórios

```
C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\
│
├── WATCHERDB_DEV\                       # 🟢 STANDARD
│   ├── watcherdb_main.py
│   ├── watcherdb_intelligence.py        # Entry point para uvicorn
│   ├── api/routers/
│   ├── modules/monitoring/
│   ├── templates/
│   ├── static/
│   └── docs/
│
├── WATCHERDB INTELLIGENCE V1\           # 🔵 ENTERPRISE
│   ├── watcherdb_intelligence/
│   │   ├── main.py
│   │   ├── api/v1/
│   │   │   ├── maintenance_score.py
│   │   │   ├── chaos_detection.py
│   │   │   ├── copilot.py
│   │   │   ├── os_performance.py
│   │   │   └── jobs.py
│   │   └── core/
│   ├── database/
│   └── docs/
│
└── WatcherDB_Professional\              # 🟣 PROFESSIONAL (A CRIAR)
    ├── watcherdb_professional/
    │   ├── main.py
    │   ├── api/v1/
    │   │   ├── dml_executor.py          # Execução de comandos DML
    │   │   ├── user_management.py       # Controle de usuários
    │   │   ├── storage_actions.py       # Adicionar datafiles, shrink
    │   │   ├── job_executor.py          # Executar jobs
    │   │   └── procedure_runner.py      # Executar procedures
    │   ├── security/
    │   │   ├── audit_logger.py          # Log de todas as ações
    │   │   ├── role_validator.py        # Validação de permissões
    │   │   └── approval_workflow.py     # Workflow de aprovação
    │   └── core/
    └── database/
```

---

## Funcionalidades por Versão

### 🟢 STANDARD (WATCHERDB_V3)

**Foco:** Monitoramento e Visualização (READ-ONLY)

| Módulo | Funcionalidade |
|--------|----------------|
| Dashboard | Overview de todos os servidores |
| Space | Monitoramento de espaço em disco e filegroups |
| Memory | Análise de memória SQL Server |
| CPU | Análise de CPU e workers |
| Jobs | Visualização de status de jobs (sem execução) |
| Backup | Status de backups |
| Always On | Monitoramento de AGs |
| Security | Visualização de usuários e permissões |
| Logs | Visualização de event logs |

**Restrições:**
- ❌ Sem execução de comandos
- ❌ Sem IA/Copilot
- ❌ Sem análise preditiva
- ✅ Apenas leitura de dados

---

### 🔵 ENTERPRISE (WATCHERDB INTELLIGENCE V1)

**Foco:** Análise Inteligente + IA (READ-ONLY com Insights)

Inclui **TUDO do Standard** mais:

| Módulo | Funcionalidade |
|--------|----------------|
| **Maintenance Score** | Score preditivo de saúde por instância |
| **Chaos Detection** | Detecção de padrões de falha correlacionados |
| **DBA Copilot** | IA que responde perguntas sobre o ambiente |
| **OS Performance** | KPIs do Windows OS (Memory, CPU, Disk) |
| **Predictive Alerts** | Alertas preditivos baseados em tendências |
| **Trend Analysis** | Análise de tendências históricas |

**Copilot Features:**
- Responde perguntas em linguagem natural
- Gera relatórios automáticos
- Sugere ações baseadas em dados
- Explica problemas e recomendações
- Conhece toda a estrutura do programa

**Restrições:**
- ❌ Sem execução de comandos DML
- ❌ Sem ações diretas no banco
- ✅ Leitura + Análise + Recomendações

---

### 🟣 PROFESSIONAL (WATCHERDB_PRO) - A CRIAR

**Foco:** Ações Diretas com Auditoria (READ + WRITE)

Inclui **TUDO do Enterprise** mais:

| Módulo | Funcionalidade | Exemplo de Uso |
|--------|----------------|----------------|
| **DML Executor** | Executar SELECT, INSERT, UPDATE, DELETE | Corrigir dados corrompidos |
| **User Management** | Criar/alterar/remover usuários e permissões | Gerenciar acessos |
| **Storage Actions** | Adicionar datafiles, shrink, resize | Expandir filegroups |
| **Job Executor** | Iniciar/parar/criar jobs | Executar backup manual |
| **Procedure Runner** | Executar stored procedures | Rodar manutenção |
| **Index Management** | Rebuild/Reorganize indexes | Otimização |
| **Kill Sessions** | Matar sessões bloqueadoras | Resolver deadlocks |
| **Failover Control** | Failover manual de AGs | DR |

**Segurança Obrigatória:**

```
┌─────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                          │
├─────────────────────────────────────────────────────────────┤
│ 1. AUTHENTICATION                                           │
│    - Windows Authentication (AD)                            │
│    - MFA opcional                                           │
├─────────────────────────────────────────────────────────────┤
│ 2. AUTHORIZATION                                            │
│    - Role-based access (DBA_ReadOnly, DBA_Execute, DBA_Admin)│
│    - Permissões por servidor/instância                      │
├─────────────────────────────────────────────────────────────┤
│ 3. APPROVAL WORKFLOW (para ações críticas)                  │
│    - Shrink → Requer aprovação                              │
│    - DROP/DELETE → Requer aprovação                         │
│    - Failover → Requer aprovação                            │
├─────────────────────────────────────────────────────────────┤
│ 4. AUDIT LOG                                                │
│    - Quem executou                                          │
│    - O que executou                                         │
│    - Quando executou                                        │
│    - Resultado (sucesso/falha)                              │
│    - Rollback disponível                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Arquitetura de Herança

```
                    ┌─────────────────────┐
                    │   WATCHERDB_CORE    │
                    │   (Módulos Base)    │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │    STANDARD     │ │   ENTERPRISE    │ │  PROFESSIONAL   │
    │   (Read Only)   │ │  (Read + AI)    │ │ (Read + Write)  │
    └─────────────────┘ └─────────────────┘ └─────────────────┘
           │                    │                    │
           │                    │ extends            │ extends
           │                    ▼                    ▼
           │           ┌─────────────────┐ ┌─────────────────┐
           │           │  + Copilot      │ │ + All Enterprise│
           │           │  + Maint. Score │ │ + DML Executor  │
           │           │  + Chaos Detect │ │ + User Mgmt     │
           │           │  + OS Perf      │ │ + Storage Acts  │
           └───────────┤  + Predictive   │ │ + Job Executor  │
                       └─────────────────┘ │ + Audit Log     │
                                           │ + Approval Flow │
                                           └─────────────────┘
```

---

## Plano de Implementação

### Fase 1: Organização (Atual)

1. **Consolidar STANDARD** em `WATCHERDB_V3`
   - Remover features de IA
   - Manter apenas monitoramento básico
   - Documentar funcionalidades

2. **Consolidar ENTERPRISE** em `WATCHERDB INTELLIGENCE V1`
   - Manter código atual
   - Adicionar Copilot com conhecimento do programa
   - Integrar todos os módulos de análise

### Fase 2: Criar PROFESSIONAL

1. **Criar estrutura** `WATCHERDB_PRO`
   ```bash
   mkdir "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\WATCHERDB_PRO"
   ```

2. **Copiar base do Enterprise**
   - Copiar `watcherdb_intelligence/`
   - Adicionar módulos de execução

3. **Implementar módulos de ação:**
   - `dml_executor.py`
   - `user_management.py`
   - `storage_actions.py`
   - `job_executor.py`
   - `procedure_runner.py`

4. **Implementar segurança:**
   - `audit_logger.py`
   - `role_validator.py`
   - `approval_workflow.py`

### Fase 3: UI/UX

1. **Diferenciar visualmente:**
   - Standard: Tema azul/cinza
   - Enterprise: Tema azul/dourado
   - Professional: Tema azul/vermelho (indica poder)

2. **Botões de ação (PRO only):**
   - Botão "Execute" em cada painel
   - Modal de confirmação
   - Indicador de permissão

---

## Tabela de Preços (Exemplo)

| Versão | Licenciamento | Uso Sugerido |
|--------|---------------|--------------|
| Standard | Gratuito/Interno | Equipe de operações |
| Enterprise | Por instância monitorada | Equipe de DBAs |
| Professional | Por DBA + instância | DBAs sênior com autorização |

---

## Configuração por Versão

### Standard - config.json
```json
{
  "version": "standard",
  "features": {
    "monitoring": true,
    "dashboards": true,
    "alerts_view": true,
    "ai_copilot": false,
    "predictive": false,
    "execute_commands": false
  }
}
```

### Enterprise - config.json
```json
{
  "version": "enterprise",
  "features": {
    "monitoring": true,
    "dashboards": true,
    "alerts_view": true,
    "ai_copilot": true,
    "predictive": true,
    "maintenance_score": true,
    "chaos_detection": true,
    "os_performance": true,
    "execute_commands": false
  }
}
```

### Professional - config.json
```json
{
  "version": "professional",
  "features": {
    "monitoring": true,
    "dashboards": true,
    "alerts_view": true,
    "ai_copilot": true,
    "predictive": true,
    "maintenance_score": true,
    "chaos_detection": true,
    "os_performance": true,
    "execute_commands": true,
    "dml_execution": true,
    "user_management": true,
    "storage_actions": true,
    "job_execution": true,
    "approval_workflow": true,
    "audit_logging": true
  },
  "security": {
    "require_mfa": false,
    "approval_required_for": ["shrink", "drop", "delete", "failover"],
    "audit_retention_days": 365
  }
}
```

---

## Próximos Passos

1. [ ] Validar estrutura de diretórios proposta
2. [ ] Criar diretório WATCHERDB_PRO
3. [ ] Definir quais módulos do WATCHERDB_DEV vão para Standard
4. [ ] Implementar feature flags para controle de versão
5. [ ] Criar módulos de execução para Professional
6. [ ] Implementar sistema de auditoria
7. [ ] Criar workflow de aprovação
8. [ ] Documentar API de cada versão

---

## Conclusão

Esta estratégia permite:

1. **Separação clara** de responsabilidades por versão
2. **Segurança em camadas** para ações destrutivas
3. **Escalabilidade** - adicionar features sem quebrar versões anteriores
4. **Auditoria completa** no Professional
5. **IA contextual** no Enterprise que entende todo o sistema

**Comando para criar WATCHERDB_PRO:**
```powershell
$proPath = "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\WATCHERDB_PRO"
New-Item -ItemType Directory -Path $proPath -Force
Copy-Item -Path "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1\*" -Destination $proPath -Recurse
```
