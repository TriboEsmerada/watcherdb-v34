# -*- coding: utf-8 -*-
"""Corre um ficheiro .sql de CONSULTA contra a WatcherDB_Intelligence (2026-09-23).

PORQUE EXISTE: o owner autorizou a AI a correr SELECTs (CLAUDE.md, "O que podes
fazer"). Colar resultados no chat perde dados -- uma colagem foi truncada aos
50 mil caracteres a 2026-09-23 e o fim do resultado perdeu-se.

IDENTIDADE: reutiliza api.routers.intelligence.helpers.execute_intelligence_query,
que constroi a ligacao a partir do .env com get_secret() (services/secrets.py).
A password nunca passa por aqui, nunca vai para stdout e nunca entra em argumento
de linha de comando. Trusted_Connection nao e' usado -- a identidade e' a que o
portal ja' usa (sql_monitoring por omissao, INTELLIGENCE_SQL_USER).

GUARDA (o ponto principal): cada instrucao tem de comecar por SELECT ou WITH, e
nenhuma palavra de mutacao pode aparecer fora de comentarios e literais. Se algo
falhar a verificacao, NADA e' executado -- nem as instrucoes que passariam. A
regra "so' consultas" deixa de depender de quem escreve a query.

Uso:
  cd "C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4"
  py docs/context/sql/_run.py docs/context/sql/<ficheiro>.sql
  py docs/context/sql/_run.py <ficheiro>.sql --max 50
  py docs/context/sql/_run.py <ficheiro>.sql --csv C:\\...\\_qout\\saida.csv
  py docs/context/sql/_run.py <ficheiro>.sql --check    (so' valida, nao liga)
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Palavras que nunca podem aparecer numa instrucao (fora de comentarios/literais).
PROIBIDO = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|MERGE|EXEC|EXECUTE|"
    r"GRANT|REVOKE|DENY|BACKUP|RESTORE|SHUTDOWN|RECONFIGURE|DBCC|KILL|WAITFOR|"
    r"OPENROWSET|OPENQUERY|OPENDATASOURCE|BULK|SET|USE|DECLARE|INTO)\b",
    re.IGNORECASE,
)
PROIBIDO_PREFIXO = re.compile(r"\b(xp_|sp_)\w+", re.IGNORECASE)
COMECO_OK = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def separar(sql: str):
    """Percorre o SQL a distinguir literais, comentarios de linha e de bloco.

    Devolve (instrucoes_originais, instrucoes_limpas). As limpas servem so' para
    a guarda -- um comentario que fale de UPDATE nao deve bloquear a consulta, e
    um '--' dentro de um literal nao deve cortar a instrucao a meio.
    """
    orig, limpo = [], []
    buf_o, buf_l = [], []
    i, n = 0, len(sql)
    while i < n:
        c, prox = sql[i], sql[i + 1] if i + 1 < n else ""
        if c == "'":  # literal: copia tal e qual ate' a aspa de fecho ('' escapa)
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            trecho = sql[i:j + 1]
            buf_o.append(trecho)
            buf_l.append("''")  # literal neutralizado para a guarda
            i = j + 1
        elif c == "-" and prox == "-":
            j = sql.find("\n", i)
            j = n if j == -1 else j
            buf_o.append(sql[i:j])
            buf_l.append(" ")
            i = j
        elif c == "/" and prox == "*":
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            buf_o.append(sql[i:j])
            buf_l.append(" ")
            i = j
        elif c == ";":
            orig.append("".join(buf_o))
            limpo.append("".join(buf_l))
            buf_o, buf_l = [], []
            i += 1
        else:
            buf_o.append(c)
            buf_l.append(c)
            i += 1
    if "".join(buf_l).strip():
        orig.append("".join(buf_o))
        limpo.append("".join(buf_l))
    pares = [(o, l) for o, l in zip(orig, limpo) if l.strip()]
    return [p[0] for p in pares], [p[1] for p in pares]


def validar(limpas):
    """Devolve lista de problemas. Vazia = pode correr."""
    problemas = []
    for idx, stmt in enumerate(limpas, 1):
        if not COMECO_OK.match(stmt):
            inicio = stmt.strip()[:40].replace("\n", " ")
            problemas.append(f"instrucao {idx}: nao comeca por SELECT/WITH -- {inicio!r}")
        for m in PROIBIDO.finditer(stmt):
            problemas.append(f"instrucao {idx}: palavra de mutacao {m.group(1).upper()!r}")
        for m in PROIBIDO_PREFIXO.finditer(stmt):
            problemas.append(f"instrucao {idx}: procedimento de sistema {m.group(0)!r}")
    return problemas


def imprimir(linhas, max_linhas):
    if not linhas:
        print("  (sem linhas)")
        return
    cols = list(linhas[0].keys())
    larg = {c: max(len(str(c)), *(len(str(r.get(c, ""))) for r in linhas[:max_linhas])) for c in cols}
    larg = {c: min(w, 40) for c, w in larg.items()}
    print("  " + " | ".join(str(c)[:larg[c]].ljust(larg[c]) for c in cols))
    print("  " + "-+-".join("-" * larg[c] for c in cols))
    for r in linhas[:max_linhas]:
        print("  " + " | ".join(str(r.get(c, ""))[:larg[c]].ljust(larg[c]) for c in cols))
    if len(linhas) > max_linhas:
        print(f"  ... {len(linhas) - max_linhas} linhas omitidas de {len(linhas)} (--max para ver mais, --csv para o todo)")


def carregar_env():
    """Mesma resolucao em 3 niveis de watcherdb_main.py:22-40. Sem isto,
    INTELLIGENCE_SQL_PASSWORD fica vazia e a ligacao morre com
    'SQL Authentication requer senha' -- o .env so' e' lido no arranque do
    servico, nao por um script solto."""
    import os

    try:
        from dotenv import load_dotenv
    except ImportError:
        print("[aviso] python-dotenv ausente; variaveis tem de vir do ambiente")
        return None
    candidatos = []
    wdd = os.environ.get("WATCHERDB_DATA_DIR")
    if wdd:
        candidatos.append(Path(wdd) / ".env")
    # ProgramData SO' quando empacotado (o original condiciona a sys.frozen).
    # Sem esta condicao, um script solto lia o .env de producao em vez do da
    # raiz -- e o de producao nao traz a senha decifravel nesta sessao.
    if getattr(sys, "frozen", False):
        candidatos.append(Path(r"C:\ProgramData\WatcherDB") / ".env")
    candidatos.append(ROOT / ".env")
    for c in candidatos:
        if c.exists():
            load_dotenv(c)
            return c
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Corre um .sql de consulta na Intelligence")
    ap.add_argument("ficheiro")
    ap.add_argument("--max", type=int, default=40, help="linhas a mostrar por bloco (default 40)")
    ap.add_argument("--csv", help="grava todas as linhas em CSV (um ficheiro por bloco se houver varios)")
    ap.add_argument("--check", action="store_true", help="so' valida a guarda, nao liga a base")
    a = ap.parse_args(argv)

    caminho = Path(a.ficheiro)
    if not caminho.is_absolute():
        caminho = (ROOT / caminho) if (ROOT / caminho).exists() else caminho
    sql = caminho.read_text(encoding="utf-8")

    originais, limpas = separar(sql)
    if not originais:
        print("[ABORT] ficheiro sem instrucoes")
        return 2

    problemas = validar(limpas)
    if problemas:
        print(f"[RECUSADO] {caminho.name}: so' consultas sao permitidas. Nada foi executado.")
        for p in problemas:
            print(f"  - {p}")
        return 1

    print(f"[ok] {caminho.name}: {len(originais)} instrucao(oes), todas de leitura")
    if a.check:
        print("--check OK. Nao ligou a base.")
        return 0

    env = carregar_env()
    print(f"[env] {env}" if env else "[env] nenhum .env encontrado")

    from api.routers.intelligence.helpers import (  # noqa: E402
        INTELLIGENCE_DATABASE,
        INTELLIGENCE_SERVER,
        INTELLIGENCE_SQL_USER,
        execute_intelligence_query,
    )

    print(f"[liga] {INTELLIGENCE_SERVER} -> {INTELLIGENCE_DATABASE} como {INTELLIGENCE_SQL_USER}\n")

    for idx, stmt in enumerate(originais, 1):
        print(f"--- bloco {idx} " + "-" * 50)
        linhas = execute_intelligence_query(stmt, raise_on_error=False)
        imprimir(linhas, a.max)
        if a.csv and linhas:
            destino = Path(a.csv)
            if len(originais) > 1:
                destino = destino.with_name(f"{destino.stem}_{idx}{destino.suffix or '.csv'}")
            destino.parent.mkdir(parents=True, exist_ok=True)
            with destino.open("w", newline="", encoding="utf-8-sig") as fh:
                w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
                w.writeheader()
                w.writerows(linhas)
            print(f"  [csv] {destino} ({len(linhas)} linhas)")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
