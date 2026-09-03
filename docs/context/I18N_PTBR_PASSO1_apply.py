#!/usr/bin/env python3
"""i18n: pt-BR como 4.o locale (overlay esparso) + linguista -- PASSO 1: aplicar patches.

Identidade: owner (filesystem local). Onde: raiz do V3.4.
    python docs/context/I18N_PTBR_PASSO1_apply.py --dry-run     # so' verifica que todos os alvos existem
    python docs/context/I18N_PTBR_PASSO1_apply.py               # aplica
    python docs/context/I18N_PTBR_PASSO1_apply.py --nestor      # tambem actualiza council_v33_local.md (Nestor central)
    python docs/context/I18N_PTBR_PASSO1_apply.py --root <dir>  # aplicar noutra copia (usado pela AI para validar em scratchpad)

Impacto: edita 8 ficheiros (runtime i18n, portal, validador, teste, FEATURE_MATRIX,
AGENTS_GUIDE, ADR-001, CHANGELOG) e cria 2 (static/i18n/pt-BR.json,
knowledge_base/domain/i18n_glossary.md). Zero BD, zero servico, zero V1.
Cada patch exige contagem exacta do texto-alvo; se um alvo mudou, o script PARA
antes de escrever o que quer que seja (fase 1 = verificar tudo; fase 2 = escrever).

Rollback: git checkout -- static/js/watcherdb_i18n_v2.js templates/watcherdb_portal.html \
            scripts/i18n_validate.py tests/unit/test_i18n_parity.py docs/FEATURE_MATRIX.md \
            docs/AGENTS_GUIDE.md docs/adr/ADR-001-council-composition.md docs/changelog/CHANGELOG.md \
            static/i18n/pt.json
          git clean -f static/i18n/pt-BR.json knowledge_base/domain/i18n_glossary.md

Sidecar obrigatorio: docs/context/I18N_PTBR_LOTE_A.json
    [{"key": "ns.key", "class": "fix", "pt_pt": "...", "pt_br": "..."}, ...]
    (saida do v33-i18n-linguist, lote A). "fix" -> pt.json recebe pt_pt e pt-BR.json recebe pt_br
    quando pt_br != pt_pt. pt.json e' editado por TEXTO (linha a linha), nunca por round-trip JSON,
    porque tem chaves duplicadas (effort_label/impact_label ~1656 e ~1787) que um dump apagaria.
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent
NESTOR_COUNCIL = Path.home() / ".nestor-library/watcherdb-family/architecture/v_specific/v3_3/council_v33_local.md"

# ----------------------------------------------------------------------------
# Patches de texto: (ficheiro relativo, texto antigo, texto novo, ocorrencias esperadas)
# ----------------------------------------------------------------------------
JS = "static/js/watcherdb_i18n_v2.js"
HTML = "templates/watcherdb_portal.html"
VAL = "scripts/i18n_validate.py"
TST = "tests/unit/test_i18n_parity.py"
FM = "docs/FEATURE_MATRIX.md"
AG = "docs/AGENTS_GUIDE.md"
ADR = "docs/adr/ADR-001-council-composition.md"
CHG = "docs/changelog/CHANGELOG.md"

SELECTOR_OLD = """            '  <div class="i18n-lang-option" data-lang="pt" role="option" lang="pt-BR">',
            '    <span class="i18n-lang-flag">🇧🇷</span>',
            '    <span class="i18n-lang-name">Português</span>',
            '    <i class="fas fa-check i18n-lang-check"></i>',
            '  </div>',
"""
SELECTOR_NEW = """            '  <div class="i18n-lang-option" data-lang="pt" role="option" lang="pt-PT">',
            '    <span class="i18n-lang-flag">🇵🇹</span>',
            '    <span class="i18n-lang-name">Português (Portugal)</span>',
            '    <i class="fas fa-check i18n-lang-check"></i>',
            '  </div>',
            '  <div class="i18n-lang-option" data-lang="pt-BR" role="option" lang="pt-BR">',
            '    <span class="i18n-lang-flag">🇧🇷</span>',
            '    <span class="i18n-lang-name">Português (Brasil)</span>',
            '    <i class="fas fa-check i18n-lang-check"></i>',
            '  </div>',
