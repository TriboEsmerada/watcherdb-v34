# 👥 ABA USERS - MONITORAMENTO DE SEGURANÇA DE USUÁRIOS

## WatcherDB v1.4.8.4

**Data de Implementação:** 20 de novembro de 2025
**Versão:** 1.4.8.4

---

## 📋 RESUMO

Implementada nova aba "Users" para monitoramento abrangente de segurança de usuários e logins no SQL Server, com foco em auditoria e detecção de riscos de segurança.

**IMPORTANTE:** Esta é uma funcionalidade de **monitoramento apenas**. Não há botões de ação automática. Os DBAs devem executar correções diretamente nos bancos de dados.

---

## ✨ FUNCIONALIDADES IMPLEMENTADAS

### 1. **Usuários Órfãos**

Detecta usuários de banco de dados sem login correspondente no servidor.

**O que detecta:**
- Usuários de database sem SID correspondente em `sys.server_principals`
- Causas comuns: Login deletado, migração de servidor, restore de database

**Query SQL:**
```sql
-- Percorre todos os databases
-- Compara sys.database_principals com sys.server_principals
-- Identifica SIDs sem correspondência
```

**Dados exibidos:**
- Database name
- User name
- SID (Security Identifier)
- User type (SQL User, Windows User, etc.)

**Card KPI:** Vermelho se > 0, verde se = 0

---

### 2. **Permissões Excessivas**

Identifica usuários e logins com permissões administrativas críticas.

**O que detecta:**

**Server-level:**
- Membros de `sysadmin`
- Membros de `securityadmin`
- Membros de `serveradmin`
- Permissões `CONTROL SERVER`

**Database-level:**
- Membros de `db_owner`
- Membros de `db_securityadmin`
- Membros de `db_ddladmin`

**Exceções:** Exclui contas de sistema (NT SERVICE, NT AUTHORITY, sa)

**Dados exibidos:**
- Login/User name
- Database (ou "SERVER LEVEL")
- Role/Permission name
- Motivo da classificação como excessiva

**Card KPI:** Laranja se > 0, verde se = 0

---

### 3. **Usuários Inativos**

Lista logins sem atividade recente (30+ dias).

**O que detecta:**
- Logins que nunca fizeram login desde criação
- Logins sem atividade nos últimos 30 dias
- Status de disabled/enabled

**Query SQL:**
```sql
-- Usa sys.dm_exec_sessions para buscar último login
-- Calcula dias de inatividade
-- Identifica logins desabilitados
```

**Dados exibidos:**
- Login name
- Data de criação
- Data do último login (ou "Nunca")
- Dias inativo
- Status (Desabilitado/Habilitado)

**Card KPI:** Amarelo se > 0, verde se = 0

**Recomendação:** Logins inativos por 90+ dias devem ser revisados para possível desabilitação.

---

### 4. **Políticas de Senha Fracas**

Detecta logins SQL com políticas de segurança de senha desabilitadas.

**O que detecta:**
- `CHECK_POLICY = OFF` (não valida complexidade da senha)
- `CHECK_EXPIRATION = OFF` (senha nunca expira)
- Logins desabilitados
- Data da última alteração de senha

**Query SQL:**
```sql
SELECT FROM sys.sql_logins
WHERE is_policy_checked = 0
   OR is_expiration_checked = 0
```

**Dados exibidos:**
- Login name
- CHECK_POLICY status (SIM/NÃO)
- CHECK_EXPIRATION status (SIM/NÃO)
- Desabilitado (SIM/NÃO)
- Última alteração de senha

**Card KPI:** Vermelho se > 0, verde se = 0

**Risco:** Senhas fracas facilitam ataques de força bruta e comprometimento de segurança.

---

### 5. **Membros de Roles Críticos**

Auditoria completa de membros em roles com permissões críticas.

