# 06 — Caso contra (challenger, Fase 2, 2026-09-15)

Autor: challenger, só leitura, a partir dos relatórios 00–04.
Verificação do orquestrador: confirmado `logs/service_stderr.log.1:55205-55207` e `:94064-94066` (`Instances OK: 62` / `Instances Off: 1`); `watcherdb_main.py:1334` (`'use_windows_auth': True,  # default seguro`); `watcherdb_main.py:2295-2298` (Space dashboard itera `app.state.sql_servers_config`); `CONTEXT.md:307-309` (20/08: availability 63, sidebar 62 até `provision_oatxp01_v33`).

**Veredicto.** Premissa fraca, solução sobredimensionada. Não há prova de a barra lateral ter mostrado 62 no período dos logs; o "63" do dashboard não é contagem de instâncias; "gestão persiste em servers.json via collector" tem o custo mais alto (transporte inexistente, duas cifras, credenciais no browser, estado partilhado V1) para uma operação rara que exige sempre passos fora do portal. Os defeitos com mais peso: ecrãs que ainda iteram 95 ids e o fallback para `Trusted_Connection`.

## 1. Premissa "63 vs 62 é bug de inventário"

**Factos**
- Logs V3.4: sempre 63 na barra lateral (482 + 2 linhas), nunca 62; nenhuma linha `[INVENTORY_REPO]` (`inventory_repo.py:184`, `:245`). Linhas sem data.
- Dois arranques em `service_stderr.log.1` (55205-55207, 94064-94066): `Instances OK: 62` + `Instances Off: 1` → sidebar 63, Online 62, `totI` = 63 (`portal.html:36832`).
- 20/08 teve exactamente "dashboard 63, sidebar 62" (`CONTEXT.md:307-309`): OATXP01 com primeira disponibilidade → 63; sidebar 62 até `provision_oatxp01_v33` (sem creds locais, `require_credentials=True`, `watcherdb_main.py:1155`).
- Filtro da sidebar só com pesquisa ≥2 caracteres (`portal.html:7029-7036`); sem pesquisa `filteredServers = [...allServers]` (`:6397`).
- "3 repetições" seguidas do GET ao dashboard não provam nada: cache TTL 60 s (`helpers.py:41-46`) servida directamente (`intelligence_kpis.py:954-956`).

**Hipóteses**

| # | Hipótese | A favor | Contra | Probabilidade |
|---|---|---|---|---|
| H-A | O "62" era o Online do cartão (ou "Instances OK"), não o contador da sidebar | 2 arranques 62 OK + 1 Off = 63; sidebar nunca 62 nos logs | Relato diz "barra lateral"; sem captura | Alta |
| H-0820 | Relato da janela de 20/08 (availability 63, antes do provisionamento DPAPI do OATXP01) | Forma exacta documentada | Só se o relato for antigo | Média |
| H1 | Dupla contagem `extra_off` sem ver `ok_count` (`helpers.py:1918-1941`) + corrida do gather | Mecanismo real | Explica 63 falso no dashboard, não sidebar 62 | Média como defeito, baixa como origem |
| H-search | Pesquisa activa | `minScore=1` (`portal.html:7108-7113`) | Teria de dar exactamente 62 | Baixa |
| H-rollout | Confusão com os 62 do `sql_auth_rollout.json` / GRANTs 62/63 (`CONTEXT.md:392`) | Números existem | Nenhum ecrã mostra essa contagem | Baixa |
| H-DNS | Incidente 15/09 15:11-16:25 | — | Faz descer abaixo de 63 | Muito baixa |

**Testes discriminantes**
1. **T0 (custo zero):** perguntar ao owner data/hora/porta (8433/8434), que rótulo mostrava 62 (`SERVIDORES (N)` ou "Online") e se a pesquisa estava vazia.
2. **T1 (2 min, `sql_monitoring`):** Q4 do relatório 04 reduzida a `in_off=1 OR in_svc_down=1` com `in_ok`. `in_ok=1` → H1 activa hoje.
3. **T2 (sem produção):** teste unitário com as duas ordens de conclusão de `collect_instance_availability` / `collect_service_status`.

Até T0, "bug de inventário" é **hipótese não suportada**; os dados apontam para fórmula e rótulo do dashboard.

## 2. "A gestão persiste em servers.json" é o requisito certo?

