/* ============================================================
   WatcherDB — BASE LAYER
   Minimal reset + dark canvas defaults. Kept small on purpose:
   tokens carry the system, components carry the rest.
   ============================================================ */

*, *::before, *::after { box-sizing: border-box; }
* { margin: 0; padding: 0; }

html { color-scheme: dark; }

body {
    font-family: var(--font-sans);
    font-size: var(--font-base);
    line-height: var(--line-normal);
    background: var(--surface-app);
    color: var(--text-primary);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

/* Numeric readouts: tabular, lining figures so dense tables
   and KPIs don't shift width as values tick. */
.wdb-num, [data-num] {
    font-variant-numeric: tabular-nums lining-nums;
    font-feature-settings: var(--num);
}

/* Mono utility for IDs / SQL / sizes */
.wdb-mono { font-family: var(--font-mono); }

/* Visible, consistent focus ring for keyboard-driven DBAs */
:where(a, button, input, select, textarea, [tabindex]):focus-visible {
    outline: 2px solid var(--brand-blue-bright);
    outline-offset: 2px;
    border-radius: var(--radius-sm);
}

::selection { background: rgba(96, 165, 250, 0.30); }

/* Thin dark scrollbars (the live portal hand-rolls these per
   container; centralize the default here). */
* {
    scrollbar-width: thin;
    scrollbar-color: var(--slate-600) var(--surface-sunken);
}
*::-webkit-scrollbar { width: 12px; height: 12px; }
*::-webkit-scrollbar-track { background: var(--surface-sunken); }
*::-webkit-scrollbar-thumb {
    background: var(--slate-600);
    border-radius: var(--radius-sm);
    border: 2px solid var(--surface-sunken);
}
*::-webkit-scrollbar-thumb:hover { background: var(--slate-500); }
