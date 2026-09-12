import './BrandBadge.css';

export function BrandBadge({
  size = 'md',
  className,
}: {
  size?: 'sm' | 'md';
  className?: string;
}) {
  const rootClassName = ['pp-brand-badge', `pp-brand-badge--${size}`, className]
    .filter(Boolean)
    .join(' ');

  return (
    <span className={rootClassName}>
      <span className="pp-brand-badge-mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" className="pp-brand-badge-paw">
          <ellipse cx="11" cy="10" rx="2.6" ry="3.4" fill="var(--pp-surface)" />
          <ellipse cx="16" cy="7.5" rx="2.8" ry="3.6" fill="var(--pp-surface)" />
          <ellipse cx="21" cy="10" rx="2.6" ry="3.4" fill="var(--pp-surface)" />
          <ellipse cx="16" cy="19" rx="6.4" ry="5.4" fill="var(--pp-surface)" />
        </svg>
      </span>
      <span className="pp-brand-badge-word">PawPal+</span>
    </span>
  );
}
