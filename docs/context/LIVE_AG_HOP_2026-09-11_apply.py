# -*- coding: utf-8 -*-
"""LIVE AG HOP (2026-09-11, GO do owner) -- o canal AlwaysOn do LIVE salta para a primaria.

Facto medido a 11/09: numa secundaria, sys.dm_hadr_database_replica_states so' devolve a linha local.
Por isso o canal AlwaysOn aberto no SQLHDSPRD405 (secundaria) mostrava so' as suas linhas e lag "n/d"
em todas -- honesto, mas nao da o numero que interessa (MYBAGP2 com 111 GB de redo). Mesmo padrao do
drill "Acompanhar resume": quem e' a primaria vem de sys.dm_hadr_availability_group_states.primary_replica,
visivel em QUALQUER no'.

Comportamento novo do GET /api/v1/live/{instance}/alwayson:
  - le' as linhas locais (como antes) + uma query auxiliar (AG -> primaria, nome local);
  - para cada AG cuja primaria NAO e' a instancia pedida, agrupa por primaria e (max. 2 saltos, 5 s cada)
    le' ALWAYSON_SQL na primaria; as linhas desses AGs passam a vir da primaria (todas as replicas, filas,
    lag por delta de commits). AGs em que a local e' primaria mantem as linhas locais;
  - qualquer falha no salto mantem as linhas locais + nota; nunca 503 por causa do salto;
  - resposta ganha "hops": [{ag, primary, server_id}] e "notes": [].
Front: linha "Dados lidos na primária X — esta instância é secundária" no topo da tabela.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/LIVE_AG_HOP_2026-09-11_apply.py --check
  py docs/context/LIVE_AG_HOP_2026-09-11_apply.py
  py -m pytest tests/unit/test_live_ag_hop_20260911.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > SQLHDSPRD405_I01 > AG
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "router": Path("api/routers/live_monitoring.py"),
    "portal": Path("templates/watcherdb_portal.html"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_live_ag_hop_20260911.py"),
}
MARK = "ALWAYSON_PRIMARIES_SQL"

R_OLD = '''@router.get("/{instance}/alwayson")
async def get_alwayson_live(instance: str):
    """AlwaysOn AG status + queues em tempo real."""
    rows, err = _query_instance(instance, ALWAYSON_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)
    for r in (rows or []):
        if r.get("last_commit_time") and hasattr(r["last_commit_time"], "isoformat"):
            r["last_commit_time"] = r["last_commit_time"].isoformat()
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "replicas": rows or [],
    })
'''

R_NEW = '''# 2026-09-11: quem e' a primaria de cada AG -- estado do grupo replicado pelo cluster, visivel em
# qualquer no' (ao contrario de dm_hadr_database_replica_states, que numa secundaria so' tem a linha local).
ALWAYSON_PRIMARIES_SQL = """
SET NOCOUNT ON;
SELECT ag.name AS ag_name,
       ags.primary_replica,
       CAST(@@SERVERNAME AS NVARCHAR(256)) AS local_server  -- @@SERVERNAME: e' o par de replica_server_name (host renomeado sem sp_dropserver: ServerName difere)
