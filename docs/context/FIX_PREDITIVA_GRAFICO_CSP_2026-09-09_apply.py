"""FIX 2026-09-09 (lote 3 da preditiva) -- o relatorio abre, mas sem grafico e sem estilo.

Sintoma (screenshot do owner, como admin): "Predictive Growth Analysis" abre, os numeros
estao certos (137 dias de historico), mas o grafico sumiu e a pagina esta "bagunçada".
Consola: 3 violacoes de Content-Security-Policy -- script do jsdelivr bloqueado
(script-src 'self' nonce), <style> inline bloqueado, <script> inline bloqueado.

Causa: o portal injecta o HTML do relatorio num iframe about:blank via document.write.
Um iframe about:blank HERDA a CSP do documento pai (a politica estrita de 12/08:
script-src/style-src 'self' + nonce, sem CDNs, tudo auto-hospedado em /static/vendor).
O relatorio gerado pelo script traz um <style> inline, um <script> inline e carrega o
Chart.js de cdn.jsdelivr.net -> os tres bloqueados. Nunca se viu antes porque o relatorio
nunca tinha chegado a gerar nesta maquina (lote 2 de hoje) e, na era em que gerava, o dev
empilhava um middleware permissivo por cima da CSP.

Fix (3 pecas, sem tocar na CSP -- a politica esta certa, o relatorio e' que nao a cumpria):
  1. Chart.js auto-hospedado: copia static/vendor/chartjs/chart.min.js (v4.5.1 UMD) do V6,
     que ja o tem, para o mesmo caminho no V3.4. Sem CDN, como manda o comentario da CSP.
  2. Script do relatorio: <script src> passa a /static/vendor/chartjs/chart.min.js
     (o iframe about:blank resolve URLs relativos contra a origem do portal);
     rodape "Gerado em ... | WatcherDB Intelligence v5 (WatcherDB Data Source)" ->
     "Gerado em ... | WatcherDB" (pedido do owner).
  3. Portal (displayReport viva, ~29308): antes do document.write, injecta o nonce do
     pedido ({{ csp_nonce }}, ja usado noutros blocos do template) em todo o <script>
     e <style> do relatorio que ainda nao tenha nonce, e reescreve qualquer URL antigo do
     jsdelivr para a copia local (relatorios ja gerados em disco continuam a abrir).
     Atributos style="" e handlers continuam permitidos pela CSP via *-attr 'unsafe-inline'.

Uso (raiz do repo):
  py docs/context/FIX_PREDITIVA_GRAFICO_CSP_2026-09-09_apply.py --check
  py docs/context/FIX_PREDITIVA_GRAFICO_CSP_2026-09-09_apply.py --preview DIR
  py docs/context/FIX_PREDITIVA_GRAFICO_CSP_2026-09-09_apply.py

Depois de aplicar:
  py -m pytest tests/unit/test_predictive_report_hardening_20260909.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34     # o script do relatorio e' lido a cada pedido,
                                             # mas o template do portal esta em cache
  Ctrl+F5; Space > Filegroups > Analise (admin): grafico + estilo escuro do relatorio, consola
  sem violacoes de CSP nesse pedido.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V6_CHART = ROOT.parent / "WATCHERDB_V6" / "static" / "vendor" / "chartjs" / "chart.min.js"
DST_CHART = ROOT / "static" / "vendor" / "chartjs" / "chart.min.js"

PORTAL = ROOT / "templates" / "watcherdb_portal.html"
SCRIPT = ROOT / "scripts" / "filegroup_interactive_report_v5_watcherdb.py"
TEST = ROOT / "tests" / "unit" / "test_predictive_report_hardening_20260909.py"

EDITS: list[tuple[Path, str, str, int]] = []


def edit(path: Path, old: str, new: str, count: int = 1) -> None:
    EDITS.append((path, old, new, count))


# --------------------------------------------------------------- script --
edit(SCRIPT,
     '    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>\n',
     '    <!-- 2026-09-09: Chart.js auto-hospedado (CSP do portal: sem CDNs); o iframe do portal\n'
     '         resolve o caminho contra a origem do servico -->\n'
     '    <script src="/static/vendor/chartjs/chart.min.js"></script>\n')

edit(SCRIPT,
     "            Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | WatcherDB Intelligence v5 (WatcherDB Data Source)<br>\n",
     "            Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | WatcherDB<br>\n")

# --------------------------------------------------------------- portal --
edit(PORTAL,
     "            const iframe = document.getElementById('reportFrame');\n"
     "            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;\n"
     "            iframeDoc.open();\n"
     "            iframeDoc.write(htmlContent);\n"
     "            iframeDoc.close();\n",
     "            // 2026-09-09: o iframe about:blank HERDA a CSP do portal (script-src/style-src\n"
     "            // com nonce, sem CDNs). O relatorio traz <style> e <script> inline e carregava o\n"
     "            // Chart.js do jsdelivr -> tudo bloqueado: sem grafico, sem estilo. Injecta-se o\n"
     "            // nonce deste pedido nos blocos inline e qualquer CDN antigo (relatorios ja em\n"
     "            // disco) e' reescrito para a copia auto-hospedada. style=\"\" e handlers continuam\n"
     "            // permitidos pela CSP via *-attr.\n"
     "            const _cspNonce = '{{ csp_nonce }}';\n"
     "            const _safeHtml = String(htmlContent || '')\n"
     "                .replace(/https:\\/\\/cdn\\.jsdelivr\\.net\\/npm\\/chart\\.js@[^\"']+/g, '/static/vendor/chartjs/chart.min.js')\n"
     "                .replace(/<script(?![^>]*\\bnonce=)([\\s>])/gi, `<script nonce=\"${_cspNonce}\"$1`)\n"
     "                .replace(/<style(?![^>]*\\bnonce=)([\\s>])/gi, `<style nonce=\"${_cspNonce}\"$1`);\n"
     "            const iframe = document.getElementById('reportFrame');\n"
     "            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;\n"
     "            iframeDoc.open();\n"
     "            iframeDoc.write(_safeHtml);\n"
     "            iframeDoc.close();\n")

# ----------------------------------------------------------------- test --
TEST_APPEND = '''

def test_report_is_csp_compatible_20260909():
    """O iframe herda a CSP do portal: sem CDN no relatorio, Chart.js auto-hospedado,
    nonce injectado nos blocos inline antes do document.write, rodape 'WatcherDB'."""
    assert "cdn.jsdelivr.net" not in SCRIPT
    assert "/static/vendor/chartjs/chart.min.js" in SCRIPT
    assert (ROOT / "static" / "vendor" / "chartjs" / "chart.min.js").exists()
    assert "Intelligence v5 (WatcherDB Data Source)" not in SCRIPT
    assert "const _cspNonce = '{{ csp_nonce }}';" in PORTAL
    assert "iframeDoc.write(_safeHtml);" in PORTAL
    assert "iframeDoc.write(htmlContent);" not in PORTAL
'''
TEST_MARKER = "def test_report_is_csp_compatible_20260909"


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    preview_dir = None
    if "--preview" in argv:
        i = argv.index("--preview")
        if i + 1 >= len(argv):
            print("--preview precisa de DIR")
            return 2
        preview_dir = Path(argv[i + 1]).resolve()

    if not V6_CHART.exists() and not DST_CHART.exists():
        print(f"[ABORT] Chart.js nao encontrado em {V6_CHART} nem em {DST_CHART}.\n"
              "  Descarrega manualmente (v4.x UMD) para static/vendor/chartjs/chart.min.js:\n"
              "  Invoke-WebRequest https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js -OutFile static\\vendor\\chartjs\\chart.min.js")
        return 1

    contents: dict[Path, str] = {}
    eols: dict[Path, str] = {}
    for p in {e[0] for e in EDITS} | {TEST}:
        if not p.exists():
            print(f"[ABORT] nao existe: {p}")
            return 1
        raw = p.read_bytes().decode("utf-8")
        contents[p] = raw
        eols[p] = "\r\n" if "\r\n" in raw else "\n"

    problems = applied = skipped = 0
    for path, old, new, count in EDITS:
        text = contents[path]
        old = old.replace("\n", eols[path])
        new = new.replace("\n", eols[path])
        if new in text and old not in text:
            skipped += 1
            print(f"[skip] ja aplicado: {path.name}: {old[:60]!r}")
            continue
        n = text.count(old)
        if n != count:
            problems += 1
            print(f"[ABORT] {path.name}: esperado {count}x, encontrado {n}x: {old[:90]!r}")
            continue
        contents[path] = text.replace(old, new)
        applied += 1
        print(f"[ok] {path.name}: {count}x {old[:60]!r}")

    if TEST_MARKER in contents[TEST]:
        print(f"[skip] teste ja presente em {TEST.name}")
    else:
        contents[TEST] = contents[TEST].rstrip(eols[TEST]) + TEST_APPEND.replace("\n", eols[TEST])
        applied += 1
        print(f"[ok] {TEST.name}: +1 teste")

    if problems:
        print(f"\n{problems} anchor(s) falharam -- NADA escrito.")
        return 1
    if check_only:
        print(f"\n--check OK: {applied} edicoes aplicaveis, {skipped} ja aplicadas; "
              f"Chart.js: {'ja existe' if DST_CHART.exists() else 'sera copiado de ' + str(V6_CHART)}. Nada escrito.")
        return 0

    target_root = preview_dir if preview_dir is not None else ROOT
    for path, text in contents.items():
        out = target_root / path.relative_to(ROOT)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(text.encode("utf-8"))
        print(f"[write] {out.relative_to(target_root)}")
    dst = target_root / DST_CHART.relative_to(ROOT)
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DST_CHART if DST_CHART.exists() else V6_CHART, dst)
        print(f"[copy]  {dst.relative_to(target_root)} ({dst.stat().st_size} bytes, Chart.js v4.5.1 UMD do V6)")
    else:
        print(f"[skip]  {dst.relative_to(target_root)} ja existe")

    if preview_dir is not None:
        print(f"\n--preview OK: copias em {preview_dir}. Repo intacto.")
    else:
        print(f"\nAplicado: {applied} edicoes ({skipped} ja estavam). Corre agora:\n"
              "  py -m pytest tests/unit/test_predictive_report_hardening_20260909.py -q --no-cov\n"
              "  Restart-Service WatcherDBWebServiceV34   (depois Ctrl+F5 e Analise como admin)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
