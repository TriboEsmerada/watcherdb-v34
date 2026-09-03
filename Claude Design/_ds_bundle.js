/* ============================================================
   WatcherDB — TYPOGRAPHY

   On-prem DBA tool: a native system UI stack is intentional (no
   webfont download, instant first paint, OS-native legibility).
   The stack resolves to whatever each OS ships — San Francisco on
   macOS/iOS, Segoe UI on Windows, system-ui elsewhere — so no font
   files are required to ship.

   Mono is load-bearing: server IDs, SQL, sizes, paths. We rely on
   the OS-native monospaced face (ui-monospace → SF Mono / Consolas /
   Monaco) for column alignment in dense tables.

   NOTE: if you later want a *branded* face (e.g. Inter for sans or
   Cascadia Code for mono), upload the font file and add an
   @font-face here, then prepend the family to the relevant stack.
   We deliberately do NOT name an unresolved webfont in the stack —
   that was the kind of silent gap this system corrects.
   ============================================================ */

:root {
    --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                 system-ui, sans-serif;
    --font-mono: ui-monospace, 'SF Mono', 'Consolas', 'Monaco', monospace;

    /* Modular scale (1.25 — Major Third). Floor is 12px: dense,
       but never below readable for long DBA sessions. */
    --font-xs:   0.75rem;    /* 12px — badges, metadata, table chrome */
    --font-sm:   0.875rem;   /* 14px — labels, buttons, table body */
    --font-base: 1rem;       /* 16px — body */
    --font-lg:   1.125rem;   /* 18px — card titles */
    --font-xl:   1.25rem;    /* 20px — section titles */
    --font-2xl:  1.5rem;     /* 24px — view headers */
    --font-3xl:  1.875rem;   /* 30px — KPI numbers */
    --font-4xl:  2.25rem;    /* 36px — hero metric */

    --line-tight:   1.25;  /* @kind other */
    --line-normal:  1.5;   /* @kind other */
    --line-relaxed: 1.75;  /* @kind other */

    --weight-normal:   400; /* @kind other */
    --weight-medium:   500; /* @kind other */
    --weight-semibold: 600; /* @kind other */
    --weight-bold:     700; /* @kind other */

    /* Tabular figures: KPIs, sizes, counts must not jitter as
       they update. Apply --num to any live numeric readout. */
    --num: "tnum" 1, "lnum" 1; /* @kind other */
}
