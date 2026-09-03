// Sidebar — server list. Uses redundant status encoding (dot + env chip).
const ENV_COLOR = {
  PRD: "var(--sev-critical-border)",
  QLT: "var(--sev-warning-border)",
  TST: "var(--sev-info-border)",
};
const STATUS_DOT = {
  ok: "var(--sev-ok-border)",
  warning: "var(--sev-warning-border)",
  critical: "var(--sev-critical-border)",
};

function Sidebar({ servers, activeId, onSelect }) {
  const count = servers.length;
  return (
    <aside style={{
      width: "var(--sidebar-width)", minWidth: "var(--sidebar-width)",
      background: "var(--surface-raised)", borderRight: "1px solid var(--color-border)",
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "12px 16px", color: "var(--text-tertiary)", fontSize: "var(--font-xs)",
        fontWeight: 700, letterSpacing: ".06em", borderBottom: "1px solid var(--color-border)",
      }}>
        <span>SERVIDORES ({count})</span>
        <i className="fas fa-chevron-down" style={{ opacity: .6, color: "var(--brand-blue-bright)" }}></i>
      </div>
      <div style={{ overflowY: "auto", padding: 8, display: "flex", flexDirection: "column", gap: 4 }}>
        {servers.map((s) => {
          const active = s.id === activeId;
          return (
            <button key={s.id} onClick={() => onSelect(s.id)} style={{
              textAlign: "left", cursor: "pointer", fontFamily: "inherit",
              padding: "10px 12px", borderRadius: "var(--radius-sm)",
              background: active ? "var(--surface-hover)" : "transparent",
              border: "1px solid transparent",
              borderLeft: active ? "4px solid var(--brand-blue)" : "4px solid transparent",
              transition: "background var(--motion-fast)",
              display: "flex", alignItems: "center", gap: 10,
            }}
            onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = "var(--surface-hover)"; }}
            onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = "transparent"; }}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                background: STATUS_DOT[s.status], boxShadow: `0 0 0 3px color-mix(in srgb, ${STATUS_DOT[s.status]} 22%, transparent)`,
              }}></span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", fontSize: "var(--font-sm)", fontWeight: 600, color: "var(--text-primary)" }}>{s.id}</span>
                <span style={{ display: "block", fontSize: "var(--font-xs)", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.engine}</span>
              </span>
              <span style={{
                fontSize: 10, fontWeight: 700, letterSpacing: ".04em",
                padding: "2px 7px", borderRadius: "var(--radius-sm)",
                color: ENV_COLOR[s.env], border: `1px solid ${ENV_COLOR[s.env]}`,
                background: "color-mix(in srgb, " + ENV_COLOR[s.env] + " 12%, transparent)",
              }}>{s.env}</span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
window.Sidebar = Sidebar;
