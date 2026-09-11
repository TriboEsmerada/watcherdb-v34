# PROPAGAÇÃO V6 — LIVE F9: cinco acertos de UX do painel LIVE (lote 2026-09-11)

> Para a AI do V6. **Verificar primeiro, assumir nunca.** Só se aplica se o V6 tiver o painel LIVE com
> programas por instância (grep `_liveRenderChannelOptions`, `_liveRenderMemory`, `PLANCACHE_SQL`).
> Origem: `docs/context/LIVE_F9_2026-09-11_apply.py` (código integral). Sequência: aplicar primeiro o lote
> `PROMPT_PROPAGACAO_V6_LIVE_CANAIS_2026-09-11.md` (as âncoras deste dependem dele).

| # | Sintoma (medido pelo owner) | Causa no código | Correcção |
|---|---|---|---|
| 1 | Filtrar o Canal com uma instância seleccionada: o select volta ao placeholder, o polling continua nela | o filtro reconstrói as opções só com as que casam; `_liveInstance` fica | a seleccionada aparece sempre, numa optgroup "Selecionada" logo a seguir ao placeholder (`live.selected_group`) |
| 2 | Barra vermelha de dirty pages fora de escala (281 MB a 61% da largura ao lado de 10,6 GB a 100%) | `dirty_mb / b.buffer_mb` (escala do próprio banco) vs barra azul em `maxBuf` | `dirty_mb / maxBuf` |
| 3 | Plan Cache com coluna DB vazia na maioria das linhas | `DB_NAME(qt.dbid)` de `dm_exec_sql_text` é NULL em ad hoc/preparados (medido: 20/20 e 13/20 nulos) | `COALESCE(DB_NAME(qt.dbid), DB_NAME(CAST(pa.value AS INT)))` com `OUTER APPLY (SELECT TOP 1 value FROM sys.dm_exec_plan_attributes(qs.plan_handle) WHERE attribute = 'dbid') pa` (+75 ms); front mostra `(ad hoc)` quando continua nulo |
| 4 | UI em EN com "PAUSADO", "1 queries em execucao", "41 conexoes", tooltips "Reduzir/Tamanho normal/Tela inteira" | literais crus no bloco LIVE (19, incluindo "A conectar a", "Programa nao implementado", "A colectar dados da fleet", "Buffer Pool por Database", "Plan cache vazio", "Error log vazio", "Play/Pause" e os tooltips das gauges CPU/Mem/PLE/Batch/Qry, meio-migrados) | chaves `live.*` novas (23) em pt-PT acentuado, en, es; pt-BR herda; placeholders por `_kpiTp`; tooltips por `t()` inline no template (o botão pop-out vizinho já usa esse padrão, não misturar com `data-i18n-title`) |
| 5 | Reabrir o LIVE perde programa e intervalo | só `live-last-channel` em localStorage; o init forçava `fleet` | `live-last-program` e `live-last-rate` gravados em `liveSetProgram`/`liveChangeRate` e restaurados no init (programa validado contra os botões existentes; intervalo contra 5/10/15/30 s); `_liveProgram` é reposto **sincronamente antes** do fetch dos canais para não haver flash do programa anterior |

Testes a portar: `tests/unit/test_live_f9_20260911.py` (7, estáticos). Ordem de arranque com programa
guardado por instância: `liveSetProgram(saved)` sem instância cai no estado neutro; quando `_liveLoadChannels`
repõe a instância guardada, `liveChangeChannel` inicia o polling nesse programa — não há caminho que reponha
`queries` à força.
