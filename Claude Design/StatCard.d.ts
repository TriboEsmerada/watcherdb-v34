import { ReactNode } from "react";
import { Severity } from "../severity/SeverityBadge";

/**
 * Headline metric tile for dashboard grids. Severity drives the left
 * rail and the value color. Values are tabular to prevent reflow.
 *
 * @startingPoint section="Data" subtitle="Dashboard KPI tile" viewport="320x140"
 */
export interface KpiCardProps {
  /** Short uppercase label */
  title: ReactNode;
  /** Optional second line under the title */
  subtitle?: ReactNode;
  /** The headline number/string */
  value: ReactNode;
  /** Optional smaller line under the value */
  secondary?: ReactNode;
  /** Severity state — sets rail + value color (default "ok") */
  state?: Severity;
  /** Font Awesome unicode glyph shown top-right */
  icon?: string;
  onClick?: () => void;
}

export function KpiCard(props: KpiCardProps): JSX.Element;
