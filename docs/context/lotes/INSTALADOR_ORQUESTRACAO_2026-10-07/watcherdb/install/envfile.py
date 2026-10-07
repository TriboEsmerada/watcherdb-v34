"""configure: escreve o .env do produto com as chaves EXPLICITAS (lote E do instalador, 2026-10-07).

Porque explicitas: a omissao do instalador (WatcherDB / watcherdb) difere da omissao do runtime
(WatcherDB_Intelligence / sql_monitoring, watcherdb/core/db_identity.py). Sem a chave no .env uma instalacao
nova ligaria a' base errada. Regras: merge idempotente (chaves existentes mantem-se, salvo --force); um upgrade
nunca reescreve o .env; JWT_SECRET_KEY gerado so' se faltar; passwords entram cifradas (prefixo encrypted:,
services/secrets.py:80) e NUNCA em claro; nada e' escrito em --preview.
"""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

CHAVES_ORDEM = (
    "WATCHERDB_PORT", "WATCHERDB_EDITION",
    "INTELLIGENCE_SERVER", "INTELLIGENCE_DATABASE", "INTELLIGENCE_SQL_USER", "INTELLIGENCE_SQL_PASSWORD",
    "INTELLIGENCE_USE_WINDOWS_AUTH", "JWT_SECRET_KEY",
)


def gerar_jwt() -> str:
    return secrets.token_hex(32)


def ler_env(path: Path) -> Tuple[List[str], Dict[str, int]]:
    """Linhas do ficheiro e indice {CHAVE: numero da linha} (so' linhas CHAVE=valor fora de comentarios)."""
    if not path.exists():
        return [], {}
    linhas = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").split("\n")
    idx: Dict[str, int] = {}
    for i, l in enumerate(linhas):
        s = l.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k = s.split("=", 1)[0].strip()
        if k.startswith("export "):
            k = k[7:].strip()
        idx.setdefault(k, i)
    return linhas, idx


def escrever_env(
    path: Path,
    valores: Dict[str, str],
    *,
    segredos: Optional[Dict[str, str]] = None,
    cifrar: Optional[Callable[[str], str]] = None,
    force: bool = False,
    preview: bool = False,
    gerar_jwt_se_faltar: bool = True,
) -> Dict[str, object]:
    """Escreve/actualiza o .env. `segredos` sao valores em claro que entram cifrados por `cifrar` (obrigatorio se houver).

    Devolve {"ficheiro", "escritas": [chaves], "mantidas": [chaves], "preview": bool}.
    """
    segredos = dict(segredos or {})
    if segredos and cifrar is None:
        raise ValueError("ha' segredos para escrever mas nao ha' funcao de cifra (master key ausente)")
    linhas, idx = ler_env(path)
    escritas: List[str] = []
    mantidas: List[str] = []
    finais: Dict[str, str] = {}
    for k, v in valores.items():
        finais[k] = str(v)
    for k, v in segredos.items():
        finais[k] = cifrar(v)  # type: ignore[misc]
    if gerar_jwt_se_faltar and "JWT_SECRET_KEY" not in idx and "JWT_SECRET_KEY" not in finais:
        finais["JWT_SECRET_KEY"] = gerar_jwt()
    novas = list(linhas)
    for k in [c for c in CHAVES_ORDEM if c in finais] + [c for c in finais if c not in CHAVES_ORDEM]:
        v = finais[k]
        if k in idx and not force:
            mantidas.append(k)
            continue
        linha = f"{k}={v}"
        if k in idx:
            novas[idx[k]] = linha
        else:
            if novas and novas[-1].strip() != "":
                pass
            novas.append(linha)
        escritas.append(k)
    if not preview:
        texto = "\n".join(l for l in novas if l is not None)
        if not texto.endswith("\n"):
            texto += "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
    return {"ficheiro": str(path), "escritas": escritas, "mantidas": mantidas, "preview": preview}
