import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Backdrop } from "./components/Backdrop";
import { BrandBadge } from "./components/BrandBadge";
import { useSlidingIndicator } from "./components/useSlidingIndicator";
import { EditRoutine } from "./features/scheduler/EditRoutine";
import { SchedulerPage } from "./features/scheduler/SchedulerPage";
import { HealthRecordsPage } from "./features/health/HealthRecordsPage";

function navLinkClassName({ isActive }: { isActive: boolean }) {
  return isActive ? "pp-nav-active" : undefined;
}

function App() {
  // The plum highlight in the nav pill slides to the active link.
  const { pathname } = useLocation();
  const navRef = useSlidingIndicator<HTMLElement>(pathname, ".pp-nav-active");

  return (
    <>
      <Backdrop />
      <div className="pp-page">
        <header className="pp-page-header">
          <BrandBadge />
          <div className="pp-page-header__actions">
            <EditRoutine />
            <nav ref={navRef} className="pp-nav" aria-label="Main">
              <NavLink to="/" end className={navLinkClassName}>
                Today
              </NavLink>
              <NavLink to="/health" className={navLinkClassName}>
                Health records
              </NavLink>
            </nav>
          </div>
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
