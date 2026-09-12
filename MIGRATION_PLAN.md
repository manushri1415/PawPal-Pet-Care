# Streamlit → FastAPI + React/Vite Migration Plan

**Status (2026-09-12):** Phases 0-4 done and merged (Phase 0: scaffolding;
Phase 1: scheduler backend; Phase 2: scheduler frontend redesign; Phase 3:
health backend; Phase 4: health frontend redesign). Phase 5 (cutover) not
started — pick up there next.

This is the plan as approved by the user, kept here so it survives across
chat sessions and worktrees (a plan-mode plan file only lives on the machine
that wrote it). Resuming in a new conversation: point Claude at this file and
say which phase to start.

---

## Context

PawPal+ currently runs as a Streamlit app (`app.py` for the scheduler, `pages/1_Health_Records.py`
for the RAG-based health-records/AI features). The user wants off Streamlit, driven by UI/UX
control (no full-script reruns, real components), testability (UI logic currently untestable
outside Streamlit), and deployment flexibility. This is a resume/portfolio project — **no general
user accounts** are wanted — but the AI-calling features (document extraction, Q&A) must be
**gated to the owner only** once a real Anthropic API key is configured, so a public demo visitor
can't run up API costs. The lavender/sage/terracotta visual language from the (unpushed, local-only)
`pawpal-ui-redesign` branch (`theme.py`) should carry forward into the new frontend — see the note
in §5.

Investigation (full detail from an Explore + Plan pass) confirmed the business logic is already
framework-agnostic and reusable almost as-is:
- `pawpal_system.py` (Task/Pet/Owner/Scheduler) — pure in-memory Python, **zero persistence**
  today (state only lives in Streamlit `st.session_state`). This is genuinely new work, not
  optional: a stateless API needs real storage for it.
- `pawpal_ai/` (RAG pipeline, extraction, Q&A, reminders, conflicts) — already has real SQLite
  persistence (`pawpal_ai/storage.py`, `data/pawpal.db`) and clean Pydantic schemas
  (`health_models.py`) that map ~1:1 to API response models.
- Along the way, several real bugs surfaced in the current Streamlit UI (pet-delete bypassing
  `Owner.remove_pet`, task-uncomplete bypassing any domain method, a duplicated ad hoc overlap
  check, `document_id` getting silently wiped on every approve/reject, reminders duplicating
  forever on every rerun). Fixing these is part of building a clean API layer, not scope creep —
  see §7.

No data migration is needed anywhere: nothing survives a Streamlit process restart today, so the
new tables simply start empty.

**Execution note:** per standing workflow preference, this is built in a new git worktree per
phase (or per work session), not on `main` directly — merge back to `main` at clean phase
boundaries.

---

## 1. Repo layout

Keep `pawpal_system.py`, `pawpal_ai/`, `tests/`, `data/` in place (two small additive exceptions
in §7). Add two new top-level trees:

```
api/                              # NEW — FastAPI backend
  main.py                         # app, router mounts, static/SPA serving for prod
  deps.py                         # shared deps: storages, llm/vectorstore singletons, AI-gate
  storage.py                      # SchedulerStorage: owners/pets/tasks tables (own sqlite conn)
  schemas/{scheduler,health}.py   # Pydantic I/O models
  routers/{owner,pets,tasks,health}.py
  services/{scheduler_service,health_service}.py   # domain-object rehydration + persistence glue

frontend/                         # NEW — Vite + React + TypeScript
  src/
    styles/{tokens.css,global.css}   # ported --pp-* palette from theme.py (values, not the file)
    components/{BrandBadge,Eyebrow,DotBadge,Tag,Card,EmptyState,Button,Alert}.tsx
    features/scheduler/{SchedulerPage,OwnerProfileForm,PetList,PetForm,TaskList,TaskForm,
                         ScheduleView,OverlapBanner}.tsx
    features/health/{HealthRecordsPage,OwnerKeyGate,UploadExtractPanel,ReviewPanel,
                      RemindersPanel,AskPanel,AuditPanel}.tsx
    api/{client,scheduler,health,types}.ts

Dockerfile                        # NEW — multi-stage (node build → python runtime)
```

TypeScript is worth the small extra setup because the Pydantic schemas give us a natural source
of truth to mirror as TS interfaces, catching payload drift at compile time.

---

## 2. Scheduler persistence (new — this is the one genuinely new backend subsystem)

