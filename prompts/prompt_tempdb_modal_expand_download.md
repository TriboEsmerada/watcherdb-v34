# Prompt: Expandir/Minimizar e Download HTML no Modal TempDB

## Contexto
O modal "Análise de Crescimento TempDB" do WatcherDB V3.2 não tinha opção de expandir para fullscreen nem de exportar o conteúdo. Os utilizadores precisam de ver a tabela de 15 arquivos TempDB em ecrã inteiro e de guardar o relatório localmente.

## O que foi implementado

### 1. Botões no header do modal
No header do modal de "Análise de Crescimento TempDB" (após os dados carregarem), foram adicionados 3 botões lado a lado, antes do botão de fechar:

```
[⤢ Expandir]  [⬇ Download]  [✕ Fechar]
```

### 2. Expandir/Minimizar (`toggleTempDBModalSize()`)
- Alterna entre tamanho normal (`max-width: 1200px, max-height: 90vh`) e fullscreen (`100vw × 100vh`)
- Ícone muda: `fa-expand` ↔ `fa-compress`
- Border-radius: `12px` em normal, `0` em fullscreen

### 3. Download HTML (`downloadTempDBModalHTML(serverId)`)
- Exporta o conteúdo do `.modal-body` como ficheiro `.html`
- Inclui CSS inline com dark theme (background `#0f172a`, cores consistentes)
- Nome do ficheiro: `TempDB_Analysis_{serverId}_{data}.html`
- Usa `Blob` + `URL.createObjectURL` + click automático no link
- Toast "HTML exportado" após download

## Ficheiros alterados

### `templates/watcherdb_portal.html`

**Localização:** Dentro da função `showTempDBGrowthAnalysisModal(serverId)`, no bloco que gera o HTML após carregar os dados (segunda instância do modal header, após `summary.drive`).

**Header do modal (antes):**
```html
<button class="close-modal-btn" onclick="...display='none'">
    <i class="fas fa-times"></i>
</button>
```

**Header do modal (depois):**
```html
<div style="display:flex;gap:6px;align-items:center;">
    <button class="close-modal-btn" title="Expandir/Minimizar" onclick="toggleTempDBModalSize()">
        <i id="tempdbExpandIcon" class="fas fa-expand"></i>
    </button>
    <button class="close-modal-btn" title="Download HTML" onclick="downloadTempDBModalHTML('${serverId}')">
        <i class="fas fa-download"></i>
    </button>
    <button class="close-modal-btn" onclick="...display='none'">
        <i class="fas fa-times"></i>
    </button>
</div>
```

**Funções JS adicionadas (antes de `showTempDBGrowthAnalysisModal`):**

```javascript
// Toggle TempDB modal between normal and fullscreen
function toggleTempDBModalSize() {
    const modal = document.getElementById('tempdbGrowthModal');
    const content = modal.querySelector('.modal-content');
    const icon = document.getElementById('tempdbExpandIcon');
    const isExpanded = content.style.maxWidth === '100%';
    if (isExpanded) {
        content.style.maxWidth = '1200px';
        content.style.maxHeight = '90vh';
        content.style.width = '';
        content.style.height = '';
        content.style.borderRadius = '12px';
        icon.className = 'fas fa-expand';
    } else {
        content.style.maxWidth = '100%';
        content.style.maxHeight = '100vh';
        content.style.width = '100vw';
        content.style.height = '100vh';
        content.style.borderRadius = '0';
        icon.className = 'fas fa-compress';
    }
}

// Download TempDB modal content as HTML file
function downloadTempDBModalHTML(serverId) {
    const modal = document.getElementById('tempdbGrowthModal');
    const content = modal.querySelector('.modal-content');
    const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>TempDB Analysis - ${serverId}</title>
    <style>
        body { font-family: sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { background: #1e293b; color: #94a3b8; padding: 10px 12px; }
        td { padding: 8px 12px; border-bottom: 1px solid rgba(55,65,81,0.5); }
    </style>
</head>
<body>
    <h1>TempDB Analysis — ${serverId}</h1>
    <p>Generated: ${new Date().toLocaleString('pt-PT')}</p>
    ${content.querySelector('.modal-body')?.innerHTML || ''}
</body>
</html>`;
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `TempDB_Analysis_${serverId}_${new Date().toISOString().slice(0,10)}.html`;
    a.click();
    URL.revokeObjectURL(a.href);
}
```

## Notas
- O modal "Monitoramento TempDB" (o segundo, com sessões consumidoras) já tem expandir/minimizar do sistema genérico de SQL Diagnostics
- Apenas o modal "Análise de Crescimento TempDB" precisava destes botões
- O Download HTML mantém o dark theme no ficheiro exportado
- O ficheiro exportado é standalone (sem dependências externas)
