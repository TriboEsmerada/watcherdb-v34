# PEDIDO — Modal Transaction Logs por base: validação pelo owner (2026-09-02)

Bloco único, auto-verificável. Identidade DB: **sql_monitoring** (SELECT only).
A AI não conseguiu correr o SELECT de controlo (pool sem senha no CLI; 8433
exige sessão — mesmo bloqueio de 05/08).

## 1. SELECT de controlo (SSMS ou Invoke-Sqlcmd, nome curto SQLHDSTST505)

```sql
USE WatcherDB_Intelligence;
-- (a) o que o tile e o cabeçalho do modal DEVEM mostrar (registry 85/95, frescura 24h)
;WITH b AS (SELECT Instance,[Database],Percent_Used FROM dbo.KPI_MSSQL_TLOG_USAGE_ACTIVE WITH (NOLOCK)
            WHERE Update_TS >= DATEADD(MINUTE,-1440,GETDATE()))
SELECT COUNT(*) AS rows_fresh,
       COUNT(DISTINCT CASE WHEN Percent_Used>95 THEN Instance END)               AS tile_inst_crit,
       COUNT(CASE WHEN Percent_Used>95 THEN 1 END)                               AS modal_bases_crit,
       COUNT(CASE WHEN Percent_Used>85 AND Percent_Used<=95 THEN 1 END)          AS modal_bases_warn
FROM b;
SELECT COUNT(*) AS tile_inst_warn_only FROM (
  SELECT Instance FROM dbo.KPI_MSSQL_TLOG_USAGE_ACTIVE WITH (NOLOCK)
  WHERE Update_TS >= DATEADD(MINUTE,-1440,GETDATE()) GROUP BY Instance
  HAVING MAX(CASE WHEN Percent_Used>95 THEN 1 ELSE 0 END)=0 AND MAX(CASE WHEN Percent_Used>85 THEN 1 ELSE 0 END)=1) x;

-- (b) prova do JOIN: formato de Instance nas 4 fontes + cobertura do último log backup / recovery model
SELECT TOP 25 t.Instance, t.[Database], t.Percent_Used, ds.Recovery_Model,
  (SELECT MAX(Last_Backup_Date) FROM dbo.KPI_MSSQL_BACKUPS_STG b WITH (NOLOCK)
    WHERE UPPER(b.[Database])=UPPER(t.[Database]) AND b.Backup_Type IN ('L','LOG') AND UPPER(b.Instance)=UPPER(t.Instance)) AS last_log_same_node,
  (SELECT MAX(Last_Backup_Date) FROM dbo.KPI_MSSQL_BACKUPS_STG b WITH (NOLOCK)
    WHERE UPPER(b.[Database])=UPPER(t.[Database]) AND b.Backup_Type IN ('L','LOG')) AS last_log_any_node,
  (SELECT COUNT(*) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG a WITH (NOLOCK)
    WHERE UPPER(a.Instance)=UPPER(t.Instance) AND UPPER(a.[Database])=UPPER(t.[Database]) AND a.AgName IS NOT NULL) AS ag_rows
FROM dbo.KPI_MSSQL_TLOG_USAGE_ACTIVE t WITH (NOLOCK)
LEFT JOIN dbo.KPI_MSSQL_DB_SETTINGS_STG ds WITH (NOLOCK)
       ON UPPER(ds.Instance)=UPPER(t.Instance) AND UPPER(ds.Database_Name)=UPPER(t.[Database])
WHERE t.Percent_Used>85 AND t.Update_TS >= DATEADD(MINUTE,-1440,GETDATE())
ORDER BY t.Percent_Used DESC;

-- (c) valores distintos de Backup_Type (esperado: D / I / L)
SELECT DISTINCT Backup_Type FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK);
```

**Como ler:** `tile_inst_crit` = número do tile "Instâncias c/ t-log crítico";
`modal_bases_crit` = cabeçalho do modal crítico ("M base(s) críticas");
`modal_bases_warn` = cabeçalho do modal de aviso; `tile_inst_warn_only` = tile
de aviso. Em (b): se `Recovery_Model` vier NULL em muitas linhas → JOIN ao
DB_SETTINGS falha por formato de `Instance` (dizer-me: normalizo mais). Se
`last_log_any_node` > `last_log_same_node` com `ag_rows` > 0 → o AG-aware está
a fazer falta (esperado em AG). Em (c): se aparecer algo além de D/I/L, dizer-me.

