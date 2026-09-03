# PROPAGAÇÃO V6 — lote de 29–30/07 (backups, agendamentos e cobertura)

> Plano explícito, incluindo o que **herda via BD** e por isso não precisa de código.
> Origem: sessão 2026-07-29/30 em V3.3 + V1. Commits `7e9c0fd`, `50b89e9`, `ed1f737`.

## 0. O que mudou na BD partilhada — resposta curta: **nada**

**Não houve DDL neste lote.** Não é preciso tocar no `INSTALACAO_COMPLETA_UNIFICADA.sql`.

O que mudou foram **duas queries de leitura** nos collectors V1. As tabelas, colunas e
tipos ficaram exactamente iguais. Confirmação para quem quiser verificar sem confiar:

| Ficheiro | O que mudou | Esquema? |
|---|---|---|
| `collect_agent_jobs.py:91` | `HasSchedule` passa a exigir `sysschedules.enabled = 1` | Não — coluna já existia |
| `scripts/collectors/collect_backup_jobs_disabled.py:87` | `WHERE` passa a incluir jobs activos sem agendamento ligado | Não — só o filtro |

**Mas há uma mudança de significado que tem de ser propagada como conhecimento**,
porque não se vê no esquema:

> `HasSchedule = 1` deixou de significar *"tem uma linha de agendamento"* e passou a
> significar *"tem um agendamento que dispara"*. Um consumidor que dependesse da
> semântica antiga passa a ver menos `1`s. Verificado: no V3.3 não há consumidor que
> dependa disso. **Por verificar no V6.**

E o KPI `backup-jobs-disabled` **passa a contar mais**, por deixar de sub-reportar.
Não é regressão; é o número a ficar correcto. Quem comparar séries históricas vai ver
um degrau na data do deploy.

## 1. Herda via BD — sem código no V6, mas com verificação

O V6 lê a **mesma** `WatcherDB_Intelligence`. Os dois fixes correm no collector V1,
que é único para toda a família. Portanto o V6 recebe os dados corrigidos **sem
qualquer alteração**, assim que o serviço do collector for reiniciado.

**A verificar antes de dar por herdado** — é aqui que este plano existe, em vez de se
assumir:

1. O V6 tem cópia própria de `collect_agent_jobs.py` ou de
   `collect_backup_jobs_disabled.py`? Se tiver, **não herda** — precisa do mesmo diff.
   ```powershell
   cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V6"
   Get-ChildItem -Recurse -Filter 'collect_agent_jobs.py'
   Get-ChildItem -Recurse -Filter 'collect_backup_jobs_disabled.py'
   ```
2. Algum sítio do V6 lê `HasSchedule` e assume a semântica antiga?
   ```powershell
   Select-String -Path . -Pattern 'HasSchedule' -Recurse
   ```
3. O V6 tem texto de ajuda ou documentação do KPI `backup-jobs-disabled` que diga
   *"jobs desactivados"* sem mencionar o caso do agendamento? Se tiver, é a mesma
   correcção de texto que se fez no V3.3 (ver §2).

## 2. Propagar para o V6 — portal

⚠️ **Regra do projecto:** o portal V6 é **subconjunto** do V3.3, não superset.
Fazer `grep` das âncoras **antes** de assumir que o alvo existe.

### 2.1 Linha "Backup danificado" só quando > 0

**V3.3:** `templates/watcherdb_portal.html:33990` — `_advRow(...)` passou a
`(cond ? _advRow(...) : '')`.

**Âncora a procurar no V6:** `is_damaged_count`.

- Se **não existir**: o V6 nunca separou o `is_damaged` do `no_checksum` (separação
  de 28/07, também V3.3). Nesse caso a propagação é maior do que uma linha — é o
  lote de 28/07 que ainda não foi lá. Verificar primeiro.
- Se **existir**: aplicar o mesmo padrão condicional.

**Fundamento a levar junto**, porque sem ele a alteração parece arbitrária:
`backupset.is_damaged = 1` exige `BACKUP WITH CHECKSUM` para haver detecção **e**
`WITH CONTINUE_AFTER_ERROR` para o backup não falhar — duas opções de intenção
oposta. Logo `0` não quer dizer "backups sãos"; quer dizer "nada foi apanhado onde a
detecção se aplica". Com 1153 bases sem checksum na frota, a maioria do parque está
fora do alcance da métrica. Um zero verde sobre população não medida é mentira.

