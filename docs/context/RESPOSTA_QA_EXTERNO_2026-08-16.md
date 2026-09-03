# Resposta ao QA externo — WatcherDB V3.3 (ronda de 2026-08-16)

Texto pronto a enviar. Contexto para nós: fecha o ciclo dos 14 BUG + 7 N-xx do relatorio
exploratorio; ver TRIAGEM_QA_EXTERNO_PRD_2026-08-16.md para o parecer tecnico completo.

---

## Assunto: WatcherDB V3.3 — correcoes aplicadas + 3 mudancas que afectam o proximo passe

Obrigado pelas quatro passagens. O relatorio foi accionavel: **10 dos 14 bugs estao corrigidos**,
incluindo o Critico. Abaixo o que mudou, o que precisamos que revalidem, e tres coisas que vos
partem o teste se nao souberem de antemao.

### 1. ANTES DE TESTAR — tres mudancas de contexto

**1.1 O portal mudou para HTTPS.** `http://10.88.10.27:8433` **deixou de responder** (socket TLS
nao fala HTTP em claro; nao ha redirect possivel na mesma porta). O novo URL e:

    https://TI-PF5HQWK4.tapnet.tap.pt:8433/watcherdb

**Usem o hostname, nao o IP.** O IP da maquina e' DHCP e mudou entretanto (10.88.10.27 ->
10.88.17.185); o hostname resolve sempre para o IP correcto e e' o nome que o certificado cobre de
forma estavel. O certificado e emitido pela nossa CA interna, portanto **valida sem avisos** em
maquinas do dominio. Se o vosso harness correr fora do dominio, precisa da cadeia da CA no trust
store (ou de aceitar o cert explicitamente) — digam-nos e enviamos a cadeia.

**1.2 O modelo de permissoes mudou** — passou a ter tres niveis, e o eixo e **ler vs alterar**:

| | viewer | dba | admin |
|---|---|---|---|
| Ver dashboard, drill-downs, relatorios | sim | sim | sim |
| Ver LIVE (queries, blocking, tempdb, waits) | sim | sim | sim |
| Ver saude dos collectors, lista de mutes | sim | sim | sim |
| Alterar: toggle/run collector, criar/remover mute | **403** | sim | sim |
| Alterar: resolver offline, discovery, thresholds, servidores | **403** | sim | sim |
| Gerir acessos: utilizadores, roles, AD, JWT, sessoes | **403** | **403** | sim |

**1.3 A decisao 2 foi revertida, de proposito.** Tinham pedido (e nos concordamos na altura) 403
para `viewer` nos endpoints LIVE. O owner decidiu depois que **o viewer deve ver o LIVE** — o que
fica restrito sao as accoes de escrita, nao a visibilidade. Portanto: **um viewer com 200 no LIVE
NAO e' regressao**, e' o comportamento pretendido.

Registamos a vossa objeccao (o LIVE mostra texto SQL completo, logins de servico e hostnames de
producao) e ela continua em aberto como opcao: temos desenhado, por implementar, um meio-termo em
que o viewer ve o LIVE com o **texto SQL redigido**. Se acharem que devemos ir por ai, digam.

### 2. Estado por ID

| ID | Estado | Nota |
|---|---|---|
| BUG-001 Control | **Corrigido (era falso positivo)** | O `window.open` estava correcto; o vosso harness nao observava a aba nova. Mas escondia um defeito real: nao haviamos deteccao de popup bloqueado. Agora ha toast + `opener=null`, e a aba e' reutilizada (N-01). |
| BUG-002/010 TLS | **Corrigido** | HTTPS com cert da CA interna. O HSTS que assinalaram como ineficaz **agora e' emitido so' sobre HTTPS** e tem efeito real. |
| BUG-003 i18n EN/ES | **Em aberto (backlog proprio)** | O vosso diagnostico ("chaves em falta") nao se confirmou: os 3 dicionarios tinham paridade perfeita. A causa sao ~435 strings **hardcoded** no template, sem chave i18n. E' uma wave dedicada. |
| BUG-004 FOUC | **Corrigido** | Race real: o `init()` aplicava i18n antes do dicionario carregar. |
| BUG-005 + BUG-013 ortografia/acentos | **Corrigido** | Adoptado PT-PT pos-AO90 como recomendaram. 338 valores normalizados, zero chaves renomeadas, e **teste de regressao** que falha se grafia pre-AO90 voltar. Ficam ~86 frases longas por rever a mao (acentos que dependem do contexto: `esta`/`está`, `e`/`é`). |
| BUG-006 sort | **Corrigido** | Tie-break deterministico em 3 sitios. |
| BUG-007 Fleet vs Blocking | **Corrigido como rotulagem** | Nao eram fontes dessincronizadas por bug: sao 3 consultas DMV com ambitos diferentes (frota vs canal seleccionado). Cada painel passa a dizer **que instancia** e **a que horas** foi a amostra. Correccao a uma leitura: na tabela do Fleet, "Blocked 128" e' o **SPID** da sessao bloqueada, nao uma contagem. |
| BUG-008 duracao 15 dias | **Corrigido nas duas superficies** | A causa nao era o calculo de elapsed: no painel Fleet a coluna mostrava `cpu_time/1000` rotulado como "Xs" — em plano paralelo o CPU **soma por thread**, dai 1.312.570s. Agora sao duas colunas (CPU e tempo decorrido), humanizadas, com badge `idle` para sessoes a dormir com transaccao aberta. |
| BUG-009 Ping | **Corrigido (causa-raiz real)** | O toast existia mas o botao tinha `pointer-events:none` — **o clique nunca chegava ao handler**. Agora fica esmaecido mas clicavel, com `aria-disabled`, tooltip, toast de 5s (`role="status"`) e um `console.warn('[PING] ...')` que o vosso harness apanha mesmo que o toast ja tenha desaparecido. |
| BUG-011 foco de teclado | **Em aberto** | Precisa do passe manual dedicado que sugeriram. |
| BUG-012 "task/tasks" | **Em aberto** | Backlog, entra com a wave de i18n. |
| BUG-014 critico vs WARNING | **Explicado + melhorado** | Nao e' bug: o cartao agrega "existe pelo menos 1 critica" e a modal lista criticas **e** avisos. A modal passa a mostrar "N criticas / M avisos" quando ha mistura. |
| N-01 aba duplicada | **Corrigido** | `window.open` com target nomeado. |
| N-02 strip `Blk: --` | **Por desenho** | Em modo frota nao ha instancia seleccionada; a strip so' popula por canal. Ficou rotulado. |
| N-03 flash do login | **Em aberto (cosmetico)** | Mesma familia de races de arranque que ja temos mapeada. |
| N-04 LDAP sem TLS | **Em curso** | O produto ja suporta `ldaps://` (infere porta 636 do prefixo); falta a alteracao de configuracao no ambiente. |
| N-05 nome vs role | **Em curso** | Estamos a acertar os roles antes de qualquer aperto de permissoes — apertar primeiro trancaria administradores reais fora do painel onde os roles se corrigem. |
| N-06 fusos | **Em aberto** | O auth log guarda UTC e o cabecalho mostra hora local. |
| N-07 "Failed to fetch" | **Corrigido** | O vosso diagnostico estava certo (era o redeploy). Uma falha isolada de polling deixa de escalar a erro: janela de 2 min, so' a 3a consecutiva e' que vira `error`. |
| 3d log `[PREFS]` | **Corrigido** (ja confirmaram) | |

