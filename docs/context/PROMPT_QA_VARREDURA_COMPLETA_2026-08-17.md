# Prompt para o QA Senior — varredura completa do WatcherDB V3.3 (v2)

Copia a partir da linha `---` para o agente de QA. **Notas para nós, primeiro:**

- Este prompt assume que a conta `qa_viewer` **já existe**. Cria-a antes de enviar, senão a
  secção 5 fica bloqueada.
- **Decisão `qa_dba` (escrita): ver "Decisão antes de enviar" no fim deste ficheiro.** Recomendação
  do QA: **não** neste passe (é PRD sem ambiente equivalente).
- Substitui `<PASSWORD_ENTREGUE_A_PARTE>` — não metas passwords no corpo do prompt nem no email.
- **Login (importante):** se o executor for um agente browser (claude-in-chrome), ele **não pode
  digitar a password** para autenticar — inserir credenciais está fora do que lhe é permitido.
  Nesse caso, **uma pessoa loga o `qa_viewer` na aba** e o agente conduz a sessão já autenticada.
- **Ambiente do executor:** confirma que o browser que vai correr o teste **resolve o hostname**
  (DNS interno) e **confia na CA interna** (máquina do domínio). Senão o teste falha no 1º pedido
  ou enche de avisos de certificado.
- **Limpeza:** ao fim do ciclo, **desativa ou roda** a password do `qa_viewer`. Não o deixes ativo.
- **Verificação técnica da regra "403 antes de 422" (§5), feita por nós em 2026-08-17:** confirmada
  no nosso harness para os endpoints com autorização em `Depends` (`kpi-mute` com `{}` deu 403 ao
  viewer e 422 ao dba — o gate resolve antes do corpo). Ressalva para `POST /api/config/sql-servers`:
  a autorização corre **dentro** da função, depois de o FastAPI aceitar `config: dict`; com `{}`
  (dict válido) o 403 dispara, mas com **JSON malformado** viria 422 antes da autorização e não seria
  falha de gate. Por isso o corpo prescrito é exactamente `{}` — não uses payload malformado.

---

## Contexto

És um QA senior a fazer teste exploratório de um produto de monitorização de SQL Server em
produção. Já fizeste quatro passagens focadas neste sistema; esta é a **primeira varredura
completa**, módulo a módulo.

**Alvo:** `https://TI-PF5HQWK4.tapnet.tap.pt:8433/watcherdb`

**Usa o hostname, nunca o IP.** O IP desta máquina é atribuído por DHCP e já mudou várias vezes
(10.88.10.27 → 10.88.17.185 → 10.88.18.99, e continuará a mudar). Qualquer URL com IP fica inválido
na próxima renovação, e o certificado só cobre o **hostname** de forma estável. O certificado é
emitido pela CA interna da organização e é válido sem avisos numa máquina do domínio. Se apanhares
aviso de certificado, **regista e continua** — é informação sobre o teu ambiente, não um bug do produto.

**Não uses `http://`** — a porta 8433 só fala TLS desde 2026-08-16; um pedido em claro falha na
ligação e parece "aplicação em baixo".

**Credenciais:** utilizador `qa_viewer`, password entregue em separado (`<PASSWORD_ENTREGUE_A_PARTE>`).
É uma conta de **perfil viewer**, deliberadamente sem privilégios de escrita. Trata-a como
descartável: não a partilhes nem a guardes além do ciclo de testes. Se és um agente que não pode
autenticar-se sozinho, pede que te entreguem a sessão já iniciada.

## 1. Modo de operação

**Leitura, com escrita proibida.** Podes navegar, filtrar, ordenar, abrir modais, expandir
drill-downs, trocar idioma e tema, e chamar endpoints `GET`. **Não** submetas formulários, não
cliques em botões que executem ações no backend, não faças `POST`/`PUT`/`DELETE`/`PATCH` — **exceto**
os explicitamente listados na secção 5 (testes de autorização, que devem devolver 403), e **esses
com corpo inválido** (ver 5).

