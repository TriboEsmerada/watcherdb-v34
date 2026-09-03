# PROMPT PROPAGACAO V6 — portar o registo de limiares (`kpi_thresholds_registry.py`)

Data: 2026-08-31 | Origem: alinhamento de KPIs V6↔V3.3 (sessão V6)
Regra que enquadra tudo: **owner 31/08 — nos KPIs o V3.3 é o oficial e o V6 segue-o à risca.**
Divergência = o V6 está errado.

## Porque agora, e não depois

Hoje corrigiram-se três KPIs do V6 que divergiam do oficial (commits V6 `a5cebde`,
`ad1091e`): TempDB media contenção onde o oficial mede ocupação; t-log e disco contavam
itens num campo cujo cartão diz instâncias. Nenhum dava erro — davam números plausíveis e
errados, que é a única espécie que sobrevive meses num painel.

Os três estão alinhados **por acordo entre dois ficheiros**, não por construção. O V6 não
tem registo de limiares:

```
  V3.3   api/kpi_thresholds_registry.py    1 registo, 11 pares nomeados
  V6     nenhum; 37 limiares escritos a mao so no intelligence_kpis.py,
         com o bloco de backup delay DUPLICADO em :1863 e :3668
```

Confrontados hoje: os 3 de backup delay batem (120/168, 24/30, 1/2) e mais 2 são
consistentes (disk_latency 20/50, long_locks 600). **Zero divergências encontradas.**
Os restantes ~6 estão em comparações soltas sem nome e exigem leitura caso a caso.

É por isso que é agora: **enquanto os valores concordam, o porte é mecânico.** Repontar
código para ler de um sítio onde já lê os mesmos números. No dia em que alguém afinar o
registo do V3.3, deixa de ser porte e passa a reconciliação, com um painel a discordar do
outro no meio e ninguém a saber qual está certo.

## O que fazer

1. **Copiar `api/kpi_thresholds_registry.py` do V3.3 para o V6, tal e qual.** Não adaptar
   valores. Se algum não se aplicar ao V6, deixar lá e não usar — divergir os ficheiros
   destrói o propósito.
2. **Repontar os 37 sítios** do `api/routers/intelligence_kpis.py`. Começar pelos que já
   têm nome óbvio (backup delay ×2, tempdb, tlog, disk latency, deadlocks, long locks,
   filegroups, processes runnable); os soltos (`> 90`, `>= 80`) exigem identificar a que
   KPI pertencem antes de mapear — **não adivinhar pelo valor**.
3. **Eliminar a duplicação** do bloco de backup delay (`:1863` e `:3668`): passa a haver
   uma leitura do registo, não duas cópias.
4. Os limiares que hoje estão como literais com comentário a apontar ao registo (TempDB,
   em `api/routers/intelligence_kpis.py`, `TEMPDB_WARNING_PCT`/`TEMPDB_CRITICAL_PCT`)
   passam a ler de lá — o comentário já diz que é isso que falta.

## O teste que fecha o ciclo (escrever, é barato e é o que impede a reincidência)

Comparar os dois registos e falhar se divergirem:

```python
# tests/unit/test_thresholds_match_v33.py
# Le o registo do V3.3 e o do V6 e exige igualdade par a par.
# Sem isto, afinar o V3.3 e esquecer o V6 volta a ser silencioso.
```

Se o caminho do V3.3 não estiver disponível no ambiente de teste do V6, alternativa: um
hash/snapshot do registo commitado no V6, e o teste falha quando o do V3.3 muda — obriga a
uma actualização deliberada em vez de deriva.

## Validação

Para cada KPI repontado, o número no painel V6 tem de ficar **igual ao de antes do porte**
(os valores já batem). Qualquer mudança de número significa que o mapeamento está errado —
é o sinal de que se apontou um limiar ao KPI errado.

## Referência: o que já foi confrontado e bate

| limiar oficial | valor | estado no V6 |
|---|---|---|
| `backup_delay_full` | 120 / 168 | igual, hardcoded ×2 |
| `backup_delay_diff` | 24 / 30 | igual, hardcoded ×2 |
| `backup_delay_log` | 1 / 2 | igual, hardcoded ×2 |
| `disk_latency` | 20 / 50 | consistente (`>= 20`, `>= 50`) |
| `long_locks` | 60 / 600 | 600 consistente; 60 não localizado |
| `tempdb_usage` | 60 / 80 | aplicado hoje como literal, a repontar |
| `tlog_usage` | 85 / 95 | **não localizado** |
| `deadlocks_state` | 10 / 20 | **não localizado** |
| `processes_runnable` | 20 / 50 | **não localizado** |
| `filegroup_free_pct` | 5 / 2 | **não localizado** |
| `filegroup_unlimited_free_gb` | 10 / 5 | **não localizado** |

Os "não localizado" são o trabalho real deste lote: descobrir onde o V6 os aplica (ou se
não os aplica de todo, que é a hipótese que mais me preocupa).
