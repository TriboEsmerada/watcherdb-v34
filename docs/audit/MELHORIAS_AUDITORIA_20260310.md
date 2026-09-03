# WatcherDB — Melhorias de Auditoria (10/03/2026)

## Backup
- `WATCHERDB_DEV_BACKUP_20260310_135703` criado antes de todas as alterações

## Resumo das Alterações

### 1. Sistema i18n — Multi-idioma (PT/EN/ES)

**Ficheiros:**
- `static/js/watcherdb_i18n.js` (NOVO) — dicionário de traduções ~130 chaves por idioma
- `templates/watcherdb_portal.html` — integração do i18n

**Como funciona:**
- Ficheiro `watcherdb_i18n.js` carregado no `<head>` antes do script principal
- Objecto `WATCHERDB_I18N` com 3 idiomas: `pt`, `en`, `es`
- Função `t(key)` retorna a tradução para o idioma actual, fallback para PT, fallback para a key
- Função `tCategory(name)` traduz nomes de categorias KPI
- Função `setLanguage(lang)` muda idioma e persiste em `localStorage('watcherdb_lang')`
- Função `applyLanguageToUI()` actualiza elementos visíveis sem reload completo

**Selector de idioma:**
- Dropdown `<select id="langSelector">` no header (zona direita), com opções PT/EN/ES
- Estilizado para combinar com o tema escuro
- Valor inicial carregado do localStorage

**Elementos traduzidos:**
- Categorias KPI (Disponibilidade, Performance, Espaço, Disco, Backup, Alta Disponibilidade)
- Toast labels (Instancias Offline, Blocked Sessions, etc.)
- Tab labels (Overview, Espaço em Disco, CPU, etc.)
- Títulos de página (17 createPageTitle calls)
- Títulos de gráficos (12 chart titles)
- Mensagens de loading (6 locais)

**Para adicionar novas traduções:**
1. Adicionar chave nos 3 idiomas em `WATCHERDB_I18N` no ficheiro `watcherdb_i18n.js`
2. No HTML, substituir texto hardcoded por `${t('chave')}`

**Para V5:**
- Copiar `static/js/watcherdb_i18n.js` para V5
- Adicionar `<script src="/static/js/watcherdb_i18n.js"></script>` no `<head>` do portal V5
- Adicionar o dropdown de idioma no header
- Chamar `applyLanguageToUI()` no init
- Substituir textos hardcoded por chamadas `t()` e `tCategory()`
- Verificar se V5 tem textos adicionais que precisam de tradução

---

### 2. Console.log → debugLog (~120 substituições)

**Ficheiro:** `templates/watcherdb_portal.html`

**O que foi feito:**
- ~120 ocorrências de `console.log()`, `console.warn()`, `console.error()` substituídas por `debugLog(msg, 'info'/'warn'/'error')`
- Objectos multi-argumento serializados com `JSON.stringify().substring()` para compatibilidade com debugLog (aceita string única)

**3 excepções mantidas (intencionalmente):**
1. Linha ~38: `console.log('Favicon carregado')` — executa antes do debugLog estar definido
2. Dentro da função `debugLog()` — é a implementação em si
3. Fallback `console.log('Performance optimization')` — dentro de `if (typeof debugLog !== 'function')`

**Para V5:**
- Fazer a mesma substituição no portal V5
- Padrão: usar sempre `debugLog(mensagem, nivel)` em vez de `console.log/warn/error`

---

### 3. sp_MSforeachdb → Cursor explícito

**Ficheiro:** `modules/monitoring/queries.py` (query `STATISTICS_OUTDATED`, ~linha 1350)

**Antes:**
```sql
EXEC sp_MSforeachdb @sql
```

**Depois:**
```sql
DECLARE @dbname NVARCHAR(128);
DECLARE db_cursor CURSOR LOCAL FAST_FORWARD FOR
    SELECT name FROM sys.databases
    WHERE database_id > 4
      AND name NOT IN ('master','tempdb','model','msdb')
      AND state_desc = 'ONLINE'
      AND DATABASEPROPERTYEX(name, 'Updateability') = 'READ_WRITE';

OPEN db_cursor;
FETCH NEXT FROM db_cursor INTO @dbname;
WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        -- executa com QUOTENAME(@dbname) e sp_executesql
    END TRY
    BEGIN CATCH
        -- log e continua para a próxima database
    END CATCH
    FETCH NEXT FROM db_cursor INTO @dbname;
END;
CLOSE db_cursor;
DEALLOCATE db_cursor;
```

