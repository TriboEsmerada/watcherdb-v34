# -*- coding: utf-8 -*-
"""B3c (2026-09-15) -- o bloco do errorlog (B3/B3b) passa a ler o estado de leitura por instancia (B2a-2a).

O B2a-2a (V1 7865e42, migration 014 corrida as 18:0x) grava por instancia a ultima leitura boa e a serie de falhas em
WDB_ERRORLOG_READ_STATE. Primeiros ciclos: PRD 41 lidas e 1 com falha (OATXP01, permission), QA 15 lidas.

Parecer da persona DBA cliente (incorporado):
  - "Ultima leitura bem-sucedida desta instancia" ACRESCENTA-SE a "Ultima linha recebida" (respondem a perguntas
    diferentes: ha eventos? a recolha esta viva?).
  - Com falhas seguidas: aviso com a classe traduzida (ligacao, login recusado, sem permissao, timeout de consulta,
    outro erro), NUNCA o texto do driver (nomes de servidor e login). O endpoint nem o devolve.
  - 4.o motivo de lista vazia com prioridade; e o aviso aparece tambem quando ha linhas (sao anteriores a falha).
  - Sem tabela ou sem linha da instancia: comportamento do B3 sem aviso.

Backend: api/routers/intelligence_kpis.py, terceira leitura no mesmo pedido (sql_monitoring, so SELECT com parametro,
IF OBJECT_ID e try proprio: fail-open). Sem mudanca de base de dados.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/B3C_ESTADO_LEITURA_PORTAL_2026-09-15_apply.py --check
  py docs/context/B3C_ESTADO_LEITURA_PORTAL_2026-09-15_apply.py
  py -m pytest tests/unit/test_b3_offline_errorlog_20260915.py tests/unit/test_b3b_banner_errorlog_20260915.py tests/unit/test_b3c_estado_leitura_20260915.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "kpis": Path("api/routers/intelligence_kpis.py"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "ptbr": Path("static/i18n/pt-BR.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test_b3": Path("tests/unit/test_b3_offline_errorlog_20260915.py"),
    "test": Path("tests/unit/test_b3c_estado_leitura_20260915.py"),
}
MARK = "_ERRORLOG_SIGNALS_STATE_SQL"

# ---------------------------------------------------------------- backend
STATE_SQL_BLOCK = '''_ERRORLOG_SIGNALS_STALE_MIN = 15

# B3c 2026-09-15: estado de leitura por instancia (B2a-2a, migration 014). Sem o texto do driver (persona: nomes de
# servidor e login). IF OBJECT_ID: sem a migration nao ha conjunto de resultados e o bloco fica como no B3.
_ERRORLOG_SIGNALS_FAILURE_CLASSES = ("connect", "login_failed", "permission", "query_timeout", "other")
_ERRORLOG_SIGNALS_STATE_SQL = """
SET NOCOUNT ON;
DECLARE @inst VARCHAR(128) = ?;
IF OBJECT_ID('dbo.WDB_ERRORLOG_READ_STATE', 'U') IS NOT NULL
    SELECT s.Last_Success_TS, s.Consecutive_Failures, s.First_Failure_TS, s.Last_Failure_Class
    FROM dbo.WDB_ERRORLOG_READ_STATE s WITH (NOLOCK) WHERE s.Instance = @inst;
