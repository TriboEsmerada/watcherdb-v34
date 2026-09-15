# PROPAGAÇÃO V6 — errorlog: leitor por tipo, recolhedor por janela e job em falso verde

> Para a AI do V6. **Verificar primeiro, assumir nunca.** Origem no V3.4: `docs/context/B0_MEDICAO_ERRORLOG_2026-09-15.md`
> e os lotes `ERRORLOG_LEITOR_TIPO`, `B1A_CLASSIFICADOR_ERRORLOG`, `B1B_RECOLHEDOR_ERRORLOG` e
> `M011_JOB_ERRORLOG_DESABILITAR`, todos de 2026-09-15.

## O que mudou na infra partilhada (V1), e que o V6 vai ver

- **`KPI_MSSQL_ERRORLOG_STG`** passa a ter `Log_Type` em {Lifecycle, AvailabilityGroup, Critical, Security, Error,
  Repetitive} em vez de sempre 'Error', e `Error_Number`, `Severity` e `State` preenchidos. Informativos saem.
  Arranques e encerramentos passam a entrar. A STG continua a guardar só a última janela (65 min).
- **`Log_Text_Hash`** passa a crc32 com sinal. Nas STG é int sem chave primária; na HIST é calculado.
- **Job `WatcherDB_Collect_ErrorLogs`** desabilitado (migration 011) e manifesto da Wave D com `Enabled_Expected = 0`.

## O que verificar no V6

1. **Algum leitor conta críticos pela severidade?** Grep por `'16', '17', '18'` ou `Severity >= 16` junto de
   `ERRORLOG`. Se sim, o V6 vai pintar de vermelho as instâncias com o 33208 de auditoria (severidade 17,
   repetitivo). Aplicar a regra do V3.4: crítico = `Log_Type` Critical; aviso = Error, AvailabilityGroup,
   Lifecycle; Security e Repetitive fora do cartão.
2. **Algum leitor filtra `Log_Type = 'Error'`?** Deixa de apanhar quase tudo. Trocar pela lista de tipos.
3. **Algum ecrã conta linhas brutas da STG?** Os repetitivos vêm linha a linha (uma instância tem ~1.100 por
   janela); a agregação por hora só existe na HIST, no B2b.

## Política de retenção decidida (entra no B2, ainda não implementada)

Texto com login e IP 90 dias; eventos 12 meses (12 a 36, por cliente); agregados horários 13 meses; legal hold
por instância; expurgo sobre Log_Date com registo do que apagou. O histórico não substitui SQL Server Audit nem SIEM.
Detalhe no plano `PLANO_EXECUCAO_ALERTAS_ERRORLOG_2026-09-14.md` do V3.4.
