# PROMPT V1 INTELLIGENCE — instância com identidade dividida (`SQLHDSSQLT301_I01`)

Data: 2026-08-31 | Origem: sessão V6, ao ligar o portal ao inventário canónico
**REVISTO 2026-08-31 (sessão V3.3)** após confronto com o rasto escrito — a versão
inicial deste doc tinha a premissa invertida; ver "Correcção de premissa" abaixo.
Destinatário: sessão V1 Intelligence (dono do `servers.json` canónico e dos collectors)
**Não executar nada sem decisão do owner** — envolve história de 24 tabelas.

## Correcção de premissa (o que a 1.ª versão deste doc dizia de errado)

A 1.ª versão assumia que `SQLHDSSQLT301_I01` (S a mais) era gralha no canónico e que o
id "devia ser" `SQLHDSQLT301_I01`. **O rasto escrito diz o contrário**:

- Caso "SS301 FECHADO", 2026-07-27 (`WATCHERDB_V3.3/docs/context/CONTEXT.md:126`):
  o reconcile corrido pelo owner no SSMS mostrou que **o typo está no `@@SERVERNAME`
  do próprio servidor** (fix no server bloqueado por restart, FIND-20260506-101).
- O id do JSON canónico foi **deliberadamente alinhado** ao double-S nessa data
  (`SQLHDSQLT301_I01` → `SQLHDSSQLT301_I01`; host mantém o DNS real; I02 intocado).
- Rename propagado ao V3.3 a 2026-08-05 (commit V3.3 `2dc6412`; `SOLUCOES.md:35`).
- O `sql_servername_alias` replicado também está explicado: alias do ping collector,
  redundante-inofensivo (mesma entrada do CONTEXT.md).

Portanto: **não há gralha a corrigir no canónico** — o double-S é a decisão em vigor
até haver restart do servidor. Qualquer "correcção" para single-S desfaz uma decisão
do owner de 27/07 e reabre o mismatch com o `@@SERVERNAME`.

## O problema que continua real: a história está partida em 24 tabelas

A mesma máquina física tem **duas identidades** na BD partilhada, e a divisão segue a
família de collector (medido, não suposto):

| tabelas | nome single-S (`SQLHDSQLT301_I01`) | nome double-S (`SQLHDSSQLT301_I01`) |
|---|---|---|
| filegroups + datafiles + disk usage (colectores SQL) | 135.688 | 0 |
| disk perf + memória + CPU (colectores OS) | 0 | 78.453 |
| backup failures + availability | 0 | 6.012 |
| ensemble + briefing (camada AI) | 3.409 | 0 |
| errorlog | 12.521 | 6.250 |
| anomaly detection | 8.528 | 406 |
| `KPI_MSSQL_INST_ENVS` (backups) e `kg_entities` | 1+1 | 1+1 |
| **total, em 24 tabelas** | **160.156** | **91.134** |

Nota: na tabela acima, "single-S" é o nome PRÉ-rename de 27/07 — a história antiga dos
collectores SQL ficou gravada sob ele; os collectores OS/backup e recolha pós-rename
gravam sob o double-S. Consequências que existem hoje e não dão erro:

1. **Correlação SO↔SQL não faz JOIN** para esta instância — são dois servidores para
   o sistema.
2. **`kg_entities` tem as duas** — o grafo AI acredita em duas máquinas onde há uma.
3. **`KPI_MSSQL_INST_ENVS` tem as duas** — contagem de instâncias a dobrar; candidato
   a explicar discrepâncias.
4. O mirror de credenciais do portal não casa pelo id para a metade antiga.

## Perguntas ao owner (reformuladas)

1. **Unificar a história sob o double-S** (o nome canónico em vigor)? UPDATE das
   ~160.156 linhas antigas nas tabelas onde estão sob single-S. Mutação em massa em
   infra partilhada (V3.3 + V6 a ler ao vivo) — exige janela e backup, mas alinha
   tudo com a decisão de 27/07 e é estável mesmo sem restart do servidor.
2. **Ou deixar como está e documentar o corte?** A história pré-27/07 fica sob o nome
   antigo; análise cruzada de longo prazo mente para esta instância. Defensável se a
   instância for de baixa criticidade (é QLT/SharePoint 2010).
3. **Nunca** renomear o canónico para single-S — só faria sentido DEPOIS de o servidor
   ser corrigido (restart, FIND-20260506-101) e, mesmo aí, seria nova decisão com novo
   rename em massa.
4. Há **mais casos** com padrão `instance_id <> host + '_' + instance_name`? Este caso
   é explicado e deliberado, mas a query de varredura continua a valer como higiene.

## Verificação sugerida antes de decidir (read-only)

```sql
-- 1. entradas do canonico com id incoerente com host+instance_name (varredura geral)
SELECT instance_id, host, instance_name, sql_servername_alias
FROM metadata.monitored_server
WHERE is_active = 1
  AND instance_id <> UPPER(host) + '_' + UPPER(instance_name);

-- 2. INST_ENVS a contar a dobrar
SELECT Instance, Env FROM KPI_MSSQL_INST_ENVS
WHERE Instance IN ('SQLHDSSQLT301_I01', 'SQLHDSQLT301_I01');

-- 3. confirmar o @@SERVERNAME actual do servidor (deve ainda ter o double-S)
--    (correr NA instancia, via sql_monitoring)
SELECT @@SERVERNAME;
```

## Correcção a fazer noutro sítio, independentemente da decisão

O handoff `WATCHERDB_V6/docs/context/HANDOFF_V1_INSTANCIAS_FORA_DO_CANONICO_2026-08-21.md`
(commit V6 `3b6d272`) lista `SQLHDSQLT301_I01` como órfão "só no ficheiro legado". **Não é
órfão** — é esta mesma instância com o nome pré-rename. Os órfãos SQL passam de 27 para 26.
