# WatcherDB V3.2 — Production Secrets Management

## Required Secrets

| Secret | Env Var | Purpose |
|--------|---------|---------|
| JWT signing key | `JWT_SECRET_KEY` | Token signing. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| Fernet key | `WATCHERDB_ENCRYPTION_KEY` | Server passwords encryption. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| SMTP password | `SMTP_PASSWORD` | Email notifications |
| SQL Server creds | `INTELLIGENCE_SQL_PASSWORD` | Only if using SQL auth (not Windows auth) |
| LLM API key | `ANTHROPIC_API_KEY` | Only if LLM_ENABLED=true |

## Configuration Priority (pydantic-settings)

1. Defaults in `watcherdb/core/settings.py` (lowest)
2. Values from `.env` file
3. **System / process environment variables** (highest — use this in production)

## Deployment Options

### Option A: System Environment Variables (Windows)
```powershell
# Set via System Properties > Environment Variables
[Environment]::SetEnvironmentVariable("JWT_SECRET_KEY", "your-64-char-hex-key", "Machine")
[Environment]::SetEnvironmentVariable("WATCHERDB_ENCRYPTION_KEY", "your-fernet-key", "Machine")
```

### Option B: Docker / docker-compose
```yaml
# docker-compose.yml
services:
  watcherdb:
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}  # from host env or .env
      - WATCHERDB_ENCRYPTION_KEY=${WATCHERDB_ENCRYPTION_KEY}
```

### Option C: Azure Key Vault
```python
# Future integration — add to watcherdb/core/settings.py:
# from azure.identity import DefaultAzureCredential
# from azure.keyvault.secrets import SecretClient
```

### Option D: HashiCorp Vault
```bash
vault kv put secret/watcherdb jwt_secret_key=... encryption_key=...
```

## Security Checklist
- [ ] Delete `.env` file on production servers
- [ ] Set all secrets as system environment variables
- [ ] Rotate JWT key every 90 days
- [ ] Rotate Fernet key (re-encrypt server passwords after rotation)
- [ ] Use separate secrets per environment (dev/staging/prod)
- [ ] Enable audit logging for secret access
