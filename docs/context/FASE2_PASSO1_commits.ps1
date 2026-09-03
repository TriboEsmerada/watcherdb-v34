# Fase 2 KPI Backup Failed - PASSO 1: commits (V1 ja esta staged)
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\FASE2_PASSO1_commits.ps1"

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

Write-Host ">>> Prova de contexto" -ForegroundColor Cyan
git branch --show-current   # esperado: wave-b-indexacao-dmv

Write-Host ">>> Commit 1: V1 collector + migration + canonical + changelog" -ForegroundColor Cyan
git commit -m 'feat(v1 intel): Fase 2 KPI Backup Failed - Resolved_By_Success_TS no collector' -m 'Council 21/08, v1-intel GO-com-condicoes. OUTER APPLY sysjobhistory MIN 1o sucesso pos-falha; janela Source 1 7d p/ 30d; sem DATETIME2 na query (SQL 2005); NaT p/ None no transform. Migration 8 tabelas + sp_refreshview + validacao pre-cutover; canonical CREATE no mesmo bloco.' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'

Write-Host ">>> Commit 2: V3.3 card+modal + docs + specialists + prompts" -ForegroundColor Cyan
git add WATCHERDB_V3.3/api/routers/intelligence/helpers.py WATCHERDB_V3.3/api/routers/intelligence_kpis.py WATCHERDB_V3.3/knowledge_base/architecture/kpis/backups_kpis.md WATCHERDB_V3.3/docs/changelog/CHANGELOG.md WATCHERDB_V3.3/.claude/agents/watcherdb-v1-intel-specialist.md WATCHERDB_V3.3/.claude/agents/watcherdb-v33-specialist.md WATCHERDB_V3.3/docs/context/CONTEXT.md WATCHERDB_V3.3/docs/context/PROMPT_PROPAGACAO_V6_BACKUP_FASE2_2026-08-21.md WATCHERDB_V3.3/docs/context/PEDIDO_EXECUCAO_FASE2_BACKUP_2026-08-21.md WATCHERDB_V3.3/docs/context/PROMPT_SESSAO_R2_03_COOKIE_PRIMARIO_2026-08-21.md WATCHERDB_V3.3/docs/context/FASE2_PASSO1_commits.ps1 WATCHERDB_V3.3/docs/context/FASE2_PASSO2_migration.ps1
git commit -m 'feat(v33): Fase 2 Backup Failed - card e modal leem Resolved_By_Success_TS da STG' -m 'Substitui o mecanismo Fase 1 (JOIN AGENT_JOBS_STG + helper, so ultimo run) pela coluna do collector (historico completo). Fail-open estrutural: NULL = ainda em falta. JOIN AGENT_JOBS_STG mantido so p/ campos de agendamento 17/08. Helper backup_job_failure_recovered removido. Doc drift corrigido. NAO restartar V33 antes da migration + 1 ciclo do collector.' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'

Write-Host ">>> Resultado (esperado: 2 commits novos no topo)" -ForegroundColor Cyan
git log -2 --format='%h %s'
