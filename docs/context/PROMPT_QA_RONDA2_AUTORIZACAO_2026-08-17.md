# Prompt para o QA Senior — Ronda 2: autorização, sessão e superfície de injeção

Copia a partir da linha `---`. **Notas para nós, primeiro:**

- **Só depois da ronda 1 fechada.** Esta ronda reutiliza o contexto e o ambiente da 1.
- **Duas contas obrigatórias**: `qa_viewer` (já existe da ronda 1) **e `qa_dba` (role `dba`, Local)**.
  Uma matriz de permissões testada com uma só conta prova metade da matriz. Cria `qa_dba` antes de
  enviar. Passwords entregues à parte, nunca no prompt.
- **Janela combinada.** A ronda 2 tem 4 escritas reais em produção (lista fechada, secção 4). Marca
  data/hora com o QA e avisa quem monitoriza — um mute de teste a aparecer no dashboard sem aviso
  gera confusão.
- **Login:** o agente browser não digita passwords. Uma pessoa autentica cada conta na aba
  respetiva; o agente conduz. Vão ser **duas sessões**, em abas ou perfis separados — não misturar.
- **O que só nós conseguimos verificar** (nenhuma das duas contas alcança): o log de auditoria
  (`Auth Log` no painel Control). Depois do passe, verificamos com admin que as 4 escritas da
  secção 4 deixaram rasto (`ROLE_CHANGED` não se aplica; esperamos ver os mutes criados/removidos e o
  threshold gravado). Se não deixarem, é achado nosso.
- **Limpeza:** desativar `qa_dba` no fim; `qa_viewer` só se não houver ronda 3 a seguir.

---

## Contexto

És um QA senior. Já fizeste a varredura funcional deste produto (ronda 1). Esta ronda é sobre
**quem pode fazer o quê** — e sobre o que acontece quando alguém tenta o que não pode.

**Alvo:** `https://TI-PF5HQWK4.tapnet.tap.pt:8433/watcherdb` — hostname, nunca IP; só `https://`.

**Duas contas**, passwords entregues à parte:
- `qa_viewer` — perfil **viewer** (lê tudo, não altera nada).
- `qa_dba` — perfil **dba** (lê tudo, opera: collectors, mutes, thresholds, servidores; **não** gere
  utilizadores nem configuração de acessos).

Existe um terceiro nível, `admin` (gere utilizadores, roles, AD, JWT, sessões). **Não te damos
admin** — e parte do teste é confirmar que nem `viewer` nem `dba` lá chegam.

Se és um agente que não pode autenticar-se, pede que te entreguem **cada sessão já iniciada**, em
separado. Não confundas as duas.

## 1. Modo de operação

**Leitura livre; escrita só a lista fechada da secção 4, e só com `qa_dba`, e só na janela
combinada.** Tudo o resto — formulários, botões de ação, `POST`/`PUT`/`DELETE` — proibido, exceto os
testes negativos da secção 3 (que devem devolver 403 e que enviam corpo `{}` de propósito para que,
se o gate falhar, a escrita não se concretize).

É produção. Não existe ambiente de teste equivalente. Em dúvida, não cliques e regista.

## 2. Matriz de permissões — o núcleo desta ronda

Para **cada** linha, testa com **as duas contas** e regista o código HTTP e o que a UI mostra. O
esperado está na tabela; a tua tarefa é confirmar ou desmentir **cada célula**.

