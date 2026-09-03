# WatcherDB V3.2 — Checklist de Deploy

> ⚠️ **DEPRECATED (audit 2026-04-22 / S2-8)**
>
> Este checklist refere valores obsoletos (V3.2, porta 8449). Produto actual
> e V3.3 Standard com porta 8433 e servico `WatcherDBWebServiceV33`.
>
> **Usar:** [`docs/external/standard/INSTALL_GUIDE.md`](../docs/external/standard/INSTALL_GUIDE.md)
> em substituicao deste documento.

---

## Servidor: _________________ | Data: ____/____/2026 | Responsavel: _____________

### PRE-REQUISITOS
- [ ] Python 3.11+ instalado no servidor
- [ ] ODBC Driver 17/18 for SQL Server instalado
- [ ] SQL Server acessivel a partir do servidor
- [ ] Conta de dominio para o servico (com login SQL Server)
- [ ] Porta 8449 disponivel
- [ ] PyArmor licenca activada (no PC de desenvolvimento)

### BUILD (PC de desenvolvimento)
- [ ] `python deploy/build.py` executado com sucesso
- [ ] `dist/WatcherDB_V3.2/` gerado sem erros
- [ ] VERSION.txt confirma data e versao

### COPIA
- [ ] `dist/WatcherDB_V3.2/` copiado para `C:\WatcherDB\` no servidor
- [ ] Verificar que .py estao encriptados (abrir um — deve ser ilegivel)
- [ ] .env.example copiado (NAO copiar .env com secrets reais)

### INSTALACAO
- [ ] `deploy/install_production.ps1` executado como Administrador
- [ ] Dependencias Python instaladas sem erros
- [ ] Secrets gerados (.env criado com JWT e Fernet keys)
- [ ] Servico Windows instalado (WatcherDBWebServiceV32)

### BASE DE DADOS
- [ ] `deploy/setup_database.ps1` executado
- [ ] BD WatcherDB_Intelligence criada
- [ ] Tabelas criadas (WatcherDB_Users, WatcherDB_Auth_Log, etc.)
- [ ] User admin inserido

### CONFIGURACAO
- [ ] `.env` editado com servidor SQL correcto
- [ ] Conta de servico configurada (services.msc → Log On)
- [ ] Firewall porta 8449 aberta

### VALIDACAO
- [ ] Servico arrancou (services.msc → Running)
- [ ] `curl http://localhost:8449/health/web-service` → healthy
- [ ] Portal carrega: `http://SERVIDOR:8449/watcherdb`
- [ ] Login funciona (admin)
- [ ] Dashboard de KPIs carrega dados
- [ ] Control Panel acessivel
- [ ] Sessoes Activas mostra user online
- [ ] Alterar senha funciona
- [ ] Dark/Light mode funciona

### POS-DEPLOY
- [ ] Documentar IP/hostname do servidor
- [ ] Documentar conta de servico utilizada
- [ ] Comunicar URL aos utilizadores
- [ ] Verificar logs apos 24h: `C:\WatcherDB\services\web_service\logs\`
- [ ] Verificar que servico sobrevive a restart do servidor

### NOTAS
```
_____________________________________________
_____________________________________________
_____________________________________________
```
