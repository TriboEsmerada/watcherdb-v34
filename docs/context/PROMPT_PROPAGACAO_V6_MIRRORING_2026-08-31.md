# PROMPT PROPAGACAO V6 — KPI Mirroring: Witness + Filas (2026-08-31)

Colar numa sessao V6. Regra: V6 herda a BD partilhada (as colunas novas chegam
"de graca" via view), mas o portal V6 NAO e' superset — grep anchors ANTES.

## O que mudou (e porque)

Incidente 31/08: SharePoint2010_Config_PROD SUSPENDED no principal
SQLHDSPRD302\I01 com ~100 GB de Log Send Queue — o KPI mostrava so
state/role/partner; a severidade real (disco do principal a encher) era
invisivel. Fase de dados fechada em V1 (commit "feat(v1 intel): KPI Mirroring
- Witness + Log Send/Redo Queue no collector"):

- `KPI_MSSQL_MIRRORING_STATUS_STG*`: +4 colunas NULL — `Witness_Name`,
  `Witness_State`, `Log_Send_Queue_KB`, `Redo_Queue_KB`.
- Views `_ACTIVE` e `_DET_VIEW` RECRIADAS com as colunas (NAO eram SELECT * —
  se a tua copia V6 do canonical tiver as views antigas, o refresh nao chega).

## Contratos para a AI de la'

1. **Filas: NULL = "sem dado"; 0 = "sem backlog" (valor real).** NUNCA
   coalescer NULL para 0 em queries nem em JS (`|| 0` proibido nestes campos)
   — 0 por omissao mascara exactamente o incidente que motivou isto.
2. Witness so' existe em safety FULL; "FULL sem witness" = failover manual —
   o V3.3 mostra isso por extenso no cartao do modal. Threshold visual:
   vermelho quando fila > 1 GB (1048576 KB) — mesmo limiar do WARNING que o
   collector agora loga.
3. A ordem de deploy ja' foi cumprida no shared (migration + collector); o V6
   so' precisa de mexer no SEU consumo. Se o V6 ler a view com SELECT
   explicito de colunas, acrescentar as 4; se for SELECT *, nada a fazer no
   SQL.
4. Portal V6: grep por "mirroring" / "Mirroring_State" / "Partner_Instance"
   nos templates. Se o V6 nem tem modal de mirroring, reportar "nao aplicavel
   no portal" e fechar so' com a nota de que a BD ja' expõe os campos.
5. Referencia de implementacao V3.3 (adaptar aos anchors V6, nao copiar cego):
   backend `api/routers/intelligence_kpis.py` (branch mirroring/-total/-issues,
   +Safety_Level/Witness_State/filas no SELECT), frontend cartao do modal
   (linha Safety/Witness/filas com formatter KB→MB/GB, so' renderizada quando
   o payload traz os campos — degrada bem).

## Canonical V6 (regra 2 do owner — obrigatorio nesta sessao V6)

O V6 mantem COPIA propria do canonical de instalacao. Sincronizar com o commit
V1 `5278f08`: SECTION16_MIRRORING_STATUS.sql (ou secção equivalente no
INSTALACAO V6) ganha as 4 colunas nas 7 CREATE TABLE + as 2 views recriadas
com as colunas nos 6 branches. Sem isto, um fresh install V6 cria schema
divergente da BD viva (precedente FIND-20260810-101 — canonical vs frota).

## Validacao V6

SELECT na `_DET_VIEW`: a linha SUSPENDED deve trazer Log_Send_Queue_KB > 1e8
(enquanto o incidente durar). No portal V6 (se aplicavel): modal mostra a fila
em GB a vermelho.
