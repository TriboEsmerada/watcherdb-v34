# Plano — caminho de menor privilégio para os servidores monitorizados

Data: 2026-08-20 · Estado: **AGUARDA GO DO OWNER** · Bloqueador nº 1 de aceitação bancária

## O problema, numa frase

O produto liga-se aos SQL Servers **monitorizados do cliente** sempre com Windows
Auth (`Trusted_Connection=yes`), hardcoded, obrigando a conta de serviço a ter
permissões amplas em toda a frota. É o achado que um CISO de banca bloqueia à
cabeça — viola a Regra de Ouro #2 no produto que sai para o cliente, não só na
Intelligence (esse foi o P-05, já corrigido).

## O que a consulta ao sql-deep-reviewer estabeleceu

**Boas notícias, verificadas na fonte:**

1. **Nada exige `sysadmin` nem `xp_cmdshell`.** As referências a `xp_cmdshell`/
   `DBCC INPUTBUFFER` no código são texto de recomendação, não são executadas.
2. **Religar é um branch num único ponto** — [connection_pool.py:325](../../api/connection_pool.py#L325),
   onde `get_connection` faz hardcode do builder Windows Auth. Os caminhos sync
   e async convergem aqui; não há duas vias para esquecer.
3. **O código morto está correcto.** `_build_connection_string_sql_auth`
   ([connection_pool.py:702](../../api/connection_pool.py#L702)) não apodreceu —
   e a password que recebe **já vem decifrada** (o helper `_decrypt` partilhado,
   exercitado pelo caminho Windows, trata o prefixo Fernet). Religar não precisa
   de tocar nesta função.
4. **O modelo de dados já suporta modo misto** — flag `use_windows_auth` por
   servidor no `servers.json` ([connection_pool.py:481](../../api/connection_pool.py#L481)).

**Inventário do que excede `db_datareader`** (privilégio mínimo por operação):

| Operação | Onde (amostra) | Privilégio mínimo |
|---|---|---|
| DMVs de servidor (`dm_exec_*`, `dm_os_*`, `dm_hadr_*`, `dm_exec_sql_text`) | todo o módulo Performance + LIVE | `VIEW SERVER STATE` |
| Error log | `live_monitoring.py:904/914`, `mirroring_diagnosis.py:97` | `EXECUTE ON sys.xp_readerrorlog` |
| Jobs + backups (msdb) | `jobs.py`, `sqlserver_kpi_service.py:559/629` | `SELECT` em msdb OU `SQLAgentReaderRole` |
| `DBCC SQLPERF(LOGSPACE)` | `mirroring_diagnosis.py:82`, `sqlserver_kpi_service.py:271` | coberto por `VIEW SERVER STATE` |
| Plano XML + Query Store | `plan_analysis.py:147/152-182` | `VIEW SERVER STATE` (cache) + `VIEW DATABASE STATE` (QS) |
| Metadata de schema | vários | `VIEW ANY DEFINITION` |

## Os três gaps entre o código e o `LEAST_PRIVILEGE_SETUP.sql`

O script canónico existe ([docs/security/LEAST_PRIVILEGE_SETUP.sql](../../docs/security/LEAST_PRIVILEGE_SETUP.sql))
e concede a base (`VIEW SERVER STATE`, `VIEW ANY DEFINITION`, `VIEW ANY DATABASE`,
`SELECT` em backup*/sysjobs*). Mas há três buracos entre o que concede e o que o
código corre — **têm de fechar antes de o piloto depender disto**:

| # | Gap | Consequência se não fechar | Fix |
|---|---|---|---|
| 1 | **`xp_readerrorlog` não concedido** (`:135` só dá `EXEC sp_help_jobactivity`, não o `xp_readerrorlog`) | error log e diagnóstico de mirroring degradam (código já cai graciosamente, mas perde-se a feature) | `GRANT EXECUTE ON sys.xp_readerrorlog` em `master` — template pronto em `WATCHERDB_V6/tools/grants/grant_xp_readerrorlog.sql` |
| 2 | **`sysjobactivity` + `syssessions` lidos mas não concedidos** (`jobs.py:338-341`, `live_monitoring.py:615-619`; o script para em sysjobs/history/steps) | a aba Jobs perde a actividade em tempo real | `SELECT` explícito nessas tabelas, ou `SQLAgentReaderRole` (cobre jobs de todos os owners — necessário, o serviço não é dono) |
| 3 | **`SHOWPLAN` mal-tierado** — está em `[TIER: PRO]` (`:167`) mas `plan_analysis.py` corre em V3.3 **Standard** | análise de plano degrada em Standard | mover `SHOWPLAN` para a secção Standard, ou aceitar degradação documentada; Query Store precisa ainda de `VIEW DATABASE STATE` por BD |

## A recomendação (sql-deep-reviewer, subscrita pelo consultor)

**Modelo híbrido**, que o código já suporta nativamente:

- **Default = SQL Auth `sql_monitoring` least-privilege** — com o
  `LEAST_PRIVILEGE_SETUP.sql` corrigido dos 3 gaps. A conta de serviço Windows
  deixa de precisar de dbo em toda a frota.
- **`use_windows_auth:true` por servidor como excepção documentada** — para
  instâncias onde o cliente recuse conceder o `GRANT EXECUTE ON xp_readerrorlog`.
  Nesses, o error log / mirroring caem graciosamente. O flag já existe.

Nenhum item força privilégio alto. O único que sai de `VIEW SERVER STATE` +
`SELECT` msdb é o `xp_readerrorlog`, e resolve-se com **um** GRANT granular
read-only (não é `xp_cmdshell`, não dá sysadmin).

## Plano de execução — por fases, com pontos de paragem

**Nada abaixo é feito sem GO. Cada fase é um ponto de decisão.**

### Fase 0 — corrigir o script SQL (documento, zero risco de produção)
Fechar os 3 gaps no `LEAST_PRIVILEGE_SETUP.sql`. É SQL de GRANT, não é código de
produto. O owner revê e corre num servidor de teste. **Reversível** (REVOKE).

### Fase 1 — religar o caminho SQL Auth (código, risco médio)
Branch em `connection_pool.py:325`: escolher o builder conforme
`creds['use_windows_auth']` por servidor, com tratamento de `None` (fallback ou
erro explícito). A função `_build_connection_string_sql_auth` não muda.
**Risco:** muda como o produto lê **todos** os servidores. Exige:
- consenso com v33-specialist antes de aplicar (regra de ouro do projecto);
- teste com uma instância real em modo SQL Auth antes de generalizar;
- o `servers.json` populado com `use_windows_auth:false` + credencial por servidor.

### Fase 2 — validar em campo (operação do owner)
Correr o produto contra um servidor com o `sql_monitoring` least-privilege e
confirmar que cada KPI/collector lê. O que degradar identifica o GRANT em falta.

### Fase 3 — propagar ao V6 e documentar
V6 tem o mesmo hardcode. Documentar a excepção do Windows Auth no INSTALL_GUIDE.

## O que decide, e o que fica a aguardar

**A sua decisão inicial é só sobre a Fase 0 e 1.** As restantes dependem do
resultado. Recomendo:

1. **GO à Fase 0 já** — corrigir o script SQL é baixo risco e destranca o resto.
2. **Fase 1 com dispatch prévio ao v33-specialist** — é mudança de produto que
   toca na leitura de toda a frota; não a faço sem o consenso que a regra do
   projecto exige, e sem uma instância de teste.

Sem este bloqueador fechado, a resposta do banco à instalação continua NO-GO,
por muito que a assinatura e o EULA sejam resolvidos.