**Server-level roles monitorados:**
- `sysadmin` (controle total)
- `securityadmin` (gerencia logins e permissões)
- `serveradmin` (configuração do servidor)
- `processadmin` (gerencia processos)
- `setupadmin` (linked servers)
- `bulkadmin` (bulk insert)
- `diskadmin` (gerencia arquivos de disco)
- `dbcreator` (cria e altera databases)

**Database-level roles monitorados:**
- `db_owner` (controle total do database)
- `db_securityadmin` (gerencia permissões)
- `db_accessadmin` (gerencia access)
- `db_ddladmin` (DDL operations)
- `db_backupoperator` (backup operations)

**Dados exibidos:**
- Member name
- Database name (ou "SERVER" para server-level)
- Role name
- Member type (SQL_LOGIN, WINDOWS_LOGIN, etc.)

**Card KPI:** Amarelo (informativo), exibe total de membros

**Uso:** Auditoria periódica para garantir princípio de menor privilégio.

---

## 🎨 INTERFACE VISUAL

### Cards KPI (Topo da Aba)

```
┌─────────────┬─────────────┬─────────────┬─────────────┬─────────────┬─────────────┐
│ Total Users │   Órfãos    │  Permissões │  Inativos   │   Senhas    │   Roles     │
│             │             │  Excessivas │             │   Fracas    │  Críticos   │
│    156      │      3      │      8      │     12      │      5      │     45      │
│  (Roxo)     │  (Vermelho) │  (Laranja)  │  (Amarelo)  │ (Vermelho)  │ (Amarelo)   │
└─────────────┴─────────────┴─────────────┴─────────────┴─────────────┴─────────────┘
```

