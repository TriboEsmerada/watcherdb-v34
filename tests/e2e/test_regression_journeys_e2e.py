"""WatcherDB V3.3 — jornadas de regressao no browser (Playwright).

PORQUE EXISTE
As cinco rondas do QA externo (Ago/2026) produziram ~30 achados e a esmagadora
maioria era de FRONTEND: botoes invisiveis a toda a gente, modulo que nunca
renderiza, i18n incompleto, FOUC, sort sem desempate. Nada disso e' alcancavel
por uma suite de backend -- so' existe no DOM depois de o JS correr. O que havia
em `tests/e2e/` cobria UM cartao.

LICAO DA PRIMEIRA EXECUCAO (2026-08-19) -- ler antes de acrescentar testes aqui
A primeira versao destas jornadas corria SEM sessao e deu dois falsos positivos
seguidos:

  1. "elementos com gate de role tem display:none" -> e' o gate a FUNCIONAR. O
     codigo poe `display:none` por JS quando o utilizador nao tem o role
     (portal.html ~5008/~5017). Sem sessao, todos aparecem escondidos.
  2. a mesma verificacao movida para o markup -> tambem falso positivo: o
     `display:none` escrito no HTML e' o estado inicial deliberado (esconder ate'
     o role ser conhecido, para nao haver flash de controlos de admin), e o JS
     repoe-o a `flex` a seguir.

O defeito real (R2-07) era `display:none` no markup COM o atributo de gate
removido -- nada voltava a mostra-los. Nem runtime-sem-sessao nem markup
distinguem isso. So' uma sessao AUTENTICADA distingue: entra-se como admin e
verifica-se que os controlos aparecem.

Consequencia de desenho: tudo o que depende de estado de sessao exige
credenciais, e sem elas o teste NAO corre em vez de correr e medir outra coisa.
Um teste que mede "nao fiz login" e chama-lhe "o botao esta morto" e' pior do
que nao existir.

PRE-REQUISITOS
    pip install pytest-playwright && playwright install chromium
    servico a correr (HTTPS -- ver nota no conftest.py)

    # obrigatorio para as jornadas com sessao:
    $env:WATCHERDB_QA_USER = "qa_admin_ou_dba"
    $env:WATCHERDB_QA_PASS = "..."
    # opcional: qual o role esperado dessa conta (default: admin)
    $env:WATCHERDB_QA_ROLE = "admin"

CORRER
    pytest tests/e2e/test_regression_journeys_e2e.py -v -m e2e --no-cov
"""

import json
import os

import pytest

pytestmark = pytest.mark.e2e

PORTAL = "/watcherdb"

QA_USER = os.getenv("WATCHERDB_QA_USER", "")
QA_PASS = os.getenv("WATCHERDB_QA_PASS", "")
QA_ROLE = os.getenv("WATCHERDB_QA_ROLE", "admin").lower()

SEM_CREDENCIAIS = not (QA_USER and QA_PASS)
MOTIVO_SEM_CREDENCIAIS = (
    "sem WATCHERDB_QA_USER/WATCHERDB_QA_PASS — estas jornadas dependem de estado "
    "de sessao e, sem login, mediriam 'nao estou autenticado' em vez do defeito. "
    "Provisionar as contas de QA (qa_dba/qa_viewer) desbloqueia-as."
)
precisa_sessao = pytest.mark.skipif(SEM_CREDENCIAIS, reason=MOTIVO_SEM_CREDENCIAIS)

# Ruido que nao e' defeito nosso. Manter CURTO -- cada entrada e' um sitio onde
# deixamos de olhar. O 401 entra so' no carregamento sem sessao, onde e' o
# comportamento esperado do proprio produto.
RUIDO_SEMPRE = ("favicon", "chrome-extension://", "ERR_INTERNET_DISCONNECTED")
RUIDO_SEM_SESSAO = ("401", "Unauthorized")


