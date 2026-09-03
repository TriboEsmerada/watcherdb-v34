# PLANO — Melhoria do KPI Mirroring (sessão de 2026-09-01)

Base: wave de 31/08 (Witness + filas em produção, commits 5278f08/4ccedbc) +
colheita do script MirrorRebuild do owner (FIND-20260831-104,
docs/context/SCRIPT_MIRROR_REBUILD_FASE0_2026-08-31.sql) + incidente
SharePoint (fila 101 GB vs dados 6,8 GB).

## Regra 0 (obrigatória, ANTES de código)
Dispatch `watcherdb-v1-intel-specialist` — perguntas concretas já preparadas:
1. Fase A usa só leitura cruzada de views existentes (mirroring DET_VIEW +
   DATAFILES agregado) — confirmar que o JOIN não fere contratos nem
   performance do modal (DATAFILES é grande; agregar por Instance+Database).
2. Fase B precisa de HISTÓRICO da fila: existe HIST archiving para o KPI de
   mirroring? Se não: mini-tabela `WDB_MIRRORING_QUEUE_HIST` (Instance,
   Database, Log_Send_Queue_KB, Update_TS; retenção 7d; escrita pelo próprio
   collector no fim do store) — VETO dele decide o desenho.
3. "Suspenso desde": persistir first-seen do estado problemático — mesma
   mini-tabela ou coluna nova? Alternativa barata sem schema: derivar da HIST.
4. Fase C: sys.database_mirroring_endpoints exige que permissão para o
   sql_monitoring? (VIEW ANY DEFINITION?) Se exigir GRANT novo → FORA
   (regra: sql_monitoring é SELECT-only, sem grants novos).

## Fase A — Veredito RESUME-vs-REBUILD no modal (core de amanhã)
Heurística do script do owner, VALIDADA ao vivo a 31/08 com os nossos KPIs
(fila 103.666 MB > dados 6.989 MB → REBUILD; a heurística corrigiu a
recomendação humana anterior, que era RESUME):

    fila_kb > data_mb * 1024  →  "REBUILD (fila > dados — re-seed é mais
                                  rápido que drenar)"
    caso contrário            →  "RESUME pode bastar (fila < dados)"

- Backend (`intelligence_kpis.py`, branch mirroring): LEFT JOIN agregado ao
  DATAFILES (`SUM(Size_MB) WHERE File_Type='ROWS'` por Instance+Database) →
  campo `Data_MB` no payload. Fail-open: sem DATAFILES → sem veredito.
- Frontend (cartão do modal): linha "Veredito" só quando SUSPENDED/
  DISCONNECTED e com os DOIS números por extenso (regra modais nome-não-
  -número): "REBUILD — fila 101,2 GB > dados 6,8 GB". Nada de veredito em
  bases saudáveis.
- Nota de honestidade no tooltip: veredito é heurística de triagem, não
  ordem — o runbook (script do owner) é a via de execução.

## Fase A2 — Drill-down de diagnóstico enriquecido (pedido owner 31/08)
O drill "Diagnosticar este mirroring" (link do cartão, layout Diagnóstico de
17/08 — portal ~:38075, data-mirror-diag-*) foi desenhado quando o KPI só
tinha state/role/partner. Agora há muito mais — o drill passa a contar a
história completa do espelho num só ecrã:

- **Secção "Estado do espelho"**: Mirroring_State + Safety (FULL sync / OFF
  async por extenso) + Witness (estado, ou "nenhum — failover manual" em
  FULL) + papel e parceiro (já existia).
- **Secção "Transporte"**: Log por enviar + Redo no mirror (unidade humana,
  vermelho > 1 GB) + veredito da Fase A com os números; com Fase B, a
  tendência (crescer/drenar MB/h + "suspenso desde").
- **Secção "Impacto no principal"**: t-log da base (Size/Used do DATAFILES
  File_Type='LOG' — o caso vivo: log 101 GB / 99,9% por causa da fila) +
  drive onde vive (ligação mental ao KPI de disco).
- **Secção "Próximos passos"**: texto accionável derivado do veredito
  (RESUME: comando de referência; REBUILD: apontar ao runbook MirrorRebuild
  do owner — docs/context/SCRIPT_MIRROR_REBUILD_FASE0_2026-08-31.sql) —
  consultivo, nunca botão de execução.
- Fontes: TUDO já recolhido (mirroring DET_VIEW + DATAFILES + disco); zero
  recolha nova nesta fase. Endpoint/RC4 só se a Fase C entrar.
- Gate visual: `/design-review` rápido ou parecer do frontend-specialist
  sobre o layout Diagnóstico (padrão existente de secções), + browser test
  no caso vivo.

## Fase B — Tendência da fila + "suspenso desde" (se v1-intel aprovar desenho)
- Fila com histórico → modal mostra "a crescer ~X MB/h desde <data>" ou
  "a drenar ~X MB/h, ETA <estimativa>". É a diferença entre ver um número e
  ver um filme. Depende da resposta 2/3 do specialist; se exigir schema novo,
  segue o playbook migration standalone (o de 31/08, com a lição env-slot e
  o diff sys.sql_modules vs canonical ANTES de qualquer DROP/CREATE).

## Fase C — Config smells do endpoint (opcional, só se permissão já existir)
- `encryption_algorithm_desc` (RC4 deprecated — caso real do incidente) e
  witness ausente em safety FULL como linhas de "configuração a rever" no
  drill de diagnóstico. Se exigir GRANT novo: cortar sem pena.

## Gates e fecho
- tier checker (tudo Std — leitura/apresentação); browser test do modal
  (caso vivo SharePoint = REBUILD visível; base saudável = sem veredito).
- Commits + prompt V6 explicado (portal V6 grep-first; contrato NULL≠0
  mantém-se).
- Wave-close ÚNICO para 31/08 + 01/09: specialists (v1-intel + v33) ganham
  a secção mirroring completa, KB/Nestor, CHANGELOGs — fechar tudo junto.

## Fora de scope (não misturar)
- FINDs 101/103 (signal-vs-noise do Backup Delayed) — wave própria.
- Fases 1-6 do pacote MirrorRebuild — pista de OPERADOR (runbook, ingestão
  na KB via core-librarian com os 5 gates), nunca collector.
- FIND-102 (assert identidade pós-connect) — wave própria de resiliência V1.

## Validação final de amanhã
1. Modal SharePoint: veredito REBUILD com os números; restantes 109 bases
   espelhadas: zero veredito (não são problema).
2. Drill-down (Fase A2) no caso vivo: as 4 secções contam a história inteira
   — estado, transporte (101 GB), impacto no t-log do principal, próximos
   passos — sem precisar de SSMS para a triagem; numa base saudável o drill
   degrada limpo (sem veredito, sem alarme).
3. Se Fase B entrar: tendência coerente com 2+ ciclos observados.
4. Contagens do card/painel INALTERADAS (nada disto mexe em contagem).
