# Backup Delayed (council 01/09) - PASSO 4: charts da modal coerentes com o total
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\DELAYED_PASSO4_charts_commit.ps1"
# DEPOIS (consola Admin): Restart-Service WatcherDBWebServiceV33
# (so portal HTML - sem backend, sem migration, sem BD)

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

git add WATCHERDB_V3.3/templates/watcherdb_portal.html WATCHERDB_V3.3/docs/context/DELAYED_PASSO4_charts_commit.ps1

git commit -m 'fix(v33): modal Backup Delayed - numero da barra ia para dentro do preenchimento e coluna ficava velha + rotulos de unidade nos totais' -m 'Owner 01/09: coluna da direita do chart por ambiente mostrava linhas (106/44/4) com o Total em bases (75) - o recount usava querySelector div:last-child que apanhava o PREENCHIMENTO da barra (unico filho do contentor) e escrevia o numero DENTRO da barra, deixando a coluna da direita com o valor velho. Fix: lastElementChild da row + limpar texto residual do preenchimento. E no chart por tipo as parcelas sobrepoem-se (uma base pode ter FULL e LOG em atraso ao mesmo tempo) - o rotulo do total passa a dizer a unidade: Total (bases) no ambiente, Bases distintas no tipo. Ambiente: 46+25+4=75=tile. Tipo: 59/55/40 com total 75 bases distintas explicado.' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'

git log -1 --format='%h %s'
