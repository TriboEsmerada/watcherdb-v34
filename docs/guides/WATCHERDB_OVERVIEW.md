# WatcherDB — Visao Geral do Produto

## O que e o WatcherDB?

O WatcherDB e um **software de vigilancia automatica** para bases de dados SQL Server.

Imagine ter um colaborador que trabalha 24 horas por dia, 7 dias por semana, a vigiar todos os seus servidores de bases de dados — verificando se os backups estao em dia, se o espaco em disco esta a acabar, se algum servico parou, se ha problemas de performance — e que lhe mostra tudo num unico ecra, no browser, sem precisar de entrar servidor a servidor.

E isso que o WatcherDB faz.

---

## Problema que Resolve

Numa empresa com dezenas ou centenas de servidores SQL Server, a equipa de administracao de bases de dados (DBA) gasta horas por dia a:

- Verificar se os backups de todos os servidores correram com sucesso
- Verificar se o espaco em disco esta a acabar em algum servidor
- Verificar se os servicos de SQL Server estao todos a funcionar
- Investigar problemas de lentidao ou bloqueios
- Gerar relatorios de estado para a gestao

**Antes do WatcherDB:** A equipa entra em cada servidor individualmente, abre ferramentas, corre comandos, e anota os resultados. Com 100 servidores, isto demora horas.

**Com o WatcherDB:** Tudo e visivel num unico painel web. A equipa ve imediatamente onde ha problemas, sem precisar de entrar em nenhum servidor.

---

## O que o WatcherDB Mostra

### Painel Principal — KPIs

Ao abrir o WatcherDB, ve-se um resumo de TODOS os servidores:

| Indicador | O que significa | Exemplo |
|-----------|----------------|---------|
| **Bases de dados disponiveis** | Quantas bases estao online vs offline | 1.840 bases OK, 0 offline |
| **Servidores activos** | Quantos servidores estao a responder | 75 de 82 OK, 7 offline |
| **Backups** | Se todas as bases tem backup recente | 22 com backup em falta |
| **Espaco em disco** | Se algum disco esta quase cheio | 14 discos acima de 90% |
| **Performance** | Se ha problemas de lentidao | 1 sessao bloqueada, 5 CPUs altas |
| **Alta disponibilidade** | Se os mecanismos de redundancia estao OK | Todos os grupos sincronizados |

Os indicadores estao codificados por cores:
- **Verde** = Tudo OK
- **Amarelo** = Atencao necessaria
- **Vermelho** = Problema critico, accao imediata

### Detalhe por Servidor

Ao clicar num servidor, ha **14 vistas** diferentes:

| Vista | O que mostra |
|-------|-------------|
| **Resumo** | Estado geral do servidor |
| **Alta Disponibilidade** | Redundancia e replicas de dados |
| **Backup** | Historico e falhas de backup |
| **Espaco** | Utilizacao de disco e previsao de crescimento |
| **Disco** | Volumes fisicos e espaco livre |
| **Encriptacao** | Bases de dados encriptadas |
| **Processador** | Utilizacao de CPU |
| **Memoria** | Utilizacao de RAM |
| **Servicos** | Estado dos servicos Windows |
| **Registos** | Mensagens de erro do SQL Server |
| **Diagnostico SQL** | Bloqueios, lentidao, consultas problematicas |
| **Seguranca** | Permissoes e acessos |
| **Utilizadores** | Contas de login e permissoes |
| **Tarefas Agendadas** | Jobs automaticos e falhas |

### Painel de Administracao

Acessivel apenas por administradores, permite:

- **Gerir utilizadores** — criar, editar, desactivar contas
- **Integrar com Active Directory** — os colaboradores usam as mesmas credenciais Windows
- **Ver quem esta online** — sessoes activas em tempo real
- **Monitorar recursos** — CPU, memoria e disco do servidor do WatcherDB
- **Configurar politicas** — duracao de sessao, tentativas de login, etc.

---

## Arquitectura (Simplificada)

```
┌──────────────┐
│   Browser    │  ← Qualquer computador na rede
│  (Chrome)    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  WatcherDB   │  ← Servidor dedicado (Windows Server)
│  (Portal)    │     Porta 8433
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Servidores  │  ← Os 100+ SQL Servers da empresa
│  SQL Server  │     (nao instala nada neles)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Base de     │  ← Guarda historico e metricas
│  Dados       │     (WatcherDB Intelligence)
└──────────────┘
```

**Pontos importantes:**
- O WatcherDB **nao instala nada** nos servidores que monitoriza
- Apenas **le informacao** — nao altera nada nos servidores
- Os dados **ficam dentro da empresa** — nao envia nada para a Internet
- Funciona com as **credenciais Windows existentes** — sem passwords adicionais

---

## Requisitos

| Componente | Necessario |
|-----------|-----------|
| **Servidor para o WatcherDB** | 1 maquina Windows Server com 16GB RAM |
| **Rede** | Acesso aos servidores SQL Server (porta 1433) |
| **Utilizadores** | Conta de dominio Windows com permissao de leitura nos SQL Servers |
| **Browser** | Chrome, Edge, Firefox (qualquer versao recente) |

**Nao e necessario:**
- Instalar software nos servidores monitorizados
- Acesso a Internet (funciona totalmente offline)
- Licencas de software de terceiros

---

## Seguranca

| Aspecto | Como funciona |
|---------|--------------|
| **Acesso ao portal** | Login com utilizador e password ou credenciais Windows (Active Directory) |
| **Permissoes** | 4 niveis: Administrador, Operador, Analista, Visualizador |
| **Dados** | Tudo fica no servidor da empresa, nada sai para a Internet |
| **Encriptacao** | Comunicacao segura, passwords encriptadas |
| **Auditoria** | Registo automatico de quem acede e quando |
| **Proteccao do codigo** | Software encriptado e protegido contra copia |

---

## Poupanca Estimada

Baseado em dados reais de uma implementacao com 100 servidores:

| Metrica | Antes | Com WatcherDB |
|---------|:-----:|:-------------:|
| Horas DBA em tarefas manuais/semana | 30h | 10h |
| Tempo de deteccao de problemas | Horas | Segundos |
| Servidores monitorizados por pessoa | ~20 | 100+ |
| Trabalho fora de horas (verificacoes) | Frequente | Eliminado |
| **Poupanca anual estimada** | — | **~36.000 EUR** |

---

## Idiomas Disponiveis

O portal esta disponivel em:
- Portugues 🇵🇹
- Ingles 🇬🇧
- Espanhol 🇪🇸

A mudanca de idioma e instantanea, sem necessidade de recarregar a pagina.

---

## Resumo

O WatcherDB e como ter um **vigilante digital** para as bases de dados da empresa:

- **Ve tudo** — 100+ servidores num unico ecra
- **Trabalha 24/7** — sem pausas, sem ferias
- **Avisa antes** — detecta problemas antes de afectarem o negocio
- **Nao interfere** — apenas observa, nao altera nada
- **Fica em casa** — dados nunca saem da empresa

Para informacao tecnica detalhada, consultar o [Guia do Utilizador](USER_GUIDE_PT.md).

---

*WatcherDB V3.3 Standard Edition — Plataforma de Monitorizacao SQL Server banking-grade*
*© 2026*
