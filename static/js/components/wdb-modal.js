/**
 * <wdb-modal> — Reusable modal web component
 *
 * Usage:
 *   <wdb-modal id="myModal" title="Report" size="large">
 *     <p>Content here</p>
 *   </wdb-modal>
 *
 *   document.getElementById('myModal').open();
 *   document.getElementById('myModal').close();
 */
class WdbModal extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
    }

    static get observedAttributes() {
        return ['title', 'size', 'open'];
    }

    connectedCallback() {
        this.render();
        this._setupEvents();
    }

    get isOpen() {
        return this.hasAttribute('open');
    }

    open() {
        this.setAttribute('open', '');
        this.dispatchEvent(new CustomEvent('modal-open', { bubbles: true }));
    }

    close() {
        this.removeAttribute('open');
        this.dispatchEvent(new CustomEvent('modal-close', { bubbles: true }));
    }

    attributeChangedCallback() {
        if (this.shadowRoot.querySelector('.modal-overlay')) {
            this.render();
        }
    }

    _setupEvents() {
        this.shadowRoot.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-overlay') || e.target.classList.contains('modal-close')) {
                this.close();
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) this.close();
        });
    }

    render() {
        const title = this.getAttribute('title') || '';
        const size = this.getAttribute('size') || 'medium';
        const isOpen = this.isOpen;

        this.shadowRoot.innerHTML = `
            <style>
                :host { display: ${isOpen ? 'block' : 'none'}; }
                .modal-overlay {
                    position: fixed; inset: 0;
                    background: rgba(0,0,0,0.7);
                    display: flex; align-items: center; justify-content: center;
                    z-index: 10000;
                    backdrop-filter: blur(4px);
                }
                .modal-content {
                    background: var(--color-bg-secondary, #111827);
                    border: 1px solid var(--color-border, #374151);
                    border-radius: 12px;
                    width: ${size === 'large' ? '90%' : size === 'small' ? '400px' : '600px'};
                    max-width: 1200px;
                    max-height: 85vh;
                    display: flex; flex-direction: column;
                    box-shadow: 0 25px 50px rgba(0,0,0,0.5);
                }
                .modal-header {
                    display: flex; align-items: center; justify-content: space-between;
                    padding: 16px 24px;
                    border-bottom: 1px solid var(--color-border, #374151);
                }
                .modal-header h3 {
                    color: var(--color-text-primary, #f1f5f9);
                    margin: 0; font-size: 18px;
                }
                .modal-close {
                    background: none; border: none; color: #94a3b8;
                    font-size: 20px; cursor: pointer; padding: 4px 8px;
                    border-radius: 4px;
                }
                .modal-close:hover { background: rgba(255,255,255,0.1); color: #f1f5f9; }
                .modal-body {
                    padding: 24px; overflow-y: auto; flex: 1;
                    color: var(--color-text-secondary, #cbd5e1);
                }
            </style>
            <div class="modal-overlay">
                <div class="modal-content">
                    <div class="modal-header">
                        <h3>${title}</h3>
                        <button class="modal-close" aria-label="Close">&times;</button>
                    </div>
                    <div class="modal-body">
                        <slot></slot>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('wdb-modal', WdbModal);
