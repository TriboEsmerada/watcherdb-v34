"""
Server and connection models for WatcherDB
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ConnectionInfo:
    """SQL Server connection information"""
    host: str
    instance: str = "MSSQLSERVER"
    port: int = 1433
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    trusted_connection: bool = True
    driver: str = "ODBC Driver 17 for SQL Server"
    timeout: int = 30

    def get_connection_string(self) -> str:
        """Build ODBC connection string"""
        conn_str = f"DRIVER={{{self.driver}}};"
        conn_str += f"SERVER={self.host}"

        if self.instance and self.instance != "MSSQLSERVER":
            conn_str += f"\\{self.instance}"

        conn_str += f",{self.port};"

        if self.database:
            conn_str += f"DATABASE={self.database};"

        if self.trusted_connection:
            conn_str += "Trusted_Connection=yes;"
        else:
            if self.username:
                conn_str += f"UID={self.username};"
            if self.password:
                conn_str += f"PWD={self.password};"

        conn_str += f"Connection Timeout={self.timeout};"

        return conn_str


@dataclass
class ServerConfig:
    """SQL Server configuration"""
    id: int
    host: str
    instance: str = "MSSQLSERVER"
    port: int = 1433
    environment: str = "production"  # production, staging, development
    priority: str = "normal"  # critical, high, normal, low
    description: str = ""
    enabled: bool = True

    def to_connection_info(self) -> ConnectionInfo:
        """Convert to ConnectionInfo"""
        return ConnectionInfo(
            host=self.host,
            instance=self.instance,
            port=self.port
        )
