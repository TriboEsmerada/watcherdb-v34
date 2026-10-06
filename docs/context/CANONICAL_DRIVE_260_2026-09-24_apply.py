# -*- coding: utf-8 -*-
"""Canonical V3.4: Drive das tabelas DISK_USAGE passa a VARCHAR(260) (2026-09-24).

Gemeo do lote com o mesmo nome na arvore da V1. A V3.4 carrega a sua propria
copia do canonical, e as duas divergiram -- durante esta sessao apanhei-me a
citar linhas de uma arvore enquanto o especialista citava a outra, e as
contagens nao batiam. Sao ficheiros distintos e cada um precisa do seu patch.

SINTOMA (futuro, nao presente): uma instalacao de raiz a partir do canonical de
hoje cria KPI_MSSQL_DISK_USAGE_STG e _HIST com `Drive VARCHAR(8)`. O recolhedor
grava volume_mount_point completo -- `F:\\Hist_Data_10\\` tem 16 caracteres e
`C:\\ClusterStorage\\I06_TEMPDB\\` tem 29. O INSERT rebenta com "String or
binary data would be truncated" e a recolha de disco daquela instancia morre.

PORQUE SO' AGORA: producao ja' esta' a varchar(256) -- alargada a' mao algures
em Dez/2025. O canonical nunca aprendeu. Verificado na frota a 2026-09-23:
sys.columns diz 256 nas seis tabelas de ambiente vivas e 8 nas duas
STG_BLUE/STG_GREEN legadas (0 linhas, mortas). 279 volumes em 59 instancias,
o mais comprido com 29 caracteres.

AGRAVADO POR e38409f (V1, 2026-09-23): ao remover `WHERE mf.type = 0`, os
volumes dedicados a LOG passaram a entrar -- e sao justamente os que aparecem
como mount points em cluster (`L:\\Logs1\\`, `C:\\ClusterStorage\\I06_LOGS\\`).

O QUE MUDA (2 ficheiros, 2 sitios cada):
  database/INSTALACAO_COMPLETA_UNIFICADA.sql   ~1124 STG, ~1369 HIST
  database/SQLSERVER_KPI_REPLICATION_COMPLETE.sql  ~299 STG, ~460 HIST

Sobre o segundo: aponta para WatcherDB_Intelligence_V2 e vem de uma replicacao
do Oracle de 2025-11-27. NAO confirmei que seja executado hoje. Corrijo-o na
mesma porque deixar uma definicao sabidamente errada no repo e' exactamente o
mecanismo que produziu este drift -- e porque a correccao sao dois numeros.

O QUE **NAO** MUDA, de proposito:
  - KPI_OS_DISK_PERF_STG/_HIST e o parametro @Drive de usp_OS_Disk_Upsert
    (~6816, ~6874, ~7201). Familia WMI: grava so' a letra, MAX(LEN(Drive)) = 2
    em producao. Alargar antes de resolver o filtro `not d.Name.endswith(":")`
    em os_performance.py:524 nao muda nada. Parecer do guardiao do recolhedor
    (2026-09-23): nao tocar nesta wave.
  - KPI_MSSQL_DATAFILES_STG.Drive, que fica em VARCHAR(10) -- o recolhedor
    grava LEFT(caminho, 3) e o ed35ccc deixou de depender dele para juntar o
    Volume_Free_MB.

EFEITO EM PRODUCAO: nenhum. As tabelas vivas ja' estao a 256.

Uso:
  cd "C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4"
  py docs/context/CANONICAL_DRIVE_260_2026-09-24_apply.py --check
  py docs/context/CANONICAL_DRIVE_260_2026-09-24_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "inst": Path("database/INSTALACAO_COMPLETA_UNIFICADA.sql"),
    "repl": Path("database/SQLSERVER_KPI_REPLICATION_COMPLETE.sql"),
}

ANTIGO = """    Instance            VARCHAR(64)     NOT NULL,
    Drive               VARCHAR(8)      NOT NULL,"""

NOVO = """    Instance            VARCHAR(64)     NOT NULL,
    -- 2026-09-24: VARCHAR(8) truncava mount points. Producao ja' estava a 256
    -- (alargada a' mao em Dez/2025); so' o canonical e' que ficou para tras.
    -- Caso real mais comprido na frota: C:\\ClusterStorage\\I06_TEMPDB\\ (29).
    Drive               VARCHAR(260)    NOT NULL,"""


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(
                f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito"
            )
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}

    textos = {k: p.read_bytes().decode("utf-8") for k, p in src.items()}
    if any("Drive               VARCHAR(260)" in t for t in textos.values()):
        print("[ABORT] ja aplicado")
        return 1

    out = {k: _apply(t, [(ANTIGO, NOVO, 2)], REL[k].name) for k, t in textos.items()}
    print("[ok] INSTALACAO: DISK_USAGE_STG e _HIST -> VARCHAR(260)")
    print("[ok] REPLICATION (Intelligence_V2, uso nao confirmado): idem")
    print("[--] KPI_OS_DISK_PERF_* e @Drive de usp_OS_Disk_Upsert NAO tocados (familia WMI)")
    if check:
        print("--check OK. Nada escrito.")
        return 0

    for k, texto in out.items():
        src[k].write_bytes(texto.encode("utf-8"))
        print(f"[write] {REL[k]}")
    print("\nAplicado. Nao e' preciso reiniciar nada -- producao ja' estava a 256.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
