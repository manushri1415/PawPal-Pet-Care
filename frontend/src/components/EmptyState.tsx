import './EmptyState.css';
import type { ReactNode } from 'react';

export function EmptyState({ title, subtitle }: { title: string; subtitle: ReactNode }) {
  return (
    <div className="pp-empty-state">
      <div className="pp-empty-state__illustration" />
      <h3>{title}</h3>
      <p>{subtitle}</p>
    </div>
  );
}