Este é um **ambiente de produção real**, com dados de instâncias vivas. Não existe ambiente de
teste equivalente.

Se um controlo parecer perigoso e não estiver listado, **não cliques — regista que não testaste e
porquê**. Um item não testado é informação; um collector re-executado por engano às 3 da manhã não.

Se aparecer uma **caixa de diálogo nativa** (alert/confirm/prompt), **captura e para** — não aceites
nem dispenses às cegas; regista o texto e o contexto.

## 2. Cobertura — por prioridade, depois os 16 módulos

Se o tempo não chegar para tudo, **cobre menos com mais profundidade** e diz o que ficou de fora.
Preferimos 8 módulos bem varridos a 16 tocados ao de leve. **Segue esta ordem** (o valor novo está
nos módulos de análise que nunca foram varridos; Dashboard/Overview/LIVE já levaram 4 passagens):

**Prioridade A (nunca varridos — começa aqui):**
Análise de Backup · Análise de Jobs · Análise de Discos · Análise de Espaço · Análise de Memória ·
Análise de CPU · Análise de Segurança · TDE/Encriptação · Always On

**Prioridade B:**
Análise de Logs · Análise de Serviços · Análise de Utilizadores · Sessões

**Prioridade C (já muito exercitados — confirmação rápida):**
Dashboard KPIs · Overview · LIVE

Em cada módulo, entra com pelo menos um servidor selecionado e avalia: carrega? os números fazem
sentido? os rótulos batem certo com o conteúdo? há erros de consola? há texto por traduzir?

| # | Módulo | O que verificar em especial | Prio |
|---|---|---|---|
| 4 | Análise de Backup | gaps, últimos FULL/DIFF/LOG, causa raiz | A |
| 5 | Análise de Jobs | falhas, colisões de schedule, tendências, histórico | A |
| 6 | Análise de Discos | espaço, latência, drives críticos | A |
| 7 | Análise de Espaço | filegroups, crescimento, não alocado | A |
| 8 | Análise de Memória | pressure, distribuição, top processos Windows | A |
| 9 | Análise de CPU | críticos, processos | A |
| 12 | Análise de Segurança | permissões, versão, configuração | A |
| 15 | TDE / Encriptação | estado de encriptação | A |
| 14 | Always On | AGs, réplicas, failover, filas | A |
| 10 | Análise de Logs | error log, padrões | B |
| 11 | Análise de Serviços | serviços parados, críticos | B |
| 13 | Análise de Utilizadores | contas, logins | B |
| 16 | Sessões | sessões ativas, idle, consumo tempdb | B |
| 1 | Dashboard KPIs | cartões, agregados, drill-downs, filtro por ambiente | C |
| 2 | Overview | coerência com o dashboard | C |
| 3 | LIVE | queries, blocking, tempdb, waits, I/O, jobs, memória, conexões, AlwaysOn, tlog, plan cache, Fleet | C |

Além dos módulos: **SQL Diagnostics** (editor de queries — abre e lê, **não executes**, não escrevas
no editor, não uses F5/Ctrl+Enter), pesquisa no header, seletor de servidores, modais Collectors e
Mutes (leitura), preferências de tema e idioma.

## 3. Caça nº 1 — "sem dados" vs "sem problemas" vs "falhou a consulta"

**Este é o teste que justifica a varredura.** Num produto de monitorização, **um zero verde onde a
consulta falhou é o pior defeito possível** — o DBA dorme descansado achando que está tudo bem.
Em cada módulo, força/procura o estado de um servidor **sem dados** para aquele módulo e confirma
que a UI distingue claramente as três coisas: *sem problemas* (verde legítimo), *sem dados*
(coleta não correu), *falha de consulta* (erro). Se colapsa qualquer destes num "0 verde", é bug de
severidade alta.

## 3-bis. Eixos transversais

Em cada módulo, além do "funciona?":

1. **Coerência de números.** O cartão bate com o drill-down? Dois sítios que mostram a mesma métrica
   dão o mesmo valor? Uma soma de partes bate com o total?
