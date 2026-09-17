# ADR — V6 e V3.4: como acabar com a propagação por prompt (2026-09-17)

Estado: **proposta ao owner** (decisão pendente). Pareceres: `architecture-advisor` e `challenger`, com os números medidos
pelo orquestrador a 17/09. Só leitura; nada aqui foi aplicado.

## O que se mediu

- Código (api, services, modules, templates, static, database, deploy, tools): V3.4 308 ficheiros, V6 647; comuns 180
  (69 iguais, **111 diferentes**); só no V3.4 **128**; só no V6 467.
- **Não há um único commit git em comum**: V3.4 nasceu a 03/09 como snapshot da V3.3; V6 nasceu a 19/04 como clone do V5.
  Logo não existe "rebase" — qualquer reunificação é uma nova linhagem, construída à mão uma vez.
- O código só-V6 **toca nos comuns**: `watcherdb_main.py` 79 `include_router` contra 29; `intelligence_kpis.py` +3.345/−1.241;
  portal ~40 % reescrito (791 vs 669 funções JS; 515 comuns); `connection_pool` com modelos opostos (V3.4 SQL Auth por
  `servers.json` + `_resolve_credentials`; V6 `Trusted_Connection=yes` puro, mas com circuit breaker, guarda de escrita e
  `check_least_privilege` que o V3.4 não tem); `auth_service` 1.570 vs 813 linhas (V6 sem login AD).
- Licenciamento: o registry do V6 (`TIER_ALLOWLIST_MAP`) é superconjunto do V3.4 — aí o canónico é o V6. Mas há uma
  contradição comercial: `dba_copilot_rule_based` está em Standard no V6 e removido no V3.4 (FIND-013-B, 05/05).
- Tier no V6 é imposto por ausência de ficheiro (1 router em 100 lê `is_enabled`); juntar os dois file-sets = juntar os tiers.
- Base partilhada: o V6 escreve em ~20 tabelas por `execute_write_on_intelligence`; `threshold_current`, `kg_knowledge_base`,
  `WatcherDB_Metrics_Snapshots`, `incident_memory` têm 0 ocorrências no canónico do V1. Dois sistemas de limiares
  (`WDB_KPI_THRESHOLDS` vs `threshold_current`) contra as mesmas STG.
- Estado do V6: `main` parado a 03/08; ramo `wave-propagacao-v33-20260819` 37 commits à frente; 131 ficheiros por commitar;
  **sem remoto**; a "certificação 7/7" aparece em 8 documentos e nenhum lista os 7 itens.
- Propagação: 12 prompts entre 04 e 15/09, zero aplicados; latência quando há sessão dedicada 16–19 h; hoje 6 lotes portados
  à mão (cada um reescrito) e 5 por portar. `admin123` ainda vivo em `services/auth_service.py:433-455` do V6 (lote pronto).

## O que os dois pareceres concordam

1. "Rebase" tal como foi dito **está errado**: sem merge-base, sem freeze possível (os comuns são o produto).
2. A propagação por prompt **já falhou**; a divergência de segurança na mesma BD partilhada é intolerável.
3. Antes de qualquer decisão: **commit dos 131, `wave` → `main`, tag, remoto privado, e baseline medida** (7/7 definido, golden eval, pytest).
4. Canónico é **por ficheiro**: pool/auth/portal/KPIs/collector health = V3.4; licensing/packaging AI = V6.

## Onde divergem

- **Advisor:** GO condicional para a nova linhagem (`v6-next` a partir do V3.4 `main`, só-V6 copiado, ganchos refeitos uma vez,
  portal com painéis AI injectados no serve); custo 3–4 semanas de esforço / 6–8 de calendário; gatilho de abortar: > 25 comuns
  com ganchos não isoláveis por registry. Métricas: `N_div` 111 → ≤ 15; `P_pend` 5 → 0; `Trusted_Connection` no V6 27 → 0.
- **Challenger:** a nova linhagem paga tudo à cabeça e depende de o V6 deixar de tocar nos comuns, o que os 6 commits de hoje
  (6/6 em comuns) contradizem. Recomenda **C agora** (dois códigos + gate automático que falha o fecho do dia quando um commit
  V3.4 em ficheiro security-critical não tem par no V6 com o trailer `propagado do V3.4 <sha>`), **D-restrito como política**
  (paridade obrigatória em segurança e schema; features best-effort, medidas) e núcleo partilhado **só** para auth + pool +
  secrets + licensing.

## Recomendação do orquestrador

Corrijo a minha posição de ontem: não é rebase, e não é já.

1. **Esta semana (sem decisão de arquitectura):** arrumar o V6 (commit, merge, tag, remoto privado, `git bundle`), aplicar o
   lote `V6_SEM_FALLBACK_ADMIN123`, definir por escrito os 7 itens da certificação e medi-los. Instalar o **gate C** (lista
   security-critical + trailer) — reversível, custo de um dia, mede a barra de imediato.
2. **Semana 2 — medir antes de escolher:** inventário de ganchos nos 180 comuns (imports de código só-V6, routers extra,
   `is_enabled`). É este número que decide: ≤ 25 isoláveis → nova linhagem (advisor); mais do que isso → núcleo pequeno
   (auth + pool + secrets + licensing) e o resto fica em C/D-restrito. Em paralelo: reconciliar com o V1 as tabelas que o V6
   escreve fora do canónico (veto latente do guardião, seja qual for a opção) e resolver a contradição do `dba_copilot`.
3. **Política desde já (D-restrito):** um fix de segurança ou de schema no V3.4 sem par no V6 em 5 dias úteis é incidente,
   não dívida.

## Decisões que só o owner pode tomar

- Onde vive o remoto do V6 (privado) e se o `watcherdb-v34` público passa a privado.
- `dba_copilot_rule_based`: Standard ou Pro?
- Se o V6 "GA" é o `main` de 03/08 (com sementes) ou o ramo de hoje.
