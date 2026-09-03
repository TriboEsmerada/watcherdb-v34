# i18n pt-BR overlay + v33-i18n-linguist - PASSO 2: commit (depois do PASSO 1 verde)
# Identidade: owner (git). Onde: PowerShell na raiz do V3.4. Impacto: so' git local.
# Pre-condicao: python docs/context/I18N_PTBR_PASSO1_apply.py  (sem [ABORT])
#               python -m pytest tests/unit/test_i18n_parity.py -q   -> 6 passed
#               python scripts/i18n_validate.py                      -> 0 errors
# Rollback: git reset --soft HEAD~1 (mantem ficheiros) ou git revert <sha> apos push.
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current   # esperado: main
git status --short

git add .claude/agents/v33-i18n-linguist.md .claude/agents/v33-i18n-coverage.md `
        docs/context/I18N_PTBR_PASSO1_apply.py docs/context/I18N_PTBR_LOTE_A.json `
        docs/context/I18N_PTBR_PASSO2_commit.ps1 `
        docs/context/PLANO_I18N_LINGUIST_PTBR_2026-09-03.md `
        docs/context/PROMPT_PROPAGACAO_V6_I18N_PTBR_2026-09-03.md `
        docs/context/CONTEXT.md docs/changelog/CHANGELOG.md `
        docs/FEATURE_MATRIX.md docs/AGENTS_GUIDE.md docs/adr/ADR-001-council-composition.md `
        static/js/watcherdb_i18n_v2.js templates/watcherdb_portal.html `
        static/i18n/pt.json static/i18n/pt-BR.json `
        scripts/i18n_validate.py tests/unit/test_i18n_parity.py `
        knowledge_base/domain/i18n_glossary.md

$msg = @'
feat(i18n): pt-BR como 4.o idioma (overlay esparso) + micro-agent v33-i18n-linguist

Decisao owner 03/09 (charter: core-council-architect; plano em
PLANO_I18N_LINGUIST_PTBR_2026-09-03):
- pt.json fixado como pt-PT pos-AO90; nasce static/i18n/pt-BR.json com
  apenas as chaves que diferem (fallback por chave ja existia no motor).
- runtime: SUPPORTED_LANGS + FALLBACK_CHAIN com 'pt-BR'; selector com 4
  opcoes (PT-PT com bandeira correcta, PT-BR novo); 3 ciclos de idioma do
  portal deixam de ter ['pt','en','es'] hardcoded.
- validador e teste de paridade conhecem o overlay (subconjunto de pt, sem
  orfas nem overrides identicos; AO90 e placeholders tambem em pt-BR).
- lote A do linguista: 98 chaves de pt.json com vocabulario pt-BR ou acentos
  em falta passam a pt-PT; o original vai para o overlay.
- council: novo micro-agent v33-i18n-linguist (qualidade de traducao,
  acentuacao rigorosa, glossario); v33-i18n-coverage conhece o overlay.
- glossario de termos que nao se traduzem em knowledge_base/domain.
Zero backend, zero BD. Pendentes: lotes B (acentos pt/es), C (es neutro),
D (en-US), E (211 chaves pt==en).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
# -m $msg falha no PS7 quando a mensagem tem aspas duplas; usar ficheiro + -F (licao 03/09).
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