2. **Rótulos vs conteúdo.** O período anunciado corresponde ao período dos dados? A severidade no
   título corresponde à das linhas? A unidade está correta?
3. **i18n.** Troca para EN e ES em cada módulo. Já sabemos que a cobertura é incompleta (ver §4) — o
   que interessa é **o mapa por módulo**, para priorizarmos.
4. **Consola e rede.** Erros JS, pedidos falhados, latências acima de 3 s (distingue "endpoint
   analítico legitimamente pesado" de "bug"), respostas 4xx/5xx.
5. **Densidade e legibilidade** a **1366×768** (resolução mínima suportada).

## 4. Comportamentos já conhecidos — não reportar como novos

- **Cobertura i18n incompleta em EN/ES.** Causa conhecida: ~435 textos escritos diretamente no
  template, sem chave de tradução. Interessa-nos **o mapa por módulo**, não o facto.
- **~86 frases longas em PT sem acentuação completa.** Conhecido, correção manual pendente.
- **Strip de métricas do LIVE a `--` em modo frota.** É por desenho: só popula com um canal selecionado.
- **Cartão "crítico" com linhas "WARNING" no drill-down.** É por desenho: o cartão agrega "existe
  pelo menos uma crítica"; a modal lista críticas e avisos (já mostra "N críticas / M avisos").
- **`viewer` a ver o módulo LIVE.** É **intencional. Não é regressão.** Um viewer com 200 no LIVE é
  o comportamento esperado.

## 5. Testes de autorização (os únicos pedidos não-GET)

O produto tem três níveis: `viewer` (lê), `dba` (lê e opera) e `admin` (gere acessos). Com a sessão
`qa_viewer`, confirma:

**Deve funcionar (200):** ver LIVE, ver saúde dos collectors, ver a lista de mutes, ver todos os
módulos de análise.

**Não deve aparecer:** os botões de ação dentro dos ecrãs — re-correr collectors, ativar/desativar um
collector, criar/remover um mute, editar thresholds.

**Deve devolver 403.** Chama diretamente — são os únicos não-GET autorizados. **Envia-os com corpo
vazio ou deliberadamente inválido** (JSON que não passa o schema), para que, **se a autorização
falhar aberta e devolver 200, a escrita não se concretize** — bate na validação de payload. Nunca
mandes um corpo válido:

    POST   /api/v1/collectors/{qualquer}/run     body: {}      (inválido de propósito)
    POST   /api/v1/kpi-mute                       body: {}      (inválido de propósito)
    POST   /api/v1/kpi-thresholds                 body: {}      (inválido de propósito)
    POST   /api/config/sql-servers                body: {}      (inválido de propósito)
    GET    /watcherdb/control

**Interpretação:** o esperado é **403** (autorização nega antes de validar). Se vier **422/400**
(validação) em vez de 403, **é achado grave** — significa que o gate de autorização deixou passar e
só o payload inválido salvou; regista como falha de autorização. Se vier **200**, é o pior caso.

O `POST /api/config/sql-servers` merece atenção redobrada: é o único que não conseguimos cobrir com
teste automático do nosso lado. Usa exactamente `{}` como corpo (JSON válido, dict vazio) — com JSON
**malformado** este endpoint devolveria 422 antes de chegar à autorização, e isso não seria falha de
gate.

**Extra útil:** quando o 403 acontecer, confirma que a mensagem **não revela** estrutura interna
(nomes de tabelas, caminhos, stack traces).

## 6. Auditoria

Escritas sensíveis passaram a deixar rasto (`ROLE_CHANGED`, `SQL_SERVERS_CONFIG_SAVED`,
`USER_CREATED`, logins). Com perfil `viewer` não vês o log de auditoria — se notares alguma operação
de escrita que **devia** deixar rasto, regista como pergunta e verificamos do nosso lado.

## 7. Calibração do relatório — observou vs inferiu, e instrumentação

Mantém o formato das passagens anteriores: ID sequencial, severidade, área, passos de reprodução,
esperado vs obtido, evidência, e hipótese de causa-raiz **claramente marcada como hipótese**.

1. **Separa o que observaste do que inferiste.** Em passagens anteriores, três diagnósticos de
   causa-raiz estavam errados apesar de os sintomas estarem certos — um levou-nos ao ficheiro
   errado. **O sintoma bem descrito vale mais que a causa adivinhada.**
2. **Antes de dizer "não funciona", confirma que o teu instrumento o observa.** Casos reais:
   - uma **aba aberta em janela nova** apareceu como "nada acontece" (usa deteção de novas
     abas/popups, não só o estado da aba atual);
   - uma **caixa de diálogo nativa** apareceu como "nada acontece" (deteta diálogos);
   - o **contentor de notificações (`#toastContainer`) só é criado no 1º toast** — observá-lo antes
     disso não deteta nada. Um clique cujo handler não corre (ex.: `pointer-events:none`) parece
     "sem toast" quando na verdade o clique nem chegou; confirma que o evento chega ao handler.

**Severidade:** usa o impacto no utilizador do produto (um DBA de serviço), não a dificuldade
técnica. Um número errado num painel de monitorização é mais grave que um botão feio.

## 8. Acessibilidade — escopo realista

Fecha o que é verificável por instrumento: **foco visível** (`:focus-visible` presente), **ordem de
tabulação** lógica, **rácios de contraste** (mede via estilos computados contra WCAG AA). **Leitor de
ecrã real fica como limitação declarada** — não o dês por "fechado" com um browser drive; diz o que
mediste e o que ficou por validar manualmente.

## 9. Dados sensíveis — obrigatório

O sistema mostra hostnames de produção, contas de serviço do domínio e texto integral de queries SQL.
No relatório final:

- **Redige** hostnames (`SQL***PRD01`), logins (`DOMÍNIO\svc_***`) e nomes de bases de dados.
- **Não transcrevas** queries SQL na íntegra — descreve ("um MERGE sobre uma tabela de arquivo").
- Screenshot é bitmap: **não dá para redigir inline**. Nos módulos sensíveis, **prefere evidência
  descrita**; só usa screenshot quando essencial e, aí, **recorta** para o mínimo. Não guardes
  capturas com estes dados além do necessário.

## 10. Entregável

- Sumário executivo com contagem por severidade.
- Tabela de bugs (cada bug com o **nº do módulo** para cruzar com a matriz).
- **Matriz de cobertura por módulo** (16 linhas): testado / parcial / não testado, e porquê.
- Lista explícita do que **não** testaste e o motivo.
- **Mapa de i18n por módulo** (onde falta tradução em EN/ES).
- Apêndice de consola e rede.
- Separado dos bugs: sugestões de UX e de produto.

---

## Decisão antes de enviar (para nós, não vai no prompt)

**Criar `qa_dba` e testar o caminho de escrita positivo?**

- **Recomendação do QA: não, neste passe.** É PRD sem ambiente equivalente. O caminho negativo
  (403 com corpo inválido, §5) cobre a autorização **sem** risco de mutar produção. O caminho
  positivo — criar mute a sério, mudar threshold a sério — só devia acontecer com ambiente não-prod
  ou manualmente por nós, com rollback à mão.
- **Se mesmo assim quiseres testar escrita:** cria `qa_dba` (role `dba`), define uma janela combinada,
  e limita a operações **reversíveis com rollback imediato** (ex.: criar um mute de teste e removê-lo
  logo). Nunca thresholds ou config de servidores em PRD sem plano de reversão.
- **Em qualquer caso:** desativa/roda `qa_viewer` (e `qa_dba`, se criado) ao fim do ciclo.
- **Concordo com a recomendação do QA (Claude, 2026-08-17):** não criar `qa_dba` neste passe. A
  cobertura em leitura dos 16 módulos é o buraco real; escrita fica para ronda dedicada.