**Critério geral extraído** (útil para lá do backup): esconder o zero quando a medição
só cobre um subconjunto; manter o zero quando a população foi toda medida.

### 2.2 Documentação do KPI `backup-no-checksum` e `backup-failed`

**V3.3:** 10 sítios em `50b89e9` (PT + EN) e 5 em `ed1f737` (ES).

**Âncoras:** `'backup-no-checksum'` e `'backup-failed'` no registo de documentação.

O que estava errado e é o mesmo em qualquer edição que tenha herdado o texto antigo:
as descrições afirmavam que **backupsets danificados estão contados no "sem
checksum"**. Deixou de ser verdade a 28/07. Três sítios por idioma:

1. `description` do `backup-no-checksum` — sai a menção a danificados
2. `howItWorks[0]` — a query lê as duas fontes, mas o KPI conta só `no_checksum`
3. `howItWorks[2]` (bullet do `is_damaged`) — passa a dizer que **não** entra
4. `thresholds` / `conditions` — sai "ou danificado" e "e sem danos"
5. `description` do `backup-failed` — o ponteiro passa a distinguir os dois casos

⚠️ **Verificar os três idiomas.** No V3.3 o espanhol ficou duas horas a afirmar o
contrário do PT/EN porque se assumiu que a entrada só tinha `en`. São **29 entradas
com `es`** — a paridade existe e tem de ser mantida.

### 2.3 Documentação do KPI `backup-jobs-disabled`

**V3.3:** 11 sítios em `ed1f737` (texto de ajuda + PT + EN + ES).

Passa a dizer: conta jobs com `enabled = 0` **ou** activos com todos os agendamentos
desligados. O título ficou **intacto** de propósito — renomear o KPI é decisão de
produto em aberto, não correcção de documentação. Manter a mesma decisão no V6.

## 3. Já identificado, ainda não implementado em lado nenhum

`FIND-20260729-106` — **`Avg Livre` é média não ponderada**. `AVG(Percent_Free)` dá o
mesmo peso a um volume de 2 TB e a um de 100 GB. Caso medido: card a mostrar
`Avg Livre 51,2%` ao lado de `Livre 616,6 GB / 2774,9 GB` (= 22,2%) — **os dois
números contradizem-se na mesma linha**, e o utilizador questionou um alerta
CRÍTICO que estava correcto.

**O V6 tem o mesmo defeito, e o sítio está localizado:**
`WATCHERDB_V6/api/routers/intelligence_kpis.py:2883` — mesmo `AVG(Percent_Free)`.

Decisão tomada com o owner: **remover**, não corrigir. Ponderado passaria a 22,2%,
idêntico ao `Livre: X / Y GB` já exibido — redundante. Não ponderado é enganador. Não
há versão útil. No lugar, mostrar **qual** é a drive crítica e quanto lhe resta, que é
a regra de "nome accionável em vez de número solto".

Fundamento a registar na doc dos dois lados: **espaço livre não é fungível entre
volumes** — o SQL Server não usa folga da drive G para um ficheiro que vive na F. Por
isso o agregado nunca deve competir em destaque com o mínimo.

## 4. Ordem sugerida

1. **Verificações do §1** — decidem se há trabalho de código ou se herda mesmo
2. **§2.2 e §2.3** (documentação) — corrigem afirmações falsas; é o mais urgente,
   porque documentação errada leva a decisões erradas com confiança
3. **§2.1** (linha condicional) — só depois de confirmar que o V6 tem `is_damaged`
4. **§3** (`Avg Livre`) — nos dois lados no mesmo lote, para não divergirem outra vez

## 5. Gates

- `watcherdb-v1-intel-specialist` — **em dívida**. O fix de `7e9c0fd` tocou infra
  partilhada sem parecer prévio. Pedir a posteriori, nem que seja para confirmar que
  nenhum consumidor depende da semântica antiga do `HasSchedule`.
- `v33-feature-matrix-checker` — Std puro neste lote, mas a regra é correr sempre.
- Validação: `node --check` nos blocos `<script>` do portal (baseline V3.3: 12/12) e
  `ast.parse` em qualquer ficheiro Python tocado.
