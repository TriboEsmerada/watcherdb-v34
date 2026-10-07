"""Ferramentas de instalacao do WatcherDB, como subcomandos do executavel (2026-10-07).

Porque e' Python e nao PowerShell: a cifra Fernet so' existe aqui (services/secrets.py), pyodbc e o driver
ODBC ja' viajam no bundle, sqlcmd e Invoke-Sqlcmd nao existem em todas as maquinas, e o servidor alvo nao
tem Python -- so' o watcherdb.exe. Tudo fica testavel em pytest.

Regra de arranque: watcherdb_service.py so' importa este pacote DEPOIS de decidir o subcomando (import
tardio), para o arranque do servico continuar sem importar watcherdb.*/api.* (erro 1053 com EDR).

Omissoes do INSTALADOR para instalacoes novas (direccao do owner, 2026-10-07). Nao confundir com as
omissoes do runtime em watcherdb/core/db_identity.py, que sao a rede de seguranca da frota actual
(WatcherDB_Intelligence / sql_monitoring): o instalador escreve SEMPRE as chaves explicitas no .env.
"""
from __future__ import annotations

OMISSAO_BASE_INSTALADOR = "WatcherDB"
OMISSAO_LOGIN_INSTALADOR = "watcherdb"

__all__ = ["OMISSAO_BASE_INSTALADOR", "OMISSAO_LOGIN_INSTALADOR"]
