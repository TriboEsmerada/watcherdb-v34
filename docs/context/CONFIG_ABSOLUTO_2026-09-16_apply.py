# -*- coding: utf-8 -*-
"""Caminhos de configuracao absolutos no pool de ligacoes -- e o rollout do SQL Auth que afinal nunca aconteceu (2026-09-16).

ACHADO (medido hoje):
 - api/connection_pool.py guardava DOIS caminhos relativos ao directorio corrente: "config/servers.json" (linha 200) e
   "config/sql_auth_rollout.json" (linha 215). O servico Windows corre com o CWD em System32, por isso nenhum dos dois
   e' encontrado: 2.145 avisos "Cannot stat config/servers.json" so' no log actual; zero linhas de allowlist.
 - Consequencias, todas ao mesmo tempo: (1) sem cache de credenciais, _resolve_credentials devolve None; (2) sem creds,
   _build_server_target_ex nem chega a consultar as portas aprendidas pelo recolhedor (WDB_INSTANCE_TCP_PORT) -- as
   instancias nomeadas continuam a depender do SQL Browser, exactamente o que falha com a rede ma (episodio de 16/09
   de manha); (3) a allowlist de 62 servidores do SQL Auth (config/sql_auth_rollout.json, 09/09) nunca foi lida, e a
   frota inteira continua a ligar por Trusted_Connection com a identidade do servico -- o CONTEXT.md de 09/09 registou
   "ROLLOUT SQL AUTH ACTIVADO: 62/63" com a ressalva honesta de que "o log NAO prova"; agora prova o contrario.
 - Os grants de menor privilegio estao aplicados em 62/63 desde 08/09 (pre-flight verde), portanto ligar o SQL Auth a
   serio e' o estado preparado e desejado -- mas e' uma mudanca de frota num reinicio, e por isso ENTRA POR CANARIO.
 - modules/monitoring/watcherdb_alwayson_check.py:126 tem o mesmo defeito (terceiro leitor relativo; os outros ja
   tinham sido migrados para config_dir() a 19/08).

O QUE FAZ:
 1. connection_pool: os dois caminhos passam por watcherdb.core.paths.config_dir() (dev: <raiz>/config; congelado:
    C:\\ProgramData\\WatcherDB\\config), com recurso a` raiz do projecto por __file__ -- nunca ao CWD. Um aviso unico
    no arranque escreve no log os caminhos resolvidos e se existem, para o estado deixar de ser adivinhado.
 2. alwayson_check: idem.
 3. Teste: os caminhos sao absolutos, apontam para config_dir(), e nao mudam quando o CWD muda.
 4. Docs: SOLUCOES (o episodio), CONTEXT (3 linhas: fecho dos lotes A/B do bootstrap + este achado), runbook (defeito 1
    resolvido), CHANGELOG.
NAO FAZ: nao mexe na allowlist (ficheiro do owner, fora do git) nem no servers.json. O canario e' feito pelo owner na
allowlist ANTES do reinicio -- ver a mensagem de entrega.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/CONFIG_ABSOLUTO_2026-09-16_apply.py --check
  py docs/context/CONFIG_ABSOLUTO_2026-09-16_apply.py
  py -m pytest tests/unit/test_config_absoluto_20260916.py tests/unit/test_connection_pool.py -q --no-cov
  (reiniciar SO' depois de reduzir a allowlist ao canario -- ver entrega)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "pool": Path("api/connection_pool.py"),
    "ao": Path("modules/monitoring/watcherdb_alwayson_check.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "solucoes": Path("docs/context/SOLUCOES.md"),
    "context": Path("docs/context/CONTEXT.md"),
    "runbook": Path("docs/context/RUNBOOK_PORTAL_NAO_ABRE_2026-09-16.md"),
    "test": Path("tests/unit/test_config_absoluto_20260916.py"),
}
MARK = "def _config_file_path("

POOL_EDITS = [
    # helper de modulo, antes da classe do pool
    ("""class SQLServerConnectionPool:
""",
     """def _config_file_path(nome: str) -> str:
    \"\"\"Caminho ABSOLUTO de um ficheiro de config/ -- nunca relativo ao CWD.

    2026-09-16: os dois ficheiros deste pool ("config/servers.json" e "config/sql_auth_rollout.json") eram relativos ao
    directorio corrente. O servico Windows corre com o CWD em System32, por isso nunca os encontrava: 2.145 avisos
    "Cannot stat" no log, nenhuma credencial em cache, portas aprendidas nunca consultadas (so' se consultam quando ha
    creds) e a allowlist de 62 servidores do SQL Auth nunca lida -- a frota continuava em Trusted_Connection enquanto o
    blackboard dizia "rollout activado". Mesma origem que o episodio de 2026-04-29 (SOLUCOES.md), noutros leitores.
    config_dir() e' a regra da casa (dev: <raiz>/config; congelado: ProgramData); o recurso e' a raiz do projecto.
    \"\"\"
    try:
        from watcherdb.core.paths import config_dir
        return str(config_dir() / nome)
    except Exception:
        from pathlib import Path as _P
        return str(_P(__file__).resolve().parents[1] / "config" / nome)


