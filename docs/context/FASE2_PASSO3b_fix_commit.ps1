# Fase 2.1 - commit do fix NaN->None (apanhado na corrida manual, 22003)
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\FASE2_PASSO3b_fix_commit.ps1"

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"

git add "WATCHERDB INTELLIGENCE V1/scripts/collectors/collect_backup_failures.py" "WATCHERDB_V3.3/docs/context/FASE2_PASSO2_migration.ps1" "WATCHERDB_V3.3/docs/context/FASE2_PASSO3b_fix_commit.ps1"
git commit -m 'fix(v1 intel): Fase 2.1 - NaN/NaT para None no transform antes do store' -m 'Corrida manual pre-servico apanhou 22003 Numeric value out of range: pd.concat por servidor converte colunas all-None (Backup_Type_Classified em servers so com rows sysjobhistory) em float64 NaN e o pyodbc rejeita nan em NVARCHAR. Fix: astype(object).where(notna, None) em todas as colunas no fim do transform. Bissecao via tabela temp espelho (6 casos de binding OK; culpado era o NaN dos dados reais). Validado: PRD 1732 QA 888 TST 351 STORE SUCCESS; 43 resolved vs 19 unresolved na janela 30d. Inclui tambem v3 do script de migration (nome curto SQLHDSTST505 - FQDN nao resolve, DNS flap conhecido - e Invoke-Sqlcmd em vez de sqlcmd inexistente).' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'
git log -1 --format='%h %s'
