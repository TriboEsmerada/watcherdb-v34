"""Gera um ficheiro .regsrvr (SSMS Registered Servers) com as instancias do inventario.

Para correr um script nas 63 instancias de uma vez SEM codigo a ligar a bases de dados: o SSMS
importa o grupo, e "New Query" sobre o grupo executa em todas com a autenticacao da sessao SSMS.

NAO liga a nada. NAO escreve passwords (Windows Auth no .regsrvr; a conta e' a de quem abre o SSMS).
Saida em %TEMP% (fora do repo: contem hostnames; nao commitar).

Uso:  py scripts/qa/runtime/gera_regsrvr.py [--group WatcherDB-63] [--out %TEMP%\\watcherdb63.regsrvr]
Depois, no SSMS: View > Registered Servers > Local Server Groups > botao direito > Import... > o ficheiro.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[3]


def _target(e: dict) -> str:
    host = (e.get("host") or "").strip()
    inst = (e.get("instance") or "").strip()
    port = e.get("port")
    if inst and inst.upper() not in ("MSSQLSERVER", "DEFAULT"):
        return f"{host}\\{inst}"
    if port and int(port) != 1433:
        return f"{host},{port}"
    return host


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="WatcherDB-63")
    ap.add_argument("--out", default=os.path.join(os.environ.get("TEMP", "."), "watcherdb63.regsrvr"))
    ap.add_argument("--servers", default=str(ROOT / "config" / "servers.json"))
    args = ap.parse_args()

    with open(args.servers, encoding="utf-8") as fh:
        cfg = json.load(fh)
    entradas = [e for e in cfg.get("monitored_servers", cfg.get("servers", [])) if e.get("enabled") is not False]
    itens = []
    for e in entradas:
        sid = (e.get("id") or "").strip()
        tgt = _target(e)
        if not sid or not tgt:
            continue
        itens.append((sid, tgt, str(e.get("environment") or "")))
    if not itens:
        print("ABORT: nenhuma instancia no inventario")
        return 1

    # Formato do export do SSMS (SMO RegisteredServersStore, namespace 2007/08). Se o SSMS
    # recusar o import, o fallback e' registar o grupo a` mao ou via modulo PowerShell
    # SqlServer (SQLSERVER:\SQLRegistration) -- nenhum dos dois liga a bases de dados.
    NS = "http://schemas.microsoft.com/sqlserver/RegisteredServers/2007/08"

    def server_xml(name: str, target: str, desc: str) -> str:
        return f"""
    <RegisteredServers:RegisteredServer name="{escape(name, {'"': '&quot;'})}">
      <RegisteredServers:ServerType>8c91a03d-f9b4-46c0-a305-b5dcc79ff907</RegisteredServers:ServerType>
      <RegisteredServers:Description>{escape(desc)}</RegisteredServers:Description>
      <RegisteredServers:ServerName>{escape(target)}</RegisteredServers:ServerName>
      <RegisteredServers:UseCustomConnectionColor>false</RegisteredServers:UseCustomConnectionColor>
      <RegisteredServers:CustomConnectionColorArgb>-986896</RegisteredServers:CustomConnectionColorArgb>
      <RegisteredServers:ConnectionStringWithEncryptedPassword>server={escape(target)};trusted_connection=true;trustservercertificate=true;pooling=false;multipleactiveresultsets=false;packet size=4096;connect timeout=15;application name=WatcherDB-P2</RegisteredServers:ConnectionStringWithEncryptedPassword>
      <RegisteredServers:CredentialPersistenceType>None</RegisteredServers:CredentialPersistenceType>
    </RegisteredServers:RegisteredServer>"""

    body = "".join(server_xml(sid, tgt, amb) for sid, tgt, amb in sorted(itens))
    xml = f"""<?xml version="1.0"?>
<RegisteredServers:RegisteredServersStore xmlns:RegisteredServers="{NS}">
  <RegisteredServers:ServerGroup name="{escape(args.group, {'"': '&quot;'})}">
    <RegisteredServers:ServerType>8c91a03d-f9b4-46c0-a305-b5dcc79ff907</RegisteredServers:ServerType>
    <RegisteredServers:Description>Gerado de config/servers.json (WatcherDB V3.4, P2). Windows Auth da sessao SSMS.</RegisteredServers:Description>{body}
  </RegisteredServers:ServerGroup>
</RegisteredServers:RegisteredServersStore>
"""
    Path(args.out).write_text(xml, encoding="utf-8")
    print(f"{len(itens)} instancias -> {args.out}")
    print("SSMS: View > Registered Servers > Local Server Groups > botao direito > Import... (fica fora do repo; nao commitar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