| Recurso | viewer | dba | Como testar |
|---|---|---|---|
| Ver dashboard, drill-downs, todos os módulos de análise | 200 | 200 | navegar |
| Ver LIVE (todos os painéis) | 200 | 200 | navegar; `GET /api/v1/live/{inst}/queries` |
| Ver saúde dos collectors | 200 | 200 | modal Collectors; `GET /api/v1/collectors/health` |
| Ver lista de mutes | 200 | 200 | modal Mutes; `GET /api/v1/kpi-mute` |
| Refresh do cache | 200 | 200 | `POST /api/intelligence-kpis/refresh` (sem corpo) |
| **Botões de ação visíveis** (re-correr, ativar/desativar, criar/remover mute, editar threshold) | **ausentes** | presentes | inspecionar DOM em cada modal |
| Correr collector | **403** | 200* | `POST /api/v1/collectors/{task}/run` — viewer com `{}`; **dba: NÃO chamar** (escrita real, fora da lista) |
| Ativar/desativar collector | **403** | 200* | idem — viewer com `{}`; dba não |
| Criar mute | **403** | 200 | viewer com `{}`; dba **só** conforme secção 4 |
| Remover mute | **403** | 200 | idem |
| Gravar threshold | **403** | 200 | `POST /api/v1/kpi-thresholds` — viewer com `{}`; dba **só** conforme secção 4 |
| Gravar inventário de servidores | **403** | 200* | `POST /api/config/sql-servers` com `{}` — viewer 403; **dba: NÃO chamar** (mexe em produção, fora da lista) |
| Resolver "servidor offline" | **403** | 200* | viewer com `{}`; dba não |
| Discovery de bases de dados | **403** | 200* | `POST /discover/all` — viewer com `{}`; dba não |
| **Painel Control** (`/watcherdb/control`) | **403** | **403** | abrir a URL com cada conta |
| Listar utilizadores | **403** | **403** | `GET /api/auth/users` |
| Mudar role de alguém | **403** | **403** | `POST /api/auth/admin/users/qa_viewer/role` com `{}` |
| Ver log de auditoria | **403** | **403** | `GET /api/auth/admin/auth-log` |
| Ver sessões ativas | **403** | **403** | `GET /api/auth/admin/sessions` |
| Config AD / JWT | **403** | **403** | `GET /api/auth/admin/system-config` |

`200*` = esperado que o `dba` **possa**, mas **não o testes** — é escrita real em produção fora da
lista fechada. Regista como "não testado por segurança; permissão inferida do desenho".

**Interpretação dos códigos nos testes negativos:** o esperado é **403**. Se vier **422/400**, o gate
de autorização deixou passar e só a validação do corpo salvou — **achado grave**. Se vier **200**, é
o pior caso. Se vier **401**, a sessão não estava autenticada — repete com sessão válida antes de
concluir.

**Ressalva técnica para `POST /api/config/sql-servers`:** usa **exatamente `{}`** (JSON válido).
Com JSON malformado este endpoint devolve 422 **antes** da autorização, e isso não é falha de gate.

## 3. Escalada de privilégio — o que um utilizador hostil tentaria

Com **`qa_viewer`** (a conta mais fraca), tenta — tudo deve falhar com 401/403, e nada deve
alterar estado:

1. **Mudar o próprio role**: `POST /api/auth/admin/users/qa_viewer/role` `{"role":"admin"}` — deve
   ser 403. (Corpo válido de propósito aqui: se passar, é a falha mais grave possível; regista
   e **para** — nós revertemos.)
2. **Reset da própria password por via de admin**: `POST /api/auth/users/qa_viewer/reset-password`
   `{}` — 403.
3. **Ver preferências/dados de outro utilizador**: procura no DOM ou na API qualquer parâmetro
   `username` que possas trocar por outro nome; regista se algum devolver dados alheios.
4. **Token**: copia o token JWT da sessão (localStorage/cookie). Testa: (a) usar depois de fazer
   logout — deve ser 401; (b) editar o payload (mudar `role`) e reenviar — deve ser 401 (assinatura
   inválida); (c) usar sem `Authorization` — 401. **Não** partilhes o token no relatório.
5. **Sessão desativada**: (não podes fazer, exige admin) — regista como "a verificar por nós":
   desativar `qa_viewer` com sessão aberta e confirmar que o próximo pedido dá 401.

Com **`qa_dba`**:
6. Tenta abrir `/watcherdb/control` e chamar `GET /api/auth/users` — **403** nas duas. Um `dba` que
   consiga listar ou alterar utilizadores é achado grave.

## 4. Escritas permitidas — lista fechada, só `qa_dba`, só na janela combinada

Quatro operações, **reversíveis**, com rollback imediato feito por ti na mesma sessão:

