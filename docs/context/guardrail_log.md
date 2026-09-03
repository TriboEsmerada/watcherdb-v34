# Guardrail log — tentativas bloqueadas pelo hook PreToolUse

> Append-only, escrito por `.claude/hooks/guard_write_paths.py`.
> Formato: `timestamp | tool | alvo | motivo`

- `2026-06-12 17:51:18` | DENY | Bash | `sqlcmd -S X -Q "DELETE FROM dbo.KPI_MSSQL_EVENTS"` | Padrao de mutacao detectado: SQL DELETE
- `2026-06-12 17:55:07` | DENY | Write | `C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\api\main.py` | Escrita fora dos caminhos permitidos
- `2026-06-12 18:06:59` | DENY | Write | `C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\api\main.py` | Escrita fora dos caminhos permitidos
- `2026-06-12 18:06:59` | DENY | Bash | `sqlcmd -S X -Q "DELETE FROM dbo.T"` | Padrao de mutacao detectado: SQL DELETE
- `2026-06-12 18:06:59` | DENY | Bash | `git push origin main` | Padrao de mutacao detectado: git push
- `2026-06-12 18:06:59` | DENY | PowerShell | `Remove-Item -Recurse -Force "C:/tmp/x"` | Padrao de mutacao detectado: Remove-Item -Recurse -Force
- `2026-06-12 18:06:59` | DENY | PowerShell | `sqlcmd -Q "ALTER TABLE dbo.T ADD C int"` | Padrao de mutacao detectado: SQL ALTER
- `2026-06-12 18:07:00` | DENY | Write | `C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\CLAUDE.md` | Escrita fora dos caminhos permitidos
