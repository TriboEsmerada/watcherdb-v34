"""
Security regression tests para allowlist de samAccountName / group name em api.routers.users.

Cobre P0 finding do audit 2026-04-22 (security-auditor): command injection potencial
via `$`, `(`, `)`, `;` em input AD quando passado para PowerShell script.

Allowlist rejeita qualquer char fora do set AD valido, bloqueando injection mesmo que
o contexto de uso mude no futuro (belt-and-suspenders vs. dependencia de PS single-quote).
"""
import pytest

from api.routers.users import _AD_SAM_NAME_PATTERN, _AD_GROUP_NAME_PATTERN


class TestSamAccountNameAllowlist:
    @pytest.mark.parametrize("sam", [
        "user.name",
        "user_name",
        "john-doe",
        "SRV01$",         # computer account (legitimo em AD)
        "svc.account",
        "a",              # min length 1
        "A" * 64,         # max length 64
        "USER123",
        "user.name-01",
    ])
    def test_accepts_valid_sam_names(self, sam):
        assert _AD_SAM_NAME_PATTERN.match(sam), f"Should accept {sam!r}"

    @pytest.mark.parametrize("malicious", [
        "user$(evil_cmd)",           # PS subshell syntax (mesmo se single-quoted eh literal)
        "user;ls",                    # command separator
        "user|cat /etc/passwd",       # pipe
        "user'; rm -rf /",            # quote escape + cmd
        "user&whoami",                # background
        "user`whoami`",               # backtick execution
        'user"inject"',               # double quote
        "user name",                  # space (nao valido em sam)
        "user\nnewline",              # newline
        "user\\backslash",            # backslash
        "user/forward",               # forward slash
        "user@domain",                # at sign
        "user=equal",                 # equal
        "",                           # empty
        "A" * 65,                     # over length limit
        "user(subexpr)",              # parentheses
        "user[bracket]",              # brackets
        "user{brace}",                # braces
    ])
    def test_rejects_injection_attempts(self, malicious):
        assert not _AD_SAM_NAME_PATTERN.match(malicious), f"Should reject {malicious!r}"


class TestADGroupNameAllowlist:
    @pytest.mark.parametrize("grp", [
        "Domain Admins",           # espaco eh legitimo em group names
        "DB-Admins",
        "Group_1",
        "SQL.Admins",
        "A" * 128,                 # max length 128
        "a",                       # min length 1
    ])
    def test_accepts_valid_group_names(self, grp):
        assert _AD_GROUP_NAME_PATTERN.match(grp), f"Should accept {grp!r}"

    @pytest.mark.parametrize("malicious", [
        "Group$evil",              # dollar nao permitido em grupos
        "Group;ls",                # command separator
        "Group|cat",               # pipe
        "Group&whoami",            # background
        "Group`cmd`",              # backtick
        "Group(cmd)",              # subexpression
        "Group'; DROP",            # quote escape
        'Group"attack"',           # double quote
        "",                        # empty
        "A" * 129,                 # over length
        "Group\nnewline",          # newline
        "Group\\back",             # backslash
    ])
    def test_rejects_injection_attempts(self, malicious):
        assert not _AD_GROUP_NAME_PATTERN.match(malicious), f"Should reject {malicious!r}"