"""
'''

KPIS_EDITS = [
    ("_ERRORLOG_SIGNALS_STALE_MIN = 15\n", STATE_SQL_BLOCK, 1),
    ("def _errorlog_signals_payload(instance, hours, agora, ancora, ciclo, ultima_linha, rows):\n",
     "def _errorlog_signals_payload(instance, hours, agora, ancora, ciclo, ultima_linha, rows, estado=None):\n", 1),
    ("    ciclo_min = None if ciclo is None else max(0, int((agora - ciclo).total_seconds() // 60))\n"
     "    if ciclo_min is None or ciclo_min > _ERRORLOG_SIGNALS_STALE_MIN:\n",
     "    ciclo_min = None if ciclo is None else max(0, int((agora - ciclo).total_seconds() // 60))\n"
     "    # B3c: estado da instancia (Last_Success_TS, Consecutive_Failures, First_Failure_TS, Last_Failure_Class)\n"
     "    leitura = None\n"
     "    if estado is not None:\n"
     "        falhas = int(estado[1] or 0)\n"
     "        classe = estado[3] if estado[3] in _ERRORLOG_SIGNALS_FAILURE_CLASSES else \"other\"\n"
     "        leitura = {\"last_success\": iso(estado[0]), \"consecutive_failures\": falhas,\n"
     "                   \"failing_since\": iso(estado[2]) if falhas else None, \"failure_class\": classe if falhas else None}\n"
     "    if leitura and leitura[\"consecutive_failures\"] > 0:\n"
     "        vazio = \"instance_unreadable\"\n"
     "    elif ciclo_min is None or ciclo_min > _ERRORLOG_SIGNALS_STALE_MIN:\n", 1),
    ('        "collector_stale": vazio == "collector_stale",\n',
     '        "collector_stale": ciclo_min is None or ciclo_min > _ERRORLOG_SIGNALS_STALE_MIN,\n', 1),
    ('        "instance_last_row": iso(ultima_linha),\n',
     '        "instance_last_row": iso(ultima_linha),\n        "read_state": leitura,\n', 1),
    ("        rows = cur.fetchall()\n"
     "        return _errorlog_signals_payload(instance, hours, agora, ancora, ciclo, ultima_linha, rows)\n",
     "        rows = cur.fetchall()\n"
     "        estado = None\n"
     "        try:  # B3c: fail-open (migration 014 por correr, GRANT em falta)\n"
     "            cur.execute(_ERRORLOG_SIGNALS_STATE_SQL, instance)\n"
     "            estado = cur.fetchone() if cur.description else None\n"
     "        except Exception as e:\n"
     "            logger.debug(f\"recent-signals: estado de leitura indisponivel: {e}\")\n"
     "        return _errorlog_signals_payload(instance, hours, agora, ancora, ciclo, ultima_linha, rows, estado)\n", 1),
]

# ---------------------------------------------------------------- portal
RS_DECL = ("            // B3c 2026-09-15: estado de leitura da instancia (B2a-2a). Sem ele, o bloco fica como no B3.\n"
           "            const rs = d.read_state || null;\n"
           "            const falhaLeitura = !!(rs && +rs.consecutive_failures > 0);\n"
           "            const classeFalha = {\n"
           "                connect: _kpiTp('overview.offline_errorlog_failure_connect', 'ligação', {}),\n"
           "                login_failed: _kpiTp('overview.offline_errorlog_failure_login_failed', 'login recusado', {}),\n"
           "                permission: _kpiTp('overview.offline_errorlog_failure_permission', 'sem permissão', {}),\n"
           "                query_timeout: _kpiTp('overview.offline_errorlog_failure_query_timeout', 'timeout de consulta', {}),\n"
           "                other: _kpiTp('overview.offline_errorlog_failure_other', 'outro erro', {}),\n"
           "            };\n")

LINHA_OLD = ("                    · ${_oelT('instance_last', 'Última linha recebida desta instância: {when}', { when: ultima })}\n"
             "                </div>`;\n")
LINHA_NEW = ("                    · ${_oelT('instance_last', 'Última linha recebida desta instância: {when}', { when: ultima })}\n"
             "                    ${rs ? ' · ' + _oelT('last_read', 'Última leitura bem-sucedida desta instância: {when}', { when: rs.last_success ? _oelHora(rs.last_success, true) : _kpiTp('overview.offline_errorlog_last_read_none', 'nenhuma registada', {}) }) : ''}\n"
             "                </div>`;\n"
             "            if (falhaLeitura) {\n"
             "                // B3c (persona): aviso com prioridade, tambem com linhas listadas (sao anteriores a falha); sem texto do driver\n"
             "                html += `<div style=\"font-size: 13px; color: ${getSevTokens('WARNING').text}; margin-top: 8px;\"><i class=\"fas fa-plug-circle-xmark\" aria-hidden=\"true\"></i>\n"
             "                    ${_oelT('unreadable', 'O recolhedor não consegue ler o errorlog desta instância desde {since} ({class}, {n} ciclos seguidos).',\n"
             "                            { since: _oelHora(rs.failing_since, true), class: classeFalha[rs.failure_class] || classeFalha.other, n: +rs.consecutive_failures })}\n"
             "                    ${(Array.isArray(d.events) && d.events.length) ? _oelT('unreadable_rows_note', 'As linhas listadas são anteriores à falha.') : ''}</div>`;\n"
             "            }\n")

MOTIVO_OLD = "                const motivo = d.empty_reason === 'collector_stale'\n"
MOTIVO_NEW = ("                const motivo = d.empty_reason === 'instance_unreadable'\n"
              "                    ? ['empty_instance_unreadable', 'Nenhuma linha nesta janela, e o recolhedor não consegue ler esta instância: a ausência de linhas não diz nada sobre o servidor.']\n"
              "                    : d.empty_reason === 'collector_stale'\n")

PORTAL_EDITS = [
    ("            const ultima = d.instance_last_row ? _oelHora(d.instance_last_row, true)\n",
     RS_DECL + "            const ultima = d.instance_last_row ? _oelHora(d.instance_last_row, true)\n", 1),
    (LINHA_OLD, LINHA_NEW, 1),
    (MOTIVO_OLD, MOTIVO_NEW, 1),
]

I18N = {
    "pt": {
        "offline_errorlog_last_read": "Última leitura bem-sucedida desta instância: {when}",
        "offline_errorlog_last_read_none": "nenhuma registada",
        "offline_errorlog_unreadable": "O recolhedor não consegue ler o errorlog desta instância desde {since} ({class}, {n} ciclos seguidos).",
        "offline_errorlog_unreadable_rows_note": "As linhas listadas são anteriores à falha.",
        "offline_errorlog_empty_instance_unreadable": "Nenhuma linha nesta janela, e o recolhedor não consegue ler esta instância: a ausência de linhas não diz nada sobre o servidor.",
        "offline_errorlog_failure_connect": "ligação",
        "offline_errorlog_failure_login_failed": "login recusado",
        "offline_errorlog_failure_permission": "sem permissão",
        "offline_errorlog_failure_query_timeout": "timeout de consulta",
        "offline_errorlog_failure_other": "outro erro",
    },
    "en": {
        "offline_errorlog_last_read": "Last successful read of this instance: {when}",
        "offline_errorlog_last_read_none": "none recorded",
        "offline_errorlog_unreadable": "The collector has been unable to read this instance's error log since {since} ({class}, {n} consecutive cycles).",
        "offline_errorlog_unreadable_rows_note": "The lines listed predate the failure.",
        "offline_errorlog_empty_instance_unreadable": "No lines in this window, and the collector cannot read this instance: the absence of lines says nothing about the server.",
        "offline_errorlog_failure_connect": "connection",
        "offline_errorlog_failure_login_failed": "login refused",
        "offline_errorlog_failure_permission": "no permission",
        "offline_errorlog_failure_query_timeout": "query timeout",
        "offline_errorlog_failure_other": "other error",
    },
    "es": {
        "offline_errorlog_last_read": "Última lectura correcta de esta instancia: {when}",
        "offline_errorlog_last_read_none": "ninguna registrada",
        "offline_errorlog_unreadable": "El colector no consigue leer el errorlog de esta instancia desde {since} ({class}, {n} ciclos seguidos).",
        "offline_errorlog_unreadable_rows_note": "Las líneas listadas son anteriores al fallo.",
        "offline_errorlog_empty_instance_unreadable": "Ninguna línea en esta ventana, y el colector no consigue leer esta instancia: la ausencia de líneas no dice nada sobre el servidor.",
        "offline_errorlog_failure_connect": "conexión",
        "offline_errorlog_failure_login_failed": "inicio de sesión rechazado",
        "offline_errorlog_failure_permission": "sin permiso",
        "offline_errorlog_failure_query_timeout": "timeout de consulta",
        "offline_errorlog_failure_other": "otro error",
    },
}
PTBR = {
    "offline_errorlog_last_read_none": "nenhuma registrada",
    "offline_errorlog_unreadable": "O coletor não consegue ler o errorlog desta instância desde {since} ({class}, {n} ciclos seguidos).",
    "offline_errorlog_empty_instance_unreadable": "Nenhuma linha nesta janela, e o coletor não consegue ler esta instância: a ausência de linhas não diz nada sobre o servidor.",
    "offline_errorlog_failure_connect": "conexão",
}


def _chaves(d):
    return "".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)},\n' for k, v in d.items())


CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **Errorlog no ecrã offline e no banner diz se a recolha desta instância está viva** (B3c, owner 15/09). Com o\n"
                  "  estado de leitura por instância do recolhedor (B2a-2a), o bloco mostra a última leitura bem-sucedida ao lado da\n"
                  "  última linha recebida e, quando o recolhedor falha seguidamente, avisa desde quando e porquê (ligação, login\n"
                  "  recusado, sem permissão, timeout de consulta, outro erro), mesmo com linhas listadas. Nunca mostra o texto do\n"
                  "  driver. Sem a tabela nova, o bloco fica como antes. [tier: Std]\n"
                  "\n", 1)

B3_TEST_EDIT = ("        assert set(novas) == chaves and len(chaves) == 28, loc  # B3b: +5 chaves do banner\n",
                "        assert set(novas) == chaves and len(chaves) == 38, loc  # B3b: +5 chaves do banner; B3c: +10\n", 1)

TEST_SRC = r'''"""
2026-09-15 -- B3c: o bloco do errorlog le o estado de leitura por instancia (B2a-2a).
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
RENDER = PORTAL[PORTAL.index("function _oelRender(elId, d) {"):PORTAL.index("function extractHostname(serverIdOrName) {")]
AGORA = datetime(2026, 9, 15, 18, 30)