FROM sys.availability_groups ag WITH (NOLOCK)
JOIN sys.dm_hadr_availability_group_states ags WITH (NOLOCK) ON ags.group_id = ag.group_id;
"""

AG_HOP_MAX = 2        # primarias distintas por pedido
AG_HOP_TIMEOUT_S = 5  # por salto; o canal faz polling de 5 s


def _ag_norm(name) -> str:
    """'host\\\\inst' / 'HOST\\\\INST,1433' / 'host.dom\\\\inst' -> 'HOST\\\\INST' (comparacao entre primary_replica e ServerName)."""
    s = str(name or "").strip().upper().split(",")[0]
    host, _, inst = s.partition("\\\\")
    return host.split(".")[0] + (("\\\\" + inst) if inst else "")


def _ag_sid(name) -> str:
    """'HOST\\\\INST' -> 'HOST_INST' (formato server_id do pool)."""
    return _ag_norm(name).replace("\\\\", "_")


def _alwayson_hop(instance: str, rows: list) -> tuple[list, list, list]:
    """Substitui as linhas dos AGs cuja primaria e' outra instancia pelas linhas lidas nessa primaria.
    Nunca levanta: qualquer falha mantem as linhas locais e regista uma nota."""
    hops, notes = [], []
    prim_rows, err = _query_instance(instance, ALWAYSON_PRIMARIES_SQL, timeout=AG_HOP_TIMEOUT_S)
    if err or not prim_rows:
        if err:
            notes.append(f"primary_replica: {str(err)[:120]}")
        return rows, hops, notes
    local = _ag_norm(prim_rows[0].get("local_server"))
    by_primary: dict = {}
    for p in prim_rows:
        prim = p.get("primary_replica")
        if not prim:
            notes.append(f"{p.get('ag_name')}: primaria desconhecida (AG offline ou sem quorum)")
            continue
        if _ag_norm(prim) == local:
            continue
        by_primary.setdefault(_ag_norm(prim), set()).add(str(p.get("ag_name") or ""))
    if not by_primary:
        return rows, hops, notes
    out = list(rows)
    for prim, ags in list(by_primary.items())[:AG_HOP_MAX]:
        sid = _ag_sid(prim)
        if sid.upper() == str(instance or "").upper():
            continue
        prows, perr = _query_instance(sid, ALWAYSON_SQL, timeout=AG_HOP_TIMEOUT_S)
        if perr or prows is None:
            notes.append(f"{sid}: {str(perr or 'sem conexao')[:120]}")
            continue
        fetched = [r for r in prows if str(r.get("ag_name") or "") in ags]
        out = [r for r in out if str(r.get("ag_name") or "") not in ags] + fetched
        for ag in sorted(ags):
            hops.append({"ag": ag, "primary": prim, "server_id": sid})
    if len(by_primary) > AG_HOP_MAX:
        notes.append(f"{len(by_primary) - AG_HOP_MAX} primaria(s) nao consultada(s) (limite {AG_HOP_MAX})")
    return out, hops, notes


@router.get("/{instance}/alwayson")
def get_alwayson_live(instance: str):
    """AlwaysOn AG status + queues em tempo real. Numa secundaria, as linhas dos AGs vem da primaria
    (2026-09-11): so' la' existem as linhas de todas as replicas e o lag por delta de commits.

    `def` e nao `async def` (parecer sql-deep-reviewer 11/09): pyodbc e' sincrono e o salto pode
    fazer ate' 3 round-trips; num `async def` isso bloqueava o event loop para todos os utilizadores.
    Como `def`, o FastAPI corre-o no threadpool. Os restantes endpoints do LIVE tem o mesmo padrao
    (1 round-trip cada) -- lote proprio, registado no CONTEXT.md."""
    rows, err = _query_instance(instance, ALWAYSON_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)
    rows, hops, notes = _alwayson_hop(instance, rows or [])
    for r in rows:
        if r.get("last_commit_time") and hasattr(r["last_commit_time"], "isoformat"):
            r["last_commit_time"] = r["last_commit_time"].isoformat()
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "replicas": rows,
        "hops": hops, "notes": notes,
    })
'''

P_EDITS = [
    ("""        function _liveRenderAlwaysOn(data) {
            const replicas = data.replicas || [];
""",
     """        function _liveRenderAlwaysOn(data) {
            const replicas = data.replicas || [];
            // 2026-09-11: numa secundaria as linhas vem da primaria -- dizer de onde vieram
            const _hops = Array.isArray(data.hops) ? data.hops : [];
            const _prims = [...new Set(_hops.map(x => x.primary))];
            const _hopNote = _prims.length
                ? `<div style="margin-bottom:8px;padding:6px 10px;border-left:3px solid #3b82f6;background:var(--color-bg-sunken);color:var(--color-text-tertiary);font-size:12px;">${_diagEsc(_kpiTp('live.ag_from_primary', 'Dados lidos na primária {primary} — esta instância é secundária', { primary: _prims.join(', ') }))}</div>`
                : '';
""", 1),
    ("""            let h = '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="background:var(--color-bg-panel);color:var(--color-text-tertiary);position:sticky;top:0;"><th style="padding:5px 8px;text-align:left;">AG</th>""",
     """            let h = _hopNote + '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="background:var(--color-bg-panel);color:var(--color-text-tertiary);position:sticky;top:0;"><th style="padding:5px 8px;text-align:left;">AG</th>""", 1),
]

