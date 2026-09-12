import './Eyebrow.css';

export function Eyebrow({
  label,
  tone = 'lavender',
  large = false,
}: {
  label: string;
  tone?: 'lavender' | 'sage' | 'terracotta';
  large?: boolean;
}) {
  const className = [
    'pp-eyebrow',
    `pp-eyebrow--${tone}`,
    large ? 'pp-eyebrow--large' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <span className={className}>
      <span className="pp-eyebrow-dot" aria-hidden="true" />
      {label}
    </span>
  );
}
