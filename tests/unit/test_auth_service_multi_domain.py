"""
Unit tests for _authenticate_ldap multi-domain pipeline (FIND-20260428-006).

Closes coverage gap identificado pelo qa-specialist em sweep Fase 4.3:
- tests/unit/test_ad_input_validation.py:42 testa apenas regex de input validation
  (cria falsa sensacao de coverage). Auth path real estava untested.
- 5 cenarios canonicos cobrindo Patch D (commit 691a529) multi-domain logic.

Cenarios cobertos:
    (a) AD_DOMAINS=[] fallback single-domain via AD_SERVER/AD_DOMAIN/AD_BASE_DN
    (b) fan-out N domains - sucesso no domain N (testa iteracao + first-hit-wins)
    (c) user@fqdn filter - filtra domains_to_try para FQDN match
    (d) DOM\\user NetBIOS filter - filtra para NetBIOS short label
    (e) wrong password em multi-domain - todos falham, retorna None

Mock _try_single_domain_bind via unittest.mock.patch - sem live LDAP necessario.
Charters: watcherdb-qa-specialist (pattern dois olhares - tech + user).

Cross-links:
- ADR-019 Ed25519 license operations (security context)
- findings-inbox.md FIND-20260428-006 (P0 coverage)
- services/auth_service.py:_authenticate_ldap (linha ~860)
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


# ============================================================================
# Helpers
# ============================================================================

def _user_info_for_domain(domain: str, username: str = "alice") -> dict:
    """Mock _try_single_domain_bind success return shape."""
    return {
        "username": username,
        "ad_domain": domain,
        "display_name": f"{username.title()} Test",
        "groups": [f"CN=DBA-Team,OU=Groups,DC={domain.replace('.', ',DC=')}"],
        "email": f"{username}@{domain}",
    }


@pytest.fixture
def auth_module():
    """Import + reset auth_service globals to predictable test state.

    Resets AD_ENABLED + AD_DOMAINS + singular AD_* vars per test to avoid
    cross-test pollution.
    """
    from services import auth_service as auth
    # Snapshot
    snap = {
        "AD_ENABLED": auth.AD_ENABLED,
        "_has_ldap": auth._has_ldap,
        "AD_DOMAINS": list(auth.AD_DOMAINS),
        "AD_SERVER": auth.AD_SERVER,
        "AD_DOMAIN": auth.AD_DOMAIN,
        "AD_BASE_DN": auth.AD_BASE_DN,
        "AD_DEFAULT_ROLE": auth.AD_DEFAULT_ROLE,
    }
    # Test setup: enable AD + ldap3 simulated
    auth._has_ldap = True
    auth.AD_ENABLED = True
    auth.AD_DOMAINS = []
    auth.AD_SERVER = ""
    auth.AD_DOMAIN = ""
    auth.AD_BASE_DN = ""
    auth.AD_DEFAULT_ROLE = "viewer"
    yield auth
    # Teardown: restore
    for k, v in snap.items():
        setattr(auth, k, v)


# ============================================================================
# (a) AD_DOMAINS=[] fallback single-domain
# ============================================================================

def test_a_fallback_single_domain_when_ad_domains_empty(auth_module):
    """AD_DOMAINS=[] mas AD_SERVER set -> fallback usa singulares."""
    auth_module.AD_DOMAINS = []
    auth_module.AD_SERVER = "dc01.legacy.local"
    auth_module.AD_DOMAIN = "legacy.local"
    auth_module.AD_BASE_DN = "DC=legacy,DC=local"

    captured_dom_cfgs = []

    def mock_bind(username, password, dom_cfg, connect_timeout):
        captured_dom_cfgs.append(dict(dom_cfg))
        return _user_info_for_domain("legacy.local", username)

    with patch.object(auth_module, "_try_single_domain_bind", side_effect=mock_bind):
        result = auth_module._authenticate_ldap("alice", "Secret123!")

    assert result is not None, "Expected successful auth in single-domain fallback"
    assert result["ad_domain"] == "legacy.local"
    assert len(captured_dom_cfgs) == 1, "Esperava exactamente 1 bind attempt (fallback)"
    assert captured_dom_cfgs[0]["server"] == "dc01.legacy.local"
    assert captured_dom_cfgs[0]["domain"] == "legacy.local"


# ============================================================================
# (b) Fan-out N domains - sucesso no domain N (first-hit-wins)
# ============================================================================

def test_b_fanout_success_on_third_domain(auth_module):
    """3 domains config: 2 falham, 3 sucede. First-hit-wins."""
    auth_module.AD_DOMAINS = [
        {"domain": "dom1.local", "server": "dc01.dom1.local", "base_dn": "DC=dom1,DC=local"},
        {"domain": "dom2.local", "server": "dc01.dom2.local", "base_dn": "DC=dom2,DC=local"},
        {"domain": "dom3.local", "server": "dc01.dom3.local", "base_dn": "DC=dom3,DC=local"},
    ]

    call_log = []

    def mock_bind(username, password, dom_cfg, connect_timeout):
        call_log.append(dom_cfg["domain"])
        if dom_cfg["domain"] == "dom3.local":
            return _user_info_for_domain("dom3.local", username)
        return None  # fail

    with patch.object(auth_module, "_try_single_domain_bind", side_effect=mock_bind):
        result = auth_module._authenticate_ldap("alice", "Secret123!")

    assert result is not None, "Expected fan-out success no third domain"
    assert result["ad_domain"] == "dom3.local"
    assert call_log == ["dom1.local", "dom2.local", "dom3.local"], (
        "Esperava iteracao em ordem ate' first hit (3 attempts)"
    )


# ============================================================================
# (c) user@fqdn filter
# ============================================================================

def test_c_explicit_fqdn_filters_to_matching_domain_only(auth_module):
    """username 'alice@dom2.local' -> filtra para dom2 apenas (skip dom1, dom3)."""
    auth_module.AD_DOMAINS = [
        {"domain": "dom1.local", "server": "dc01.dom1.local", "base_dn": "DC=dom1,DC=local"},
        {"domain": "dom2.local", "server": "dc01.dom2.local", "base_dn": "DC=dom2,DC=local"},
        {"domain": "dom3.local", "server": "dc01.dom3.local", "base_dn": "DC=dom3,DC=local"},
    ]

    call_log = []

    def mock_bind(username, password, dom_cfg, connect_timeout):
        call_log.append(dom_cfg["domain"])
        # username deve ja ter sido stripped do dominio
        assert username == "alice", f"clean_username deve ser 'alice', got '{username}'"
        return _user_info_for_domain("dom2.local", username)

    with patch.object(auth_module, "_try_single_domain_bind", side_effect=mock_bind):
        result = auth_module._authenticate_ldap("alice@dom2.local", "Secret123!")

    assert result is not None
    assert result["ad_domain"] == "dom2.local"
    assert call_log == ["dom2.local"], (
        f"Esperava filter para 1 domain so', got {call_log}"
    )


# ============================================================================
# (d) DOM\user NetBIOS filter
# ============================================================================

def test_d_explicit_netbios_filters_to_matching_domain(auth_module):
    """username 'TAPNET\\alice' -> filtra para tapnet.tap.pt (NetBIOS short match)."""
    auth_module.AD_DOMAINS = [
        {"domain": "tapnet.tap.pt", "server": "dc.tapnet.tap.pt", "base_dn": "DC=tapnet,DC=tap,DC=pt"},
        {"domain": "external.tap.pt", "server": "dc.external.tap.pt", "base_dn": "DC=external,DC=tap,DC=pt"},
    ]

    call_log = []

    def mock_bind(username, password, dom_cfg, connect_timeout):
        call_log.append(dom_cfg["domain"])
        assert username == "alice", f"NetBIOS clean_username deve ser 'alice', got '{username}'"
        return _user_info_for_domain("tapnet.tap.pt", username)

    with patch.object(auth_module, "_try_single_domain_bind", side_effect=mock_bind):
        result = auth_module._authenticate_ldap("TAPNET\\alice", "Secret123!")

    assert result is not None
    assert result["ad_domain"] == "tapnet.tap.pt"
    assert call_log == ["tapnet.tap.pt"], (
        f"Esperava NetBIOS filter para tapnet so', got {call_log}"
    )


# ============================================================================
# (e) Wrong password em multi-domain - todos falham, retorna None
# ============================================================================

def test_e_wrong_password_all_domains_fail_returns_none(auth_module):
    """Wrong password: todos os 3 domains falham -> retorna None."""
    auth_module.AD_DOMAINS = [
        {"domain": "dom1.local", "server": "dc01.dom1.local", "base_dn": "DC=dom1,DC=local"},
        {"domain": "dom2.local", "server": "dc01.dom2.local", "base_dn": "DC=dom2,DC=local"},
        {"domain": "dom3.local", "server": "dc01.dom3.local", "base_dn": "DC=dom3,DC=local"},
    ]

    call_log = []

    def mock_bind_always_fail(username, password, dom_cfg, connect_timeout):
        call_log.append(dom_cfg["domain"])
        return None  # always fail

    with patch.object(auth_module, "_try_single_domain_bind", side_effect=mock_bind_always_fail):
        result = auth_module._authenticate_ldap("alice", "WrongPassword!")

    assert result is None, (
        "Expected None quando todas as bind attempts falham (multi-domain auth fail)"
    )
    assert call_log == ["dom1.local", "dom2.local", "dom3.local"], (
        "Esperava iteracao por TODOS os 3 domains antes de desistir"
    )


# ============================================================================
# Sanity: AD disabled / ldap3 missing -> bypass
# ============================================================================

def test_sanity_ad_disabled_returns_none_without_calling_bind(auth_module):
    """AD_ENABLED=False -> early return None, never touches _try_single_domain_bind."""
    auth_module.AD_ENABLED = False

    with patch.object(auth_module, "_try_single_domain_bind") as mock_bind:
        result = auth_module._authenticate_ldap("alice", "Secret123!")

    assert result is None
    mock_bind.assert_not_called()


def test_sanity_ldap3_unavailable_returns_none(auth_module):
    """_has_ldap=False -> early return None (ldap3 not installed)."""
    auth_module._has_ldap = False

    with patch.object(auth_module, "_try_single_domain_bind") as mock_bind:
        result = auth_module._authenticate_ldap("alice", "Secret123!")

    assert result is None
    mock_bind.assert_not_called()
