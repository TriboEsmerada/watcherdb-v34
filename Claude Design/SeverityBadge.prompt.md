import React from "react";
import { SeverityBadge } from "./SeverityBadge.jsx";

const LEVELS = {
  ok:       { text: "--sev-ok-text",       border: "--sev-ok-border",       icon: "\uf058" },
  info:     { text: "--sev-info-text",     border: "--sev-info-border",     icon: "\uf05a" },
  warning:  { text: "--sev-warning-text",  border: "--sev-warning-border",  icon: "\uf071" },
  critical: { text: "--sev-critical-text", border: "--sev-critical-border", icon: "\uf06a" },
  overflow: { text: "--sev-overflow-text", border: "--sev-overflow-border", icon: "\uf714" },
};

/**
 * AlertRow — a single scannable alert in a stacked list.
 * Severity is encoded four ways at once: left rail, leading icon,
 * title weight, and trailing SeverityBadge. Built for fast triage.
 */
export function AlertRow({
  level = "info",
  title,
  meta,
  badgeText,
  action,
  onClick,
}) {
  const l = LEVELS[level] || LEVELS.info;

  return (
    <div
      onClick={onClick}
      style={{
        display: "grid",
        gridTemplateColumns: "4px 22px 1fr auto",
        alignItems: "center",
        gap: "12px",
        background: "var(--surface-raised)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-md)",
        padding: "10px 14px 10px 0",
        cursor: onClick ? "pointer" : "default",
        transition: "border-color var(--motion-base), background var(--motion-base)",
      }}
      onMouseEnter={(e) => { if (onClick) e.currentTarget.style.borderColor = "var(--color-border-strong)"; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--color-border)"; }}
    >
      <div style={{ alignSelf: "stretch", width: 4, background: `var(${l.border})`, borderRadius: "var(--radius-md) 0 0 var(--radius-md)" }} />
      <i className="fas" aria-hidden="true" style={{ textAlign: "center", color: `var(${l.text})`, fontFamily: '"Font Awesome 6 Free"', fontWeight: 900, fontSize: 14 }}>{l.icon}</i>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: "var(--font-sm)", fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{title}</div>
        {meta && <div className="wdb-num" style={{ fontSize: "var(--font-xs)", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)", marginTop: 2 }}>{meta}</div>}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginRight: 14 }}>
        <SeverityBadge level={level} size="sm">{badgeText}</SeverityBadge>
        {action}
      </div>
    </div>
  );
}
