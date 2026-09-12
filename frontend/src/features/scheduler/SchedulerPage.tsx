import { OverlapBanner } from './OverlapBanner';
import { OwnerProfileForm } from './OwnerProfileForm';
import { ScheduleView } from './ScheduleView';
import { PetList } from './PetList';
import { TaskList } from './TaskList';

/**
 * Composes the scheduler feature components built in Phase 2. Every child
 * here is fully self-contained (own React Query fetching/mutations, zero
 * required props) — this component is pure layout. See MIGRATION_PLAN.md §5:
 * a native React redesign, not a port of app.py's Streamlit layout.
 */
export function SchedulerPage() {
  return (
    <div className="pp-scheduler-page">
      <h1>Scheduler</h1>

      <div className="pp-section">
        <OverlapBanner />
      </div>

      <div className="pp-grid-2 pp-section">
        <OwnerProfileForm />
        <ScheduleView />
      </div>

      <div className="pp-section">
        <PetList />
      </div>

      <div className="pp-section">
        <TaskList />
      </div>
    </div>
  );
}
