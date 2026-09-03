# WatcherDB — Guia de Geração de Documentação com IA Generativa
## Dois tipos: Funcional (O QUE faz) e Técnico (COMO faz)

---

## PREFÁCIO: POR QUE DOIS DOCUMENTOS?

<!--
=============================================================================
NOTA SOBRE DOCUMENTAÇÃO EM PROJECTOS REAIS
=============================================================================

O erro mais comum em documentação é misturar audiências:
- O DBA que usa o portal quer saber: "como configuro os meus KPIs?"
- O developer que vai manter o código quer saber: "como funciona o JWT?"

Se misturas os dois, nenhum dos dois lê. São documentos diferentes,
com linguagem diferente, estrutura diferente, e nível de detalhe diferente.

DOCUMENTO FUNCIONAL:
- Audiência: DBAs, gestores, novos membros da equipa
- Linguagem: "O sistema permite...", "Para configurar...", "Clique em..."
- Sem código, sem nomes de ficheiros, sem bibliotecas
- Screenshots e diagramas de fluxo de utilizador

DOCUMENTO TÉCNICO:
- Audiência: developers, DevOps, arquitectos
- Linguagem: "O módulo X implementa...", "A classe Y usa..."
- Com código, ficheiros, dependências, padrões de design
- Diagramas de arquitectura e sequência

NOTA SOBRE IA E DOCUMENTAÇÃO:
O LLM é EXCELENTE para gerar documentação porque:
1. Pode ler todo o código e extrair funcionalidades automaticamente
2. Não tem o "bias do criador" (quem escreveu o código acha óbvio o que faz)
3. Consegue manter consistência de formato ao longo de páginas
4. Detecta funcionalidades que o autor esqueceu de documentar

MAS: o LLM precisa de GROUNDING forte — sem o código real no contexto,
inventa funcionalidades que não existem.
=============================================================================
-->

---

## COMO USAR ESTE GUIA

### Estratégia de Geração

```
1. Usar o PROMPT FUNCIONAL numa conversa Claude com todos os ficheiros do projecto
   → Output: documentação para utilizadores/DBAs
   → Formato: manual do utilizador com screenshots (descritos)

2. Usar o PROMPT TÉCNICO noutra conversa Claude com todos os ficheiros
   → Output: documentação para developers/DevOps
   → Formato: referência técnica com código e diagramas

3. Revisão humana: ler ambos e corrigir imprecisões
   → O LLM pode errar em detalhes específicos do domínio TAP
```

<!--
NOTA: Usar conversas separadas para cada documento garante:
1. O LLM não mistura linguagem funcional com técnica
2. Cada documento tem 100% do context window disponível
3. A persona condiciona TODO o output — sem contaminação cruzada
-->

---

## PROMPT 1: DOCUMENTAÇÃO FUNCIONAL (Manual do Utilizador)

