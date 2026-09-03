import pyodbc

# ============================================================================
# Schema unificado V3.2 + V5 — definido em
# database/10_FIX_FG_USAGE_DET_VIEW.sql (a 2026-04-08).
#
# A view dbo.KPI_MSSQL_FG_USAGE_DET_VIEW expoe:
#   * Colunas legacy V3.2: Instance, Database, Filegroup, Total_MB, Used_MB,
#                          Free_MB, Percent_Used, Max_Size_MB, Growth_Type, Update_TS
#   * Colunas novas V5:   Env, Current_MB, Used%, State
# ============================================================================

EXPECTED_COLUMNS = {
    # Legacy (V3.2 — antes da unificacao)
    'Instance', 'Database', 'Filegroup',
    'Total_MB', 'Used_MB', 'Free_MB', 'Percent_Used',
    'Max_Size_MB', 'Growth_Type', 'Update_TS',
    # Novo (V5 — schema unificado)
    'Env', 'Current_MB', 'Used%', 'State',
}


def _connect():
    return pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=SQLHDSTST505\\I01;'
        'DATABASE=WatcherDB_Intelligence;'
        'Trusted_Connection=yes;'
        'Connection Timeout=10'
    )


def test_view_has_unified_schema():
    """A view tem que expor TODAS as colunas do schema unificado V3.2 + V5."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 1 * FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW")
        columns = {column[0] for column in cursor.description}
        cursor.fetchall()
    finally:
        conn.close()

    missing = EXPECTED_COLUMNS - columns
    assert not missing, f"Missing columns in unified DET view: {missing}"


def test_state_classification_returns_known_values():
    """A coluna State so' deve devolver valores conhecidos do CASE."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT State
            FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW WITH (NOLOCK)
        """)
        states = {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()

    # 'OK' deve estar quase sempre presente; 'CRITICAL'/'WARNING' so se houver
    # filegroups proximos do limite. Aceitamos qualquer subconjunto destes 3.
    valid = {'OK', 'WARNING', 'CRITICAL'}
    invalid = states - valid
    assert not invalid, f"State column has unexpected values: {invalid}"


# ============================================================================
# Smoke script (standalone) — corre exploratoriamente quando o ficheiro e'
# executado directamente em vez de via pytest. Mantido para o workflow de
# debug interactivo do DBA — basta `python tests/integration/test_det_view.py`.
# ============================================================================

if __name__ == '__main__':
    conn = _connect()
    cursor = conn.cursor()

    # Test 0: Check column names in the view
    print("=== Test 0: Column names in DET view ===")
    cursor.execute("SELECT TOP 1 * FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW")
    columns = [column[0] for column in cursor.description]
    print(f"  Columns ({len(columns)}): {columns}")
    cursor.fetchall()

    # Test 1: Sample rows
    print("\n=== Test 1: Sample rows (TOP 5 ORDER BY Instance) ===")
    cursor.execute("SELECT TOP 5 * FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW ORDER BY 1")
    rows = cursor.fetchall()
    if rows:
        for r in rows:
            print(f'  {r}')
    else:
        print("  No data")

    # Test 2: Legacy V3.2 columns query
    print("\n=== Test 2: SQLMDMDEV03 filegroups (legacy V3.2 columns) ===")
    cursor.execute("""
        SELECT TOP 10 Instance, [Database], Filegroup, Percent_Used
        FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW
        WHERE Instance LIKE 'SQLMDMDEV03%'
        ORDER BY Percent_Used DESC
    """)
    rows = cursor.fetchall()
    if rows:
        for r in rows:
            print(f'  {r[0]} | {r[1]} | {r[2]} | {r[3]}%')
    else:
        print("  No data for SQLMDMDEV03")

    # Test 3: V5-style query (new schema columns Env + Current_MB + [Used%] + State)
    print("\n=== Test 3: V5-style query (CRITICAL/WARNING with State+Env+[Used%]) ===")
    cursor.execute("""
        SELECT TOP 5 Instance, ISNULL(Env, 'Undefined') AS Env,
               [Database], Filegroup, Used_MB, Current_MB, [Used%], State
        FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW
        WHERE State IN ('CRITICAL', 'WARNING')
        ORDER BY [Used%] DESC
    """)
    rows = cursor.fetchall()
    if rows:
        for r in rows:
            print(f'  {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]}MB | {r[5]}MB | {r[6]}% | {r[7]}')
    else:
        print("  No CRITICAL/WARNING filegroups")

    conn.close()
    print("\nDone!")