"""

SEQ_OLD = "            const seq = ['pt', 'en', 'es'];\n"
SEQ_NEW = ("            const seq = (typeof WatcherI18N !== 'undefined' && WatcherI18N.SUPPORTED_LANGS) "
           "? WatcherI18N.SUPPORTED_LANGS : ['pt', 'pt-BR', 'en', 'es'];\n")
NXT_OLD = "            const nxt = seq[(seq.indexOf(cur) + 1) % 3];\n"
NXT_NEW = "            const nxt = seq[(seq.indexOf(cur) + 1) % seq.length];\n"
KPIREPORT_OLD = ("function kpiReportCycleLang() { const seq = ['pt', 'en', 'es']; "
                 "const cur = (typeof getLanguage === 'function' ? getLanguage() : 'pt'); "
                 "const nxt = seq[(seq.indexOf(cur) + 1) % 3];")
KPIREPORT_NEW = ("function kpiReportCycleLang() { const seq = (typeof WatcherI18N !== 'undefined' && WatcherI18N.SUPPORTED_LANGS) "
                 "? WatcherI18N.SUPPORTED_LANGS : ['pt', 'pt-BR', 'en', 'es']; "
                 "const cur = (typeof getLanguage === 'function' ? getLanguage() : 'pt'); "
                 "const nxt = seq[(seq.indexOf(cur) + 1) % seq.length];")

CHANGELOG_ENTRY = """- **Português do Brasil como 4.º idioma do portal (overlay esparso) + micro-agent
  `v33-i18n-linguist`** (decisão owner 03/09; charter pelo core-council-architect).
  `pt.json` fixa-se como **pt-PT pós-AO90** (norma de 16/08) e nasce
  `static/i18n/pt-BR.json` contendo apenas as chaves cujo texto difere do pt-PT;
  o motor já resolvia fallback por chave (`FALLBACK_CHAIN`), pelo que pt-BR cai em
  pt para tudo o resto. Selector passa a 4 opções (🇵🇹 Português (Portugal),
  🇧🇷 Português (Brasil), English, Español) e os 3 ciclos de idioma do portal
  deixam de ter `['pt','en','es']` hardcoded. `scripts/i18n_validate.py` e
  `tests/unit/test_i18n_parity.py` conhecem o overlay (subconjunto de pt, sem
  chaves órfãs nem overrides idênticos a pt; AO90 e placeholders também em pt-BR).
  Lote A do linguista: vocabulário pt-BR que vivia em `pt.json` (usuário, arquivo,
  carregando, coleta, monitoramento, configurações…) passa a pt-PT e o original
  vai para o overlay. Glossário de termos que não se traduzem em
  `knowledge_base/domain/i18n_glossary.md`. Pendentes para lotes B-E: acentuação
  (pt 195 / es 313 chaves com candidatos), es neutro, en-US, 211 chaves pt==en.
  [tier: Std]
"""

GLOSSARY = """# Glossário i18n — WatcherDB V3.4

Fonte para `v33-i18n-linguist` e `v33-i18n-coverage`. Decisões do owner 2026-09-03:
`pt.json` = pt-PT pós-AO90 (default); `pt-BR.json` = overlay esparso (só o que difere);
`en.json` = en-US; `es.json` = espanhol neutro (sem vosotros, sem léxico só ibérico).
Acentuação rigorosa em pt / pt-BR / es é exigência explícita (finding P1 quando falta).

## 1. Termos que ficam em inglês em TODOS os locales

| Termo | Nota |
|---|---|
| AlwaysOn / Always On, Availability Group (AG), listener, réplica → **replica** só em en | pt/es podem dizer "réplica" |
| backup, backupset, FULL / DIFF / LOG, restore, RPO, RTO | nunca "cópia de segurança" na UI |
| tempdb / TempDB, filegroup / FileGroup, data file, log file, transaction log | "T-Log" aceitável |
| job, SQL Agent / Agent, schedule (quando é `msdb.dbo.sysschedules`) | "agendamento" = a acção, ok em pt |
| DMV, XE (Extended Events), wait stats, plan cache, parameter sniffing | |
| failover, mirroring, linked server, snapshot, collation, recovery model | |
| CPU, RAM, IOPS, KPI, SLA, TDE, DBCC, DNS, TCP, ODBC, AD, LDAP/LDAPS | |
| Max Server Memory, STATISTICS IO/TIME, Actual Execution Plan, query hash | nomes de opções/artefactos |
| drive, label, database (quando nome de objecto ou coluna), instance name | "base de dados" quando é prosa em pt |
| dashboard, login, logout, timeout, cluster, deadlock, lock, latch, spill | |