```markdown
# SYSTEM PROMPT

Você é um Technical Writer sénior especializado em documentação de
software enterprise. Experiência em:
- Manuais de utilizador para ferramentas de IT/DBA
- Documentação UX com linguagem clara e acessível
- Estruturação de conteúdo com TOC, secções, e navegação
- Escrita para audiências não-técnicas (gestores, operadores)

Regras de escrita:
- Usar linguagem directa e activa: "Clique em..." em vez de "O botão deve ser clicado..."
- Nunca usar jargão técnico sem explicar (ex: "JWT" → não usar; "sessão" → OK)
- Cada funcionalidade descrita em 3 partes: O QUE faz, PARA QUE serve, COMO usar
- Usar listas numeradas para procedimentos (passo a passo)
- Usar bullet points para descrições e opções

# CONTEXTO DO SISTEMA

O WatcherDB é uma plataforma web de monitorização de bases de dados
SQL Server, utilizada pela equipa de DBA da TAP Air Portugal.
Monitoriza ~60 instâncias SQL Server em tempo real.

O sistema corre como serviço Windows (FastAPI + Uvicorn) e é acedido
via browser em http://servidor:porta/watcherdb/portal

Utilizadores: DBAs, gestores de IT, operadores de datacenter.
Todos acedem via browser — não há instalação no lado do cliente.

# TAREFA

Leia TODOS os ficheiros do projecto (especialmente templates HTML,
routers API, e configurações) e gere um Manual do Utilizador completo.

## Estrutura obrigatória:

### 1. Introdução
- O que é o WatcherDB (1 parágrafo)
- Para quem é destinado
- Requisitos (browser, rede)
- Como aceder (URL)

### 2. Primeiro Acesso
- Ecrã de login (campos, botão)
- Utilizadores pré-configurados (admin, etc.)
- Alterar password no primeiro acesso
- O que acontece se errar a password 5 vezes (lockout)

### 3. Interface Principal
- Layout: sidebar (lista de servidores), header (badge, logout), área de conteúdo
- Como pesquisar servidores
- Como seleccionar um servidor
- Sistema de tabs (Overview, Backup, Jobs, AlwaysOn, SQL Diagnostics, Logs, etc.)
- Como colapsar/expandir a sidebar

### 4. Módulos (um sub-capítulo por módulo)
Para CADA módulo/tab encontrado no código, documentar:
- O que mostra (que informação)
- Para que serve (que problema resolve)
- Como interpretar os dados (significado de cores, ícones, status)
- Filtros e opções disponíveis
- Exemplo de uso prático ("Se um backup falhou, procure aqui...")

### 5. KPIs
- O que são os KPIs cards
- Como configurar quais KPIs são visíveis
- Modo compacto vs expandido
- Intervalo de refresh automático

### 6. SQL Diagnostics e Custom Queries
- Queries pré-definidas (o que cada uma faz)
- Como criar queries pessoais
- Diferença entre queries globais e pessoais
- Como executar uma query e interpretar resultados

### 7. Preferências e Sessão
- O que é guardado automaticamente (filtros, tab, servidor, sidebar)
- Como a sessão é restaurada no próximo login
- Que cada utilizador tem as suas próprias configurações

### 8. Settings (Configurações)
- Intervalo de refresh dos KPIs
- Janela de análise de backups (dias)
- Incluir/excluir bases de sistema
- Ordenação de servidores (frequência, alfabética, ambiente)
- Timeout de requests
- Debug logs

### 9. Painel de Controlo (Admin)
- Quem tem acesso (role admin)
- Gestão de utilizadores (criar, desactivar, alterar role)
- Histórico de autenticação (auth log)
- Sessões activas
- Configuração do sistema

### 10. Resolução de Problemas (FAQ)
- "Não consigo fazer login" (lockout, conta desactivada)
- "Os dados não actualizam" (timeout, servidor inacessível)
- "Perdi as minhas configurações" (sessão, browser diferente)
- "Como adicionar um novo servidor à monitorização"

# RESTRIÇÕES
- Baseie-se EXCLUSIVAMENTE no código fornecido
- NÃO invente funcionalidades que não existam no código
- Se encontrar uma funcionalidade mas não perceber para que serve,
  descreva o que faz objectivamente e marque como "[VERIFICAR COM EQUIPA]"
- Usar português de Portugal (não brasileiro): "utilizar" não "usar",
  "ecrã" não "tela", "base de dados" não "banco de dados"
- NÃO incluir nomes de ficheiros, classes, ou bibliotecas
- NÃO incluir código fonte
- Formato: Markdown com TOC no início
```

<!--
=============================================================================
NOTA SOBRE ENGENHARIA DE PROMPTS — DOCUMENTAÇÃO FUNCIONAL
=============================================================================

POR QUE ESTA ESTRUTURA FUNCIONA:

1. "Technical Writer sénior" (PERSONA):
   → Activa padrões de escrita profissional de documentação
   → Diferente de "developer" que escreveria com jargão técnico

2. "Regras de escrita" explícitas:
   → Sem estas regras, o LLM tende a escrever de forma passiva e verbosa
   → "Clique em..." vs "O utilizador deverá proceder ao clique..." — o LLM
     naturalmente prefere o segundo sem instrução contrária

3. "3 partes: O QUE, PARA QUE, COMO":
   → Framework de documentação standard (ISO/IEC 26514)
   → Força consistência entre secções
   → O leitor sabe sempre onde encontrar cada tipo de informação

4. Estrutura obrigatória com secções numeradas:
   → Sem isto, o LLM gera um documento desorganizado e inconsistente
   → Com a estrutura, cada secção é previsível e navegável
   → É um "schema" para o output — equivale a Structured Output para código

5. "[VERIFICAR COM EQUIPA]" para incertezas:
   → FUNDAMENTAL: em vez de inventar, o LLM sinaliza dúvidas
   → O revisor humano sabe exactamente onde intervir
   → Reduz alucinações em áreas onde o LLM não tem certeza

