#!/usr/bin/env python3
"""Lote F6a (BUG-003) -- modal "Analise Preditiva de Crescimento" segue o idioma + referencias legadas a "Oracle" saem.

Owner 09/09 (screenshot EN): titulo, textos de carregamento, ecras "Sem Dados Historicos" / "Script Nao Encontrado" /
erro / pop-up bloqueado e o botao "Fechar" em PT cru. Regiao do portal ~28873-29331: openReportModal, showNoDataError
(definida 2x -- a 2.a sobrepoe a 1.a; ambas patched para nao deixar texto cru em codigo morto), showScriptNotFoundError,
showReportError (2x, idem), displayReport (2x). O namespace predict.* ja existia (parcial): 27 chaves entram nele;
predict.oracle_timeout deixa de mencionar Oracle. Zero mudancas de comportamento; o 403 do endpoint e' outro achado.

Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_F6A_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_F6A_PASSO1_apply.py
Rollback: git checkout -- templates/watcherdb_portal.html static/i18n docs/changelog/CHANGELOG.md
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
HTML, CHG = "templates/watcherdb_portal.html", "docs/changelog/CHANGELOG.md"
KEYS = HERE / "I18N_F6A_KEYS.json"
CODE = '<code style="background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 4px;">filegroup_interactive_report_v5.py</code>'

# (old, new, esperado, regex?)
PATCHES = [
    ("title.textContent = 'Análise Preditiva de Crescimento';", "title.textContent = t('predict.title');  // lote F6a 2026-09-09", 1, False),
    ('<i class="fas fa-brain"></i> Executando Machine Learning...', '<i class="fas fa-brain"></i> ${t(\'predict.running_ml\')}', 1, False),
    ("Extraindo dados históricos\n", "${t('predict.extracting')}\n", 1, False),
    ("Executando modelo de regressão linear\n", "${t('predict.running_model')}\n", 1, False),
    ("Gerando gráficos interativos\n", "${t('predict.charts')}\n", 1, False),
    ('<i class="fas fa-clock"></i> Isso pode levar 30-90 segundos...', '<i class="fas fa-clock"></i> ${t(\'predict.may_take\')}', 1, False),
    ("                        Sem Dados Históricos\n", "                        ${t('predict.no_data_title')}\n", 2, False),
    (r"Não foram encontrados dados históricos no Oracle para este filegroup\.\s*A análise preditiva requer pelo menos <strong>\$\{t\('predict\.min_7_days'\)\}</strong> de uso\.",
     "${t('predict.no_data_intro')} ${_kpiTp('predict.requires_at_least', 'A análise preditiva requer pelo menos {min} de uso.', { min: '<strong>' + t('predict.min_7_days') + '</strong>' })}", 2, True),
    ("                            Detalhes do FileGroup\n", "                            ${t('predict.fg_details')}\n", 2, False),
    ('<td style="padding: 8px 0; color: var(--color-text-disabled);">Servidor:</td>', '<td style="padding: 8px 0; color: var(--color-text-disabled);">${t(\'predict.server_label\')}</td>', 3, False),
    ("<li>Este filegroup foi criado recentemente</li>", "<li>${t('predict.cause_recent')}</li>", 2, False),
    ("<li>Nome do filegroup diferente na tabela Oracle</li>", "<li>${t('predict.cause_name_mismatch')}</li>", 2, False),
    ("                            O Que Fazer\n", "                            ${t('predict.what_to_do')}\n", 2, False),
    ("<li>Verificar nome do filegroup na tabela Oracle</li>", "<li>${t('predict.check_fg_name')}</li>", 2, False),
    ("onmouseout=\"this.style.background='var(--color-border-strong)'\">\n                            <i class=\"fas fa-times\"></i> Fechar",
     "onmouseout=\"this.style.background='var(--color-border-strong)'\">\n                            <i class=\"fas fa-times\"></i> ${t('predict.close')}", 3, False),
    ("onmouseout=\"this.style.transform='translateY(0)'\"\n                    >\n                        <i class=\"fas fa-times\"></i> Fechar",
     "onmouseout=\"this.style.transform='translateY(0)'\"\n                    >\n                        <i class=\"fas fa-times\"></i> ${t('predict.close')}", 1, False),
    ("cursor: pointer; font-size: 14px;\"\n                    >\n                        Fechar\n                    </button>",
     "cursor: pointer; font-size: 14px;\"\n                    >\n                        ${t('predict.close')}\n                    </button>", 1, False),
    ("                        Script de Análise Não Encontrado\n", "                        ${t('predict.script_title')}\n", 1, False),
    ("O script necessário para análise preditiva não foi encontrado no sistema.", "${t('predict.script_missing')}", 1, False),
    ("                            Detalhes do Erro\n", "                            ${t('predict.error_details')}\n", 1, False),
    ("                            FileGroup Solicitado\n", "                            ${t('predict.fg_requested')}\n", 1, False),
    ("                            Como Resolver\n", "                            ${t('predict.how_to_fix')}\n", 1, False),
    (f"<li>Verifique se o arquivo {CODE} existe na raiz do projeto</li>",
     "<li>${_kpiTp('predict.check_file_exists', 'Verifique se o ficheiro {file} existe na raiz do projeto', { file: '" + CODE + "' })}</li>", 1, False),
    ("<li>Credenciais Oracle incorretas em oracle_to_csv.py</li>", "<li>${t('predict.cause_db_creds')}</li>", 1, False),
    ('<h3 style="color: var(--color-text-primary); margin-bottom: 16px;">Pop-up Bloqueado</h3>', '<h3 style="color: var(--color-text-primary); margin-bottom: 16px;">${t(\'predict.popup_blocked\')}</h3>', 1, False),
    ("Seu navegador bloqueou a abertura do relatório em nova aba.", "${t('predict.popup_msg')}", 1, False),
    ('<i class="fas fa-external-link-alt"></i> Abrir Relatório', '<i class="fas fa-external-link-alt"></i> ${t(\'predict.open_report\')}', 1, False),
]
CHANGELOG_ENTRY = """- **Lote F6a (BUG-003): a modal "Análise Preditiva de Crescimento" segue o idioma** (owner 09/09: "ainda
  continua em português com o inglês seleccionado"). Título, textos de carregamento, ecrãs "Sem Dados
  Históricos", "Script Não Encontrado", erro e pop-up bloqueado, e o botão "Fechar" ganham chaves
  `predict.*` em pt-PT, en-US e es. As referências a "Oracle" nesses textos, herdadas de um antepassado do
  produto, desaparecem. As definições duplicadas dessas funções (a segunda sobrepõe a primeira) ficam
  ambas traduzidas para não sobrar texto cru em código morto. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def norm(s, nl):
    return s.replace("\n", nl) if nl != "\n" else s


def patch_predict(raw, nl, loc, keys):
    lines = [l.rstrip("\r") for l in raw.split("\n")]  # robusto a CRLF/LF mistos
    nl = "\n" if "\r\n" not in raw else "\r\n"
    try:
        s = next(i for i, l in enumerate(lines) if l.strip() == '"predict": {')
        e = next(i for i in range(s + 1, len(lines)) if lines[i].startswith("  }"))
    except StopIteration:
        return None, 'bloco "predict" nao encontrado'
    existing = {re.match(r'\s*"([^"]+)":', lines[i]).group(1) for i in range(s + 1, e) if re.match(r'\s*"([^"]+)":', lines[i])}
    new_lines = []
    for k, v in keys.items():
        val = json.dumps(v[loc], ensure_ascii=False)
        if k in existing:
            idx = next(i for i in range(s + 1, e) if re.match(r'\s*"%s":' % re.escape(k), lines[i]))
            comma = "," if lines[idx].rstrip().endswith(",") else ""
            lines[idx] = f'    "{k}": {val}{comma}'
        else:
            new_lines.append(f'    "{k}": {val},')
    lines[s + 1:s + 1] = new_lines
    out = nl.join(lines)
    try: json.loads(out)
    except Exception as ex: return None, f"json invalido: {ex}"
    return out, None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    problems, outs = [], {}
    keys = json.loads(KEYS.read_bytes().decode("utf-8"))
    html, hnl = read(root / HTML)
    if "t('predict.title')" in html: problems.append("ja aplicado (predict.title no portal)")
    for old, new, exp, is_rx in PATCHES:
        c = len(re.findall(old, html, re.S)) if is_rx else html.count(norm(old, hnl))
        if c != exp: problems.append(f"patch esperado {exp}x, encontrado {c}x: {old[:60]!r}")
    for loc in ("pt", "en", "es"):
        raw, nl = read(root / f"static/i18n/{loc}.json")
        new, err = patch_predict(raw, nl, loc, keys)
        if err: problems.append(f"{loc}.json: {err}")
        else: outs[f"static/i18n/{loc}.json"] = new
    craw, cnl = read(root / CHG); anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada")
    if "Lote F6a (BUG-003)" in craw: problems.append("CHANGELOG: ja aplicado")
    if problems:
        print(f"[ABORT] nada foi escrito ({len(problems)} problemas):"); [print("   -", x) for x in problems]; sys.exit(2)
    if a.dry_run:
        print(f"[DRY] {len(PATCHES)} patches ({sum(p[2] for p in PATCHES)} ocorrencias) no portal, {len(keys)} chaves predict.* em pt/en/es, CHANGELOG OK"); return
    for old, new, exp, is_rx in PATCHES:
        html = re.sub(old, lambda m: new, html, flags=re.S) if is_rx else html.replace(norm(old, hnl), norm(new, hnl))
    (root / HTML).write_bytes(html.encode("utf-8")); print(f"[OK] {HTML}")
    for rel, txt in outs.items(): (root / rel).write_bytes(txt.encode("utf-8")); print(f"[OK] {rel}")
    (root / CHG).write_bytes(craw.replace(anchor, anchor + CHANGELOG_ENTRY.replace("\n", cnl) + cnl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: py -3.14 -m pytest tests/unit/test_i18n_parity.py -q --no-cov ; py -3.14 scripts/i18n_validate.py ; browser Ctrl+F5 -> aba Space, botao de analise preditiva de um filegroup, em EN")


if __name__ == "__main__":
    main()
