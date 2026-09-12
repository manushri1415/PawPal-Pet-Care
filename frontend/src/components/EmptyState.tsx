import './EmptyState.css';

export function EmptyState({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="pp-empty-state">
      <div className="pp-empty-state__illustration" />
      <h3>{title}</h3>
      <p>{subtitle}</p>
    </div>
  );
}
