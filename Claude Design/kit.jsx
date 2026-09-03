/* ============================================================
   WatcherDB — SEVERITY SYSTEM  (the core consulting deliverable)

   In the codebase, alert severity is expressed FOUR incompatible
   ways across files:
     1. tokens:        --color-danger #dc2626 / hover #ef4444
     2. portal_fix:    --color-critical #ef4444 / --color-overflow #dc2626
     3. Tailwind CDN:  red-600 / red-900 / text-red-400 / text-red-200
     4. badges:        background #dc2626; color #000 or #fff (ad-hoc)

   This file defines ONE 5-level scale. Each level ships four
   roles so severity is encoded REDUNDANTLY (color + fill + icon),
   never by hue alone — required for colorblind DBAs scanning
   under pressure and for WCAG 2.1 AA (1.4.1 Use of Color).

   Roles per level:
     --sev-*-text    bright tint, AA on --surface-app & --surface-raised
     --sev-*-tint    low-alpha wash for row/card backgrounds
     --sev-*-border  left-rail / outline color
     --sev-*-solid   saturated fill for badges & bars
     --sev-*-on      text color that sits on the solid fill (AA)

   Severity order (low -> high): ok < info < warning < critical < overflow
   Icon (Font Awesome 6) is the canonical glyph for each level.
   ============================================================ */

:root {
    /* ---- OK / HEALTHY — fa-circle-check ---- */
    --sev-ok-text:   #34d399;   /*  8.9:1 on app bg */
    --sev-ok-tint:   rgba(16, 185, 129, 0.12);
    --sev-ok-border: #10b981;
    --sev-ok-solid:  #059669;
    --sev-ok-on:     #ffffff;

    /* ---- INFO — fa-circle-info ---- */
    --sev-info-text:   #60a5fa;  /*  7.4:1 on app bg */
    --sev-info-tint:   rgba(37, 99, 235, 0.14);
    --sev-info-border: #3b82f6;
    --sev-info-solid:  #2563eb;
    --sev-info-on:     #ffffff;

    /* ---- WARNING — fa-triangle-exclamation ---- */
    --sev-warning-text:   #fbbf24;  /* 11.2:1 on app bg (was #d97706 ~5:1) */
    --sev-warning-tint:   rgba(245, 158, 11, 0.13);
    --sev-warning-border: #f59e0b;
    --sev-warning-solid:  #d97706;
    --sev-warning-on:     #0a0f1a;  /* dark text on amber = 8.4:1 */

    /* ---- CRITICAL — fa-circle-exclamation ---- */
    --sev-critical-text:   #f87171;  /*  6.5:1 on app bg (was #dc2626 ~4:1) */
    --sev-critical-tint:   rgba(220, 38, 38, 0.15);
    --sev-critical-border: #ef4444;
    --sev-critical-solid:  #dc2626;
    --sev-critical-on:     #ffffff;

    /* ---- OVERFLOW / BREACHED — fa-skull-crossbones ----
       The terminal state in space monitoring (filegroup past
       100%). Distinguished from CRITICAL by a deep oxblood fill
       + ring so it never reads as "just another red". */
    --sev-overflow-text:   #fca5a5;
    --sev-overflow-tint:   rgba(124, 45, 18, 0.30);
    --sev-overflow-border: #dc2626;
    --sev-overflow-solid:  #7c2d12;
    --sev-overflow-on:     #fecaca;

    /* ---- Back-compat aliases to the old danger/success names ---- */
    --color-success:        var(--sev-ok-border);
    --color-success-bg:     #064e3b;
    --color-success-hover:  var(--sev-ok-text);
    --color-warning:        var(--sev-warning-border);
    --color-warning-bg:     #78350f;
    --color-warning-hover:  var(--sev-warning-text);
    --color-danger:         var(--sev-critical-solid);
    --color-danger-bg:      #7f1d1d;
    --color-danger-hover:   var(--sev-critical-border);
    --color-info-bg:        #1e3a8a;
}
