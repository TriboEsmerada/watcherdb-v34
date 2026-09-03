# Runbook — Adicionar / remover servidor do monitoramento

> Desde a wave inventário (19-20/08/2026), existe **um único ficheiro que manda**:
> `WATCHERDB INTELLIGENCE V1/config/servers.json` (o canónico). Tudo o resto —
> BD (`metadata.monitored_server`), collectors, `INST_ENVS`, portal — flui
> automaticamente a partir dele. Arquitectura completa:
> `knowledge_base/architecture/cross_cutting/inventario_servers_json_fonte_unica.md`.

## Adicionar uma instância

### 1. Preparar o servidor alvo (uma vez por servidor)

Criar o login `sql_monitoring` (SQL auth, só leitura) + grants de monitoria.
Usar os canónicos existentes no V1 — **não** criar scripts novos:

- `V1/scripts/apply_grants_all_servers.py` (ou o bloco de GRANTs equivalente no SSMS)
- `V1/database/SETUP_ENVIRONMENT_TABLES.sql` se aplicável

Identidade: os GRANTs correm com a identidade do DBA no SSMS; a coleta usa
sempre e apenas `sql_monitoring` (Regra de Ouro #2 — nunca Windows auth).

### 2. Acrescentar a entrada ao canónico

Editar `WATCHERDB INTELLIGENCE V1/config/servers.json`:

```json
{
  "id": "NOVOSERVER_I01",
  "host": "NOVOSERVER",
  "instance": "I01",
  "port": 1433,
  "description": "o que o servidor faz",
  "environment": "production",
  "priority": 1,
  "enabled": true,
  "use_windows_auth": false,
  "username": "sql_monitoring",
  "password": "encrypted:...."
}
```

Notas:
- `id` = `HOST_INSTANCIA` (underscore, max 64 chars, único; sem instância = só o host).
- `environment`: aceita aliases (PRD/production, QA/QLT, TST/test, DEV) — ver
  `ENV_ALIASES` no `inventory_provider.py`.
- `password`: cifrada com o EncryptionManager do V1 (Fernet). One-liner (correr
  a partir da pasta V1; pede a password interactivamente, nunca fica no histórico):

  ```powershell
  cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1"
  python -c "from watcherdb_intelligence.collectors import EncryptionManager; import getpass; print('encrypted:' + EncryptionManager().encrypt(getpass.getpass('password: ')))"
  ```
- Porta de instância nomeada: não interessa acertar — o collector aprende a porta
  real via SQL Browser e re-aprende sozinho se ela mudar (auto-heal; caso PRD214).
- `databases[]`: **não preencher** — o discovery diário preenche sozinho. E é
  catálogo informativo, nunca scope de coleta.
- Uma entrada inválida é rejeitada com WARN e **não trava** o resto da frota;
  os motivos ficam no log do collector (REJECT codes).

### 3. Esperar ≤10 minutos (não fazer mais nada)

- A sync detecta o hash novo → INSERT em `metadata.monitored_server` + audit.
- Os collectors incluem o servidor no ciclo seguinte (membership vem do provider).
- O discovery diário preenche `databases[]`.
- `KPI_MSSQL_INST_ENVS` / `server_config` são projectados automaticamente.

### 4. (Opcional) Sidebar do portal V3.3

O servidor já é monitorizado; para aparecer também na **sidebar** do V3.3 é
preciso a credencial no mirror local do V3.3 (`WATCHERDB_V3.3/config/servers.json`,
cifra própria do V3.3 — ficheiro **gitignored**, nunca vai ao git):

- Acrescentar entrada equivalente com a password re-cifrada com a master key do
  V3.3 (`services.secrets` / Fernet) — padrão do script `provision_oatxp01_v33.py`
  (fases: ler decifrado do V1 → re-cifrar V3.3 → append com backup).
- `Restart-Service WatcherDBWebServiceV33`.

### 5. Verificar

- Portal: Resumo Executivo passa a N+1 instâncias; Disponibilidade Online inclui o novo.
- BD: `SELECT * FROM metadata.server_sync_audit WHERE entity_key='NOVOSERVER_I01' ORDER BY logged_at DESC;` → linha INSERT.
- Se não aparecer: ver WARNs de validação no log do collector (entrada rejeitada?).

## Remover / pausar uma instância

### Pausa (reversível — usar primeiro)

`"enabled": false` na entrada do canónico. Em ≤10 min a coleta pára; a BD fica
com `enabled=0` e audit `changed_cols='enabled'`. Reverter = voltar a `true`.

### Remoção definitiva

Apagar a entrada do canónico. Na run seguinte, a **ausência** marca
`is_active=0` + `removed_at` (desactivação é sempre por ausência, nunca por
idade; a guarda de frota de 20 % impede desactivações em massa acidentais —
se apagares muitos de uma vez, a run falha por segurança e nada muda).

- O histórico KPI **fica** (nada é apagado das tabelas de dados).
- O reconcile limpa o `INST_ENVS` com guarda de 30 dias.
- Se estava na sidebar V3.3: remover também do `WATCHERDB_V3.3/config/servers.json` + restart do web service.

## O que NUNCA se faz

- Tocar na BD à mão (INSERT/UPDATE em `monitored_server`, `INST_ENVS`, `server_config`).
- Reactivar o `sql_servers.json` (ARQUIVADO — nenhum código o lê).
- Listas de servidores em env vars, config de collectors ou código.
- Password em claro em qualquer ficheiro, ou credenciais na BD.

## Diagnóstico rápido

| Pergunta | Onde |
|---|---|
| Porque desapareceu o servidor X? | `SELECT * FROM metadata.server_sync_audit WHERE entity_key='X' ORDER BY logged_at DESC` |
| A sync está a correr? | `SELECT TOP 3 * FROM metadata.server_sync_run ORDER BY run_id DESC` (SKIP por hash é normal; full-run diária às 03h) |
| Entrada foi rejeitada? | WARNs `[inventory]` no log do collector V1 |
| Está na sidebar mas sem dados? | Suporte parcial por versão (SQL < 2012) ou creds locais em falta |
