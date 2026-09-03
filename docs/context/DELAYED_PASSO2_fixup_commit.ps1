# Backup Delayed (council 01/09) - PASSO 2: fixup pos-ship (divergencias modal)
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\DELAYED_PASSO2_fixup_commit.ps1"
# DEPOIS (consola Admin): Restart-Service WatcherDBWebServiceV33
# (so portal HTML - sem backend, sem migration, sem collector)

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

git add WATCHERDB_V3.3/templates/watcherdb_portal.html WATCHERDB_V3.3/docs/context/DELAYED_PASSO2_fixup_commit.ps1

git commit -m 'fix(v33): modal Backup Delayed - barras recontadas, pre-filtro por classe nas 4 linhas do tile, linhas vs bases explicito' -m 'Owner 01/09 apos ship do council: (1) graficos por ambiente/tipo recontam sobre as linhas visiveis (cadeia reiniciada oculta por default ja nao infla as barras vs o total); (2) as 4 linhas do tile abrem a modal PRE-FILTRADA pela sua classe via tokens CLASS aplicados aos DADOS antes do render - critico, aviso, agendamento DIFF parado, system DBs de nos AG - mesma regra 2026-07-31 do pre-filtro FULL/DIFF: numeros nao se contradizem; (3) linha de reconciliacao passa a dizer N linhas = M bases via data-basekey - o cartao conta bases (dedupe R1), a modal lista linhas por tipo.' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'

git log -1 --format='%h %s'
