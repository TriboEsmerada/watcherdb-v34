"""TESTSUKITA V1 - ratchet de regressao + hipoteses de causa (o que o TestSprite chama "root-cause hypothesis",
aqui honesto: e' uma hipotese por assinatura, nunca um veredicto).

Compara a corrida de hoje com a ultima corrida anterior que tenha casos:
  regressao   = ok/aviso ontem -> erro hoje
  nova        = caso que nao existia ontem e esta' com erro hoje
  resolvida   = erro ontem -> ok hoje
  persistente = erro ontem e hoje
  api: endpoints cujo status mudou por perfil (ex.: 200 -> 500, 403 -> 200)
Escreve <dia>/council/RATCHET.json e RATCHET.md; o painel le o JSON. Exit 0 sempre (informativo).
  py scripts/qa/testsukita_ratchet.py [--root docs/qa/externo] [--dia AAAA-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

HIPOTESES = [
    # V1 PASSO 3: assinaturas da 1.a corrida do v1 (restart do servico a meio; re-render do dashboard)
    (r"ERR_CONNECTION_REFUSED|Page\.goto|net::ERR_|ERR_EMPTY_RESPONSE", "servico em baixo ou reiniciado durante a corrida: ver council/service_log_window.log ('Shutting down' / 'Started server process') e Event Log 7039/7031"),
    (r"dashboard sem cartoes", "dashboard re-renderizou entre a espera e a leitura (refresh 30 s); se persistir, dashboard realmente vazio"),
    (r"429|rate limit", "rate limit do login (5/min): corridas seguidas ou scripts do externo a mais; nao e' defeito do portal"),
    (r"AbortError", "pedido cancelado pela troca de aba: ruido, nao defeito"),
    (r"falhou com 401|Credenciais invalidas|conta desactivada|bloqueada", "credencial/perfil no .env.qa ou conta bloqueada (15 min apos 5 falhas)"),
    (r"tem role '", "conta configurada no perfil errado (.env.qa)"),
    (r"\b5\d\d\b.*GET|respostas 5xx|http5xx", "erro do servico: ver council/service_log_window.log na mesma janela"),
    (r"nao terminou em \d+ ms|Timeout|timeout", "instancia lenta ou sem resposta (WMI/DMV); comparar com a mesma aba noutras noites"),
    (r"ReferenceError|TypeError|SyntaxError", "excepcao JS do portal: defeito real, ver playwright/ (screenshot+trace) e dom/"),
    (r"nao filtrou|contagem nao acompanha|perdeu o foco", "regressao do filtro de bases (FIX DB-FILTER 2fad907)"),
    (r"nao cabe na janela|sobrepoe", "regressao de layout (UX-05 0ce813e)"),
    (r"modal esta' vazia|modal nao ficou visivel", "drill-down do cartao: endpoint /instances/<kpi> ou handler do cartao"),
    (r"instancias distintas", "cartao e modal com unidades diferentes (regra unica do Always On ce0db42)"),
    (r"sem credenciais", "perfil sem conta no .env.qa (admin: criar qa_admin)"),
]


def hipotese(texto: str) -> str:
    for rx, h in HIPOTESES:
        if re.search(rx, texto, re.I):
            return h
    return "sem assinatura conhecida: ler o JSON do caso e o screenshot"


def estado(j: dict) -> str:
    if j.get("pageerrors") or j.get("console_errors") or j.get("http5xx"):
        return "err"
    return "warn" if j.get("warn") else "ok"


def assinatura(j: dict) -> str:
    return " | ".join((j.get("pageerrors") or [])[:2] + (j.get("console_errors") or [])[:2] + (j.get("http5xx") or [])[:2] + (j.get("warn") or [])[:1])


def carrega(d: Path) -> dict:
    out = {}
    for f in (d / "council" / "cases").glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        out[f"{j.get('perfil')}/{j.get('caso')}"] = j
    return out


def api_status(casos: dict) -> dict:
    out = {}
    for k, j in casos.items():
        if j.get("caso") == "api_smoke":
            for e in j.get("endpoints", []):
                out[f"{j.get('perfil')} {e['path']}"] = e["status"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "docs" / "qa" / "externo"))
    ap.add_argument("--dia", default=None)
    a = ap.parse_args()
    root = Path(a.root)
    dias = sorted(d for d in root.iterdir() if d.is_dir() and DIA_RE.match(d.name) and (d / "council" / "cases").exists())
    if not dias:
        print("sem corridas"); return
    hoje = root / a.dia if a.dia else dias[-1]
    anteriores = [d for d in dias if d.name < hoje.name and any((d / "council" / "cases").glob("*.json"))]
    prev = anteriores[-1] if anteriores else None
    H, P = carrega(hoje), (carrega(prev) if prev else {})
    r = {"dia": hoje.name, "anterior": prev.name if prev else None, "regressoes": [], "novas": [], "resolvidas": [], "persistentes": [], "api_mudou": []}
    for k, j in sorted(H.items()):
        e, ep = estado(j), (estado(P[k]) if k in P else None)
        item = {"caso": k, "assinatura": assinatura(j)[:300], "hipotese": hipotese(assinatura(j))}
        if e == "err" and ep in ("ok", "warn"):
            r["regressoes"].append(item)
        elif e == "err" and ep is None:
            r["novas"].append(item)
        elif e == "err" and ep == "err":
            r["persistentes"].append(item)
        elif e != "err" and ep == "err":
            r["resolvidas"].append({"caso": k})
    ah, ap_ = api_status(H), api_status(P)
    for k, s in sorted(ah.items()):
        if k in ap_ and ap_[k] != s:
            r["api_mudou"].append({"endpoint": k, "antes": ap_[k], "hoje": s})
    r["resumo"] = {x: len(r[x]) for x in ("regressoes", "novas", "resolvidas", "persistentes", "api_mudou")}
    (hoje / "council" / "RATCHET.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Ratchet {hoje.name} vs {r['anterior'] or 'sem anterior'}", ""]
    for sec in ("regressoes", "novas", "persistentes"):
        md.append(f"## {sec} ({len(r[sec])})")
        md += [f"- **{i['caso']}** — {i['assinatura'][:160]}\n  - hipotese: {i['hipotese']}" for i in r[sec]] or ["- nenhuma"]
        md.append("")
    md.append(f"## resolvidas ({len(r['resolvidas'])})"); md += [f"- {i['caso']}" for i in r["resolvidas"]] or ["- nenhuma"]; md.append("")
    md.append(f"## api mudou ({len(r['api_mudou'])})"); md += [f"- {i['endpoint']}: {i['antes']} -> {i['hoje']}" for i in r["api_mudou"]] or ["- nenhum"]
    (hoje / "council" / "RATCHET.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"ratchet {hoje.name} vs {r['anterior']}: " + ", ".join(f"{k}={v}" for k, v in r["resumo"].items()))


if __name__ == "__main__":
    main()