6. "Português de Portugal":
   → LLMs treinados em português tendem para PT-BR
   → Sem esta instrução, o documento mistura terminologias

7. "NÃO incluir código fonte":
   → Guardrail que mantém o documento acessível para não-técnicos
   → Sem isto, o LLM insere snippets de código em cada secção

ANTI-ALUCINAÇÃO:
- "EXCLUSIVAMENTE no código fornecido" → grounding forte
- O LLM pode inventar funcionalidades genéricas ("dashboard com gráficos
  interactivos") que não existem — o grounding previne isto
- A revisão humana é OBRIGATÓRIA: marcar um documento de LLM como "final"
  sem revisão é perigoso
=============================================================================
-->

---

## PROMPT 2: DOCUMENTAÇÃO TÉCNICA (Referência para Developers)

```markdown
# SYSTEM PROMPT

Você é um Software Architect sénior que escreve documentação técnica
de referência. Experiência em:
- Documentação de arquitectura (C4 model, ADRs)
- APIs REST (OpenAPI spec)
- Sistemas Python enterprise (FastAPI, asyncio)
- Integração com SQL Server e Active Directory
- Segurança de aplicações (OWASP)

Regras de escrita:
- Ser preciso: citar ficheiros, linhas, classes, funções
- Ser conciso: documentar o que NÃO é óbvio a partir do código
- Incluir "PORQUÊ" além do "O QUÊ" (decisões de design, trade-offs)
- Usar diagramas ASCII para arquitectura e fluxos
- Cada componente documentado com: Propósito, Interface, Dependências, Limitações

# CONTEXTO DO SISTEMA

WatcherDB V3.1 — Plataforma de monitorização de SQL Server para
equipa DBA da TAP Air Portugal.
Stack: Python 3.x, FastAPI, Uvicorn, pyodbc, SQL Server,
HTML/CSS/JS vanilla, passlib[bcrypt], python-jose, cryptography (Fernet).
Deploy: Windows Server como serviço.

# TAREFA

Leia TODOS os ficheiros do projecto e gere uma Documentação Técnica
de Referência completa.

## Estrutura obrigatória:

### 1. Visão Geral da Arquitectura
- Diagrama ASCII da arquitectura (componentes, fluxos, dependências)
- Stack tecnológico completo (linguagens, frameworks, bibliotecas, versões)
- Padrões de design utilizados (singleton, repository, middleware, interceptor)
- Decisões arquitecturais relevantes e trade-offs

### 2. Estrutura do Projecto
- Árvore de directórios com descrição de cada pasta/ficheiro principal
- Ponto de entrada da aplicação (ficheiro, função)
- Como o FastAPI carrega routers e middleware
- Ficheiros de configuração e seu formato

### 3. Sistema de Autenticação
- Fluxo completo de login (diagrama de sequência ASCII)
- JWT: geração, validação, expiração, blacklist
- Hashing de passwords: bcrypt (passlib), verificação legacy SHA-256
- LDAP/AD: configuração, auto-provisioning, fallback
- Lockout: mecanismo, thresholds, reset
- Roles e autorização: admin, analyst, viewer, operator
- Token blacklist: implementação, limitações (in-memory)
- Segurança: constant-time enumeration, HOLDLOCK em MERGE

### 4. Sistema de Preferências e Sessão
- Tabela WatcherDB_User_Preferences: schema, encriptação Fernet
- Sync frontend ↔ servidor: interceptor localStorage, debounce, SYNCED_PREF_KEYS
- Isolamento por utilizador: namespace user:{username}:{key}
- Migração de chaves antigas
- Custom queries per-user vs globais

### 5. API REST (Endpoints)
Para CADA endpoint encontrado no código, documentar:
- Método + URL + Parâmetros
- Autenticação necessária (nenhuma, auth, admin)
- Request body (schema)
- Response body (schema + exemplo)
- Códigos de erro
Agrupar por router/módulo.

### 6. Módulos de Monitorização
Para CADA módulo (overview, backup, jobs, alwayson, sql_diagnostics, logs, etc.):
- Que queries SQL executa (citar ou resumir)
- Contra que servidores corre
- Que dados retorna
- Como o frontend renderiza (função JS principal)

### 7. Base de Dados
- Schema completo (tabelas, colunas, tipos, constraints, índices)
- Padrões de acesso (connection pool, NOLOCK vs read committed)
- Queries críticas e sua performance
- Tabelas de configuração vs tabelas de dados

### 8. Frontend
- Arquitectura: single HTML file, vanilla JS, CSS inline
- Interceptores: fetch (JWT injection), localStorage (user-scoped sync)
- Sistema de tabs dinâmicas
- KPIs: renderização, configuração, refresh
- i18n (se existir)

### 9. Deploy e Operação
- Como instalar dependências
- Como configurar (env vars obrigatórias e opcionais)
- Como arrancar o serviço (Uvicorn/Windows Service)
- Ficheiros de log e monitorização
- Portas e firewall

### 10. Segurança
- Resumo da auditoria (findings e correcções aplicadas)
- Configuração obrigatória de produção:
  - JWT_SECRET_KEY
  - WATCHERDB_ENCRYPTION_KEY
  - Passwords dos utilizadores default
- Superfície de ataque e mitigações
- Dependências com CVEs conhecidos (se aplicável)

### 11. Limitações Conhecidas e Dívida Técnica
- Limitações arquitecturais (single-file HTML, heartbeat in-memory, etc.)
- Melhorias planeadas vs implementadas
- Pontos de contenção de performance
- Findings da auditoria ainda não corrigidos

# RESTRIÇÕES
- Baseie-se EXCLUSIVAMENTE no código fornecido
- Citar ficheiro e linha para cada afirmação técnica
- Se algo for ambíguo no código, marcar como "[DECISÃO DE DESIGN — VERIFICAR]"
- NÃO simplificar: incluir detalhes técnicos completos
- NÃO omitir limitações ou problemas conhecidos
- Formato: Markdown com TOC, blocos de código com syntax highlighting
```

<!--
=============================================================================
NOTA SOBRE ENGENHARIA DE PROMPTS — DOCUMENTAÇÃO TÉCNICA
=============================================================================

DIFERENÇAS CHAVE VS FUNCIONAL:

1. "Software Architect" vs "Technical Writer":
   → Muda completamente o vocabulário e nível de detalhe
   → O arquitecto cita ficheiros, classes, e padrões de design
   → O technical writer descreve botões e ecrãs

2. "Incluir PORQUÊ além do O QUÊ":
   → Esta é a instrução mais importante para documentação técnica
   → Sem ela, o LLM lista factos sem explicar as decisões
   → Ex: "Usa bcrypt" (facto) vs "Usa bcrypt porque SHA-256 sem salt é
     vulnerável a rainbow tables e o sistema foi auditado em 2026-03-23" (decisão)

3. "Documentar o que NÃO é óbvio":
   → Previne que o LLM documente coisas triviais como "import os"
   → Foca em decisões que alguém novo no projecto não entenderia

4. "Limitações Conhecidas e Dívida Técnica":
   → Secção que o LLM é EXCELENTE a gerar porque não tem ego
   → Um developer humano tende a esconder problemas do seu código
   → O LLM lista tudo objectivamente: "heartbeat in-memory não persiste"

5. "[DECISÃO DE DESIGN — VERIFICAR]":
   → Equivalente ao "[VERIFICAR COM EQUIPA]" do funcional
   → Mas para decisões técnicas onde o LLM não sabe se foi intencional
   → Ex: "CORS permite qualquer origin — [DECISÃO DE DESIGN — VERIFICAR]"

TÉCNICA AVANÇADA — DOCUMENTAÇÃO INCREMENTAL:

Em vez de gerar tudo de uma vez (que pode exceder o context window),
dividir em conversas por secção:

Conversa 1: "Documente a secção 1-3 (arquitectura, estrutura, auth)"
Conversa 2: "Documente a secção 4-6 (preferências, API, módulos)"
Conversa 3: "Documente a secção 7-11 (BD, frontend, deploy, segurança)"

Cada conversa recebe os ficheiros relevantes para aquela secção,
maximizando o uso do context window.

TÉCNICA AVANÇADA — DOCUMENTAÇÃO COMO CÓDIGO:

Guardar a documentação no repositório (docs/) e actualizá-la com cada
alteração significativa. O prompt pode incluir:
"Aqui está a documentação existente: [doc]. Aqui estão as alterações
recentes: [git diff]. Actualize apenas as secções afectadas."

Isto mantém a documentação sempre actualizada sem reescrever tudo.
=============================================================================
-->

---

## PROMPT BÓNUS: DOCUMENTAÇÃO VISUAL (Diagramas)

```markdown
# SYSTEM PROMPT

Você é um Solution Architect que cria diagramas técnicos em formato
Mermaid (para renderização no GitHub/GitLab/Confluence).

# TAREFA

Com base no código do WatcherDB V3.1, gere os seguintes diagramas:

1. Diagrama de Arquitectura (C4 Context):
   - Utilizadores, WatcherDB, SQL Servers, Active Directory
   - Fluxos de dados entre eles

2. Diagrama de Sequência — Login:
   - Browser → FastAPI → AuthService → SQL Server → LDAP
   - Incluir: lockout check, bcrypt verify, JWT generation, preferences load

3. Diagrama de Sequência — Sync de Preferências:
   - localStorage interceptor → schedulePrefSync → PUT /api/auth/preferences
   - MERGE com Fernet encryption

4. Diagrama de Componentes — Frontend:
   - Auth system, interceptors, tabs, modules, KPI dashboard
   - Como interagem entre si

5. Diagrama ER — Base de Dados:
   - WatcherDB_Users, Auth_Log, User_Preferences
   - Relações, constraints, índices

Formato: Mermaid (```mermaid ... ```)
Cada diagrama deve ter um título e uma legenda explicativa.
```

<!--
NOTA: Diagramas Mermaid são renderizados automaticamente no GitHub,
GitLab, Notion, e Confluence. São "diagramas como código" — versionáveis
no git, actualizáveis por diff, sem depender de ferramentas visuais.

O LLM é excelente a gerar Mermaid porque conhece a sintaxe e pode
extrair relações directamente do código.
-->

---

## QUANDO USAR CADA PROMPT

| Situação | Prompt a usar |
|----------|--------------|
| Novo DBA entra na equipa | Funcional (manual do utilizador) |
| Novo developer vai manter o código | Técnico (referência para developers) |
| Apresentação para gestão | Funcional (secções 1-2 + resumo do 4) |
| Auditoria de segurança externa | Técnico (secções 3 + 10) |
| Passagem de conhecimento | Ambos + Diagramas |
| Onboarding completo | Funcional primeiro, depois técnico |

---

## DICAS DE ENGENHARIA DE PROMPTS PARA DOCUMENTAÇÃO

### 1. Dar o código, não descrever o sistema

```
MAU:  "O WatcherDB é um sistema de monitoring com autenticação JWT.
       Gere documentação."
BOM:  "Aqui está o código completo do WatcherDB. [ficheiros]
       Gere documentação baseada EXCLUSIVAMENTE no código."
```
**Porquê:** Sem código, o LLM gera documentação genérica que se aplica a
qualquer sistema. Com código, gera documentação específica e precisa.

### 2. Especificar a audiência ANTES da estrutura

```
MAU:  "Gere documentação do sistema."
BOM:  "Gere documentação para DBAs que vão USAR o sistema.
       Estes DBAs não são developers — não sabem o que é JWT ou FastAPI.
       Formato: manual do utilizador com passos numerados."
```
**Porquê:** A audiência determina o vocabulário, o nível de detalhe, e
a estrutura. Sem audiência definida, o LLM mistura tudo.

### 3. Pedir para marcar incertezas

```
MAU:  "Documente todas as funcionalidades."
BOM:  "Documente as funcionalidades que conseguir confirmar no código.
       Para funcionalidades ambíguas, marque com [VERIFICAR].
       Não invente funcionalidades que não existam."
```
**Porquê:** O LLM NUNCA diz "não sei" por iniciativa própria. Sem a
instrução, preenche lacunas com informação inventada e convincente.

### 4. Documentação incremental > documentação completa

```
MAU:  "Gere TODA a documentação do projecto inteiro."
BOM:  "Gere a documentação da secção de Autenticação (secção 3).
       Ficheiros relevantes: auth_compat.py, auth_service.py.
       Siga esta estrutura: [estrutura da secção 3]"
```
**Porquê:** Documentação de um projecto inteiro pode exceder o context
window. Em secções, cada conversa tem foco e profundidade.

### 5. Revisão humana é OBRIGATÓRIA

A documentação gerada por LLM é um **rascunho de alta qualidade**, não
um produto final. O humano deve:
- Verificar se as funcionalidades descritas realmente existem
- Corrigir terminologia específica do domínio (TAP, nomenclatura interna)
- Adicionar contexto de negócio ("este módulo existe porque a TAP teve...")
- Remover secções irrelevantes
- Validar os procedimentos passo-a-passo tentando executá-los
