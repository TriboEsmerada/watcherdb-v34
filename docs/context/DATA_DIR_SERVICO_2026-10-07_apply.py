# -*- coding: utf-8 -*-
"""O servico empacotado nao sabia onde estava a pasta de dados (2026-10-07).

ACHADO (gate de release 2026-10-06, deploy-architect, ALTO): o codigo resolve a pasta de dados em
3 niveis -- env WATCHERDB_DATA_DIR > C:\\ProgramData\\WatcherDB (frozen) > raiz do projecto (dev)
(watcherdb/core/paths.py:33-39; copias em watcherdb_service.py:51-57 e watcherdb_main.py:30-38).
O instalador V3.4 provisiona master key, config e licenca em %ProgramData%\\WatcherDB\\V3.4
(release_vars.psd1:51 DataFolderName; install.ps1:226), define WATCHERDB_DATA_DIR so' no SEU processo
enquanto corre wrap-master-key (install.ps1 PASSO f) e nunca no ambiente do servico. Resultado
previsivel no servidor alvo: "No master key available" e licenca fail-close. O smoke do build define
a variavel e mascara o problema (build_release.ps1:564-567).

AGRAVANTE encontrada ao desenhar: o LICENCIAMENTO nem sequer honra WATCHERDB_DATA_DIR. So' aceita
variaveis por ficheiro (WATCHERDB_LICENSE_PATH, WATCHERDB_PUBLIC_KEY_PATH, WATCHERDB_INSTALL_MARKER_PATH,
WATCHERDB_CRL_PATH) ou o caminho fixo C:\\ProgramData\\WatcherDB (startup_guard.py:77,88,272;
grace_period.py:43,66; crl.py:61,145). Logo, pôr a variavel no servico resolveria pool/cache/.env mas
NAO a licenca nem a chave publica.

O QUE MUDA (5 ficheiros + 1 teste):
  watcherdb/licensing/startup_guard.py  license.dat e ed25519_public.pem: candidato <WATCHERDB_DATA_DIR>/...
                                        entre a variavel especifica e o caminho fixo (3 sitios).
  watcherdb/licensing/grace_period.py   install_marker.json: base = WATCHERDB_DATA_DIR quando definida.
  watcherdb/licensing/crl.py            revoked_licenses.json: idem.
  deploy/install.ps1                    depois de criar/reconfigurar o servico, grava no ambiente POR
                                        SERVICO (HKLM\\SYSTEM\\CurrentControlSet\\Services\\<nome>\\Environment,
                                        REG_MULTI_SZ) WATCHERDB_DATA_DIR=<DataDir> e WATCHERDB_PORT=<WebPort>,
                                        preservando outras entradas. O SCM aplica no proximo arranque;
                                        sem reboot, sem ambiente de maquina, sem tocar noutros servicos.
  tests/unit/test_data_dir_servico_20261007.py (novo)

O QUE NAO MUDA: a ordem de prioridade (variavel especifica continua a ganhar); dev sem variavel
(marker e CRL continuam em C:\\ProgramData\\WatcherDB, como hoje); watcherdb/core/paths.py (ja' honra a
variavel); o MSI (deploy/msi/Product.wxs so' define WATCHERDB_PORT como ambiente de maquina -- fica
para o lote do MSI; o veiculo do PC2 e' o ZIP + install.ps1).

Uso:
  py docs/context/DATA_DIR_SERVICO_2026-10-07_apply.py --check
  py docs/context/DATA_DIR_SERVICO_2026-10-07_apply.py --preview
  py docs/context/DATA_DIR_SERVICO_2026-10-07_apply.py --repo <copia>
  py docs/context/DATA_DIR_SERVICO_2026-10-07_apply.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SG = Path("watcherdb/licensing/startup_guard.py")
GP = Path("watcherdb/licensing/grace_period.py")
CRL = Path("watcherdb/licensing/crl.py")
INST = Path("deploy/install.ps1")
TEST = Path("tests/unit/test_data_dir_servico_20261007.py")

# (ficheiro, texto_antigo, texto_novo, ocorrencias_esperadas)
EDITS = [
    (SG,
     '    candidates.append(Path(r"C:\\ProgramData\\WatcherDB\\license.dat"))\n',
     '    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # 2026-10-07: pasta de dados do servico (DATA_DIR_SERVICO)\n'
     '    if _data_dir:\n'
     '        candidates.append(Path(_data_dir) / "license.dat")\n'
     '    candidates.append(Path(r"C:\\ProgramData\\WatcherDB\\license.dat"))\n',
     1),
    (SG,
     '    candidates.append(Path(r"C:\\ProgramData\\WatcherDB\\ed25519_public.pem"))\n',
     '    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # 2026-10-07: DATA_DIR_SERVICO\n'
     '    if _data_dir:\n'
     '        candidates.append(Path(_data_dir) / "ed25519_public.pem")\n'
     '    candidates.append(Path(r"C:\\ProgramData\\WatcherDB\\ed25519_public.pem"))\n',
     2),
    (GP,
     '    base = programdata_dir or DEFAULT_PROGRAMDATA\n',
     '    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # 2026-10-07: DATA_DIR_SERVICO\n'
     '    base = programdata_dir or (Path(_data_dir) if _data_dir else DEFAULT_PROGRAMDATA)\n',
     1),
    (CRL,
     '    candidates.append(DEFAULT_PROGRAMDATA / DEFAULT_CRL_FILENAME)\n',
     '    _data_dir = os.getenv("WATCHERDB_DATA_DIR")  # 2026-10-07: DATA_DIR_SERVICO\n'
     '    if _data_dir:\n'
     '        candidates.append(Path(_data_dir) / DEFAULT_CRL_FILENAME)\n'
     '    candidates.append(DEFAULT_PROGRAMDATA / DEFAULT_CRL_FILENAME)\n',
     1),
    (INST,
     '    Write-Ok "Servico $ServiceName reconfigurado (upgrade)."\n'
     '}\n',
     '    Write-Ok "Servico $ServiceName reconfigurado (upgrade)."\n'
     '}\n'
     '\n'
     '# 2026-10-07 (lote DATA_DIR_SERVICO): o servico tem de saber onde esta a pasta de dados. O codigo\n'
     '# resolve WATCHERDB_DATA_DIR em 3 niveis (watcherdb/core/paths.py) e o licenciamento tambem; sem a\n'
     '# variavel um bundle frozen procura em C:\\ProgramData\\WatcherDB, mas este instalador provisionou em\n'
     '# $DataDir (DataFolderName do SOT) -> "No master key available" e licenca fail-close. Ambiente POR\n'
     '# SERVICO (HKLM\\...\\Services\\<nome>\\Environment, REG_MULTI_SZ): o SCM aplica-o no proximo arranque,\n'
     '# sem reboot, sem tocar no ambiente da maquina nem noutros servicos. Entradas alheias sao preservadas.\n'
     "Write-Step 'PASSO (i-ter): ambiente do servico (WATCHERDB_DATA_DIR, WATCHERDB_PORT)'\n"
     '$svcRegPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\$ServiceName"\n'
     "$svcEnvWanted = [ordered]@{ 'WATCHERDB_DATA_DIR' = $DataDir; 'WATCHERDB_PORT' = [string]$rv.WebPort }\n"
     '$svcEnvExisting = @()\n'
     'try { $svcEnvExisting = @((Get-ItemProperty -Path $svcRegPath -Name Environment -ErrorAction Stop).Environment) } catch { $svcEnvExisting = @() }\n'
     "$svcEnvKept = @($svcEnvExisting | Where-Object { $_ -and (($_ -split '=', 2)[0] -notin @($svcEnvWanted.Keys)) })\n"
     '$svcEnvMerged = @($svcEnvKept) + @($svcEnvWanted.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" })\n'
     'Set-ItemProperty -Path $svcRegPath -Name Environment -Type MultiString -Value $svcEnvMerged\n'
     'Write-Ok "Ambiente do servico: WATCHERDB_DATA_DIR=$DataDir, WATCHERDB_PORT=$($rv.WebPort) (entradas alheias preservadas: $($svcEnvKept.Count))."\n',
     1),
]

TEST_SRC = '''# -*- coding: utf-8 -*-
"""2026-10-07 -- DATA_DIR_SERVICO: o licenciamento honra WATCHERDB_DATA_DIR e o instalador grava-a no servico.