KEYS = {
    "pt": "Dados lidos na primária {primary} — esta instância é secundária",
    "en": "Data read on primary {primary} — this instance is a secondary",
    "es": "Datos leídos en la primaria {primary} — esta instancia es secundaria",
}
ANCHOR = {"pt": '    "error_http": "Erro HTTP {code}",\n', "en": '    "error_http": "HTTP error {code}",\n',
          "es": '    "error_http": "Error HTTP {code}",\n'}

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **LIVE › AlwaysOn: aberto numa secundária, o canal mostra a visão da primária** (GO do owner 11/09).\n"
                  "  Numa secundária a DMV só devolve a linha local, e o lag saía \"n/d\" em todas as linhas. O endpoint pergunta\n"
                  "  ao estado do grupo quem é a primária de cada AG (visível em qualquer nó), salta até ela (máx. 2 primárias,\n"
                  "  5 s cada) e devolve todas as réplicas com filas e lag por delta de commits; se o salto falhar, ficam as\n"
                  "  linhas locais com nota, nunca 503. A tabela diz de onde vieram os dados. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-11 -- LIVE alwayson: numa secundaria as linhas vem da primaria (hop), sem nunca dar 503 pelo salto.
"""
import json
from pathlib import Path

from api.routers import live_monitoring as lm

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def _local_rows():
    return [{"ag_name": "AG1", "replica_server_name": "HOSTB\\I01", "role_desc": "SECONDARY", "database_name": "DB1",
             "commit_lag_sec": None, "last_commit_time": None}]


def _primary_rows():
    return [{"ag_name": "AG1", "replica_server_name": "HOSTA\\I01", "role_desc": "PRIMARY", "database_name": "DB1", "commit_lag_sec": 0},
            {"ag_name": "AG1", "replica_server_name": "HOSTB\\I01", "role_desc": "SECONDARY", "database_name": "DB1", "commit_lag_sec": 42},
            {"ag_name": "OTHER", "replica_server_name": "HOSTA\\I01", "role_desc": "PRIMARY", "database_name": "X", "commit_lag_sec": 0}]


def test_norm_and_sid():
    assert lm._ag_norm("hosta.dom.local\\i01,1433") == "HOSTA\\I01"
    assert lm._ag_norm("HOSTA") == "HOSTA"
    assert lm._ag_sid("HOSTA\\I01") == "HOSTA_I01"


def test_secondary_hops_to_primary(monkeypatch):
    calls = []

    def fake(instance, sql, database="master", timeout=10):
        calls.append((instance, "PRIM" if "local_server" in sql else "AG", timeout))
        if "local_server" in sql:  # ALWAYSON_SQL menciona is_primary_replica num comentario
            return [{"ag_name": "AG1", "primary_replica": "HOSTA\\I01", "local_server": "HOSTB\\I01"}], None
        if instance == "HOSTA_I01":
            return _primary_rows(), None
        return _local_rows(), None

    monkeypatch.setattr(lm, "_query_instance", fake)
    body = json.loads(lm.get_alwayson_live("HOSTB_I01").body)
    assert body["hops"] == [{"ag": "AG1", "primary": "HOSTA\\I01", "server_id": "HOSTA_I01"}]
    names = sorted((r["replica_server_name"], r["role_desc"]) for r in body["replicas"])
    assert names == [("HOSTA\\I01", "PRIMARY"), ("HOSTB\\I01", "SECONDARY")]  # OTHER (AG nao local) fica de fora
    assert [r for r in body["replicas"] if r["role_desc"] == "SECONDARY"][0]["commit_lag_sec"] == 42
    assert ("HOSTA_I01", "AG", lm.AG_HOP_TIMEOUT_S) in calls


def test_primary_does_not_hop(monkeypatch):
    def fake(instance, sql, database="master", timeout=10):
        if "local_server" in sql:  # ALWAYSON_SQL menciona is_primary_replica num comentario
            return [{"ag_name": "AG1", "primary_replica": "HOSTA\\I01", "local_server": "hosta\\i01"}], None
        return _primary_rows(), None

    monkeypatch.setattr(lm, "_query_instance", fake)
    body = json.loads(lm.get_alwayson_live("HOSTA_I01").body)
    assert body["hops"] == [] and len(body["replicas"]) == 3


def test_hop_failure_keeps_local_rows_with_note(monkeypatch):
    def fake(instance, sql, database="master", timeout=10):
        if "local_server" in sql:  # ALWAYSON_SQL menciona is_primary_replica num comentario
            return [{"ag_name": "AG1", "primary_replica": "HOSTA\\I01", "local_server": "HOSTB\\I01"}], None
        if instance == "HOSTA_I01":
            return None, "Sem conexao a HOSTA_I01"
        return _local_rows(), None

    monkeypatch.setattr(lm, "_query_instance", fake)
    resp = lm.get_alwayson_live("HOSTB_I01")
    body = json.loads(resp.body)
    assert resp.status_code == 200 and body["hops"] == []
    assert body["replicas"] == _local_rows() and any("HOSTA_I01" in n for n in body["notes"])


def test_unknown_primary_keeps_local_rows(monkeypatch):
    def fake(instance, sql, database="master", timeout=10):
        if "local_server" in sql:  # ALWAYSON_SQL menciona is_primary_replica num comentario
            return [{"ag_name": "AG1", "primary_replica": None, "local_server": "HOSTB\\I01"}], None
        return _local_rows(), None

    monkeypatch.setattr(lm, "_query_instance", fake)
    body = json.loads(lm.get_alwayson_live("HOSTB_I01").body)
    assert body["hops"] == [] and body["replicas"] == _local_rows() and body["notes"]


def test_endpoint_is_sync_so_fastapi_uses_threadpool():
    import inspect
    assert not inspect.iscoroutinefunction(lm.get_alwayson_live)  # pyodbc sincrono + ate' 3 round-trips


def test_local_query_error_still_503(monkeypatch):
    import pytest
    from fastapi import HTTPException
    monkeypatch.setattr(lm, "_query_instance", lambda *a, **k: (None, "boom"))
    with pytest.raises(HTTPException) as ei:
        lm.get_alwayson_live("HOSTB_I01")
    assert ei.value.status_code == 503


def test_portal_shows_where_data_came_from():
    assert "_kpiTp('live.ag_from_primary'" in PORTAL
    assert "let h = _hopNote + '<table" in PORTAL
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        assert "{primary}" in d["live"]["ag_from_primary"], loc
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:100]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    router_raw = src["router"].read_bytes().decode("utf-8")
    if "--tests-only" in argv:
        # 2026-09-14: a 1.a versao do ficheiro de teste saiu com parenteses a mais (ast.parse falhava na
        # recolha). Reescreve so' o teste; o codigo do lote ja esta aplicado.
        compile(TEST_SRC, str(REL["test"]), "exec")
        src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[write] {REL['test']} (so' o teste)")
        return 0
    if MARK in router_raw:
        print("[ABORT] ja aplicado (para refazer so' o teste: --tests-only)"); return 1
    out = {
        "router": _apply(router_raw, [(R_OLD, R_NEW, 1)], "router"),
        "portal": _apply(src["portal"].read_bytes().decode("utf-8"), P_EDITS, "portal"),
    }
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        if '"ag_from_primary"' in raw:
            raise SystemExit(f"[ABORT] {loc}: chave live.ag_from_primary ja existe")
        line = f'    "ag_from_primary": {json.dumps(KEYS[loc], ensure_ascii=False)},\n'
        out[loc] = _apply(raw, [(ANCHOR[loc], ANCHOR[loc] + line, 1)], loc)
    if src["changelog"].exists():
        out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    print("[ok] anchors: router 1 bloco; portal 2 blocos; i18n 1 chave x3; changelog")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    compile(TEST_SRC, str(REL["test"]), "exec")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_live_ag_hop_20260911.py -q --no-cov ; py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
