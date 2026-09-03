# 🚀 Watcher DB - Guia de Inicialização

## 📋 Visão Geral

O Watcher DB agora suporta **duas formas de configuração**:

1. **Inicialização via Excel** (recomendado na primeira vez)
   - Lê o Excel uma vez e popula os JSONs
   - Mais rápido depois (não precisa mais ler o Excel)

2. **Configuração Manual via Templates**
   - Use os templates JSON para preencher manualmente
   - Útil quando não há Excel disponível

---

## 🎯 Opção 1: Inicialização via Excel (Recomendado)

### Passo 1: Configurar o caminho do Excel

Edite `config/alwayson_inventory.json` e configure o caminho do Excel:

```json
{
  "excel_path": "C:\\Server_Inventory\\TAP_SQL_Server_Inventory.xlsx",
  "sheet_name": "Servers",
  ...
}
```

### Passo 2: Executar o script de inicialização

```powershell
python scripts/initialize_configs.py
```

### O que o script faz:

1. ✅ Lê o Excel uma vez
2. ✅ Popula `config/alwayson_inventory.json` com a lista de servidores Always On
3. ✅ Popula `config/sql_servers.json` com todos os servidores
4. ✅ Cria backup do `sql_servers.json` existente (se houver)

### Resultado:

- ✅ `alwayson_inventory.json` terá o campo `ag_servers` preenchido
- ✅ `sql_servers.json` terá todos os servidores do Excel
- ✅ O sistema **não precisará mais ler o Excel** (muito mais rápido!)

---

## 📝 Opção 2: Configuração Manual via Templates

### Passo 1: Copiar os templates

```powershell
copy config\sql_servers.json.template config\sql_servers.json
copy config\alwayson_inventory.json.template config\alwayson_inventory.json
```

### Passo 2: Preencher `sql_servers.json`

Edite `config/sql_servers.json` e adicione seus servidores:

```json
{
  "metadata": {
    "generated_at": "2025-11-10T10:00:00",
    "source_file": "manual",
    "total_servers": 2,
    "version": "1.0"
  },
  "servers": [
    {
      "id": "SQLHDSPRD214_I01",
      "host": "SQLHDSPRD214",
      "instance": "I01",
      "port": 1433,
      "description": "Servidor de produção - Always On",
      "environment": "production",
      "priority": 1
    },
    {
      "id": "SQLDEV01",
      "host": "SQLDEV01",
      "instance": "",
      "port": 1433,
      "description": "Servidor de desenvolvimento",
      "environment": "development",
      "priority": 3
    }
  ]
}
```

**Campos obrigatórios:**
- `id`: Identificador único (formato: `HOST_INSTANCE` ou `HOST`)
- `host`: Nome do servidor (sem instância)
- `instance`: Nome da instância (ex: `I01`, ou vazio para DEFAULT)
- `port`: Porta do SQL Server (padrão: 1433)

**Campos opcionais:**
- `description`: Descrição do servidor
- `environment`: Ambiente (`production`, `development`, `quality`)
- `priority`: Prioridade (1 = alta, 2 = média, 3 = baixa)

### Passo 3: Preencher `alwayson_inventory.json`

Edite `config/alwayson_inventory.json` e adicione os servidores Always On:

```json
{
  "excel_path": "C:\\\\Server_Inventory\\\\TAP_SQL_Server_Inventory.xlsx",
  "sheet_name": "Servers",
  "columns": {
    "server": "ServerName",
    "instance": "Instance",
    "server_instance": "ServerInstance",
    "is_always_on": "IsAlwaysOn",
    "ag_name": "AGName",
    "listener": "AGListener"
  },
  "ag_servers": [
    {
      "server": "SQLHDSPRD214",
      "instance": "I01",
      "server_instance": "SQLHDSPRD214\\I01",
      "ag_name": "SQLAGSPRD213",
      "listener": "SQLAGSPRD213\\I01"
    }
  ]
}
```

**Importante:**
- O campo `server_instance` deve estar no formato: `"SERVER\\INSTANCE"` (com barra invertida dupla)
- O campo `ag_name` deve corresponder ao nome do Availability Group

---

## 🔄 Atualizar Configurações

### Atualizar do Excel novamente:

```powershell
python scripts/initialize_configs.py
```

### Editar manualmente:

1. Edite diretamente os arquivos JSON
2. Reinicie o Watcher DB para carregar as mudanças

---

## ⚡ Performance

### Antes (lendo Excel toda vez):
- ⏱️ ~2-3 segundos para carregar Always On
- 📊 Lê Excel a cada inicialização

### Depois (usando JSON):
- ⚡ ~0.01 segundos para carregar Always On
- 📊 Lê apenas JSON (muito mais rápido!)

---

## 🐛 Troubleshooting

### Erro: "Excel não encontrado"

**Solução:** Verifique o caminho em `alwayson_inventory.json`:
- Use `\\` (dupla barra invertida) no JSON
- Exemplo: `"C:\\\\Server_Inventory\\\\arquivo.xlsx"`

### Erro: "ag_servers não encontrado no JSON"

**Solução:** Execute o script de inicialização:
```powershell
python scripts/initialize_configs.py
```

### Servidor não aparece na lista

**Solução:** 
1. Verifique se está no `sql_servers.json`
2. Verifique se o formato do `id` está correto (`HOST_INSTANCE`)
3. Reinicie o Watcher DB

---

## 📚 Arquivos Relacionados

- `config/sql_servers.json.template` - Template para servidores SQL
- `config/alwayson_inventory.json.template` - Template para Always On
- `scripts/initialize_configs.py` - Script de inicialização
- `config/sql_servers.json` - Configuração de servidores (gerado)
- `config/alwayson_inventory.json` - Configuração Always On (gerado)

---

## 💡 Dicas

1. **Backup automático:** O script cria backup do `sql_servers.json` antes de sobrescrever
2. **Validação:** O script valida os dados antes de salvar
3. **Logs:** Verifique os logs para ver quantos servidores foram carregados
4. **Performance:** Use JSON sempre que possível (muito mais rápido que Excel)

---

## ✅ Checklist de Inicialização

- [ ] Configurar caminho do Excel em `alwayson_inventory.json`
- [ ] Executar `python scripts/initialize_configs.py`
- [ ] Verificar se `ag_servers` foi populado em `alwayson_inventory.json`
- [ ] Verificar se `servers` foi populado em `sql_servers.json`
- [ ] Reiniciar Watcher DB
- [ ] Testar acesso aos servidores

---

**Pronto!** Agora o Watcher DB está configurado e otimizado! 🚀

