# Propagação V6 — lote 2026-08-12 (packaging + portal header)

Origem: sessão V3.3 de 10-12/08 (teste de instalação real em SQLHDSPRD213 →
bug P0 no bundle → revisão de header/toolbar). Este documento é o **handoff
explicado**: leva as regras e o porquê, não só o diff. A AI do V6 deve poder
decidir sozinha o que aplicar, o que adaptar e o que recusar.

Estado do V6 verificado por grep a 2026-08-12 (não assumido).

---

## 0. Contrato de leitura para a AI do V6

1. **O V6 não é superset do V3.3.** O portal V6 é um subset mais simples.
   Cada item abaixo diz explicitamente o que existe e o que NÃO existe no V6,
   verificado por grep. Se um âncora não aparecer, o item não se aplica —
   não inventes o equivalente.
2. **Âncoras são strings de pesquisa, nunca números de linha.** Os ficheiros
   divergiram; números de linha do V3.3 não servem no V6.
3. **Ordem importa** nos itens 1 e 2 (packaging antes de código).
4. Nada aqui toca em BD, schema ou features Pro. É tudo runtime + chrome.

---

## 1. Tectos de dependências (P1 preventivo) — APLICA-SE

### O que aconteceu no V3.3

O `requirements.txt` tinha `fastapi>=0.114.0` **sem tecto**. Ao recriar a venv
de build, o pip resolveu para fastapi 0.136.1, que arrastou **starlette 1.0.0**.

O detalhe que ninguém viu vir: o fastapi 0.128 declarava
`Requires-Dist: starlette<0.51.0` — protegia-nos sozinho. O fastapi 0.136
**removeu esse tecto** (`starlette>=0.46.0`, sem limite superior). Ou seja,
a protecção que tínhamos era acidental e desapareceu numa versão menor do
fastapi. Resultado: o bundle empacotado ficou com uma major nova de starlette
que ninguém pediu, e o portal inteiro passou a devolver 500 em produção.

### Estado do V6 (verificado)

`WATCHERDB_V6/requirements.txt`:
```
fastapi>=0.104.0      <- piso AINDA MAIS BAIXO que o V3.3 tinha, sem tecto
uvicorn[standard]>=0.24.0
pydantic>=2.4.0
```
`starlette` **não está declarado** — é transitivo via fastapi, exactamente a
dependência acidental que nos mordeu.

### Regra a adoptar

> Qualquer pacote cujo namespace seja importado directamente pelo código tem
> de ser **linha directa** no requirements, com tecto de major. Não confiar
> em tecto transitivo de terceiros — ele pode desaparecer sem aviso.

### Diff proposto (adaptar versões ao que o V6 já corre)

```
fastapi>=0.114.0,<0.130.0
starlette>=0.40.0,<0.51.0
uvicorn[standard]>=0.24.0,<0.41.0
pydantic>=2.4.0,<3.0.0
python-multipart>=0.0.7,<0.1.0
```

**Atenção V6:** o piso do fastapi sobe de 0.104 para 0.114. Confirmar que
nada no V6 depende de comportamento anterior a 0.114 antes de aplicar.
Se o V6 tiver venv antiga a funcionar, correr `pip list` primeiro e ajustar
os pisos ao que já lá está, mantendo os tectos.

---

## 2. TemplateResponse old-style (P2 latente) — APLICA-SE PARCIALMENTE

### A avaria

Starlette 1.0 **removeu** o shim que aceitava `TemplateResponse(nome, contexto)`.
Com a assinatura nova, os argumentos entram desalinhados: `request` recebe a
string do template e `name` recebe o dicionário de contexto. O Jinja tenta usar
esse dicionário como chave de cache → `TypeError: unhashable type: 'dict'` → 500.

### Estado do V6 (verificado)

| Superfície | V3.3 | V6 |
|---|---|---|
| Portal principal | `TemplateResponse` (3 rotas) — **partia** | **`FileResponse`** — imune |
| Parciais htmx | `TemplateResponse` ×3 | **`TemplateResponse` ×3** — vulnerável |

Âncoras no V6 (`api/routers/htmx.py`): as três chamadas
`templates.TemplateResponse(` cujo primeiro argumento é uma string de template
(`"partials/_server_list_items.html"`, a variável `template`, e
`"partials/_server_header.html"`).

