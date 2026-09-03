# Nova Aba: Encrypted (TDE)

## Data: 2025-01-20
## Versão: WatcherDB v1.4.8.6

---

## ✅ O Que Foi Feito

Criada uma **nova aba dedicada "Encrypted"** para testar isoladamente a funcionalidade de TDE (Transparent Data Encryption).

### Objetivo:

Verificar se o problema de timeout no Overview também ocorre em uma aba isolada, ou se é específico do Overview (que faz 8 requisições simultâneas).

---

## 🎨 Interface da Nova Aba

### Localização:
- Botão no menu principal, entre "Security" e "Space"
- Ícone: 🔒 (lock)
- Nome: "Encrypted"

### Conteúdo Exibido:

1. **Status TDE Card**:
   - Indicador visual (verde = Ativo, cinza = Inativo)
   - Status: Ativo ou Inativo
   - Se ativo:
     - 📜 Número de certificados
     - 🔐 Número de databases encriptadas

2. **Certificados TDE** (se existirem):
   - Nome do certificado
   - Tipo de criptografia
   - Data de expiração
   - Data de criação
   - Emissor

3. **Databases Encriptadas** (se existirem):
   - Lista de databases com TDE ativo
   - Certificado usado
   - Estado da criptografia

4. **Aviso** (se TDE não configurado):
   - Mensagem informando que TDE não está ativo
   - Orientação básica

---

## 🔧 Implementação Técnica

### 1. Botão na Navegação

**Arquivo**: `templates/watcherdb_portal.html` (Linha ~1896)

```html
<button class="nav-btn" onclick="showTab('encrypted')" title="TDE Encryption">
    <i class="fas fa-lock"></i> Encrypted
</button>
```

### 2. Handler da Aba

**Arquivo**: `templates/watcherdb_portal.html` (Linha ~2777)

```javascript
} else if (tab.tabType === 'encrypted') {
    await loadEncryptedForTab(tabId);
}
```

### 3. Função `loadEncryptedForTab()`

**Arquivo**: `templates/watcherdb_portal.html` (Linha ~4049)

Carrega a aba e chama a função principal `loadTDEEncryption()`.

### 4. Função Principal `loadTDEEncryption()`

**Arquivo**: `templates/watcherdb_portal.html` (Linha ~5632)

**Características**:
- ✅ Converte `serverId` de backslash para underscore antes das chamadas
- ✅ Usa timeout de **120 segundos** (2 minutos)
- ✅ Faz **2 requisições** apenas (não 8 como Overview):
  - `/api/queries/tde-status/{server_id}`
  - `/api/queries/tde-database-status/{server_id}`
- ✅ Logs detalhados no console para debug
- ✅ Tratamento de erro com mensagem clara para timeout

### 5. Label da Aba

**Arquivo**: `templates/watcherdb_portal.html` (Linha ~2564)

```javascript
'encrypted': 'Encrypted',
```

---

## 📊 Logs de Debug

Ao abrir a aba "Encrypted", você verá no console:

```
🔐 Carregando TDE Encryption Analysis...
🔑 Server ID Original: SQLHDSPRD214\I01
🔑 Server ID Formatado: SQLHDSPRD214_I01
📡 Chamando APIs TDE...
   - /api/queries/tde-status/SQLHDSPRD214_I01
   - /api/queries/tde-database-status/SQLHDSPRD214_I01
✅ Dados TDE recebidos:
   - tde_status length: 1
   - tde_database_status length: 14
🔐 Análise TDE:
   - hasTdeCertificate: TDECert_TAP
   - hasEncryptedDatabases: true
   - encryptedDatabases count: 12
   - tdeActive (FINAL): true
```

---

## 🧪 Como Testar

1. **CTRL+SHIFT+R** no navegador (recarregar JavaScript)
2. Selecione o servidor `SQLHDSPRD214\I01`
3. Clique no botão **"Encrypted"** (ícone 🔒)
4. **Aguarde até 2 minutos** (se houver lentidão)
5. Observe o console (F12) para ver os logs

---

## 🎯 O Que Isso Vai Nos Dizer

### ✅ Se funcionar na aba "Encrypted":

**Significa**: O problema é específico do **Overview**, que faz muitas requisições simultâneas (8).

**Solução**:
- Reduzir número de requisições simultâneas no Overview
- Adicionar requisições sequenciais ao invés de paralelas
- Aumentar pool de conexões no backend

### ❌ Se também der timeout na aba "Encrypted":

**Significa**: O problema é **genérico** - servidor SQL Server muito lento.

**Possíveis causas**:
- Rede lenta entre backend e SQL Server
- SQL Server sobrecarregado
- Queries TDE muito pesadas
- Firewall ou proxy causando latência

**Solução**:
- Investigar performance das queries no SQL Server
- Verificar latência de rede
- Adicionar cache mais agressivo no backend

---

## 📝 Vantagens da Nova Aba

1. **Isolamento**: Testa TDE isoladamente, sem interferência de outras requisições
2. **Timeout Maior**: 120s (vs 30s antigo do Overview)
3. **Logs Detalhados**: Mostra exatamente o que está acontecendo
4. **Visual Claro**: Interface dedicada apenas para TDE
5. **Diagnóstico**: Ajuda a identificar se problema é no Overview ou geral

---

## 🚀 Próximos Passos

Após testar a nova aba:

### Cenário 1: Funciona na aba "Encrypted"

1. Otimizar Overview para reduzir requisições simultâneas
2. Adicionar loading progressivo (carregar dados em etapas)
3. Considerar cache mais agressivo

### Cenário 2: Também dá timeout

1. Investigar performance no SQL Server
2. Verificar logs do backend para ver tempo de query
3. Considerar adicionar índices nas tabelas de certificados

---

**Data**: 2025-01-20
**Autor**: Claude Code (Anthropic)
**Status**: ✅ Aba Criada - Aguardando Teste
**Versão**: v1.4.8.6