Adicionar instância exige cinco artefactos em dois domínios de cifra:
1. Login e GRANTs na instância alvo no SSMS com identidade do DBA (`RUNBOOK_ADICIONAR_REMOVER_SERVIDOR.md:11-20`) — o portal **não pode** (Regra de Ouro 2).
2. Entrada no canónico V1 (password `EncryptionManager`).
3. Sync 10 min → `metadata.monitored_server`.
4. Espelho DPAPI no V3.4 (`services/secrets.py`); sem ele fica escondida (`inventory_repo.py:176-182`).
5. Entrada em `config/sql_auth_rollout.json`; sem ela o pool liga `Trusted_Connection=yes` (`connection_pool.py:766`, `:784`).

Formulário que escreve só o passo 2 dá falsa sensação de "feito".

| Eixo | Custo portal → collector |
|---|---|
| Transporte | **Não existe** (sem listener HTTP em `services/collector_service/`). Listener novo (porta, TLS, auth serviço-a-serviço, firewall), tabela de pedidos (schema partilhado, veto V1, Pro) ou drop de ficheiro (mesmo host não garantido) |
| Credenciais | Password no browser → portal → collector; em memória em dois processos com cifras diferentes; auditor bancário pedirá MFA/4-eyes |
| Concorrência | 3 escritores do canónico (runbook, `discover_databases.py`, endpoint): lock + CAS por hash |
| Auditoria | `SQL_SERVERS_CONFIG_SAVED` só guarda "N servidores" (`watcherdb_main.py:1259-1267`); precisa diff por id, actor, run_id |
| UX | pior caso ~11 min; sem "pendente" a pergunta repete-se |
| Edições | V6 4.ª cópia; collector serve Std e Pro |
| Tier | `docs/FEATURE_MATRIX.md` não menciona gestão de inventário; "Std+Pro" do 03 é inferência |

**Agravante vivo (FACTO):** INSERT do sync cria `use_windows_auth: True  # default seguro` (`watcherdb_main.py:1334`); `_local_credential_ids` conta como credencial (`inventory_repo.py:161`) → "tem credenciais" falso que empurra para `Trusted_Connection`.

**Posição:** em Std, a gestão no portal **não deve escrever**. Runbook + CLI de provisionamento no V1 corrido pelo DBA na máquina do collector (atómico, validação, dry-run com diff), zero superfície de rede e zero credenciais no browser. Portal só leitura com estado.

## 3. Onde "mesmo conjunto" piora a operação

1. **Sem credenciais na sidebar → `Trusted_Connection`.** FACTO: `SQLServerMonitoring` delega no pool (`modules/monitoring/monitoring.py:120,160`), que fora da allowlist liga Trusted (`connection_pool.py:754,784`). HIPÓTESE: itens clicáveis geram logins AD em servidores do banco (classe dos 5 logins falhados de 15/09, `CONTEXT.md:464`). Array separado, não clicável, com teste de que não se constrói connection string.
2. **Alias partido** (SS301): conjunto por id mostra "sem recolha" permanente — cinzento falso.
3. **Listener AG:** o `sql_servers.json` de 95 tinha listeners/farms (`CONTEXT.md:301`); não recuperar esse ficheiro.
4. **Falha de DNS no collector** (15/09, 29/07): hoje o total encolhe em silêncio (verde falso "100% sobre 44 de 107", `CONTEXT.md:157`); com denominador = inventário, dezenas de "sem recolha" e `instances_offline` (A2/A3) dispara em massa — vermelho falso. Aceitável **só** com porta de saúde do collector: heartbeat velho ou >X% sem recolha → estado único "recolha parada", sem alertas por instância, % = "—".
5. **Disponibilidade % muda de base:** relatórios mês a mês deixam de ser comparáveis; anotar no CHANGELOG.
6. **Filtro por ambiente não fecha:** offline por host e `Undefined` fora da soma (`portal.html:36831`).

## 4. E6c é bloqueante?

- Para fórmula do dashboard e estado da sidebar: **não**.
- Modal só-leitura **é** o item 3 do E6c.
- Para declarar "inventário unificado": **item 1 bloqueia**. `/api/monitoring/space/dashboard` itera os 95 ids (`watcherdb_main.py:2295-2298`, arranque `:172-183`), backup summary também (`:2465-2466`) — terceiro conjunto vivo (95 vs 63 vs 62); os 33 fora do inventário seguem por `Trusted_Connection`.
- Itens 4 (hardcoded/Excel) e 2 (fallback AlwaysOn): dívida, não bloqueio.

