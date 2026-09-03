# Backup Delayed (council 01/09) - PASSO 6: cross-filter entre os charts da modal
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\DELAYED_PASSO6_crossfilter_commit.ps1"
# DEPOIS (consola Admin): Restart-Service WatcherDBWebServiceV33
# (so portal HTML - sem backend, sem migration, sem BD)

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

git add WATCHERDB_V3.3/templates/watcherdb_portal.html WATCHERDB_V3.3/docs/context/DELAYED_PASSO6_crossfilter_commit.ps1

git commit -m 'feat(v33): modal Backup Delayed - cross-filter entre chart de ambiente e chart de tipo' -m 'Owner 02/09: clicar numa barra de tipo passa a recontar o chart de ambientes so com esse tipo, e vice-versa. Cada chart reage aos filtros dos OUTROS (tipo e instancia filtram o de ambiente; ambiente e instancia filtram o de tipo) mas nunca ao seu proprio - permite trocar de seleccao dentro do mesmo chart sem o esvaziar (padrao cross-filter). Condicoes de match replicadas da lista (incl. Undefined = envs fora de PRD/QLT/TST/DEV e combobox multiselect). Totais continuam em bases distintas por chart, com fail-open para linhas se o payload nao tiver basekey.' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'

git log -1 --format='%h %s'