**Vantagens:**
- Filtra apenas databases ONLINE e READ_WRITE
- Não salta databases silenciosamente
- TRY/CATCH por database — erro numa DB não afecta as outras
- QUOTENAME protege contra nomes especiais

**Para V5:**
- Copiar a query `STATISTICS_OUTDATED` actualizada do `queries.py`

---

### 4. NOLOCK adicionado a sys.indexes

**Ficheiro:** `modules/monitoring/queries.py` (~linha 1389)

**Antes:**
```sql
FROM sys.indexes i WHERE i.object_id = s.object_id
```

**Depois:**
```sql
FROM sys.indexes i WITH(NOLOCK) WHERE i.object_id = s.object_id
```

**Nota:** DMVs (sys.dm_*) não precisam de NOLOCK — apenas catálogos de sistema (sys.indexes, sys.objects, etc.)

**Para V5:**
- Verificar se queries em V5 usam NOLOCK consistentemente em catálogos de sistema

---

### 5. Error handling padronizado

**Ficheiros:**
- `api/routers/oracle_kpis.py` — 17 `except:` vazios corrigidos com `logger.debug()` ou `logger.warning()`
- `api/routers/overview_dashboard.py` — 2 `except Exception: pass` substituídos por `logger.warning(f"Error during cleanup: {e}")`

**Padrão adoptado:**
- Loops de iteração (views, instâncias): `except Exception as e: logger.debug(f"...")`
- Fallbacks esperados (view A → view B): `except Exception as e: logger.debug(f"Fallback...")`
- Cleanup/finally: `except Exception as e: logger.warning(f"Error during cleanup: {e}")`
- Erros inesperados: `except Exception as e: logger.error(f"..."); raise HTTPException(500, ...)`

**Para V5:**
- Aplicar o mesmo padrão de logging nos routers equivalentes
- Eliminar todos os `except: pass` e `except Exception: pass`

---

### 6. Blocked Sessions — Melhorias anteriores (mesma sessão)

**Ficheiros:**
- `modules/monitoring/queries.py` — `BLOCKING_HIERARCHY` query:
  - Adicionado `WaitTimeSec` (conversão ms → segundos)
  - Filtro `wait_time >= 45000` (ignora locks < 45s)
  - Ordem por `wait_time DESC`
- `templates/watcherdb_portal.html` — Modal de blocked sessions:
  - Badge HIGH (laranja, 45s-2min) vs CRITICAL (vermelho, ≥2min)
  - Toast onclick abre modal em vez de navegar para KPIs

---

### 7. KPI Documentation Modal — Actualização de conteúdo

**Ficheiro:** `templates/watcherdb_portal.html` (objecto `KPI_DOCUMENTATION`, ~linha 30835)

**O que foi feito:**
- **Blocked Sessions** — documentação completamente actualizada:
  - Descrição agora menciona o threshold de 45 segundos
  - howItWorks: adicionados 3 novos itens (filtro 45s, badge severity, toast→modal)
  - Thresholds: adicionados 4 níveis (CRITICAL ≥2min, HIGH 45s-2min, IGNORED <45s, OK)
- **Toast→Modal** — adicionada nota em 6 KPIs que possuem toast de alerta:
  - DB Not Availability, Instances Off, Blocked Sessions
  - Transaction Logs Critical, FileGroups Critical, Disk File System Critical
  - AlwaysOn Unhealthy
  - Cada um agora documenta que o "Toast de alerta abre directamente o modal"

**Para V5:**
- Copiar o objecto `KPI_DOCUMENTATION` actualizado para o portal V5
- Verificar se V5 tem KPIs adicionais que precisam de documentação

---

## Ficheiros Alterados (Resumo)

| Ficheiro | Tipo de Alteração |
|---|---|
| `static/js/watcherdb_i18n.js` | NOVO — sistema i18n |
| `templates/watcherdb_portal.html` | i18n, console→debugLog, toast modal, blocked sessions UI |
| `modules/monitoring/queries.py` | cursor, NOLOCK, WaitTimeSec, threshold 45s |
| `api/routers/oracle_kpis.py` | error handling (17 excepts) |
| `api/routers/overview_dashboard.py` | error handling (2 excepts) |
| `api/routers/intelligence_kpis.py` | CPU offline filter (sessão anterior) |

## Replicação

Todas as alterações foram replicadas para:
- WATCHERDB_DEV_V4
- WATCHERDB_V4

**V5 NÃO foi alterado** — este documento serve como guia para implementação manual no V5.
