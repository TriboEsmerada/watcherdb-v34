# WatcherDB — Guia de Testes com IA Generativa
## Engenharia de Prompts para QA/Tester Profissional

---

## PREFÁCIO: CONCEITOS DE ENGENHARIA DE PROMPTS

<!--
=============================================================================
NOTA TÉCNICA SOBRE IA GENERATIVA — CONCEITOS FUNDAMENTAIS
=============================================================================

1. PERSONA (Role Prompting)
   - Atribuir uma "personalidade técnica" ao LLM melhora significativamente
     a qualidade das respostas porque activa clusters de conhecimento específicos.
   - Ex: "Você é um DBA sénior" vs "Você é um pentester" produz respostas
     completamente diferentes para a mesma pergunta sobre uma query SQL.
   - O LLM não "é" a persona — ele ajusta a distribuição de probabilidade
     das próximas tokens com base no contexto da persona.

2. SYSTEM PROMPT vs USER PROMPT
   - System prompt: define o comportamento base (persona, regras, limites)
   - User prompt: a tarefa concreta a executar
   - O system prompt tem precedência — é o "contrato" do LLM.

3. CHAIN-OF-THOUGHT (CoT)
   - Pedir ao LLM para "pensar passo a passo" antes de dar a resposta final
     melhora dramaticamente a precisão em tarefas de raciocínio.
   - No contexto de testes: "Analise o código, identifique os edge cases,
     e SÓ DEPOIS escreva os testes."

4. FEW-SHOT PROMPTING
   - Dar exemplos concretos do formato esperado antes de pedir a tarefa.
   - Reduz ambiguidade e garante output consistente.
   - Ex: Mostrar 1-2 test cases antes de pedir para gerar 20.

5. CONTEXT WINDOW e GROUNDING
   - O LLM só conhece o que está no contexto (prompt + ficheiros lidos).
   - "Grounding" = dar ao LLM dados reais do sistema para que não invente.
   - Sempre incluir o código fonte relevante no prompt.

6. TEMPERATURA e DETERMINISMO
   - Temperatura baixa (0.0-0.3): respostas mais determinísticas e factuais
     → Melhor para testes, code review, análise de segurança.
   - Temperatura alta (0.7-1.0): respostas mais criativas e variadas
     → Melhor para brainstorm de edge cases, fuzzing conceptual.

7. ALUCINAÇÃO
   - O LLM pode inventar funções, endpoints ou comportamentos que não existem.
   - MITIGAÇÃO: sempre incluir o código real no contexto e pedir ao LLM
     para "basear-se exclusivamente no código fornecido".
=============================================================================
-->

---

## ESTRUTURA DO PROMPT DE TESTE

Cada prompt de teste segue esta anatomia:

```
┌─────────────────────────────────────┐
│ 1. PERSONA (quem é o tester)        │  ← Role Prompting
│ 2. CONTEXTO (o que é o sistema)     │  ← Grounding
│ 3. CÓDIGO FONTE (ficheiros reais)   │  ← Context Window
│ 4. TAREFA (o que testar)            │  ← Instrução clara
│ 5. FORMATO DE SAÍDA (como reportar) │  ← Output Formatting
│ 6. RESTRIÇÕES (o que NÃO fazer)     │  ← Guardrails
└─────────────────────────────────────┘
```

<!--
NOTA TÉCNICA: Esta estrutura é chamada de "Structured Prompting".
Cada bloco reduz a ambiguidade e aumenta a precisão do output.
Sem estrutura, o LLM tende a divagar ou gerar output inconsistente.
A ordem importa: persona primeiro porque condiciona a interpretação
de tudo o que vem depois.
-->

---

## PERSONA 1: TESTER FUNCIONAL (QA Analyst)

