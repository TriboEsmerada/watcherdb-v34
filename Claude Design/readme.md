// Overview dashboard — KPI grid + critical alerts feed.
function OverviewDashboard() {
  const { KpiCard, AlertRow, Button } = window.WDBKit;
  const d = window.WDB_DATA;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-md)" }}>
      {/* KPI grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--space-sm)" }}>
        {d.kpis.map((k, i) => (
          <KpiCard key={i} title={k.title} subtitle={k.subtitle} value={k.value}
                   secondary={k.secondary} state={k.state} icon={k.icon} onClick={() => {}} />
        ))}
      </div>

      {/* Alerts feed */}
      <section>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-sm)" }}>
          <h3 style={{ fontSize: "var(--font-xl)", fontWeight: 700, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: 10 }}>
            <i className="fas fa-bell" style={{ color: "var(--sev-critical-text)", fontSize: 16 }}></i>
            Alertas ativos
            <span style={{ fontSize: "var(--font-xs)", fontWeight: 600, color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>· auto-refresh 60s</span>
          </h3>
          <Button variant="ghost" size="sm" icon={"fa-arrows-rotate"}>Atualizar</Button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {d.alerts.map((a, i) => (
            <AlertRow key={i} level={a.level} title={a.title} meta={a.meta} badgeText={a.badge}
              action={<button title="Copiar SQL" style={{ background: "transparent", border: "1px solid var(--color-border)", color: "var(--text-link)", borderRadius: "var(--radius-sm)", padding: "5px 9px", cursor: "pointer", fontSize: 12 }}><i className="fas fa-copy"></i></button>}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
window.OverviewDashboard = OverviewDashboard;
