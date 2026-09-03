# Propagação V6 — achados da ronda 2 do QA + P-05 (identidade de BD)

Data: 2026-08-19 · Origem: WATCHERDB_V3.3, branch `wave-b-indexacao-dmv` · 5 commits

Este lote **não toca no schema da BD**. Não há alteração ao
`INSTALACAO_COMPLETA_UNIFICADA.sql` nem às tabelas `KPI_MSSQL_*`. É tudo código de
aplicação.

Âncoras do V6 verificadas a 2026-08-19 — o V6 **não é superset** do V3.3 e três dos
sete itens estão em sítios diferentes ou não se aplicam. Ler a coluna "aplica?" antes
de copiar seja o que for.

---

## Os cinco commits

| SHA | Assunto |
|---|---|
| `7daeb34` | identidade de BD explícita + password decifrada + markers de plataforma |
| `84cdbfd` | autorização antes da validação do corpo (18 endpoints → `Depends`) |
| `ca8d8f6` | `server_id` malformado dá 400; logout deixa de expor prefs de outro utilizador |
| `dd5f8d3` | redacção por role no LIVE; stub no cabeçalho deixa de mascarar o cookie |
| `7919dfb` | validação de `Origin` nas escritas sem corpo obrigatório |

---

## 1. P-05 — identidade de BD e password cifrada · **APLICA, prioridade máxima**

**O defeito, e é o mesmo no V6.** A password no `.env` está guardada como
`encrypted:<fernet>`. Só o `connection_pool` a lê com `get_secret()`, que decifra; os
routers liam com `os.getenv` cru e entregavam o *ciphertext* ao pyodbc, o que dá
login 18456. Resultado: a autenticação SQL nunca funcionou nesse caminho, e o
`SQL_TRUSTED_CONNECTION=yes` era o remendo que punha o dashboard a andar —
mascarando a falha de decifragem. O Windows Auth era o sintoma, não a doença.

Em cima disso, o default do `getenv` era `"true"` em quatro sítios: uma instalação
limpa que não escreva a variável **nasce em Windows Auth**, o que viola a Regra de
Ouro #2 logo no arranque.

**Âncoras V6 confirmadas:**

| Ficheiro V6 | Linha | Defeito |
|---|---|---|
| `api/routers/intelligence_kpis.py` | 277 | default `"true"` + precedência silenciosa do `SQL_TRUSTED_CONNECTION` |
| `api/routers/intelligence_kpis.py` | 279 | password lida com `os.getenv` |
| `api/routers/overview_dashboard.py` | 36 | default `"true"` |
| `api/routers/overview_dashboard.py` | 38 | password lida com `os.getenv` |
| `api/routers/connection_pool.py` | 686 | `use_windows_auth` lido cru |
| `migrate.py` | 42 | default `"true"` |

**Contrato a herdar** (não é só o diff — é a regra):

1. **Não existe default implícito de autenticação.** `UNSET` é um estado próprio, e
   nenhum estado que não seja explícito liga com Windows Auth.
2. **`CONFLICT` também é estado.** Duas variáveis a dizer coisas opostas não se
   resolvem por precedência silenciosa — recusa-se o arranque.
3. **Separação obrigatória entre resolver e impor.** `resolve()` **nunca levanta**,
   porque corre no import dos routers e tem de ser inofensiva em testes e
   ferramentas offline. Quem recusa o arranque é `enforce_explicit_identity()`, no
   ponto de entrada do serviço, **depois** do `.env` carregado.
4. **O guard não pode ir para o import do `watcherdb_main`.** No V3.3 há cinco
   ficheiros de teste que o importam; um raise ali põe a suite vermelha em CI sem
   nada estar mal. Verificar o equivalente no V6 antes de escolher o sítio.
5. **Segredos lêem-se sempre com `get_secret()`**, nunca com `os.getenv`. O
   `get_secret` regista erro e devolve o default em vez de levantar, portanto é
   seguro no import.
6. O log de arranque diz **a origem da decisão**, não só o valor — sem isso, um
   `WINDOWS_AUTH=True` inexplicado custa meio dia a diagnosticar (custou).

Ficheiro de referência: `watcherdb/core/db_identity.py` no V3.3. Copiar o módulo
inteiro é preferível a reimplementar.

