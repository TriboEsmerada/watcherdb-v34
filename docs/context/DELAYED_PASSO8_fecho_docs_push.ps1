# Backup Delayed + servico - PASSO 8: bandas em bases + fecho de docs + push para o GitHub
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\DELAYED_PASSO8_fecho_docs_push.ps1"
# DEPOIS (consola Admin): Restart-Service WatcherDBWebServiceV33
#   (ha mudanca de backend: contadores das bandas passam a bases)

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

git add WATCHERDB_V3.3/api/routers/intelligence/backup_delayed_classes.py WATCHERDB_V3.3/api/routers/intelligence/helpers.py WATCHERDB_V3.3/tests/unit/test_backup_delayed_classes_20260901.py WATCHERDB_V3.3/docs/changelog/CHANGELOG.md WATCHERDB_V3.3/docs/context/CONTEXT.md WATCHERDB_V3.3/docs/context/SOLUCOES.md WATCHERDB_V3.3/docs/context/PROMPT_PROPAGACAO_V6_DELAYED_SIGNAL_2026-09-01.md WATCHERDB_V3.3/docs/context/PROMPT_PROPAGACAO_V6_MIRROR_MELHORIA_2026-09-01.md WATCHERDB_V3.3/docs/context/PROMPT_PROPAGACAO_V6_MANUTENCAO_BD_2026-07-28.md WATCHERDB_V3.3/docs/context/PROMPT_PROPAGACAO_V6_THRESHOLDS_F15_2026-08-13.md WATCHERDB_V3.3/docs/context/DELAYED_PASSO8_fecho_docs_push.ps1

git commit -m 'fix(v33): bandas de aviso do Delayed contam bases (R1) + fecho de docs do pos-ship' -m 'Owner 02/09 (baixar tambem os avisos): ag_system_gap_count e diff_schedule_stopped_count passam a contar BASES como o executivo - dedupe por Base_Key no modulo (by_env idem); tile fica coerente com o cabecalho da modal que ja dizia N bases. Medido vivo: AG gap 64 linhas para 40 bases em 17 nos. Listas do modal continuam por linha. Teste de contrato novo (11 verdes). Tier checker PASS no lote fd5be40..HEAD (zero creep; ambito Std). Docs: CHANGELOG (pos-ship 8 acertos + fix servico mutex), 2 episodios SOLUCOES (mutex race + querySelector last-child), diario CONTEXT, addendum V6 no PROMPT_PROPAGACAO_V6_DELAYED_SIGNAL (8 acertos + bonus mutex-wait) e ajustes pendentes nos prompts V6 de manutencao BD, thresholds F15 e mirror melhoria.' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'

git log -1 --format='%h %s'

# push de TUDO (branch de trabalho actual)
git push origin wave-b-indexacao-dmv
