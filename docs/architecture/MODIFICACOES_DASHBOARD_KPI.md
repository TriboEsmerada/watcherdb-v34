# Modificações no Dashboard KPI

## Resumo das Alterações

Este documento descreve as modificações realizadas no dashboard KPI (`watcherdb_portal.html`) para suportar os novos modos de coleta de KPIs.

## Funcionalidades Implementadas

### 1. ✅ Badges Visuais nos Cards

- **Localização**: Canto superior direito de cada card de KPI
- **Badge "⚡ FAST"** (verde): Exibido quando `is_fast = true`
- **Badge "📊 COMPLETO"** (amarelo/laranja): Exibido quando `is_fast = false`
- **Fonte de dados**: Campo `is_fast` da API `/api/v1/kpis/metadata`

### 2. ✅ Filtro por Modo de Coleta

- **Localização**: Topo da seção de KPIs, abaixo do indicador de última coleta
- **Opções**:
  - "Todos" - Mostra todos os KPIs
  - "⚡ Fast (5 min)" - Mostra apenas KPIs leves (coletados a cada 5 minutos)
  - "📊 Completo (15 min)" - Mostra apenas KPIs completos (coletados a cada 15 minutos)
- **Persistência**: Estado do filtro salvo em `localStorage` (chave: `kpiModeFilter`)
- **Endpoint usado**: `/api/v1/kpis/by-mode/{mode}` para obter lista de KPIs por modo

### 3. ✅ Tempo Médio de Coleta

