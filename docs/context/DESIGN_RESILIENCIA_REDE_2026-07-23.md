# DESIGN — Resiliência de rede: DNS + IP em dual-path (Wave "nunca para")

**Data:** 2026-07-23 | **Requisito do owner (verbatim):** "esse programa tem que funcionar
tanto com dns quanto com ip. se um der pau, usa o outro. assim o programa nunca para."
**Estado:** APROVADO em conceito; implementação a agendar. Nascido do incidente de hoje:
100% dos eventos offline do dia (39+8+38) eram doença de resolução na máquina do coletor,
0% frota.

## Princípio

Cada alvo tem DOIS caminhos: o nome (DNS) e o último IP conhecido (cache persistente).
Ordem: DNS com timeout curto → sucesso: usa e actualiza cache; falha: **fallback ao IP
cacheado**. Só quando AMBOS falham é que o alvo é declarado inacessível. DNS que volta a
responder com IP diferente do cache → actualiza + loga (caso re-IP).

## Componentes

1. **Módulo resolvedor** (`resolve_with_fallback(host, timeout=2s) -> (ip, source)`):
   - source ∈ {DNS, CACHE, FAIL}; nunca lança para o caller por causa de DNS — devolve FAIL
     só se cache também vazio/inválido.
   - Anti-hang: resolução com timeout PRÓPRIO (thread/socket), nunca getaddrinfo nu —
     hoje medimos getaddrinfo a variar 0.00s→146s na mesma máquina.
2. **Cache persistente de IPs**:
   - V1 collector: tabela partilhada `WDB_HOST_IP_CACHE` (Host PK, IP, Last_Resolved_TS,
     Last_Verified_TS, Source) na Intelligence — **GATE: veto v1-intel-specialist**
     (infra partilhada) + canonical INSTALACAO sync.
   - V3.3/V6 web: mesmo padrão via ficheiro local `config/ip_cache.json` OU leitura da
     tabela (decidir na implementação; menos peças = melhor).
3. **Pontos de integração**:
   - V1: `base_collector` (connect a cada instância) + ping collector (resolve→ICMP).
   - V3.3/V6: pool da Intelligence + live-path (SQL Diag "Servidor Indisponivel" — hoje
     deu falso OFFLINE com resolver frio) + endpoint os-boot etc.
4. **Sinergias da mesma wave** (mesmo sítio do código, mesmo teste):
   - Circuit breaker anti-massa: >N% da frota a falhar num sweep → evento único
     "suspeita local (rede/DNS do coletor)", não N×CRITICAL.
   - Distinguir DNS_FAIL de ICMP_TIMEOUT de TCP_REFUSED no diagnóstico dos eventos.
   - Reconciliação esperado-vs-coletado no KPI Disponibilidade (collect_inst_availability
     tem `1 AS Is_Available` hardcoded — servidor em baixo não gera linha e desaparece).
   - Logon dos serviços Windows → LocalSystem (boot falhou hoje: conta de domínio sem DC
     antes da VPN; PRE-CHECK: localizar chave Fernet dos encrypted: do config).

## Fora de scope

- Substituir nomes por IPs em configs/conn strings (mata Kerberos futuro + gestão).
- Registar IPs à mão: o cache é APRENDIDO das resoluções bem-sucedidas, nunca mantido
  manualmente (IPs mudam; manutenção manual = staleness garantida).

## Validação de aceitação

Simular DNS morto (regra NRPT para servidor inexistente ou bloqueio) → coletor continua
a coletar TODA a frota via cache; KPI Disponibilidade sem falsos offline; evento único
de degradação "DNS local em falha, a operar por cache de IP".
