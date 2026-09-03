"""
Alembic environment configuration for WatcherDB V3.2

This project uses raw pyodbc (NOT SQLAlchemy ORM), so migrations
are written as raw SQL executed via op.execute().

Connection settings are read from the same environment variables
used by api/connection_pool.py:
  - INTELLIGENCE_SERVER  (default: SQLHDSTST505\\I01)
  - INTELLIGENCE_DATABASE (default: WatcherDB_Intelligence)
"""

import os
import sys
import pyodbc
from logging.config import fileConfig

from alembic import context

# O alembic corre standalone (fora do processo do servico). Poe a raiz do
# projecto no sys.path para reutilizar a resolucao de identidade em vez de
# duplicar a regra aqui -- foi a duplicacao que gerou o achado P-05.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from watcherdb.core.db_identity import enforce_explicit_identity  # noqa: E402
from services.secrets import get_secret  # noqa: E402

# Alembic Config object — access to .ini values
config = context.config

# Setup logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No SQLAlchemy metadata — we use raw SQL migrations
target_metadata = None


def get_pyodbc_connection_string() -> str:
    """Build pyodbc connection string from environment variables."""
    server = os.getenv("INTELLIGENCE_SERVER", r"SQLHDSTST505\I01")
    database = os.getenv("INTELLIGENCE_DATABASE", "WatcherDB_Intelligence")
    # Sem default implicito: uma migracao nunca deve ligar-se com a conta de
    # servico por omissao. Sem configuracao explicita, o alembic para aqui.
    use_windows_auth = enforce_explicit_identity().use_windows_auth

    driver = "ODBC Driver 17 for SQL Server"

    if use_windows_auth:
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Trusted_Connection=yes;"
            f"Connection Timeout=30;"
        )
    else:
        sql_user = os.getenv("INTELLIGENCE_SQL_USER", "sql_monitoring")
        # get_secret decifra o formato "encrypted:<fernet>" do .env (P-05).
        sql_password = get_secret("INTELLIGENCE_SQL_PASSWORD", "")
        if not sql_password:
            raise ValueError("SQL Authentication requires INTELLIGENCE_SQL_PASSWORD")
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={sql_user};"
            f"PWD={sql_password};"
            f"Connection Timeout=30;"
        )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL script only."""
    context.configure(
        url="mssql+pyodbc://",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects via pyodbc."""
    conn_str = get_pyodbc_connection_string()
    connection = pyodbc.connect(conn_str, autocommit=False)

    try:
        # Alembic expects a DBAPI connection; wrap it for the MigrationContext
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Use raw SQL transactions for MSSQL
            transaction_per_migration=True,
        )

        with context.begin_transaction():
            context.run_migrations()

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
