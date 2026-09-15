# PROPAGAÇÃO V6 — aba Users: sessões ativas agora e fim do falso "inativo"

> Para a AI do V6. **Verificar primeiro, assumir nunca.** Origem: `docs/context/USERS_SESSOES_ATIVAS_2026-09-15_apply.py`
> (código integral e testes). Sem mudança de base de dados.

## O defeito (verificar se o V6 o tem)

O SQL Server não guarda data de último login. Se a lista de inativos do V6 fizer `MAX(login_time)` de
`sys.dm_exec_sessions`, então "último login" é só "sessão ligada agora", "Nunca" quer dizer "sem sessão neste
momento" e os dias contam desde a criação. Grep: `FROM sys.dm_exec_sessions` junto de `days_inactive`, e o
texto "30+ dias". Medido no V3.4 em SQLHDSPRD212: 136 de 158 logins apareciam como inativos. Grupos do AD
aparecem sempre como inativos, porque a sessão regista o login individual.

Se o relatório do V6 recomendar desabilitar contas "inativas" com base nessa lista, é o risco mais sério:
corrigir primeiro.

## Correcção (a mesma do V3.4)

- A secção passa a "Logins sem sessão ligada agora", com o mesmo número e texto honesto; o cartão do topo
  diz "Sem sessão agora". Os dias dizem "(desde a criação)" ou "(sessão aberta)".
- Secção nova "Sessões ativas agora" (nunca "Acessos recentes"): por login, sessões, ligado desde, último
  pedido, até 3 hosts e 2 programas, do pedido mais recente para o mais antigo. Exclui a própria sessão da
  leitura (`@@SPID`) e só `is_user_process = 1`. Estado vazio explícito. Nota sobre grupos do AD.
- Hosts e programas só no ecrã: não entram no relatório (parecer da persona DBA cliente).
- O relatório deixa de recomendar desabilitar; diz que sem sessão agora não prova inatividade.

## Decisão de produto em aberto (não portar como feito)

Inatividade verdadeira precisa de recolha periódica de sessões para a Intelligence (base partilhada,
canónico, veto do guardião do recolhedor). O owner ainda não decidiu.

## Testes a portar

`tests/unit/test_users_sessoes_ativas_20260915.py` (6: agregação e ordem com linhas simuladas, tecto de
hosts e de linhas, consulta, secção fora do relatório, textos, chaves). A prova do V3.4 correu o endpoint
real contra SQLHDSPRD212 (52 logins com sessão, ordem confirmada) e renderizou a aba em inglês em Node.