def _ik():
    from api.routers import intelligence_kpis as ik
    return ik


def _p(estado, rows=(), ciclo_min=3):
    ik = _ik()
    return ik._errorlog_signals_payload("SQLX_I01", 2, AGORA, None, AGORA - timedelta(minutes=ciclo_min), AGORA,
                                        list(rows), estado)


def test_falhas_seguidas_tem_prioridade_e_nunca_trazem_o_texto():
    p = _p((AGORA - timedelta(hours=1), 7, AGORA - timedelta(minutes=35), "connect"), ciclo_min=40)
    assert p["empty_reason"] == "instance_unreadable" and p["collector_stale"] is True
    assert p["read_state"] == {"last_success": "2026-09-15T17:30:00", "consecutive_failures": 7,
                               "failing_since": "2026-09-15T17:55:00", "failure_class": "connect"}
    assert "text" not in json.dumps(p["read_state"])


def test_com_linhas_o_estado_vem_na_mesma_e_classe_desconhecida_passa_a_other():
    linha = ("E", AGORA - timedelta(minutes=50), "Critical", 17053, 16, "x", None)
    p = _p((None, 2, AGORA, "inventada"), rows=[linha])
    assert p["empty_reason"] is None and p["read_state"]["failure_class"] == "other"
    assert p["read_state"]["last_success"] is None


