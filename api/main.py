"""FastAPI app entry point.

Phase 0 scaffolded a single liveness route. Phase 1 added the scheduler
routers (owner/pets/tasks/schedule). Phase 3 added the health-records router.
Phase 5 (cutover) adds production serving of the built frontend: `npm run
build` writes `frontend/dist`, this app serves it, and the whole product runs
as one process on one port -- which is also why no CORS middleware exists
anywhere (see MIGRATION_PLAN.md §6).

The app is assembled by `create_app()` rather than at module scope so tests can
point a *real* app -- all five routers included -- at a fake dist in tmp_path
(tests/test_spa_serving.py). The module-level `app` below, which
`uvicorn api.main:app` and every existing test import, is just the default
instance of it.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from api.backend import get_storage_backend, storage_backend_kind
from api.origin import OriginVerifyMiddleware, origin_verify_required
from api.routers import health, owner, pets, schedule, session, tasks
from api.sessions import SessionCookieMiddleware
from pawpal_ai.config import get_settings

# uvicorn attaches handlers to this logger, so a warning sent here reaches the
# terminal and `docker logs`. pawpal_ai's structured log is the wrong channel
# for anything operational: it writes to a rotating file inside the container,
# which is discarded along with the container.
_log = logging.getLogger("uvicorn.error")

# Derived from this file's location, never Path.cwd(): uvicorn is started from
# a systemd unit, a Docker WORKDIR or an editor at least as often as from the
# repo root, and a cwd-relative path would not raise there -- it would silently
# fall into API-only mode and serve a blank site from a perfectly good build.
_REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = _REPO_ROOT / "frontend" / "dist"

# Everything outside these prefixes is reserved for the SPA (MIGRATION_PLAN.md §3).
# Both are machine-facing -- /api is the JSON surface, /assets the fingerprinted
# bundles -- so neither may ever fall back to index.html (_reject_reserved_path).
_API_PREFIX = "api"
_ASSETS_PREFIX = "assets"

# Content types are guessed from the file extension, and on Windows `mimetypes`
# seeds that table from the registry -- which on this machine answers
# text/plain for .mjs and nothing at all for .woff2. A module script served as
# text/plain is refused outright by the browser, so pin the handful of types a
# Vite build actually emits instead of inheriting whatever the host OS believes.
for _extension, _content_type in (
    (".js", "text/javascript"),
    (".mjs", "text/javascript"),
    (".css", "text/css"),
    (".json", "application/json"),
    (".map", "application/json"),
    (".svg", "image/svg+xml"),
    (".woff", "font/woff"),
    (".woff2", "font/woff2"),
    (".webmanifest", "application/manifest+json"),
):
    mimetypes.add_type(_content_type, _extension)

# Vite fingerprints everything under assets/ (app-abc123.js), so those URLs can
# never change meaning and are safe to keep for a year. index.html is the exact
# opposite: it is the one file that names the current hashes, so a cached copy
# goes on requesting bundles that the next deploy has already deleted -- a
# blank page until the user thinks to hard-refresh. It must be revalidated on
# every load, and so must the un-fingerprinted root files Vite copies from
# public/ (favicon.ico, favicon.png, ...), which change in place under a stable name.
_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
_REVALIDATE_CACHE_CONTROL = "no-cache"


def _warn_if_database_is_new(db_path: Path) -> None:
    """Say so, loudly, when the app is about to create its database from nothing.

    On a first run that is expected. It is also exactly what a deployment that
    is losing its data looks like, and nothing else would ever mention it: the
    Dockerfile declares /app/data a VOLUME, but `docker run` without `-v`
    attaches a fresh anonymous volume to every new container, so each one boots
    onto an empty database and serves it without complaint. Checking for the
    file catches that on any host, not only Docker, because every boot that has
    lost its data is a boot that finds no database file.
    """
    if db_path.exists():
        return
    _log.warning(
        "No database at %s -- starting with a new, empty database. That is expected "
        "on a first run. If this deployment should already have data, its data "
        "directory is not being persisted: under Docker, mount a named volume at "
        "/app/data (docker run -v pawpal-data:/app/data ...).",
        db_path,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Before the backend below, never after: constructing it creates the
    # database file, and then there is nothing left to detect. Only a SQLite
    # deployment has a file that can silently go missing.
    if storage_backend_kind() == "sqlite":
        _warn_if_database_is_new(Path(get_settings().db_path))

    # Construct the storage backend before the app accepts traffic, rather
    # than lazily inside the first request's threadpool thread: its schema
    # creation and migrations then run exactly once, before any request can
    # race them.
    get_storage_backend()
    yield


class _FingerprintedStaticFiles(StaticFiles):
    """StaticFiles for content-hashed bundles, stamped immutable.

    Subclassing is the only hook StaticFiles offers for per-response headers.
    `file_response` is also the path it takes for conditional requests, so 304s
    carry the same header as the 200 that seeded them. The signature is left
    open because it is Starlette-internal and has changed shape before.
    """

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = _IMMUTABLE_CACHE_CONTROL
        return response


def _resolve_within(root: Path, relative_path: str) -> Optional[Path]:
    """Resolve `relative_path` under `root`; return None if it escapes.

    The ASGI scope path arrives percent-decoded, so a request for
    "/%2e%2e%2fsecret.txt" reaches us as the literal "../secret.txt" -- clients
    collapse dot segments only in their *unencoded* form, so the join really
    can point anywhere on disk. On Windows "/C:/Windows/win.ini" is worse
    still: pathlib drops `root` entirely when the right-hand side names a
    drive. Comparing the fully resolved candidate against the resolved root
    catches both, and symlinks out of the tree along with them.
    """
    try:
        candidate = (root / relative_path).resolve()
    except (OSError, ValueError):
        # Reserved characters, over-long names or an embedded NUL: Windows
        # raises here rather than returning a path that merely does not exist.
        return None
    if not candidate.is_relative_to(root):
        return None
    return candidate


def _reject_unknown_api_path(full_path: str) -> None:
    """Keep /api/* out of the SPA fallback -- it 404s as JSON instead.

    An unmatched /api path is always a bug (a typo in a fetch, a renamed
    endpoint), never a client-side route, and index.html at 200 is the worst
    possible answer: the caller's `response.json()` then dies on
    "Unexpected token '<'", which points at the parsing code instead of the
    missing endpoint and costs an hour in the wrong layer.
    """
    if full_path == _API_PREFIX or full_path.startswith(f"{_API_PREFIX}/"):
        raise HTTPException(status_code=404, detail="Not Found")


def _reject_reserved_path(full_path: str) -> None:
    """As above, and the same for /assets.

    A path under /assets names a fingerprinted bundle, never a client-side
    route. It normally never reaches the fallback at all because the StaticFiles
    mount claims it first -- but it does when the build shipped no assets/
    directory, and answering a .js request with index.html at 200 produces
    "Unexpected token '<'" in the browser console, which says nothing about the
    bundle being absent.
    """
    _reject_unknown_api_path(full_path)
    if full_path == _ASSETS_PREFIX or full_path.startswith(f"{_ASSETS_PREFIX}/"):
        raise HTTPException(status_code=404, detail="Not Found")


def _register_spa_routes(app: FastAPI, dist_dir: Path) -> None:
    """Serve the built frontend from `dist_dir`, or explain that it is missing.

    Called last, after every /api router and after FastAPI's own /docs and
    /openapi.json, because Starlette matches routes in registration order: a
    catch-all registered earlier would shadow all of them.
    """
    dist_root = dist_dir.resolve()
    index_html = dist_root / "index.html"

    if not index_html.is_file():
        _register_api_only_routes(app)
        return

    # An assets/ directory is not guaranteed -- a tiny build can inline
    # everything -- so mount it only when it is really there. `check_dir=False`
    # is not a substitute: it moves StaticFiles' existence check from
    # construction to request time rather than removing it, so an index.html
    # shipped without an assets/ sibling answered every /assets/* request with
    # a 500 (RuntimeError: StaticFiles directory ... does not exist). When the
    # mount is absent, _reject_reserved_path keeps those paths a JSON 404
    # instead of letting the catch-all answer a .js request with HTML.
    assets_dir = dist_root / _ASSETS_PREFIX
    if assets_dir.is_dir():
        app.mount(
            f"/{_ASSETS_PREFIX}",
            _FingerprintedStaticFiles(directory=assets_dir),
            name=_ASSETS_PREFIX,
        )

    # GET/HEAD only, deliberately. The fallback exists for document navigation;
    # a POST/PATCH/DELETE arriving here is a mistake, and index.html at 200
    # would make that mistake look like success. Starlette answers those with a
    # JSON 405 instead -- and because this route claims no other method, a
    # wrong-method call to a *real* endpoint (PATCH /api/tasks, say) still gets
    # its accurate 405 rather than being swallowed here as a 404.
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_spa(full_path: str) -> Response:
        """Static file if one exists, else index.html so client-side routing
        survives a hard refresh on /app or /app/health (the SPA's routes
        besides the landing page at /)."""
        _reject_reserved_path(full_path)

        target = _resolve_within(dist_root, full_path)
        if target is None:
            raise HTTPException(status_code=404, detail="Not Found")
        if target.is_file():
            return FileResponse(target, headers={"cache-control": _REVALIDATE_CACHE_CONTROL})
        return FileResponse(
            index_html,
            media_type="text/html",
            headers={"cache-control": _REVALIDATE_CACHE_CONTROL},
        )


def _register_api_only_routes(app: FastAPI) -> None:
    """No build present: serve the API alone and say so on every page request.

    This is the normal state in a fresh checkout, in CI and throughout the test
    suite, so it must never be an import-time failure -- `StaticFiles(directory=...)`
    raises on a missing directory, which would take the whole suite down at
    collection rather than at any one test.

    A page request answers 503 with a build hint rather than 404: the URL is not
    wrong, the deployment is half-built. 503 also stops an uptime check on "/"
    from reporting a green deploy that serves no UI.
    """

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def frontend_not_built(full_path: str) -> Response:
        # /api keeps its own 404s even here, so a bad endpoint is never
        # misreported as "the frontend isn't built".
        _reject_unknown_api_path(full_path)
        raise HTTPException(
            status_code=503,
            detail=(
                "Frontend is not built: frontend/dist/index.html is missing. "
                "Run `npm run build` in frontend/, or `npm run dev` for the Vite "
                "dev server (it proxies /api here). The JSON API is unaffected."
            ),
        )


def _register_no_frontend_routes(app: FastAPI) -> None:
    """The API alone, with nothing to say about a frontend (AWS Lambda).

    There, CloudFront serves the SPA from S3 and forwards only /api/* to this
    app, so any other path reaching it is simply not found -- a hint about
    running `npm run build` would be wrong for that deployment.
    """

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def not_found(full_path: str) -> Response:
        raise HTTPException(status_code=404, detail="Not Found")


def create_app(dist_dir: Optional[Path] = None, serve_frontend: bool = True) -> FastAPI:
    """Build an app instance.

    `dist_dir` defaults to the real frontend/dist; tests pass a tmp_path so SPA
    serving can be exercised without an npm build (tests/test_spa_serving.py).
    `serve_frontend=False` builds the API-only app the Lambda function runs
    (api/lambda_handler.py).
    """
    app = FastAPI(title="PawPal+ API", lifespan=lifespan)
    # Attaches the session cookie api/sessions.py queues, to success and error
    # responses alike.
    app.add_middleware(SessionCookieMiddleware)
    # Added last, so it is the outermost layer: a request that did not come
    # through CloudFront is refused before it can create a session.
    if origin_verify_required():
        app.add_middleware(OriginVerifyMiddleware, secret=os.getenv("PAWPAL_ORIGIN_VERIFY_SECRET", ""))

    app.include_router(session.router)
    app.include_router(owner.router)
    app.include_router(pets.router)
    app.include_router(tasks.router)
    app.include_router(schedule.router)
    app.include_router(health.router)

    @app.get("/api/healthz")
    def healthz() -> dict:
        """Liveness check used by the frontend dev proxy and deployment health checks."""
        return {"status": "ok"}

    # Must stay last -- see _register_spa_routes.
    if serve_frontend:
        _register_spa_routes(app, DIST_DIR if dist_dir is None else Path(dist_dir))
    else:
        _register_no_frontend_routes(app)
    return app


app = create_app()
