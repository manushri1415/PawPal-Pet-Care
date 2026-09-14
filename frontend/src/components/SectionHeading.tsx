import './SectionHeading.css';
import type { ReactNode } from 'react';

/**
 * Human-friendly section heading: a serif title, one line of supporting
 * text, and an optional actions slot on the right. Replaces the small
 * uppercase Eyebrow labels on the dashboard. Pass `id` and point the
 * section's `aria-labelledby` at it.
 */
export function SectionHeading({
  id,
  title,
  description,
  actions,
  level = 2,
}: {
  id?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  level?: 2 | 3;
}) {
  const Heading = level === 2 ? 'h2' : 'h3';
  return (
    <div className="pp-section-heading">
      <div className="pp-section-heading__text">
        <Heading id={id} className="pp-section-heading__title">
          {title}
        </Heading>
        {description && <p className="pp-section-heading__description">{description}</p>}
      </div>
      {actions && <div className="pp-section-heading__actions">{actions}</div>}
    </div>
  );
}