def _abre(page, base_url, timeout=30000):
    page.goto(f"{base_url}{PORTAL}", wait_until="load", timeout=timeout)
    page.wait_for_load_state("networkidle", timeout=timeout)


def _autentica(page, base_url):
    """Login pela API, reaproveitando o cookie jar do contexto do browser."""
    resposta = page.context.request.post(
        f"{base_url}/api/auth/login",
        data=json.dumps({"username": QA_USER, "password": QA_PASS}),
        headers={"Content-Type": "application/json"},
    )
    assert resposta.ok, (
        f"login de {QA_USER} falhou com {resposta.status} — credenciais erradas "
        "ou conta desactivada; as jornadas com sessao nao podem correr"
    )
    corpo = resposta.json()
    token = corpo.get("access_token") or corpo.get("token")
    assert token, f"login devolveu 200 mas sem token: {sorted(corpo)}"

    # O portal ainda le o token do localStorage (a migracao para cookie-only e'
    # o R2-03, por fechar). Injectamos antes de carregar a pagina.
    page.add_init_script(
        "(() => { try { localStorage.setItem('watcherdb_token', %s); } catch (e) {} })()"
        % json.dumps(token)
    )
    _abre(page, base_url)
    page.wait_for_function(
        "() => document.body && !/Carregando KPIs/i.test(document.body.innerText)",
        timeout=30000,
    )


class TestJ1PortalCarregaLimpo:
    """J1 — sem sessao, o portal ainda tem de carregar sem rebentar.

    Um SyntaxError num bloco de script derruba tudo o que vem depois nesse bloco;
    o sintoma sao ReferenceErrors em cascata de funcoes que 'desapareceram', e o
    defeito real fica escondido atras deles (incidente 2026-05-26).

    Corre SEM credenciais de proposito: e' o unico estado que nao depende de
    provisionamento e ja apanha a classe de bug mais destrutiva.
    """

    def test_sem_excepcao_por_apanhar(self, page, base_url):
        excepcoes = []
        page.on("pageerror", lambda e: excepcoes.append(str(e)))
        _abre(page, base_url)
        assert not excepcoes, "excepcao JS por apanhar ao carregar:\n  - " + "\n  - ".join(excepcoes[:5])

    def test_sem_erros_de_consola_alem_do_401_esperado(self, page, base_url):
        erros = []
        page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        _abre(page, base_url)
        tolerado = RUIDO_SEMPRE + RUIDO_SEM_SESSAO
        reais = [e for e in erros if not any(r.lower() in e.lower() for r in tolerado)]
        assert not reais, "erros de consola inesperados:\n  - " + "\n  - ".join(reais[:10])


@precisa_sessao
class TestJ2ControlosDeRoleAparecem:
    """J2 — R2-07: os controlos com gate tem de APARECER a quem tem o role.

    O defeito de 18/08 nao foi mostrar a quem nao devia; foi esconder de toda a
    gente, admin incluido, porque o `display:none` do markup ficou sem o atributo
    que o desligava. So' se ve com sessao: sem login, escondido e' o correcto.
    """

    def test_controlos_gated_ficam_visiveis(self, page, base_url):
        if QA_ROLE not in ("admin", "dba"):
            pytest.skip(f"conta de QA tem role '{QA_ROLE}'; esta jornada exige admin ou dba")
        _autentica(page, base_url)
        escondidos = page.evaluate(
            """() => Array.from(document.querySelectorAll('[data-dba-gated="1"]'))
                 .filter(el => getComputedStyle(el).display === 'none')
                 .map(el => el.id || (el.getAttribute('onclick') || el.tagName))"""
        )
        assert not escondidos, (
            f"role '{QA_ROLE}' devia ver estes controlos e nao os ve — forma do "
            f"R2-07: {escondidos}"
        )

    def test_botao_do_control_segue_o_role(self, page, base_url):
        _autentica(page, base_url)
        visivel = page.evaluate(
            """() => { const b = document.getElementById('controlPanelBtn');
                       return b ? getComputedStyle(b).display !== 'none' : null; }"""
        )
        assert visivel is not None, "botao controlPanelBtn nao existe no DOM"
        assert visivel == (QA_ROLE == "admin"), (
            f"controlPanelBtn visivel={visivel} para role '{QA_ROLE}' — "
            "esperado visivel so' para admin"
        )