## 2. Depois de `Restart-Service` do V33 (8433) + hard refresh

- [ ] Tile "Instâncias c/ t-log crítico" = `tile_inst_crit`; abrir → cabeçalho "M base(s) críticas em N instância(s)" com M = `modal_bases_crit`, N = `tile_inst_crit`.
- [ ] Cards mostram **nome da base** à cabeça (`base @ instância`), % usado colorido, usado/tamanho GB, último backup de log (ou "sem backup de log registado" / "N/A (recovery SIMPLE)"), Recovery, Snapshot.
- [ ] Charts lado a lado: ambiente × "Último backup de log"; clicar num ambiente reconta o chart de idade e vice-versa; Total dos dois = cabeçalho.
- [ ] Combobox de instâncias: Aplicar/Limpar filtra e os totais seguem.
- [ ] Expandir um card: "Detalhe completo do registo" mostra os campos por base (sem Base_Key/Threshold_*).
- [ ] Drilldown "Clique para abrir o Log Space desta base no SQL Diagnostics": abre a instância e o filtro da tabela fica com o nome da base.
- [ ] Modal de aviso: mesmo padrão; M = `modal_bases_warn`.
- [ ] Regressão: modal **Backup Delayed** continua com combobox, cross-filter e os mesmos números de ontem.
- [ ] Tema claro / escuro / alto contraste; 1366×768; consola sem SyntaxError/ReferenceError.

Reportar: os 5 números de (a), qualquer linha estranha de (b)/(c), e os itens
da checklist que falharam (com print).

**Resultado 02/09 (owner):** (a) rows_fresh 1082 · tile_inst_crit 5 ·
modal_bases_crit 16 · modal_bases_warn 7 · tile_inst_warn_only 1 — portal
confirmou (Nunca 13 + Atrasado 2 + OK 1 = 16). Commit `53fee46`. JOIN validado
(Recovery_Model em 23/23; Backup_Type L/D/I).

## 3. Drill-down "Diagnóstico de Transaction Log" (parte 2, após novo commit + restart)

- [ ] No modal TLOG, clicar "Diagnosticar o log desta base…" num card: abre a modal "Diagnostico de Transaction Log" (mesma casca do mirroring), com 6 tiles (Log usado, log_reuse_wait, Último backup de log, Transação mais antiga, Runway, Triagem).
- [ ] Caso **SQLHDSQLT301_I02 / MSS10_QLT_CONTENT_Admin** (99,8 %, FULL, sem log backup): Triagem = CADEIA PARADA; problema "Recovery FULL sem NENHUM backup de log registado" (crítico); recomendação 1 = religar job de log backup com T-SQL de verificação e `-- BACKUP LOG` comentado; VLFs no painel (ou "n/d" se < 2016 SP2).
- [ ] Caso **SQLHDSPRD214_I01 / DBADashDB** (AG): painel "HA" mostra AG/role/estado; Último backup de log OK.
- [ ] Caso **SQLHDSTST023_I01 / ReportServer** (log backup 30/06): Triagem CADEIA PARADA com "parado há N h" e limiar do registry (2 h).
- [ ] "Copiar T-SQL" copia; "Evidência técnica" mostra tabelas (transações abertas, backups 3d, log por dia, volume, errorlog); "Dados brutos" JSON.
- [ ] Painel lateral tem a linha "Intelligence (última coleta): X% às HH:MM · log backup: NEVER/LATE/OK (live Y%, ±pp)".
- [ ] "Não recolhido": esperado `errorlog (xp_readerrorlog)` se a conta não tiver GRANT (Msg 229) — **dizer-me o que apareceu** (sonda viva pedida pelo v33-specialist).
- [ ] Uma instância **2012/2014** da frota: modal abre, painel VLFs = "n/d (SQL < 2016 SP2 ou sem acesso)", sem erro.
- [ ] Refresh (ícone) recarrega; maximizar; Esc fecha; tema claro/escuro; consola sem erros.
- [ ] Regressão: drill de **Mirroring** continua a abrir a partir do card de mirroring.
- [ ] Tempo de abertura: < 45 s no pior caso (errorlog grande); se passar disso, dizer-me qual o bloco em "Não recolhido".

