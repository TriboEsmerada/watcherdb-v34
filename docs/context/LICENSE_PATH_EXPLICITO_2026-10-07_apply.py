# -*- coding: utf-8 -*-
"""Caminho configurado da licenca e' autoritativo (2026-10-07).

SINTOMA: tests/unit/test_startup_guard.py::test_startup_guard_grace_period_allows_missing_license vermelho
em qualquer maquina com licenca real instalada (na baseline do build, deploy/build_release.ps1:334-340).
O teste aponta WATCHERDB_LICENSE_PATH a um ficheiro inexistente e espera LicenseMissingError -> grace.

CAUSA: _resolve_license_path() devolvia o PRIMEIRO CANDIDATO QUE EXISTE. Com o explicito ausente caia em
C:\\ProgramData\\WatcherDB\\license.dat -- no PC1 e' a licenca do V3.3, assinada por outra chave ->
LicenseSignatureError -> SystemExit. Defeito de produto: um operador que configure WATCHERDB_LICENSE_PATH
(ou, desde o lote DATA_DIR_SERVICO, WATCHERDB_DATA_DIR) para uma pasta sem licenca valida em silencio a
licenca de outra instalacao em vez de reportar 'licenca em falta'.

REGRA NOVA: o primeiro nivel CONFIGURADO e' autoritativo.
  license.dat:   WATCHERDB_LICENSE_PATH  >  <WATCHERDB_DATA_DIR>/license.dat  >  C:\\ProgramData\\WatcherDB\\license.dat
  chave publica: WATCHERDB_PUBLIC_KEY_PATH (so' ele)  >  <DATA_DIR>/ed25519_public.pem ou (sem DATA_DIR)
                 C:\\ProgramData\\WatcherDB\\ed25519_public.pem, depois o fallback do bundle (base_dir/deploy/keys)
  CRL:           WATCHERDB_CRL_PATH (so' ele)  >  <DATA_DIR>/revoked_licenses.json ou (sem DATA_DIR) ProgramData,
                 depois o fallback do bundle. CRL ausente = sem revogacoes (load_crl_safe ja' trata).
Sem variaveis nada muda (dev e frota actual).

O QUE MUDA: watcherdb/licensing/startup_guard.py (3 funcoes), watcherdb/licensing/crl.py (_resolve_crl_path),
tests/unit/test_data_dir_servico_20261007.py (1 assert: ProgramData deixa de estar na lista quando ha' DATA_DIR),
deploy/build_release.ps1 (sai da baseline o teste que passa a passar), tests/unit/test_license_path_explicito_20261007.py (novo).

Uso:
  py docs/context/LICENSE_PATH_EXPLICITO_2026-10-07_apply.py --check | --preview | --repo <copia> | (aplica)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SG = Path("watcherdb/licensing/startup_guard.py")
CRL = Path("watcherdb/licensing/crl.py")
T_DD = Path("tests/unit/test_data_dir_servico_20261007.py")
BR = Path("deploy/build_release.ps1")
T_NEW = Path("tests/unit/test_license_path_explicito_20261007.py")

SG_OLD = '''def _resolve_license_path() -> Path:
    """Find license.dat em 3-tier priority (FIND-20260424-004 pattern)."""
    env_path = os.getenv("WATCHERDB_LICENSE_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # 2026-10-07: pasta de dados do servico (DATA_DIR_SERVICO)
    if _data_dir:
        candidates.append(Path(_data_dir) / "license.dat")
    candidates.append(Path(r"C:\\ProgramData\\WatcherDB\\license.dat"))
    # Bundle fallback — caller passa base_dir se quiser
    return next((p for p in candidates if p.exists()), candidates[-1])


def _resolve_public_key_path(base_dir: Optional[Path] = None) -> Path:
    """Find ed25519_public.pem em 3-tier priority (FIND-20260424-004)."""
    env_path = os.getenv("WATCHERDB_PUBLIC_KEY_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # 2026-10-07: DATA_DIR_SERVICO
    if _data_dir:
        candidates.append(Path(_data_dir) / "ed25519_public.pem")
    candidates.append(Path(r"C:\\ProgramData\\WatcherDB\\ed25519_public.pem"))
    if base_dir:
        candidates.append(base_dir / "deploy" / "keys" / "ed25519_public.pem")
    return next((p for p in candidates if p.exists()), candidates[-1])
'''
SG_NEW = '''def _resolve_license_path() -> Path:
    """license.dat: o primeiro nivel CONFIGURADO e' autoritativo (2026-10-07, LICENSE_PATH_EXPLICITO).

    WATCHERDB_LICENSE_PATH > <WATCHERDB_DATA_DIR>/license.dat > C:\\\\ProgramData\\\\WatcherDB\\\\license.dat (legado).
    Antes devolvia-se o primeiro candidato existente: um caminho explicito sem ficheiro caia em silencio na
    licenca de ProgramData -- numa maquina com outra instalacao (PC1: V3.3) validava-se a licenca errada em
    vez de reportar 'licenca em falta' (e o grace nunca entrava).
    """
    env_path = os.getenv("WATCHERDB_LICENSE_PATH")
    if env_path:
        return Path(env_path)
    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # DATA_DIR_SERVICO
    if _data_dir:
        return Path(_data_dir) / "license.dat"
    return Path(r"C:\\ProgramData\\WatcherDB\\license.dat")


def _resolve_public_key_path(base_dir: Optional[Path] = None) -> Path:
    """ed25519_public.pem: ver _public_key_candidates_tried (o explicito e' autoritativo; o bundle e' o fallback)."""
    candidates = _public_key_candidates_tried(base_dir)
    return next((p for p in candidates if p.exists()), candidates[-1])
'''
SG_TRIED_OLD = '''def _public_key_candidates_tried(base_dir: Optional[Path]) -> list:
    """For diagnostic messages — rebuild candidate list."""
    env_path = os.getenv("WATCHERDB_PUBLIC_KEY_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # 2026-10-07: DATA_DIR_SERVICO
    if _data_dir:
        candidates.append(Path(_data_dir) / "ed25519_public.pem")
    candidates.append(Path(r"C:\\ProgramData\\WatcherDB\\ed25519_public.pem"))
    if base_dir:
        candidates.append(base_dir / "deploy" / "keys" / "ed25519_public.pem")
    return candidates
'''
SG_TRIED_NEW = '''def _public_key_candidates_tried(base_dir: Optional[Path]) -> list:
    """Candidatos da chave publica, por ordem (2026-10-07, LICENSE_PATH_EXPLICITO).

    WATCHERDB_PUBLIC_KEY_PATH, se definido, e' o UNICO candidato. Senao: <WATCHERDB_DATA_DIR>/ed25519_public.pem
    quando ha' DATA_DIR, ou C:\\\\ProgramData\\\\WatcherDB\\\\ed25519_public.pem (legado) quando nao ha'; e por fim o
    fallback do bundle (base_dir/deploy/keys), porque a chave publica viaja no pacote.
    """
    env_path = os.getenv("WATCHERDB_PUBLIC_KEY_PATH")
    if env_path:
        return [Path(env_path)]
    candidates = []
    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # DATA_DIR_SERVICO
    if _data_dir:
        candidates.append(Path(_data_dir) / "ed25519_public.pem")
    else:
        candidates.append(Path(r"C:\\ProgramData\\WatcherDB\\ed25519_public.pem"))
    if base_dir:
        candidates.append(base_dir / "deploy" / "keys" / "ed25519_public.pem")
    return candidates
'''
CRL_OLD = '''def _resolve_crl_path(base_dir: Optional[Path] = None) -> Path:
    """3-tier priority: env var → ProgramData → bundle fallback."""
    env = os.getenv("WATCHERDB_CRL_PATH")
    candidates = []
    if env:
        candidates.append(Path(env))
    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # 2026-10-07: DATA_DIR_SERVICO
    if _data_dir:
        candidates.append(Path(_data_dir) / DEFAULT_CRL_FILENAME)
    candidates.append(DEFAULT_PROGRAMDATA / DEFAULT_CRL_FILENAME)
    if base_dir:
        candidates.append(Path(base_dir) / DEFAULT_CRL_FILENAME)
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]  # return last (likely non-existent — caller checks)
'''
CRL_NEW = '''def _resolve_crl_path(base_dir: Optional[Path] = None) -> Path:
    """CRL: o explicito e' autoritativo (2026-10-07, LICENSE_PATH_EXPLICITO).

    WATCHERDB_CRL_PATH, se definido, e' o unico candidato. Senao <WATCHERDB_DATA_DIR>/revoked_licenses.json
    quando ha' DATA_DIR, ou ProgramData (legado) quando nao ha'; depois o fallback do bundle. Ausente = sem
    revogacoes (load_crl_safe trata).
    """
    env = os.getenv("WATCHERDB_CRL_PATH")
    if env:
        return Path(env)
    candidates = []
    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # DATA_DIR_SERVICO
    if _data_dir:
        candidates.append(Path(_data_dir) / DEFAULT_CRL_FILENAME)
    else:
        candidates.append(DEFAULT_PROGRAMDATA / DEFAULT_CRL_FILENAME)
    if base_dir:
        candidates.append(Path(base_dir) / DEFAULT_CRL_FILENAME)
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]  # return last (likely non-existent — caller checks)
'''
T_DD_OLD = '''    tried = sg._public_key_candidates_tried(None)
    assert tried.index(tmp_path / "ed25519_public.pem") < tried.index(Path(r"C:\\\\ProgramData\\\\WatcherDB\\\\ed25519_public.pem"))
'''
T_DD_NEW = '''    tried = sg._public_key_candidates_tried(None)
    # 2026-10-07 (LICENSE_PATH_EXPLICITO): com DATA_DIR definido o caminho fixo de ProgramData sai da lista
    assert tried[0] == tmp_path / "ed25519_public.pem"
    assert all("ProgramData" not in str(p) for p in tried)
'''
BR_OLD = """    'tests.unit.test_qa_comprehensive.TestLevel6_ProjectHygiene::test_docs_organized_in_subdirs',
    'tests.unit.test_startup_guard::test_startup_guard_grace_period_allows_missing_license'
)
"""
BR_NEW = """    'tests.unit.test_qa_comprehensive.TestLevel6_ProjectHygiene::test_docs_organized_in_subdirs'
    # 2026-10-07: test_startup_guard_grace_period_allows_missing_license saiu da baseline -- passou a verde com
    # o lote LICENSE_PATH_EXPLICITO (caminho explicito autoritativo; antes caia na licenca real de ProgramData).
)
"""

EDITS = [(SG, SG_OLD, SG_NEW), (SG, SG_TRIED_OLD, SG_TRIED_NEW), (CRL, CRL_OLD, CRL_NEW), (T_DD, T_DD_OLD, T_DD_NEW), (BR, BR_OLD, BR_NEW)]

T_NEW_SRC = '''# -*- coding: utf-8 -*-
"""2026-10-07 -- LICENSE_PATH_EXPLICITO: o primeiro nivel configurado e' autoritativo.

