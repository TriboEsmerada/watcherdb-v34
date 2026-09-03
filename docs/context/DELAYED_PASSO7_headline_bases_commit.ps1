# Backup Delayed (council 01/09) - PASSO 7: cabecalho em bases + totais seguem todos os filtros
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\DELAYED_PASSO7_headline_bases_commit.ps1"
# DEPOIS (consola Admin): Restart-Service WatcherDBWebServiceV33
# (so portal HTML - sem backend, sem migration, sem BD)

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

git add WATCHERDB_V3.3/templates/watcherdb_portal.html WATCHERDB_V3.3/docs/context/DELAYED_PASSO7_headline_bases_commit.ps1

git commit -m 'fix(v33): modal Backup Delayed - Mostrando passa a bases e totais dos charts seguem todos os filtros' -m 'Owner 02/09 (Mostrando 190 vs totais 101): o cabecalho ficou na unidade velha (linhas) quando tile e charts passaram a bases. Fix: (1) Mostrando N bases (M linhas por tipo) - bases VISIVEIS, mesma unidade do tile; (2) os TOTAIS dos 2 charts passam a seguir TODOS os filtros activos (incl. o proprio) - cabecalho, Total (bases) e Bases distintas dizem sempre o MESMO numero; so as barras ignoram o proprio filtro, para se poder trocar de seleccao dentro do chart; (3) linha de reconciliacao deixa de duplicar a conversao linhas-bases. Vale para as 4 modais (critico, aviso, DIFF parado, System DBs AG) - renderer e filtros sao partilhados, o pre-filtro por classe corta os dados antes do render.' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'

git log -1 --format='%h %s'