## 2. Pares pt-PT ↔ pt-BR recorrentes (o overlay só existe para estes)

| pt-PT (pt.json) | pt-BR (pt-BR.json) |
|---|---|
| utilizador(es) | usuário(s) |
| ficheiro(s) | arquivo(s) |
| Definições (menu Settings) | Configurações |
| registo | registro |
| A carregar… | Carregando… |
| recolha (de dados) | coleta |
| monitorização | monitoramento |
| Base de Dados | Banco de Dados |
| relacionados com | relacionados a |
| Estado | Status |
| Pesquisar | Buscar |
| ecrã | tela |
| gerir / gestão | gerenciar / gerenciamento |
| guardar | salvar |
| equipa, controlo, planeamento | equipe, controle, planejamento |

Grafia comum pós-AO90 (não é marcador de variante): atualizar, ativo, direto, ótimo, coleção.

## 3. Espanhol neutro — evitar

ordenador → equipo/servidor; fichero → archivo; vosotros/vuestro → ustedes/su;
coger → tomar/obtener; "ordenar" ok; "vale" → "aceptar".

## 4. en-US — evitar en-GB

colour, optimise, analyse, licence (subst.), catalogue, behaviour, centre.
"""


def patches():
    return [
        # --- runtime i18n --------------------------------------------------
        (JS, " * Supports: PT-BR (default), EN, ES\n",
             " * Supports: PT-PT (default, pt.json), PT-BR (pt-BR.json = overlay esparso com fallback por chave para pt), EN, ES\n", 1),
        (JS, "    const SUPPORTED_LANGS = ['pt', 'en', 'es'];\n",
             "    const SUPPORTED_LANGS = ['pt', 'pt-BR', 'en', 'es'];\n", 1),
        (JS, "        pt: ['pt'],\n        en: ['en', 'pt'],\n",
             "        pt: ['pt'],\n        'pt-BR': ['pt-BR', 'pt'],   // overlay esparso (decisao owner 2026-09-03)\n        en: ['en', 'pt'],\n", 1),
        (JS, "     * @param {string} lang - Language code ('pt', 'en', 'es')\n",
             "     * @param {string} lang - Language code ('pt', 'pt-BR', 'en', 'es')\n", 1),
        (JS, "{ pt: 'pt-PT', en: 'en', es: 'es' };",
             "{ pt: 'pt-PT', 'pt-BR': 'pt-BR', en: 'en', es: 'es' };", 2),
        (JS, "            var flags = { pt: '🇧🇷', en: '🇺🇸', es: '🇪🇸' };\n            var labels = { pt: 'PT', en: 'EN', es: 'ES' };\n",
             "            var flags = { pt: '🇵🇹', 'pt-BR': '🇧🇷', en: '🇺🇸', es: '🇪🇸' };\n            var labels = { pt: 'PT', 'pt-BR': 'PT-BR', en: 'EN', es: 'ES' };\n", 1),
        (JS, "            '  <span id=\"langFlagDisplay\">🇧🇷 PT</span>',\n",
             "            '  <span id=\"langFlagDisplay\">🇵🇹 PT</span>',\n", 1),
        (JS, SELECTOR_OLD, SELECTOR_NEW, 1),
        # --- portal: ciclos de idioma sem lista hardcoded --------------------
        (HTML, SEQ_OLD, SEQ_NEW, 2),
        (HTML, NXT_OLD, NXT_NEW, 2),
        (HTML, KPIREPORT_OLD, KPIREPORT_NEW, 1),
        (HTML, "(PT-EN-ES)", "(PT / PT-BR / EN / ES)", 1),
        # --- validador -------------------------------------------------------
        (VAL, "SUPPORTED_LANGS = ['pt', 'en', 'es']\n",
              "SUPPORTED_LANGS = ['pt', 'pt-BR', 'en', 'es']\n"
              "OVERLAY_LANGS = {'pt-BR'}  # overlay esparso: subconjunto de pt, fallback por chave no runtime (owner 2026-09-03)\n", 1),
        (VAL, "        # Keys in reference but missing in this lang\n        missing = ref_keys - lang_keys\n",
              "        # Keys in reference but missing in this lang (overlay langs may be sparse)\n"
              "        missing = set() if lang in OVERLAY_LANGS else (ref_keys - lang_keys)\n", 1),
        (VAL, "        if lang == REFERENCE_LANG:\n            continue\n        lang_keys = set(translations[lang].keys())\n        missing = ref_keys - lang_keys\n",
              "        if lang == REFERENCE_LANG or lang in OVERLAY_LANGS:\n            continue\n        lang_keys = set(translations[lang].keys())\n        missing = ref_keys - lang_keys\n", 1),
        (VAL, "                    'type': 'POSSIBLY_UNTRANSLATED',\n",
              "                    'type': 'OVERLAY_REDUNDANT' if lang in OVERLAY_LANGS else 'POSSIBLY_UNTRANSLATED',\n", 1),
        # --- teste ----------------------------------------------------------
        (TST, '"""Paridade e higiene dos dicionarios i18n (pt/en/es).\n',
              '"""Paridade e higiene dos dicionarios i18n (pt/en/es + overlay pt-BR).\n', 1),
        (TST, 'LOCALES = ("pt", "en", "es")\n',
              'LOCALES = ("pt", "en", "es")\n'
              'OVERLAY_LOCALES = ("pt-BR",)  # overlay esparso de pt (owner 2026-09-03): subconjunto, sem chaves extra\n', 1),
        (TST, "    return {loc: _load(loc) for loc in LOCALES}\n",
              "    return {loc: _load(loc) for loc in LOCALES + OVERLAY_LOCALES}\n", 1),
        (TST, "    for loc in LOCALES:\n        assert (I18N_DIR",
              "    for loc in LOCALES + OVERLAY_LOCALES:\n        assert (I18N_DIR", 1),
        (TST, '    offenders = {\n        k: v for k, v in dicts["pt"].items()\n        if isinstance(v, str) and _PRE_AO90.search(v)\n    }\n',
              '    offenders = {\n        f"{loc}:{k}": v\n        for loc in ("pt",) + OVERLAY_LOCALES\n        for k, v in dicts[loc].items()\n        if isinstance(v, str) and _PRE_AO90.search(v)\n    }\n', 1),
        (TST, '    for loc in ("en", "es"):\n        for key, value in dicts[loc].items():\n',
              '    for loc in ("en", "es") + OVERLAY_LOCALES:\n        for key, value in dicts[loc].items():\n', 1),
        (TST, '    assert not problems, f"placeholders divergentes: {problems[:10]}"\n',
              '    assert not problems, f"placeholders divergentes: {problems[:10]}"\n'
              '\n\n'
              'def test_ptbr_overlay_is_sparse_subset_of_pt(dicts):\n'
              '    """pt-BR e\' overlay (owner 2026-09-03): so\' chaves que existem em pt E cujo texto difere de pt."""\n'
              '    pt = dicts["pt"]\n'
              '    for loc in OVERLAY_LOCALES:\n'
              '        flat = dicts[loc]\n'
              '        assert flat, f"{loc}.json vazio -- overlay sem overrides nao faz sentido"\n'
              '        orphans = sorted(k for k in flat if k not in pt)\n'
              '        assert not orphans, f"{loc}.json com chaves que pt nao tem: {orphans[:10]}"\n'
              '        redundant = sorted(k for k, v in flat.items() if pt.get(k) == v)\n'
              '        assert not redundant, f"{loc}.json com overrides identicos a pt (redundantes): {redundant[:10]}"\n', 1),
        # --- docs -----------------------------------------------------------
        (FM, "- PT (default), EN, ES — 3 línguas distintas (Portuguese, English, Spanish). Ground truth: `static/js/watcherdb_i18n_v2.js` SUPPORTED_LANGS. Ficheiros: `static/i18n/{pt,en,es}.json`.\n",
             "- PT-PT (default, `pt.json`), PT-BR (`pt-BR.json`, overlay esparso: só chaves que diferem de pt-PT; fallback por chave), EN (en-US), ES (neutro). Ground truth: `static/js/watcherdb_i18n_v2.js` SUPPORTED_LANGS + FALLBACK_CHAIN. Glossário: `knowledge_base/domain/i18n_glossary.md`. Decisão owner 2026-09-03.\n", 1),
        (AG, "| `v33-i18n-coverage` | Dado HTML alterado, lista chaves pt/en/es em falta |\n",
             "| `v33-i18n-coverage` | Dado HTML alterado, lista chaves pt/en/es em falta (+ overrides pt-BR em falta, WARN) |\n"
             "| `v33-i18n-linguist` | Dado diff de `static/i18n/*.json`, audita qualidade de tradução: variante (pt-PT / pt-BR overlay / en-US / es neutro), acentuação, glossário SQL Server, consistência intra-locale |\n", 1),
        (AG, "| Mudança em SPA, validar i18n | `v33-i18n-coverage` (micro) |\n",
             "| Mudança em SPA, validar i18n | `v33-i18n-coverage` (micro) → `v33-i18n-linguist` (micro), em sequência |\n", 1),
        (ADR, "### Micro-agents (Fase 3 — 6 agents single-task)\n",
              "### Micro-agents (Fase 3 — 6 agents single-task; 7.º adicionado 2026-09-03)\n", 1),
        (ADR, "- `v33-i18n-coverage`\n",
              "- `v33-i18n-coverage`\n- `v33-i18n-linguist` (2026-09-03 — qualidade de tradução; par do coverage. Charter: core-council-architect)\n", 1),
    ]


