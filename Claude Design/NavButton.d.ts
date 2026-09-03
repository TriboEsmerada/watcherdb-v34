import React from "react";

/**
 * Button — primary action control. The live portal used gradient
 * fills ad-hoc; this flattens to a solid brand fill (calmer, better
 * contrast) with secondary/ghost/danger variants.
 */
export function Button({
  variant = "primary",  // primary | secondary | ghost | danger
  size = "md",          // sm | md
  icon,                 // Font Awesome unicode glyph
  children,
  disabled,
  onClick,
  ...rest
}) {
  const pad = size === "sm" ? "6px 12px" : "8px 16px";
  const fs = size === "sm" ? "var(--font-xs)" : "var(--font-sm)";

  const skins = {
    primary:   { background: "var(--brand-blue)",  color: "#fff",                 border: "1px solid transparent" },
    secondary: { background: "var(--slate-600)",   color: "var(--text-primary)",  border: "1px solid transparent" },
    ghost:     { background: "transparent",        color: "var(--text-secondary)",border: "1px solid var(--color-border)" },
    danger:    { background: "var(--sev-critical-solid)", color: "#fff",          border: "1px solid transparent" },
  };
  const hovers = {
    primary: "var(--brand-blue-hover)",
    secondary: "var(--slate-500)",
    ghost: "var(--surface-hover)",
    danger: "var(--sev-critical-border)",
  };
  const skin = skins[variant] || skins.primary;

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: pad,
        fontSize: fs,
        fontWeight: 600,
        fontFamily: "inherit",
        borderRadius: "var(--radius-md)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: "background var(--motion-fast)",
        ...skin,
      }}
      onMouseEnter={(e) => { if (!disabled) e.currentTarget.style.background = hovers[variant] || hovers.primary; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = skin.background; }}
      {...rest}
    >
      {icon && <i className="fas" aria-hidden="true" style={{ fontFamily: '"Font Awesome 6 Free"', fontWeight: 900, fontSize: "0.9em" }}>{icon}</i>}
      {children}
    </button>
  );
}
