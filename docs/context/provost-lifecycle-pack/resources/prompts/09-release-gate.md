---
stage: 09
title: Release gate GO/NO-GO
version: 0.1.0
constraints: [GIT, SEC, DOCS]
---

# Etapa 09 — Release gate de {{PROGRAM_NAME}} v{{VERSION}}

Decisão binária GO/NO-GO. O gate existe para dizer NO-GO sem drama —
um NO-GO barato hoje evita um incidente caro amanhã. Nenhum item é
"waivável" por pressa; waiver exige registo escrito com dono e prazo.

## Checklist (todas as linhas com evidência, não opinião)

**Qualidade**
- [ ] Suite QA completa verde no commit candidato (hash: ______)
- [ ] Teste UI nos viewports-alvo feito nesta versão (não "na anterior")
- [ ] Zero bugs conhecidos de severidade alta abertos

**Soberania e segurança**
- [ ] Scan de segredos no diff desde a última release
- [ ] Dependências: audit limpo; novas deps revistas (licença + manutenção)
- [ ] Identidades: nenhuma credencial nova fora do cofre

**Consistência de produto**
- [ ] Feature Matrix atualizada — nada shipped fora da matriz
      (tier creep = NO-GO se houver edições)
- [ ] CHANGELOG fechado com a versão SemVer certa
- [ ] Docs de utilizador refletem o comportamento novo

**Empacotamento**
- [ ] Artefacto da etapa 08 rebuild no commit candidato (não reaproveitar
      build antigo)
- [ ] Upgrade a partir da versão anterior testado
- [ ] Rollback documentado e testado

**Git**
- [ ] Tag da versão criada; branch de release limpa
- [ ] Zero trabalho uncommitted em QUALQUER repo do produto
      (verificar repo a repo)

<!-- EXPAND: se o produto tem múltiplas edições ou repos dependentes,
acrescenta secção "Propagação" com a lista de destinos e o estado de
cada um; release de um lado com o outro divergente = NO-GO. -->

## Veredicto

`GO` / `NO-GO` + 3 linhas de justificação + assinatura (humano).
NO-GO lista os bloqueadores por ordem de esforço, não de gravidade —
destrava primeiro o rápido.

## Critério de saída
- [ ] Veredicto registado no CHANGELOG/release notes
- [ ] Se GO: tag + artefacto arquivado + anúncio
- [ ] Se NO-GO: bloqueadores com dono e prazo