**Severidade menor que no V3.3**: o portal principal do V6 usa `FileResponse`,
portanto não parte. Só as rotas htmx partem, e só se starlette >= 1.0.

### Fix (compatível com starlette 0.50 E 1.0)

```python
# ANTES
return templates.TemplateResponse(
    "partials/_server_header.html",
    {"request": request, "server_id": server_id},
)
# DEPOIS — request passa a 1o argumento; sai do dict (o starlette injecta-o)
return templates.TemplateResponse(
    request,
    "partials/_server_header.html",
    {"server_id": server_id},
)
```

Aplicar mesmo que o V6 corra hoje com starlette 0.50: a assinatura nova
funciona nas duas versões e elimina a bomba-relógio.

---

## 3. Header / toolbar — acessibilidade e ícones (P1) — APLICA-SE COM ADAPTAÇÃO

### O que se descobriu

O owner disse "alguns ícones não estão bons". A revisão mostrou que os ícones
eram o **terceiro** problema. Os dois primeiros:

**(a) Contraste.** Os 6 botões da nav usam texto branco 14px/600 sobre
gradientes de nível 500 — 14px peso 600 **não** é "large text" (o limiar é
18.66px bold), logo o mínimo WCAG AA é 4.5:1. Medições: Ping 2.56:1,
Mutes 2.15:1, KPIs 3.67:1 na ponta clara. **Todos falham.**

**(b) O caso grave.** O botão Collectors usa
`linear-gradient(..., var(--color-text-disabled) 0%, var(--color-border) 100%)`.
No tema **Claro** isso resolve para cinzento claro com texto branco por cima:
**1,49:1 — ilegível.** A intenção era despromover visualmente o botão, mas
fez-se baixando o contraste do preenchimento em vez de mudar o estilo.

**(c) Alto Contraste.** A folha de estilo do tema HC aplica
`background-image: none !important`. Um `linear-gradient` **é** um
`background-image`. Logo, em HC os 6 botões perdem o fundo e, como têm
`border: none` inline, ficam texto solto sem qualquer limite visível —
falha 1.4.11 (non-text contrast) e destrói a affordance de botão.

### Estado do V6 (verificado por grep)

| Elemento | V6 |
|---|---|
| `background-image: none !important` no tema HC | **SIM** (existe) |
| `var(--color-text-disabled) 0%` no Collectors | **SIM** (1 ocorrência) |
| Ícones `fa-heartbeat`, `fa-shield-alt`, `fa-chart-line`, `fa-network-wired`, `fa-bell-slash` | **SIM** (todos) |
| Segmented de tema `data-kpi-theme-btn` | **NÃO EXISTE** |

Conclusão: **(a), (b) e (c) aplicam-se todos ao V6.** O item do `aria-pressed`
e a chave i18n do tema **não se aplicam** (o V6 não tem esse controlo).

### Solução aplicada no V3.3 — 3 níveis de ênfase

Ordem, posição, labels e ícones-de-função **intactos** (o reconhecimento numa
nav vive de posição + label, não de saturação). Muda só o peso do preenchimento:

- **Nível 1 — LIVE**: único sólido. `background: var(--color-danger)` +
  `border: 1px solid var(--color-danger)`. É o botão de emergência; merece ser
  o único saturado.
- **Nível 2 — Ping, KPIs**: fill tonal + **texto na cor do accent** (não branco).
  Ex.: `background: rgba(59,130,246,0.16); border: 1px solid rgba(59,130,246,0.45);
  color: var(--color-text-link)`. Passa AA folgadamente.
- **Nível 3 — admin-gated (Collectors, Mutes, Control)**: outline.
  `background: transparent; border: 1px solid var(--color-border);
  color: var(--color-text-secondary)`. **Sobrevive ao Alto Contraste**, porque
  `border-color` não é `background-image`.

Acrescentar `white-space: nowrap` a todos (senão "Collectors" parte a linha
quando os labels crescem em EN/ES).

### Ícones — só 2 trocas, e por COLISÃO, não por gosto

| Botão | Antes | Depois | Porquê |
|---|---|---|---|
| Control | `fa-shield-alt` | `fa-users-gear` | O escudo é o glifo de **segurança** em 20+ sítios do portal (TDE, Resource Governor, página Security, relatórios). Quem clica espera segurança e recebe gestão de utilizadores. |
| Collectors | `fa-heartbeat` | `fa-tower-broadcast` | O coração é o glifo de **saúde** (CPU, AlwaysOn sync, tiles de status). No topo lia-se "saúde dos servidores" — que é o que os KPIs fazem. Torre = agentes que transmitem telemetria. |

