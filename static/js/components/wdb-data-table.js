/**
 * <wdb-data-table> — Sortable, filterable data table
 *
 * Usage:
 *   <wdb-data-table
 *     columns='["Name","Status","Score"]'
 *     sortable
 *     filterable>
 *   </wdb-data-table>
 *
 *   document.querySelector('wdb-data-table').data = [{...}, ...];
 */
class WdbDataTable extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this._data = [];
        this._sortCol = -1;
        this._sortAsc = true;
        this._filter = '';
    }

    static get observedAttributes() {
        return ['columns'];
    }

    get data() { return this._data; }
    set data(val) {
        this._data = Array.isArray(val) ? val : [];
        this.render();
    }

    get columns() {
        try { return JSON.parse(this.getAttribute('columns') || '[]'); }
        catch { return []; }
    }

    connectedCallback() { this.render(); }
    attributeChangedCallback() { this.render(); }

    _sort(colIdx) {
        if (this._sortCol === colIdx) {
            this._sortAsc = !this._sortAsc;
        } else {
            this._sortCol = colIdx;
            this._sortAsc = true;
        }
        this.render();
    }

    _getFilteredSorted() {
        let rows = [...this._data];
        const cols = this.columns;

        // Filter
        if (this._filter) {
            const q = this._filter.toLowerCase();
            rows = rows.filter(row =>
                cols.some(col => String(row[col] ?? '').toLowerCase().includes(q))
            );
        }

        // Sort
        if (this._sortCol >= 0 && this._sortCol < cols.length) {
            const key = cols[this._sortCol];
            rows.sort((a, b) => {
                const va = a[key] ?? '', vb = b[key] ?? '';
                const cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb));
                return this._sortAsc ? cmp : -cmp;
            });
        }
        return rows;
    }

    render() {
        const cols = this.columns;
        const rows = this._getFilteredSorted();
        const filterable = this.hasAttribute('filterable');

        this.shadowRoot.innerHTML = `
            <style>
                :host { display: block; }
                .table-container { overflow-x: auto; border-radius: 8px; border: 1px solid var(--color-border, #374151); }
                ${filterable ? `
                .filter-input {
                    width: 100%; padding: 8px 12px; margin-bottom: 8px;
                    background: var(--color-bg-tertiary, #1e293b); color: var(--color-text-primary, #f1f5f9);
                    border: 1px solid var(--color-border, #374151); border-radius: 6px;
                    font-size: 14px;
                }` : ''}
                table { width: 100%; border-collapse: collapse; font-size: 13px; }
                th {
                    background: var(--color-bg-tertiary, #1e293b);
                    color: var(--color-text-secondary, #94a3b8);
                    padding: 10px 12px; text-align: left;
                    font-weight: 600; cursor: pointer; user-select: none;
                    border-bottom: 2px solid var(--color-border, #374151);
                    white-space: nowrap;
                }
                th:hover { color: var(--color-text-primary, #f1f5f9); }
                th .sort-icon { margin-left: 4px; font-size: 10px; }
                td {
                    padding: 8px 12px; color: var(--color-text-primary, #f1f5f9);
                    border-bottom: 1px solid rgba(55,65,81,0.5);
                }
                tr:hover td { background: rgba(59,130,246,0.05); }
                .empty { text-align: center; padding: 24px; color: #64748b; }
            </style>
            ${filterable ? `<input class="filter-input" placeholder="Filter..." value="${this._filter}">` : ''}
            <div class="table-container">
                <table>
                    <thead><tr>
                        ${cols.map((col, i) => `
                            <th data-col="${i}">
                                ${col}
                                <span class="sort-icon">${this._sortCol === i ? (this._sortAsc ? '\u25B2' : '\u25BC') : ''}</span>
                            </th>
                        `).join('')}
                    </tr></thead>
                    <tbody>
                        ${rows.length === 0 ? `<tr><td colspan="${cols.length}" class="empty">No data</td></tr>` :
                          rows.map(row => `<tr>${cols.map(col => `<td>${row[col] ?? ''}</td>`).join('')}</tr>`).join('')}
                    </tbody>
                </table>
            </div>
        `;

        // Event listeners
        if (filterable) {
            this.shadowRoot.querySelector('.filter-input')?.addEventListener('input', (e) => {
                this._filter = e.target.value;
                this.render();
            });
        }
        this.shadowRoot.querySelectorAll('th').forEach(th => {
            th.addEventListener('click', () => this._sort(parseInt(th.dataset.col)));
        });
    }
}

customElements.define('wdb-data-table', WdbDataTable);