Antes, um WATCHERDB_LICENSE_PATH (ou DATA_DIR) sem ficheiro caia em silencio na licenca de
C:\\\\ProgramData\\\\WatcherDB -- no PC1 a do V3.3 -> assinatura invalida em vez de 'licenca em falta'.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from watcherdb.licensing import startup_guard as sg
from watcherdb.licensing import crl as crlmod

_VARS = ("WATCHERDB_LICENSE_PATH", "WATCHERDB_PUBLIC_KEY_PATH", "WATCHERDB_CRL_PATH", "WATCHERDB_DATA_DIR")


@pytest.fixture()
def limpo(monkeypatch):
    for v in _VARS:
        monkeypatch.delenv(v, raising=False)
    return monkeypatch


def test_licenca_explicita_inexistente_nao_cai_em_programdata(limpo, tmp_path):
    alvo = tmp_path / "nao_existe.dat"
    limpo.setenv("WATCHERDB_LICENSE_PATH", str(alvo))
    assert sg._resolve_license_path() == alvo  # mesmo sem existir: o validador dira' 'licenca em falta'


def test_data_dir_sem_licenca_nao_cai_em_programdata(limpo, tmp_path):
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    assert sg._resolve_license_path() == tmp_path / "license.dat"


def test_sem_nada_configurado_fica_o_legado(limpo):
    assert sg._resolve_license_path() == Path(r"C:\\\\ProgramData\\\\WatcherDB\\\\license.dat")


