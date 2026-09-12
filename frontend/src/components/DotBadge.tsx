import './DotBadge.css';
import type { Priority } from '../api/types';

export const PRIORITY_COLORS: Record<Priority, string> = {
  high: 'var(--pp-terracotta)',
  medium: 'var(--pp-ochre)',
  low: 'var(--pp-sage)',
};

export function DotBadge({ label, color }: { label: string; color: string }) {
  return (
    <span className="pp-dot-badge" style={{ color }}>
      <span className="pp-dot-badge-dot" style={{ background: color }} />
      {label}
    </span>
  );
}
