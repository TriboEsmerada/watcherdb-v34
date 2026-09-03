---
name: recall
description: Antes de diagnosticar um problema em WatcherDB (V3.3/V1/V6), procura por SINTOMA no indice de solucoes passadas (docs/context/SOLUCOES.md) + CONTEXT.md + findings-inbox.md + postmortems e devolve os ponteiros (commit/ficheiro/doc). Uso "/recall <sintoma ou palavras-chave>". Grep-first para problemas, nao so para scripts.
---

# Recall — "ja vimos isto?"

## Quando dispara

- User invoca `/recall <texto>`.
- PROACTIVO: antes de qualquer diagnostico/investigacao (bug, falso
  positivo, regressao, "porque e' que X mostra 0/zero/vermelho/verde",
  collector parado, drift, erro de ligacao). Custo ~segundos; poupa
  horas de re-investigar o que ja esta documentado (precedentes:
  SS301, "1 OFF", par cego, mirroring view partida — todos ja estavam
  escritos quando foram "redescobertos").

## Fontes (ordem)

1. `docs/context/SOLUCOES.md` — indice por sintoma (1 linha por episodio:
   data | sintoma | causa-raiz | fix | ponteiro | palavras-chave). **Fonte
   primaria.**
2. `docs/context/CONTEXT.md` — Diario (entradas longas, por data).
3. `findings-inbox.md` — FIND-1XX (raiz do repo).
4. `docs/context/postmortems/*.md`, `docs/bugfixes/*.md`, `docs/context/DESIGN_*.md`.
5. Memoria persistente (`memory/*.md`, ja carregada no indice) — licoes de metodo.
6. Se nada: `"c:\...\WATCHERDB INTELLIGENCE V1\CHANGELOG.md"` (entradas fix).

## Procedimento

1. Extrair 3-8 palavras-chave do sintoma: nomes de tabela/view/KPI,
   ficheiro, mensagem de erro, palavra do ecra ("Backup OK", "N/D",
   "Instances OK"), PT **e** EN (ex: "disponibilidade availability",
   "espelhamento mirroring"), sem acentos.
2. Grep (Grep tool, `-i`) em SOLUCOES.md primeiro, depois nas restantes
   fontes. Um hit em SOLUCOES.md chega — seguir o ponteiro.
3. Devolver ao user em <=10 linhas:
   - **Hits** (data · sintoma · causa-raiz · fix · ponteiro), max 5, mais
     recente primeiro;
   - **Veredicto**: "JA RESOLVIDO (aplicar/verificar o fix X)" |
     "PARECIDO (precedente Y, causa pode ser outra — verificar Z na fonte)" |
     "SEM PRECEDENTE (investigar de raiz)".
   - Nunca assumir que o precedente e' a causa actual: verificar na fonte
     (licao 2026-07-28 "codigo morto" — classificacao de outra sessao
     estava errada).
4. Se o problema for NOVO e ficar resolvido na sessao: acrescentar a
   linha em `SOLUCOES.md` (ver "Registo").

## Registo (manter o indice vivo)

Acrescentar 1 linha em `docs/context/SOLUCOES.md` sempre que:
- `/wave-close` (passo 6 da checklist) — por cada bug/armadilha da Wave;
- `/postmortem` (passo 7) — causa-raiz + fix;
- um FIND-1XX passa a resolved;
- uma sessao corrige algo que custou >30 min a diagnosticar.

Formato (1 linha, sem quebras, ';' dentro das celulas):
`| AAAA-MM-DD | sintoma (<=120c) | causa-raiz (<=140c) | fix (<=120c) | ponteiro (SHA/ficheiro:linha/FIND/doc) | palavras-chave minusculas sem acentos PT+EN |`

Regras: 1 linha por episodio (agrupar re-ocorrencias: actualizar a linha
com "recorrente AAAA-MM-DD"); mais recente no topo; nomes de servidores
reais sao permitidos aqui (doc interno, nao-IP — ao contrario dos
postmortems, que sao anonimizados); nunca apagar linhas (historico).

## Limites

- E' um indice de grep, nao uma base de dados. Se passar de ~300 linhas,
  reavaliar SQLite+FTS (decisao owner 2026-08-19: so' nessa altura).
- Nao substitui CONTEXT.md (decisoes) nem findings (tracking aberto);
  aponta para eles.