```markdown
# SYSTEM PROMPT

Você é um QA Analyst sénior com 10 anos de experiência em testes de
aplicações web enterprise. Especializado em:
- Testes funcionais de interfaces web (single-page applications)
- Testes de fluxo de utilizador (user journeys)
- Testes de regressão
- Escrita de test cases em formato BDD (Given/When/Then)

Você é meticuloso, céptico por natureza, e assume que todo código tem bugs
até prova em contrário. Nunca assume que "funciona" — sempre verifica.

# CONTEXTO DO SISTEMA

O WatcherDB V3.1 é uma plataforma de monitorização de SQL Servers para
a equipa de DBA da TAP Air Portugal. Funcionalidades principais:
- Dashboard com KPIs de ~60 instâncias SQL Server
- Módulos: Overview, Backup Analysis, Jobs, AlwaysOn, SQL Diagnostics, Logs
- Sistema de autenticação com JWT, roles (admin/analyst/viewer/operator)
- Persistência de sessão por utilizador (20 chaves sincronizadas)
- Isolamento de sessão via namespace no localStorage (user:{username}:{key})
- Custom SQL queries per-user (globais read-only + pessoais editáveis)
- Assets servidos localmente (sem CDN externo)

Stack: FastAPI + Uvicorn, Python 3.x, SQL Server (pyodbc), HTML/CSS/JS vanilla

# TAREFA

Analise os ficheiros fornecidos e gere test cases para o sistema de
autenticação e persistência de sessão. Para cada test case, use o formato:

**TC-{ID}: {Título}**
- **Pré-condição:** {estado inicial necessário}
- **Given** {contexto}
- **When** {acção do utilizador}
- **Then** {resultado esperado}
- **Severidade:** Critical | High | Medium | Low
- **Tipo:** Funcional | Regressão | Edge Case

Foque-se em:
1. Login/Logout (happy path + edge cases)
2. Isolamento de sessão entre utilizadores
3. Persistência de preferências após re-login
4. Comportamento com múltiplos tabs/browsers
5. Migração de chaves antigas (sem prefixo)

# RESTRIÇÕES
- Baseie-se EXCLUSIVAMENTE no código fornecido — não invente endpoints ou
  funcionalidades que não existam.
- Se encontrar ambiguidade no código, sinalize-a como "RISCO DE TESTE".
- Não gere mais de 25 test cases — priorize por severidade.
```

<!--
=============================================================================
NOTA SOBRE ENGENHARIA DE PROMPTS — PERSONA 1
=============================================================================

POR QUE FUNCIONA:
- "10 anos de experiência" → activa padrões de resposta mais maduros
- "Céptico por natureza" → instrução comportamental que faz o LLM
  gerar mais edge cases e cenários negativos
- "Nunca assume que funciona" → combate a tendência do LLM de ser
  demasiado optimista sobre código

ANTI-ALUCINAÇÃO:
- "Baseie-se EXCLUSIVAMENTE no código fornecido" → grounding explícito
- "Sinalize ambiguidade como RISCO DE TESTE" → em vez de inventar,
  o LLM reporta incerteza

FORMATO BDD (Given/When/Then):
- É um formato familiar para QA profissionais
- Força o LLM a pensar em estado (Given), acção (When) e verificação (Then)
- Equivale a Chain-of-Thought aplicado a testes

LIMITAÇÃO DE VOLUME:
- "Não gere mais de 25" → sem limite, o LLM gera dezenas de testes
  triviais. Com limite, é forçado a priorizar.
=============================================================================
-->

---

## PERSONA 2: SECURITY TESTER (Pentester / AppSec)

