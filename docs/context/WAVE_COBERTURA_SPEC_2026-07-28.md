# WAVE COBERTURA — o silêncio não pode significar duas coisas

> Spec. Origem: observação do owner sobre a aba Jobs (2026-07-28/29) — *"ela diz
> tudo o que não tem, mas ficamos sem saber o que tem"*. A investigação mostrou
> que não é uma aba: é uma postura do produto.

## 1. O problema

O produto é um **relator de excepções**. Diz o que está partido e nunca declara a
linha de base. Consequência: o silêncio conflaciona dois estados muito diferentes —
**"está tudo bem"** e **"não consegui medir"**.

Quatro instâncias observadas no mesmo dia, por caminhos independentes:

| Onde | Sintoma |
|---|---|
| KPI Backups | "sem checksum" com 1153 a dominar o cartão — e uma falha real (`is_damaged`) escondida lá dentro |
| Card Resumo Consolidado | prometia síntese, entregava um filtro de excepções (removido) |
| Relatório de Backup | gaps, jobs falhados, findings — nenhuma vista de cobertura |
| Aba Jobs | diz o que falta, nunca o que existe |

## 2. O critério de diagnóstico: **denominador**, não vocabulário

Primeira tentativa: contar palavras de "problema" vs "estado" por módulo i18n.
**Falhou** — 2 falsos positivos em 3 nas primeiras posições:

- `users` (rácio 10,0) → **bom**. `total_users`, `active`, `inactive` são categorias
  de *inventário*, não excepções. E tem estados vazios explícitos
  (*"Nenhum usuário órfão detectado"*).
- `security` (rácio 3,5) → **o melhor módulo do produto** (ver §3).
- `overview` (rácio 5,5) → caso real, parcial.

O rácio serve para **ordenar candidatos**, não para decidir. O critério que decide é:

> **Existe fracção?** "X de N" implica que se sabe o universo.
> Uma contagem nua — "3 com problema" — não distingue *3 de 100 medidos* de
> *3 de 3 medidos, 97 por medir*.

## 3. A referência já existe dentro do produto

**Módulo Security.** Vocabulário: `score`, `passed`, `failed`, `warnings`,
`verifications`, `config_healthy`, `expected` vs `current_value`. É um modelo de
verificações: **N checks, X passaram, Y falharam**, com valor esperado e actual.

> **Ressalva do passo 0 (2026-07-29).** A referência é o *vocabulário*, não os
> cartões. Os cartões de topo do Security mostram **contagens nuas** — `Passed 1`,
> `Failed 1`, `Warnings 5` (`portal:19047-19071`). O denominador existe no código
> (`checks.length`) e só é **inferível** pelo Score (12,5% ⇒ 1 de 8); nunca é
> mostrado. A referência precisa da própria correcção antes de ser espalhada.

**Módulo Services** — *descoberto no passo 0, é a referência mais completa.*
`portal:31696-31718` mostra `${runningServices.length}/${services.length}` — fracção
explícita no cartão principal. E, decisivo, `portal:31672-31689` implementa o balde
que falta em todo o lado: quando a recolha falha, os cartões mostram `N/A`, `-/-`,
`-` com mensagem própria e causas prováveis, em vez de zeros que se leriam como
"está tudo bem". **É o único sítio do produto onde "não consigo medir" já tem
tratamento visual próprio nos cartões de topo.** Modelo preferencial para a wave.

**KPI Integridade.** A distinção `MEASURABLE` / `NOT_MEASURABLE` provou que ~80% do
"nunca validado" era falha de coleta e não negligência — mudou a conclusão de
negócio, não só o ecrã.

A wave **não inventa um padrão**: espalha um que já está validado internamente.
Esse é o argumento mais forte a favor, e reduz o risco de execução.

## 4. Passo 0 — auditoria (a fazer PRIMEIRO)

Estado real da cobertura desta análise, para não se assumir mais do que se sabe:

| Aba | Auditada? | Veredicto |
|---|---|---|
| Security | ✔ | **referência** — tem denominador |
| Users | ✔ | bom — inventário + estados vazios explícitos |
| Overview | ✔ | **parcial** — bons estados vazios, mas cartões de topo sem denominador |
| Jobs | ✔ | **sem denominador** na análise de manutenção |
| Backup | ✔ | **sem denominador** ("8 falhou" de quantas?) |
| Space, Disk, Memory, CPU, AlwaysOn | ✘ | rastreados por vocabulário, **não verificados** — lote 2 |
| Log | ~ | visto de passagem: contagens nuas (`totalEvents`, `totalErrors`) + cartão "Período". **Candidato a infractor**, confirmar no lote 2 |

### 4.1 Resultado do lote 1 — as 5 "nunca olhadas" (2026-07-29)

| Aba | Cartões de topo | Denominador | Veredicto |
|---|---|---|---|
| **Services** | status, running, stopped, critical_down | **SIM** — `N/M` | **bom** — e tem estado "não consigo medir" (ver §3) |
| **Sessions** | 7 chips clicáveis (`portal:9096-9114`) | **SIM** — cartão `total` ao lado dos subconjuntos | **bom** — padrão de inventário, como Users |
| **Encrypted** | donut, sem `stat-card` (`portal:19181-19190`) | **SIM** — `encPct`/`unencPct` sobre `totalDbs` | **bom** |
| **SQL Diag** | nenhum | n/a | fora de escopo — é catálogo de queries, não relatório de estado |
| **Performance** | usa `metric-card`, não `stat-card`; entra por `loadPerformanceModuleForTab` (`portal:6501`), fora do padrão das outras dez | por verificar | **divergência estrutural** |

> **A hipótese de partida não se confirmou.** As três abas nunca olhadas que têm
> cartões de topo **já têm denominador**. O não-examinado não era o infractor mais
> provável — mais uma razão para o rácio de vocabulário não decidir nada (§2).

