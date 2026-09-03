---
stage: 07
title: Hardening — segurança e resiliência
version: 0.1.0
constraints: [ENCAPS, SEC]
---

# Etapa 07 — Hardening de {{PROGRAM_NAME}}

Antes do primeiro utilizador real: endurecer segurança e resiliência.
Duas frentes, ambas obrigatórias.

## Frente A — Segurança (bloco SEC)

1. Revisita o threat model da etapa 03 contra o código REAL — o que
   mudou desde o desenho?
2. Auditoria de identidades: nenhuma credencial pessoal em código/
   config; conta de serviço com privilégio mínimo confirmado (testa o
   que ela NÃO consegue fazer).
3. Passa OWASP Top 10 como checklist; injeção (SQL/command/prompt) com
   inputs adversariais reais.
4. Segredos: scan do repo inteiro + histórico git; rotação definida.
5. Auth: endpoints de mutação exigem auth server-side; UI-gate sem
   backend-gate é vulnerabilidade, não feature.
   <!-- EXPAND: se a app expõe rede local/internet, acrescenta: regra
   de firewall com perfil correto para a INTERFACE real (perfil Domain
   falha se a interface está Public) + rate limiting verificado. -->

## Frente B — Resiliência de execução

6. Boot hardening de serviço/processo longo: shutdown limpo
   (should_exit, daemon threads), zero I/O síncrono bloqueante em
   contexto async (to_thread), /healthz honesto (verifica dados, não
   só processo).
7. Monitor em camadas: processo vivo → porta aberta → endpoint
   responde → dados frescos. Cada camada com alarme próprio.
8. Falha de dependência (BD fora, API externa em baixo): degradação
   graciosa visível ao utilizador; nunca crash-loop silencioso.
9. Restart storm test: mata o processo 5x seguidas — recupera sempre?
   deixa lixo (locks, tasks órfãs, ficheiros temp)?
10. Relógio e fuso: timestamps em UTC internamente; conversão só na UI.

## Critério de saída
- [ ] Checklist OWASP passado com evidência (não "parece ok")
- [ ] Scan de segredos no repo + histórico limpo
- [ ] Kill-and-restart 5x sem estado corrompido
- [ ] Healthcheck honesto (inclui freshness de dados)
