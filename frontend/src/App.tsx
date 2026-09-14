import { NavLink, Route, Routes } from "react-router-dom";
import { Backdrop } from "./components/Backdrop";
import { BrandBadge } from "./components/BrandBadge";
import { SchedulerPage } from "./features/scheduler/SchedulerPage";
import { HealthRecordsPage } from "./features/health/HealthRecordsPage";

function navLinkClassName({ isActive }: { isActive: boolean }) {
  return isActive ? "pp-nav-active" : undefined;
}

function App() {
  return (
    <>
      <Backdrop />
      <div className="pp-page">
        <header className="pp-page-header">
          <BrandBadge />
          <nav className="pp-nav" aria-label="Main">
            <NavLink to="/" end className={navLinkClassName}>
              Today
            </NavLink>
            <NavLink to="/health" className={navLinkClassName}>
              Health records
            </NavLink>
          </nav>
        </header>
        <Routes>
          <Route path="/" element={<SchedulerPage />} />
          <Route path="/health" element={<HealthRecordsPage />} />
        </Routes>
      </div>
    </>
  );
}

export default App;
