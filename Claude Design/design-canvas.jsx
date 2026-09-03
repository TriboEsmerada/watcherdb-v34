<!-- @dsCard group="Spacing" viewport="700x150" name="Radii & elevation" subtitle="Corner radii and dark-tuned shadow ramp" -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<link rel="stylesheet" href="../styles.css">
<style>
  body { padding: 22px; background: var(--surface-app); display: flex; gap: 26px; align-items: center; }
  .grp { display: flex; gap: 16px; align-items: center; }
  .r { width: 60px; height: 60px; background: var(--surface-panel); border: 1px solid var(--color-border); display: grid; place-items: end center; padding-bottom: 4px; }
  .e { width: 76px; height: 60px; background: var(--surface-raised); border-radius: var(--radius-md); display: grid; place-items: end center; padding-bottom: 4px; }
  .k { font-family: var(--font-mono); font-size: 10px; color: var(--text-tertiary); }
  .div { width: 1px; height: 64px; background: var(--color-border); }
</style>
</head>
<body>
  <div class="grp">
    <div class="r" style="border-radius:var(--radius-sm)"><span class="k">sm 4</span></div>
    <div class="r" style="border-radius:var(--radius-md)"><span class="k">md 8</span></div>
    <div class="r" style="border-radius:var(--radius-lg)"><span class="k">lg 12</span></div>
  </div>
  <div class="div"></div>
  <div class="grp">
    <div class="e" style="box-shadow:var(--shadow-sm)"><span class="k">sm</span></div>
    <div class="e" style="box-shadow:var(--shadow-md)"><span class="k">md</span></div>
    <div class="e" style="box-shadow:var(--shadow-lg)"><span class="k">lg</span></div>
    <div class="e" style="box-shadow:var(--shadow-xl)"><span class="k">xl</span></div>
  </div>
</body>
</html>
