// ============================================================================
// WatcherDB PORTAL - PATCH JAVASCRIPT PARA CORRIGIR EXIBICAO
// ============================================================================
// Este arquivo corrige a exibicao para mostrar FILEGROUPS em vez de LOGICAL NAMES
// REQUIRES: /static/js/security_utils.js loaded before this file
// ============================================================================

console.log("🔧 [PATCH] Carregando correção do portal...");

// ============================================================================
// CONFIGURAÇÃO
// ============================================================================

const DASHBOARD_CONFIG = {
    // Endpoint CORRETO para usar
    endpoint: '/api/monitoring/space/server/{server_id}/dashboard',
    
    // Ordenação: false = overflows por último (padrão)
    reverseOverflow: false,
    
    // Cache local
    cacheEnabled: true,
    cacheDuration: 5 * 60 * 1000, // 5 minutos
};

// Cache local
let dashboardCache = new Map();

// ============================================================================
// FUNÇÃO PRINCIPAL: CARREGAR DADOS DO DASHBOARD
// ============================================================================

async function loadDashboardDataFixed(serverId) {
    try {
        console.log(`📊 [DASHBOARD] Carregando dados para ${serverId}`);
        
        // Verificar cache
        if (DASHBOARD_CONFIG.cacheEnabled) {
            const cached = getCachedData(serverId);
            if (cached) {
                console.log(`📦 [CACHE] Usando dados em cache`);
                renderDashboardFixed(cached);
                return;
            }
        }
        
        // Mostrar loading
        showLoading();
        
        // Montar URL do endpoint CORRETO
        const url = DASHBOARD_CONFIG.endpoint.replace('{server_id}', serverId);
        
        console.log(`🌐 [REQUEST] GET ${url}`);
        
        // Fazer requisição
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        console.log(`✅ [RESPONSE] Dados recebidos:`, data);
        
        if (!data.success) {
            throw new Error(data.error || 'Erro desconhecido ao buscar dados');
        }
        
        // Salvar no cache
        if (DASHBOARD_CONFIG.cacheEnabled) {
            setCachedData(serverId, data.data);
        }
        
        // Renderizar
        renderDashboardFixed(data.data);
        
        // Carregar health score
        loadHealthScoreFixed(serverId);
        
        console.log(`✅ [DASHBOARD] Dados carregados com sucesso`);
        
    } catch (error) {
        console.error(`❌ [DASHBOARD] Erro ao carregar:`, error);
        showError(`Erro ao carregar dashboard: ${error.message}`);
    } finally {
        hideLoading();
    }
}

// ============================================================================
// FUNÇÕES DE CACHE
// ============================================================================

function getCachedData(serverId) {
    const cacheKey = `dashboard_${serverId}`;
    const cached = dashboardCache.get(cacheKey);
    
    if (cached) {
        const age = Date.now() - cached.timestamp;
        if (age < DASHBOARD_CONFIG.cacheDuration) {
            return cached.data;
        } else {
            // Cache expirado
            dashboardCache.delete(cacheKey);
        }
    }
    
    return null;
}

function setCachedData(serverId, data) {
    const cacheKey = `dashboard_${serverId}`;
    dashboardCache.set(cacheKey, {
        data: data,
        timestamp: Date.now()
    });
}

function clearCache() {
    dashboardCache.clear();
    console.log('🗑️ [CACHE] Cache limpo');
}

// ============================================================================
// RENDERIZAÇÃO DO DASHBOARD - VERSÃO CORRIGIDA
// ============================================================================

function renderDashboardFixed(data) {
    console.log(`🎨 [RENDER] Renderizando dashboard...`);
    
    // Renderizar summary
    renderSummary(data.summary);
    
    // Renderizar filegroups
    renderFilegroups(data.filegroups);
    
    console.log(`✅ [RENDER] Dashboard renderizado`);
}

function renderSummary(summary) {
    // Atualizar badges de summary
    const summaryContainer = document.getElementById('dashboard-summary');
    if (!summaryContainer) return;
    
    safeHTML(summaryContainer, `
        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-label">Total</div>
                <div class="summary-value">${summary.total_filegroups}</div>
            </div>
            <div class="summary-card overflow">
                <div class="summary-label">🚨 Overflows</div>
                <div class="summary-value">${summary.overflow_count}</div>
            </div>
            <div class="summary-card critical">
                <div class="summary-label">🔴 Criticos</div>
                <div class="summary-value">${summary.critical_count}</div>
            </div>
            <div class="summary-card warning">
                <div class="summary-label">🟡 Avisos</div>
                <div class="summary-value">${summary.warning_count}</div>
            </div>
            <div class="summary-card ok">
                <div class="summary-label">✅ OK</div>
                <div class="summary-value">${summary.ok_count}</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">Uso Medio</div>
                <div class="summary-value">${summary.average_usage_percent.toFixed(1)}%</div>
            </div>
        </div>
    `);
}

