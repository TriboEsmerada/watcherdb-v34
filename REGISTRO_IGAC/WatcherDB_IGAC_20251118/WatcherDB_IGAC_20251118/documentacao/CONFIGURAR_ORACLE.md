# Como Configurar Credenciais Oracle

## ⚠️ IMPORTANTE: Verificar Ambiente Python

**O servidor pode estar usando um Python diferente do que você usa no terminal!**

Para verificar qual Python o servidor está usando, acesse:
```
http://127.0.0.1:8000/api/oracle-kpis/test-connection
```

O campo `python_info.executable` mostra qual Python está sendo usado.

### Se o Python for diferente:

Instale `oracledb` no Python que o servidor está usando:
```powershell
# Substitua pelo caminho do Python que o servidor usa
C:\caminho\para\python.exe -m pip install oracledb
```

## Problema Identificado

O `oracledb` precisa estar instalado no **mesmo ambiente Python** que o servidor está usando. As variáveis de ambiente `ORACLE_USER` e `ORACLE_PASSWORD` também precisam estar configuradas.

## Solução: Configurar Variáveis de Ambiente

### 🚀 Método Rápido (Script Automatizado)

Execute o script PowerShell que criamos:
```powershell
.\configurar_oracle_credenciais.ps1
```

O script vai:
- Solicitar seu usuário e senha Oracle
- Oferecer opção de configurar temporariamente ou permanentemente
- Dar instruções claras sobre próximos passos

### Opção 1: Configurar na Sessão Atual (Temporário)

**Windows PowerShell:**
```powershell
$env:ORACLE_USER='seu_usuario_oracle'
$env:ORACLE_PASSWORD='sua_senha_oracle'
```

**Windows CMD:**
```cmd
set ORACLE_USER=seu_usuario_oracle
set ORACLE_PASSWORD=sua_senha_oracle
```

⚠️ **Nota:** Essas variáveis só funcionam na sessão atual. Quando fechar o terminal, elas serão perdidas.

### Opção 2: Configurar Permanentemente (Recomendado)

#### Windows PowerShell (Permanente para Usuário)

1. Abra o PowerShell como Administrador
2. Execute:
```powershell
[System.Environment]::SetEnvironmentVariable('ORACLE_USER', 'seu_usuario_oracle', 'User')
[System.Environment]::SetEnvironmentVariable('ORACLE_PASSWORD', 'sua_senha_oracle', 'User')
```

3. **Reinicie o terminal** para as variáveis serem carregadas

#### Windows (Interface Gráfica)

1. Pressione `Win + R` e digite `sysdm.cpl`
2. Vá na aba "Avançado"
3. Clique em "Variáveis de Ambiente"
4. Em "Variáveis do usuário", clique em "Novo"
5. Adicione:
   - Nome: `ORACLE_USER`
   - Valor: `seu_usuario_oracle`
6. Repita para `ORACLE_PASSWORD`
7. Clique em "OK" em todas as janelas
8. **Reinicie o terminal** onde o servidor está rodando

### Opção 3: Criar Arquivo .env (Alternativa)

Crie um arquivo `.env` na raiz do projeto:

```env
ORACLE_USER=seu_usuario_oracle
ORACLE_PASSWORD=sua_senha_oracle
ORACLE_HOST=oradb_ocrl01.xpto.pt
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=SYSAPP.XPTO.PT
```

⚠️ **Nota:** O código atual não carrega automaticamente arquivos `.env`. Você precisaria usar uma biblioteca como `python-dotenv` ou configurar manualmente.

## Verificar se Funcionou

Após configurar, execute novamente:
```bash
python check_oracle_env.py
```

Você deve ver:
```
ORACLE_USER: [OK] Configurado
ORACLE_PASSWORD: [OK] Configurado
```

## Testar Conexão

Após configurar e reiniciar o servidor, teste a conexão:
```
http://127.0.0.1:8000/api/oracle-kpis/test-connection
```

## Importante

- ⚠️ **Nunca commite credenciais no Git!**
- 🔒 Mantenha as senhas seguras
- 🔄 Reinicie o servidor após configurar as variáveis
- ✅ Use a Opção 2 (permanente) para não precisar configurar toda vez