**Ordem:** T0/T1 → fórmula do dashboard → modal só-leitura (E6c-3) → E6c-1 (boot, Space/Backup via InventoryRepo) → estados "sem credenciais"/"sem recolha" → CLI V1 → portal→collector só com procura provada.

## 5. Critérios de aceite mensuráveis

Ids normalizados `UPPER(REPLACE(LTRIM(RTRIM(x)),'\','_'))`.
- **INV** = `metadata.monitored_server` com `tenant_id='default' AND is_active=1 AND enabled=1` (como `sql_monitoring`).
- **SB** = `servers[]` de `/api/v3/servers` + array aditivo `unavailable[]`.
- **DASH** = partição por ids: `ok_ids`, `off_ids`, `no_collection_ids`.

| # | Critério | Prova | Falha |
|---|---|---|---|
| C1 | SB ∪ unavailable = INV, diferença simétrica vazia | teste de contrato + query ao vivo, por ids | qualquer id a mais/menos (63=63 com troca também falha) |
| C2 | Partição disjunta e \|ok\|+\|off\|+\|nc\| = \|INV\|; ids fora do INV em lista à parte | Q4 sem `in_ok=1 AND (in_off=1 OR in_svc_down=1)`; unitário OK+serviço em baixo | `totI` > \|INV\| |
| C3 | Determinismo | duas ordens do gather → payload igual; 5 amostras >60 s sem mudança → igual | variação |
| C4 | Convergência ≤12 min p95 sem restart | adicionar/desactivar instância de teste no canónico; T(audit sync) → T(log N±1) | >15 min ou restart |
| C5 | Falha do collector | DEV com heartbeat parado e 30% sem recolha → 1 estado "recolha parada", 0 `instances_offline` por instância, % = "—" | alerta por instância ou % calculada |
| C6 | Regra 2 | clique em sem-credenciais não chama `_build_connection_string`; 0 `Trusted_Connection` nos logs | qualquer tentativa |
| C7 | Retrocompatibilidade | `tests/test_functional_acceptance.py:127-275` verde; `ok_count/off_count` mantidos; campos aditivos; prompt V6 | contrato alterado |
| C8 | Filtro por ambiente | PRD+QLT+TST+Undefined = total sem filtro | diferença ≠ 0 |

## 6. Ranking

| | A. Quase nada | B. A + E6c-1 + CLI V1 | C. Portal → collector |
|---|---|---|---|
| Conteúdo | Partição por ids no dashboard; integração serviço→disponibilidade depois do gather; sidebar "63 · 1 sem credenciais" não clicável; modal só GET, POST desactivado (E6c-3); link runbook | A + boot/Space/Backup via InventoryRepo + script V1 add/disable (atómico, EncryptionManager, espelho DPAPI, allowlist, dry-run diff) | CRUD UI, transporte novo, credenciais web, lock, auditoria diff, pendente, paridade V5/V6 |
| Custo | 1-2 dias | ~1 semana | várias semanas + auditoria segurança + decisão tier |
| Risco | Baixo | Médio (Space/Backup 95→63 visível; CLI gate V1) | Alto |
| Blast radius V1 | Nenhum | CLI no repo V1, sem schema | Schema/serviço partilhado → veto provável |
| Tier | Neutro | Neutro | Entrada nova na FEATURE_MATRIX |

**Escolha: A já, B a seguir, C só com prova de procura.** Frequência de mudança baixa (meia dúzia desde 19/08); nenhum fluxo de adição completo dentro do portal (GRANTs exigem SSMS); valor de C tem tecto e risco não.

## Auto-ataque
- Relato pode ser actual e de outro ambiente (8433 PRD); decide T0 + log desse ambiente.
- "Frequência baixa" é do laboratório; cliente com >100 instâncias no onboarding muda a conta — depende de `install_wizard.py` cobrir a importação inicial.
- Trusted no clique da sidebar é leitura de código; o drill-down pode filtrar antes — decide o teste C6.
- H-A assenta em linhas de pré-carga no arranque; T0 com captura resolve.