Same file, `data/pawpal.db`, but a **separate connection and schema** owned by `api/storage.py`
— `pawpal_ai/` stays completely untouched. On connect, set explicitly (not left to SQLite
defaults): `PRAGMA foreign_keys = ON` (enforce `pets.owner_id`/`tasks.owner_id`/`tasks.pet_id`
references), `PRAGMA journal_mode = WAL` (readers don't block the writer), `PRAGMA busy_timeout =
5000` (safe concurrent access across the two independent connections into one file).

```sql
CREATE TABLE owners (owner_id PK, name, email, phone_number, available_hours_per_day,
                      work_start_hour, work_start_minute, work_end_hour, work_end_minute,
                      break_between_tasks_minutes, created_at, updated_at)   -- singleton row

CREATE TABLE pets (pet_id PK, owner_id, name, pet_type, age, age_months, gender, color,
                    created_at, updated_at)

CREATE TABLE tasks (task_id PK, owner_id, pet_id NULL, name, category, duration, priority,
                     frequency, notes, scheduled_time, due_date, end_date, completed,
                     created_at, updated_at)
```

This `pets` table is also the fix for "two disconnected pet lists": today the scheduler's pets
(`owner.pets`) and the health-records page's pets (`st.session_state.health_pets`) are entirely
separate, in-memory-only lists. Neither `pawpal_ai` table has a pets table of its own — it only
ever stored a free `pet_id` string — so unifying on one real `pets` table needs no `pawpal_ai`
schema change, just both routers validating `pet_id` against it.

**Owner is a singleton**: first boot creates one `Owner` row; `/api/owner` never takes an id.

**Mutation pattern** (`api/services/scheduler_service.py`): rehydrate the relevant `Pet`/`Task`
objects from SQL into real `pawpal_system` objects, call the one `Owner`/`Scheduler` method the
endpoint needs, persist only the rows that method is documented to touch. This is what fixes the
bypass bugs (§7) for free — the service always goes through `owner.remove_pet(...)`, the new
`owner.uncomplete_task(...)`, etc., never a raw list/attribute mutation.

**Pet delete + existing health records**: default to `409 Conflict` if the pet has any health
records ("N health record(s) exist; pass `?force=true`"), rather than silently orphaning them.

---

## 3. REST API surface

All under `/api`; everything else is reserved for the built SPA (§5).

**Owner** — `GET/PATCH /api/owner`

**Pets** — `GET/POST /api/pets`, `GET/PATCH/DELETE /api/pets/{pet_id}?force=`

**Tasks**
- `GET /api/tasks?pet_id=&status=open|completed|all&sort=priority|time|duration`
- `POST /api/tasks`, `GET/PATCH/DELETE /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/complete` → `{task, next_occurrence}`
- `POST /api/tasks/{task_id}/uncomplete` (new `Owner.uncomplete_task`)
- `GET /api/tasks/overlaps` (new `Scheduler.detect_time_overlaps` — replaces the ad hoc UI check)

**Schedule** (stateless, always computed live)
- `POST /api/schedule/generate?date=` → `generate_daily_schedule` + `detect_conflicts`

**Health — documents/extraction** (🔒 AI-gated, §4)
- `POST /api/health/pets/{pet_id}/documents:extract` (multipart file or `{text}`) →
  `ingest_bytes/ingest_text` → `process_document`; persists via `save_document`/`save_record`

**Health — review** (free)
- `GET /api/health/pets/{pet_id}/records?review_status=`, `GET /api/health/records/{id}`
- `POST /api/health/records/{id}/approve|reject` → **only** `set_review_status` (see bug fix §7)
- `PATCH /api/health/records/{id}` → preserves existing `document_id` when re-saving fields

**Health — reminders & conflicts** (free)
- `POST /api/health/pets/{pet_id}/schedule-care` → calls `approve_and_schedule(...)` directly
  (the existing combinator the Streamlit page never actually uses)
- `GET /api/health/pets/{pet_id}/reminders`, `GET /api/health/pets/{pet_id}/conflicts?unresolved_only=`
- `POST /api/health/conflicts/{id}/resolve`

**Ask** (🔒 AI-gated) — `POST /api/health/pets/{pet_id}/ask` `{question, document_id?}`

**Audit** (free) — `GET /api/health/audit?limit=`

---

## 4. AI-gate (owner-only access to cost-incurring endpoints)

- New env var `PAWPAL_OWNER_KEY` (blank by default, added to `.env.example`) — kept in
  `api/deps.py`, not `pawpal_ai/config.py`, since it's an API-layer concern.
- `api/deps.py::require_owner`: reads header `X-PawPal-Owner-Key`, compares with
  `secrets.compare_digest`.
  - Key unset on server → **503** (fail closed — a forgotten secret never means "ungated").
  - Missing/wrong header → **401**.
  - Applied via `Depends(require_owner)` on exactly the extract and ask routes, unconditionally
    (not gated behind `settings.use_claude()`, so it can't accidentally ship open when the
    provider flips from mock to claude).
- Frontend: `OwnerKeyGate.tsx` — one-time paste-in box on the Health Records page, stored in
  `sessionStorage` (deliberately not `localStorage` — the key should disappear when the browser
  tab/session closes rather than persist indefinitely; a small inconvenience worth it for a
  secret); `api/health.ts` attaches the header only on the two gated calls; a 401 renders an
  inline "enter your owner key" prompt instead of a generic error.
- This is a shared-secret gate, not real auth — appropriate for "no general accounts, but only I
  should trigger paid calls." Never reuse `ANTHROPIC_API_KEY` as this secret.

---

## 5. Frontend

Vite + React + TypeScript, React Router (`/` Scheduler, `/health` Health Records), React Query
for data fetching/caching (fixes the audit's "no loading states" complaint by construction).
Relative `/api/...` paths only — same-origin in prod, Vite-proxied in dev — so **no CORS
middleware needed anywhere**.

**Redesign, not a port.** The React UI is a native rebuild, not a recreation of Streamlit's DOM
structure/layout. Only the *palette and design tokens* carry over from `theme.py`; component
composition, layout, and interactions (cards, modals, hover states, transitions, illustration
layers) are designed fresh for React/CSS, unconstrained by what was achievable via Streamlit
`st.html`/CSS-selector overrides. This is what makes the "cozy pet-shop" direction (peeking
animal illustrations, proper responsive cards, etc.) actually tractable.

Palette: copy the `--pp-*` custom property values from `theme.py` into `frontend/src/styles/tokens.css`;
they're already flat CSS custom properties, so this is close to copy-paste. **Provenance
correction (found while doing Phase 0):** that lavender/sage/terracotta `theme.py` work was never
pushed to GitHub — `origin/main` is still on an earlier "Mockup A" pass (terracotta/sand/ink, no
`theme.py`). The only copy is the local worktree at `.claude/worktrees/pawpal-ui-redesign` (or
commit `41a8db9` on branch `worktree-pawpal-ui-redesign`) — pull the hex values from there, not
from whatever's currently live in `app.py`. Rebuild the *visual patterns* the palette expresses
(brand badge, eyebrow labels, dot badges, dashed tag pills, tinted hover-lift cards, empty states,
AA-contrast buttons) as real, freely-composable React components. Priority colors: low=sage,
medium=ochre, high=terracotta.

**Vector store note**: `pawpal_ai.VectorStore` stays in-memory (a single process-wide instance in
`api/deps.py` is fine for a single-user app), same as today's per-session behavior — lost on
process restart. That's parity with the current app, not a regression; persisting it is already
tracked as separate future work in `UPGRADES.md` and is out of scope here.

---

## 6. Dev workflow & production serving

- **Dev**: `uvicorn api.main:app --reload --port 8000` + `npm run dev` (Vite) with a
  `server.proxy: {"/api": "http://localhost:8000"}` dev-proxy (already wired in Phase 0).
- **Prod**: one process/port. `npm run build` → `frontend/dist`; `api/main.py` mounts it via
  `StaticFiles` plus a catch-all `GET /{full_path}` → `index.html` (registered after all `/api/*`
  routes) for client-side routing on hard refresh.
- New multi-stage `Dockerfile` (node build stage → python runtime stage), replacing the
  `streamlit run app.py` command in UPGRADES.md's old deployment sketch.

---

## 7. Bug fixes carried out as part of building the clean API layer

| Issue | Today | Fix |
|---|---|---|
| Pet delete bypasses `Owner.remove_pet` | `app.py`: `owner.pets.remove(pet)` | service calls `owner.remove_pet(pet_id)` |
| Task un-complete bypasses any domain method | `app.py`: `task.completed = False` | new `Owner.uncomplete_task(task_id)` |
| Overlap check duplicated ad hoc in the UI | `app.py` | new `Scheduler.detect_time_overlaps(tasks)`, exposed as `GET /api/tasks/overlaps` |
| `approve_and_schedule` combinator unused; conflicts/reminders re-derived inline | `pages/1_Health_Records.py` | `schedule-care` endpoint calls it directly |
| `document_id` silently wiped on every approve/reject (`save_record(rec, document_id="")`) | same file | approve/reject call **only** `set_review_status`; edit preserves the existing `document_id` |
| Reminders duplicate forever each rerun; conflicts never actually persisted from the UI | same file | deterministic `reminder_id = f"rem_{record.record_id}"` (upsert); dedupe conflicts by `(record_type, field, value_a, value_b)` before insert |
| Two disconnected pet lists (scheduler vs. health records) | both UI files | one shared `pets` table (§2) |

`pawpal_system.py` gains exactly two additive methods for this (`Owner.uncomplete_task`,
`Scheduler.detect_time_overlaps`), each with new unit tests in `tests/test_pawpal.py`. Nothing
else in `pawpal_system.py`/`pawpal_ai/` changes.

---

## 8. Phases (each boundary left in a working, demoable state)

0. **Scaffolding — ✅ DONE, merged to `main`.** `api/` FastAPI skeleton with `/api/healthz`;
   `frontend/` Vite+React+TS scaffold with React Router, React Query, dev proxy, empty
   `styles/tokens.css`/`global.css` placeholders. Verified: existing pytest suite (136 tests)
   unaffected; uvicorn + Vite both start; Vite's `/api` proxy reaches FastAPI; `npm run build`
   succeeds. `app.py`/`pages/` untouched throughout.
1. **Scheduler backend — NOT STARTED, do this next.** The two new `pawpal_system.py` methods +
   tests, `api/storage.py` (with the WAL/foreign-keys pragmas from §2), scheduler
   schemas/service/routers, `tests/test_api_scheduler.py`.
2. **Scheduler frontend redesign** — palette tokens filled in (see the provenance correction in
   §5 — pull from the local unpushed worktree, not `app.py`), base components, routing shell,
   `features/scheduler/*` built natively for React (not a Streamlit DOM port, per §5).
3. **Health backend — ✅ DONE.** `api/schemas/health.py` (mostly reusing
   `pawpal_ai.health_models` types directly, per the enum-reuse convention from
   Phase 1), `api/services/health_service.py`, `api/routers/health.py`, the
   backend half of the AI-gate (`api/deps.py::require_owner`, env
   `PAWPAL_OWNER_KEY`, header `X-PawPal-Owner-Key` — the `sessionStorage`
   frontend half lands in Phase 4 per §4), plus the bug fixes from §7
   (extraction persists records immediately with the right `document_id`;
   approve/reject call only `set_review_status`; edit preserves
   `document_id`; `schedule-care` calls `approve_and_schedule` directly and is
   idempotent — deterministic `rem_<record_id>` reminder ids, conflicts
   deduped by `(record_type, field, value_a, value_b)` in either order).
   `tests/test_api_health.py` (26 cases) and `tests/test_ai_gate.py` (provider
   via injected `MockLLM`, free/deterministic) — full suite 208/208.
4. **Health frontend redesign — ✅ DONE, merged to `main`.** `features/health/*`,
   `OwnerKeyGate` → full functional parity (fixes included) with a genuinely redesigned
   UI, cutover-ready. Verified: pytest (208/208), `tsc -b`/`npm run build`/`oxlint`, and a
   full CDP-driven browser smoke test of the health-records flow (incl. the owner-key
   gate). Two real bugs surfaced by that smoke test and fixed along the way: a startup
   race between the two storage singletons' first construction (`api/main.py` lifespan
   hook now builds them sequentially), and `SchedulerStorage`'s single sqlite3 connection
   having no lock around concurrent per-request threadpool access (`api/storage.py`,
   now `threading.RLock`-protected).
5. **Cutover** — static/SPA serving in `api/main.py`, `Dockerfile`; delete `app.py`, `pages/`,
   `tests/test_app_ui.py`; drop `streamlit` from `requirements.txt`; update `README.md` /
   `IMPLEMENTATION_SUMMARY.md`; add `PAWPAL_OWNER_KEY` to `.env.example`.

---

## 9. Testing

- Existing `tests/test_pawpal.py`, `test_edge_cases.py`, `test_pawpal_ai.py`, `conftest.py` keep
  passing unchanged, plus a few new cases for the two additive methods.
- `tests/test_api_scheduler.py`, `tests/test_api_health.py`: FastAPI `TestClient`, isolated
  storage per test via `tmp_path` + `app.dependency_overrides`; health tests run with
  `PAWPAL_LLM_PROVIDER=mock` (free/deterministic, matching the existing suite's convention).
- `tests/test_ai_gate.py`: no key configured → 503; wrong/missing header → 401; correct → 200.
- `tests/test_app_ui.py` retired in Phase 5 alongside `app.py`/`pages/`.

**Verification**: `pytest -q` after each backend phase; `npm run build` (type-check + bundle)
after each frontend phase; manual smoke test via `uvicorn` + `npm run dev` at phase boundaries 2
and 4 (full scheduler flow, then full health-records flow including the owner-key gate); final
`docker build` + container run as the last check before calling cutover done.
