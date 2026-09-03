**KpiCard** — headline metric tile for dashboard grids; severity sets the left rail and value color, numbers are tabular. **StatCard** — denser label+value cell for stat strips.

```jsx
<KpiCard title="Critical Alerts" value="7" state="critical" icon={"\uf071"} secondary="3 breached" onClick={...} />
<KpiCard title="Servers" subtitle="all environments" value="42" state="ok" />

<StatCard label="CPU" value="71" unit="%" state="warning" />
<StatCard label="Page life expectancy" value="9,910" unit="s" state="ok" />
```

States: `ok` · `info` · `warning` · `critical` · `overflow`. `icon` takes a Font Awesome unicode glyph (e.g. `"\uf071"`).
