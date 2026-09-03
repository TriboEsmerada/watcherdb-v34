# PROMPT — próxima sessão V3.3 (pós Wave A, sessão de 2026-07-28)

> Nome por **conteúdo**, não por data: esta sessão perdeu tempo com um prompt
> chamado `..._2026-07-29.md` que foi escrito a 28/07 *para* o dia seguinte — e a
> data do ficheiro foi tomada como a data do trabalho. Não repetir.

Cola isto numa sessão nova:

---

Lê `docs/context/CONTEXT.md` (entradas 2026-07-28) e executa em OODA, modo consultor
+ GO por lote, memórias owner activas (panorama sempre; nome-não-número; validação
node 12/12 + py ast; BD⇒canonical+docs+contrato V6; commit sempre + plano V6;
antes/depois no fecho; checkpoint antes de mudanças).

## Estado herdado — Wave A FECHADA e a funcionar

Não re-investigar. Está validado em produção:

- 3 tabelas na BD partilhada (SECAO 19 do canonical): `WDB_INSTANCE_TCP_PORT`,
  `WDB_HOST_IP_CACHE`, `WDB_PING_RESOLVER_BREAKER`. **62 instâncias** com porta e IP
  aprendidos, 0 valores inválidos, breaker nunca abriu.
- O collector aprende porta+IP na própria coleta; o ping cruza offline com o IP
  cacheado **e exige prova TCP**; o V3.3 consome tudo com cache TTL 5 min.
- 3 bugs apanhados e corrigidos: porta errada com múltiplos listeners, overflow com
  sinal acima de 32767, e a guarda anti-crash (`FIND-20260702-001`) que estava **morta
  desde 2 de Julho** por `setattr` incompatível com `pyodbc.Connection`.
- 9 commits. Plano V6 pronto em `PROMPT_PROPAGACAO_V6_WAVE_A_2026-07-28.md`.

## Prioridade 1 — Wave Cobertura, passo 0

Spec: `docs/context/WAVE_COBERTURA_SPEC_2026-07-28.md`. **Ler antes de mexer.**

O passo 0 é uma auditoria, não código: percorrer as abas por verificar e responder a
uma pergunta só — *os cartões de topo mostram uma fracção ("X de N") ou uma contagem
nua?* Contagem nua = o silêncio conflaciona "está bem" com "não medi".

- **Por verificar:** Space, Disk, Memory, CPU, Log, AlwaysOn
- **Nunca olhadas:** Performance, Encrypted, Services, Sessions, SQL Diag
- **Já auditadas, não repetir:** Security (é a **referência** — N checks, X passaram),
  Users (bom), Overview (parcial), Jobs e Backup (sem denominador)

Não automatizar por regex: já se tentou e falhou (markup heterogéneo entre abas). E não
usar contagem de vocabulário como diagnóstico — deu 2 falsos positivos em 3.

## Prioridade 2 — depois do passo 0

1. **Backups — secção de cobertura no relatório** (protegida / desprotegida / **não
   consigo medir**). Requer campo novo no `DatabaseBackupPatternAnalysis`: o produto já
   classifica a fonte da cadência (`_source_label`: sysjobs / R+8 history / inferido) mas
   despeja-a em `logger.info` e nunca sai para a API. **Não é trabalho só de frontend.**
2. **Drill do "Backup danificado"** — a linha existe no card sem clique, de propósito;
   falta endpoint filtrado por `Failure_Source='is_damaged'`. O endpoint
   `backup-no-checksum` já devolve `Is_Damaged_Count` separado.
3. **Collector V1 consumir a porta aprendida** — hoje ainda liga por `host\instância`
   (SQL Browser). Mexe no `ServerManager`, afecta **todos** os collectors: lote próprio,
   com gate `v1-intel`.
4. **Checksum no tab Backups** — decisão em aberto: o card é da frota, o tab é por
   servidor; o enquadramento tem de ser "este servidor: N bases sem checksum".

## Avisos operacionais

- **Rede instável.** A 28/07 o collector chegou a recolher 0 de 42 instâncias com
  timeouts de 60s. Se voltar, não é o código: confirmar nos logs
  `logs/collectors/inst_availability_*.log` antes de investigar produto.
- **Sessão paralela.** Existe outra sessão a trabalhar (branch `wave-b-indexacao-dmv`,
  Wave B de indexação por DMV). O `CONTEXT.md` pode ter entradas por commitar que não
  são tuas — `git status` por ficheiro antes de `git add`, nunca `add -A`.
- **Restarts:** edit em backend V3.3 ⇒ `Restart-Service` V33; edit em collector ⇒
  restart do serviço do collector. Frontend ⇒ só `Ctrl+Shift+R`.
