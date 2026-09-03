# WatcherDB V3.3 Standard Edition — Pricing Model

## Modelo de Pricing: Por Servidor Monitorizado (anual)

### Tiers

| Tier | Servidores | Preco/servidor/ano | Preco total/ano |
|------|:----------:|:------------------:|:---------------:|
| **Starter** | 1-25 | 150€ | 150€ - 3.750€ |
| **Professional** | 26-100 | 100€ | 2.600€ - 10.000€ |
| **Enterprise** | 101-500 | 75€ | 7.575€ - 37.500€ |
| **Unlimited** | 500+ | Contactar | Negociavel |

### Exemplos Concretos

| Cliente | Servidores | Tier | Preco/ano |
|---------|:----------:|------|:---------:|
| PME pequena | 10 | Starter | **1.500€** |
| Empresa media | 50 | Professional | **5.000€** |
| Companhia aerea (exemplo) | **100** | **Professional** | **10.000€** |
| Grande empresa | 200 | Enterprise | **15.000€** |
| Banca/Telco | 500 | Enterprise | **37.500€** |

---

## O Que Esta Incluido

### Em TODOS os tiers

| Feature | Incluido |
|---------|:--------:|
| KPIs em tempo real | ✅ |
| Monitoring de AlwaysOn/AG | ✅ |
| Analise de Backup (gaps, tendencias) | ✅ |
| Analise de Espaco (filegroups, forecast) | ✅ |
| Analise de Jobs (conflitos, tendencias) | ✅ |
| CPU, Memoria, Disco, Services | ✅ |
| SQL Diagnostics (blocking, deadlocks) | ✅ |
| Seguranca (TDE, permissoes) | ✅ |
| Users & Logins analysis | ✅ |
| Network Diagnostics | ✅ |
| Control Panel (admin, users, config) | ✅ |
| Active Directory integration | ✅ |
| i18n (PT/EN/ES) | ✅ |
| Servico Windows (auto-start) | ✅ |
| Actualizacoes de versao (1 ano) | ✅ |
| Suporte por email (dias uteis) | ✅ |

### Add-ons (opcionais)

| Add-on | Preco/ano |
|--------|:---------:|
| Suporte prioritario (SLA 4h) | +2.000€ |
| Instalacao assistida (remoto) | 500€ (one-time) |
| Instalacao presencial | 1.500€ (one-time) |
| Formacao equipa DBA (4h online) | 800€ (one-time) |
| Personalizacao (queries custom) | Sob consulta |
| AI/ML module (V5 — futuro) | +5.000€/ano |

---

## Modelo Alternativo: Licenca Perpetua

Para clientes que preferem compra unica:

| Tier | Preco (one-time) | Manutencao anual (20%) |
|------|:-----------------:|:----------------------:|
| Starter (1-25 srv) | 3.000€ | 600€/ano |
| Professional (26-100 srv) | 15.000€ | 3.000€/ano |
| Enterprise (101-500 srv) | 50.000€ | 10.000€/ano |

A manutencao anual inclui:
- Actualizacoes de versao
- Suporte por email
- Bug fixes

---

## Justificacao de Preco

### ROI para cliente com 100 servidores:

```
Poupanca anual estimada:     36.400€
Custo WatcherDB (Profissional): 10.000€/ano
ROI:                          264%
Payback:                      ~3.3 meses
```

### Comparacao com concorrencia:

```
WatcherDB (100 srv):           10.000€/ano
SolarWinds DPA (100 srv):     ~30.000€/ano  → 3x mais caro
Redgate SQL Monitor (100 srv): ~20.000€/ano → 2x mais caro
Datadog (100 srv):             ~50.000€/ano → 5x mais caro
```

---

## Politica Comercial

### Descontos

| Condicao | Desconto |
|----------|:--------:|
| Pagamento anual antecipado | 10% |
| Contrato 3 anos | 15% |
| Educacao / non-profit | 30% |
| Partner / revendedor | 20-30% |

### Trial

- **30 dias gratis** — funcionalidade completa, ate 10 servidores
- Sem cartao de credito
- Dados ficam no servidor do cliente (nao perde nada)

### Licenciamento

- Licenca por **servidor SQL monitorizado** (nao por user)
- Nao conta instancias — conta servidores fisicos/VMs
- Cluster AlwaysOn: conta como 1 servidor (todos os nos incluidos)
- Servidor de desenvolvimento/teste: **gratuito** (nao conta)

---

## Estrutura de Custos (interno)

| Item | Custo |
|------|------:|
| Desenvolvimento (2 pessoas, 6 meses) | ~60.000€ |
| Infraestrutura (servidores, ferramentas) | ~5.000€ |
| Licencas (PyArmor Pro) | 89€ |
| Marketing/website | ~2.000€ |
| Juridico (contratos, DPIA) | ~3.000€ |
| **Total investimento** | **~70.000€** |

### Break-even

```
Com preco medio de 8.000€/cliente/ano:
Break-even = 70.000€ / 8.000€ = 9 clientes

Com 5 clientes no primeiro ano:
Receita = 5 × 8.000€ = 40.000€
Margem = 40.000€ - 10.000€ (operacional) = 30.000€
```