NESTOR_PATCHES = [
    ("These 6 agents exist only in", "These 7 agents exist only in", 1),
    ("| `v33-i18n-coverage.md` | Detect hardcoded strings, missing i18n keys | Template changes |\n",
     "| `v33-i18n-coverage.md` | Detect hardcoded strings, missing i18n keys | Template changes |\n"
     "| `v33-i18n-linguist.md` | Translation quality: variant (pt-PT / pt-BR overlay / en-US / neutral es), accents, SQL Server glossary, consistency | `static/i18n/*.json` changes |\n", 1),
]


# ----------------------------------------------------------------------------
def read(p: Path):
    raw = p.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    return raw, nl


def write(p: Path, text: str):
    p.write_bytes(text.encode("utf-8"))


def norm(s: str, nl: str):
    return s.replace("\n", nl) if nl != "\n" else s


def check_and_apply(root: Path, plist, dry: bool):
    """Fase 1: verifica TODAS as contagens. Fase 2: aplica. Nunca escreve se fase 1 falhar."""
    problems = []
    texts = {}
    for rel, old, new, n in plist:
        p = root / rel
        if not p.exists():
            problems.append(f"{rel}: ficheiro nao existe")
            continue
        if rel not in texts:
            texts[rel] = read(p)
        raw, nl = texts[rel]
        c = raw.count(norm(old, nl))
        if c != n:
            problems.append(f"{rel}: esperado {n}x, encontrado {c}x -> {old[:70]!r}")
    if problems:
        print("[ABORT] alvos nao batem (nada foi escrito):")
        for x in problems:
            print("   -", x)
        sys.exit(2)
    for rel, old, new, n in plist:
        raw, nl = texts[rel]
        texts[rel] = (raw.replace(norm(old, nl), norm(new, nl)), nl)
    if dry:
        print(f"[DRY] {len(plist)} patches verificados em {len(texts)} ficheiros")
        return
    for rel, (raw, nl) in texts.items():
        write(root / rel, raw)
        print(f"[OK] {rel}")


