import { useQuery } from "@tanstack/react-query";
import { Link, Route, Routes } from "react-router-dom";
import { apiGet } from "./api/client";

interface HealthzResponse {
  status: string;
}

/**
 * Phase 0 scaffolding only: proves the dev proxy + React Query plumbing work
 * end-to-end by hitting the backend's liveness route. Real scheduler/health
 * pages replace the placeholders below in Phases 2 and 4.
 */
function BackendStatus() {
  const { data, error, isLoading } = useQuery({
    queryKey: ["healthz"],
    queryFn: () => apiGet<HealthzResponse>("/api/healthz"),
  });

  if (isLoading) return <p>Checking backend…</p>;
  if (error) return <p>Backend unreachable: {(error as Error).message}</p>;
  return <p>Backend status: {data?.status}</p>;
}

function SchedulerPagePlaceholder() {
  return (
    <section>
      <h1>Scheduler</h1>
      <p>Coming in Phase 2.</p>
      <BackendStatus />
    </section>
  );
}

function HealthRecordsPagePlaceholder() {
  return (
    <section>
      <h1>Health Records</h1>
      <p>Coming in Phase 4.</p>
    </section>
  );
}

function App() {
  return (
    <>
      <nav>
        <Link to="/">Scheduler</Link> | <Link to="/health">Health Records</Link>
      </nav>
      <Routes>
        <Route path="/" element={<SchedulerPagePlaceholder />} />
        <Route path="/health" element={<HealthRecordsPagePlaceholder />} />
      </Routes>
    </>
  );
}

export default App;
