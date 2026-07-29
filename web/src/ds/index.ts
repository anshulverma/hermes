// Import token CSS globally
import './tokens/fonts.css';
import './tokens/colors.css';
import './tokens/status.css';
import './tokens/typography.css';
import './tokens/spacing.css';
import './tokens/radius.css';
import './tokens/elevation.css';
import './tokens/animations.css';
import './tokens/semantic.css';
import './tokens/base.css';
import './styles.css';

// Load the bundle (side effect)
import './bundle.ts';

// Type definitions for DS components
export type BadgeProps = {
  children: React.ReactNode;
  variant?: 'subtle' | 'outline' | 'solid';
  tone?: 'live' | 'ok' | 'attention' | 'danger';
  size?: 'sm' | 'md';
  style?: React.CSSProperties;
  [key: string]: any;
};

export type ButtonProps = {
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type CardProps = {
  children: React.ReactNode;
  variant?: 'default' | 'outlined';
  padding?: boolean;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type DividerProps = {
  orientation?: 'horizontal' | 'vertical';
  style?: React.CSSProperties;
  [key: string]: any;
};

export type IconButtonProps = {
  icon: string;
  variant?: 'ghost' | 'subtle' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type TableProps = {
  children: React.ReactNode;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type DialogProps = {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  title?: string;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type EmptyStateProps = {
  title: string;
  message?: string;
  icon?: string;
  action?: React.ReactNode;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type TooltipProps = {
  content: React.ReactNode;
  children: React.ReactNode;
  placement?: 'top' | 'bottom' | 'left' | 'right';
  style?: React.CSSProperties;
  [key: string]: any;
};

export type AttentionBannerProps = {
  kind: 'info' | 'warning' | 'error';
  children: React.ReactNode;
  onDismiss?: () => void;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type CrewBackdropProps = {
  theme?: string;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type CrewRowProps = {
  member: {
    id: string;
    state: string;
    resources?: { gpu?: number; cpu?: number };
    health?: any;
    current_ticket?: string;
    throughput_per_min?: number;
    last_heartbeat?: string;
  };
  onClick?: () => void;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type DrawerProps = {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  title?: string;
  width?: string;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type EventRowProps = {
  event: {
    ts: string;
    kind: string;
    message: string;
    host?: string;
    ticket_id?: string;
  };
  style?: React.CSSProperties;
  [key: string]: any;
};

export type HealthBadgeProps = {
  health: {
    reachable?: boolean;
    agent_ok?: boolean;
    auth_ok?: boolean;
    workspace_ready?: boolean;
    guard_installed?: boolean;
    latency_ms?: number;
  };
  size?: 'sm' | 'md';
  style?: React.CSSProperties;
  [key: string]: any;
};

export type KanbanColumnProps = {
  state: string;
  count: number;
  tickets: any[];
  onTicketClick?: (ticket: any) => void;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type StatTileProps = {
  label: string;
  value: string | number;
  trend?: 'up' | 'down' | 'neutral';
  delta?: string;
  icon?: string;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type StatusPillProps = {
  state: string;
  label?: string;
  size?: 'sm' | 'md';
  style?: React.CSSProperties;
  [key: string]: any;
};

export type TicketCardProps = {
  ticket: {
    id: string;
    subject: string;
    phase?: string;
    attempts?: number;
    elapsed_s?: number;
    resource_req?: string;
    host?: string;
  };
  onClick?: () => void;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type CheckboxProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  disabled?: boolean;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type InputProps = {
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  type?: string;
  disabled?: boolean;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type SelectProps = {
  options: Array<{ value: string; label: string }>;
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type SwitchProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  disabled?: boolean;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type HeaderProps = {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  style?: React.CSSProperties;
  [key: string]: any;
};

export type TabsProps = {
  tabs: Array<{ id: string; label: string; content?: React.ReactNode }>;
  activeTab?: string;
  onTabChange?: (id: string) => void;
  style?: React.CSSProperties;
  [key: string]: any;
};

// Re-export typed components from the global namespace
function getComponent<T = any>(name: string): T {
  if (typeof window === 'undefined') {
    // SSR fallback - return a stub component
    return (() => null) as any;
  }
  const ds = window.MonoDarkDashDesignSystem_66fdfe || window.DSNS;
  if (!ds || !ds[name]) {
    console.warn(`DS component "${name}" not found on window.DSNS`);
    return (() => null) as any;
  }
  return ds[name];
}

export const Badge: React.FC<BadgeProps> = getComponent('Badge');
export const Button: React.FC<ButtonProps> = getComponent('Button');
export const Card: React.FC<CardProps> = getComponent('Card');
export const Divider: React.FC<DividerProps> = getComponent('Divider');
export const IconButton: React.FC<IconButtonProps> = getComponent('IconButton');
export const Table: React.FC<TableProps> = getComponent('Table');
export const Dialog: React.FC<DialogProps> = getComponent('Dialog');
export const EmptyState: React.FC<EmptyStateProps> = getComponent('EmptyState');
export const Tooltip: React.FC<TooltipProps> = getComponent('Tooltip');
export const AttentionBanner: React.FC<AttentionBannerProps> = getComponent('AttentionBanner');
export const CrewBackdrop: React.FC<CrewBackdropProps> = getComponent('CrewBackdrop');
export const CrewRow: React.FC<CrewRowProps> = getComponent('CrewRow');
export const Drawer: React.FC<DrawerProps> = getComponent('Drawer');
export const EventRow: React.FC<EventRowProps> = getComponent('EventRow');
export const HealthBadge: React.FC<HealthBadgeProps> = getComponent('HealthBadge');
export const KanbanColumn: React.FC<KanbanColumnProps> = getComponent('KanbanColumn');
export const StatTile: React.FC<StatTileProps> = getComponent('StatTile');
export const StatusPill: React.FC<StatusPillProps> = getComponent('StatusPill');
export const TicketCard: React.FC<TicketCardProps> = getComponent('TicketCard');
export const Checkbox: React.FC<CheckboxProps> = getComponent('Checkbox');
export const Input: React.FC<InputProps> = getComponent('Input');
export const Select: React.FC<SelectProps> = getComponent('Select');
export const Switch: React.FC<SwitchProps> = getComponent('Switch');
export const Header: React.FC<HeaderProps> = getComponent('Header');
export const Tabs: React.FC<TabsProps> = getComponent('Tabs');

// Export constants
export const TICKET_STATES = getComponent('TICKET_STATES');
export const TONES = getComponent('TONES');
export const BACKDROP_THEMES = getComponent('BACKDROP_THEMES');
export const CREW_GRID = getComponent('CREW_GRID');