| # | Operação | Como | Rollback | Confirmar |
|---|---|---|---|---|
| 4.1 | Criar um mute de teste | modal Mutes → KPI `cpu-critical`, instância `QA_TESTE_NAO_EXISTE`, razão `ronda 2 QA — apagar`, 1 hora | remover na mesma modal | aparece na lista; depois desaparece |
| 4.2 | Remover o mute de 4.1 | botão Unmute | — | lista volta ao estado inicial |
| 4.3 | Gravar um threshold e repor | Settings → thresholds → escolhe um KPI configurável, **anota o valor atual**, muda +1, grava, **repõe o valor original**, grava | repor o original | valor final igual ao inicial |
| 4.4 | Refresh do cache | `POST /api/intelligence-kpis/refresh` | não precisa | 200 |

**Não** faças mais nenhuma escrita com `qa_dba`. Em particular: **não** corras collectors, **não**
mudes servidores, **não** resolvas eventos offline. São `200*` na matriz — permissão inferida, não
testada.

Depois do passe, **nós** confirmamos no log de auditoria (admin) que 4.1–4.3 deixaram rasto.

## 5. Superfície de injeção — em leitura, sem escrever nada

**Stored XSS (o mais relevante):** os nomes de instância, job, base de dados e package vêm da base de
dados e são renderizados na UI. Não podes injetar (não tens escrita na BD), mas podes **procurar**:
percorre as listas dos módulos e regista qualquer nome que contenha `<`, `>`, `"`, `'`, `&` — e
como a UI o rende (escapado ou interpretado). Um nome com `<b>` a aparecer a negrito é achado.

**XSS reflectido:** na pesquisa do header e em qualquer campo de filtro, tenta
`<img src=x onerror="window.__qa=1">` e `"><svg onload=window.__qa=1>`. Depois verifica
`window.__qa` na consola. A CSP com nonce deve bloquear a execução — se `__qa` ficar definido, é
achado crítico. Regista também se a CSP **reportou** o bloqueio na consola.

**Injeção em parâmetros de URL:** onde houver `server_id`, `instance`, `kpi_type` na URL ou na API,
tenta `'`, `' OR 1=1 --`, `../`, `%00`. Esperado: 400/404/422 limpos, **sem** texto ODBC, sem stack
trace, sem nomes de tabela na resposta. Regista o corpo de cada erro.

**Fuga de informação em erros:** provoca 403, 404 e 422 nos endpoints acima e lê o corpo. Qualquer
menção a caminho de ficheiro, nome de tabela/view, driver ODBC, versão de biblioteca ou traceback é
achado (severidade média — informação para um atacante).

## 6. Sessão

Com qualquer conta:
1. **Logout invalida?** Faz logout; reutiliza o token guardado — 401.
2. **Expiração**: regista o tempo de expiração do JWT (campo `exp` no payload); se a janela do teste
   o permitir, deixa uma aba parada até expirar e confirma que a UI pede novo login em vez de
   mostrar dados congelados.
3. **Heartbeat**: `POST /api/auth/heartbeat` — regista com que frequência a UI o chama e se uma
   sessão parada continua "online" indefinidamente.
4. **Duas abas, duas contas**: `qa_viewer` numa, `qa_dba` noutra, mesmo browser. Confirma que uma
   não herda a sessão da outra (cookies/localStorage por origem — se partilharem, a última a
   autenticar ganha; regista qual comportamento observas).

## 7. Formato do relatório

Como nas rondas anteriores, mais:
- **A matriz da secção 2 preenchida** — cada célula com o código observado. É o entregável
  principal desta ronda.
- Para cada escalada da secção 3: tentado / resultado / estado alterado? (deve ser sempre "não").
- Para 4.1–4.3: hora exata de cada escrita e do rollback (para cruzarmos com o log de auditoria).
- Achados de injeção com payload, contexto e **como a UI rendeu** — sem screenshot de dados reais.
- **O que não testaste** e porquê (os `200*` entram aqui).

Sintoma antes de causa; hipótese marcada como hipótese; instrumento a observar a ação (popups,
diálogos, `#toastContainer` só nasce no 1º toast). Redige hostnames, logins e SQL.

## 8. Dados sensíveis

Igual à ronda 1, e mais um: **não transcrevas tokens JWT** nem cookies no relatório, nem parciais.
