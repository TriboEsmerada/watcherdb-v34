# WatcherDB — Valuation, Pricing e Plano de Comercializacao
**Data:** 2026-08-21 | **Autor:** Claude (orquestrador) + watcherdb-marketing-strategist (pricing concorrencia via WebSearch) | **Status:** PROPOSTA — decisoes de preco/comercializacao sao do owner

---

## 1. Evidencia levantada (base dos calculos)

### 1.1 Esforco de desenvolvimento (fonte: git + filesystem)
| Metrica | Valor | Fonte |
|---|---|---|
| Inicio real do projecto | ~Nov/2025 | ficheiro .py mais antigo V1 Intelligence: 2025-11-28 |
| Periodo total | ~9 meses (Nov/2025 → Ago/2026) | |
| Commits (repo familia projetosPython) | 785 em 90 dias activos | git rev-list; 1o commit 2026-01-27 |
| Commits (repo proprio V6) | 833 em 88 dias activos | git V6; 1o commit 2026-04-19 |
| Pico de actividade | Abril/2026: 293 commits/mes | git log por mes |
| Dias uteis efectivos estimados (uniao) | ~110–140 | overlap dos 2 repos |
| Horas estimadas | **700–1.000h** (central ~850h) | 6–8h/dia activo |

### 1.2 Volume de codigo (excl. venvs, mtime real)
| Projecto | Python | SQL | HTML/JS |
|---|---|---|---|
| V1 Intelligence (collectors + infra partilhada) | 63.5k | 78k | — |
| V3.3 Standard | 22.3k | 47.2k | 56k (portal) |
| V5 Pro | 57.4k | 31.2k | ~60k |
| V6 Hybrid | 18k | 33.4k | ~47k |
| Council | 18k | 0.6k | — |
| **Total bruto** | **~180k** | **~190k** | **~150k** |

Deduplicado (V6 = V3.3 + extras; V5 partilha modulos): codebase efectivo **~250–300k linhas**. 76 ficheiros de teste so no V3.3 (129 passed na ultima suite); QA de 6 niveis; PyArmor Pro; security hardening banking-grade (rondas QA 2–5, least-privilege, Fernet/DPAPI, RBAC).

### 1.3 Custos AI (ASSUMPCAO — owner confirmar com facturas reais)
- Assumido: Claude (plano Max) US$100–200/mes × 9 meses ≈ **US$900–1.800**
- Outros: PyArmor Pro (licenca ja detida, reg 11618), Ollama/modelos locais = custo zero de runtime
- Se houve uso API além do plano, ajustar; ordem de grandeza total tooling: **US$1–2k**

---

## 2. Valor base (custo real incorrido)

```
Tempo:  700–1.000h × US$60–100/h (taxa mercado senior DBA SQL Server + Python full-stack)
      = US$42.000 – 100.000
AI/tooling: ~US$1.000 – 2.000
─────────────────────────────────
VALOR BASE ≈ US$45.000 – 100.000  (central ~US$65.000 ≈ €60k ≈ R$360k*)
```
*cambio aproximado 08/2026; confirmar no dia.

Este e o **custo real** — o que foi de facto investido. NAO e o valor do activo.

## 3. Custo de substituicao (replacement cost — ancora de valuation pre-receita)

O que custaria a uma empresa reconstruir o mesmo activo SEM assistencia AI, com equipa tradicional:
- Equipa minima: 3–4 pessoas (backend Python, frontend, DBA/SQL Server senior, AI/ML eng)
- Duracao realista: 12–18 meses para ~250–300k linhas com esta profundidade de dominio (collectors 63 servers, BLUE/GREEN swap, AI pipeline 20 steps, QLoRA, portal 56k linhas, hardening banking)
- Esforco: **5–9 pessoa-anos** × US$120–160k/ano fully-loaded

```
CUSTO DE SUBSTITUICAO ≈ US$600.000 – 1.400.000
```

O multiplicador AI e real: ~850h de founder+AI produziu o que custaria US$600k+ em engenharia tradicional (**leverage ~10–15x**).

## 4. Valor de mercado do activo

**Hoje (pre-1o-cliente):** venda de activo pre-receita transacciona tipicamente a 20–50% do replacement cost, dependendo do comprador (estrategico paga mais):
```
VALOR DE MERCADO HOJE ≈ US$120.000 – 500.000
  - comprador financeiro/oportunista: ponta baixa (US$120–250k)
  - comprador estrategico (vendor de tooling SQL, consultora com carteira banking): US$300–500k
```

**Com 1o cliente banking assinado** (ex.: 20 instancias Pro @ US$2.500 = US$50k ARR): o regime muda — multiplo 3–4x ARR micro-SaaS + premio vertical 25–30% + prova de mercado. O 1o contrato vale mais pela validacao do que pela receita.

**Horizonte 3 anos** (5 clientes × 15–30 instancias mix Std/Pro → ARR US$150–400k): valuation **US$0,6M – 2M+** a multiplos 4–8x de vertical B2B SaaS.

Ressalva do specialist (subscrevo): pre-receita, qualquer numero e especulativo; o replacement cost e a ancora mais defensavel. Nao publicar valuation externamente sem ARR.

