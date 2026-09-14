# PROPAGAÇÃO V6 — A2: disciplina dos avisos críticos e sino com histórico

> Para a AI do V6. **Verificar primeiro, assumir nunca.** Só se aplica se o portal do V6 tiver o sistema de
> avisos críticos (grep `TOAST_CRITICAL_CHECKS`, `pollCriticalKPIs`, `_toastBaselineDone`). O V6 não é
> superset do V3.4: se o sistema não existir lá, este prompt fica sem efeito.
> Origem: `docs/context/A2_AVISOS_CRITICOS_2026-09-14_apply.py` (código integral, testes, chaves).

## Os três defeitos (verificar se o V6 os tem)

| # | Sintoma | Grep que o denuncia |
|---|---|---|
| D1 | Quem abre o portal com condições críticas já activas nunca vê aviso | `_toastBaselineDone = false; // primeiro poll e silencioso` |
| D2 | Um valor que oscila (3, 4, 3, 4) dispara a cada subida | ``toastKey = `${check.key}_${currentValue}` `` |
| D3 | No ecrã de KPIs o aviso é descartado sem registo | `if (isOnDashboardKPIs()) return;` na 1.ª linha de `showCriticalToast` |

## Correcção (a mesma do V3.4)

- **Estado por condição**, `_toastLastFired`, **separado** de `_toastPreviousState` (que continua a
  alimentar o texto "3 → 4"). Dispara só se agravou face ao último valor que já disparou. **Limpa sempre
  que o valor volta a 0, fora do ramo de disparo**, senão fica preso ao último valor alto.
- **Primeira leitura:** grava cada condição no histórico e mostra **um** aviso consolidado que abre o sino.
- **Suprimido no ecrã de KPIs:** grava no histórico **já marcado como lido**. O ecrã é o aviso; contá-lo
  no badge seria avisar o DBA do evento que ele está a ver.
- **Sino** antes do selector de idioma: badge de não lidos, painel com hora, título, valor e detalhe, e o
  clique abre a mesma modal que o aviso. Histórico em localStorage por viewer, tecto 50, try/catch.
- **Sem lembrete por toast:** o badge pulsa quando o não-lido mais antigo passa de 30 min (respeita
  `prefers-reduced-motion`).
- **Dados stale persistentes** (10 leituras seguidas) gravam "monitorização de críticos parada"; antes o
  sino ficava vazio sem sinal.

## Acessibilidade (não herdar o gap do menu de perfil)

Teclado ao padrão do selector de idioma (commit `c15493a` no V3.4): setas, Home/End, **Escape fecha e
devolve o foco ao botão**. O menu de perfil do V3.4 fecha só por clique fora, sem Escape nem retorno de
foco: é um gap registado, não um modelo. `aria-live` do badge numa região própria, separada do
`#toastContainer`, para não duplicar anúncios ao leitor de ecrã.

## Testes a portar

`tests/unit/test_a2_avisos_criticos_20260914.py` (10, estáticos). A prova de comportamento do V3.4 extraiu
as funções reais do portal e correu-as em Node com uma sequência de leituras: arranque consolidado,
oscilação 2-3-2-3 dispara uma vez, nova ocorrência depois de 0, suprimido gravado como lido, stale, badge.
Vale a pena repetir no V6, porque os testes estáticos não apanham um erro de lógica no estado.
