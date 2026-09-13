# PawPal+ production image -- see MIGRATION_PLAN.md §6 ("Dev workflow & production
# serving"). Dev runs two processes (uvicorn plus Vite's dev server proxying
# /api); production is deliberately one process on one port, with the React
# bundle baked in and api/main.py serving it via StaticFiles behind a catch-all
# fallback. That collapse to a single origin is what lets the frontend use
# relative /api/... paths and keeps CORS middleware out of the app entirely.
#
# This supersedes the `streamlit run app.py --server.port $PORT` deployment
# sketch in UPGRADES.md's deployment roadmap (step 3); Streamlit is gone as of
# the cutover phase.


# ---------------------------------------------------------------------------
# Stage 1 -- build the SPA
# ---------------------------------------------------------------------------
# Pinned to the Node 22 line the frontend is developed against, so the bundle
# that ships is built by the same major version that built the one tested
# locally.
FROM node:22-alpine AS frontend-build

WORKDIR /build

# Manifests first, install as its own layer. Dependencies churn far less than
# source does, so editing a .tsx file reuses this cached install instead of
# refetching the whole tree. `npm ci` rather than `npm install` because it
# installs exactly what package-lock.json pins and fails loudly if the lockfile
# has drifted from package.json -- a silently-resolved different dependency
# tree is precisely what a release build must not do.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# .dockerignore drops node_modules and dist from the context, so this copies
# source only -- a host-built tree can't clobber the install above (and on a
# Windows/macOS host it would carry the wrong platform's native binaries).
COPY frontend/ ./

# `npm run build` is `tsc -b && vite build`, so a type error fails the image
# build instead of shipping a broken bundle. Output is /build/dist: vite.config.ts
# sets no outDir, so this is Vite's default.
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 -- Python runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

# PYTHONDONTWRITEBYTECODE: .pyc files written into a container layer are pure
# write amplification, discarded with the container. PYTHONUNBUFFERED: without
# it uvicorn's stdout sits in a block buffer and `docker logs` looks silent
# during an incident. PYTHONPATH pins the import root so `api.main:app`
# resolves regardless of the cwd a deploy target happens to start us in.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Absolute, unlike the repo-relative defaults in .env.example. These have to
# agree with the directories chown'd and the volume declared below no matter
# what the process's working directory turns out to be; a relative
# "data/pawpal.db" resolved from an unexpected cwd would silently create a
# second, empty database somewhere unwritable or unmounted.
ENV PAWPAL_DB_PATH=/app/data/pawpal.db \
    PAWPAL_LOG_PATH=/app/logs/app.log

WORKDIR /app

# Dependencies as their own layer, ahead of any application code, so editing a
# router doesn't reinstall numpy/pydantic/uvicorn.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Only what the server actually imports at runtime. Everything omitted is
# omitted on purpose:
#   tests/                 running the suite is CI's job against a checkout;
#                          shipping it would drag pytest and its fixtures into
#                          a production image to sit unused.
#   evaluation/            the offline eval harness and ablation study. Neither
#                          is an import target of api/ -- they're run by hand
#                          against a checkout.
#   main.py,               the original CLI and the AI demo script. Both are
#   demo_pawpal_ai.py      __main__ entry points, imported by nothing in api/.
#   data/sample_documents/ demo fixtures, and doubly pointless here: /app/data
#                          is a volume mount point (below), so anything baked
#                          underneath it is shadowed the moment a volume is
#                          attached.
#   ai_interactions.md     pawpal_ai.pipeline appends to it only when called
#                          with write_trace=True, and health_service never
#                          passes that -- so no API request can reach the
#                          write, and the file needn't exist or be writable.
COPY api/ ./api/
COPY pawpal_ai/ ./pawpal_ai/
COPY pawpal_system.py ./

# Landed at the same repo-relative path the source tree uses, so api/main.py's
# StaticFiles mount resolves identically whether it derives the directory from
# the cwd or from __file__.
COPY --from=frontend-build /build/dist ./frontend/dist

# Run unprivileged. The chown is the part that carries the weight: nothing here
# writes at build time, but on the first request the app creates its SQLite
# database (api/storage.py) and opens its rotating log handler
# (pawpal_ai/logging_setup.py). A non-root user pointed at root-owned
# /app/data and /app/logs therefore fails at first write, in the request path,
# not during the build where it would be obvious.
#
# The ordering is load-bearing: mkdir and chown must come *before* VOLUME.
# Docker seeds a fresh volume from the image's contents and ownership at that
# mount point, and any chown applied in a layer after the VOLUME line is
# discarded -- which is exactly how this setup regresses to
# unwritable-at-runtime while still building green.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin pawpal \
    && mkdir -p /app/data /app/logs \
    && chown -R pawpal:pawpal /app/data /app/logs

# One SQLite file holds both api/storage.py's owners/pets/tasks tables and
# pawpal_ai's health records, so it is the whole of the app's durable state and
# has to survive the container being replaced on redeploy. Logs are
# deliberately not a volume: they rotate under a size cap, and `docker logs`
# covers the operational need.
VOLUME ["/app/data"]

USER pawpal

# 8000 is the default. Deploy targets that inject PORT (Cloud Run, Railway,
# Heroku) override it at runtime and the CMD honours that; EXPOSE can only
# document the static default.
ENV PORT=8000
EXPOSE 8000

# python:3.13-slim ships neither curl nor wget, and installing one purely to
# poll a health endpoint adds a package and its CVE surface for something the
# interpreter already in the image can do. A non-200 raises HTTPError, which
# exits non-zero and marks the container unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/healthz', timeout=4).status == 200 else 1)"]

# Secrets stay runtime env vars -- never build args, never baked layers.
# ANTHROPIC_API_KEY is read only when PAWPAL_LLM_PROVIDER=claude, and
# PAWPAL_OWNER_KEY guards the two LLM-calling endpoints (documents:extract and
# ask). Leaving PAWPAL_OWNER_KEY unset is a safe default rather than a broken
# one: those endpoints then return 503 instead of standing open to the public,
# because the gate fails closed by design (MIGRATION_PLAN.md §4). The container
# is fully functional with neither variable set -- the default mock provider
# needs no key at all.

# JSON (exec) form, so no shell lingers as PID 1 swallowing SIGTERM: `exec`
# hands the process slot to uvicorn, which then receives the signal directly
# and drains connections cleanly on `docker stop` instead of being killed after
# the timeout. The shell is present only to expand ${PORT:-8000} at runtime,
# which the exec form does not do by itself.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
