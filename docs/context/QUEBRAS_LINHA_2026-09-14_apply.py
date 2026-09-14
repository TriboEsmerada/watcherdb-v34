# -*- coding: utf-8 -*-
"""Quebras de linha (2026-09-14) -- repara dois ficheiros e protege os documentos de contexto.

  1. docs/context/CONTEXT.md passou de LF (446 linhas, commit 10a4855) a CRLF (454 linhas, e0be54f).
     O conteudo novo eram 8 linhas; o resto foi o ficheiro inteiro com outras quebras. Causa: a AI
     acrescentou ao blackboard com Path.write_text, que no Windows converte "\\n" em "\\r\\n", e o
     ficheiro nao tinha regra no .gitattributes. Estraga o git blame do blackboard inteiro.
  2. static/i18n/pt-BR.json tem terminacoes mutiladas (\\r\\r\\r\\n na copia de trabalho). A regra
     eol=lf NAO resolveu no commit: removeu um CR e deixou 178 linhas com \\r\\r\\n no repositorio.
     O JSON continua valido; a corrupcao e que ficou no historico.

O que faz: reescreve os dois ficheiros so com LF, verifica que o conteudo e IDENTICO (texto sem CR
para o .md; json.loads igual para o .json), e acrescenta ao .gitattributes uma regra para os
documentos de contexto, para isto nao voltar a acontecer.

Uso:
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/QUEBRAS_LINHA_2026-09-14_apply.py --check
  py docs/context/QUEBRAS_LINHA_2026-09-14_apply.py
  git diff --ignore-cr-at-eol --stat      (esperado: so o .gitattributes muda de conteudo)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALVOS = [Path("docs/context/CONTEXT.md"), Path("static/i18n/pt-BR.json")]
ATTR = ROOT / ".gitattributes"
REGRA = "docs/context/*.md text eol=lf"


def so_lf(b: bytes) -> bytes:
    # qualquer sequencia de CR antes de um LF passa a LF; CR soltos (sem LF) nao existem nestes ficheiros
    return re.sub(rb"\r+\n", b"\n", b)


def main(argv):
    check = "--check" in argv
    planos = []
    for rel in ALVOS:
        p = ROOT / rel
        antes = p.read_bytes()
        depois = so_lf(antes)
        if b"\r" in depois:
            print(f"[ABORT] {rel}: sobram CR soltos depois da normalizacao -- nada escrito"); return 1
        # conteudo tem de ser identico, so as quebras mudam
        if rel.suffix == ".json":
            if json.loads(antes.decode("utf-8")) != json.loads(depois.decode("utf-8")):
                print(f"[ABORT] {rel}: o JSON mudaria de conteudo -- nada escrito"); return 1
        elif antes.replace(b"\r", b"") != depois:
            print(f"[ABORT] {rel}: o texto mudaria de conteudo -- nada escrito"); return 1
        crs = antes.count(b"\r")
        linhas = depois.count(10)   # 10 = byte do LF; evita confundir a quebra real com o texto "\n"
        print(f"[ok] {rel}: {crs} CR a remover, conteudo identico, {linhas} linhas LF")
        planos.append((p, depois, crs))

    attr = ATTR.read_bytes().decode("utf-8") if ATTR.exists() else ""
    precisa_regra = REGRA not in attr
    print(f"[ok] .gitattributes: {'acrescenta' if precisa_regra else 'ja tem'} a regra '{REGRA}'")

    if check:
        print("--check OK. Nada escrito."); return 0
    for p, depois, crs in planos:
        if crs:
            p.write_bytes(depois); print(f"[write] {p.relative_to(ROOT)}")
    if precisa_regra:
        base = attr if attr.endswith("\n") or not attr else attr + "\n"
        ATTR.write_bytes((base + "# 2026-09-14: documentos de contexto em LF (o blackboard virou CRLF inteiro num commit)\n"
                          + REGRA + "\n").encode("utf-8"))
        print("[write] .gitattributes")
    print("\nFeito. Confirma com: git diff --ignore-cr-at-eol --stat")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
