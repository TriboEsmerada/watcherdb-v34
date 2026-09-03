# PROMPT DE SESSAO — Wave R2-03 cookie-primario (owner 2026-08-21)

Colar numa sessao V3.3 fresca. Versao do owner 21/08 (noite), substitui a
versao entregue so' em chat na sessao principal do mesmo dia.

---

Abre a wave R2-03 cookie-primário (decisão registada em docs/context/CONTEXT.md,
diário 2026-08-21). Scope: auth do portal V3.3 passa a cookie httponly primário;
watcherdb_token sai do localStorage (12 call-sites manuais + interceptor global —
ver auth_compat.py:187-195); logout com invalidação server-side; primitiva CSRF
como trabalho CONCORRENTE (não sequencial), partilhada com o SSIS Manager
(precedente commit 6ec4c55 — a tese "SameSite=Lax cobre CSRF" está errada).
Abre com dispatch: watcherdb-security-auditor (primitiva CSRF + ordem de migração
sem partir sessões activas) + watcherdb-frontend-specialist (mapa dos call-sites);
QA adversarial no fim com a prova document.cookie vs localStorage antes/depois.

---

## Guardas para a AI da sessao nova (nao remover)

1. Correr `/recall cookie csrf localStorage R2-03` ANTES de tocar em codigo
   (regra 11). O precedente vivo esta' em CONTEXT.md diario 2026-08-21 (linha
   "DECISAO R2-03 ACEITE"): factos ja' verificados na fonte —
   auth_compat.py:187-195 e 338-343; 12 call-sites manuais; decisao owner +
   QA senior. NAO re-litigar a decisao nem re-descobrir os call-sites do zero
   sem confirmar contra este rasto.
2. A primeira linha do pedido chega; o resto e' redundancia defensiva caso o
   diario nao seja lido (escolha deliberada do owner).
3. Se a sessao partir para implementacao sem ler o precedente: TRAVAR e ler
   primeiro.