### 4.2 Quatro sistemas de cartões, não um

O passo 0 explica porque a extracção por regex falhou: o portal tem **quatro**
famílias de cartão de topo, com markup sem nada em comum.

| Sistema | Estrutura | Abas |
|---|---|---|
| `stat-card` em `stats-grid` | `.label` + `.value` + **`.sub-value`** (`portal:16313`) | Security, Services, Sessions, Space, Log |
| `metric-card` | `title` + `value` + **`subtitle`** (`portal:16624-16632`) | Overview, Memory, CPU |
| `perf-module` / `renderPerfSections` | orientado a `data.cards` da API (`portal:51752`) | Performance |
| `.card` simples com gradiente inline | markup ad-hoc por cartão (`portal:29181-29205`) | AlwaysOn |

**Alavanca de implementação:** os dois sistemas principais **já têm slot para o
denominador** — `.sub-value` no `stat-card` (já usado no Space) e `subtitle` no
`metric-card` (já usado no Memory, com `X / Y GB`). O "X de N" cabe lá **sem UI
nova**, o que satisfaz directamente a regra do §7.

### 4.3 Resultado do lote 2 e quadro final (2026-07-29)

| Aba | Denominador | Veredicto |
|---|---|---|
| Services | `N/M` + estado "não consigo medir" | **bom** — referência |
| Sessions | cartão `total` | bom |
| Encrypted | donut sobre `totalDbs` | bom |
| Space | cartão `Total Databases` | bom |
| Memory | subtítulo `X / Y GB` | bom |
| CPU | valor em %, subtítulo `Cores: N` | bom |
| AlwaysOn | `Réplicas: ${replicas.length}`, `Bases` — inventário | bom |
| Security | score implica; cartões mostram contagem nua | **parcial** |
| Disk | gráficos por drive com %; "Alertas Inteligentes" sem universo | **parcial** |
| **Log** | nenhum (`totalEvents`, `totalErrors`, `Período`) | **infractor** |
| SQL Diag | n/a | fora de escopo — catálogo de queries |

Nota estrutural: só o **Performance** foge ao padrão `loadXForTab` → `renderX`
(é `window.loadPerformanceModuleForTab`, definido no fim do ficheiro,
`portal:51694`). O Disk segue o padrão — `loadDiskAnalysisForTab:9289` →
`renderDiskAnalysis:10157`.

### 4.4 Inversão de eixo que o passo 0 obriga

**Sete das onze abas já têm denominador.** O trabalho de cobertura por cartão é
pequeno: Log, e os cartões do Security e do Disk. A hipótese de partida —
"o produto é um relator de excepções em todo o lado" — não sobrevive à auditoria.

O problema real está **a montante**: falhas engolidas em silêncio que produzem
verdes falsos em abas cuja lógica de apresentação está correcta. Três instâncias
de produção documentadas no mesmo dia (2026-07-29):

1. **Dashboard** — 100% de disponibilidade sobre 44 de 107 instâncias, sem sinal
   de recolha incompleta ([[FIND-20260729-101]]).
2. **Collector** — filtro anti-falso-positivo abre quando os dados de que depende
   estão velhos, e produz falsos `SQL_DOWN` ([[FIND-20260729-102]]).
3. **Disk** — três sub-fetches com o comentário literal `pode falhar
   silenciosamente` (`portal:9332-9362`); se o de I/O falha, `ioCriticals`
   calcula 0 sobre lista vazia e lê-se como "sem problemas de I/O"
   ([[FIND-20260729-105]]).

> **Eixo principal da wave passa a ser: falha engolida nunca pode render como
> estado saudável.** A cobertura por cartão ("X de N") passa a eixo secundário —
> continua a valer, mas resolve o caso menor.

**Método do passo 0:** ler o renderizador de cada aba e responder a uma pergunta só —
*os cartões de topo mostram uma fracção, ou uma contagem nua?* Não automatizar: a
tentativa de extrair cartões por regex falhou (markup demasiado heterogéneo entre
abas), e uma classificação frágil é pior que nenhuma.

## 5. Passos seguintes (por ordem de valor)

1. **Backups — secção de cobertura no relatório.** Protegida / desprotegida /
   **não consigo medir**. O último balde é o que falta hoje: as bases com backup
   externo (TSM, Commvault) não têm job no Agent e a cadência é *inferida do
   histórico*. O produto já classifica a fonte em três categorias
   (`_source_label`: sysjobs / R+8 history / inferido) — e despeja-as em
   `logger.info`. **Requer campo novo no `DatabaseBackupPatternAnalysis`** para o
   valor sair para a API; não é trabalho só de frontend.
2. **Jobs — inventário.** O que existe, o que corre, quando, e o que correu bem.
   Falhas e colisões passam a **sobreposição**, não a vista única. O produto já tem
   o mapa completo de agendamentos — é o que lhe permite detectar colisões; mostra
   só os choques.
3. **Overview — denominador nos cartões de topo.** "DBs com Problema" ganha universo.

## 6. Regra transversal (a que fica depois da wave)

> Nenhum ecrã pode deixar o silêncio significar duas coisas.
> Onde houver contagem de excepções, tem de haver universo.
> Onde não se conseguiu medir, tem de se dizer — como o KPI de Integridade já faz.

## 7. O que NÃO fazer

- **Não criar superfícies novas.** O card Resumo Consolidado foi removido em vez de
  ganhar um modal, precisamente para não haver aba + relatório + modal a divergir.
  A cobertura entra **onde a informação já vive**.
- **Não remendar aba a aba** sem o passo 0: sem a auditoria, corre-se o risco de
  gastar esforço em módulos que já estão bem (como o Users e o Security estavam).