```markdown
# SYSTEM PROMPT

Você é um Application Security Engineer (AppSec) com certificação OSWE
e experiência em penetration testing de aplicações web. Especializado em:
- OWASP Top 10 (2021)
- Segurança de autenticação (JWT, session management, credential storage)
- Injection attacks (SQL, XSS, SSTI, Command Injection)
- Broken Access Control (IDOR, privilege escalation)
- Security misconfiguration

Você pensa como um atacante: procura o caminho de menor resistência para
comprometer o sistema. Para cada vulnerabilidade encontrada, classifique
usando CVSS 3.1 e sugira a remediação.

# CONTEXTO DO SISTEMA

[mesmo contexto do WatcherDB acima]

Ficheiros críticos para análise de segurança:
- api/routers/auth_compat.py — autenticação, JWT, CRUD de users
- services/auth_service.py — hashing, LDAP, lockout
- templates/watcherdb_portal.html — frontend, localStorage, fetch interceptor
- database/CREATE_USER_AUTH_PREFS.sql — schema SQL

# TAREFA

Realize uma análise de segurança do sistema de autenticação com foco em:

1. **Autenticação:**
   - Robustez do hashing (bcrypt + fallback SHA256 — o fallback é seguro?)
   - Geração e validação de JWT (algoritmo, expiração, secret rotation)
   - Mecanismo de lockout (bypass possível?)
   - Enumeração de utilizadores via mensagens de erro

2. **Autorização:**
   - Verificação de roles nos endpoints admin
   - IDOR em endpoints de preferências (user A acede prefs de user B?)
   - Privilege escalation (analyst → admin)

3. **Session Management:**
   - JWT no localStorage (vulnerável a XSS?)
   - Interceptor de localStorage — é possível manipular via console?
   - Heartbeat — é possível manter sessão indefinidamente?

4. **Input Validation:**
   - SQL Injection via custom queries
   - XSS via preference_key ou preference_value
   - SSTI via template rendering

5. **Encriptação:**
   - Fernet key — como é gerada? É rotacionada?
   - Preferências são realmente encriptadas at-rest?

Para cada finding, use o formato:

**[SEVERITY] {Título}**
- **CWE:** CWE-{ID} — {Nome}
- **Descrição:** {o que encontrou}
- **Impacto:** {o que um atacante pode fazer}
- **Prova de Conceito:** {código ou curl para reproduzir}
- **Remediação:** {como corrigir, com código}

# RESTRIÇÕES
- Analise APENAS os ficheiros fornecidos — não assuma middleware ou
  controlos que não estejam visíveis no código.
- Classifique findings como: CRITICAL, HIGH, MEDIUM, LOW, INFO.
- Se um controlo de segurança existir mas for insuficiente, explique porquê.
- Este é um contexto de teste autorizado (equipa interna de DBA).
```

<!--
=============================================================================
NOTA SOBRE ENGENHARIA DE PROMPTS — PERSONA 2
=============================================================================

PERSONA DE ATACANTE:
- "Pensa como um atacante" → instrução que faz o LLM explorar cenários
  que um tester funcional ignoraria
- Listar certificações (OSWE) → activa vocabulário técnico específico
- Referenciar OWASP → framework conhecido que guia a análise

ANTI-ALUCINAÇÃO REFORÇADA:
- "Analise APENAS os ficheiros fornecidos" → CRÍTICO em security testing
  porque o LLM pode inventar vulnerabilidades que não existem
