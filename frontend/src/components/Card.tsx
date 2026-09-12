import './Card.css';
import type { ReactNode } from 'react';

type CardTone = 'lavender' | 'sage' | 'plain';

export function Card({
  tone = 'plain',
  ruled = false,
  className,
  children,
}: {
  tone?: CardTone;
  ruled?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const rootClassName = ['pp-card', `pp-card--${tone}`, ruled && 'pp-card--ruled', className]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={rootClassName}>
      <div className="pp-card__content">{children}</div>
    </div>
  );
}