function renderFilegroups(filegroups) {
    const container = document.getElementById('filegroups-container');
    if (!container) {
        console.error('❌ Container #filegroups-container não encontrado');
        return;
    }
    
    // Limpar container
    container.innerHTML = '';

    if (!filegroups || filegroups.length === 0) {
        safeHTML(container, '<div class="no-data">Nenhum filegroup encontrado</div>');
        return;
    }
    
    console.log(`📊 [RENDER] Renderizando ${filegroups.length} filegroups`);
    
    // Renderizar cada filegroup
    filegroups.forEach((fg, index) => {
        const card = createFileGroupCard(fg, index);
        container.appendChild(card);
    });
}

// ============================================================================
// CRIAR CARD DE FILEGROUP - VERSÃO CORRIGIDA
// ============================================================================

function createFileGroupCard(fg, index) {
    const card = document.createElement('div');
    card.className = `filegroup-card alert-${fg.alert_level.toLowerCase()}`;
    card.dataset.index = index;
    
    // Ícone baseado no tipo
    const typeIcon = fg.filegroup_type === 'LOG' ? '📝' : '💾';
    
    // Badge de alert level
    const alertBadge = getAlertBadge(fg.alert_level);
    
    // Overflow warning
    const overflowWarning = fg.is_overflow ? 
        '<div class="overflow-banner">🚨 OVERFLOW - AÇÃO URGENTE!</div>' : '';
    
    safeHTML(card, `
        ${overflowWarning}

        <div class="filegroup-header">
            <div class="filegroup-title">
                <span class="type-icon">${typeIcon}</span>
                <h3>${fg.database_name}.${fg.filegroup_name}</h3>
                <span class="filegroup-type-badge">${fg.filegroup_type}</span>
            </div>
            ${alertBadge}
        </div>

        <div class="filegroup-body">
            <!-- Barra de progresso -->
            <div class="progress-container">
                <div class="progress-bar">
                    <div class="progress-fill ${getProgressClass(fg.usage_percent)}"
                         style="width: ${fg.usage_percent}%">
                    </div>
                </div>
                <div class="progress-label">
                    <span>${fg.usage_percent.toFixed(1)}% usado</span>
                    <span>${fg.used_size_gb.toFixed(2)} GB / ${fg.total_size_gb.toFixed(2)} GB</span>
                </div>
            </div>

            <!-- Metricas -->
            <div class="metrics-grid">
                <div class="metric">
                    <span class="metric-icon">💾</span>
                    <div class="metric-content">
                        <div class="metric-label">Tamanho Total</div>
                        <div class="metric-value">${fg.total_size_gb.toFixed(2)} GB</div>
                    </div>
                </div>

                <div class="metric">
                    <span class="metric-icon">📊</span>
                    <div class="metric-content">
                        <div class="metric-label">Em Uso</div>
                        <div class="metric-value">${fg.used_size_gb.toFixed(2)} GB</div>
                    </div>
                </div>

                <div class="metric">
                    <span class="metric-icon">🆓</span>
                    <div class="metric-content">
                        <div class="metric-label">Livre</div>
                        <div class="metric-value">${fg.free_size_gb.toFixed(2)} GB</div>
                    </div>
                </div>

                <div class="metric">
                    <span class="metric-icon">📈</span>
                    <div class="metric-content">
                        <div class="metric-label">MaxSize</div>
                        <div class="metric-value">${fg.max_size_gb.toFixed(2)} GB</div>
                    </div>
                </div>

                <div class="metric">
                    <span class="metric-icon">💿</span>
                    <div class="metric-content">
                        <div class="metric-label">Volume ${fg.volume}</div>
                        <div class="metric-value">${fg.disk_available_gb.toFixed(2)} GB livre</div>
                    </div>
                </div>

                <div class="metric">
                    <span class="metric-icon">📂</span>
                    <div class="metric-content">
                        <div class="metric-label">Files</div>
                        <div class="metric-value">${fg.file_count}</div>
                    </div>
                </div>
            </div>

            <!-- Risk Factors -->
            ${renderRiskFactors(fg.risk_factors)}

            <!-- Detalhes expansiveis -->
            <div class="filegroup-details">
                <button class="btn-details" data-toggle-index="${index}">
                    Ver Logical Names (${fg.logical_names.length})
                </button>
                <div class="details-content" id="details-${index}" style="display: none;">
                    <div class="logical-names">
                        ${fg.logical_names.map(name =>
                            `<span class="logical-name-tag">${name}</span>`
                        ).join('')}
                    </div>
                </div>
            </div>
        </div>
    `);

    // Bind toggle details event
    card.querySelector('[data-toggle-index]')?.addEventListener('click', () => toggleDetails(index));

    return card;
}

// ============================================================================
// FUNÇÕES AUXILIARES
// ============================================================================

function getAlertBadge(alertLevel) {
    const badges = {
        'OVERFLOW': '<span class="badge badge-overflow">🚨 OVERFLOW</span>',
        'CRITICAL': '<span class="badge badge-critical">🔴 CRÍTICO</span>',
        'WARNING': '<span class="badge badge-warning">🟡 AVISO</span>',
        'OK': '<span class="badge badge-ok">✅ OK</span>',
    };
    return badges[alertLevel] || badges['OK'];
}

