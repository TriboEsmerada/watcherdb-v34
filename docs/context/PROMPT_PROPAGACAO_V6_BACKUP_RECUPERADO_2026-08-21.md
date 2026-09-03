# Propagação V6 — lote 2026-08-21 (KPI Backup Failed "recuperado" + UI navbar + lição SCM)

> Para a AI da sessão V6. V6 partilha a BD WatcherDB_Intelligence com o V3.3
> (mesmas STG), mas o BACKEND e o PORTAL V6 são código próprio e o portal V6
> NÃO é superset do V3.3 — grep de âncoras ANTES de assumir que a feature existe.
> Commits V3.3 de referência: `b13a7e2` (KPI), `f6a15c0` (UI), + `f343453`/`d8e233f`
> (limpeza navbar posterior, sessão paralela).

## 1. KPI Backup Failed — semântica nova (REGRA, não só diff)

**Problema que o V6 herda por ler as mesmas tabelas:** as falhas de job em
`KPI_MSSQL_BACKUP_EXEC_FAILURES_STG` com `Failure_Source='sysjobhistory'` têm
`Database=NULL` por desenho do collector (falha é job-level). Qualquer lógica
"resolvido por backup posterior" baseada em (Instance, Database, Type) NUNCA
dispara para elas — a falha só sai do KPI quando envelhece para fora da janela
de 7d do collector. Medição 21/08 em PRD: **76% do tile era ruído já
recuperado**; e um job com cadência >7d que falhe e nunca recupere desaparece
ao 7.º dia (falso-verde).

**Contrato da correcção (Fase 1, opção E do council de 21/08):**
- Recuperado ⇔ o MESMO job (`JobId` + `Instance`) tem execução posterior com
  SUCESSO: `KPI_MSSQL_AGENT_JOBS_STG.LastRunStatus='Succeeded'` **E**
  `LastRunDate > Run_Datetime` da falha. `>` estrito: `LastRunDate` é o INÍCIO
  do run, logo um run continue-on-error (job "sucesso" com step de backup
  falhado no mesmo run) NÃO conta como recuperação.
- JOIN normalizado obrigatório: `AGENT_JOBS_STG.Instance` é `@@SERVERNAME` cru
  (backslash); `EXEC_FAILURES.Instance` é underscore → `REPLACE` no ON.
- **Fail-open**: se o snapshot de AGENT_JOBS estiver stale (`Update_TS` > 15
  min = 3× a cadência de 5 min do collector) → NÃO marcar nada como
  recuperado. Nunca esconder falhas com base em dados velhos.
- **Tile conta só "ainda em falta"; recuperados NÃO desaparecem** — ficam no
  drill-down com selo "Recuperado ✓ <data>" (decisão DBA persona: nunca
  desaparecimento silencioso; rasto de auditoria).
- **Paridade card==modal por construção**: um único helper usado nos dois
  paths (V3.3: `api/routers/intelligence/helpers.py::backup_job_failure_recovered`).
  Não dupliques a lógica — a classe de bug card≠modal já custou 3 waves no V3.3.
- Rótulos/help passam a declarar a janela ("falhas dos últimos 7 dias") e a
  semântica de recuperação.

**Âncoras V6 a grep primeiro:** onde o V6 lê `KPI_MSSQL_BACKUP_EXEC_FAILURES_STG`
(card e drill-down), se já faz JOIN a `KPI_MSSQL_AGENT_JOBS_STG`, e se o portal
V6 sequer tem os tiles Full/Diff/Log falhou separados (pode ter um só card).
Se o V6 não expõe este KPI no portal, a mudança é só backend/API.

**Rejeitados pelo council (NÃO reintroduzir):** janela configurável pelo
utilizador (2 sintomas puxam em direcções opostas; anti-pattern config 25/05);
parse de `Database` do comando do step (VETO v1-intel — Ola Hallengren/TDP não
parseáveis; contaminaria a STG partilhada com falsos "recuperados").

**Fase 2 (futura, no V1 — beneficia V6 automaticamente):** coluna
`Resolved_By_Success_TS` no collector + janela 7d→30d. Quando entrar, a
lógica acima simplifica para `WHERE Resolved_By_Success_TS IS NULL` (manter
fail-open). O V6 será avisado por novo lote.

## 2. i18n (se o portal V6 tiver o drill-down)

5 chaves novas em `kpi_modal.*` (pt/en/es): `recovered_at` ("Recuperado -
sucesso a {when}"), `still_missing` ("AINDA EM FALTA"), `still_missing_count`,
`recovered_count`, `stale_no_verdict`. Ver `static/i18n/*.json:867-871` no V3.3.

## 3. UI — Collectors/Mutes da navbar para o dropdown do utilizador

Pedido do owner (21/08): itens "Collectors" e "Mutes" saem da navbar e entram
no dropdown do avatar, entre "KPIs" e "Alterar Senha", visíveis a `dba||admin`
por condicional no template do dropdown (NÃO usar o toggle `data-dba-gated` —
força `display:flex` inline e sobrepõe o CSS de `.profile-menu-item`).
Bónus obrigatório: o guard client-side dentro de `openCollectorsModal`/
`openKpiMuteModal` estava `admin`-only e contradizia o backend `_require_dba`
(dba OU admin, decisão owner 16/08) — alinhar para `dba||admin`. Verificar se
o portal V6 tem estes botões de todo (grep `openCollectorsModal`) antes de
propagar; a sessão paralela removeu ainda o botão "Control" redundante da
navbar (`f343453`, `d8e233f`) — replicar a intenção (navbar mínima, gestão no
dropdown), não o diff literal.

## 4. LIÇÃO OPERACIONAL (aplica-se ao V6 já)

Remoção de `services/web_service` no V3.3 (20/08) partiu o boot do serviço no
1.º restart: o registry SCM (`PythonClass`) apontava para o módulo removido —
dependência invisível ao grep de imports. E o wrapper novo mudou o contrato de
serving (TLS do config.yaml → env vars) sem ninguém notar até o browser
rejeitar. **Regra para qualquer cleanup de código de serviço no V6:**
1. verificar `sc qc` + `PythonClass`/`ImagePath` dos serviços WatcherDB;
2. paridade de contrato (porta, esquema http/https, auth) entre wrapper velho
   e novo — healthz 200 NÃO chega;
3. restart de validação na MESMA sessão, ou pendência escrita no diário.
Precedente completo: SOLUCOES.md V3.3, linha 2026-08-21.