Antes: startup_guard/grace_period/crl so' aceitavam variaveis por ficheiro ou C:\\\\ProgramData\\\\WatcherDB fixo,
e o install.ps1 provisionava em %ProgramData%\\\\WatcherDB\\\\V3.4 sem dizer ao servico onde era.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from watcherdb.licensing import startup_guard as sg
from watcherdb.licensing import grace_period as gp
from watcherdb.licensing import crl as crlmod

ROOT = Path(__file__).resolve().parents[2]
INSTALL = (ROOT / "deploy" / "install.ps1").read_text(encoding="utf-8").replace("\\r\\n", "\\n")

_ESPECIFICAS = ("WATCHERDB_LICENSE_PATH", "WATCHERDB_PUBLIC_KEY_PATH", "WATCHERDB_INSTALL_MARKER_PATH", "WATCHERDB_CRL_PATH")


@pytest.fixture()
def limpo(monkeypatch):
    for v in _ESPECIFICAS + ("WATCHERDB_DATA_DIR",):
        monkeypatch.delenv(v, raising=False)
    return monkeypatch


def test_licenca_na_pasta_de_dados(limpo, tmp_path):
    (tmp_path / "license.dat").write_text("x", encoding="utf-8")
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    assert sg._resolve_license_path() == tmp_path / "license.dat"


