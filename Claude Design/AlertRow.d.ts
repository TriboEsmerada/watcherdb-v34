import React from "react";

const STATE = {
  ok:       { border: "--sev-ok-border",       value: "--sev-ok-text" },
  info:     { border: "--sev-info-border",     value: "--text-primary" },
  warning:  { border: "--sev-warning-border",  value: "--sev-warning-text" },
  critical: { border: "--sev-critical-border", value: "--sev-critical-text" },
  overflow: { border: "--sev-overflow-border", value: "--sev-overflow-text" },
};

/**
 * StatCard — compact label+value cell for stat strips (CPU, memory,
 * counts). Denser than KpiCard; left rail carries severity.
 */
export function StatCard({ label, value, unit, state = "info" }) {
  const s = STATE[state] || STATE.info;
  return (
    <div
      style={{
        background: "var(--surface-raised)",
        border: "1px solid var(--color-border)",
        borderLeft: `4px solid var(${s.border})`,
        borderRadius: "var(--radius-md)",
        padding: "12px 14px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        gap: 6,
        minHeight: 84,
      }}
    >
      <span style={{ fontSize: "var(--font-xs)", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</span>
      <span className="wdb-num" style={{ fontSize: "var(--font-2xl)", fontWeight: 700, lineHeight: 1.1, color: `var(${s.value})` }}>
        {value}
        {unit && <span style={{ fontSize: "var(--font-sm)", color: "var(--text-tertiary)", marginLeft: 4, fontWeight: 500 }}>{unit}</span>}
      </span>
    </div>
  );
}
