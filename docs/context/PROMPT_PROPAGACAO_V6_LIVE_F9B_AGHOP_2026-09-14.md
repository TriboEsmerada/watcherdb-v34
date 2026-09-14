# PROPAGAÇÃO V6 — LIVE: nomes no Fleet, tooltips e salto à primária (lotes F9b e AG HOP)

> Para a AI do V6. **Verificar primeiro, assumir nunca.** Só se aplica se o V6 tiver o painel LIVE.
> Sequência: aplicar antes os dois lotes anteriores (`PROMPT_PROPAGACAO_V6_LIVE_CANAIS_2026-09-11.md` e
> `PROMPT_PROPAGACAO_V6_LIVE_F9_2026-09-11.md`); as âncoras destes dependem deles.
> Origem: `docs/context/LIVE_F9B_2026-09-11_apply.py` e `docs/context/LIVE_AG_HOP_2026-09-11_apply.py`
> (código integral). Commits no V3.4: `dca254e`, `185a4ff`, `8f9f995`.

## Lote F9b — nomes de instância e tooltips

| Sintoma medido | Causa | Correcção |
|---|---|---|
| Fleet dashboard mostra "SQLMDMQLT…", "SQLHDSPRD…" cortados em 4 painéis | células de 70–75 px com elipse, e o nome já vinha amputado por `split('_')[0]`, o que torna duas instâncias do mesmo host indistinguíveis | id completo (`HOST_INST`) em 130 px com `flex-shrink:0`; elipse e `title` ficam como rede |
| Tooltips em português com a interface em inglês | literais crus: botão LIVE da navbar (title e aria-label), "Arrasta para mover" no bezel, "Expandir/Reduzir modal" no modal de diagnóstico; o OFF não tinha tooltip | chaves `live.drag_to_move`, `live.off_tip`, `live.nav_aria`, `live.nav_tip` e `ui.expand_collapse_modal` em pt-PT, en e es; pt-BR herda |

Grep no V6: `.instance||'').split('_')[0]` (6 ocorrências no V3.4, todas no renderizador do Fleet),
`width:75px;color:var(--color-text-link)`, `width:70px;color:var(--color-text-link)`,
`title="Arrasta para mover"`, `title="LIVE - Monitoramento em Tempo Real"`.

O botão LIVE da navbar é HTML estático, portanto usa `data-i18n-title` e `data-i18n-aria`, que o motor
já suporta. Os botões do bezel são gerados por JS e usam `t()` no template, que é o padrão que o botão
de destacar janela já usava ali. **Não misturar os dois mecanismos no mesmo grupo de botões.**

## Lote AG HOP — o canal AlwaysOn aberto numa secundária mostra a visão da primária

**Facto medido a 11/09 (SQLHDSPRD405) e confirmado a 14/09 (SQLHDSGENPRD02):** numa secundária,
`sys.dm_hadr_database_replica_states` devolve apenas a linha local. O canal mostrava uma réplica só e
o atraso saía sempre "n/d". A primária vem do estado do grupo, replicado pelo cluster e visível em
qualquer nó.

Contrato do endpoint depois da mudança:

- Query auxiliar na instância pedida: nome do AG, `ags.primary_replica` de
  `sys.dm_hadr_availability_group_states`, e `@@SERVERNAME` como nome local.
  **`@@SERVERNAME`, não `SERVERPROPERTY('ServerName')`:** num host renomeado sem `sp_dropserver` os
  dois divergem, e é o primeiro que emparelha com `replica_server_name` (parecer sql-deep-reviewer).
- Normalizar ambos os nomes antes de comparar: maiúsculas, cortar a porta depois da vírgula, host sem
  domínio, manter a barra invertida da instância. Formato confirmado na frota: `HOST\INST` dos dois lados.
- Para cada AG cuja primária não é a instância pedida, agrupar por primária e ler a mesma query lá.
  **Tecto de 2 primárias e 5 s por salto**, porque o canal sonda de 5 em 5 segundos.
- Falha no salto mantém as linhas locais e acrescenta nota. **Nunca 503 por causa do salto.** A query
  local a falhar continua a dar 503, como antes.
- Resposta ganha `hops` e `notes`; a tabela abre com "Dados lidos na primária X, esta instância é
  secundária" (`live.ag_from_primary`, com marcador `{primary}`).

**O endpoint passa a `def`, não `async def`.** O pyodbc é síncrono e o salto faz até 3 idas; o tempo de
login é de 15 s por ligação, portanto o pior caso são 30 s a bloquear o event loop do FastAPI para
todos os utilizadores. Como `def`, o FastAPI corre-o no threadpool. **Os restantes endpoints do LIVE
têm o mesmo padrão com uma ida cada:** está registado como dívida no V3.4 e o V6 deve verificar o seu.

Casos que degradam com nota e nunca com erro: AG distribuído (a primária é o reencaminhador, não um
servidor), host renomeado, AG sem quórum (`primary_replica` nulo), e failover a decorrer (a primária
antiga responde em RESOLVING durante um ciclo e corrige-se no seguinte).

## Testes a portar

`tests/unit/test_live_f9b_20260911.py` (4, estáticos) e `tests/unit/test_live_ag_hop_20260911.py` (8):
normalização de nomes, secundária salta e substitui as linhas do AG, primária não salta, falha no salto
mantém linhas locais com nota, primária desconhecida idem, erro local continua a dar 503, endpoint é
síncrono, e o portal diz de onde vieram os dados.
