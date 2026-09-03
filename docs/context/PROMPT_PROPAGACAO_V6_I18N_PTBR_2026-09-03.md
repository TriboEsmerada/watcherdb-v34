# Prompt de propagação para o V6 — i18n pt-BR overlay + linguista (2026-09-03)

Colar na sessão da AI do WATCHERDB_V6. Origem: V3.4 commit `feat(i18n): pt-BR como 4.o idioma`.
Canonical: `docs/FEATURE_MATRIX.md` §UX & i18n (V3.4) + `knowledge_base/domain/i18n_glossary.md`.

## O que mudou no canonical (V3.4) e porquê

1. **Política de locales** (decisão owner 2026-09-03):
   - `pt.json` = pt-PT pós-AO90, default e ground truth de chaves.
   - `pt-BR.json` = **overlay esparso**: só chaves cujo texto difere do pt-PT. Runtime resolve
     `FALLBACK_CHAIN['pt-BR'] = ['pt-BR', 'pt']` por chave. Nunca paridade total.
   - `en.json` = en-US. `es.json` = espanhol neutro (sem vosotros, sem léxico só ibérico).
   - Acentuação rigorosa em pt / pt-BR / es é exigência explícita do owner (finding P1 quando falta).
2. **Glossário** de termos que ficam em inglês em todos os locales + pares pt-PT↔pt-BR:
   `knowledge_base/domain/i18n_glossary.md` (copiar tal e qual para o V6).
3. **Council**: micro-agent `v33-i18n-linguist` (qualidade de tradução) a par de `v33-i18n-coverage`
   (cobertura). Sequência obrigatória em mudanças i18n: coverage → linguist.

## O que o V6 tem de verificar / fazer

- [ ] Localizar o motor i18n do V6 e confirmar se tem fallback por chave. Se sim, replicar
      `SUPPORTED_LANGS` + `FALLBACK_CHAIN` com `pt-BR`. Se não, o overlay exige merge em load
      (`Object.assign({}, pt, ptBR)`) — decidir antes de copiar ficheiros.
- [ ] Procurar listas hardcoded `['pt','en','es']` e `% 3` em ciclos de idioma (no V3.4 havia 3 no portal).
- [ ] Selector: 🇵🇹 Português (Portugal) `lang="pt-PT"` + 🇧🇷 Português (Brasil) `lang="pt-BR"`;
      `document.documentElement.lang` mapeia `pt → pt-PT`.
- [ ] Validador e teste de paridade: overlay = subconjunto de pt, sem chaves órfãs, sem overrides
      idênticos a pt; AO90 e placeholders também aplicados ao overlay (ver `tests/unit/test_i18n_parity.py` V3.4).
- [ ] Reaplicar o lote A (`docs/context/I18N_PTBR_LOTE_A.json` do V3.4) às chaves que existam no V6
      com o mesmo nome; o script `I18N_PTBR_PASSO1_apply.py` aborta em chave inexistente — adaptar.
- [ ] Adaptar os dois charters (`.claude/agents/v33-i18n-linguist.md`, `v33-i18n-coverage.md`) ao
      namespace do V6 (paths reais), sem alterar regras.
- [ ] Lotes pendentes (B acentos pt/es, C es neutro, D en-US, E 211 chaves pt==en) correm no V6 com
      o linguista local depois de o V3.4 fechar os seus — não duplicar trabalho.

## Não fazer

- Não criar `pt-PT.json` nem `en-US.json`: o pt-PT vive em `pt.json`.
- Não exigir paridade total do `pt-BR.json` no validador do V6.
- Não traduzir os termos do glossário "para ficar mais português".
