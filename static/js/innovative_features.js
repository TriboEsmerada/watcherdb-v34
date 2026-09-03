/**
 * WatcherDB - Innovative Features Integration
 * Integra Maintenance Score, Chaos Detection e DBA Copilot ao portal existente
 * Version: 1.0.1
 *
 * REQUIRES: /static/js/security_utils.js loaded before this file
 */

// =============================================
// CONFIGURACAO
// =============================================
const INTELLIGENCE_API = 'http://localhost:8001/api/v1';  // API do WatcherDB Intelligence V1 (porta 8001)

// Estado global das features inovadoras
const innovativeState = {
    scores: null,
    chaosData: null,
    insights: null,
    copilotMessages: [],
    lastUpdate: null,
    autoRefreshInterval: null
};

// =============================================
// MAINTENANCE SCORE
// =============================================
const MaintenanceScore = {
    async load() {
        const container = document.getElementById('maintenance-score-content');
        if (!container) return;

        safeHTML(container, `
            <div class="loading-state">
                <i class="fas fa-spinner fa-spin"></i>
                <span>Calculando scores de manutencao preditiva...</span>
            </div>
        `);

        try {
            const response = await fetch(`${INTELLIGENCE_API}/maintenance-score/`);
            if (!response.ok) throw new Error(`Erro ${response.status}`);

            const data = await response.json();
            innovativeState.scores = data;
            innovativeState.lastUpdate = new Date();
            this.render(data);
        } catch (error) {
            console.error('Erro MaintenanceScore:', error);
            safeHTML(container, `
                <div class="error-state">
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>Erro ao carregar scores: ${error.message}</span>
                    <button class="btn-retry" data-action="retry-maintenance">
                        <i class="fas fa-redo"></i> Tentar novamente
                    </button>
                </div>
            `);
            container.querySelector('[data-action="retry-maintenance"]')?.addEventListener('click', () => MaintenanceScore.load());
        }
    },

    render(data) {
        const container = document.getElementById('maintenance-score-content');
        if (!container) return;

        const summary = data.summary || {};
        const scores = data.scores || [];

        // Ordenar por score (menor primeiro = mais critico)
        scores.sort((a, b) => a.score - b.score);

        safeHTML(container, `
            <!-- Summary Cards -->
            <div class="innovative-summary-grid">
                <div class="innovative-summary-card">
                    <div class="summary-icon info"><i class="fas fa-server"></i></div>
                    <div class="summary-value">${summary.total_instances || 0}</div>
                    <div class="summary-label">Total Instancias</div>
                </div>
                <div class="innovative-summary-card critical">
                    <div class="summary-icon critical"><i class="fas fa-exclamation-circle"></i></div>
                    <div class="summary-value">${summary.critical_count || 0}</div>
                    <div class="summary-label">Criticas</div>
                </div>
                <div class="innovative-summary-card warning">
                    <div class="summary-icon warning"><i class="fas fa-exclamation-triangle"></i></div>
                    <div class="summary-value">${summary.warning_count || 0}</div>
                    <div class="summary-label">Warning</div>
                </div>
                <div class="innovative-summary-card healthy">
                    <div class="summary-icon healthy"><i class="fas fa-check-circle"></i></div>
                    <div class="summary-value">${summary.healthy_count || 0}</div>
                    <div class="summary-label">Saudaveis</div>
                </div>
                <div class="innovative-summary-card">
                    <div class="summary-icon info"><i class="fas fa-chart-line"></i></div>
                    <div class="summary-value">${Math.round(summary.average_score || 0)}</div>
                    <div class="summary-label">Score Medio</div>
                </div>
            </div>

            <!-- Score Cards Grid -->
            <div class="innovative-section-title">
                <i class="fas fa-heartbeat"></i> Scores por Instancia
                <span class="section-subtitle">Clique em uma instancia para ver detalhes</span>
            </div>
            <div class="score-cards-grid">
                ${scores.map(score => this.renderScoreCard(score)).join('')}
            </div>
        `);

        // Event delegation for score card clicks
        container.querySelectorAll('.score-card[data-instance]').forEach(card => {
            card.addEventListener('click', () => MaintenanceScore.showDetails(card.dataset.instance));
        });
    },

    renderScoreCard(score) {
        const level = score.risk_level?.toLowerCase() || 'healthy';
        const trendIcon = score.trend === 'IMPROVING' ? 'fa-arrow-up' :
                         score.trend === 'DEGRADING' ? 'fa-arrow-down' : 'fa-minus';
        const trendClass = score.trend?.toLowerCase() || 'stable';

        const risks = (score.top_risks || []).slice(0, 2);

        return `
            <div class="score-card ${level}" data-instance="${score.instance_id}">
                <div class="score-card-header">
                    <span class="instance-name">${score.instance_id?.replace('_', '\\\\') || 'Unknown'}</span>
                    <span class="risk-badge ${level}">${score.risk_level || 'N/A'}</span>
                </div>
                <div class="score-display">
                    <span class="score-value ${level}">${score.score || 0}</span>
                    <span class="score-max">/100</span>
                </div>
                <div class="score-bar-container">
                    <div class="score-bar-fill ${level}" style="width: ${score.score || 0}%"></div>
                </div>
                <div class="score-trend ${trendClass}">
                    <i class="fas ${trendIcon}"></i>
                    ${score.trend || 'STABLE'}
                    ${score.score_change_24h ? ` (${score.score_change_24h > 0 ? '+' : ''}${score.score_change_24h.toFixed(1)})` : ''}
                </div>
                ${risks.length > 0 ? `
                    <div class="score-risks">
                        ${risks.map(r => `<div class="risk-item"><i class="fas fa-warning"></i> ${r}</div>`).join('')}
                    </div>
                ` : ''}
                <div class="incident-probability">
                    <span title="Probabilidade de incidente em 24h">
                        <i class="fas fa-clock"></i> 24h: ${(score.incident_probability?.hours_24 || 0).toFixed(0)}%
                    </span>
                </div>
            </div>
        `;
    },

    async showDetails(instanceId) {
        try {
            const response = await fetch(`${INTELLIGENCE_API}/maintenance-score/instance/${instanceId}?include_details=true`);
            if (!response.ok) throw new Error('Erro ao carregar detalhes');

            const score = await response.json();
            this.renderDetailsModal(score);
        } catch (error) {
            alert('Erro: ' + error.message);
        }
    },

    renderDetailsModal(score) {
        const level = score.risk_level?.toLowerCase() || 'healthy';

        const modalWrapper = document.createElement('div');
        safeHTML(modalWrapper, `
            <div class="innovative-modal-overlay">
                <div class="innovative-modal">
                    <div class="modal-header">
                        <h2><i class="fas fa-server"></i> ${score.instance_id?.replace('_', '\\\\')}</h2>
                        <button class="modal-close" data-action="close-modal">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-body">
                        <div class="modal-score-display ${level}">
                            <div class="big-score">${score.score || 0}</div>
                            <div class="score-label">/100 - ${score.risk_level}</div>
                        </div>

                        <div class="modal-section">
                            <h3><i class="fas fa-exclamation-circle"></i> Probabilidade de Incidente</h3>
                            <div class="probability-grid">
                                <div class="prob-item">
                                    <span class="prob-time">24h</span>
                                    <span class="prob-value">${(score.incident_probability?.hours_24 || 0).toFixed(1)}%</span>
                                </div>
                                <div class="prob-item">
                                    <span class="prob-time">48h</span>
                                    <span class="prob-value">${(score.incident_probability?.hours_48 || 0).toFixed(1)}%</span>
                                </div>
                                <div class="prob-item">
                                    <span class="prob-time">72h</span>
                                    <span class="prob-value">${(score.incident_probability?.hours_72 || 0).toFixed(1)}%</span>
                                </div>
                            </div>
                        </div>

                        ${score.risk_factors?.length > 0 ? `
                            <div class="modal-section">
                                <h3><i class="fas fa-list"></i> Fatores de Risco</h3>
                                ${score.risk_factors.map(f => `
                                    <div class="risk-factor-item">
                                        <div class="factor-header">
                                            <span class="factor-name">${f.name}</span>
                                            <span class="factor-weight">${(f.risk_contribution || 0).toFixed(0)}%</span>
                                        </div>
                                        <div class="factor-desc">${f.description}</div>
                                        ${f.recommendation ? `<div class="factor-action"><i class="fas fa-lightbulb"></i> ${f.recommendation}</div>` : ''}
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `);

        const overlay = modalWrapper.firstElementChild;
        document.body.appendChild(overlay);

        // Event listeners for modal close
        overlay.addEventListener('click', (e) => { if (e.target === overlay) MaintenanceScore.closeModal(); });
        overlay.querySelector('.innovative-modal').addEventListener('click', (e) => e.stopPropagation());
        overlay.querySelector('[data-action="close-modal"]').addEventListener('click', () => MaintenanceScore.closeModal());
    },

    closeModal(event) {
        if (event && event.target !== event.currentTarget) return;
        const modal = document.querySelector('.innovative-modal-overlay');
        if (modal) modal.remove();
    }
};

// =============================================
// CHAOS DETECTION
// =============================================
const ChaosDetection = {
    async load(timeWindow = 60) {
        const container = document.getElementById('chaos-detection-content');
        if (!container) return;

        safeHTML(container, `
            <div class="loading-state">
                <i class="fas fa-spinner fa-spin"></i>
                <span>Detectando padroes de anomalias...</span>
            </div>
        `);

        try {
            const [chaosRes, alertsRes] = await Promise.all([
                fetch(`${INTELLIGENCE_API}/chaos-detection/?time_window_minutes=${timeWindow}`),
                fetch(`${INTELLIGENCE_API}/chaos-detection/alerts/urgent`)
            ]);

            if (!chaosRes.ok) throw new Error(`Erro ${chaosRes.status}`);

            const chaosData = await chaosRes.json();
            const alertsData = alertsRes.ok ? await alertsRes.json() : {};

            innovativeState.chaosData = { ...chaosData, alerts: alertsData };
            this.render(innovativeState.chaosData);
        } catch (error) {
            console.error('Erro ChaosDetection:', error);
            safeHTML(container, `
                <div class="error-state">
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>Erro ao detectar chaos: ${error.message}</span>
                    <button class="btn-retry" data-action="retry-chaos">
                        <i class="fas fa-redo"></i> Tentar novamente
                    </button>
                </div>
            `);
            container.querySelector('[data-action="retry-chaos"]')?.addEventListener('click', () => ChaosDetection.load());
        }
    },

    render(data) {
        const container = document.getElementById('chaos-detection-content');
        if (!container) return;

        const cascadeCount = data.cascade_analyses?.length || 0;
        const infraCount = data.infrastructure_correlations?.length || 0;
        const hasUrgent = data.alerts?.requires_immediate_attention || false;

        safeHTML(container, `
            <!-- Alerta urgente se houver -->
            ${hasUrgent ? `
                <div class="urgent-alert">
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>ATENCAO: Correlacoes criticas detectadas que requerem acao imediata!</span>
                </div>
            ` : ''}

            <!-- Summary Cards -->
            <div class="innovative-summary-grid">
                <div class="innovative-summary-card">
                    <div class="summary-icon info"><i class="fas fa-search"></i></div>
                    <div class="summary-value">${data.total_events_analyzed || 0}</div>
                    <div class="summary-label">Eventos Analisados</div>
                </div>
                <div class="innovative-summary-card ${data.total_correlations_found > 0 ? 'warning' : ''}">
                    <div class="summary-icon warning"><i class="fas fa-link"></i></div>
                    <div class="summary-value">${data.total_correlations_found || 0}</div>
                    <div class="summary-label">Correlacoes</div>
                </div>
                <div class="innovative-summary-card ${cascadeCount > 0 ? 'critical' : ''}">
                    <div class="summary-icon critical"><i class="fas fa-stream"></i></div>
                    <div class="summary-value">${cascadeCount}</div>
                    <div class="summary-label">Cascatas</div>
                </div>
                <div class="innovative-summary-card ${infraCount > 0 ? 'warning' : ''}">
                    <div class="summary-icon warning"><i class="fas fa-network-wired"></i></div>
                    <div class="summary-value">${infraCount}</div>
                    <div class="summary-label">Prob. Infra</div>
                </div>
            </div>

            <div class="chaos-grid">
                <!-- Padroes Detectados -->
                <div class="chaos-section">
                    <div class="innovative-section-title">
                        <i class="fas fa-project-diagram"></i> Padroes Detectados
                    </div>
                    ${this.renderPatterns(data)}
                </div>

                <!-- Timeline -->
                <div class="chaos-section">
                    <div class="innovative-section-title">
                        <i class="fas fa-history"></i> Timeline de Eventos
                    </div>
                    ${this.renderTimeline(data)}
                </div>
            </div>

            <!-- Acoes Prioritarias -->
            ${data.alerts?.priority_actions?.length > 0 ? `
                <div class="chaos-section full-width">
                    <div class="innovative-section-title critical">
                        <i class="fas fa-bolt"></i> Acoes Prioritarias
                    </div>
                    <div class="priority-actions">
                        ${data.alerts.priority_actions.map(action => `
                            <div class="action-item">
                                <i class="fas fa-arrow-right"></i>
                                ${action}
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
        `);
    },

    renderPatterns(data) {
        const groups = data.correlated_groups || [];

        const patterns = {
            CASCADE: { count: 0, icon: 'fa-stream', label: 'Cascata', desc: 'Problemas propagando entre servidores' },
            SIMULTANEOUS: { count: 0, icon: 'fa-bolt', label: 'Simultaneo', desc: 'Multiplos servidores ao mesmo tempo' },
            PERIODIC: { count: 0, icon: 'fa-clock', label: 'Periodico', desc: 'Padroes recorrentes em horarios fixos' },
            BLAST_RADIUS: { count: 0, icon: 'fa-radiation', label: 'Blast Radius', desc: 'Impacto de falha em outros sistemas' }
        };

        groups.forEach(g => {
            if (patterns[g.pattern_type]) patterns[g.pattern_type].count++;
        });

        return `
            <div class="patterns-list">
                ${Object.entries(patterns).map(([key, p]) => `
                    <div class="pattern-item ${p.count > 0 ? 'active' : ''}">
                        <div class="pattern-icon"><i class="fas ${p.icon}"></i></div>
                        <div class="pattern-info">
                            <div class="pattern-name">${p.label}</div>
                            <div class="pattern-desc">${p.desc}</div>
                        </div>
                        <div class="pattern-count">${p.count}</div>
                    </div>
                `).join('')}
            </div>
        `;
    },

    renderTimeline(data) {
        const events = [];

        (data.correlated_groups || []).forEach(group => {
            (group.events || []).forEach(event => {
                events.push({ ...event, group_id: group.group_id });
            });
        });

        events.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

        if (events.length === 0) {
            return `
                <div class="empty-state">
                    <i class="fas fa-check-circle"></i>
                    <span>Nenhum evento correlacionado no periodo</span>
                </div>
            `;
        }

        return `
            <div class="timeline-list">
                ${events.slice(0, 8).map(event => {
                    const severity = event.severity?.toLowerCase() || 'medium';
                    const time = new Date(event.timestamp).toLocaleString('pt-BR');
                    return `
                        <div class="timeline-item ${severity}">
                            <div class="timeline-dot ${severity}"></div>
                            <div class="timeline-content">
                                <div class="timeline-time">${time}</div>
                                <div class="timeline-title">${event.event_type || 'Evento'}</div>
                                <div class="timeline-desc">${event.description || ''}</div>
                                <span class="timeline-instance">${event.instance_id}</span>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    }
};

// =============================================
// DBA COPILOT
// =============================================
const DBACopilot = {
    async init() {
        const container = document.getElementById('copilot-content');
        if (!container) return;

        safeHTML(container, this.renderInterface());

        // Bind event listeners after rendering
        container.querySelector('#copilot-send')?.addEventListener('click', () => DBACopilot.sendMessage());
        container.querySelector('[data-action="report-daily"]')?.addEventListener('click', () => DBACopilot.generateReport('daily_summary'));
        container.querySelector('[data-action="report-health"]')?.addEventListener('click', () => DBACopilot.generateReport('health_check'));

        await Promise.all([
            this.loadQuickAnswers(),
            this.loadInsights(),
            this.checkStatus()
        ]);
    },

    renderInterface() {
        return `
            <div class="copilot-layout">
                <!-- Chat Section -->
                <div class="copilot-chat-section">
                    <div class="copilot-header">
                        <div class="copilot-title">
                            <i class="fas fa-robot"></i> DBA Copilot
                        </div>
                        <div id="copilot-status" class="copilot-status">
                            <i class="fas fa-circle"></i> Verificando...
                        </div>
                    </div>

                    <div id="copilot-messages" class="copilot-messages">
                        <div class="copilot-welcome">
                            <i class="fas fa-robot"></i>
                            <h3>Ola! Sou o DBA Copilot</h3>
                            <p>Posso ajudar com analises do ambiente SQL Server, responder perguntas e gerar relatorios.</p>
                            <p>Experimente perguntar algo como:</p>
                        </div>
                    </div>

                    <div id="quick-actions" class="quick-actions">
                        <!-- Quick actions loaded dynamically -->
                    </div>

                    <div class="copilot-input-area">
                        <textarea id="copilot-input" placeholder="Digite sua pergunta..." rows="1"></textarea>
                        <button id="copilot-send">
                            <i class="fas fa-paper-plane"></i>
                        </button>
                    </div>
                </div>

                <!-- Insights Section -->
                <div class="copilot-insights-section">
                    <div class="innovative-section-title">
                        <i class="fas fa-lightbulb"></i> Insights Proativos
                    </div>
                    <div id="copilot-insights">
                        <div class="loading-state small">
                            <i class="fas fa-spinner fa-spin"></i>
                        </div>
                    </div>

                    <div class="innovative-section-title" style="margin-top: 24px;">
                        <i class="fas fa-file-alt"></i> Relatorios Rapidos
                    </div>
                    <div class="report-buttons">
                        <button class="report-btn" data-action="report-daily">
                            <i class="fas fa-calendar-day"></i> Resumo Diario
                        </button>
                        <button class="report-btn" data-action="report-health">
                            <i class="fas fa-heartbeat"></i> Health Check
                        </button>
                    </div>
                </div>
            </div>
        `;
    },

    async checkStatus() {
        try {
            const response = await fetch(`${INTELLIGENCE_API}/copilot/status`);
            const status = await response.json();
            const indicator = document.getElementById('copilot-status');
            if (indicator) {
                if (status.llm_available) {
                    safeHTML(indicator, `<i class="fas fa-circle online"></i> ${status.provider} Online`);
                    indicator.className = 'copilot-status online';
                } else {
                    safeHTML(indicator, `<i class="fas fa-circle offline"></i> Modo Rule-Based`);
                    indicator.className = 'copilot-status offline';
                }
            }
        } catch (error) {
            console.error('Erro ao verificar status:', error);
        }
    },

    async loadQuickAnswers() {
        try {
            const response = await fetch(`${INTELLIGENCE_API}/copilot/quick-answers`);
            const answers = await response.json();
            const container = document.getElementById('quick-actions');
            if (container) {
                safeHTML(container, answers.map(qa => `
                    <button class="quick-action-btn quick-question-btn" data-question="${qa.question.replace(/"/g, '&quot;')}">
                        ${qa.question}
                    </button>
                `).join(''));

                // Event delegation for quick question buttons
                container.querySelectorAll('.quick-question-btn').forEach(btn => {
                    btn.addEventListener('click', () => DBACopilot.askQuestion(btn.dataset.question));
                });
            }
        } catch (error) {
            console.error('Erro ao carregar quick answers:', error);
        }
    },

    async loadInsights() {
        try {
            const response = await fetch(`${INTELLIGENCE_API}/copilot/insights`);
            const insights = await response.json();
            innovativeState.insights = insights;

            const container = document.getElementById('copilot-insights');
            if (!container) return;

            if (!insights || insights.length === 0) {
                safeHTML(container, `
                    <div class="empty-state small">
                        <i class="fas fa-check-circle"></i>
                        <span>Nenhum insight no momento</span>
                    </div>
                `);
                return;
            }

            safeHTML(container, insights.map(insight => {
                const severity = insight.severity?.toLowerCase() || 'info';
                return `
                    <div class="insight-item ${severity}">
                        <div class="insight-icon ${severity}">
                            <i class="fas ${severity === 'critical' ? 'fa-exclamation-circle' :
                                           severity === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle'}"></i>
                        </div>
                        <div class="insight-content">
                            <div class="insight-title">${insight.title}</div>
                            <div class="insight-desc">${insight.description}</div>
                            ${insight.suggested_action ? `
                                <div class="insight-action"><i class="fas fa-arrow-right"></i> ${insight.suggested_action}</div>
                            ` : ''}
                        </div>
                    </div>
                `;
            }).join(''));
        } catch (error) {
            console.error('Erro ao carregar insights:', error);
        }
    },

    async askQuestion(question) {
        const input = document.getElementById('copilot-input');
        if (input) input.value = question;
        await this.sendMessage();
    },

    async sendMessage() {
        const input = document.getElementById('copilot-input');
        const sendBtn = document.getElementById('copilot-send');

        if (!input || !input.value.trim()) return;

        const question = input.value.trim();
        input.value = '';

        this.addMessage('user', question);
        sendBtn.disabled = true;
        this.addMessage('bot', '<i class="fas fa-spinner fa-spin"></i> Processando...', true);

        try {
            const response = await fetch(`${INTELLIGENCE_API}/copilot/ask`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: question,
                    include_recommendations: true,
                    language: 'pt-BR'
                })
            });

            if (!response.ok) throw new Error(`Erro ${response.status}`);

            const answer = await response.json();
            this.removeLoadingMessage();

            let html = `<p>${answer.answer}</p>`;
            if (answer.recommendations?.length > 0) {
                html += `
                    <div class="recommendations">
                        <strong>Recomendacoes:</strong>
                        <ul>${answer.recommendations.map(r => `<li>${r}</li>`).join('')}</ul>
                    </div>
                `;
            }
            this.addMessage('bot', html);

        } catch (error) {
            this.removeLoadingMessage();
            this.addMessage('bot', `<span class="error-text">Erro: ${error.message}</span>`);
        } finally {
            sendBtn.disabled = false;
        }
    },

    addMessage(type, content, isLoading = false) {
        const container = document.getElementById('copilot-messages');
        if (!container) return;

        // Remove welcome message
        const welcome = container.querySelector('.copilot-welcome');
        if (welcome) welcome.remove();

        const msg = document.createElement('div');
        msg.className = `copilot-message ${type}`;
        if (isLoading) msg.classList.add('loading-msg');

        safeHTML(msg, `
            <div class="message-avatar ${type}">
                <i class="fas ${type === 'user' ? 'fa-user' : 'fa-robot'}"></i>
            </div>
            <div class="message-bubble">${content}</div>
        `);

        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;
    },

    removeLoadingMessage() {
        const container = document.getElementById('copilot-messages');
        const loading = container?.querySelector('.loading-msg');
        if (loading) loading.remove();
    },

    async generateReport(type) {
        this.addMessage('bot', `<i class="fas fa-spinner fa-spin"></i> Gerando relatorio ${type}...`, true);

        try {
            const response = await fetch(`${INTELLIGENCE_API}/copilot/report`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    report_type: type,
                    period_hours: 24,
                    format: 'markdown'
                })
            });

            if (!response.ok) throw new Error(`Erro ${response.status}`);

            const report = await response.json();
            this.removeLoadingMessage();

            this.addMessage('bot', `
                <div class="report-content">
                    <h4><i class="fas fa-file-alt"></i> ${report.title}</h4>
                    <pre>${report.content}</pre>
                    ${report.key_findings?.length > 0 ? `
                        <div class="key-findings">
                            <strong>Principais Descobertas:</strong>
                            <ul>${report.key_findings.map(f => `<li>${f}</li>`).join('')}</ul>
                        </div>
                    ` : ''}
                </div>
            `);
        } catch (error) {
            this.removeLoadingMessage();
            this.addMessage('bot', `<span class="error-text">Erro ao gerar relatorio: ${error.message}</span>`);
        }
    }
};

