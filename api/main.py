"""FastAPI app entry point.

Phase 0 (scaffolding only): a single liveness route so the frontend and CI can
confirm the backend is reachable. Scheduler and health-records routers land in
later phases (see the migration plan) — this file will grow to mount them via
`app.include_router(...)` and, in production, to serve the built frontend
(`frontend/dist`) as static files with an SPA fallback route.
"""

from fastapi import FastAPI

app = FastAPI(title="PawPal+ API")


@app.get("/api/healthz")
def healthz() -> dict:
    """Liveness check used by the frontend dev proxy and deployment health checks."""
    return {"status": "ok"}
