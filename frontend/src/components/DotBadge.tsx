import './DotBadge.css';
import type { CareStatus, Priority } from '../api/types';

export const PRIORITY_COLORS: Record<Priority, string> = {
  high: 'var(--pp-terracotta)',
  medium: 'var(--pp-ochre)',
  low: 'var(--pp-sage)',
};

// Same three hues as PRIORITY_COLORS, so "urgent / soon / settled" reads
// consistently between the scheduler and health-records feature.
export const CARE_STATUS_COLORS: Record<CareStatus, string> = {
  overdue: 'var(--pp-terracotta)',
  due_soon: 'var(--pp-ochre)',
  current: 'var(--pp-sage)',
  unknown: 'var(--pp-ink-soft)',
};

export const CARE_STATUS_LABELS: Record<CareStatus, string> = {
  overdue: 'Overdue',
  due_soon: 'Due soon',
  current: 'Current',
  unknown: 'Unknown',
};

export function DotBadge({ label, color }: { label: string; color: string }) {
  return (
    <span className="pp-dot-badge" style={{ color }}>
      <span className="pp-dot-badge-dot" style={{ background: color }} />
      {label}
    </span>
  );
}
