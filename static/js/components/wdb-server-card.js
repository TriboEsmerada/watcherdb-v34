/**
 * <wdb-server-card> — Server card for sidebar list
 *
 * Usage:
 *   <wdb-server-card
 *     server-id="SQLPRD01_I01"
 *     name="SQLPRD01\I01"
 *     status="online"
 *     environment="production">
 *   </wdb-server-card>
 */
class WdbServerCard extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
    }

    static get observedAttributes() {
        return ['server-id', 'name', 'status', 'environment', 'selected'];
    }

    connectedCallback() { this.render(); }
    attributeChangedCallback() { this.render(); }

    render() {
        const name = this.getAttribute('name') || 'Unknown';
        const status = this.getAttribute('status') || 'unknown';
        const env = this.getAttribute('environment') || '';
        const selected = this.hasAttribute('selected');
        const serverId = this.getAttribute('server-id') || '';

        const statusColors = {
            online: '#10b981', offline: '#ef4444', warning: '#f59e0b', unknown: '#6b7280'
        };
        const envLabels = {
            production: 'PRD', development: 'DEV', staging: 'STG', test: 'TST'
        };

        this.shadowRoot.innerHTML = `
            <style>
                :host { display: block; cursor: pointer; }
                .card {
                    padding: 10px 12px; margin: 2px 0;
                    border-radius: 6px; border-left: 3px solid ${statusColors[status] || '#6b7280'};
                    background: ${selected ? 'rgba(59,130,246,0.15)' : 'transparent'};
                    transition: background 0.2s;
                    display: flex; align-items: center; gap: 10px;
                }
                .card:hover { background: rgba(59,130,246,0.1); }
                .status-dot {
                    width: 8px; height: 8px; border-radius: 50%;
                    background: ${statusColors[status] || '#6b7280'};
                    flex-shrink: 0;
                }
                .info { flex: 1; min-width: 0; }
                .name {
                    color: var(--color-text-primary, #f1f5f9);
                    font-size: 13px; font-weight: 500;
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
                }
                .env-badge {
                    font-size: 10px; font-weight: 700; padding: 2px 6px;
                    border-radius: 3px; color: #fff; flex-shrink: 0;
                    background: ${env === 'production' ? '#dc2626' : env === 'development' ? '#2563eb' : '#6b7280'};
                }
            </style>
            <div class="card"
                 hx-get="/htmx/server/${serverId}/header"
                 hx-target="#serverHeader"
                 hx-swap="innerHTML">
                <div class="status-dot"></div>
                <div class="info">
                    <div class="name">${name}</div>
                </div>
                ${env ? `<span class="env-badge">${envLabels[env] || env.substring(0,3).toUpperCase()}</span>` : ''}
            </div>
        `;
    }
}

customElements.define('wdb-server-card', WdbServerCard);
