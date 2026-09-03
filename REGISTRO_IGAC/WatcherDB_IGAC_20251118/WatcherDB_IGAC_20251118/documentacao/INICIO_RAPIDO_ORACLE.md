# 🚀 Início Rápido - Configurar Oracle

## 🚀 Método Mais Fácil: Script Automatizado

Execute um dos scripts que criamos:

**PowerShell:**
```powershell
.\iniciar_servidor_oracle.ps1
```

**CMD (Windows):**
```cmd
iniciar_servidor_oracle.bat
```

O script vai:
- ✅ Solicitar suas credenciais Oracle (se não estiverem configuradas)
- ✅ Configurar as variáveis de ambiente automaticamente
- ✅ Verificar se `oracledb` está instalado
- ✅ Iniciar o servidor com tudo configurado

## Passo a Passo Manual

### 1️⃣ Configure as Variáveis de Ambiente

**No PowerShell, ANTES de iniciar o servidor:**

```powershell
$env:ORACLE_USER='seu_usuario_oracle'
$env:ORACLE_PASSWORD='sua_senha_oracle'
```

### 2️⃣ Verifique se Estão Configuradas

```powershell
echo $env:ORACLE_USER
echo $env:ORACLE_PASSWORD
```

Se aparecerem os valores, está OK! ✅

### 3️⃣ Inicie o Servidor NO MESMO TERMINAL

**IMPORTANTE:** O servidor DEVE ser iniciado no mesmo terminal onde você configurou as variáveis!

```powershell
python watcherdb_main.py
# ou
uvicorn watcherdb_main:app --reload
```

### 4️⃣ Teste a Conexão

Abra no navegador:
```
http://127.0.0.1:8000/api/oracle-kpis/test-connection
```

Você deve ver `"success": true` ✅

## ⚠️ Problemas Comuns

### ❌ "Credenciais não configuradas" mesmo após configurar

**Causa:** Servidor foi iniciado antes de configurar as variáveis, ou em terminal diferente.

**Solução:**
1. Pare o servidor (Ctrl+C)
2. Configure as variáveis NOVAMENTE no mesmo terminal
3. Inicie o servidor NOVAMENTE no mesmo terminal

### ❌ Variáveis desaparecem ao fechar o terminal

**Causa:** Variáveis foram configuradas apenas na sessão atual.

**Solução:** Configure permanentemente:
```powershell
[System.Environment]::SetEnvironmentVariable('ORACLE_USER', 'seu_usuario', 'User')
[System.Environment]::SetEnvironmentVariable('ORACLE_PASSWORD', 'sua_senha', 'User')
```

Depois feche e reabra o terminal.

## ✅ Checklist

- [ ] `oracledb` instalado no Python correto (verificado ✅)
- [ ] Variáveis `ORACLE_USER` e `ORACLE_PASSWORD` configuradas
- [ ] Servidor iniciado no MESMO terminal onde configurou as variáveis
- [ ] Teste de conexão retorna `"success": true`

## 📝 Exemplo Completo

```powershell
# 1. Configure
$env:ORACLE_USER='meu_usuario'
$env:ORACLE_PASSWORD='minha_senha'

# 2. Verifique
echo "Usuario: $env:ORACLE_USER"
echo "Senha configurada: $($env:ORACLE_PASSWORD -ne $null)"

# 3. Inicie o servidor (no mesmo terminal!)
python watcherdb_main.py
```

