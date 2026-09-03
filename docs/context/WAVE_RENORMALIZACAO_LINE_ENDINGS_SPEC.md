# Spec — Wave de renormalização de fim-de-linha no monorepo

> **Estado:** especificada, **não executada**. Aberta em 2026-07-29 durante a Wave B.
> **Âmbito:** repositório `projetosPython` (parent). O `WATCHERDB_V6` tem git próprio —
> verificar separadamente se sofre do mesmo.

---

## Problema

Medido em 2026-07-29:

```
Ficheiros marcados como modificados:      618
Com alteracoes de conteudo reais:           2
core.autocrlf:                           true
.gitattributes na raiz:            nao existe
```

**616 ficheiros (99,7%) são ruído puro de fim-de-linha.** Os blobs no repositório têm
CRLF, os ficheiros em disco têm LF, e sem `.gitattributes` o git marca a diferença de
bytes como alteração real.

## Porque é que isto não é cosmético

Custou dois commits mal rotulados no mesmo dia:

| Commit | Mensagem | Conteúdo real |
|---|---|---|
| `2a70b1d` | *feat(wave-b): indexacao dirigida por DMV* | notas de porta TCP da Wave A |
| `f6af8d5` | *fix(v1): guarda anti-crash* | o fix **+** os dois CHANGELOG da Wave B **+** um prompt V6 da Wave A **+** uma spec nova |

Mecanismo: qualquer `git add <directório>` ou `git add -A` varre 616 ficheiros fantasma
mais o que estiver pendente de outras sessões. O `git status` fica ilegível — 618 linhas
onde deviam estar 2 — portanto a revisão pré-commit deixa de ser praticável e o erro
passa despercebido.

Efeito secundário: `git status` deixa de servir para o requisito de verificação
cruzada entre repositórios, porque ninguém lê 618 linhas antes de cada commit.

## Mitigação em vigor (funciona, mas é disciplina)

`git add` por **ficheiro explícito**, nunca por directório, seguido de
`git diff --cached --stat` para confirmar a contagem antes de commitar. Provado no
commit `1cc6d1d` (Wave B): 5 ficheiros pedidos, 5 ficheiros commitados.

## Correcção definitiva

**Pré-requisitos — nenhum destes é opcional:**

1. Árvore de trabalho **limpa** dos 2 ficheiros com alterações reais (commitados ou
   descartados). Verificar com:
   ```bash
   git diff --numstat -w --ignore-blank-lines 2>/dev/null | awk '$1!=0 || $2!=0'
   ```
   Tem de devolver vazio.
2. **Nenhuma sessão paralela** a escrever no repositório. A renormalização toca 616
   ficheiros; um `add` concorrente durante a operação é irrecuperável sem esforço.
3. Branch dedicada e **tag de âncora** antes de começar.

**Execução:**

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython"
git checkout -b wave-renormalizacao-line-endings
git tag pre-renormalizacao-20260729

# .gitattributes na raiz -- decide o fim-de-linha por tipo, deixa de depender de config local
#   * text=auto
#   *.ps1 text eol=crlf
#   *.bat text eol=crlf
#   *.cmd text eol=crlf
#   *.sh  text eol=lf
#   *.png binary
#   *.jpg binary
#   *.pdf binary

git add .gitattributes
git commit -m 'chore: gitattributes para fixar fim-de-linha por tipo de ficheiro'

git add --renormalize .
git status --porcelain | Measure-Object -Line   # esperado: ~616
git commit -m 'chore: renormalizacao de fim-de-linha, sem alteracao de conteudo'
```

**Validação obrigatória depois:**

```powershell
git diff pre-renormalizacao-20260729 --stat -w --ignore-blank-lines
```
Tem de vir **vazio**. Se aparecer qualquer ficheiro, houve alteração de conteúdo a
disfarçar-se de whitespace — parar e investigar antes de fazer merge.

E depois, o teste que interessa: `git status --porcelain` deve devolver **zero** linhas
numa árvore limpa. É esse o objectivo, não o commit.

## Itens adjacentes apanhados no mesmo diagnóstico

- **`WATCHERDB INTELLIGENCE V1/services/collector_service/service_health.txt`** —
  ficheiro de saúde escrito em runtime pelo serviço, versionado. Gera diff a cada
  execução do collector. Candidato a `.gitignore` (e `git rm --cached`).
- **Directórios não seguidos na raiz** — `WATCHERDB_V6/` (git próprio, esperado),
  mas também `WATCHERDB_V3.3 - Copy/`, `_archive/`, `Cockpit/`, `JADE/`, `Nestor/`,
  `Python.Cokpit/`, `SSIS_Package_BI/`, `llama.cpp/`, `nestor-template/`,
  `polo-visual-service/`. Decidir por cada um: ignorar, seguir, ou remover.
  `WATCHERDB_V3.3 - Copy/` merece atenção — uma cópia da árvore de produção ao lado
  da original é uma fonte provável de edições no sítio errado.

## Porque não foi feito na Wave B

Fora do âmbito (a Wave B era indexação da BD partilhada) e o pré-requisito 2 não estava
satisfeito — havia trabalho paralelo a entrar no repositório durante a própria sessão,
que foi precisamente o que produziu os dois commits mal rotulados.
