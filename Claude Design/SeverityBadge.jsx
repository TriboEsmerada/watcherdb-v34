import { ReactNode } from "react";
import { Severity } from "./SeverityBadge";

/**
 * A single alert in a triage list. Severity is encoded redundantly:
 * left rail + leading icon + title + trailing SeverityBadge.
 *
 * @startingPoint section="Severity" subtitle="Scannable alert list row" viewport="700x80"
 */
export interface AlertRowProps {
  level?: Severity;
  /** Primary alert text (e.g. "PRIMARY filegroup over capacity") */
  title: ReactNode;
  /** Mono metadata line (server · db · metric). Optional. */
  meta?: ReactNode;
  /** Override badge label; defaults to the level name */
  badgeText?: ReactNode;
  /** Optional trailing control (e.g. a copy-SQL button) */
  action?: ReactNode;
  onClick?: () => void;
}

export function AlertRow(props: AlertRowProps): JSX.Element;
