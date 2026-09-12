"""FastAPI app entry point.

Phase 0 scaffolded a single liveness route. Phase 1 added the scheduler
routers (owner/pets/tasks/schedule). Phase 3 adds the health-records router
(see MIGRATION_PLAN.md). Production static/SPA serving (`frontend/dist`) as
static files with a catch-all fallback route lands in the cutover phase (5).
"""

from fastapi import FastAPI

from api.routers import health, owner, pets, schedule, tasks

app = FastAPI(title="PawPal+ API")

app.include_router(owner.router)
app.include_router(pets.router)
app.include_router(tasks.router)
app.include_router(schedule.router)
app.include_router(health.router)


@app.get("/api/healthz")
def healthz() -> dict:
    """Liveness check used by the frontend dev proxy and deployment health checks."""
    return {"status": "ok"}