- **Localização**: Abaixo do valor principal do KPI
- **Formato**: "Tempo médio: X ms" (formatado automaticamente: ms, s, min)
- **Fonte de dados**: Campo `avg_duration_ms` da API
- **Estilo**: Texto pequeno, cor cinza claro (#94a3b8)

### 4. ✅ Indicador de Última Coleta

- **Localização**: Topo do dashboard, abaixo do cabeçalho
- **Exibe**:
  - "⚡ Fast: última coleta há X minutos"
  - "📊 Completo: última coleta há X minutos"
- **Atualização**: A cada 30 segundos automaticamente
- **Cores de alerta**:
  - Verde: Normal
  - Amarelo: Fast > 10 minutos ou Completo > 30 minutos
  - Cinza (itálico): "Aguardando coleta..." (quando não há dados)

### 5. ✅ Tooltips Informativos

- **Ativação**: Hover sobre card de KPI (aparece após 500ms)
- **Conteúdo**:
  - Nome completo do KPI (`display_name`)
  - Descrição
  - Categoria (Fast ou Completo)
  - Tempo médio de coleta
  - Tabela de armazenamento (`table_name`)
- **Design**: Tooltip escuro, discreto, posicionado automaticamente

## Estrutura de Código

### CSS Adicionado

Localização: Linha ~1093 (após `.kpi-card .kpi-secondary-value`)

- `.kpi-badge` - Estilos para badges Fast/Completo
- `.kpi-avg-duration` - Estilo para tempo médio
- `.kpi-mode-filter` - Estilos para filtro de modo
- `.kpi-collection-status` - Estilos para indicador de última coleta
- `.kpi-tooltip` - Estilos para tooltips

### JavaScript Adicionado

#### Funções Principais

1. **`loadKPIMetadata()`** (linha ~14847)
   - Carrega metadados de KPIs da API `/api/v1/kpis/metadata`
   - Cache de 5 minutos
   - Retorna objeto com metadados indexados por nome do KPI

2. **`formatDuration(ms)`** (linha ~14874)
   - Formata tempo em milissegundos para formato legível
   - Exemplos: "35ms", "1.2s", "15.5min"

3. **`getLastCollectionTime(mode)`** (linha ~14882)
   - Obtém timestamp da última coleta para um modo específico
   - Usa endpoint `/api/v1/kpis/by-mode/{mode}`

4. **`getTimeSinceCollection(timestamp)`** (linha ~14906)
   - Calcula minutos desde última coleta

5. **`generateCollectionStatusHtml(fast, complete)`** (linha ~14913)
   - Gera HTML do indicador de última coleta

6. **`generateKPIModeFilterHtml()`** (linha ~14940)
   - Gera HTML do filtro por modo

7. **`filterKPIsByMode(mode)`** (linha ~14955)
   - Filtra cards de KPI baseado no modo selecionado
   - Salva preferência em localStorage

8. **`initializeKPITooltips()`** (linha ~14985)
   - Inicializa tooltips em todos os cards de KPI
   - Usa dados de `data-kpi-meta` attribute

#### Modificações em Funções Existentes

1. **`generateKPICards(data)`** (linha ~14914)
   - Adicionado: Badge baseado em `is_fast`
   - Adicionado: Tempo médio de coleta
   - Adicionado: Atributo `data-kpi-meta` para tooltips

2. **`renderDashboardCardsContent(...)`** (linha ~15225)
   - Adicionado: Carregamento de metadados antes de gerar cards
   - Adicionado: Obtenção de última coleta por modo
   - Adicionado: Geração de HTML do indicador e filtro
   - Adicionado: Aplicação de filtro salvo após renderizar
   - Adicionado: Inicialização de tooltips
   - Adicionado: Intervalo para atualizar indicador a cada 30s

## Endpoints da API Utilizados

1. **`GET /api/v1/kpis/metadata`**
   - Retorna todos os metadados de KPIs
   - Usado para obter `is_fast`, `avg_duration_ms`, `display_name`, etc.

2. **`GET /api/v1/kpis/by-mode/{mode}`**
   - Retorna KPIs filtrados por modo (`kpi-fast`, `kpi-only`, `all`)
   - Usado para filtrar cards e obter última coleta

## Estrutura de Dados Esperada

### Metadados de KPI (da API)

```json
{
  "name": "blocked_sessions",
  "display_name": "Sessões Bloqueadas",
  "category": "fast",
  "description": "...",
  "avg_duration_ms": 140.72,
  "max_duration_ms": 2163.45,
  "table_name": "KPI_MSSQL_BLOCKED_SESSIONS_STG",
  "is_fast": true
}
```

## Como Testar

### 1. Teste de Badges

1. Abra o dashboard KPI
2. Verifique se os cards mostram badges "⚡ FAST" ou "📊 COMPLETO" no canto superior direito
3. Badges devem corresponder ao campo `is_fast` da API

### 2. Teste de Filtro

1. Use o dropdown "Filtrar por modo de coleta"
2. Selecione "⚡ Fast (5 min)" - apenas cards com badge FAST devem aparecer
3. Selecione "📊 Completo (15 min)" - apenas cards com badge COMPLETO devem aparecer
4. Selecione "Todos" - todos os cards devem aparecer
5. Recarregue a página - o filtro deve manter a seleção anterior

### 3. Teste de Tempo Médio

1. Verifique se abaixo do valor principal de cada KPI aparece "Tempo médio: X ms"
2. O formato deve ser legível (ms, s, ou min)

### 4. Teste de Indicador de Última Coleta

1. Verifique se no topo aparece:
   - "⚡ Fast: última coleta há X minutos"
   - "📊 Completo: última coleta há X minutos"
2. Aguarde 30 segundos - o indicador deve atualizar automaticamente
3. Se não houver dados, deve mostrar "Aguardando coleta..." em itálico

### 5. Teste de Tooltips

1. Passe o mouse sobre um card de KPI
2. Após 500ms, deve aparecer um tooltip com:
   - Nome completo
   - Descrição
   - Categoria
   - Tempo médio
   - Tabela (se disponível)
3. Ao remover o mouse, o tooltip deve desaparecer

### 6. Teste de Tratamento de Erros

1. Se a API `/api/v1/kpis/metadata` não estiver disponível:
   - Dashboard deve continuar funcionando
   - Badges e tempo médio não aparecerão
   - Filtro ainda funcionará (mostrando todos)

2. Se a API `/api/v1/kpis/by-mode/{mode}` falhar:
   - Filtro deve continuar funcionando com dados locais
   - Indicador de última coleta mostrará "Aguardando coleta..."

## Notas Técnicas

- **Cache de Metadados**: 5 minutos (configurável via `KPI_METADATA_CACHE_TTL`)
- **Atualização de Indicador**: A cada 30 segundos
- **Tooltip Delay**: 500ms após hover
- **Persistência**: Filtro salvo em `localStorage` (chave: `kpiModeFilter`)
- **Compatibilidade**: Mantém compatibilidade com código existente
- **Performance**: Metadados carregados em paralelo com dados de KPIs

## Possíveis Melhorias Futuras

1. Adicionar animação suave ao filtrar cards
2. Adicionar contador de KPIs visíveis no filtro
3. Adicionar opção para ocultar/mostrar badges
4. Adicionar gráfico de histórico de tempos de coleta
5. Adicionar notificações quando última coleta ultrapassar threshold

## Troubleshooting

### Badges não aparecem
- Verifique se a API `/api/v1/kpis/metadata` está retornando dados
- Verifique se o campo `is_fast` está presente nos metadados
- Verifique console do navegador para erros

### Filtro não funciona
- Verifique se `kpiMetadataCache` está populado
- Verifique se os KPIs têm `data-kpi-id` correto
- Verifique console para erros de JavaScript

### Tooltips não aparecem
- Verifique se os cards têm atributo `data-kpi-meta`
- Verifique se `initializeKPITooltips()` está sendo chamada
- Verifique se há conflitos de z-index com outros elementos

### Indicador não atualiza
- Verifique se o intervalo está sendo criado (`window.kpiCollectionStatusInterval`)
- Verifique se a API está retornando timestamps válidos
- Verifique console para erros de fetch

