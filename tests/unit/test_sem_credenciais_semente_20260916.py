"""
2026-09-16 -- guarda permanente: nenhuma credencial-semente volta a entrar em scripts de instalacao, guias ou ferramentas.

Historia: tres sitios semeavam admin/admin123 (V3.4 legado, instalador V1, guias do cliente), um deles esteve num
repositorio publico, e o canonico tirou as sementes sem criar substituto. Este teste falha se voltar a aparecer
um hash bcrypt completo ou uma password-semente fora de comentario.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HASH_BCRYPT = re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}")
SEMENTES = re.compile(r"admin123|viewer123", re.IGNORECASE)
PASTAS = [("database", "*.sql"), ("deploy", "*.ps1"), ("deploy", "*.md"), ("docs/guides", "*.md"), ("tools", "*.py")]


def _ficheiros():
    for pasta, padrao in PASTAS:
        yield from sorted((ROOT / pasta).glob(padrao))


def _linha_e_comentario(linha, sufixo):
    s = linha.lstrip()
    return (sufixo == ".sql" and s.startswith("--")) or (sufixo in (".ps1", ".py") and s.startswith("#"))


def test_nenhum_hash_bcrypt_completo_em_scripts_guias_ou_ferramentas():
    culpados = [f"{p.relative_to(ROOT)}:{n}" for p in _ficheiros()
                for n, l in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
                if HASH_BCRYPT.search(l)]
    assert culpados == [], f"hash bcrypt escrito em ficheiro: {culpados}"


def test_nenhuma_password_semente_fora_de_comentario():
    culpados = []
    for p in _ficheiros():
        for n, l in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if SEMENTES.search(l) and not _linha_e_comentario(l, p.suffix):
                culpados.append(f"{p.relative_to(ROOT)}:{n}: {l.strip()[:80]}")
    assert culpados == [], "password-semente fora de comentario:\n" + "\n".join(culpados)


def test_os_guias_do_cliente_nao_publicam_credenciais():
    for nome in ("USER_GUIDE_PT.md", "USER_GUIDE_EN.md", "referencia_tecnica.md"):
        texto = (ROOT / "docs" / "guides" / nome).read_text(encoding="utf-8", errors="replace")
        assert not SEMENTES.search(texto), f"{nome} ainda publica uma password-semente"
        assert "bootstrap_admin.py" in texto, f"{nome} nao explica como nasce o primeiro administrador"


def test_o_instalador_nao_corre_o_legado_nem_o_07_e_corre_o_bootstrap():
    ps1 = (ROOT / "deploy" / "setup_database.ps1").read_text(encoding="utf-8", errors="replace")
    activos = [l for l in ps1.splitlines() if not l.lstrip().startswith("#")]
    texto = "\n".join(activos)
    assert '"CREATE_USER_AUTHENTICATION_SYSTEM.sql"' not in texto
    assert '"07_ADD_MUST_CHANGE_PASSWORD.sql"' not in texto
    assert '"14_ADD_MUST_CHANGE_PASSWORD.sql"' in texto
    assert "bootstrap_admin.py" in texto and "$SkipBootstrap" in texto


def test_o_script_legado_esta_marcado_como_historico():
    cab = (ROOT / "database" / "CREATE_USER_AUTHENTICATION_SYSTEM.sql").read_text(encoding="utf-8", errors="replace")[:900]
    assert "HISTORICO" in cab and "bootstrap_admin.py" in cab