## 4. Layout do mockup + capacidade efectiva (parte 3, após commit + restart)

- [ ] Cabeçalho da modal: "Diagnostico de Transaction Log — <base>" à esquerda; à direita "Gerado em … | Próxima atualização em 04:59" a contar; ao chegar a 00:00 recarrega sozinho; fechar a modal pára o contador.
- [ ] Badge "CRÍTICO · 3 crítico(s) · desde dd/mm/aaaa hh:mm:ss" (DBADashDB: último log backup + 1 h).
- [ ] Tile "Log usado": 96,x % e sub "… · 37% do limite efectivo (74.4xx MB)"; cor **laranja** (aviso) se o disco aguentar. Problema "Ficheiro de log a 96,x %" em aviso com "limite efectivo a 37%".
- [ ] Banner "DIAGNÓSTICO PRINCIPAL": "CADEIA DE BACKUP DE LOG INTERROMPIDA", cadeia FULL → Backup de log atrasado (7,x h) → LOG_BACKUP → Log nao trunca → Crescimento continuo → Risco de erro 9002; caixa RISCO "CRÍTICO" + "Ja ocorreram 17 evento(s) de erro 9002…" + botão "Ver eventos →" que abre e faz scroll à secção Errorlog.
- [ ] Três colunas: "O que fazer" (3 cartões numerados, Impacto/Esforço rotulados, chevron abre o T-SQL, "Ver todas as recomendações (N) →" mostra as restantes); "Porque (resumo…)" em linhas com ponto colorido e "Ver detalhes dos problemas →"; "Contexto do log" à direita com "Limite efectivo".
- [ ] Rodapé: "Evidência técnica (n)", "Histórico de backups (n)", "Eventos relacionados (Errorlog) (17)", "Dados brutos (JSON) (1)" — abrem/fecham com chevron.
- [ ] Mirroring: mesma estrutura (banner "MIRRORING SUSPENDED — LOG DO PRINCIPAL NAO TRUNCA", "desde" só se houver 'suspend' no errorlog).
- [ ] Export HTML mantém o layout novo (banner + cadeia + secções abertas).
- [ ] 1366×768: 3 colunas ainda cabem; ≤ 1280 px colapsa para 1 coluna. Tema claro. Consola limpa.

## 5. Mirroring no 2.º mockup (após commit + restart)

- [ ] Abrir o drill de Mirroring (SharePoint2010_Config_PROD): cabeçalho "SQLHDSPRD302\I01 (Principal) → SQLHDSPRD301\I01 (Mirror)" e sub "Recuperação: FULL • Database: …".
- [ ] 4 tiles com ícone à esquerda: MIRRORING SUSPENDED · LOG PRINCIPAL 100 % (52,2 GB / 52,2 GB) · FILA PARA O MIRROR 111,3 GB · PROTEÇÃO HA DEGRADADA.
- [ ] Banner: headline "MIRRORING INTERROMPIDO ESTÁ IMPEDINDO A REUTILIZAÇÃO DO TRANSACTION LOG", parágrafo, 4 cartões da cadeia com setas, nota "O Principal permanece ONLINE…"; painel "RISCO ATUAL" com 6 factos coloridos e sub-cartão "Volume do log: … GB livres (…%)".
- [ ] 3 colunas: "O que fazer agora" (Proteger o Principal / Identificar a causa da suspensão / Recuperar o Mirroring; "Ver plano completo de ações →" ↔ "Ver menos"), "Estratégia sugerida (heurística)" (Rebuild… / Send Queue / Tamanho da base / Relação 16,0x / "Ver runbook de rebuild →" abre a secção), "Contexto rápido" (11 linhas do modelo; "Ver detalhes completos →" abre modal com tudo).
- [ ] Rodapé em 2 colunas: Estado detalhado do Mirroring (linhas clicáveis → detalhe) · Errorlog (Principal / Mirror) · Filas e performance | SQL de diagnóstico · Runbook de rebuild (re-seed) · Dados brutos (JSON).
- [ ] Badge "CRÍTICO · desde …" só se houver 'suspend' no errorlog (sem GRANT em xp_readerrorlog fica sem "desde" — dizer-me).
- [ ] Export HTML mantém o layout; modal não maximizada colapsa para 2/1 colunas.
