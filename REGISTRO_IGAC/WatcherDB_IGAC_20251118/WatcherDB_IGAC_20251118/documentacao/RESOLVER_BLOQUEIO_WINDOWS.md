# 🔒 Resolver Bloqueio do Windows Security

## Problema

O Windows Security está bloqueando o `python.exe` com a mensagem:
> "Controlled folder access blocked python.exe from making changes"

Isso pode impedir que o `oracledb` funcione corretamente.

## Solução: Desabilitar ou Configurar Controlled Folder Access

### Opção 1: Desabilitar Temporariamente (Para Teste)

1. Abra **Windows Security** (procure por "Segurança do Windows" no menu Iniciar)
2. Vá em **Proteção contra vírus e ameaças**
3. Clique em **Gerenciar configurações** (em "Configurações de proteção contra vírus e ameaças")
4. Role até **Controlled folder access**
5. Clique em **Gerenciar Controlled folder access**
6. Desative o controle (toggle OFF)

⚠️ **Nota:** Isso reduz a segurança. Use apenas para teste.

### Opção 2: Adicionar Exceção (Recomendado)

1. Abra **Windows Security**
2. Vá em **Proteção contra vírus e ameaças**
3. Clique em **Gerenciar configurações**
4. Role até **Controlled folder access**
5. Clique em **Gerenciar Controlled folder access**
6. Clique em **Permitir um aplicativo através do Controlled folder access**
7. Clique em **Adicionar um aplicativo permitido**
8. Selecione **Aplicativos bloqueados recentemente**
9. Encontre `python.exe` e adicione
10. OU clique em **Navegar** e selecione:
    - `C:\Users\ue_e-snetto\AppData\Local\Programs\Python\Python312\python.exe`
    - Ou o caminho do Python que o servidor está usando

### Opção 3: Adicionar Pasta do Projeto como Exceção

1. Abra **Windows Security**
2. Vá em **Proteção contra vírus e ameaças**
3. Clique em **Gerenciar configurações**
4. Role até **Controlled folder access**
5. Clique em **Gerenciar Controlled folder access**
6. Clique em **Permitir um aplicativo através do Controlled folder access**
7. Clique em **Adicionar pasta protegida**
8. Adicione a pasta do projeto:
   ```
   C:\Users\usuario\Documents\PROJETO\Python\DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV
   ```

## Verificar se Funcionou

Após configurar, reinicie o servidor e teste:
```
http://127.0.0.1:8000/api/oracle-kpis/test-connection
```

## Importante

- ⚠️ Desabilitar o Controlled folder access reduz a segurança do sistema
- ✅ Adicionar exceções específicas é mais seguro
- 🔄 Reinicie o servidor após fazer as alterações

## Alternativa: Executar como Administrador

Se não quiser alterar as configurações do Windows, você pode executar o servidor como Administrador:

1. Clique com botão direito no PowerShell
2. Selecione **Executar como administrador**
3. Configure as variáveis de ambiente
4. Inicie o servidor

⚠️ **Nota:** Executar como administrador também reduz a segurança.

