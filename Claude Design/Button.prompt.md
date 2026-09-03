import { ReactNode } from "react";

/**
 * Primary action control. Solid brand fill (no gradients), with
 * secondary / ghost / danger variants.
 *
 * @startingPoint section="Controls" subtitle="Button + variants" viewport="700x100"
 */
export interface ButtonProps {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  /** Font Awesome unicode glyph (e.g. "\uf0c7") */
  icon?: string;
  disabled?: boolean;
  children?: ReactNode;
  onClick?: () => void;
}

export function Button(props: ButtonProps): JSX.Element;
