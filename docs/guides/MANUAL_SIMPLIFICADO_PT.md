# WatcherDB V3.3 — Manual Simplificado

**Para DBA junior, operador de turno, primeiro dia de uso.**

Este manual usa linguagem simples, sem jargao. Para detalhe tecnico completo ver [USER_GUIDE_PT.md](USER_GUIDE_PT.md).

---

## O que e o WatcherDB

E uma pagina web onde consegues ver o estado de todos os teus servidores SQL Server num so ecra. Em vez de abrires cada servidor um a um, vens aqui e ves tudo em conjunto: quais estao a correr, quais estao com problemas, quais vao precisar de atencao em breve.

---

## Indice

1. [Instalar em 10 minutos](#1-instalar-em-10-minutos)
2. [Primeiro login](#2-primeiro-login)
3. [O que significa cada cor](#3-o-que-significa-cada-cor)
4. [Como usar o dashboard](#4-como-usar-o-dashboard)
5. [O servico parou — o que fazer](#5-o-servico-parou--o-que-fazer)
6. [Perguntas que vais ter](#6-perguntas-que-vais-ter)
7. [Onde pedir ajuda](#7-onde-pedir-ajuda)

---

## 1. Instalar em 10 minutos

### Antes de comecar

Precisas de:

- Um servidor Windows (Windows Server 2016 ou mais recente).
- Permissao de administrador nesse servidor.
- O ficheiro do instalador: `WatcherDB_V3.3_Standard.msi`.
- Uma conta de servico (um username e password) que o WatcherDB vai usar para se ligar aos SQL Server que queres monitorizar.

### Passos

**1. Faz duplo clique** no `WatcherDB_V3.3_Standard.msi`.

**2. Aceita a licenca** e clica "Install". Se a janela do Controlo de Conta de Utilizador aparecer, clica "Sim".

**3. Quando terminar**, abre o PowerShell (como administrador) e escreve:

```powershell
Get-Service WatcherDBWebServiceV33
```

Deves ver `Status: Running`. Se vires `Stopped`, salta para a [Seccao 5 — O servico parou](#5-o-servico-parou--o-que-fazer).

**4. Abre o browser** e vai a:

```
http://localhost:8433
```

Se estiveres noutro computador, substitui `localhost` pelo nome ou IP do servidor. Por exemplo: `http://sqlmonitor01:8433`.

**5. Vais ver o ecra de login.** Se nao aparecer, verifica que a porta 8433 esta aberta na firewall. Em PowerShell:

```powershell
New-NetFirewallRule -DisplayName "WatcherDB" -Direction Inbound -LocalPort 8433 -Protocol TCP -Action Allow
```

---

## 2. Primeiro login

### Conta inicial

No primeiro arranque, existe uma conta `admin` com password temporaria. A password inicial esta no ficheiro:

```
C:\ProgramData\WatcherDB\initial_admin_password.txt
```

Abre o ficheiro, copia a password, faz login, e **muda a password imediatamente** no canto superior direito (menu do utilizador -> "Mudar password"). O ficheiro da password inicial e apagado automaticamente depois da primeira mudanca.

### Se a tua empresa usa Active Directory

Podes associar o WatcherDB ao AD para que os utilizadores entrem com o login de dominio. Nao precisas de criar contas uma a uma.

Os passos sao:

1. Faz login com `admin`.
2. Clica em "Control" (canto superior direito).
3. Vai a "Configuracoes" -> "Active Directory".
4. Preenche: Dominio (ex: `empresa.local`), Servidor LDAP (ex: `dc01.empresa.local`), Conta de servico (uma conta do dominio com permissao de leitura no AD).
5. Clica "Testar" — se o teste passar, clica "Guardar".

A partir deste momento, qualquer utilizador do dominio pode tentar fazer login. Por defeito, o acesso e "viewer" (so consulta). Para dar acesso de admin, cria o utilizador manualmente ou marca-o como admin em "Gestao de Utilizadores".

---

## 3. O que significa cada cor

O WatcherDB usa tres cores para indicar o estado de cada metrica:

| Cor | Significado | O que fazer |
|-----|-------------|-------------|
| **Verde** | Tudo bem. | Nada, continua com o resto do dia. |
| **Amarelo** | Atencao. Algo esta fora do normal mas ainda nao e urgente. | Verifica se consegues resolver nos proximos dias. |
| **Vermelho** | Situacao critica. Precisa de accao agora. | Abre a instancia afectada e verifica o detalhe na tab correspondente. |

### Limiares por omissao

Estes sao os valores que fazem um KPI passar a amarelo ou vermelho. Podes
consulta-los sempre actualizados no portal em **Configuracoes -> Thresholds
em vigor** (leitura; a edicao por cliente chega numa versao futura).

| KPI | Amarelo | Vermelho |
|-----|---------|----------|
| TempDB (utilizacao) | &gt;= 60% | &gt;= 80% |
| Latencia de disco (read/write) | &gt;= 20 ms | &gt;= 50 ms |
| CPU de instancia | aviso do colector a 80% | &gt;= 95% |
| Locks longos (duracao) | &gt; 60 s | &gt; 600 s |
| Backup FULL em atraso | ha mais de 120h (5 dias) | ha mais de 168h (7 dias) |
| Backup DIFF em atraso | ha mais de 24h | ha mais de 30h |
| Backup LOG em atraso | ha mais de 1h | ha mais de 2h |
| Processos a espera de CPU | &gt; 20 por instancia | &gt; 50 por instancia |
| CHECKDB antigo | ha mais de 30 dias | — |

Outros KPIs (espaco em disco por drive, transaction log, filegroups,
memoria, deadlocks) sao classificados na camada de recolha por drive/
database — os criterios completos aparecem no mesmo ecra "Thresholds em
vigor".

**Nota importante:** estes valores sao os defaults reais do produto para
ambiente OLTP geral. Ambientes de datawarehouse ou ETL tem padroes
diferentes — fala com o suporte se precisares de valores diferentes
enquanto a edicao por cliente nao esta disponivel.

---

## 4. Como usar o dashboard

### Ecra principal (KPI Dashboard)

Quando fazes login, ves um painel com muitos cartoes coloridos. Cada cartao mostra o estado agregado de um KPI em todas as instancias que tens a monitorizar.

Por exemplo, o cartao "Backups" mostra-te quantas instancias estao com backup em dia e quantas estao atrasadas. Se clicares no cartao, abres a lista das instancias afectadas.

No topo do ecra tens filtros:

- **Ambiente:** PRD (producao), HOM (homologacao), DEV (desenvolvimento). Podes escolher so um ou todos.
- **Status:** podes mostrar so os verdes, so os amarelos, ou so os vermelhos.
- **Pesquisa:** escreve parte do nome de uma instancia para filtrar.

### Tab de servidor (16 tabs)

Quando escolhes uma instancia, abres o ecra de detalhe com 16 tabs. As mais usadas sao:

- **Overview:** resumo rapido do estado.
- **Always On:** se a instancia for participante de um Availability Group.
- **Backup:** quando foi o ultimo full, diff, log. Falhas recentes.
- **Space:** espaco usado e livre em cada base de dados.
- **Disk:** espaco por volume do SO.
- **CPU / Memory:** uso actual e historico.
- **Services:** servico SQL Server, SQL Agent, SSRS, SSAS, Browser.
- **Log:** SQL Server Error Log filtrado por severidade.
- **Security:** permissoes, utilizadores com sysadmin, TDE.
- **Jobs:** SQL Agent jobs e historico de execucao.
- **Performance:** deadlocks, blocking, queries lentas, missing indexes.

Se alguma tab estiver vazia ou a dar erro, e provavel que o collector nao tenha dados para essa instancia ainda. Espera 5 minutos e recarrega.

---

## 5. O servico parou — o que fazer

Se o WatcherDB nao abre no browser, ou se recebeste alerta de que o servico parou, segue estes 4 passos por esta ordem.

### Passo 1 — Verifica o estado do servico

Abre PowerShell como administrador:

```powershell
Get-Service WatcherDBWebServiceV33
```

- Se disser `Running`, o servico esta activo. Problema esta noutro lado (firewall, rede, porta). Salta para o Passo 4.
- Se disser `Stopped`, continua para o Passo 2.

### Passo 2 — Tenta reiniciar o servico

```powershell
Start-Service WatcherDBWebServiceV33
```

- Se arrancar (`Running` depois de alguns segundos), esta resolvido.
- Se der erro ou voltar a parar imediatamente, continua para o Passo 3.

### Passo 3 — Ve o log do servico

O log esta em:

```
C:\ProgramData\WatcherDB\logs\watcherdb_main.log
```

Abre com Notepad e procura pelas linhas mais recentes com a palavra `ERROR`. Os erros mais comuns sao:

- **"Could not connect to WatcherDB_Intelligence"** — a base de dados do collector esta inacessivel. Verifica no SQL Server Management Studio se consegues abrir a BD `WatcherDB_Intelligence`.
- **"Port 8433 already in use"** — outro programa esta a usar a porta. Usa `netstat -ano | findstr :8433` para ver qual, e desliga-o ou muda a porta do WatcherDB em `services\web_service\config.yaml`.
- **"License file not found"** — o ficheiro `C:\ProgramData\WatcherDB\license.dat` esta em falta ou corrompido. Pede o ficheiro ao administrador.
- **"DPAPI decryption failed"** — a conta Windows que corre o servico nao e a mesma que instalou. Configura o servico para correr com a conta correcta em `services.msc -> WatcherDBWebServiceV33 -> Log On`.

### Passo 4 — Abre ticket de suporte

Se nenhum dos passos acima resolveu, abre ticket com:

- O conteudo das ultimas 50 linhas do log (`watcherdb_main.log`).
- A saida de `Get-Service WatcherDBWebServiceV33 | Format-List *`.
- A versao do WatcherDB (canto inferior direito da pagina web, ou no ficheiro `C:\Program Files\WatcherDB\V3.3\version.txt`).
- Descricao do que estavas a fazer quando o problema aconteceu.

Ver [Seccao 7 — Onde pedir ajuda](#7-onde-pedir-ajuda).

---

## 6. Perguntas que vais ter

### "Em que porta o WatcherDB esta a escutar?"

Porta **8433**. Se alguma doc antiga disser 8449 ou 8000, ignora — foram versoes anteriores.

### "Em que frequencia e que os dados sao actualizados?"

Os collectors correm a cada 5 minutos em media. Se ves um valor "velho" no dashboard, espera 5-10 minutos e recarrega.

### "Porque e que aparece um KPI vermelho mas eu acho que esta tudo bem?"

Duas razoes comuns:

1. O threshold e conservador para o teu ambiente. Ajusta em "Control -> Thresholds".
2. O KPI reflecte uma janela de tempo passada (ex: backup ausente ha 25h passou a amarelo; fizeste backup ha 10 minutos mas ainda nao foi recolhido). Espera 5 minutos.

### "Uma instancia nao aparece no dashboard."

Duas hipoteses:

1. Nao foi adicionada a lista de instancias a monitorizar. Pede ao admin para a adicionar em "Control -> Instances".
2. O collector da V1 nao conseguiu ligar-se. Verifica que a conta de servico tem permissao de login e `VIEW SERVER STATE` no SQL Server.

### "Posso receber alertas por email?"

**V3.3 Standard nao tem alerting por email/Teams/Slack integrado ainda.** Esta funcionalidade esta planeada para o proximo release. Por agora, podes configurar SQL Server Agent jobs que consomem a API do WatcherDB e enviam email via Database Mail.

### "Qual e a diferenca entre Standard e Pro?"

- **Standard (o que tens agora):** monitorizacao, KPIs, tabs de diagnostico, Performance Intelligence com 8 investigators, reports PDF.
- **Pro:** tudo o que Standard tem, mais AI local (Ollama), deteccao automatica de anomalias, investigacao autonoma, relatorios executivos, capacity planning com ML, integracao ITSM. Ver [Anexo B do USER_GUIDE_PT.md](USER_GUIDE_PT.md).

### "E seguro usar em ambiente bancario?"

Sim. O WatcherDB V3.3 tem MSI signed, SBOM publicado, codigo ofuscado com PyArmor, zero phone-home (nao envia dados para fora do teu perimetro), suporta AD hybrid, e passa security review de CISO sem iteracao extra. Para detalhe tecnico ver [Anexo A do USER_GUIDE_PT.md](USER_GUIDE_PT.md).

### "Os dados do WatcherDB saem do meu datacenter?"

**Nao.** Todos os dados ficam no servidor onde instalaste o WatcherDB. Nao ha telemetria, nao ha cloud, nao ha analytics remotos. Zero egress.

### "Tenho 30 instancias — e suficiente para este produto?"

Sim. O WatcherDB V3.3 foi testado confortavelmente ate 100 instancias. Com 30, tens folga.

### "O DBA Copilot funciona sem internet?"

No WatcherDB V3.3 Standard, o Copilot usa respostas baseadas em regras (nao AI). Funciona 100% offline. A versao AI do Copilot com LLM local esta disponivel em WatcherDB Pro (ver Anexo B do USER_GUIDE_PT.md).

---

## 7. Onde pedir ajuda

### Antes de abrir ticket

1. Recarrega a pagina (Ctrl+F5).
2. Faz logout e login novamente.
3. Verifica o log em `C:\ProgramData\WatcherDB\logs\watcherdb_main.log`.
4. Ve a [Seccao 6 — Perguntas que vais ter](#6-perguntas-que-vais-ter) acima.

### Quando abrires ticket, inclui

- **Versao do WatcherDB:** canto inferior direito da pagina ou `C:\Program Files\WatcherDB\V3.3\version.txt`.
- **O que estavas a fazer:** ex. "tentei abrir a tab Jobs na instancia SQL01".
- **O que esperavas:** ex. "ver a lista de jobs".
- **O que aconteceu:** ex. "pagina em branco, consola do browser mostra erro 500".
- **Screenshot** da pagina e da consola do browser (F12 -> tab Console).
- **Ultimas 50 linhas** do ficheiro `watcherdb_main.log`.

### Contactos

- **Suporte comercial:** contactar o vendor (vem no email de compra ou na licenca).
- **Documentacao tecnica completa:** [USER_GUIDE_PT.md](USER_GUIDE_PT.md) (este mesmo directorio).
- **Questoes de licenciamento:** contactar account manager do vendor.

### Tempo de resposta esperado

| Prioridade | Descricao | Tempo de resposta (dias uteis) |
|------------|-----------|-------------------------------|
| **P1 Critical** | Servico parado em producao, impacto em monitorizacao de ambientes criticos | 2 horas |
| **P2 High** | Funcionalidade partida mas workaround disponivel | 1 dia util |
| **P3 Medium** | Bug nao-bloqueante, questao de configuracao | 3 dias uteis |
| **P4 Low** | Feature request, duvida de uso, cosmetico | 5 dias uteis |

---

**WatcherDB V3.3 Standard Edition — Manual Simplificado**

Este manual foi escrito para ser lido de ponta a ponta em menos de 20 minutos. Se precisas de detalhe tecnico profundo (endpoints API, estrutura de BD, algoritmos de performance), vai ao [USER_GUIDE_PT.md](USER_GUIDE_PT.md).

Publicado em 22 de Abril de 2026.