class SQLServerConnectionPool:
""", 1),
    ("""        self._creds_cache_path = "config/servers.json"
""",
     """        self._creds_cache_path = _config_file_path("servers.json")
""", 1),
    ("""        self._sql_auth_rollout_path = "config/sql_auth_rollout.json"
""",
     """        self._sql_auth_rollout_path = _config_file_path("sql_auth_rollout.json")
        # Uma linha no arranque para o estado deixar de ser adivinhado (ate' 16/09 ninguem sabia que estes
        # ficheiros nao eram encontrados). WARNING de proposito: INFO nao chega ao log do servico.
        logger.warning(
            "[CONFIG] servers.json=%s (%s) | sql_auth_rollout.json=%s (%s)",
            self._creds_cache_path, "existe" if os.path.exists(self._creds_cache_path) else "NAO EXISTE",
            self._sql_auth_rollout_path, "existe" if os.path.exists(self._sql_auth_rollout_path) else "NAO EXISTE",
        )
""", 1),
    # a contagem da allowlist passa a ver-se no log do servico
    ("""            logger.info(
                f"SQL Auth rollout allowlist: {len(self._sql_auth_rollout)} servidor(es)"
            )
""",
     """            logger.warning(   # 2026-09-16: era INFO e nunca chegou ao log; o rollout tem de ser verificavel
                f"SQL Auth rollout allowlist: {len(self._sql_auth_rollout)} servidor(es) "
                f"({self._sql_auth_rollout_path})"
            )
""", 1),
]

AO_EDITS = [
    ("""            servers_path = Path('config/servers.json')
""",
     """            # 2026-09-16: caminho absoluto (o servico corre com o CWD em System32; o relativo nunca existia)
            try:
                from watcherdb.core.paths import config_dir
                servers_path = config_dir() / 'servers.json'
            except Exception:
                servers_path = Path(__file__).resolve().parents[2] / 'config' / 'servers.json'
""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **O pool de ligações passa a encontrar a sua configuração** (16/09). Dois ficheiros — `servers.json` e a\n"
    "  allowlist do SQL Auth — eram procurados por caminho relativo ao directório corrente, e o serviço Windows corre\n"
    "  noutro sítio: nunca os encontrava. Sem eles, o portal ligava sempre por identidade de Windows, nunca usava as\n"
    "  portas manuais nem as aprendidas pelo recolhedor, e o rollout do SQL Auth de 09/09 nunca chegou a acontecer.\n"
    "  Passam a resolver-se pela pasta de configuração da instalação, e o arranque escreve no registo os caminhos e se\n"
    "  existem. A activação do SQL Auth na frota faz-se por canário, através da allowlist. [tier: Std]\n"
    "\n",
    1,
)

SOL_EDIT = (
    "|---|---|---|---|---|---|\n",
    "|---|---|---|---|---|---|\n"
    "| 2026-09-16 | Frota inteira a ligar por Trusted_Connection apesar de a allowlist do SQL Auth ter 62 servidores e os "
    "grants estarem aplicados (09/09 registado como ROLLOUT ACTIVADO); 2145 avisos Cannot stat config/servers.json no log; "
    "instancias nomeadas sempre pelo SQL Browser apesar das portas aprendidas na BD; episodios de rede mais longos | "
    "api/connection_pool.py guardava dois caminhos RELATIVOS ao CWD (config/servers.json e config/sql_auth_rollout.json) e "
    "o servico Windows corre com o CWD em System32: nenhum era encontrado; sem creds, _build_server_target_ex nem consulta "
    "as portas aprendidas (o _learned_target esta' dentro do if creds), e a allowlist vazia = todos Trusted; a linha de "
    "log que confirmaria a allowlist era INFO e o ficheiro nunca chegava a ser lido, por isso o 09/09 ficou sem prova | "
    "_config_file_path() com watcherdb.core.paths.config_dir() e recurso a` raiz do projecto (nunca CWD) nos dois caminhos "
    "e no alwayson_check; aviso de arranque com os caminhos resolvidos e se existem; contagem da allowlist a WARNING; "
    "activacao por canario via allowlist antes do reinicio | docs/context/CONFIG_ABSOLUTO_2026-09-16_apply.py; "
    "tests/unit/test_config_absoluto_20260916.py; RUNBOOK_PORTAL_NAO_ABRE_2026-09-16.md | caminho relativo; CWD System32; "
    "Cannot stat; sql_auth_rollout; allowlist; Trusted_Connection; portas aprendidas; SQL Browser; config_dir; rollout que "
    "nao aconteceu; log nao prova |\n",
    1,
)

