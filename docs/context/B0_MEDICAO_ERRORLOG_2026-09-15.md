# B0 — medição do errorlog de produção antes de desenhar a retenção

> 2026-09-15 | orquestrador | Bloco B do `PLANO_EXECUCAO_ALERTAS_ERRORLOG_2026-09-14.md`.
> Identidade: `sql_monitoring`, só leitura (`xp_readerrorlog`), pool do V3.4. Scripts no scratchpad da sessão.

## Método

- As 14 instâncias de produção com mais linhas no histórico dos últimos 30 dias. Todas legíveis por
  `sql_monitoring`, incluindo 405 e 406. `xp_enumerrorlogs` não é permitido, e não faz falta.
- Log actual de cada uma, lido inteiro e **sem filtro por palavra**. Log anterior só em 6 instâncias, para
  amostras. Regras afinadas com linhas reais antes de contar (a primeira versão confundia o cabeçalho de
  cada log rodado com um arranque, e "Parallel redo is shutdown" com um encerramento).
- Política medida: **guardar** eventos um a um, **agregar** erros repetitivos por hora e número, **largar**
  informativos.

**Limites.** Em 11 instâncias o log actual cobre só 4 a 10 horas, porque rodaram de madrugada. A
extrapolação para um dia inclui a rajada de arranque e por isso sobrestima o que se guarda. O log anterior
de SQLHDSPRD214 tem 6.405.936 linhas e não foi classificado: uma primeira leitura sem timeout ficou
pendurada mais de 20 minutos e foi parada.

## Volume por dia, 14 instâncias

| Medida | Linhas por dia |
|---|---|
| Total no errorlog | 168.781 |
| Com a palavra "Error" (o que o recolhedor filtra hoje) | 71.508 |
| Guardar um a um, com a política | 336 |
| Linhas agregadas (hora, número de erro) | 388 |

Com a política, cerca de 724 linhas por dia em vez de 71.508, uma redução de 99%. Extrapolado para as 59
instâncias com histórico, dá cerca de 3.000 linhas por dia e 275 mil em 90 dias. Hoje a tabela de histórico
tem 2,7 milhões, e mesmo assim só guarda uma janela por dia.

## Classes

| Acção | Classe | Exemplos medidos |
|---|---|---|
| Guardar | arranque | "SQL Server is starting at normal priority base" (não contém "Error": o filtro de hoje perde-o) |
| Guardar | encerramento | "SQL Server is terminating", "SQL Trace was stopped due to server shutdown" |
| Guardar | mudança de papel AG | "state of the local availability replica ... changed from", "is changing roles from" |
| Guardar | memória paginada | 124 em 25 dias em SQLRPAPRD02, 8 em 10 h em SQLHDSPRD302 |
| Guardar | dump, non-yielding, I/O 833, DBCC com erros, autogrow falhado | nenhum na janela medida |
| Guardar | erros com severidade 11 a 16 que não são repetitivos | 18210 e 3041 (backup falhou a escrever) em SQLHDSREVPRD03, 1474, 1479 e 9642 (mirroring) |
| Agregar por hora | 18456 login falhado | sinal de segurança: separar do motor |
| Agregar por hora | 33208 e 33204 auditoria sem acesso ao log de segurança | 5.819 em 10 h em SQLHDSPRD202; 260.706 em 25 dias em SQLRPAPRD02 |
| Agregar por hora | 976, 983, 35262, 41145, 35278 informativos de AG no arranque | severidade 14 a 17, rajada a cada arranque |
| Agregar por hora | 17836 pacote de rede inválido, 1222 lock timeout | severidade 20 no 17836, normalmente scanners |
| Largar | sucesso de backup, arranque de bases, parallel redo, configuração | 4.407 linhas de backup com sucesso em 10 h em SQLHDSPRD302 |

**Severidade sozinha não serve de filtro.** O erro que mais volume faz, 33208, tem severidade 17.

## Achados operacionais (para o owner)

1. **Nove instâncias de produção reiniciaram esta madrugada, entre as 02:07 e as 05:04 de 15/09:** 214,
   MDMPRD01, 301, 405, REVPRD03, 213, 201, 023 e 013. É o cenário do ecrã de offline, e com o recolhedor
   no portátil desligado a monitorização não viu nada.
2. **A auditoria do SQL Server não consegue escrever no log de segurança** em pelo menos 6 instâncias (202,
   RPAPRD02, MDMPRD01, 301, 024, REVPRD03). É configuração da conta de serviço, e é o maior produtor de
   ruído do errorlog. Numa banca, auditoria que não escreve é também um achado de conformidade.
3. **SQLHDSPRD214 escreveu 6,4 milhões de linhas no log anterior ao reinício.** A causa não foi
   identificada. O ficheiro deve ser visto no disco antes de o recolhedor voltar a ler logs anteriores.
4. **SQLHDSREVPRD03** teve 12 falhas de escrita de backup (18210) em 6 horas.
5. Três instâncias (302, 202, 406) rodam o log à meia-noite; as restantes só rodam no arranque. Por isso
   SQLRPAPRD02 tem um log de 25 dias com 525 mil linhas.

## O que isto decide para B1 e B2

- O recolhedor tem de ler **sem** `N'Error'` e classificar: arranques e encerramentos não têm a palavra.
- Agregação por hora e número, com contagem, primeira e última hora e uma linha de exemplo.
- `xp_readerrorlog` sobre um ficheiro enorme pode prender uma sessão em produção: o recolhedor precisa de
  timeout de consulta e nunca deve ler logs anteriores em bloco.
- 18456 vai para uma classe de segurança separada; o aviso de errorlog (A3, hoje não ligado) só volta a
  ser candidato depois disto.
- Retenção de 90 dias cabe folgada: cerca de 275 mil linhas para 59 instâncias.