def test_chave_publica_explicita_e_o_unico_candidato(limpo, tmp_path):
    limpo.setenv("WATCHERDB_PUBLIC_KEY_PATH", str(tmp_path / "k.pem"))
    assert sg._public_key_candidates_tried(tmp_path) == [tmp_path / "k.pem"]


def test_chave_publica_cai_no_bundle_quando_falta_na_pasta_de_dados(limpo, tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "deploy" / "keys").mkdir(parents=True)
    (bundle / "deploy" / "keys" / "ed25519_public.pem").write_text("x", encoding="utf-8")
    dados = tmp_path / "dados"
    dados.mkdir()
    limpo.setenv("WATCHERDB_DATA_DIR", str(dados))
    assert sg._resolve_public_key_path(bundle) == bundle / "deploy" / "keys" / "ed25519_public.pem"
    assert all("ProgramData" not in str(p) for p in sg._public_key_candidates_tried(bundle))


def test_chave_publica_sem_data_dir_mantem_programdata_e_bundle(limpo, tmp_path):
    tried = sg._public_key_candidates_tried(tmp_path)
    assert tried[0] == Path(r"C:\\\\ProgramData\\\\WatcherDB\\\\ed25519_public.pem")
    assert tried[-1] == tmp_path / "deploy" / "keys" / "ed25519_public.pem"