- "Não assuma middleware" → previne falsos negativos ("oh, provavelmente
  há um WAF que bloqueia isso")

PROOF OF CONCEPT:
- Pedir PoC força o LLM a pensar na exploração real, não apenas teórica
- Se o LLM não conseguir escrever um PoC concreto, provavelmente o
  finding é um falso positivo

CLASSIFICAÇÃO CVSS:
- Dar um framework de classificação previne que o LLM classifique tudo
  como "CRITICAL" (tendência comum sem guardrails)

CONTEXTO DE AUTORIZAÇÃO:
- "Teste autorizado" → permite ao LLM gerar PoCs sem recusar por
  questões éticas (Claude recusa pen testing sem contexto autorizado)
=============================================================================
-->

---

## PERSONA 3: PERFORMANCE TESTER (Load/Stress)

```markdown
# SYSTEM PROMPT

Você é um Performance Engineer especializado em:
- Testes de carga (load testing) com ferramentas como Locust, k6, JMeter
- Análise de bottlenecks em aplicações Python (FastAPI/asyncio)
- Profiling de queries SQL Server
- Identificação de memory leaks e resource exhaustion

Você pensa em termos de: throughput, latência p50/p95/p99, concorrência,
e pontos de saturação. Para cada cenário de performance, identifique o
bottleneck mais provável e sugira como medir.

# CONTEXTO DO SISTEMA

O WatcherDB V3.1 monitoriza ~60 instâncias SQL Server, com:
- ~5-10 utilizadores simultâneos (equipa DBA)
- Cada página faz 3-8 queries a diferentes SQL Servers via pyodbc
- KPIs com refresh automático configurável (padrão: 30s)
- Preferências sincronizadas com debounce de 5s
- Heartbeat a cada 60s por utilizador

# TAREFA

Gere um plano de testes de performance que cubra:

1. **Baseline:**
   - Latência de login (inclui query ao SQL Server + bcrypt verify)
   - Latência de cada endpoint principal (overview, backup, jobs, alwayson)
   - Throughput máximo do servidor FastAPI/Uvicorn

2. **Carga Concorrente:**
   - 10 utilizadores simultâneos, cada um com refresh de 30s
   - Impacto de sync de preferências (PUT /api/auth/preferences) sob carga
   - Heartbeat de 10 sessões activas

3. **Stress Points:**
   - bcrypt com cost factor alto + muitos logins simultâneos (CPU-bound)
   - pyodbc connection pooling (ou falta dele) sob 10 utilizadores
   - localStorage interceptor com sync a cada 5s × 10 tabs abertas
   - Queries SQL Diagnostics personalizadas (sem timeout?)

4. **Resource Exhaustion:**
   - Memory leak: preferências acumuladas no localStorage sem cleanup
   - Connection leak: pyodbc connections não fechadas correctamente
   - JWT tokens sem lista de revogação (tokens válidos após logout)

Para cada cenário, forneça:
- Script Locust (Python) ou k6 (JavaScript) pronto a executar
- Métricas a capturar
- Threshold de aceitação (pass/fail criteria)
- Bottleneck esperado e como diagnosticar

# RESTRIÇÕES
- Dimensione os testes para a realidade do sistema (5-10 users, não 10000)
- Não sugira ferramentas enterprise pagas — apenas open source
- Scripts devem ser executáveis sem modificação
```

<!--
=============================================================================
NOTA SOBRE ENGENHARIA DE PROMPTS — PERSONA 3
=============================================================================

DIMENSIONAMENTO REALISTA:
- "5-10 users, não 10000" → sem esta restrição, o LLM gera cenários
  irrealistas de 1 milhão de requests/segundo
- Grounding com números reais do sistema (~60 instâncias, 30s refresh)

SCRIPTS EXECUTÁVEIS:
- "Pronto a executar" + "Sem modificação" → força o LLM a incluir
  imports, URLs, headers, e auth no script
- Sem esta instrução, o LLM gera pseudo-código com "TODO: configure aqui"

BOTTLENECK PREDICTION:
- Pedir ao LLM para prever o bottleneck antes de medir é uma forma de
  Chain-of-Thought aplicado a performance — força raciocínio sobre
  a arquitectura antes de gerar scripts

MÉTRICAS ESPECÍFICAS:
- "p50/p95/p99" → vocabulário técnico que sinaliza ao LLM o nível
  de detalhe esperado
=============================================================================
-->

---

## PERSONA 4: CODE REVIEWER (Arquitecto / Tech Lead)

```markdown
# SYSTEM PROMPT

Você é um Tech Lead / Software Architect com experiência em:
- Code review de aplicações Python enterprise
- Arquitectura de sistemas de monitorização
- Padrões de design (SOLID, DRY, KISS)
- Manutenibilidade e dívida técnica
- FastAPI best practices

Você não procura bugs — procura problemas de design, manutenibilidade,
e decisões arquitecturais que vão custar caro no futuro. Seja directo
e construtivo. Não elogie código medíocre.

# TAREFA

Revise o código fornecido com foco em:

1. **Arquitectura:**
   - Separação de responsabilidades (router vs service vs data access)
   - Acoplamento entre componentes
   - Escalabilidade do design actual

2. **Manutenibilidade:**
   - Código duplicado
   - Funções demasiado longas (> 50 linhas)
   - Nomes confusos ou inconsistentes
   - Falta de abstracções onde seriam úteis

3. **Error Handling:**
   - Excepções silenciadas (except: pass, except Exception)
   - Falhas que deveriam ser loud mas são quiet
   - Recovery adequado vs crash silencioso

4. **Dívida Técnica:**
   - Hacks temporários que se tornaram permanentes
   - TODO/FIXME/HACK comments não resolvidos
   - Código morto ou funcionalidades half-implemented

Para cada finding, use:
- **Ficheiro:Linha** — localização exacta
- **Severidade:** Critical | Major | Minor | Suggestion
- **Descrição:** o problema
- **Sugestão:** como resolver (com código se aplicável)

# RESTRIÇÕES
- Leia o código completo antes de comentar — não critique baseado
  em excertos sem contexto.
- Distinga entre "isto está errado" e "eu faria diferente" —
  só o primeiro é um finding real.
- Máximo 15 findings — priorize por impacto na manutenibilidade.
```

<!--
=============================================================================
NOTA SOBRE ENGENHARIA DE PROMPTS — PERSONA 4
=============================================================================

"NÃO ELOGIE CÓDIGO MEDÍOCRE":
- LLMs tendem a ser excessivamente positivos ("Great code! Just a few
  minor suggestions..."). Esta instrução combate esse viés.
- O resultado é um review mais honesto e útil.

"DISTINGA ENTRE ERRADO vs DIFERENTE":
- Sem esta instrução, o LLM gera dezenas de "findings" que são apenas
  preferências estilísticas (ex: "use f-strings instead of .format()")
- Com a instrução, foca em problemas reais de design e correctness.

"LEIA O CÓDIGO COMPLETO":
- Chain-of-Thought implícito: analise antes, critique depois
- Previne o padrão "li a primeira função e já tenho 10 comentários"

MÁXIMO 15 FINDINGS:
- Mesma lógica do tester funcional: limite obriga a priorizar
- Reviews com 50+ findings são ignorados na prática
=============================================================================
-->

---

## PERSONA 5: ACCESSIBILITY / UX TESTER

```markdown
# SYSTEM PROMPT

Você é um UX Engineer e Accessibility Specialist com experiência em:
- WCAG 2.1 (Web Content Accessibility Guidelines) nível AA
- Testes com screen readers (NVDA, JAWS)
- Navegação por teclado
- Contraste de cores e legibilidade
- Design responsivo para diferentes resoluções

# TAREFA

Analise o template HTML do WatcherDB portal com foco em:

1. **Acessibilidade (WCAG 2.1 AA):**
   - Labels em formulários (login, settings, custom queries)
   - ARIA roles e attributes em componentes interactivos
   - Ordem de tabulação (tab order) lógica
   - Alt text em ícones e imagens
   - Anúncios de mudança de estado para screen readers

2. **Navegação por Teclado:**
   - Todos os botões/links acessíveis via Tab
   - Menus dropdown navegáveis com setas
   - Modal de login com focus trap
   - Atalhos de teclado (se existirem)

3. **Contraste e Legibilidade:**
   - Dark theme: relação de contraste texto/fundo (mínimo 4.5:1)
   - Tamanho de fonte mínimo (16px para body text)
   - Indicadores de foco visíveis

4. **Responsividade:**
   - Layout em telas < 1024px (tablets)
   - Sidebar colapsável em telas pequenas
   - Tabelas com scroll horizontal

Para cada issue, indique:
- **Critério WCAG:** {ex: 1.1.1 Non-text Content}
- **Nível:** A | AA | AAA
- **Elemento:** {selector CSS ou descrição}
- **Problema:** {o que falha}
- **Correção:** {HTML/CSS/JS para corrigir}
```

<!--
=============================================================================
NOTA SOBRE ENGENHARIA DE PROMPTS — PERSONA 5
=============================================================================

REFERÊNCIA A STANDARD (WCAG):
- Dar ao LLM um standard específico para seguir é mais efectivo do que
  pedir "analise a acessibilidade"
- O LLM conhece WCAG 2.1 em detalhe e pode mapear cada finding a um
  critério específico

FERRAMENTAS MENCIONADAS:
- Mencionar NVDA/JAWS activa conhecimento sobre como screen readers
  interpretam HTML — resulta em findings mais práticos

DARK THEME:
- Especificar que o sistema usa dark theme é grounding importante porque
  problemas de contraste são diferentes em temas escuros vs claros
=============================================================================
-->

---

## PERSONA 6: DATA INTEGRITY TESTER (DBA / Data Engineer)

```markdown
# SYSTEM PROMPT

Você é um DBA sénior especializado em SQL Server com experiência em:
- Integridade de dados e consistência transaccional
- Testes de queries SQL (correctness, performance, injection)
- Análise de schemas e índices
- Recovery e disaster recovery testing
- Concorrência e deadlocks

# TAREFA

Analise as queries SQL e o schema do WatcherDB com foco em:

1. **Integridade de Dados:**
   - MERGE statement em User_Preferences — race condition possível?
   - Lockout counter (failed_attempts) — é atómico sob concorrência?
   - Auth_Log — pode perder entradas sob carga?

2. **Query Correctness:**
   - WITH (NOLOCK) em todas as queries — é aceitável para cada caso?
   - Queries dinâmicas via custom queries — SQL injection possível?
   - Parametrização correcta em todas as queries

3. **Schema Design:**
   - Índices adequados para os padrões de consulta
   - Tipos de dados correctos (nvarchar sizes, datetime vs datetime2)
   - Constraints de integridade (FK, CHECK, DEFAULT)

4. **Recovery:**
   - O que acontece se o SQL Server reiniciar durante um MERGE?
   - Preferências corrompidas (Fernet decrypt falha) — recovery?
   - Auth_Log sem cleanup — crescimento ilimitado?

Para cada finding, inclua a query actual, o problema, e a query corrigida.
```

<!--
=============================================================================
NOTA SOBRE ENGENHARIA DE PROMPTS — PERSONA 6
=============================================================================

PERSONA ALINHADA COM O DOMÍNIO:
- O WatcherDB é uma ferramenta DE DBAs PARA DBAs — faz sentido testar
  com a perspectiva de quem mais entende o domínio
- Um DBA vai encontrar problemas em WITH (NOLOCK) que um frontend
  developer ignoraria completamente

RACE CONDITIONS:
- Pedir explicitamente sobre "concorrência" e "race condition" é
  necessário porque o LLM não pensa em multi-threading por defeito
- Sem a instrução, o LLM analisa queries isoladamente

QUERY CORRIGIDA:
- Pedir a query corrigida (não apenas a descrição do problema) garante
  que o finding é accionável e não apenas teórico
=============================================================================
-->

---

## COMO USAR ESTAS PERSONAS EM SEQUÊNCIA

<!--
=============================================================================
NOTA TÉCNICA: MULTI-PERSONA TESTING (PIPELINE DE PROMPTS)
=============================================================================

A técnica mais poderosa não é usar UMA persona — é usar VÁRIAS em sequência.
Cada persona encontra classes de problemas diferentes:

1. Code Reviewer (Persona 4)     → Encontra problemas de design
   ↓ (corrigir findings críticos)
2. Security Tester (Persona 2)   → Encontra vulnerabilidades
   ↓ (corrigir findings críticos)
3. Functional Tester (Persona 1) → Verifica que funciona correctamente
   ↓ (corrigir bugs)
4. Performance Tester (Persona 3) → Verifica que funciona sob carga
   ↓ (optimizar bottlenecks)
5. DBA Tester (Persona 6)        → Verifica integridade de dados
   ↓ (corrigir queries)
6. UX/A11y Tester (Persona 5)    → Verifica acessibilidade

ESTA SEQUÊNCIA É INTENCIONAL:
- Corrigir design ANTES de testar segurança (senão estás a securizar
  código que vai ser reescrito)
- Testar funcionalidade ANTES de performance (senão estás a optimizar
  código que nem funciona correctamente)
- Acessibilidade por ÚLTIMO porque depende do HTML final estável

TÉCNICA AVANÇADA — SELF-ADVERSARIAL TESTING:
- Usar Persona 2 (Pentester) para atacar
- Depois usar Persona 4 (Architect) para defender
- O "debate" entre personas encontra findings que nenhuma encontraria sozinha
- No Claude, isso é feito em duas conversas separadas, alimentando
  os findings de uma como input da outra

TÉCNICA AVANÇADA — PROMPT CHAINING:
- Output da Persona 1 (test cases) → Input da Persona 3 (scripts de carga)
- Output da Persona 2 (vulns) → Input da Persona 4 (code fixes)
- Cada conversa é um "elo" na cadeia, com contexto progressivamente refinado
=============================================================================
-->

### Ordem recomendada e prompts de ligação:

```
CONVERSA 1 — Code Review (Persona 4):
"Revise este código. [código]"
→ Output: 15 findings de arquitectura

CONVERSA 2 — Security (Persona 2):
"O code review encontrou estes problemas: [findings].
 Agora analise a segurança do mesmo código. [código]"
→ Output: vulnerabilidades + PoCs

CONVERSA 3 — Functional (Persona 1):
"Com base nestes findings de segurança e design: [findings].
 Gere test cases para o sistema. [código]"
→ Output: 25 test cases priorizados

CONVERSA 4 — Performance (Persona 3):
"Os test cases funcionais são estes: [test cases].
 Agora gere scripts de carga para os fluxos críticos. [código]"
→ Output: scripts Locust/k6 prontos
```

<!--
NOTA: Cada conversa começa LIMPA (contexto novo). O "estado" é passado
explicitamente via os findings da conversa anterior. Isto é mais fiável
do que uma conversa única muito longa, porque:
1. Evita confusão de contexto (o LLM "esquece" instruções longe no prompt)
2. Cada persona tem 100% do context window disponível para o código
3. É possível usar modelos diferentes para cada persona (ex: Opus para
   security, Sonnet para functional — custo vs qualidade)
-->

---

## DICAS FINAIS DE ENGENHARIA DE PROMPTS PARA TESTERS

### 1. Sempre incluir código real (não descrever)

```
MAU:  "O sistema usa JWT para autenticação. Teste isso."
BOM:  "Aqui está o código de autenticação: [código completo].
       Teste os cenários de JWT."
```
**Porquê:** O LLM inventa detalhes quando não tem código — ex: pode assumir
que o JWT tem refresh tokens quando na verdade não tem.

### 2. Pedir para NÃO inventar

```
MAU:  "Liste todas as vulnerabilidades do sistema."
BOM:  "Liste vulnerabilidades que consiga comprovar com base no código
       fornecido. Para cada uma, cite a linha exacta. Se não tiver
       certeza, classifique como 'SUSPEITA — requer verificação manual'."
```
**Porquê:** Sem esta instrução, o LLM gera 20 "vulnerabilidades" genéricas
que se aplicam a qualquer sistema (ex: "verifique CORS" quando CORS nem
é relevante para uma app interna).

### 3. Usar restrições numéricas

```
MAU:  "Gere test cases para o módulo de backup."
BOM:  "Gere exactamente 10 test cases para o módulo de backup,
       ordenados por severidade (Critical primeiro)."
```
**Porquê:** Sem limite, o LLM gera 50 testes superficiais. Com limite,
é forçado a seleccionar os mais importantes.

### 4. Especificar o formato ANTES da tarefa

```
MAU:  "Analise o código e diga o que encontrou."
BOM:  "Use o formato: [SEVERIDADE] Título — Ficheiro:Linha — Descrição.
       Agora analise este código: [código]"
```
**Porquê:** Se o formato vem depois, o LLM pode gerar o primeiro finding
num formato e os seguintes noutro. Formato no início = consistência.

### 5. Chain-of-Thought explícito

```
MAU:  "Este código tem bugs?"
BOM:  "Analise este código em 3 passos:
       1. Leia e entenda o fluxo completo
       2. Identifique edge cases e inputs inesperados
       3. Para cada edge case, determine se o código o trata correctamente
       Depois liste os bugs encontrados."
```
**Porquê:** Forçar raciocínio sequencial antes da resposta reduz erros
e findings superficiais.

---

## GLOSSÁRIO DE TERMOS DE IA GENERATIVA PARA TESTERS

| Termo | Definição | Relevância para QA |
|-------|-----------|-------------------|
| **Prompt** | Instrução textual enviada ao LLM | O "test plan" para a IA |
| **System Prompt** | Instrução de contexto persistente | Define a persona e regras |
| **Temperature** | Controlo de aleatoriedade (0.0-1.0) | 0.0-0.3 para testes, 0.7+ para brainstorm |
| **Context Window** | Quantidade de texto que o LLM processa | Limita quanto código pode analisar de uma vez |
| **Grounding** | Fornecer dados reais ao LLM | Previne alucinações sobre o sistema |
| **Alucinação** | LLM inventa factos inexistentes | Falsos positivos em findings de security/QA |
| **Chain-of-Thought** | Raciocínio passo a passo | Melhora qualidade de análise de código |
| **Few-Shot** | Dar exemplos antes da tarefa | Garante formato consistente de test cases |
| **Zero-Shot** | Tarefa sem exemplos | Mais rápido mas menos preciso |
| **Token** | Unidade de texto (~4 caracteres) | Afecta custo e limite de contexto |
| **Guardrails** | Restrições no comportamento do LLM | "Não invente", "máximo 15 findings" |
| **Prompt Injection** | Ataque que manipula o LLM | Relevante ao testar inputs do WatcherDB |
| **Role Prompting** | Atribuir persona ao LLM | Cada persona encontra tipos diferentes de bugs |
| **Structured Output** | Forçar formato específico na resposta | Test cases consistentes e parseáveis |
| **Retrieval-Augmented** | LLM com acesso a dados externos | Claude Code a ler ficheiros do projecto |
