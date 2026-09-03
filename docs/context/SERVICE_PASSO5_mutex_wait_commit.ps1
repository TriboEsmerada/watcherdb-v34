# Servico V33 - PASSO 5: espera pelo mutex no arranque (fim do StartServiceFailed)
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\SERVICE_PASSO5_mutex_wait_commit.ps1"
# DEPOIS (consola Admin): Restart-Service WatcherDBWebServiceV33
#   -> este restart e' a VALIDACAO: deve passar a' PRIMEIRA (antes falhava e
#      exigia segunda tentativa). Confirmar no Event Log a linha
#      "mutex libertado pela instancia anterior" se houve espera.

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

git add WATCHERDB_V3.3/watcherdb_service.py WATCHERDB_V3.3/docs/context/SERVICE_PASSO5_mutex_wait_commit.ps1

git commit -m 'fix(v33): servico espera ate 45s pelo mutex single-instance no arranque - Restart-Service deixa de falhar a primeira' -m 'Causa raiz do StartServiceFailed recorrente: o stop reporta STOPPED ao SCM antes de o processo antigo morrer (janela graciosa de shutdown ~30s) e o SO so liberta o mutex Global na morte do processo. O arranque novo testava o mutex UMA vez e abortava. Fix: retry a cada 2s ate 45s, a reportar SERVICE_START_PENDING com waitHint para o SCM nao matar o arranque; log informativo quando a espera aconteceu e erro so depois do deadline (ai e mesmo outra instancia). Evidencia: Event Log 02/09 09:33:02 instancia ja em execucao / arranque abortado seguido de arranque manual 47s depois. Compile OK + 4 testes test_service_entry verdes. Propagar a V6 (mesmo wrapper, mesmos 4 defeitos de boot hardening corrigidos em 23/07 - este e o 5o).' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'

git log -1 --format='%h %s'