// =============================================
// TAB INTEGRATION - Hook into existing showTab
// =============================================
const originalShowTab = window.showTab;

window.showTab = function(tabName) {
    // Se for uma das abas inovadoras, carrega os dados
    switch(tabName) {
        case 'maintenance-score':
            setTimeout(() => MaintenanceScore.load(), 100);
            break;
        case 'chaos-detection':
            setTimeout(() => ChaosDetection.load(), 100);
            break;
        case 'copilot':
            setTimeout(() => DBACopilot.init(), 100);
            break;
    }

    // Chama a funcao original se existir
    if (typeof originalShowTab === 'function') {
        originalShowTab(tabName);
    }
};

// =============================================
// AUTO-REFRESH
// =============================================
function startAutoRefresh(intervalMs = 60000) {
    if (innovativeState.autoRefreshInterval) {
        clearInterval(innovativeState.autoRefreshInterval);
    }

    innovativeState.autoRefreshInterval = setInterval(() => {
        const currentTab = document.querySelector('.tab-content.active')?.id;
        if (currentTab === 'maintenance-score') MaintenanceScore.load();
        else if (currentTab === 'chaos-detection') ChaosDetection.load();
    }, intervalMs);
}

// Export to global
window.MaintenanceScore = MaintenanceScore;
window.ChaosDetection = ChaosDetection;
window.DBACopilot = DBACopilot;
window.startAutoRefresh = startAutoRefresh;

console.log('✅ Innovative Features JS loaded');
