/**
 * <wdb-kpi-card> — KPI metric display card
 *
 * Usage:
 *   <wdb-kpi-card
 *     title="CPU Usage"
 *     value="45"
 *     unit="%"
 *     status="ok"
 *     icon="fa-microchip">
 *   </wdb-kpi-card>
 */
class WdbKpiCard extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
    }

    static get observedAttributes() {
        return ['title', 'value', 'unit', 'status', 'icon', 'trend'];
    }

    connectedCallback() { this.render(); }
    attributeChangedCallback() { this.render(); }

    render() {
        const title = this.getAttribute('title') || '';
        const value = this.getAttribute('value') || '\u2014';
        const unit = this.getAttribute('unit') || '';
        const status = this.getAttribute('status') || 'neutral';
        const icon = this.getAttribute('icon') || 'fa-chart-bar';
        const trend = this.getAttribute('trend') || '';

        const statusColors = {
            ok: '#10b981', warning: '#f59e0b', critical: '#ef4444',
            info: '#3b82f6', neutral: '#6b7280'
        };
        const color = statusColors[status] || statusColors.neutral;

        const trendIcon = trend === 'up' ? '\u2191' : trend === 'down' ? '\u2193' : '';
        const trendColor = trend === 'up' ? '#ef4444' : trend === 'down' ? '#10b981' : '#6b7280';

        this.shadowRoot.innerHTML = `
            <style>
                :host { display: block; }
                .kpi-card {
                    background: var(--color-bg-secondary, #111827);
                    border: 1px solid var(--color-border, #374151);
                    border-radius: 8px; padding: 16px;
                    border-left: 3px solid ${color};
                    transition: transform 0.2s, box-shadow 0.2s;
                }
                .kpi-card:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                }
                .header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
                .header i { color: ${color}; font-size: 14px; }
                .title { color: #94a3b8; font-size: 12px; font-weight: 500; text-transform: uppercase; }
                .value-row { display: flex; align-items: baseline; gap: 4px; }
                .value { color: #f1f5f9; font-size: 28px; font-weight: 700; }
                .unit { color: #64748b; font-size: 14px; }
                .trend { color: ${trendColor}; font-size: 14px; margin-left: 8px; }
            </style>
            <div class="kpi-card">
                <div class="header">
                    <i class="fas ${icon}"></i>
                    <span class="title">${title}</span>
                </div>
                <div class="value-row">
                    <span class="value">${value}</span>
                    <span class="unit">${unit}</span>
                    ${trendIcon ? `<span class="trend">${trendIcon}</span>` : ''}
                </div>
            </div>
        `;
    }
}

customElements.define('wdb-kpi-card', WdbKpiCard);
