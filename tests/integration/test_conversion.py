import pyodbc

# Teste de conversão
instance = 'SQLHDSPRD212_I01'
database = 'master'
filegroup = 'PRIMARY'

# Converter formato
instance_sql = instance
if '_I' in instance_sql and '\\' not in instance_sql:
    parts = instance_sql.split('_I')
    instance_sql = f"{parts[0]}\\I{parts[1]}"

print(f"Original: {instance}")
print(f"Convertido: {instance_sql}")

# Testar query
watcherdb_server = "SQLHDSTST505\\I01"
watcherdb_database = "WatcherDB_Intelligence"

conn_str = (
    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    f'SERVER={watcherdb_server};'
    f'DATABASE={watcherdb_database};'
    f'Trusted_Connection=yes;'
    f'Connection Timeout=30;'
)

print(f"\nConectando: {watcherdb_server}")
conn = pyodbc.connect(conn_str)

query = f"""
SELECT TOP 1
    Instance,
    [Database],
    Filegroup,
    CAST(Total_MB AS FLOAT) AS Size_MB,
    CAST(Used_MB AS FLOAT) AS Used_MB,
    CAST(Percent_Used AS FLOAT) AS Used_PCT,
    Update_TS
FROM dbo.KPI_MSSQL_FG_USAGE_STG
WHERE Instance = '{instance_sql}'
  AND [Database] = '{database}'
  AND Filegroup = '{filegroup}'
ORDER BY Update_TS DESC
"""

print(f"\nQuery:")
print(query)

cursor = conn.cursor()
cursor.execute(query)
row = cursor.fetchone()

if row:
    print(f"\n✓ ENCONTRADO!")
    print(f"Instance: {row[0]}")
    print(f"Database: {row[1]}")
    print(f"Filegroup: {row[2]}")
    print(f"Total MB: {row[3]}")
    print(f"Percent Used: {row[5]}%")
else:
    print(f"\n✗ NÃO ENCONTRADO")
    print(f"\nVerificando se existe algum dado para este instance...")
    cursor.execute("SELECT COUNT(*) FROM dbo.KPI_MSSQL_FG_USAGE_STG WHERE Instance LIKE ?", (f"%{instance.split('_')[0]}%",))
    count = cursor.fetchone()[0]
    print(f"Registros encontrados com '{instance.split('_')[0]}': {count}")

conn.close()