def test_crl_explicita_e_autoritativa(limpo, tmp_path):
    limpo.setenv("WATCHERDB_CRL_PATH", str(tmp_path / "nao_existe.json"))
    assert crlmod._resolve_crl_path(tmp_path) == tmp_path / "nao_existe.json"


def test_crl_com_data_dir_nao_cai_em_programdata(limpo, tmp_path):
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    p = crlmod._resolve_crl_path(None)
    assert p == tmp_path / crlmod.DEFAULT_CRL_FILENAME


def test_baseline_do_build_ja_nao_lista_o_teste_do_grace():
    br = (Path(__file__).resolve().parents[2] / "deploy" / "build_release.ps1").read_text(encoding="utf-8")
    assert "test_startup_guard_grace_period_allows_missing_license'" not in br
'''


def _read(root: Path, rel: Path) -> str:
    with open(root / rel, encoding="utf-8", newline="") as fh:
        return fh.read()


def check(root: Path) -> list[str]:
    p: list[str] = []
    for rel, velho, _novo in EDITS:
        t = _read(root, rel).replace("\r\n", "\n")
        c = t.count(velho)
        if c != 1:
            p.append(f"{rel}: ancora esperada 1x, encontrada {c}x: {velho.strip().splitlines()[0][:70]!r}")
        if "LICENSE_PATH_EXPLICITO" in t:
            p.append(f"{rel}: ja aplicado")
    if (root / T_NEW).exists():
        p.append(f"ja existe: {T_NEW}")
    return sorted(set(p))


def apply(root: Path, preview: bool) -> None:
    textos: dict[Path, str] = {}
    crlf: dict[Path, bool] = {}
    for rel, velho, novo in EDITS:
        if rel not in textos:
            bruto = _read(root, rel)
            crlf[rel] = "\r\n" in bruto
            textos[rel] = bruto.replace("\r\n", "\n")
        textos[rel] = textos[rel].replace(velho, novo, 1)
        print(f"{rel}: {velho.strip().splitlines()[0][:60]}")
    print(f"{T_NEW}: novo (9 testes)")
    if preview:
        print("\n--- preview: nada escrito ---")
        return
    for rel, txt in textos.items():
        with open(root / rel, "w", encoding="utf-8", newline="") as fh:
            fh.write(txt.replace("\n", "\r\n") if crlf[rel] else txt)
    (root / T_NEW).write_text(T_NEW_SRC, encoding="utf-8", newline="\n")
    print("\naplicado.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--repo", type=Path, default=ROOT)
    a = ap.parse_args()
    root = a.repo.resolve()
    p = check(root)
    if p:
        print("CHECK FALHOU:\n  " + "\n  ".join(p))
        return 1
    print(f"check ok em {root}")
    if a.check:
        return 0
    apply(root, a.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