def test_leitura_boa_e_sem_estado_ficam_como_no_b3():
    p = _p((AGORA - timedelta(minutes=4), 0, None, "connect"))
    assert p["read_state"] == {"last_success": "2026-09-15T18:26:00", "consecutive_failures": 0,
                               "failing_since": None, "failure_class": None}
    assert p["empty_reason"] == "window_quiet"
    assert _p(None)["read_state"] is None and _p(None)["empty_reason"] == "window_quiet"


def test_consulta_do_estado_so_leitura_e_fail_open(monkeypatch):
    ik = _ik()
    sql = ik._ERRORLOG_SIGNALS_STATE_SQL
    assert "IF OBJECT_ID('dbo.WDB_ERRORLOG_READ_STATE', 'U') IS NOT NULL" in sql and "WITH (NOLOCK)" in sql
    assert "Last_Failure_Text" not in sql and not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|EXEC)\b", sql)

    class Cur:
        description = None

        def __init__(self):
            self.n = 0

        def execute(self, sql, *params):
            self.n += 1
            self.description = [("x",)]
            if self.n == 3:
                raise RuntimeError("The SELECT permission was denied on the object 'WDB_ERRORLOG_READ_STATE'")

        def fetchone(self):
            return (AGORA, None, AGORA - timedelta(minutes=2), None)

        def fetchall(self):
            return []

        def close(self):
            pass

    class Conn:
        def cursor(self):
            return Cur()

    monkeypatch.setattr(ik, "get_intelligence_connection", lambda: Conn())
    monkeypatch.setattr(ik, "get_intelligence_pool", lambda: type("Pool", (), {"return_connection": lambda self, c: None})())
    p = ik._errorlog_recent_signals_sync("SQLX_I01", 2)
    assert p["success"] is True and p["read_state"] is None


