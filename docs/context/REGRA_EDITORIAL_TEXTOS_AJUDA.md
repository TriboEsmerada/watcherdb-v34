# Regra editorial — textos de ajuda do portal

**Estabelecida:** 2026-07-21, após varredura que encontrou racional interno de engenharia
(Waves, ROI, nomes de ficheiros `.md`, detalhes de dedupe) dentro de tooltips visíveis ao DBA cliente.

## O problema que isto previne

Não foi falta de capacidade de escrever bem — foi **erosão**. Cada vez que se tomava uma decisão
(arquivar um filtro, adiar para outra Wave, cruzar com outra tabela), o racional era **anexado ao
tooltip** em vez de ir para `docs/`. O texto cresceu como um log de decisões.

Prova de que o padrão certo é alcançável: o tooltip `backup-jobs-disabled` estava limpo e claro
enquanto os 4 irmãos estavam contaminados — mesma equipa, mesmo ficheiro.

## As 5 regras

### 1. Teste dos 5 segundos
Se o texto não responde a **o que é / porque importa / o que faço** em 3 frases curtas,
não vai para produção como está.

Estrutura-alvo:
```
TITULO CURTO

O que e' (1 frase).

PORQUE IMPORTA: o risco concreto, em linguagem de operacao.

O QUE FAZER: a accao.

(opcional, rodape) Nota tecnica curta - ex. unidade de contagem.
```

### 2. Grep antes do merge
Qualquer alteração a help text corre:
```bash
grep -iE "wave|sprint|commit [0-9a-f]{6}|roi|archived|\.md\)" <texto novo>
```
Se apanhar algo → o racional vai para `docs/architecture/` ou para **comentário de código**
acima do objecto. **Nunca dentro da string exibida.**

> Comentário `//` com "Wave R+11.2" é **correcto**. A mesma frase dentro da string é **erro**.

### 3. Nomes de tabela/coluna nunca no hover
Detalhes de schema (`msdb.dbo.backupset.has_backup_checksums`) pertencem à secção
"Como funciona" (expansível, on-demand), nunca ao tooltip de 1 clique.

`KPI_DOCUMENTATION` já separa isto correctamente (`description` curta vs `howItWorks` detalhado).
`BACKUP_KPI_INFO` não separava nada — foi essa a causa raiz.

### 4. i18n desde o commit zero
Todo objecto de help text novo nasce com `i18n:{en, es}`, seguindo o padrão `tDoc()` do
`KPI_DOCUMENTATION` — o único mecanismo de tradução a funcionar no portal hoje.

**Não** adicionar PT-only "para traduzir depois". Historicamente não volta a acontecer:
`CARD_HELP_TEXTS` tem ~90 entradas e zero traduções.

> ⚠️ E quando o leak *é* traduzido, é pior: o cliente inglês recebeu "Wave T" em inglês.

### 5. Textos >40 palavras precisam de suporte de formatação
Popovers com texto longo têm de suportar quebras de linha explicitamente
(`white-space: pre-line` no mínimo; idealmente HTML estruturado).

> Incidente real: `PERF_HELP` estava **bem escrito**, com secções separadas por `\n\n` —
> mas `.perf-popover` não tinha `white-space`, e o DBA recebia uma parede de texto num
> popover de 320px. Bom conteúdo destruído por 1 linha de CSS em falta.

## Acessibilidade

Verificar `aria-label` e `title` com o mesmo critério. Um leak em `aria-label` faz o utilizador
de leitor de ecrã **ouvir literalmente** "Wave T".

## Estado dos objectos de help text (2026-07-21)

| Objecto | Estrutura | i18n |
|---|---|---|
| `KPI_DOCUMENTATION` | ✅ separa `description` / `howItWorks` | ✅ `i18n:{en,es}` |
| `CARD_HELP_TEXTS` (~90) | ✅ melhor padrão estrutural | ❌ zero |
| `BACKUP_KPI_INFO` (5) | ⚠️ `title=` nativo, sem HTML | ❌ zero |
| `PERF_HELP` | ⚠️ depende de `white-space` no CSS | ❌ zero |

**Dívida conhecida (wave própria):** dar i18n aos ~90 `CARD_HELP_TEXTS` e migrar
`BACKUP_KPI_INFO` de `title=` nativo para popover estruturado.
