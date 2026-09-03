# Triagem -- QA externo, Ronda 2 (autorizacao / sessao / injeccao)

Data: 2026-08-18 | Perfil usado pelo QA: `qa_viewer` | Alvo: PRD, porta 8433, TLS

---

## R2-01 -- CONFIRMADO na fonte, com duas correccoes ao relatorio

O QA observou 422 (em vez de 403) em dois endpoints com corpo `{}` e formulou a
hipotese de que "a verificacao de role esta *dentro* da funcao, em vez de num
`Depends` que corre antes". **A hipotese esta certa e o mecanismo e' esse.**

Ordem real no FastAPI (`solve_dependencies`): as dependencias declaradas na
assinatura sao resolvidas e executadas ANTES de `request_body_to_args`. Logo:

- `Depends(gate)` na assinatura -> 403 antes de validar o corpo
- `await gate(request)` dentro do corpo da funcao -> o Pydantic valida primeiro,
  e um corpo invalido devolve 422 sem a autorizacao alguma vez correr

E' exactamente por isto que os quatro endpoints operacionais que o QA testou
(collectors/run, kpi-mute, kpi-thresholds, config/sql-servers) devolveram 403
com `{}`: usam `Depends`. Os de `/api/auth/*` chamam inline.

### Correccao 1 -- o alcance e MAIOR do que o relatado

O QA concluiu "o problema e' pontual e cirurgico, nao sistemico". Nao e'.
Sao **oito** endpoints com corpo validado e gate inline em `auth_compat.py`,
nao dois. O QA encontrou dois porque testou dois:

| Linha | Endpoint | Testado pelo QA |
|---|---|---|
| 363 | `POST /users` (create_user) | nao |
| 409 | `POST /users/{u}/toggle` | nao |
| 442 | `POST /users/{u}/reset-password` | SIM (422) |
| 484 | `POST /admin/users/{u}/update` | nao |
| 506 | `POST /admin/session-policy` | nao |
| 719 | `POST /admin/ad-config` | nao |
| 732 | `POST /admin/ad-domains` | nao |
| 744 | `POST /admin/users/{u}/role` | SIM (422) |

Os endpoints `GET /api/auth/admin/*` tambem chamam inline, mas nao tem corpo
para validar -- por isso devolvem 403 e passaram no teste do QA. O defeito
existe la' tambem; e' apenas invisivel.

### Correccao 2 -- a severidade e' MENOR do que a atribuida

O QA classificou GRAVE, por analogia com a sua propria regua ("422 = gate deixou
passar"). Verificado linha a linha: em todos os oito, `_require_admin` e' a
**primeira instrucao executavel** do corpo da funcao -- nada corre antes dela.

Consequencia: com um corpo VALIDO, a funcao e' entrada e o gate nega antes de
qualquer mutacao. **Nao ha' escalada de privilegio.** O `{"role":"admin"}` que o
QA (bem) nao disparou devolveria 403.

O que o defeito realmente custa:

1. Divulga nomes de campo e a forma do validador a quem nao esta autorizado (R2-06 e' o mesmo defeito visto de outro angulo)
2. Aceita e desserializa o corpo de um pedido nao autorizado antes de o recusar
3. Anula a heuristica de deteccao do proprio QA -- e de qualquer auditoria futura
4. E' um risco latente: basta alguem inserir uma linha antes do gate para se tornar explorabilidade a serio

Reclassificado **MEDIA**. Vale corrigir, e a correccao e' uniforme e pequena --
mas nao e' o buraco de autorizacao que o titulo sugere, e o relatorio nao deve
ir para um cliente banking com GRAVE nesse campo.

---

## Restantes achados

| ID | Veredicto | Nota |
|---|---|---|
| R2-02 `/watcherdb/control` 200 ao viewer | Confirmado (era B-18 da Ronda 1) | Sem fuga de dados -- os endpoints por tras dao 403. Expoe o esqueleto da UI de admin |
| R2-03 JWT em localStorage, 24h | Confirmado, mudanca de desenho | Cookie httpOnly implica rever o wrapper de fetch inteiro. Reduzir o lifetime e' o passo barato |
| R2-04 residuo cross-user no localStorage | Confirmado, e mais incomodo do que "Baixa" sugere | As `userCustomQueries` do owner ficaram legiveis pela sessao `qa_viewer` no mesmo perfil de browser. Logout deve limpar `user:<outro>:*` |
| R2-05 `server_id` malformado -> 500 | Confirmado, robustez | Corpo limpo, sem fuga. Devia ser 400/404 |
| R2-06 422 expoe nomes de campo | Mesmo defeito que R2-01 | Fecha-se junto com ele nos endpoints gated |

---

## O ponto operacional que atravessa tudo

O QA reportou o host a cair **repetidamente** durante a sessao. Medicao
independente minha no mesmo dia: `/healthz` -- que nao faz I/O nenhum --
responde 200 mas demora **~8,2 s** de forma consistente, com o servico
`Running` e a servir 200s a outros clientes em simultaneo.

Sao duas observacoes independentes do mesmo fenomeno: nao e' o servico a cair,
e' o event loop congestionado sob concorrencia. E' o BUG-5A-01 a manifestar-se,
e reforca que a Ronda 3 (carga) e' a proxima prioridade, nao mais uma ronda
funcional. Uma ronda funcional contra um alvo a oscilar produz falsos negativos
-- foi o que aconteceu a metade da matriz desta ronda.

---

## Bloqueios que o QA nao pode resolver sozinho

1. `qa_dba` nao existe -- toda a coluna dba ficou por testar
2. `qa_viewer` foi provisionado com role `dba`, nao `viewer` (pendente desde a Ronda 1)
3. Host instavel -- ver acima
4. As escritas da seccao 4 e o corpo valido da 3.1 sao do owner, por desenho
