# WatcherDB V3.2 — Guia de Deploy em Producao

> ⚠️ **DEPRECATED (audit 2026-04-22 / S2-8)**
>
> Este documento refere valores obsoletos (V3.2, porta 8449, `WatcherDBWebServiceV32`).
> O produto actual e **V3.3 Standard Edition** com porta **8433** e servico
> **WatcherDBWebServiceV33**. Os scripts referenciados abaixo (`install_wizard.py`,
> `install_watcherdb.ps1`, `install_production.ps1`) foram convertidos em stubs
> que terminam com `exit 1`.
>
> **CAMINHO CANONICO DE INSTALACAO:**
> - Artefacto: `dist\msi\WatcherDB_V3.3_Standard.msi`
> - Operador: [`deploy/msi/README.md`](msi/README.md)
> - Cliente: [`docs/external/standard/INSTALL_GUIDE.md`](../docs/external/standard/INSTALL_GUIDE.md)
>
> Este documento permanece no repo apenas para referencia historica.

---

## Arquitectura

```
SERVIDOR APLICACIONAL
├── C:\WatcherDB\                    ← Aplicacao (codigo protegido)
│   ├── services\web_service\        ← Servico Windows (porta 8449)
│   ├── config\                      ← Configuracoes
│   ├── templates\                   ← Frontend HTML
│   ├── static\                      ← CSS, JS, imagens
│   └── database\                    ← Scripts SQL
│
└── Servico: WatcherDBWebServiceV32

SQL SERVER
└── WatcherDB_Intelligence           ← Base de dados
```

## Pre-requisitos

| Componente | Versao | Download |
|-----------|--------|----------|
| Python | 3.11+ | https://python.org/downloads |
| ODBC Driver | 17 ou 18 | https://learn.microsoft.com/sql/connect/odbc |
| SQL Server | 2016+ | Existente |
| PyArmor | Basic ($99) | https://pyarmor.dashingsoft.com |

## Passo a Passo

### 1. BUILD (no PC de desenvolvimento)

```powershell
cd C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.2

# Instalar PyArmor (se ainda nao tiver)
pip install pyarmor

# Activar licenca (so uma vez)
pyarmor reg pyarmor-regcode-xxx.zip

# Gerar pacote protegido
python deploy/build.py
```

Resultado: `dist/WatcherDB_V3.2/` com codigo encriptado.

### 2. COPIAR para o servidor

```powershell
# Via rede
robocopy "dist\WatcherDB_V3.2" "\\SERVIDOR\c$\WatcherDB" /E

# Ou via USB/RDP
# Copiar a pasta dist/WatcherDB_V3.2 para C:\WatcherDB no servidor
```

### 3. INSTALAR no servidor

```powershell
# No servidor, como Administrador:
cd C:\WatcherDB\deploy
.\install_production.ps1 -SqlServer "SQLSERVER\INSTANCIA" -Port 8449
```

### 4. CRIAR BASE DE DADOS

```powershell
cd C:\WatcherDB\deploy
.\setup_database.ps1 -SqlServer "SQLSERVER\INSTANCIA"
```

### 5. CONFIGURAR

Editar `C:\WatcherDB\.env`:
```
JWT_SECRET_KEY=<gerado automaticamente>
WATCHERDB_ENCRYPTION_KEY=<gerado automaticamente>
INTELLIGENCE_SERVER=SQLSERVER\INSTANCIA
INTELLIGENCE_DATABASE=WatcherDB_Intelligence
```

### 6. CONFIGURAR CONTA DE SERVICO

```powershell
# services.msc → WatcherDB Web Service V3.2 → Properties → Log On
# Usar conta de dominio com permissao SQL Server
```

### 7. VERIFICAR

```powershell
# Health check
curl http://localhost:8449/health/web-service

# Portal
# Abrir browser: http://SERVIDOR:8449/watcherdb
# Login: admin / (senha definida na BD)
```

## Actualizacoes

```powershell
# 1. No PC de dev: rebuild
python deploy/build.py

# 2. No servidor: parar servico
net stop WatcherDBWebServiceV32

# 3. Copiar novos ficheiros
robocopy "dist\WatcherDB_V3.2" "C:\WatcherDB" /E /XF .env

# 4. Reiniciar
net start WatcherDBWebServiceV32
```

**IMPORTANTE:** Nunca sobrescrever `.env` — contem secrets do servidor.

## Troubleshooting

| Problema | Solucao |
|----------|---------|
| Servico nao arranca | Verificar logs: `C:\WatcherDB\services\web_service\logs\` |
| Portal nao abre | Verificar porta: `netstat -ano \| findstr 8449` |
| Login falha | Verificar conexao SQL: `.env` → INTELLIGENCE_SERVER |
| Permissao negada | Conta de servico precisa de login SQL Server |
