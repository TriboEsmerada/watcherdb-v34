"""Etapa 1.4 (auditoria empacotamento): master key em ficheiro DPAPI machine-scope.

Valida a cadeia de resolucao de services.secrets:
  1. ficheiro master.key.dpapi (DPAPI machine-scope)  <- novo tier de topo
  2. WATCHERDB_ENCRYPTION_KEY_DPAPI (DPAPI user-scope, legacy)
  3. WATCHERDB_ENCRYPTION_KEY (plain, backwards compat)

Roundtrip DPAPI REAL via win32crypt — Windows-only, sem privilegios admin
(a flag CRYPTPROTECT_LOCAL_MACHINE nao exige elevacao).
"""
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="DPAPI/pywin32 sao Windows-only"
)

from cryptography.fernet import Fernet

from services import secrets as secrets_mod


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    secrets_mod.clear_cache()
    for var in (
        "WATCHERDB_ENCRYPTION_KEY",
        "WATCHERDB_ENCRYPTION_KEY_DPAPI",
        "WATCHERDB_MASTER_KEY_FILE",
        "WATCHERDB_SECRETS_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
    secrets_mod.clear_cache()


def test_provision_and_resolve_machine_scope(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    target = tmp_path / "master.key.dpapi"
    monkeypatch.setenv("WATCHERDB_MASTER_KEY_FILE", str(target))
    written = secrets_mod.provision_master_key_file(key)
    assert Path(written) == target
    assert target.is_file()
    # o ficheiro contem o blob DPAPI em base64, nunca a chave em claro
    assert key not in target.read_bytes()
    assert secrets_mod._get_master_key() == key


def test_file_tier_has_priority_over_plain_env(tmp_path, monkeypatch):
    file_key = Fernet.generate_key()
    env_key = Fernet.generate_key()
    monkeypatch.setenv(
        "WATCHERDB_MASTER_KEY_FILE", str(tmp_path / "master.key.dpapi")
    )
    secrets_mod.provision_master_key_file(file_key)
    monkeypatch.setenv("WATCHERDB_ENCRYPTION_KEY", env_key.decode())
    secrets_mod.clear_cache()
    assert secrets_mod._get_master_key() == file_key


def test_plain_env_fallback_unchanged(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    # ficheiro inexistente -> cai para o tier plain (backwards compat)
    monkeypatch.setenv(
        "WATCHERDB_MASTER_KEY_FILE", str(tmp_path / "missing.dpapi")
    )
    monkeypatch.setenv("WATCHERDB_ENCRYPTION_KEY", key.decode())
    assert secrets_mod._get_master_key() == key


def test_get_secret_roundtrip_with_file_key(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setenv(
        "WATCHERDB_MASTER_KEY_FILE", str(tmp_path / "master.key.dpapi")
    )
    secrets_mod.provision_master_key_file(key)
    token = secrets_mod.encrypt_value("s3nh4-de-teste")
    assert token.startswith("encrypted:")
    monkeypatch.setenv("WDB_TEST_SECRET_ETAPA2", token)
    assert secrets_mod.get_secret("WDB_TEST_SECRET_ETAPA2") == "s3nh4-de-teste"


def test_try_get_master_key_returns_none_without_keys(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "WATCHERDB_MASTER_KEY_FILE", str(tmp_path / "missing.dpapi")
    )
    assert secrets_mod.try_get_master_key() is None