def test_ecra_mostra_leitura_e_aviso_sem_texto_do_driver():
    assert "const falhaLeitura = !!(rs && +rs.consecutive_failures > 0);" in RENDER
    assert "_oelT('last_read'," in RENDER and "_oelT('unreadable'," in RENDER
    assert "d.empty_reason === 'instance_unreadable'" in RENDER
    assert RENDER.index("if (falhaLeitura) {") < RENDER.index("const sec = d.security || {};")
    assert "failure_text" not in RENDER and "Last_Failure_Text" not in RENDER
    for c in ("connect", "login_failed", "permission", "query_timeout", "other"):
        assert f"'overview.offline_errorlog_failure_{c}'" in RENDER
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
    kpis_raw = src["kpis"].read_bytes().decode("utf-8")
    if MARK in kpis_raw:
        print("[ABORT] ja aplicado"); return 1
    out = {"kpis": _apply(kpis_raw, KPIS_EDITS, "intelligence_kpis"),
           "portal": _apply(src["portal"].read_bytes().decode("utf-8"), PORTAL_EDITS, "portal")}
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        if set(I18N[loc]) & set(json.loads(raw)["overview"]):
            raise SystemExit(f"[ABORT] {loc}: chaves novas ja existem em overview")
        txt = _apply(raw, [('\n  "overview": {\n', '\n  "overview": {\n' + _chaves(I18N[loc]), 1)], loc)
        json.loads(txt)
        out[loc] = txt
    raw = src["ptbr"].read_bytes().decode("utf-8")
    txt = _apply(raw, [('\n  "overview": {\n', '\n  "overview": {\n' + _chaves(PTBR), 1)], "pt-BR")
    json.loads(txt)
    out["ptbr"] = txt
    out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    out["test_b3"] = _apply(src["test_b3"].read_bytes().decode("utf-8"), [B3_TEST_EDIT], "test_b3")
    compile(out["kpis"], str(REL["kpis"]), "exec")
    compile(out["test_b3"], str(REL["test_b3"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] intelligence_kpis.py {len(KPIS_EDITS)} blocos (compila); portal {len(PORTAL_EDITS)} blocos; i18n {len(I18N['pt'])} "
          f"chaves em pt/en/es, {len(PTBR)} em pt-BR; changelog; teste B3 ajustado (28 -> 38)")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_b3_offline_errorlog_20260915.py tests/unit/test_b3b_banner_errorlog_20260915.py "
          "tests/unit/test_b3c_estado_leitura_20260915.py -q --no-cov ; py scripts/i18n_validate.py ; "
          "Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
