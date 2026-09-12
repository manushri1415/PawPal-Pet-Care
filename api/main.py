"""FastAPI app entry point.

Phase 0 scaffolded a single liveness route. Phase 1 added the scheduler
routers (owner/pets/tasks/schedule). Phase 3 adds the health-records router
(see MIGRATION_PLAN.md). Production static/SPA serving (`frontend/dist`) as
static files with a catch-all fallback route lands in the cutover phase (5).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.deps import get_health_storage, get_scheduler_storage
from api.routers import health, owner, pets, schedule, tasks


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Eagerly construct both storage singletons, sequentially, before the app
    # accepts traffic. Left lazy (built on first request instead), the two
    # `@lru_cache`d singletons get constructed concurrently -- FastAPI resolves
    # sync dependencies in separate threadpool threads -- the moment a request
    # needs both at once (e.g. GET /api/owner, whose service also depends on
    # health_storage for its record counter). Against a brand-new database
    # file, each connection's initial `PRAGMA journal_mode = WAL` can then
    # race the other's, occasionally raising `sqlite3.OperationalError:
    # database is locked` on that very first request (caught via a smoke test
    # against a fresh db during Phase 4). Building them here, one at a time,
    # removes the race.
    get_scheduler_storage()
    get_health_storage()
    yield


app = FastAPI(title="PawPal+ API", lifespan=lifespan)

app.include_router(owner.router)
app.include_router(pets.router)
app.include_router(tasks.router)
app.include_router(schedule.router)
app.include_router(health.router)


@app.get("/api/healthz")
def healthz() -> dict:
    """Liveness check used by the frontend dev proxy and deployment health checks."""
    return {"status": "ok"}
