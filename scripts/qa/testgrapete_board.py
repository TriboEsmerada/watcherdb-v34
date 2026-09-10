"""TESTGRAPETE TG-1b - painel estatico das corridas (council afirma, qa-externo confere).

Le docs/qa/externo/<AAAA-MM-DD>/ (council/cases/*.json, externo/results.json,
externo/*.log, SUMMARY.md) e escreve:
  docs/qa/externo/index.html            painel: linha do tempo + ultima corrida
  docs/qa/externo/<dia>/board.html      pagina da corrida

Sem servidor, sem dependencias, sem CDN: abre por file://. Um tema so'.
Uso:  py scripts/qa/testgrapete_board.py [--root docs/qa/externo] [--dias 30]
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CSS = """
*{box-sizing:border-box}body{margin:0;background:#0f151d;color:#e6ecf3;font:14px/1.5 system-ui,Segoe UI,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:24px}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px;color:#aab6c4}
.meta{color:#76839a;font-size:13px}.tl{display:flex;gap:4px;flex-wrap:wrap;margin:10px 0}
.tl a{display:block;width:22px;height:22px;border-radius:4px;text-decoration:none}.tl .g{background:#1e8a5a}.tl .r{background:#c0392b}
.tl .a{background:#b8740f}.tl .n{background:#26313f}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media(max-width:900px){.cols{grid-template-columns:1fr}}
.card{background:#161e29;border:1px solid #26313f;border-radius:8px;padding:14px}.card h3{margin:0 0 8px;font-size:15px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #26313f;vertical-align:top}
th{color:#76839a;font-weight:600;font-size:12px;text-transform:uppercase}td.n{text-align:right;font-variant-numeric:tabular-nums}
.chip{display:inline-block;padding:1px 7px;border-radius:3px;font-size:11px;font-weight:600}.ok{background:#153224;color:#5ccf95}
.err{background:#3a1c1a;color:#f07a6d}.warn{background:#3a2c14;color:#e2a54a}.na{background:#26313f;color:#aab6c4}
a{color:#6ea3f0}.div{border-left:4px solid #e2a54a}.div li{margin:4px 0}pre{white-space:pre-wrap;font-size:12px;color:#aab6c4}
"""


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def carrega_corrida(d: Path) -> dict:
    casos = []
    for f in sorted((d / "council" / "cases").glob("*.json")) if (d / "council" / "cases").exists() else []:
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        erros = len(j.get("pageerrors", [])) + len(j.get("console_errors", [])) + len(j.get("http5xx", []))
        j["_estado"] = "err" if erros else ("warn" if j.get("warn") else "ok")
        j["_ficheiro"] = f
        casos.append(j)
    ext = []
    rj = d / "externo" / "results.json"
    if rj.exists():
        try:
            raw = json.loads(rj.read_text(encoding="utf-8"))
            ext = raw if isinstance(raw, list) else [raw]
        except Exception:
            ext = []
    for e in ext:
        log = d / "externo" / (Path(e.get("script", "")).stem + ".log")
        e["_log"] = log if log.exists() else None
        e["_linhas"] = sum(1 for _ in log.open(encoding="utf-8", errors="replace")) if log.exists() else 0
    head, base = "", ""
    s = d / "SUMMARY.md"
    if s.exists():
        m = re.search(r"HEAD (\S+), (\S+)\)", s.read_text(encoding="utf-8", errors="replace"))
        if m:
            head, base = m.group(1), m.group(2)
    c_err = sum(1 for c in casos if c["_estado"] == "err")
    c_warn = sum(1 for c in casos if c["_estado"] == "warn")
    e_err = sum(1 for e in ext if e.get("exit") not in (0, None))
    if not casos:
        # TG-1 PASSO 5: sem casos do council a corrida nao mediu nada -> cinzento,
        # mesmo que o externo tenha corrido.
        estado = "n"
    elif c_err:
        estado = "r"
    elif c_warn or e_err:
        estado = "a"
    else:
        estado = "g"
    return {"dia": d.name, "dir": d, "casos": casos, "ext": ext, "head": head, "base": base,
            "c_err": c_err, "c_warn": c_warn, "e_err": e_err, "estado": estado}


def divergencias(run: dict) -> list[str]:
    out = []
    casos, ext = run["casos"], run["ext"]
    if casos and ext:
        if run["c_err"] == 0 and run["e_err"] > 0:
            nomes = ", ".join(e.get("script", "?") for e in ext if e.get("exit") not in (0, None))
            out.append(f"Council verde, qa-externo com exit != 0 em: {nomes}. O que o externo mede que o council nao ve?")
        if run["c_err"] > 0 and run["e_err"] == 0:
            out.append("Council com erro e qa-externo limpo: o externo nao cobre o que rebentou. Candidato a script novo do externo.")
    for c in casos:
        if c["_estado"] == "err":
            out.append(f"[{c.get('perfil')}/{c.get('caso')}] " + "; ".join(
                (c.get("pageerrors") or c.get("http5xx") or c.get("console_errors") or ["?"])[:2]))
    for c in casos:
        if c["_estado"] == "warn":
            out.append(f"[{c.get('perfil')}/{c.get('caso')}] aviso: {c['warn'][0]}")
    if not casos and not ext:
        out.append("Corrida sem evidencias (bundle vazio): o job correu? ver NIGHTLY_LOG.md")
    return out


def rel(a: Path, base: Path) -> str:
    try:
        return a.relative_to(base).as_posix()
    except ValueError:
        return a.as_posix()


def tabela_council(run: dict, base: Path) -> str:
    if not run["casos"]:
        return "<p class=meta>sem casos</p>"
    linhas = []
    for c in sorted(run["casos"], key=lambda x: (x.get("perfil", ""), x.get("caso", ""))):
        chip = {"ok": "ok", "err": "err", "warn": "warn"}[c["_estado"]]
        srv = (c.get("server") or {}).get("name", "") if isinstance(c.get("server"), dict) else ""
        linhas.append(
            f"<tr><td>{esc(c.get('perfil'))}</td><td>{esc(c.get('caso'))}</td><td class=n>{esc(c.get('load_ms'))}</td>"
            f"<td class=n>{esc(c.get('dom_nodes'))}</td><td>{esc(srv)}</td>"
            f"<td><span class='chip {chip}'>{c['_estado'].upper()}</span></td>"
            f"<td><a href='{esc(rel(c['_ficheiro'], base))}'>json</a></td></tr>")
    return ("<table><tr><th>perfil</th><th>caso</th><th>load ms</th><th>DOM</th><th>servidor</th><th>estado</th><th></th></tr>"
            + "".join(linhas) + "</table>")


def tabela_externo(run: dict, base: Path) -> str:
    if not run["ext"]:
        return "<p class=meta>sem scripts</p>"
    linhas = []
    for e in run["ext"]:
        ex = e.get("exit")
        chip = "ok" if ex == 0 else ("na" if ex is None else "err")
        link = f"<a href='{esc(rel(e['_log'], base))}'>log</a>" if e.get("_log") else ""
        linhas.append(f"<tr><td>{esc(e.get('script'))}</td><td class=n><span class='chip {chip}'>{esc(ex)}</span></td>"
                      f"<td class=n>{e.get('_linhas', 0)}</td><td>{link}</td></tr>")
    return "<table><tr><th>script</th><th>exit</th><th>linhas</th><th></th></tr>" + "".join(linhas) + "</table>"


def timeline(runs: list[dict], base: Path) -> str:
    itens = []
    for r in runs:
        href = rel(r["dir"] / "board.html", base)
        itens.append(f"<a class='{r['estado']}' href='{esc(href)}' title='{esc(r['dia'])}: council {r['c_err']} erro / {r['c_warn']} aviso; externo {r['e_err']} exit!=0'></a>")
    return "<div class=tl>" + "".join(itens) + "</div>"


def pagina(run: dict, runs: list[dict], base: Path, titulo: str) -> str:
    divs = divergencias(run)
    return f"""<!doctype html><html lang="pt"><head><meta charset="utf-8"><title>{esc(titulo)}</title><style>{CSS}</style></head><body><div class=wrap>
<h1>TestGrapete <span class=meta>{esc(run['dia'])}</span></h1>
<div class=meta>HEAD {esc(run['head'] or '?')} · {esc(run['base'] or '?')} · council {len(run['casos'])} casos ({run['c_err']} erro, {run['c_warn']} aviso) · qa-externo {len(run['ext'])} scripts ({run['e_err']} com exit != 0)</div>
<h2>Linha do tempo</h2>{timeline(runs, base)}
<div class=cols>
<div class=card><h3>Council afirma</h3>{tabela_council(run, base)}</div>
<div class=card><h3>QA-externo confere</h3>{tabela_externo(run, base)}</div>
</div>
<h2>Divergencias e achados candidatos</h2>
<div class='card div'>{"<ul>" + "".join(f"<li>{esc(x)}</li>" for x in divs) + "</ul>" if divs else "<p class=meta>nenhuma: as duas metades concordam</p>"}</div>
<p class=meta>Gerado por scripts/qa/testgrapete_board.py. Evidencias em {esc(rel(run['dir'], base))}/ (screenshots e traces so' em falha, em council/playwright/).</p>
</div></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "docs" / "qa" / "externo"))
    ap.add_argument("--dias", type=int, default=30)
    a = ap.parse_args()
    root = Path(a.root)
    dirs = sorted([d for d in root.iterdir() if d.is_dir() and DIA_RE.match(d.name)]) if root.exists() else []
    runs = [carrega_corrida(d) for d in dirs][-a.dias:]
    if not runs:
        root.mkdir(parents=True, exist_ok=True)
        vazio = {"dia": "sem corridas", "dir": root, "casos": [], "ext": [], "head": "", "base": "",
                 "c_err": 0, "c_warn": 0, "e_err": 0, "estado": "n"}
        (root / "index.html").write_text(pagina(vazio, [], root, "TestGrapete"), encoding="utf-8")
        print("index.html escrito (sem corridas)")
        return
    for r in runs:
        (r["dir"] / "board.html").write_text(pagina(r, runs, r["dir"], f"TestGrapete {r['dia']}"), encoding="utf-8")
    ultimo = runs[-1]
    (root / "index.html").write_text(pagina(ultimo, runs, root, "TestGrapete"), encoding="utf-8")
    print(f"index.html + {len(runs)} board.html escritos (ultima corrida {ultimo['dia']}, estado {ultimo['estado']})")


if __name__ == "__main__":
    main()