@precisa_sessao
class TestJ3ModuloUtilizadores:
    """J3 — B-08: o modulo de Utilizadores nunca pode ficar em branco.

    Ecra vazio nao distingue 'nao ha utilizadores' de 'rebentou'. Com a sessao
    aberta e a lista mockada tem de aparecer conteudo; com lista vazia tem de
    aparecer um estado vazio EXPLICITO.
    """

    LISTA = {
        "success": True,
        "users": [
            {"username": "dba_teste", "role": "dba", "email": "dba@exemplo.local",
             "full_name": "DBA de Teste", "disabled": False},
        ],
    }

    def _mock(self, page, payload):
        page.route(
            "**/api/auth/users*",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps(payload)
            ),
        )

    def test_lista_com_utilizadores_renderiza(self, page, base_url):
        self._mock(page, self.LISTA)
        _autentica(page, base_url)
        page.evaluate("() => (typeof loadUsers === 'function') && loadUsers()")
        page.wait_for_timeout(1500)
        assert "dba_teste" in page.inner_text("body"), (
            "lista de utilizadores mockada nao apareceu no ecra"
        )

    def test_lista_vazia_da_estado_explicito(self, page, base_url):
        self._mock(page, {"success": True, "users": []})
        _autentica(page, base_url)
        page.evaluate("() => (typeof loadUsers === 'function') && loadUsers()")
        page.wait_for_timeout(1500)
        alvo = page.query_selector("#usersTableBody, #usersTable, [data-panel='users']")
        assert alvo is not None, "contentor da lista de utilizadores nao existe no DOM"
        assert (alvo.inner_text() or "").strip(), (
            "lista vazia deixou o contentor SEM TEXTO — 'sem utilizadores' e "
            "'rebentou' ficam indistinguiveis para quem olha"
        )


@precisa_sessao
class TestJ4IdiomaMudaTextoVisivel:
    """J4 — BUG-003: trocar de idioma tem de mudar TEXTO, nao so' o dicionario.

    O `tests/unit/test_i18n_parity.py` valida que pt/en/es tem as mesmas chaves e
    diz no proprio docstring que NAO cobre texto visivel sem chave. E' esse o
    buraco: dezenas de titulos de KPI estavam escritos a mao no HTML e nao
    mudavam de idioma nenhum, com a paridade de dicionario verde na mesma.
    """

    def _texto_visivel(self, page):
        return page.evaluate(
            """() => Array.from(document.querySelectorAll('h1,h2,h3,label,button,th'))
                 .map(e => (e.innerText || '').trim())
                 .filter(t => t.length > 2).join(' | ')"""
        )

    @pytest.mark.parametrize("idioma", ["en", "es"])
    def test_troca_de_idioma_altera_o_ecra(self, page, base_url, idioma):
        _autentica(page, base_url)
        antes = self._texto_visivel(page)
        assert antes, "portal autenticado sem texto visivel — carregou de facto?"

        trocou = page.evaluate(
            f"""() => {{
                 if (typeof setLanguage === 'function') {{ setLanguage('{idioma}'); return true; }}
                 if (typeof changeLanguage === 'function') {{ changeLanguage('{idioma}'); return true; }}
                 return false;
               }}"""
        )
        assert trocou, (
            "nao encontrei setLanguage/changeLanguage — o nome mudou e esta "
            "jornada deixou de guardar o que diz guardar"
        )
        page.wait_for_timeout(2000)
        assert self._texto_visivel(page) != antes, (
            f"trocar para '{idioma}' nao mudou uma palavra visivel — sinal de "
            "texto escrito a mao no HTML, fora do motor de i18n"
        )