function getProgressClass(percent) {
    if (percent >= 99) return 'progress-overflow';
    if (percent >= 90) return 'progress-critical';
    if (percent >= 80) return 'progress-warning';
    return 'progress-ok';
}

function renderRiskFactors(riskFactors) {
    if (!riskFactors || riskFactors.length === 0) {
        return '';
    }
    
    return `
        <div class="risk-factors">
            <div class="risk-factors-title">⚠️ Fatores de Risco:</div>
            <div class="risk-factors-list">
                ${riskFactors.map(risk => 
                    `<div class="risk-factor-item">${risk}</div>`
                ).join('')}
            </div>
        </div>
    `;
}

function toggleDetails(index) {
    const details = document.getElementById(`details-${index}`);
    if (details) {
        details.style.display = details.style.display === 'none' ? 'block' : 'none';
    }
}

// ============================================================================
// HEALTH SCORE
// ============================================================================

async function loadHealthScoreFixed(serverId) {
    try {
        const url = `/api/monitoring/space/server/${serverId}/dashboard/health`;
        const response = await fetch(url);
        
        if (!response.ok) return;
        
        const data = await response.json();
        
        if (data.success) {
            renderHealthScore(data);
        }
        
    } catch (error) {
        console.error('Erro ao carregar health score:', error);
    }
}

function renderHealthScore(data) {
    const container = document.getElementById('health-score-container');
    if (!container) return;
    
    const health = data;
    
    safeHTML(container, `
        <div class="health-score-card" style="border-color: ${health.status_color}">
            <div class="health-score-header">
                <h3>Health Score</h3>
                <span class="health-status" style="background-color: ${health.status_color}">
                    ${health.status}
                </span>
            </div>
            <div class="health-score-value" style="color: ${health.status_color}">
                ${health.health_score}
            </div>
            <div class="health-recommendations">
                ${health.recommendations.map(rec =>
                    `<div class="recommendation">${rec}</div>`
                ).join('')}
            </div>
        </div>
    `);
}

// ============================================================================
// UI HELPERS
// ============================================================================

function showLoading() {
    const container = document.getElementById('filegroups-container');
    if (container) {
        safeHTML(container, `
            <div class="loading-spinner">
                <div class="spinner"></div>
                <p>Carregando dados do dashboard...</p>
            </div>
        `);
    }
}

function hideLoading() {
    // Loading é substituído pelo conteúdo real
}

function showError(message) {
    const container = document.getElementById('filegroups-container');
    if (container) {
        safeHTML(container, `
            <div class="error-message">
                <span class="error-icon">❌</span>
                <p>${message}</p>
                <button class="btn-retry" data-action="retry-load">Tentar Novamente</button>
            </div>
        `);
        container.querySelector('[data-action="retry-load"]')?.addEventListener('click', () => retryLoad());
    }
}

function retryLoad() {
    const serverId = getCurrentServerId();
    if (serverId) {
        clearCache();
        loadDashboardDataFixed(serverId);
    }
}

function getCurrentServerId() {
    // Pega o server_id atual do seletor
    const selector = document.getElementById('server-selector');
    return selector ? selector.value : null;
}

// ============================================================================
// AUTO-REFRESH
// ============================================================================

let autoRefreshInterval = null;

function startAutoRefresh(intervalMinutes = 5) {
    stopAutoRefresh(); // Para qualquer refresh anterior
    
    autoRefreshInterval = setInterval(() => {
        const serverId = getCurrentServerId();
        if (serverId) {
            console.log('🔄 [AUTO-REFRESH] Atualizando dados...');
            loadDashboardDataFixed(serverId);
        }
    }, intervalMinutes * 60 * 1000);
    
    console.log(`✅ [AUTO-REFRESH] Ativado (${intervalMinutes} minutos)`);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
        console.log('⏹️ [AUTO-REFRESH] Desativado');
    }
}

// ============================================================================
// INICIALIZAÇÃO
// ============================================================================

// Quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ [PATCH] Patch carregado com sucesso!');
    
    // Event listener para mudança de servidor
    const serverSelector = document.getElementById('server-selector');
    if (serverSelector) {
        serverSelector.addEventListener('change', function() {
            loadDashboardDataFixed(this.value);
        });
    }
    
    // Carregar dados iniciais
    const serverId = getCurrentServerId();
    if (serverId) {
        loadDashboardDataFixed(serverId);
        startAutoRefresh(5); // Auto-refresh a cada 5 minutos
    }
});

// ============================================================================
// EXPORTAR FUNÇÕES GLOBAIS
// ============================================================================

window.loadDashboardDataFixed = loadDashboardDataFixed;
window.clearCache = clearCache;
window.toggleDetails = toggleDetails;
window.retryLoad = retryLoad;
window.startAutoRefresh = startAutoRefresh;
window.stopAutoRefresh = stopAutoRefresh;

console.log('🎸 [PATCH] Sistema de dashboard corrigido - Agora mostra FILEGROUPS!');