### 3. O que pedimos que revalidem (5o passe)

Tudo em `https://`:

1. **Ping sem servidor** — clicar deve dar toast **e** deixar `[PING] ...` na consola.
2. **Fleet -> QUERIES PESADAS AGORA** — confirmar que ja nao aparece duracao implausivel e que ha
   duas colunas (CPU e tempo decorrido).
3. **LIVE -> Blocking** — confirmar o rotulo "Instancia X · amostra HH:MM · so esta instancia".
4. **Idioma** — PT deve reportar `lang="pt-PT"` (na vossa 3a passagem ainda apanharam `pt-BR`
   porque o build estava a mudar a meio da sessao).
5. **Permissoes** — com a conta `qa_viewer` que vos entregamos:
   - **deve ver** LIVE, Collectors, Mutes (200);
   - **nao deve ver** os botoes de accao dentro desses ecrans (re-correr, activar/desactivar,
     criar/remover mute);
   - **deve levar 403** se chamar directamente `POST /api/v1/collectors/{task}/run`,
     `POST /api/v1/kpi-mute`, `POST /api/v1/kpi-thresholds`, `POST /api/config/sql-servers`;
   - **nao deve abrir** `/watcherdb/control`.

   Nota: o `POST /api/config/sql-servers` e' o unico caso que nao conseguimos cobrir no nosso
   harness automatico — atencao especial a esse.

### 4. Instrumentacao do harness

Dois dos vossos achados foram artefactos de observacao (BUG-001 e BUG-009). Para a proxima ronda,
sugerimos registar `page.on('popup')` e `page.on('dialog')` — sem isso, `window.open()` e dialogos
nativos aparecem como "nao acontece nada". Nao tira valor ao relatorio; poupa-nos os dois ciclos
que estes dois consumiram.

Tambem util: o `#toastContainer` **so' existe depois do primeiro toast**, portanto um
`MutationObserver` sobre esse selector antes do clique observa um no que ainda nao nasceu.

### 5. Governanca da proxima ronda

Tres pedidos, por ordem de importancia:

1. **Nao testar com credencial de administrador.** Usem a `qa_viewer` (ou uma conta `dba` se
   precisarem de exercitar accoes). A conta `salomao` usada nas rondas anteriores vai ser rodada.
2. **Nao ha ambiente QLT** para este produto — so' existe a instancia de producao. Enquanto assim
   for, mudancas com risco vao atras de interruptor de configuracao, e o vosso passe e' a validacao.
   Se o escopo crescer, vale a pena discutir montar um ambiente dedicado.
3. **Dados sensiveis.** Nas rondas anteriores, texto de queries SQL, logins de dominio e hostnames
   de producao passaram por um browser em cloud de terceiro sobre HTTP. Agora ha TLS, mas mantem-se
   a questao de os dados sairem da rede. Se o escopo continuar, precisamos de acordar por escrito o
   que pode ser capturado e retido.

### 6. O que fica em aberto do nosso lado

- BUG-003 (i18n EN/ES) — wave dedicada, ~435 strings.
- BUG-011 (foco), BUG-012, N-03, N-06 — backlog.
- ~86 frases longas com acentos por rever manualmente.
- Separar o editor de thresholds do modal de definicoes.
- Decisao em aberto: redigir ou nao o texto SQL no LIVE para `viewer`.
