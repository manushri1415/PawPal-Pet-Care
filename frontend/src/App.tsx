import { useEffect } from "react";
import { Link, Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Backdrop } from "./components/Backdrop";
import { BrandBadge } from "./components/BrandBadge";
import { useSlidingIndicator } from "./components/useSlidingIndicator";
import { EditRoutine } from "./features/scheduler/EditRoutine";
import { SchedulerPage } from "./features/scheduler/SchedulerPage";
import { HealthRecordsPage } from "./features/health/HealthRecordsPage";
import { LandingPage } from "./features/landing/LandingPage";
import { SessionBanner } from "./features/session/SessionBanner";
import { SessionGate, useSession } from "./features/session/SessionGate";

function navLinkClassName({ isActive }: { isActive: boolean }) {
  return isActive ? "pp-nav-active" : undefined;
}

/** The app proper under /app: top bar with the nav pill, then the page. */
function AppShell() {
  // The plum highlight in the nav pill slides to the active link.
  const { pathname } = useLocation();
  const navRef = useSlidingIndicator<HTMLElement>(pathname, ".pp-nav-active");
  // Nothing that reads app data renders before the session exists (SessionGate).
  const sessionReady = useSession().isSuccess;

  return (
    <>
      <Backdrop />
      <div className="pp-page">
        <header className="pp-page-header">
          <Link to="/" className="pp-page-header__brand" aria-label="PawPal+ front page">
            <BrandBadge />
          </Link>
          <div className="pp-page-header__actions">
            {sessionReady && <EditRoutine />}
            <nav ref={navRef} className="pp-nav" aria-label="Main">
              <NavLink to="/app" end className={navLinkClassName}>
                Today
              </NavLink>
              <NavLink to="/app/health" className={navLinkClassName}>
                Health records
              </NavLink>
            </nav>
          </div>
        </header>
        <SessionGate>
          <SessionBanner />
          <Outlet />
        </SessionGate>
      </div>
    </>
  );
}

/** Start each page at the top — the landing page hands over scrolled to its foot. */
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/app" element={<AppShell />}>
          <Route index element={<SchedulerPage />} />
          <Route path="health" element={<HealthRecordsPage />} />
        </Route>
        {/* Where Health Records lived before the landing page took the root. */}
        <Route path="/health" element={<Navigate to="/app/health" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default App;