**Trocar nos 3 sítios** onde o Collectors aparece (botão da nav, cabeçalho do
modal, linhas de tarefa) — senão o ícone do topo deixa de casar com o modal
que ele abre.

**NÃO trocar** (decisão explícita, para evitar churn): `fa-network-wired` (Ping),
`fa-chart-line` (KPIs), `fa-bell-slash` (Mutes), `fa-globe`, `fa-cog`.

**Verificar antes:** os glifos `fa-tower-broadcast` e `fa-users-gear` existem
no Font Awesome empacotado no V6? No V3.3 confirmei em
`static/vendor/fontawesome/css/all.min.css` (FA 6.4.0). Se o V6 tiver FA mais
antigo, `fa-tower-broadcast` (FA6) pode não existir — nesse caso o fallback é
`fa-satellite-dish` (FA5), ou actualizar o vendor.

---

## 4. Pipeline de build — NÃO APLICÁVEL HOJE, mas herda o padrão

O V6 **não tem pipeline de packaging** (sem `deploy/*.ps1`, sem PyInstaller).
Corre a partir da fonte. Portanto nada a propagar agora.

Quando o V6 ganhar empacotamento, herda estas quatro regras, todas nascidas
de incidentes reais no V3.3:

1. **Smoke-boot obrigatório pós-assinatura.** Não basta validar que o
   executável foi criado — é preciso **arrancá-lo** e bater num endpoint. Os 4
   incidentes históricos de packaging (pyodbc, structlog, email.mime, passlib)
   foram todos falhas de arranque descobertas à mão depois de builds "verdes".
2. **O smoke tem de cobrir uma rota que renderize template.** `/healthz` e
   `/docs` não passam por Jinja — foi por isso que o 500 do portal escapou a um
   smoke que existia e passava.
3. **Gate de testes no interpretador do runtime.** O V3.3 corria os testes em
   Python 3.14 e congelava 3.11 no bundle — a evidência não cobria o que o
   cliente executa.
4. **Lockfile na venv de build.** Tectos sozinhos não dão reprodutibilidade
   (dentro do range o pip ainda escolhe patches diferentes). O V3.3 gerou
   `requirements-build.lock` com `pip-compile --generate-hashes`.

---

## 5. Não aplicável ao V6

| Item | Porquê |
|---|---|
| Registo em Adicionar/Remover Programas | V6 não tem instalador |
| `MsiHiddenProperties` / MSI | V6 não tem MSI |
| `aria-pressed` no segmented de tema | Controlo não existe no V6 |
| Chave i18n `kpi_report.theme_hc` | Idem |
| Colisão ZIP↔MSI (nome de serviço) | V6 não tem serviço instalado por veículo |

---

## 6. Ordem de execução recomendada

| # | Item | Risco | Nota |
|---|---|---|---|
| 1 | Tectos de deps + starlette directo | Baixo | Fazer primeiro: protege tudo o resto |
| 2 | TemplateResponse ×3 em `htmx.py` | Baixo | Compatível com ambas as versões |
| 3 | Collectors legível (tema Claro) | Baixo | É bug, não design |
| 4 | 3 níveis de ênfase na nav | Médio | Mudança visual — validar no browser nos 3 temas |
| 5 | 2 trocas de ícone | Baixo | Confirmar glifos no FA do V6 primeiro |

## 7. Validação obrigatória

Browser test antes de declarar fechado (regra da casa — houve um incidente em
que handlers inline pareciam correctos na fonte e estavam partidos em runtime):

- Abrir o portal nos **3 temas** (Claro, Escuro, Alto Contraste) e confirmar
  que os 6 botões continuam legíveis e reconhecíveis como botões em todos.
- Confirmar que o Collectors se lê no tema **Claro** (era o caso de 1,49:1).
- Clicar os 6 botões — as acções têm de continuar a funcionar.
- Se o item 2 for aplicado, exercitar uma rota htmx e confirmar 200.

---

## Referência V3.3

- Commit do fix de packaging/portal: `88f0a0d`
- Commits do pipeline: `14f886e`, `d0f82b6`, `1fdf293`
- Diário: `docs/context/CONTEXT.md`, entradas de 2026-08-10 e 2026-08-11