**Cores:**
- **Total Users:** Gradiente roxo (#667eea → #764ba2)
- **Órfãos:** Vermelho (#ef4444) se > 0, verde (#10b981) se = 0
- **Excessivas:** Laranja (#f59e0b) se > 0, verde se = 0
- **Inativos:** Amarelo (#fbbf24) se > 0, verde se = 0
- **Senhas Fracas:** Vermelho se > 0, verde se = 0
- **Roles Críticos:** Amarelo (sempre, informativo)

**Interatividade:** Clique em um card para expandir/colapsar a seção correspondente.

---

### Seções Detalhadas

Cada categoria tem uma seção colapsável com:

- **Header clicável** com ícone chevron (▼/▲)
- **Tabela HTML** com dados detalhados
- **Scroll horizontal** para tabelas largas
- **Estilo consistente** com tema dark do WatcherDB

**Exemplo de seção expandida:**

```
┌──────────────────────────────────────────────────────────────────┐
│ 🔴 Usuários Órfãos (3) ▲                                         │
├──────────────────────────────────────────────────────────────────┤
│ ⚠ Usuários de banco de dados sem login correspondente.          │
│                                                                  │
│ Database      │ Usuário       │ SID           │ Tipo            │
│───────────────┼───────────────┼───────────────┼────────────────│
│ DB_TAP_PROD   │ user_old      │ 0x123456...   │ SQL_USER       │
│ DB_TAP_PROD   │ user_migrated │ 0xABCDEF...   │ WINDOWS_USER   │
│ DB_ANALYTICS  │ analyst_temp  │ 0x789012...   │ SQL_USER       │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🔧 ARQUITETURA TÉCNICA

### Frontend ([watcherdb_portal.html](templates/watcherdb_portal.html))

**1. Botão de Navegação (Linha 1612-1614)**
```html
<button class="nav-btn" onclick="showTab('users')" title="Users Analysis">
    <i class="fas fa-users"></i> Users
</button>
```

**2. Integração com Sistema de Abas**

- **loadTabContent()** (Linha 2732-2733): Chama `loadUsersAnalysisForTab()`
- **refreshTab()** (Linha 2472-2473): Suporta refresh da aba Users
- **Cache TTL** (Linha 1673): 3 minutos para dados de usuários

**3. Função Principal: `loadUsersAnalysisForTab()` (Linhas 3193-3273)**

```javascript
async function loadUsersAnalysisForTab(tabId) {
    // 1. Validações iniciais
    // 2. Verificar cache (TTL: 3 min)
    // 3. Loading state
    // 4. Fetch API: /api/users/server/{serverId}
    // 5. Renderizar UI com renderUsersAnalysis()
    // 6. Salvar em cache
    // 7. Tratamento de erros (incluindo AbortError)
}
```

**4. Função de Renderização: `renderUsersAnalysis()` (Linhas 3275-3639)**

Gera HTML completo com:
- Cards KPI (6 cards)
- 5 seções colapsáveis
- Tabelas com dados
- Tratamento de casos vazios (mensagens positivas)

**5. Helper Function: `toggleSection()` (Linhas 3642-3658)**

```javascript
function toggleSection(sectionId) {
    // Alterna display: none/block
    // Muda ícone chevron down/up
}
```

---

### Backend ([api/routers/users.py](api/routers/users.py))

**Router Configuration**
```python
router = APIRouter(
    prefix="/api/users",
    tags=["users-analysis"],
    responses={404: {"description": "Not found"}},
)
```

**Endpoint: `GET /api/users/server/{server_id}`**

**Parâmetros:**
- `server_id` (path): ID do servidor (ex: SQLHDSPRD001_I01)

**Response JSON:**
```json
{
  "orphaned_users": [
    {
      "database_name": "DB_TAP_PROD",
      "user_name": "user_old",
      "user_sid": "0x12345...",
      "user_type_desc": "SQL_USER"
    }
  ],
  "excessive_permissions": [
    {
      "login_name": "admin_user",
      "database_name": null,
      "role_name": "sysadmin",
      "permission": null,
      "reason": "Server-level critical role"
    }
  ],
  "inactive_users": [
    {
      "login_name": "old_service_account",
      "create_date": "2023-01-15T10:30:00",
      "last_login_date": null,
      "days_inactive": 680,
      "is_disabled": false
    }
  ],
  "weak_passwords": [
    {
      "login_name": "legacy_app",
      "is_policy_checked": false,
      "is_expiration_checked": false,
      "is_disabled": false,
      "password_last_set": "2022-03-10T14:20:00"
    }
  ],
  "critical_roles": [
    {
      "member_name": "dba_group",
      "database_name": null,
      "role_name": "sysadmin",
      "member_type": "WINDOWS_GROUP"
    }
  ],
  "total_users": 156
}
```

**Fluxo de Execução:**
1. Validar `server_id`
2. Converter server_id → server_name (HOST_INST → HOST\INST)
3. Gerar connection string
4. Conectar ao SQL Server via pyodbc
5. Executar 6 queries SQL (órfãos, excessivas server, excessivas db, inativos, senhas, roles server, roles db)
6. Formatar resultados em JSON
7. Logging e tratamento de erros

---

### SQL Queries

**1. Usuários Órfãos (Dinâmica multi-database)**

```sql
DECLARE @orphaned TABLE (...)
DECLARE db_cursor CURSOR FOR SELECT name FROM sys.databases ...

-- Para cada database ONLINE (exceto system):
USE [database_name]
INSERT INTO @orphaned
SELECT database, user, sid, type
FROM sys.database_principals dp
LEFT JOIN sys.server_principals sp ON dp.sid = sp.sid
WHERE dp.type IN ('S', 'U', 'G')
  AND sp.sid IS NULL  -- Órfão!
  AND dp.authentication_type_desc = 'INSTANCE'
```

**2. Permissões Excessivas - Server Level**

```sql
-- Membros de roles críticos
SELECT sp.name, sr.name, 'Server-level critical role'
FROM sys.server_role_members srm
JOIN sys.server_principals sp ON srm.member_principal_id = sp.principal_id
JOIN sys.server_principals sr ON srm.role_principal_id = sr.principal_id
WHERE sr.name IN ('sysadmin', 'securityadmin', 'serveradmin')

UNION ALL

-- CONTROL SERVER permissions
SELECT sp.name, spe.permission_name, 'CONTROL SERVER'
FROM sys.server_permissions spe
JOIN sys.server_principals sp ON spe.grantee_principal_id = sp.principal_id
WHERE spe.permission_name = 'CONTROL SERVER'
  AND spe.state_desc = 'GRANT'
```

**3. Permissões Excessivas - Database Level**

```sql
-- Similar à órfãos: cursor multi-database
USE [each_database]
SELECT database, user, role, 'Database-level critical'
FROM sys.database_role_members drm
JOIN sys.database_principals dp ON drm.member_principal_id = dp.principal_id
JOIN sys.database_principals dr ON drm.role_principal_id = dr.principal_id
WHERE dr.name IN ('db_owner', 'db_securityadmin', 'db_ddladmin')
```

**4. Usuários Inativos**

```sql
SELECT
    sp.name,
    sp.create_date,
    l.last_login_time,
    DATEDIFF(DAY, ISNULL(l.last_login_time, sp.create_date), GETDATE()) AS days_inactive,
    sp.is_disabled
FROM sys.server_principals sp
LEFT JOIN (
    SELECT login_name, MAX(login_time) AS last_login_time
    FROM sys.dm_exec_sessions
    GROUP BY login_name
) l ON sp.name = l.login_name
WHERE sp.type IN ('S', 'U', 'G')
  AND (l.last_login_time IS NULL OR DATEDIFF(DAY, l.last_login_time, GETDATE()) > 30)
ORDER BY days_inactive DESC
```

**5. Senhas Fracas**

```sql
SELECT
    name,
    is_policy_checked,
    is_expiration_checked,
    is_disabled,
    modify_date AS password_last_set
FROM sys.sql_logins
WHERE (is_policy_checked = 0 OR is_expiration_checked = 0)
  AND name NOT IN ('sa', '##MS_PolicyEventProcessingLogin##', ...)
ORDER BY is_policy_checked, is_expiration_checked
```

**6. Roles Críticos**

```sql
-- Server-level
SELECT sp.name, sr.name, sp.type_desc
FROM sys.server_role_members srm
JOIN sys.server_principals sp ON srm.member_principal_id = sp.principal_id
JOIN sys.server_principals sr ON srm.role_principal_id = sr.principal_id
WHERE sr.name IN ('sysadmin', 'securityadmin', ..., 'dbcreator')

-- Database-level: cursor multi-database para db_owner, etc.
```

---

## 🎯 CASOS DE USO

### Caso 1: Auditoria de Segurança Mensal

**Cenário:** DBA precisa gerar relatório de segurança mensal.

**Passos:**
1. Abrir WatcherDB
2. Selecionar servidor de produção
3. Clicar em aba "Users"
4. Revisar os 6 cards KPI
5. Expandir seções com valores > 0
6. Documentar achados

**Resultado:** Relatório completo em 2-3 minutos.

---

### Caso 2: Investigar Usuários Órfãos Após Restore

**Cenário:** Após restore de database de produção para homologação, aplicação não consegue conectar.

**Sintoma:** Erro "Login failed for user 'app_user'"

**Diagnóstico com WatcherDB:**
1. Abrir aba Users no servidor de homologação
2. Verificar seção "Usuários Órfãos"
3. Encontrar `app_user` na lista
4. Executar no SQL Server:
```sql
USE [database_restaurado]
EXEC sp_change_users_login 'Auto_Fix', 'app_user'
```

**Resultado:** Problema identificado e corrigido em < 1 minuto.

---

### Caso 3: Compliance - Princípio de Menor Privilégio

**Cenário:** Auditoria de compliance detectou violações de segregação de funções.

**Problema:** Contas de aplicação com sysadmin.

**Ação com WatcherDB:**
1. Abrir aba Users em todos os servidores de produção
2. Verificar "Permissões Excessivas"
3. Identificar contas de aplicação (`app_*`, `svc_*`)
4. Documentar para remoção de sysadmin
5. Criar logins com permissões específicas (db_owner apenas nos DBs necessários)

**Resultado:** Lista completa de violações para remediar.

---

### Caso 4: Higienização de Logins Inativos

**Cenário:** Reduzir superfície de ataque desabilitando logins inativos.

**Política:** Logins sem uso por 90+ dias devem ser desabilitados.

**Ação com WatcherDB:**
1. Abrir aba Users
2. Expandir "Usuários Inativos"
3. Filtrar visualmente por "Dias Inativo" > 90
4. Validar com times de aplicação
5. Desabilitar logins confirmados:
```sql
ALTER LOGIN [login_inativo] DISABLE
```

**Resultado:** Redução de logins ativos em 20-30%.

---

### Caso 5: Enforçar Políticas de Senha

**Cenário:** Política de segurança exige CHECK_POLICY e CHECK_EXPIRATION para todos os logins SQL.

**Ação com WatcherDB:**
1. Abrir aba Users
2. Verificar "Políticas de Senha Fracas"
3. Identificar logins não-conformes
4. Aplicar política:
```sql
ALTER LOGIN [login_name] WITH CHECK_POLICY = ON, CHECK_EXPIRATION = ON
```
5. Forçar troca de senha no próximo login:
```sql
ALTER LOGIN [login_name] WITH CHECK_EXPIRATION = ON
ALTER LOGIN [login_name] WITH PASSWORD = 'TemporaryP@ssw0rd!' MUST_CHANGE
```

**Resultado:** 100% de conformidade com política de senhas.

---

## 📊 PERFORMANCE E CACHE

### Sistema de Cache

- **TTL:** 3 minutos (180000ms)
- **Tipo:** Client-side cache no browser
- **Comportamento:**
  - 1ª visita: Carrega do servidor (~5-10s dependendo do número de databases)
  - Visitas subsequentes dentro de 3 min: Carrega do cache (~50ms)
  - Indicador visual mostra idade do cache

### Performance das Queries

**Fatores de impacto:**
- Número de databases no servidor
- Número total de logins/usuários
- Complexidade de roles e permissões

**Estimativas:**
- Servidor com 10 databases: ~2-3 segundos
- Servidor com 50 databases: ~5-8 segundos
- Servidor com 100+ databases: ~10-15 segundos

**Otimizações implementadas:**
- Queries paralelas onde possível
- Exclusão de system databases
- `BEGIN TRY/CATCH` para skip de databases offline
- Timeout de conexão: 30 segundos

---

## 🔍 TROUBLESHOOTING

### Erro: "Database error: Login failed"

**Causa:** Credenciais do WatcherDB não têm permissão.

**Solução:**
```sql
-- Conceder permissões necessárias ao login do WatcherDB
USE master
GRANT VIEW ANY DEFINITION TO [DOMAIN\WatcherDB_Service]
GRANT VIEW SERVER STATE TO [DOMAIN\WatcherDB_Service]

-- Para cada database user:
USE [database_name]
GRANT VIEW DEFINITION TO [DOMAIN\WatcherDB_Service]
```

---

### Erro: "Timeout expired"

**Causa:** Servidor com muitos databases ou queries lentas.

**Soluções:**
1. Aumentar timeout no código (padrão: 30s)
2. Verificar se há locks no servidor
3. Executar em horário de menor carga

---

### Dados não aparecem / Seção vazia

**Causa:** Nenhuma ocorrência encontrada (isso é bom!).

**Comportamento esperado:** Mensagem verde com ✅ indicando tudo OK.

Exemplo:
```
✅ Usuários Órfãos
✅ Nenhum usuário órfão detectado.
```

---

### Cache desatualizado

**Sintoma:** Dados não refletem mudanças recentes.

**Solução:**
1. Clicar no botão "⟳" (refresh) na aba
2. Ou aguardar 3 minutos para expiração do cache
3. Ou limpar cache manualmente no console:
```javascript
watcherPerformance.clearType('users')
```

---

## 🚀 PRÓXIMOS PASSOS (Futuro)

### Melhorias Planejadas

1. **Exportação de Dados**
   - Botão "Exportar CSV" para cada seção
   - Relatório PDF completo
   - Excel com múltiplas sheets

2. **Alertas Proativos**
   - Notificação quando órfãos detectados
   - Alert se sysadmin adicionado a conta de aplicação
   - Warning se login inativo por 90+ dias

3. **Histórico de Mudanças**
   - Tracking de quando usuários tornaram-se órfãos
   - Histórico de adições/remoções de roles críticos
   - Auditoria de mudanças de permissões

4. **Comparação Entre Servidores**
   - View consolidada de múltiplos servidores
   - Destacar inconsistências (ex: role só existe em alguns servers)

5. **Scripts Gerados Automaticamente**
   - Botão "Gerar Fix Script" para órfãos
   - Script de criação de login com mesmas permissões
   - Script de enable/disable de logins inativos

6. **Integração com Active Directory**
   - Validar se Windows logins ainda existem no AD
   - Detectar logins para usuários desligados
   - Sugerir conversão de logins individuais para grupos

---

## 📝 NOTAS DE IMPLEMENTAÇÃO

### Decisões de Design

**1. Sem Botões de Ação**

Decisão explícita do usuário: *"menos o Botão 'Corrigir Órfãos'... Quero essa aplicação mais para monitoria. As ações, os dbas fazem na base de dados."*

**Razão:** Segurança e controle. Ações automáticas em produção podem causar indisponibilidade.

---

**2. Seções Colapsáveis**

Inicialmente, apenas a seção de Órfãos fica expandida (pois é a mais crítica).

Usuário pode clicar nos cards ou headers para expandir outras seções.

**Razão:** UX - evitar scroll excessivo quando há muitos dados.

---

**3. TTL de 3 Minutos**

Dados de usuários mudam com frequência moderada:
- Mais que AlwaysOn (4 min)
- Menos que CPU (1 min)

**Razão:** Balanço entre freshness e performance.

---

**4. Exclusão de System Accounts**

Contas como `NT SERVICE\`, `NT AUTHORITY\`, `sa`, `##MS_*` são excluídas.

**Razão:** Reduzir ruído. DBAs focam em contas de usuários/aplicações.

---

### Compatibilidade

- **SQL Server:** 2012+ (usa `sys.dm_exec_sessions`, `sys.sql_logins`)
- **Browsers:** Chrome 90+, Firefox 88+, Edge 90+, Safari 14+
- **Python:** 3.8+
- **pyodbc:** 4.0+
- **ODBC Driver:** SQL Server 17+ (configurado em connection string)

---

### Segurança

**Permissões Necessárias:**

O login usado pelo WatcherDB precisa de:

```sql
-- Server-level
USE master
GRANT VIEW ANY DEFINITION TO [WatcherDB_Login]
GRANT VIEW SERVER STATE TO [WatcherDB_Login]

-- Cada database (ou via script dinâmico)
USE [database_name]
GRANT VIEW DEFINITION TO [WatcherDB_Login]
```

**Dados Sensíveis:**

- SIDs são exibidos como hexadecimal
- Senhas **NÃO** são exibidas (apenas metadata)
- Nenhuma informação confidencial é armazenada no cache client-side

---

## 🎉 CONCLUSÃO

A aba Users transforma o WatcherDB em uma ferramenta completa de auditoria de segurança de SQL Server, permitindo DBAs identificarem rapidamente:

✅ Usuários órfãos que causam erros de conexão
✅ Permissões excessivas que violam compliance
✅ Logins inativos que aumentam superfície de ataque
✅ Políticas de senha fracas que facilitam comprometimento
✅ Membros de roles críticos para auditoria periódica

Tudo isso em uma interface visual moderna, com cache inteligente e integração perfeita com o ecossistema WatcherDB existente.

---

**Documentação criada por:** Claude Code
**Data:** 20/11/2025
**Versão WatcherDB:** 1.4.8.4
**Responsável Técnico:** Salomão (DBA TAP)
