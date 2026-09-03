# WatcherDB V3.3 Standard Edition — Data Protection Impact Assessment (DPIA)
## Modulo: Database Discovery

### 1. Descricao do Tratamento

| Campo | Valor |
|-------|-------|
| **Responsavel** | Equipa DBA (cliente) |
| **Encarregado** | DPO do cliente (se aplicavel) |
| **Finalidade** | Monitoring e diagnostico de SQL Server |
| **Base Legal** | Interesse legitimo (Art. 6(1)(f) RGPD) |
| **Dados tratados** | Metadata de base de dados (nomes de tabelas, colunas, filegroups) |
| **Titulares afectados** | Nenhum directamente — metadata tecnica, nao dados pessoais |

### 2. Dados Recolhidos pelo Discovery

| Tipo de Metadata | Exemplo | Contem dados pessoais? |
|-----------------|---------|:----------------------:|
| Nome de database | `DW_TAP`, `COMERCIAL` | Nao |
| Nome de tabela | `dbo.Orders`, `dbo.Customers` | **Potencialmente** — o nome pode revelar existencia de dados pessoais |
| Nome de coluna | `SSN`, `Credit_Card_Number` | **Sim** — revela categorias de dados pessoais |
| Tamanho de ficheiro | `500 GB` | Nao |
| Recovery model | `FULL` | Nao |
| Estado da database | `ONLINE` | Nao |

### 3. Avaliacao de Risco

| Risco | Probabilidade | Impacto | Nivel |
|-------|:------------:|:-------:|:-----:|
| Nomes de tabelas/colunas revelam categorias de dados sensíveis | Media | Baixo | **MEDIO** |
| Metadata armazenada no Intelligence DB sem encriptacao | Baixa | Medio | **MEDIO** |
| Acesso nao autorizado ao WatcherDB expoe metadata | Baixa | Medio | **MEDIO** |
| Metadata usada para inferir estrutura de dados pessoais | Baixa | Baixo | **BAIXO** |

### 4. Medidas de Mitigacao Implementadas

| Medida | Estado | Detalhe |
|--------|:------:|---------|
| Autenticacao obrigatoria (JWT + bcrypt) | ✅ | Sem acesso anonimo |
| RBAC (4 roles: admin, analyst, operator, viewer) | ✅ | Viewer nao ve metadata |
| Rate limiting (slowapi global) | ✅ | Proteccao contra brute force |
| Token blacklist persistente | ✅ | Logout real |
| Encriptacao de passwords em servers.json (Fernet) | ✅ | Credenciais SQL Server protegidas |
| CSP + HSTS + HttpOnly cookies | ✅ | Proteccao frontend |
| Audit log de autenticacao | ✅ | Quem acedeu e quando |
| Codigo protegido (PyArmor Pro) | ✅ | Logica de negocio encriptada |
| Self-hosted (zero cloud) | ✅ | Dados nunca saem do perimetro do cliente |

### 5. Medidas Adicionais Recomendadas

| Medida | Prioridade | Estado |
|--------|:----------:|:------:|
| Encriptar Intelligence DB com TDE | Alta | A implementar pelo cliente |
| Restringir Discovery a databases especificas (whitelist) | Media | Feature futura |
| Ofuscar nomes de tabelas/colunas no cache | Baixa | Nao necessario se DB encriptada |
| Periodo de retencao para metadata no cache | Baixa | Cache TTL ja implementado (30s-24h) |

### 6. Conclusao

O WatcherDB V3.3 Standard Edition trata **metadata tecnica**, nao dados pessoais directamente. O risco principal e que nomes de tabelas/colunas podem **revelar categorias** de dados pessoais (ex: tabela `Patients` implica dados de saude).

**Recomendacao:** O DPIA deve ser completado pelo **DPO do cliente**, nao pelo fornecedor, uma vez que:
- O WatcherDB e uma ferramenta — quem decide que bases monitorizar e o cliente
- A base legal (interesse legitimo) aplica-se ao tratamento do cliente, nao do fornecedor
- O fornecedor actua como **sub-processador** nos termos do RGPD

**Documentos complementares necessarios:**
- [ ] Contrato de sub-processamento (Art. 28 RGPD) entre fornecedor e cliente
- [ ] Clausula de confidencialidade no contrato de licenca
- [ ] Politica de retencao de dados para o Intelligence DB
