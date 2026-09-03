**Button** — primary action control, solid brand fill (no gradients). **NavButton** — the server-detail tab button.

```jsx
<Button variant="primary" icon={"\uf0c7"}>Run backup</Button>
<Button variant="secondary">Cancel</Button>
<Button variant="ghost" size="sm">Export</Button>
<Button variant="danger" icon={"\uf1f8"}>Drop</Button>

<NavButton icon={"\uf015"} label="Overview" active />
<NavButton icon={"\uf0a0"} label="Space" />
```

`icon` takes a Font Awesome unicode glyph; Font Awesome 6 must be loaded.
