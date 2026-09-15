import './Tabs.css';

export interface TabItem {
  id: string;
  label: string;
}

/** Simple, self-contained tab strip — the active tab is fully controlled by
 * the parent (no internal state) so a page can keep tab content mounted or
 * not as it prefers. Introduced for HealthRecordsPage's five sections; the
 * scheduler page has no analogous need for it. */
export function Tabs({
  items,
  activeId,
  onChange,
}: {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="pp-tabs" role="tablist">
      {items.map((item) => (
        <button
          key={item.id}
          id={`tab-${item.id}`}
          type="button"
          role="tab"
          aria-selected={item.id === activeId}
          aria-controls={`panel-${item.id}`}
          tabIndex={item.id === activeId ? 0 : -1}
          className={
            item.id === activeId ? 'pp-tabs__tab pp-tabs__tab--active' : 'pp-tabs__tab'
          }
          onClick={() => onChange(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
