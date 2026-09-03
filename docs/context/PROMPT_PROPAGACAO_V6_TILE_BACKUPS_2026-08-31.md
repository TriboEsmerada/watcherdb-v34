# PROMPT PROPAGACAO V6 — tile Backups: split "Em atraso" (critico)/(aviso) (2026-08-31)

Colar numa sessao V6. Regra: portal V6 NAO e' superset do V3.3 — grep anchors
ANTES de aplicar; se o anchor nao existir, reportar "nao aplicavel" e parar.

## O que mudou em V3.3 (e porque)

Incoerencia de superficies no dashboard KPIs: o painel POR CATEGORIA conta
criticos de Backups = failed_count + log_failed_count + delayed_critical_count
(promocao de 2026-08-06 — FULL parado 30d nao podia ficar amarelo), mas o tile
Backups mostrava "Em atraso" como UMA linha amarela com o total delayed_count.
Com o filtro CRITICOS activo, o tile mostrava so "Log falhou 12" enquanto o
painel dizia "Backups 365" (ecra do owner, 31/08; ~353 = gap RPO critico).

Fix V3.3 (commit "fix(v33): tile Backups expoe Em atraso (critico)/(aviso)"):
a row unica foi substituida por duas, no padrao ja usado pelos tiles de disco:

    _advRow(ev(bk,'delayed_critical_count')>0 ? C.crit : C.ok, 'Em atraso (critico)', ev(bk,'delayed_critical_count'), '', 'backup-delayed', 'Backup Delayed') +
    _advRow(ev(bk,'delayed_warning_count') >0 ? C.warn : C.ok, 'Em atraso (aviso)',   ev(bk,'delayed_warning_count'),  '', 'backup-delayed', 'Backup Delayed') +

## Contratos que a AI de la' precisa de saber

1. delayed_critical_count / delayed_warning_count (+ *_by_env) vem do backend
   helpers (V3.3: collect_backup_status) e existem desde 2026-08-06. V6 herda
   o MESMO payload se usa o mesmo backend de KPIs; verificar primeiro se o
   backend V6 ja expoe os campos — se nao, a propagacao comeca no backend.
2. As duas rows abrem a MESMA modal backup-delayed. Os ids
   backup-delayed-critical/-warning sao pseudo-ids SO para a aritmetica do
   painel (KPI_REPORT_GROUPS) — NAO sao kpiType reais; nao os passar a rows.
3. Sem chaves i18n novas: o bloco _advRow e' PT inline (debt sistemica
   conhecida); nao criar ilha de traducao de 2 chaves.
4. Nao ha mudanca de contagem em lado nenhum — e' so o ultimo metro ate ao
   primeiro ecra. Se o portal V6 nao tiver o painel Por Categoria nem o
   filtro de severidade, o split pode nao ser necessario — avaliar e reportar.
5. FIND-20260831-101 (V3.3, aberto): granularidade de delayed_critical =
   (Instance, Database, TIPO) sem dedupe por base — decisao de semantica
   executiva pendente. NAO "resolver" isto em V6 por iniciativa propria; a
   decisao vai ser tomada em conjunto e propagada.

## Passos sugeridos

1. grep no portal V6: "delayed_count" / "Em atraso" / "backup-delayed" /
   "KPI_REPORT_GROUPS" / "_advRow". Sem match = nao aplicavel, reportar.
2. Se aplicavel: replicar o split (snippet acima, adaptado aos anchors V6),
   docs V6 no mesmo bloco (catalog/changelog locais).
3. Validacao: filtro CRITICOS no dashboard V6 — soma das rows vermelhas do
   tile Backups tem de bater com o numero da categoria no painel.