---

## 5. Pricing da concorrencia (2025-2026, fontes citadas pelo specialist)

| Concorrente | Modelo | US$/instancia/ano | Fonte |
|---|---|---|---|
| Redgate SQL Monitor | subscricao per-instance | 1.164–1.495 (desc. 15–25% em volume) | ComponentSource, TrustRadius, Vendr |
| SolarWinds DPA | subscricao per-instance | 1.195 (SQL basic) – 4.695 (Oracle RAC ent.) | Vendr, SelectHub |
| SolarWinds SQL Sentry | subscricao per-instance | 1.399 | Connection.com, TrustRadius |
| Idera SQL DM | term license + manut. | 1.996 | G2, ComponentSource |
| Quest Spotlight/Foglight | quote-only, premium | ~2.500–4.500+ (estimativa terceiros) | PeerSpot |
| dbWatch | subscricao flat | ~550–600 (fonte fraca: blog Airbyte) | Airbyte |
| Datadog DBM (ref. cloud) | consumo/host/mes | ~840 so DBM; 1.500–2.500 efectivo | Last9 |

**Modelo dominante:** subscricao anual **per-instance** — padrao de facto do segmento; valida a estrutura Std/Pro do FEATURE_MATRIX.

**Diferenciador verificado:** NENHUM concorrente tem AI on-premise. Redgate Monitor AI envia dados a LLM externo (confirmado na doc oficial v14.3+). "AI soberana via Ollama local" desqualifica Redgate AI/Datadog para cargas reguladas — argumento de compliance (DORA/EBA/PCI-DSS), nao de "AI melhor".

## 6. Precificacao WatcherDB (recomendacao do specialist, subscrevo)

| Tier | US$/instancia/ano | Racional |
|---|---|---|
| **Standard (V3.3)** | **900–1.200** | 20–30% abaixo do Redgate (entrante sem marca); acima de dbWatch (especialista SQL Server custa como especialista) |
| **Pro (AI local)** | **2.200–2.800** | acima de Idera (que nao tem AI); premio = sovereignty/compliance |
| **Pro Enhanced (Council)** | **3.200–4.000** | topo de gama; pitch 100% reducao de risco regulatorio |

Bandas de volume: 10–24 inst. −15% | 25–49 −20% | 50+ −25%.
**Gap a fechar antes de publicar:** definir billing unit (instancia fisica vs named instance vs AG AlwaysOn conta 1 ou N) — target banking tem alta densidade AlwaysOn.

## 7. Formas de comercializacao

1. **Venda directa founder-led** (AGORA): banking/seguros mid-market PT/BR/EU; ciclo de venda 3–9 meses; o founder e o melhor vendedor tecnico do produto nesta fase.
2. **Parcerias com consultoras SQL/MSPs** (apos 1o cliente): revenue share 15–25%; eles tem a carteira, WatcherDB da recorrencia que consultoria nao da.
3. **White-label / OEM para integradores** (mais tarde): margem menor, escala maior; so com produto empacotado e suporte L1 delegavel.
4. **Marketplace (Azure Marketplace)** (futuro): credibilidade + procurement facilitado; exige maturidade de packaging (MSI assinado, SBOM — trabalho da Etapa 3b ja aponta la).

Recomendo 1 → 2; nao dispersar antes do 1o cliente (coerente com project_focus_v1_v33_v6).

## 8. Plano de pagamento

| Item | Estrutura |
|---|---|
| Licenca | Anual antecipada, por instancia (padrao do mercado) |
| Facturacao | Invoice/PO, net-30 a net-60 (banking NAO compra por cartao) |
| Multi-ano | 2–3 anos com price-lock: −10% adicional |
| 1o cliente (logo acquisition) | 30–40% off ano 1 + clausula de case study/referencia (pratica de mercado, nao fraqueza) |
| POC/Piloto | Pago, 60–90 dias (ex.: US$5k flat), 100% creditado se converter em contrato anual |
| Onboarding/instalacao | One-time US$2.500–5.000 (instalacao on-prem, service accounts, least-privilege setup) |
| Suporte premium 24×7 | +20% sobre a licenca (suporte standard business-hours incluido) |
| Moeda | EUR ou USD conforme cliente; BRL com indexacao anual se Brasil |

## 9. Exemplo de deal (cliente banking tipico, 25 instancias)

```
20 × Pro US$2.500      = US$50.000
 5 × Std US$1.000      = US$ 5.000
Subtotal               = US$55.000  → banda 25-49: −20% = US$44.000/ano
Ano 1 logo-deal −35%   ≈ US$28.600 + onboarding US$4.000 ≈ US$32.600
Anos 2-3 (renovacao)   = US$44.000/ano
```

---

## Proximos passos sugeridos
1. Owner confirma custos AI reais (facturas Claude) → afinar valor base.
2. Decidir billing unit (instancia/AG) — pre-requisito para publicar preco.
3. Validar faixa Pro com o 1o prospect (willingness-to-pay real > qualquer benchmark).
4. Fechar gaps de paridade apontados em 2026-07-03 (Query Store, execution plan analysis) antes de defender a ponta alta do Pro.