**Nota operacional para quem aplicar:** depois disto, um `.env` com
`SQL_TRUSTED_CONNECTION=yes` e `INTELLIGENCE_USE_WINDOWS_AUTH=false` (o caso real em
produção) passa a `CONFLICT` e **o serviço recusa arrancar**. É intencional, mas
tem de ser combinado antes, e a credencial tem de ser testada primeiro pelo caminho
decifrado.

---

## 2. R2-01/R2-06 — autorização antes da validação do corpo · **APLICA**

**O defeito.** O FastAPI resolve as dependências da assinatura **antes** de
`request_body_to_args`. Um gate chamado dentro do corpo da função deixa o Pydantic
validar primeiro: um corpo inválido devolve 422 a quem não está autorizado,
revelando nomes de campo e a forma do validador, sem a autorização alguma vez ter
corrido.

**Não é escalada de privilégio** — o gate era a primeira instrução executável, logo
um corpo válido era recusado antes de qualquer mutação. Reclassificado GRAVE → MÉDIA
na triagem. O que custa é divulgação de estrutura e a anulação da heurística de
detecção de qualquer auditoria futura.

**Âncora V6:** `api/routers/auth_compat.py` tem **18** ocorrências de
`await _require_admin(request)` — o mesmo número do V3.3 antes do fix.

**Contrato:** o gate usa-se via `Depends(_require_admin)` na assinatura, **nunca**
`await` no corpo. Converter também os endpoints **sem** corpo: dão 403 por acidente
(não há corpo para validar), mas basta alguém inserir uma linha antes do gate para
se tornar explorabilidade a sério — e deixá-los inline é escrever a invariante com
dez excepções à vista. No V3.3 a invariante ficou escrita no docstring do
`_require_admin`; replicar.

---

## 3. R2-05 — `server_id` malformado · **APLICA, noutro ficheiro**

**O defeito.** O parsing nunca falha: qualquer string produz um par
servidor/instância, que segue até ao pyodbc e rebenta num 500 genérico. Lixo enviado
pelo cliente é 400.

**Âncora V6: NÃO é `api/routers/queries/helpers.py`.** No V6 o
`execute_query_on_server` vive em **`api/routers/sql_queries.py`**. Aplicar lá.

**Contrato:** validar a **forma** (`HOST`, `HOST\INSTANCIA`, `HOST_INSTANCIA`, porta
opcional, máx. 128 chars) e não a existência — `_resolve_credentials` devolver `None`
é o fallback desenhado para servidores sem credencial guardada, portanto
"desconhecido" e "sem credencial" não são distinguíveis nessa camada e um 404
partiria servidores legítimos. A mensagem de erro **não ecoa o valor recebido**.

---

## 4. R2-02 — redacção por role no LIVE · **APLICA**

**A decisão de produto primeiro:** o viewer **vê** o LIVE. O eixo do RBAC é
ler-vs-escrever, não área (decisão do owner, V3.3 `493c6de`). Fechar a página ao
viewer reverteria essa decisão; redigir os campos preserva-a e fecha a exposição. A
flag `rbac_live_admin_only` fica desligada.

**Âncora V6:** `api/routers/live_monitoring.py` existe e tem 23 ocorrências dos
campos sensíveis. Aplica-se tal e qual.

**Contrato:**

1. **Ao nível do router (`route_class`), não endpoint a endpoint.** O endpoint 17
   nasce coberto. Controlo que depende de alguém se lembrar apodrece.
2. **O SQL não se trunca — emite-se hash.** Truncar a 500 chars continua a revelar
   nomes de tabela e a forma da query. Um SHA-256 estável deixa o viewer agrupar
   ocorrências da mesma query sem ver o texto.
3. **Campos operacionais ficam.** `session_id`, duração, CPU, waits. O viewer
   continua a ver *que* há bloqueio, só não vê o quê.
4. O role vem do `request.state.user` que o middleware de auth já põe — custo zero
   num endpoint que faz polling de 5 em 5 segundos. Confirmar que o middleware do V6
   faz o mesmo antes de copiar.

---

## 5. 2b — validação de `Origin` · **APLICA como hardening, com ressalva**

**Ressalva importante, e é o item onde o V6 difere mais.** O
`_get_token_from_request` do V6 (`api/routers/auth_compat.py:88`) devolve `None`
quando não há cabeçalho — **não tem fallback para cookie**. Ou seja: o V6 não
autentica por cookie, logo **não tem hoje a superfície de CSRF que justificou o fix
no V3.3**. O browser não anexa credenciais sozinho.

