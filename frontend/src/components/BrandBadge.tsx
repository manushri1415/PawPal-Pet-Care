import './BrandBadge.css';
import { brandAssets } from '../assets/pets';

/**
 * The brand, wherever it appears: the official logo (symbol only — two paws)
 * beside the wordmark set in text. The logo is decorative next to the word,
 * so it carries no alt text of its own.
 */
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
      <img className="pp-brand-badge-logo" src={brandAssets.logo} alt="" draggable={false} />
      <span className="pp-brand-badge-word">PawPal+</span>
    </span>
  );
}
