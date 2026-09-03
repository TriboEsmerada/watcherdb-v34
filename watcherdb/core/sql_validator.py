"""
SQL query validation using sqlparse.

Validates user-supplied SQL before execution to prevent:
- DDL operations (DROP, CREATE, ALTER, TRUNCATE)
- DML mutations (INSERT, UPDATE, DELETE, MERGE)
- Permission changes (GRANT, REVOKE, DENY)
- System commands (EXEC, EXECUTE, xp_, sp_)
"""
import re
import logging
import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DML, DDL

logger = logging.getLogger(__name__)

# Forbidden statement types
_FORBIDDEN_TYPES = {'DROP', 'CREATE', 'ALTER', 'TRUNCATE', 'INSERT', 'UPDATE',
                    'DELETE', 'MERGE', 'GRANT', 'REVOKE', 'DENY', 'EXEC', 'EXECUTE'}

# Forbidden patterns (even inside comments or strings)
_FORBIDDEN_PATTERNS = re.compile(
    r'\b(xp_|sp_configure|OPENROWSET|OPENDATASOURCE|BULK\s+INSERT|INTO\s+OUTFILE|'
    r'SHUTDOWN|RECONFIGURE|DBCC|BACKUP|RESTORE)\b',
    re.IGNORECASE
)


def validate_query(sql: str) -> tuple[bool, str]:
    """
    Validate a SQL query for safe read-only execution.

    Returns:
        (is_safe, error_message) — (True, "") if safe, (False, "reason") if blocked
    """
    if not sql or not sql.strip():
        return False, "Empty query"

    # Step 1: Check forbidden patterns on RAW input (before comment stripping)
    # This catches obfuscation like DR/**/OP where comments split keywords
    raw_no_space = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)  # strip block comments
    raw_no_space = re.sub(r'--[^\n]*', '', raw_no_space)           # strip line comments
    raw_collapsed = re.sub(r'\s+', ' ', raw_no_space).strip().upper()

    # Check if collapsed text contains forbidden keywords
    for forbidden in _FORBIDDEN_TYPES:
        if re.search(r'\b' + forbidden + r'\b', raw_collapsed):
            logger.warning(f"SQL validation blocked: forbidden keyword '{forbidden}' (post-collapse)")
            return False, f"Forbidden operation: {forbidden}"

    # Step 2: Normalize with sqlparse and check patterns
    cleaned = sqlparse.format(sql, strip_comments=True)

    if _FORBIDDEN_PATTERNS.search(cleaned):
        match = _FORBIDDEN_PATTERNS.search(cleaned)
        logger.warning(f"SQL validation blocked: forbidden pattern '{match.group()}'")
        return False, f"Forbidden operation: {match.group()}"

    # Parse and check statement types
    try:
        parsed = sqlparse.parse(cleaned)
        for statement in parsed:
            stmt_type = statement.get_type()
            if stmt_type and stmt_type.upper() in _FORBIDDEN_TYPES:
                logger.warning(f"SQL validation blocked: statement type '{stmt_type}'")
                return False, f"Forbidden statement type: {stmt_type}"

            # Check first meaningful token
            first_token = None
            for token in statement.tokens:
                if not token.is_whitespace:
                    first_token = token
                    break

            if first_token:
                word = str(first_token).upper().strip()
                if word in _FORBIDDEN_TYPES:
                    return False, f"Forbidden operation: {word}"
    except Exception as e:
        logger.error(f"SQL parse error: {e}")
        return False, f"Could not parse SQL: {e}"

    return True, ""
