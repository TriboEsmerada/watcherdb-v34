# PROPAGAÇÃO V6 — A1: o cartão de Disponibilidade deixa de dizer "Offline 0" (migration 010)

> Para a AI do V6. **Verificar primeiro, assumir nunca.** A mudança está na base partilhada
> WatcherDB_Intelligence, portanto **o V6 já a vê** se ler as mesmas vistas. O trabalho aqui não é
> reaplicar o DDL; é confirmar que o V6 consome as vistas sem se partir e aproveitar as colunas novas.
> Origem: `WATCHERDB INTELLIGENCE V1/database/migrations/010_offline_events_first_event_time.sql`,
> canónico `INSTALACAO_COMPLETA_UNIFICADA.sql` e `docs/CHANGELOG.md` [2.29.0].

## 0. O que mudou na base (já aplicado a 14/09 na base viva)

| Objecto | Antes | Depois |
|---|---|---|
| `KPI_MSSQL_SERVER_OFFLINE_EVENTS` | sem hora de início | coluna nova `First_Event_Time DATETIME2 NULL` |
| `usp_MSSQL_Server_Offline_Upsert` | só `Event_Time`, reescrito a cada ciclo | grava também `First_Event_Time`, **só no INSERT** |
| As 3 vistas `SERVER_OFFLINE_{AGG,DET,GROUPED}_VIEW` | só eventos com `Event_Time` nos últimos 15 min | todos os eventos com `Is_Resolved = 0`, sem janela |
| `GROUPED_VIEW.First_Event_Time` | alias de `Event_Time` (mentia) | coluna verdadeira, `COALESCE` com `Event_Time` |
| `GROUPED_VIEW` e `DET_VIEW`: `Env` | igualdade host = instância (dava `Undefined`) | por prefixo, `OUTER APPLY ... TOP 1` |
| `GROUPED_VIEW` | — | colunas novas `Last_Seen_Time` e `Minutes_Since_Last_Seen` |

## 1. Factos medidos (não são hipóteses)

1. A 10/09 o SQLHDSPRD407 esteve em baixo 6h30 com o cartão a dizer Offline 0. O MERGE reescreve
   `Event_Time` a cada ciclo; quando o recolhedor salta ciclos (breaker anti-alarme aberto, ciclo QA
   parado 34 min), o evento aberto envelhece para lá dos 15 min e sai das três vistas.
2. A 14/09 havia 5 eventos abertos, todos órfãos: servidores que já não existem no inventário, de
   Maio e Julho. **Retirar a janela sem fechar os órfãos transformava Offline 0 em Offline 4 falsos.**
   Foram fechados com `Resolved_By = 'auto-orphan-cleanup'` (fora do inventário E mais de 24h).
3. Eventos são por host (`SQLHDSPRD213`) e o inventário por instância (`SQLHDSPRD213_I01`). A
   igualdade exacta nunca casava, o `Env` saía `Undefined`, e o filtro de ambiente escondia o servidor.
4. Ensaio com evento sintético `ZZZ_TEST_OFFLINE_SIM` envelhecido 20 min: antes, 0 linhas na vista;
   depois, 1 linha com `Minutes_Since_First_Event = 0` e `Minutes_Since_Last_Seen = 20`.

## 2. O que o V6 tem de verificar

- **Consumidores de `Event_Time` como "desde".** Grep por `First_Event_Time`, `Minutes_Since_First_Event`
  e `Event_Time` no código que desenha a modal ou o cartão de offline. Se o V6 mostra `Event_Time` como
  "em baixo desde", passa a mentir menos se trocar para `First_Event_Time`. Se já lê `First_Event_Time`,
  ganha o valor certo sem mexer em código.
- **Contagens por ambiente.** O `Env` deixou de ser `Undefined` para servidores com instância nomeada.
  Se o V6 tinha um contorno para `Undefined` (inferência por nome, por exemplo), pode ter passado a
  contar duas vezes. Confirmar.
- **Frescura.** `Minutes_Since_Last_Seen` alto significa que o recolhedor deixou de ver o servidor, não
  que o problema passou. Não pintar esse valor de verde.
- **Nenhum consumidor pode depender da janela de 15 min** para esconder eventos antigos. Se algum
  dependia, era um bug escondido; os órfãos já não existem.

## 3. Armadilha a não herdar

A migração **008b faz `CREATE PROCEDURE` com o corpo inteiro e sem `First_Event_Time`**. Correr a 008b
depois da 010 apaga a hora de início em silêncio. A 010 foi escrita para funcionar com e sem a 008
aplicada (detecta as colunas `Service_Check_*` e gera a procedure certa). Ordem: `008 → 008b → 010`.

**Desvio registado:** o canónico declara as colunas da 008 e a base viva nunca as recebeu. Foi isso que
fez o primeiro `ALTER PROCEDURE` falhar com quatro erros 207. Se a base do V6 for outra, verificar
`COL_LENGTH('dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS', 'Service_Check_Attempted')` antes de qualquer DDL.

## 4. Pendente, em lote próprio (não aplicar por conta própria)

- **P1b:** auto-resolve contínuo de órfãos no recolhedor (`collect_server_ping.py`), com a mesma regra
  de fora do inventário e mais de 24h.
- **P4:** `Is_Available = 0` derivado de `SERVER_OFFLINE_EVENTS`, **nunca** de um timeout de ligação cru.
  Condição do guardião: uma tempestade de DNS no host do recolhedor não pode virar apagão em massa
  explícito no dashboard.
