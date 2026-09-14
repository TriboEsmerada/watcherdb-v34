# -*- coding: utf-8 -*-
"""C0 (2026-09-14) -- as classes de defeito que fechei no LIVE, ainda vivas noutros routers.

Medido no log do servico desde o arranque de 14/09, com ficheiro e linha tirados dos FRAMES do
traceback (nao por proximidade do pedido). O que o FIX_API500 (cf7fa64) ja' fechou fica de fora.

  1. 8115 "Arithmetic overflow converting numeric to numeric" -- `modification_counter * 100.0 / rows`
     dentro de DECIMAL(5,2), que so' aguenta ate' 999.99. O contador de modificacoes NAO e' limitado
     pelo numero de linhas: uma tabela de 100 linhas com 1M de modificacoes da' 1.000.000,00 e rebenta.
     4 sitios, todos a mesma expressao. Passa a DECIMAL(18,2): o valor continua a ser informativo
     (dizer "as estatisticas estao 10.000x desactualizadas" e' o ponto do KPI).
     NAO tocado: os outros ~30 DECIMAL(5,2) do repositorio sao percentagens limitadas a 100 por
     construcao (fragmentacao, impacto, espaco livre) -- alargar todos seria ruido.

  2. 451 "Cannot resolve collation conflict ... in UNION ALL, column 3" -- /api/queries/disk-files
     junta `name` de `sys.filegroups` de VARIAS bases num UNION ALL, e o nome herda a collation de
     cada base. Duas bases com collation diferente (medido: Latin1_General_100_CI_AS_KS_WS vs
     Latin1_General_CI_AS_KS_WS) partem a consulta. `COLLATE DATABASE_DEFAULT` na coluna resolve.

  3. "ODBC SQL type -16 is not yet supported" -- SERVERPROPERTY devolve sql_variant, que o driver nao
     sabe transportar. 5 colunas em security_analysis.py sem CAST. (A linha 164 compara sql_variant
     com 1 dentro de um CASE, o que e' valido e nao devolve a coluna -- fica como esta'.)

  4. 207 "Invalid column name 'encryption_state_desc'" -- sys.databases nao tem essa coluna (o estado
     de cifra vive em sys.dm_database_encryption_state). O codigo que a pede NUNCA a le': so' usa
     is_encrypted. Remove-la e' a correccao completa, sem JOIN nem CASE novos.

  Os 3 acima (2,3,4) sao o mesmo endpoint: /api/monitoring/security/server/{id}/summary, que estava
  partido de tres maneiras ao mesmo tempo. O FIX_API500 fechou a quarta (JSONResponse como dict).

  5. Decimal nao serializavel em /api/monitoring/services/overview -- mesma classe do 500 do tempdb
     que fechei no LIVE, noutro router. Helper unico, como o _live_json.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/C0_CLASSES_FORA_DO_LIVE_2026-09-14_apply.py --check
  py docs/context/C0_CLASSES_FORA_DO_LIVE_2026-09-14_apply.py
  py -m pytest tests/unit/test_c0_classes_20260914.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "kpi_service": Path("services/sqlserver_kpi_service.py"),
    "legacy": Path("api/routers/queries/_diagnostics_legacy.py"),
    "queries": Path("modules/monitoring/queries.py"),
    "space": Path("api/routers/queries/space.py"),
    "security": Path("modules/monitoring/security_analysis.py"),
    "svc": Path("api/routers/service_status.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_c0_classes_20260914.py"),
}
MARK = "_svc_json("

# ---- 1) 8115: percentagem de modificacoes nao cabe em DECIMAL(5,2) -----------------------------
OVF_OLD = "(sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(5,2)"
OVF_NEW = "(sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(18,2)"  # C0 2026-09-14: contador nao e' limitado por rows (8115)

EDITS = {
    "kpi_service": [(OVF_OLD, OVF_NEW, 2)],
    "legacy": [(OVF_OLD, OVF_NEW, 1)],
    "queries": [(OVF_OLD, OVF_NEW, 1)],
    # ---- 2) collation no UNION ALL entre bases ------------------------------------------------
    "space": [("name as fg_name ",
               "name COLLATE DATABASE_DEFAULT as fg_name ",  # C0 2026-09-14: bases com collation diferente partiam o UNION ALL (451)
               1)],
    # ---- 3) sql_variant e 4) coluna inexistente ------------------------------------------------
    "security": [
        ("                SERVERPROPERTY('IsIntegratedSecurityOnly') AS is_windows_only\n",
         "                CAST(SERVERPROPERTY('IsIntegratedSecurityOnly') AS INT) AS is_windows_only\n", 1),
        ("                SERVERPROPERTY('ProductVersion') AS product_version,\n"
         "                SERVERPROPERTY('ProductLevel') AS product_level,\n"
         "                SERVERPROPERTY('Edition') AS edition,\n"
         "                SERVERPROPERTY('ProductUpdateLevel') AS update_level\n",
         "                CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)) AS product_version,\n"
         "                CAST(SERVERPROPERTY('ProductLevel') AS NVARCHAR(128)) AS product_level,\n"
         "                CAST(SERVERPROPERTY('Edition') AS NVARCHAR(128)) AS edition,\n"
         "                CAST(SERVERPROPERTY('ProductUpdateLevel') AS NVARCHAR(128)) AS update_level\n", 1),
        ("                d.is_encrypted,\n                d.encryption_state_desc\n",
         "                d.is_encrypted\n", 1),  # C0 2026-09-14: coluna nao existe em sys.databases e nunca era lida (207)
    ],
    # ---- 5) Decimal nao serializavel -------------------------------------------------------------
    "svc": [
        ("from fastapi.responses import JSONResponse\n",
         "from fastapi.responses import JSONResponse\n"
         "from fastapi.encoders import jsonable_encoder\n", 1),
        ("from api.error_helpers import safe_http_error\n",
         "from api.error_helpers import safe_http_error\n"
         "\n"
         "\n"
         "def _svc_json(payload, status_code: int = 200):\n"
         "    \"\"\"JSONResponse com Decimal/datetime/bytes seguros (C0 2026-09-14).\n"
         "\n"
         "    /api/monitoring/services/overview dava 500 \"Object of type Decimal is not JSON\n"
         "    serializable\". Mesma classe do 500 do tempdb no LIVE: em vez de cacar coluna a\n"
         "    coluna, todas as respostas deste router passam por aqui.\n"
         "    \"\"\"\n"
         "    return JSONResponse(status_code=status_code,\n"
         "                        content=jsonable_encoder(payload, custom_encoder={bytes: lambda b: b.hex()}))\n", 1),
        ("JSONResponse(content=", "_svc_json(", 4),
    ],
}

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Fixed\n\n" if False else "## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **C0: as classes de defeito do LIVE, corrigidas nos outros routers** (medido no log de 14/09, ficheiro e\n"
                  "  linha tirados dos frames do traceback). O KPI de estatísticas desactualizadas rebentava com overflow porque\n"
                  "  a percentagem de modificações não cabe em `DECIMAL(5,2)`: o contador não é limitado pelo número de linhas.\n"
                  "  O detalhe de ficheiros por disco partia quando duas bases tinham collation diferente, ao juntar nomes de\n"
                  "  filegroup num `UNION ALL`. E o resumo de segurança estava partido de três maneiras ao mesmo tempo: uma\n"
                  "  coluna que não existe em `sys.databases` e nunca era lida, cinco `SERVERPROPERTY` sem conversão (o driver\n"
                  "  não transporta `sql_variant`), mais o defeito que o lote anterior já fechou. O resumo de serviços passa a\n"
                  "  serializar Decimal como o LIVE. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-14 -- C0: as classes de defeito do LIVE, fora do LIVE.
"""
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _ler(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_percentagem_de_modificacoes_nao_cabe_em_decimal_5_2():
    # sp.modification_counter NAO e' limitado por sp.rows: 100 linhas com 1M de modificacoes = 1.000.000,00
    for rel in ("services/sqlserver_kpi_service.py",
                "api/routers/queries/_diagnostics_legacy.py",
                "modules/monitoring/queries.py"):
        s = _ler(rel)
        assert "(sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(5,2)" not in s, rel
        assert "(sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(18,2)" in s, rel


def test_percentagens_limitadas_ficam_em_decimal_5_2():
    # o lote alarga so' a expressao que pode passar de 100; nao e' uma varredura cega
    s = _ler("modules/monitoring/queries.py")
    assert "CAST(avg_fragmentation_in_percent AS DECIMAL(5,2))" in s


def test_union_all_de_filegroups_com_collation_explicita():
    s = _ler("api/routers/queries/space.py")
    assert "name COLLATE DATABASE_DEFAULT as fg_name" in s


def test_serverproperty_convertido_e_coluna_inexistente_removida():
    s = _ler("modules/monitoring/security_analysis.py")
    assert "encryption_state_desc" not in s
    assert "CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128))" in s
    assert "CAST(SERVERPROPERTY('IsIntegratedSecurityOnly') AS INT)" in s
    # a comparacao dentro do CASE nao precisa de conversao e fica intacta
    assert "WHEN SERVERPROPERTY('IsIntegratedSecurityOnly') = 1" in s


def test_is_encrypted_continua_a_ser_lido():
    # a coluna removida nunca era usada; a que o codigo le' tem de continuar la'
    s = _ler("modules/monitoring/security_analysis.py")
    assert "d.is_encrypted" in s and "d.get('is_encrypted', 0)" in s


def test_resumo_de_servicos_serializa_decimal():
    from api.routers import service_status as svc
    assert "JSONResponse(content=" not in _ler("api/routers/service_status.py")
    resp = svc._svc_json({"mb": Decimal("1.5"), "b": b"\x0a\xff"})
    corpo = json.loads(resp.body)
    assert corpo["mb"] == 1.5 and corpo["b"] == "0aff" and resp.status_code == 200
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:90]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    if MARK in src["svc"].read_bytes().decode("utf-8"):
        print("[ABORT] ja aplicado"); return 1
    out = {}
    for chave, edits in EDITS.items():
        out[chave] = _apply(src[chave].read_bytes().decode("utf-8"), edits, chave)
    if src["changelog"].exists():
        out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    print("[ok] anchors: 4x overflow; 1x collation; 3x seguranca; 3x servicos; changelog")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    compile(TEST_SRC, str(REL["test"]), "exec")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_c0_classes_20260914.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