CONTEXT_APPEND = (
    "- 2026-09-16 | orquestrador + security-auditor | ACHADO CRITICO do instalador RESOLVIDO na ordem imposta: lote A "
    "(V3.4 046b52d) tools/bootstrap_admin.py interactivo que recusa se ja houver admin, deploy/setup_database.ps1 com "
    "Passo 3 e sem o script legado nem o 07, CREATE_USER_AUTHENTICATION_SYSTEM.sql historico sem sementes, guias sem "
    "admin123, teste de guarda; lote B (V1 a29791b) INSTALACAO_COMPLETA_UNIFICADA.sql e INSTALACAO_V3.2.sql sem sementes, "
    "4 colunas no CREATE + 30.1b idempotente com EXEC(), teste de guarda. Base viva: 0 sementes. Sem migracao (nada a "
    "corrigir aqui); verificacao para clientes no cabecalho do lote B.\n"
    "- 2026-09-16 | orquestrador | ACHADO: o ROLLOUT SQL AUTH de 09/09 NUNCA ACONTECEU. connection_pool.py lia "
    "config/servers.json (l.200) e config/sql_auth_rollout.json (l.215) por caminho RELATIVO ao CWD; o servico corre em "
    "System32 -> 2145 Cannot stat no log, zero linhas de allowlist, frota inteira em Trusted_Connection com a identidade "
    "do servico, portas aprendidas nunca consultadas pelo portal (_learned_target so' corre dentro do if creds). A nota "
    "de 09/09 dizia com razao que o log nao provava. Grants aplicados em 62/63 desde 08/09 -> corrigir e' seguro MAS e' "
    "mudanca de frota no reinicio. CONFIG_ABSOLUTO_2026-09-16_apply.py: config_dir() nos dois caminhos + "
    "alwayson_check, aviso de arranque com os caminhos, allowlist a WARNING. Entrada por canario: owner reduz a "
    "allowlist a 3 ids, reinicia, verifica sys.dm_exec_sessions no canario (login sql_monitoring, host TI-PF5HQWK4), "
    "repoe os 62.\n"
    "- 2026-09-16 | orquestrador | Por fazer a seguir: reset por administrador converte conta de AD em local "
    "(services/auth_service.py change_password reescreve password_hash sem olhar ao marcador ad_auth:; o self-service "
    "ja' recusa AD com 401 na verificacao da actual, o reset por admin nao); revisao linguistica das 194 chaves x 4 do "
    "Collector Health; decisao do owner sobre as duas copias de seguranca do servers.json apagadas na arvore do V1.\n"
)

RUNBOOK_OLD = (
    "1. **`config/servers.json` lido por caminho relativo** em `api/connection_pool.py:444`. O serviço não corre na pasta do\n"
    "   repositório, por isso escreve `Cannot stat config/servers.json` em cada tentativa e fica sem a cache de credenciais e de\n"
    "   portas aprendidas. Consequência: as ligações dependem do SQL Browser para encontrar a instância nomeada, que é\n"
    "   exactamente o que falha quando a rede está má. Corrigir com caminho absoluto a partir da raiz do projecto.\n"
)
RUNBOOK_NEW = (
    "1. ~~**`config/servers.json` lido por caminho relativo** em `api/connection_pool.py`~~ — **resolvido a 16/09**\n"
    "   (`CONFIG_ABSOLUTO_2026-09-16_apply.py`): os dois ficheiros do pool (`servers.json` e a allowlist do SQL Auth)\n"
    "   passam por `config_dir()`. O arranque escreve agora `[CONFIG] servers.json=... (existe)` no registo — se disser\n"
    "   `NAO EXISTE`, a instalação está sem configuração e é isso que explica as ligações pelo SQL Browser. Enquanto\n"
    "   esteve por corrigir, a frota inteira ligou por identidade de Windows e o rollout do SQL Auth de 09/09 não chegou\n"
    "   a acontecer — ver `SOLUCOES.md`, linha de 16/09.\n"
)
RUNBOOK_TAIL_OLD = "Enquanto o ponto 1 não for corrigido, um episódio de rede dura mais e é mais difícil de distinguir de um defeito nosso.\n"
RUNBOOK_TAIL_NEW = ("Ambos resolvidos a 16/09. Depois de um reinício, confirmar no registo a linha `[CONFIG]` e a linha\n"
                    "`SQL Auth rollout allowlist: N servidor(es)`; sem elas, o pool não encontrou a configuração.\n")

