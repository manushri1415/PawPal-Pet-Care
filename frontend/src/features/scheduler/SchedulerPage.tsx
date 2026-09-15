import './SchedulerPage.css';
import { DashboardGreeting } from './DashboardGreeting';
import { OverlapBanner } from './OverlapBanner';
import { ScheduleView } from './ScheduleView';
import { PetList } from './PetList';
import { TaskList } from './TaskList';

/**
 * The daily dashboard, ordered by what matters every day: greeting and
 * overview (with the routine at a glance), then Today's schedule beside Your
 * pets, then Today's tasks. Routine settings are edited from the top bar
 * (features/scheduler/EditRoutine.tsx). Every child is self-contained (own
 * React Query fetching/mutations, zero required props), so this component is
 * pure layout.
 */
export function SchedulerPage() {
  return (
    <div className="pp-dashboard">
      <DashboardGreeting />
      <OverlapBanner />

      <div className="pp-dashboard__top">
        <ScheduleView />
        <PetList />
      </div>

      <TaskList />
    </div>
  );
}
