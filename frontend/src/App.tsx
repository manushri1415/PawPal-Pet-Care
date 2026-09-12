import { NavLink, Route, Routes } from "react-router-dom";
import { BrandBadge } from "./components/BrandBadge";
import { SchedulerPage } from "./features/scheduler/SchedulerPage";

function HealthRecordsPagePlaceholder() {
  return (
    <section>
      <h1>Health Records</h1>
      <p>Coming in Phase 4.</p>
    </section>
  );
}

function navLinkClassName({ isActive }: { isActive: boolean }) {
  return isActive ? "pp-nav-active" : undefined;
}

function App() {
  return (
    <div className="pp-page">
      <header className="pp-page-header">
        <BrandBadge />
        <nav className="pp-nav">
          <NavLink to="/" end className={navLinkClassName}>
            Scheduler
          </NavLink>
          <NavLink to="/health" className={navLinkClassName}>
            Health Records
          </NavLink>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<SchedulerPage />} />
        <Route path="/health" element={<HealthRecordsPagePlaceholder />} />
      </Routes>
    </div>
  );
}

export default App;
