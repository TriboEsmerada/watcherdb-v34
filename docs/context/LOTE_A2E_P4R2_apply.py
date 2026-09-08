"""LOTE A-2e (P4 ronda 2 do QA externo, 2026-09-08): residuo do LIVE + revogacao observavel.

Achados da ronda 2 (HEAD f4da746), concedidos pelo council:
  1. A-4.1: _liveRenderErrorLog (portal ~51361) ainda tem o stack mono CRU, mas com aspas ESCAPADAS
     dentro da string JS (`\\'Cascadia Code\\',Consolas,monospace`). O regex do lote 41ae729 e o teste
     test_programas_do_live_sem_monospace_cru procuravam a forma sem escape => ponto cego real,
     150 folhas em runtime fora do token (P2). Correccao: var(--font-mono) + teste endurecido
     ("monospace"/"Cascadia"/"Consolas" ausentes do bloco; o unico uso legitimo e' var(--font-mono)).
  2. A-4.7: o fail-open sem a coluna password_changed_at so' e' visivel no log do processo, a que o QA
     nao tem acesso -- "nao observavel por GET". Correccao: /api/v3/health (autenticado) devolve
     auth.reset_revocation = "active" | "inactive" por sondagem a` coluna (cache 60 s). Assim o gate de
     runtime do QA e o release-check conseguem provar que a revogacao esta' activa sem ler o log.

Ancoras por texto unico; idempotente; EOL preservado.

Uso (raiz do repo):  py docs/context/LOTE_A2E_P4R2_apply.py
Depois:              py -m pytest tests/unit/test_live_typography_tokens.py tests/unit/test_reset_revoga_token.py -q --no-cov
                     Restart-Service WatcherDBWebServiceV34
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
AUTH_SVC = ROOT / "services" / "auth_service.py"
MAIN = ROOT / "watcherdb_main.py"
TEST_LIVE = ROOT / "tests" / "unit" / "test_live_typography_tokens.py"
TEST_REV = ROOT / "tests" / "unit" / "test_reset_revoga_token.py"


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


def _read(p: Path):
    raw = p.read_text(encoding="utf-8", newline="")
    return raw, ("\r\n" if "\r\n" in raw else "\n")


def _write(p: Path, s: str) -> None:
    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.write(s)


def _apply(p: Path, edits, done_marker: str) -> None:
    raw, eol = _read(p)
    if done_marker in raw:
        print(f"{p.name}: ja aplicado (skip)")
        return
    for old, _new in edits:
        o = old.replace("\n", eol)
        if raw.count(o) != 1:
            abort(f"{p.name}: esperava 1x a ancora que comeca por {old[:70]!r}, encontrei {raw.count(o)}")
    for old, new in edits:
        raw = raw.replace(old.replace("\n", eol), new.replace("\n", eol), 1)
    _write(p, raw)
    print(f"{p.name}: {len(edits)} substituicoes ancoradas")


# 1. portal: errorlog em token
_apply(
    PORTAL,
    [(
        "font-family:\\'Cascadia Code\\',Consolas,monospace;font-size:12px;line-height:1.6;",
        "font-family:var(--font-mono);font-size:12px;line-height:1.6;",
    )],
    "font-family:var(--font-mono);font-size:12px;line-height:1.6;",
)

# 2. teste do LIVE endurecido
_apply(
    TEST_LIVE,
    [(
        "def test_programas_do_live_sem_monospace_cru(portal):\n"
        "    blk = _live_render_block(portal)\n"
        "    assert not re.search(r\"font-family:\\s*monospace\\b\", blk)\n"
        "    assert \"'Cascadia Code',Consolas,monospace\" not in blk\n",
        "def test_programas_do_live_sem_monospace_cru(portal):\n"
        "    # P4 ronda 2 (2026-09-08): a forma com aspas escapadas (\\\\'Cascadia Code\\\\') escapou ao regex\n"
        "    # antigo. No bloco o unico uso legitimo e' var(--font-mono), que nao contem estes literais.\n"
        "    blk = _live_render_block(portal)\n"
        "    assert \"monospace\" not in blk, \"stack mono cru nos programas do LIVE\"\n"
        "    assert \"Cascadia\" not in blk and \"Consolas\" not in blk\n",
    )],
    "stack mono cru nos programas do LIVE",
)

# 3. auth_service: sondagem da coluna (observavel por GET)
_apply(
    AUTH_SVC,
    [(
        "\n\n# ==========================================\n"
        "# LDAP / Active Directory Authentication (generic, configurable)\n",
        "\n\n_REVOGACAO_CACHE: dict = {\"at\": 0.0, \"valor\": None}\n"
        "\n"
        "\n"
        "def revogacao_por_reset_activa(force: bool = False) -> dict:\n"
        "    \"\"\"Estado da revogacao de sessao por reset, observavel por GET (P4 ronda 2 do QA externo).\n"
        "\n"
        "    Sonda a coluna dbo.WatcherDB_Users.password_changed_at (migracao 13) com cache de 60 s.\n"
        "    \"active\"   -> a coluna existe: tokens anteriores a um reset sao rejeitados.\n"
        "    \"inactive\" -> coluna em falta (fail-open com aviso no log): correr 13_ADD_PASSWORD_CHANGED_AT.sql.\n"
        "    \"unknown\"  -> BD indisponivel na sondagem.\n"
        "    \"\"\"\n"
        "    import time as _t\n"
        "\n"
        "    agora = _t.time()\n"
        "    if not force and _REVOGACAO_CACHE[\"valor\"] and agora - _REVOGACAO_CACHE[\"at\"] < 60:\n"
        "        return _REVOGACAO_CACHE[\"valor\"]\n"
        "    try:\n"
        "        _execute_query(\"SELECT TOP 1 password_changed_at FROM dbo.WatcherDB_Users\")\n"
        "        estado = \"active\"\n"
        "    except Exception as e:\n"
        "        estado = \"inactive\" if (\"password_changed_at\" in str(e) or \"Invalid column\" in str(e)) else \"unknown\"\n"
        "    valor = {\n"
        "        \"reset_revocation\": estado,\n"
        "        \"checked_at\": datetime.now(timezone.utc).isoformat(),\n"
        "        \"migration\": \"database/13_ADD_PASSWORD_CHANGED_AT.sql\",\n"
        "    }\n"
        "    _REVOGACAO_CACHE.update(at=agora, valor=valor)\n"
        "    return valor\n"
        "\n"
        "\n"
        "# ==========================================\n"
        "# LDAP / Active Directory Authentication (generic, configurable)\n",
    )],
    "def revogacao_por_reset_activa(",
)

# 4. /api/v3/health expoe auth.reset_revocation
_apply(
    MAIN,
    [(
        "            'implementation': 'WatcherDB Monitoring System v3.0.0 - Using YOUR Excel data only'\n"
        "        }\n",
        "            # P4 ronda 2 (2026-09-08): estado da revogacao de sessao por reset, observavel por GET.\n"
        "            # Nunca faz o health falhar: erro na sondagem => \"unknown\".\n"
        "            'auth': _auth_health_flags(),\n"
        "            'implementation': 'WatcherDB Monitoring System v3.0.0 - Using YOUR Excel data only'\n"
        "        }\n",
    ), (
        "@app.get(\"/api/v3/health\")\n"
        "async def health_check():\n",
        "def _auth_health_flags() -> dict:\n"
        "    try:\n"
        "        from services.auth_service import revogacao_por_reset_activa\n"
        "        return revogacao_por_reset_activa()\n"
        "    except Exception as e:  # pragma: no cover - health nunca cai por causa disto\n"
        "        return {\"reset_revocation\": \"unknown\", \"error\": str(e)[:120]}\n"
        "\n"
        "\n"
        "@app.get(\"/api/v3/health\")\n"
        "async def health_check():\n",
    )],
    "_auth_health_flags",
)

# 5. testes da sondagem
TEST_EXTRA = '''

# ---------------------------------------------------------------- observavel por GET (P4 ronda 2)

def test_revogacao_activa_quando_a_coluna_existe(monkeypatch):
    monkeypatch.setattr(auth, "_execute_query", lambda q, p=None: [{"password_changed_at": None}])
    r = auth.revogacao_por_reset_activa(force=True)
    assert r["reset_revocation"] == "active"


def test_revogacao_inactiva_quando_a_coluna_falta(monkeypatch):
    def _boom(q, p=None):
        raise Exception("('42S22', \\"Invalid column name 'password_changed_at'\\")")
    monkeypatch.setattr(auth, "_execute_query", _boom)
    r = auth.revogacao_por_reset_activa(force=True)
    assert r["reset_revocation"] == "inactive"
    assert "13_ADD_PASSWORD_CHANGED_AT" in r["migration"]


def test_revogacao_unknown_quando_a_bd_nao_responde(monkeypatch):
    def _boom(q, p=None):
        raise Exception("Login timeout expired")
    monkeypatch.setattr(auth, "_execute_query", _boom)
    assert auth.revogacao_por_reset_activa(force=True)["reset_revocation"] == "unknown"


def test_health_expoe_a_flag_no_fonte():
    src = (PORTAL_ROOT / "watcherdb_main.py").read_text(encoding="utf-8")
    i = src.index('@app.get("/api/v3/health")')
    assert "'auth': _auth_health_flags()" in src[i:i + 4000]
'''
tsrc, teol = _read(TEST_REV)
if "test_revogacao_activa_quando_a_coluna_existe" in tsrc:
    print("test_reset_revoga_token.py: ja tem os 4 testes (skip)")
else:
    if "PORTAL_ROOT" not in tsrc:
        tsrc = tsrc.replace(
            "import services.auth_service as auth\n".replace("\n", teol),
            ("from pathlib import Path\n\nPORTAL_ROOT = Path(__file__).resolve().parents[2]\n\nimport services.auth_service as auth\n").replace("\n", teol),
            1,
        )
    _write(TEST_REV, tsrc.rstrip("\r\n") + teol + TEST_EXTRA.replace("\n", teol))
    print("test_reset_revoga_token.py: +4 (14 no total)")

print("\nLOTE A-2e concluido. Correr:  py -m pytest tests/unit/test_live_typography_tokens.py tests/unit/test_reset_revoga_token.py -q --no-cov")
print("Depois: Restart-Service WatcherDBWebServiceV34; GET /api/v3/health autenticado -> auth.reset_revocation == active")
