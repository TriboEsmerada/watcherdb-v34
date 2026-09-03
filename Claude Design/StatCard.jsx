import React from "react";

const STATE = {
  ok:       { border: "--sev-ok-border",       value: "--sev-ok-text" },
  info:     { border: "--sev-info-border",     value: "--text-primary" },
  warning:  { border: "--sev-warning-border",  value: "--sev-warning-text" },
  critical: { border: "--sev-critical-border", value: "--sev-critical-text" },
  overflow: { border: "--sev-overflow-border", value: "--sev-overflow-text" },
};

/**
 * KpiCard — a clickable headline metric tile for dashboards.
 * Left rail carries severity; the value color follows it. Numbers
 * render tabular so the grid never reflows on refresh.
 */
export function KpiCard({
  title,
  subtitle,
  value,
  secondary,
  state = "ok",
  icon,          // Font Awesome unicode glyph, optional
  onClick,
}) {
  const s = STATE[state] || STATE.ok;
  return (
    <div
      onClick={onClick}
      style={{
        position: "relative",
        background: "var(--surface-raised)",
        border: "1px solid var(--color-border)",
        borderLeft: `4px solid var(${s.border})`,
        borderRadius: "var(--radius-md)",
        padding: "14px 16px",
        cursor: onClick ? "pointer" : "default",
        transition: "transform var(--motion-base), border-color var(--motion-base)",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.borderColor = "var(--color-border-strong)"; e.currentTarget.style.borderLeftColor = `var(${s.border})`; }}
      onMouseLeave={(e) => { e.currentTarget.style.transform = "none"; e.currentTarget.style.borderColor = "var(--color-border)"; e.currentTarget.style.borderLeftColor = `var(${s.border})`; }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: subtitle ? 2 : 10 }}>
        <span style={{ fontSize: "var(--font-xs)", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{title}</span>
        {icon && <i className="fas" aria-hidden="true" style={{ color: "var(--text-disabled)", fontFamily: '"Font Awesome 6 Free"', fontWeight: 900, fontSize: 13 }}>{icon}</i>}
      </div>
      {subtitle && <div style={{ fontSize: 11, color: "var(--text-disabled)", marginBottom: 10 }}>{subtitle}</div>}
      <div className="wdb-num" style={{ fontSize: "var(--font-3xl)", fontWeight: 700, lineHeight: 1.1, color: `var(${s.value})` }}>{value}</div>
      {secondary && <div className="wdb-num" style={{ fontSize: "var(--font-xs)", color: "var(--text-tertiary)", marginTop: 4 }}>{secondary}</div>}
    </div>
  );
}