Aplicar mesmo assim? Sim, mas como hardening barato e não como correcção urgente — e
sobretudo para que, no dia em que o V6 ganhar autenticação por cookie, já esteja
coberto. Se a prioridade estiver apertada, este é o item que se adia.

**Âncoras V6 (os três existem):** `api/routers/collectors.py:274`
(`body: Optional[RunRequest] = None`), `api/routers/database_discovery.py:61`
(`POST /all`, só Query params), `api/routers/auth_compat.py:302` (`unlock`).

**Contrato:** fechar por validação de `Origin` e **não** por "exigir corpo". Exigir
corpo funciona, mas só por efeito colateral — o corpo força `application/json`, que
força preflight, que cai na allowlist do CORS. Foi assim que o buraco nasceu:
`Optional[RunRequest] = None` tornou um corpo opcional e reabriu a porta em silêncio.
Controlo que depende de efeito colateral apodrece no primeiro refactor.

Política, e porquê não é mais apertada: método seguro passa; **`Origin` ausente
passa** (curl, harness de carga, collectors — sem browser não há cookie anexado
automaticamente, e recusar aqui partiria a ronda 3 sem acrescentar segurança);
`Origin` diferente da nossa dá 403.

---

## 6. R2-03 (backend) — stubs no cabeçalho · **NÃO APLICA AINDA**

No V3.3 o `_get_token_from_request` devolvia `auth_header[7:]` sempre que o cabeçalho
começava por `Bearer `, sem cair no cookie — logo um `Authorization: Bearer null`
mascarava um cookie válido e dava 401. É o defeito que o SSIS Manager apanhou na
migração para cookie HttpOnly (`rbac.py`, commit `6ec4c55`).

**No V6 isto é inócuo hoje**, porque não há fallback para cookie: com ou sem o fix, um
stub resulta em 401. Aplicar só quando (e se) o V6 passar a autenticar por cookie —
e nessa altura aplicar **antes** de mexer no frontend, porque é pré-requisito.

---

## 7. R2-04 — resíduo cross-user no `localStorage` · **VERIFICAR ANTES**

No V3.3 o `clearAuthData()` removia o token e o perfil mas deixava as chaves
`user:<nome>:*`, e as `userCustomQueries` do owner ficaram legíveis por uma conta de
teste no mesmo perfil de browser.

O portal do V6 é subset e **não usa o esquema `user:${username}:`** nos templates que
verifiquei. Existe `templates/watcherdb_portal.html` com `AUTH_TOKEN_KEY` e
`setAuthData`, portanto há base comum — mas o esquema de chaves por utilizador pode
não existir lá. **Fazer grep das âncoras antes de propagar**; se o esquema não
existir, não há nada a corrigir e o item fecha-se como "não aplicável".

**Contrato, se aplicar:** limpar no logout **e** limpar as de outros no login — o
segundo caminho é o que apanha o browser fechado sem logout, que o primeiro sozinho
não cobre.

---

## 8. Markers de plataforma no `requirements.txt` · **VERIFICAR**

`pywin32`, `wmi` e `winkerberos` são Windows-only e sem marker `sys_platform` rebentam
o `pip install` num runner Linux — o que faz o pytest nunca correr. Verificar se o V6
tem CI em Linux e se o `requirements.txt` tem os mesmos três pacotes sem marker.

---

## Ordem recomendada

1. **P-05** — é o único com impacto de segurança real e imediato (Regra de Ouro #2).
2. **R2-01** — uniforme, mecânico, e é o que um CISO de banca pergunta.
3. **R2-02** — fecha exposição de dados sem reverter decisão de produto.
4. **R2-05** — robustez, barato.
5. **2b** e **8** — hardening.
6. **R2-03** e **R2-04** — só depois de confirmar que se aplicam.

## Validação esperada

Cada item foi validado no V3.3 com prova comportamental, não só leitura de código.
Replicar o mesmo padrão: para o P-05, os quatro estados do resolvedor e uma ligação
real pelo caminho corrigido; para o R2-01, um pedido com corpo inválido sem
autorização a devolver 401/403 em vez de 422; para o R2-02, os três roles sobre um
payload com campos aninhados; para o 2b, os sete cenários de `Origin`.
