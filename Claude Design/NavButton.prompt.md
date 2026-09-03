/**
 * Server-detail tab button (Overview, Backup, Space, CPU…).
 * Outlined when idle, brand-tinted when active.
 */
export interface NavButtonProps {
  /** Font Awesome unicode glyph */
  icon?: string;
  label: string;
  active?: boolean;
  onClick?: () => void;
}

export function NavButton(props: NavButtonProps): JSX.Element;