TEST_SRC = r'''"""
2026-09-16 -- os caminhos de configuracao do pool sao absolutos e nao dependem do directorio corrente.

Ate' hoje eram "config/servers.json" e "config/sql_auth_rollout.json" relativos ao CWD; o servico corre em System32 e
nunca os encontrava. Consequencia escondida: a allowlist de 62 servidores do SQL Auth nunca foi lida.
"""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def pool(monkeypatch):
    from api.connection_pool import SQLServerConnectionPool
    SQLServerConnectionPool._instance = None
    yield SQLServerConnectionPool()
    SQLServerConnectionPool._instance = None


def test_os_dois_caminhos_sao_absolutos_e_apontam_para_config_dir(pool):
    from watcherdb.core.paths import config_dir
    for atributo, nome in (("_creds_cache_path", "servers.json"), ("_sql_auth_rollout_path", "sql_auth_rollout.json")):
        p = Path(getattr(pool, atributo))
        assert p.is_absolute(), f"{atributo} ainda e' relativo: {p}"
        assert p == config_dir() / nome, f"{atributo} nao aponta para config_dir(): {p}"


def test_os_caminhos_nao_mudam_com_o_directorio_corrente(tmp_path, monkeypatch):
    """E' o defeito de origem: o servico corre com o CWD em System32."""
    from api.connection_pool import SQLServerConnectionPool
    SQLServerConnectionPool._instance = None
    antes = SQLServerConnectionPool()
    a, b = antes._creds_cache_path, antes._sql_auth_rollout_path
    SQLServerConnectionPool._instance = None
    monkeypatch.chdir(tmp_path)
    depois = SQLServerConnectionPool()
    assert (depois._creds_cache_path, depois._sql_auth_rollout_path) == (a, b)
    SQLServerConnectionPool._instance = None


def test_nao_sobra_nenhum_caminho_relativo_a_config():
    for rel in ("api/connection_pool.py", "modules/monitoring/watcherdb_alwayson_check.py"):
        src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        activo = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
        assert 'Path(\'config/servers.json\')' not in activo, rel
        assert '= "config/servers.json"' not in activo, rel
        assert '= "config/sql_auth_rollout.json"' not in activo, rel


def test_o_arranque_diz_onde_procura_e_a_allowlist_e_visivel():
    src = (ROOT / "api" / "connection_pool.py").read_text(encoding="utf-8", errors="replace")
    assert '"[CONFIG] servers.json=%s (%s) | sql_auth_rollout.json=%s (%s)"' in src
    i = src.index("SQL Auth rollout allowlist:")
    assert "logger.warning(" in src[i - 200:i], "a contagem da allowlist tem de ser WARNING para chegar ao log do servico"


def test_o_recurso_sem_config_dir_continua_absoluto(monkeypatch):
    """Se watcherdb.core.paths nao importar, o recurso e' a raiz do projecto -- nunca o CWD."""
    import builtins
    from api import connection_pool as cp
    real = builtins.__import__

    def sem_paths(name, *a, **k):
        if name == "watcherdb.core.paths":
            raise ImportError("simulado")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sem_paths)
    p = Path(cp._config_file_path("servers.json"))
    assert p.is_absolute() and p == ROOT / "config" / "servers.json"
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:120]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    pool = src["pool"].read_bytes().decode("utf-8")
    if MARK in pool:
        print("[ABORT] ja aplicado"); return 1
    ctx = src["context"].read_bytes().decode("utf-8")
    eol_ctx = "\r\n" if "\r\n" in ctx else "\n"
    if not ctx.endswith(eol_ctx):
        ctx += eol_ctx
    out = {
        "pool": _apply(pool, POOL_EDITS, "connection_pool"),
        "ao": _apply(src["ao"].read_bytes().decode("utf-8"), AO_EDITS, "alwayson_check"),
        "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog"),
        "solucoes": _apply(src["solucoes"].read_bytes().decode("utf-8"), [SOL_EDIT], "solucoes"),
        "context": ctx + CONTEXT_APPEND.replace("\n", eol_ctx),
        "runbook": _apply(src["runbook"].read_bytes().decode("utf-8"),
                          [(RUNBOOK_OLD, RUNBOOK_NEW, 1), (RUNBOOK_TAIL_OLD, RUNBOOK_TAIL_NEW, 1)], "runbook"),
    }
    compile(out["pool"], str(REL["pool"]), "exec")
    compile(out["ao"], str(REL["ao"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] connection_pool 4 blocos (helper, 2 caminhos + aviso de arranque, allowlist a WARNING); alwayson_check 1; "
          "changelog; SOLUCOES +1; CONTEXT +3; runbook; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_config_absoluto_20260916.py tests/unit/test_connection_pool.py -q --no-cov")
    print("NAO reiniciar antes de reduzir a allowlist ao canario (ver entrega).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