def apply_changelog(root: Path, dry: bool):
    p = root / CHG
    raw, nl = read(p)
    anchor = norm("## [Unreleased]\n\n### Changed\n\n", nl)
    if raw.count(anchor) != 1:
        print("[ABORT] CHANGELOG: ancora '## [Unreleased] / ### Changed' nao encontrada 1x")
        sys.exit(2)
    if "v33-i18n-linguist" in raw:
        print("[SKIP] CHANGELOG ja tem a entrada")
        return
    if dry:
        print("[DRY] CHANGELOG ok")
        return
    write(p, raw.replace(anchor, anchor + norm(CHANGELOG_ENTRY, nl) + nl, 1))
    print(f"[OK] {CHG}")


def lote_a(root: Path, dry: bool):
    """pt.json por texto + pt-BR.json overlay gerado do sidecar."""
    side = HERE / "I18N_PTBR_LOTE_A.json"
    if not side.exists():
        print(f"[ABORT] sidecar em falta: {side}")
        sys.exit(2)
    items = [x for x in json.loads(side.read_text(encoding="utf-8")) if x.get("class") == "fix"]
    pt_path = root / "static/i18n/pt.json"
    raw, nl = read(pt_path)
    flat = _flatten(json.loads(raw))
    problems = []
    # agrupar por (leaf, valor actual): o mesmo par pode existir em varios namespaces
    groups = {}
    for it in items:
        key = it["key"]
        if key not in flat:
            problems.append(f"chave inexistente em pt.json: {key}")
            continue
        for ph in _placeholders(flat[key]):
            if ph not in it["pt_pt"] or ph not in it["pt_br"]:
                problems.append(f"{key}: placeholder {ph} perdido")
        if flat[key].count("|") != it["pt_pt"].count("|") or flat[key].count("|") != it["pt_br"].count("|"):
            problems.append(f"{key}: formas plurais divergem")
        leaf = key.split(".")[-1]
        groups.setdefault((leaf, flat[key]), {"keys": [], "pt_pt": set()})
        groups[(leaf, flat[key])]["keys"].append(key)
        groups[(leaf, flat[key])]["pt_pt"].add(it["pt_pt"])
    for (leaf, old), g in groups.items():
        if len(g["pt_pt"]) != 1:
            problems.append(f"{leaf}={old[:40]!r}: chaves {g['keys']} pedem pt_pt diferentes {g['pt_pt']}")
            continue
        needle = json.dumps(leaf, ensure_ascii=False) + ": " + json.dumps(old, ensure_ascii=False)
        c = raw.count(needle)
        if c != len(g["keys"]):
            problems.append(f"{leaf}: '{needle[:60]}' aparece {c}x em pt.json, sidecar cobre {len(g['keys'])} chave(s) {g['keys']}")
    if problems:
        print("[ABORT] lote A inconsistente (nada foi escrito):")
        for x in problems:
            print("   -", x)
        sys.exit(2)
    new_raw = raw
    for (leaf, old), g in groups.items():
        needle = json.dumps(leaf, ensure_ascii=False) + ": " + json.dumps(old, ensure_ascii=False)
        repl = json.dumps(leaf, ensure_ascii=False) + ": " + json.dumps(next(iter(g["pt_pt"])), ensure_ascii=False)
        new_raw = new_raw.replace(needle, repl)
    json.loads(new_raw)  # pt.json continua JSON valido
    overlay = {}
    for it in items:
        if it["pt_br"] != it["pt_pt"]:
            _set(overlay, it["key"], it["pt_br"])
    n_over = len(_flatten(overlay))
    if dry:
        print(f"[DRY] lote A: {len(items)} chaves pt.json -> pt-PT; overlay pt-BR com {n_over} overrides")
        return
    write(pt_path, new_raw)
    ob = root / "static/i18n/pt-BR.json"
    ob.write_text(json.dumps(overlay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] static/i18n/pt.json ({len(items)} chaves) | static/i18n/pt-BR.json ({n_over} overrides)")


def glossary(root: Path, dry: bool):
    p = root / "knowledge_base/domain/i18n_glossary.md"
    if dry:
        print(f"[DRY] glossario -> {p} ({'existe' if p.exists() else 'novo'})")
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(GLOSSARY, encoding="utf-8")
    print("[OK] knowledge_base/domain/i18n_glossary.md (index.json: correr v33-knowledge-base-curator)")


def _flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        kk = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, kk))
        else:
            out[kk] = v
    return out


def _set(d, dotted, value):
    parts = dotted.split(".")
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


def _placeholders(s):
    import re
    return set(re.findall(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--nestor", action="store_true", help="tambem actualiza council_v33_local.md no Nestor central")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    a = ap.parse_args()
    root = Path(a.root).resolve()
    os.chdir(root)
    print(f"root: {root}  dry-run={a.dry_run}")
    check_and_apply(root, patches(), a.dry_run)
    apply_changelog(root, a.dry_run)
    lote_a(root, a.dry_run)
    glossary(root, a.dry_run)
    if a.nestor:
        if not NESTOR_COUNCIL.exists():
            print(f"[WARN] Nestor: {NESTOR_COUNCIL} nao existe -- ignorado")
        else:
            check_and_apply(NESTOR_COUNCIL.parent, [(NESTOR_COUNCIL.name, o, n, c) for o, n, c in NESTOR_PATCHES], a.dry_run)
    print("\nSeguir com: python -m pytest tests/unit/test_i18n_parity.py -q && python scripts/i18n_validate.py")


if __name__ == "__main__":
    main()