def test_chave_publica_na_pasta_de_dados(limpo, tmp_path):
    (tmp_path / "ed25519_public.pem").write_text("x", encoding="utf-8")
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    assert sg._resolve_public_key_path(None) == tmp_path / "ed25519_public.pem"
    tried = sg._public_key_candidates_tried(None)
    assert tried.index(tmp_path / "ed25519_public.pem") < tried.index(Path(r"C:\\\\ProgramData\\\\WatcherDB\\\\ed25519_public.pem"))


def test_a_variavel_especifica_continua_a_ganhar(limpo, tmp_path):
    esp = tmp_path / "outra" ; esp.mkdir()
    (esp / "lic.dat").write_text("x", encoding="utf-8")
    (tmp_path / "license.dat").write_text("x", encoding="utf-8")
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    limpo.setenv("WATCHERDB_LICENSE_PATH", str(esp / "lic.dat"))
    assert sg._resolve_license_path() == esp / "lic.dat"


def test_sem_variavel_o_caminho_fixo_mantem_se(limpo, tmp_path):
    # ficheiros inexistentes -> devolve o ultimo candidato, como antes
    assert sg._resolve_license_path() == Path(r"C:\\\\ProgramData\\\\WatcherDB\\\\license.dat")
    assert gp._resolve_marker_path() == gp.DEFAULT_PROGRAMDATA / gp.DEFAULT_MARKER_FILENAME


def test_marker_do_grace_na_pasta_de_dados(limpo, tmp_path):
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    assert gp._resolve_marker_path() == tmp_path / gp.DEFAULT_MARKER_FILENAME
    # argumento explicito continua a ganhar (usado pelos testes antigos)
    assert gp._resolve_marker_path(tmp_path / "x") == tmp_path / "x" / gp.DEFAULT_MARKER_FILENAME


def test_crl_na_pasta_de_dados(limpo, tmp_path):
    (tmp_path / crlmod.DEFAULT_CRL_FILENAME).write_text("{}", encoding="utf-8")
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    assert crlmod._resolve_crl_path(None) == tmp_path / crlmod.DEFAULT_CRL_FILENAME


def test_instalador_grava_o_ambiente_do_servico():
    i = INSTALL.index("PASSO (i-ter): ambiente do servico")
    bloco = INSTALL[i:i + 1600]
    assert "HKLM:\\\\SYSTEM\\\\CurrentControlSet\\\\Services\\\\$ServiceName" in bloco
    assert "'WATCHERDB_DATA_DIR' = $DataDir" in bloco
    assert "'WATCHERDB_PORT' = [string]$rv.WebPort" in bloco
    assert "-Type MultiString" in bloco
    assert "$svcEnvKept" in bloco, "entradas alheias do Environment tem de ser preservadas"
    # depois de criar/reconfigurar o servico e antes do passo seguinte
    assert INSTALL.index("reconfigurado (upgrade)") < i < INSTALL.index("PASSO (i-bis)")
'''


def _read(root: Path, rel: Path) -> str:
    with open(root / rel, encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_como_original(root: Path, rel: Path, txt_lf: str, crlf: bool) -> None:
    with open(root / rel, "w", encoding="utf-8", newline="") as fh:
        fh.write(txt_lf.replace("\n", "\r\n") if crlf else txt_lf)


def check(root: Path) -> list[str]:
    p: list[str] = []
    for rel, velho, _novo, n in EDITS:
        t = _read(root, rel).replace("\r\n", "\n")
        c = t.count(velho)
        if c != n:
            p.append(f"{rel}: ancora esperada {n}x, encontrada {c}x: {velho.strip()[:60]!r}")
        if "DATA_DIR_SERVICO" in t:
            p.append(f"{rel}: ja aplicado")
    if (root / TEST).exists():
        p.append(f"ja existe: {TEST}")
    return sorted(set(p))


def apply(root: Path, preview: bool) -> None:
    por_ficheiro: dict[Path, str] = {}
    crlf: dict[Path, bool] = {}
    for rel, velho, novo, n in EDITS:
        if rel not in por_ficheiro:
            bruto = _read(root, rel)
            crlf[rel] = "\r\n" in bruto
            por_ficheiro[rel] = bruto.replace("\r\n", "\n")
        por_ficheiro[rel] = por_ficheiro[rel].replace(velho, novo, n)
        print(f"{rel}: {n} edicao(oes) -> {novo.strip().splitlines()[0][:70]}")
    print(f"{TEST}: novo (7 testes)")
    if preview:
        print("\n--- preview: nada escrito ---")
        return
    for rel, txt in por_ficheiro.items():
        _write_como_original(root, rel, txt, crlf[rel])
    (root / TEST).write_text(TEST_SRC, encoding="utf-8", newline="\n")
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
