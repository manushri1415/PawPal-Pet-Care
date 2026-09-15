# 🐾 PawPal AI — Pet Health Record & Reminder Assistant

[![CI](https://github.com/manushri1415/PawPal-Pet-Care/actions/workflows/ci.yml/badge.svg)](https://github.com/manushri1415/PawPal-Pet-Care/actions/workflows/ci.yml)

PawPal AI turns messy veterinary paperwork into **verified, source-cited health
records and reliable reminders**. You upload a vet document (PDF/DOCX/TXT) or
paste text; a retrieval-augmented, multi-step AI agent proposes structured
records **grounded in the exact source passages**; you approve, edit, or reject
each one; and deterministic Python turns the approved facts into reminders and
contradiction warnings — never inventing a due date, dosage, or frequency.

> **Runs with no API key.** The default `mock` provider makes the entire app,
> its 430 tests, and the evaluation harness reproducible offline. The public demo
> runs on it too; a key is only needed for the owner space's live Claude model.

It runs as a **FastAPI backend + React/TypeScript single-page app** -- locally as
one process on one port, and in production serverless on AWS (CloudFront, API
Gateway, Lambda, DynamoDB; see [Deployment](#deployment)). (It began as a Streamlit app; the
migration off it is recorded in [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md).)

---

## The original project: PawPal+

This project **extends PawPal+**, an object-oriented pet-care scheduler built in
an earlier module. PawPal+ lets an owner manage pets and recurring care tasks
(walks, feeding, meds), sort tasks by priority/time, detect scheduling
conflicts, and generate a prioritized daily schedule. Its domain layer
(`pawpal_system.py`) and its pytest suite are preserved and still run unchanged;
what moved is everything around it — the scheduler is now the REST API under
`/api` (`api/routers/`, `api/services/scheduler_service.py`) plus the
**Scheduler** route `/app` in the React app
(`frontend/src/features/scheduler/`), and its state persists in SQLite instead
of living in a browser session.

**What PawPal AI adds:** a whole health-record subsystem — document ingestion,
RAG-based agentic extraction, human review, source citations, contradiction
detection, and a deterministic reminder engine — on the **Health Records** route
`/app/health`. Where PawPal+ relied on manual task entry, PawPal AI reads the
documents. The root `/` is a landing page that explains all of this to a
visitor and leads into the app.

---

## What it does & why it matters

Pet owners lose track of vaccine due dates, medication schedules, and follow-ups
spread across certificates, emails, and clinic printouts (I have personally
missed a vaccination due date — the motivation for this project). PawPal AI
organizes that information **without ever giving medical advice or fabricating
clinical values**, and reminds you before care items lapse.

- **AI does the interpretation** — extracting structured fields from free-form
  documents and answering questions about them.
- **Deterministic code does the math** — dates, statuses, reminders, conflict
  detection, and persistence.
- **A human is always in the loop** — nothing is saved or scheduled until you
  approve it.

---

## Architecture overview

The Mermaid source is in [`docs/system_architecture.mmd`](docs/system_architecture.mmd)
(view it on GitHub or at [mermaid.live](https://mermaid.live)). Flow:

```
Input → Validation/Injection-scan → Extraction → Chunking → Vector store →
Retriever → Agentic extraction (plan→act→check) → Schema + evidence validation →
Contradiction check → Human review → SQLite/DynamoDB → Reminder engine → Dashboard
                                          ↘ RAG Q&A ↗        ↘ Reliability evaluator
```

| Concern | Where | Kind |
|---|---|---|
| Interpret documents, answer questions | `llm.py`, `qa.py` | **AI** |
| Retrieval (embeddings + vector store) | `vectorstore.py` | local, no key |
| Schema, dates, status, reminders, conflicts, persistence | `health_models.py`, `reminders.py`, `contradictions.py`, `storage.py` | **Deterministic** |
| Approve/edit/reject before save | `frontend/src/features/health/ReviewPanel.tsx` | **Human review** |
| Evidence grounding, injection framing, approval gate, refusal | `evidence.py`, `guardrails.py`, `documents.py` | **Guardrails** |
| Reliability metrics + ablations | `evaluation/` | **Evaluation** |

**Why these choices:** RAG grounds every value in a real passage so the model
can't hallucinate; human approval is required because these are medical records;
deterministic Python owns dates/reminders because those are safety-critical and
must be exact; the vector store is a dependency-light pure-Python implementation
(local hashing embeddings + cosine) so the project builds on any machine with no
C++ compiler and no model download (a heavier DB like Chroma needs to compile
native wheels, which fails on stock Windows/Python 3.13). SQLite gives
zero-setup persistence locally; DynamoDB holds the same data in production
behind the same storage contract (`api/repositories/`).

---

## Setup

```bash
# 1. Clone
git clone <your-repo-url> PawPal-Pet-Care
cd PawPal-Pet-Care

# 2. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # macOS/Linux

# 3. Install Python dependencies (the runtime set plus test tooling)
pip install -r requirements-dev.txt
#   requirements.txt alone is the runtime set -- what the Docker image installs.

# 4. Configure environment (optional — defaults work with no key)
copy .env.example .env         # Windows  (cp on macOS/Linux)
#   leave PAWPAL_LLM_PROVIDER=mock to run offline with no key, or set
#   PAWPAL_LLM_PROVIDER=claude and ANTHROPIC_API_KEY=... for live extraction

# 5. (First run) generate the binary sample documents
python data/sample_documents/generate_samples.py
#   The SQLite DB is created automatically on first use.

# 6. Install the frontend's dependencies (Node 22+)
cd frontend && npm ci && cd ..
#   npm ci installs exactly what package-lock.json pins; npm install also works.
```

### Running it

The backend and the frontend are one product but two build systems, so there
are genuinely two ways to run it — pick by what you're doing.

**Development** — two processes, with hot reload on both sides:

```bash
# terminal 1 — API on :8000
uvicorn api.main:app --reload --port 8000

# terminal 2 — Vite dev server (prints its URL, default http://localhost:5173)
cd frontend && npm run dev
```

Open the Vite URL, not `:8000`. Vite proxies `/api` to uvicorn
(`frontend/vite.config.ts`), which is why the frontend only ever uses relative
`/api/...` paths and why there is no CORS middleware anywhere in the app.

**Production** — one process, one port, no proxy:

```bash
cd frontend && npm run build && cd ..   # writes frontend/dist
uvicorn api.main:app --port 8000        # serves the API *and* the built SPA
```

Now `http://localhost:8000` serves the app itself: `api/main.py` mounts
`frontend/dist/assets` and falls back to `index.html` for any other page URL, so
a hard refresh on `/app/health` works. Without a build present the API still runs
normally and page requests answer **503** with a "run `npm run build`" hint —
the deployment is half-built, and a 404 would misdescribe that.

**Docker** — the same single-port setup, built from scratch:

```bash
docker build -t pawpal .
docker run -p 8000:8000 -v pawpal-data:/app/data pawpal
```

The image is multi-stage (Node builds the bundle, Python runs uvicorn as a
non-root user) so no local Node or Python install is involved. The named volume
is worth passing: `/app/data` holds the one SQLite file with both the scheduler
tables and the health records, and without a volume each `docker run` starts
from an empty database. The app says so when that happens: any boot that finds
no existing database file logs a `starting with a new, empty database` warning,
so a forgotten `-v` shows up in `docker logs` rather than as data that quietly
vanished. `PORT` is honoured if your host injects one.

### Tests, evaluation, and the demo

```bash
pytest -q                        # 430 tests (SQLite; see below for DynamoDB)
python evaluation/run_eval.py    # reliability cases — prints a pass/fail summary
python evaluation/ablation.py    # retrieval + grounding ablations
python demo_pawpal_ai.py         # end-to-end CLI demo (also appends to ai_interactions.md)
cd frontend && npm run build     # type-checks (tsc -b) as well as bundling
cd frontend && npm run lint      # oxlint
```

To run the whole API suite against the DynamoDB backend instead of SQLite:
`PAWPAL_TEST_STORAGE=dynamodb pytest -q` (in-process moto), or against a real
engine with `docker run -p 8001:8000 amazon/dynamodb-local` and
`PAWPAL_TEST_DYNAMODB_ENDPOINT=http://localhost:8001`.

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every pull
request and every push to `main`: the pytest suite once per storage backend
(SQLite, and DynamoDB against a DynamoDB Local service container); the
reliability evaluation, which must match the committed report; the frontend
lint and build; and a Docker job that smoke-tests the production image and
confirms data survives the container being replaced. On `main`, once those
pass, a deploy job ships to AWS — see [Deployment](#deployment).

---

## Visitors, the owner space & AI

Every environment variable is optional and documented in
[`.env.example`](.env.example); the app runs with none of them set.

PawPal is public and has no accounts, so every request acts for exactly one of
two kinds of owner (`api/sessions.py`), and every read and write goes through a
repository bound to that owner (`api/repositories/`):

- **A demo visitor.** The first API request gets a private sandbox, seeded from
  real PawPal fixtures run through the real pipeline (`api/demo/seed.json`,
  built by `scripts/build_demo_seed.py`): three pets, a routine with recurring
  and overlapping tasks, extracted health records with evidence, reminders and
  a conflict. It is identified by a random `HttpOnly`, `SameSite=Lax` cookie,
  expires after 48 hours (`PAWPAL_DEMO_TTL_HOURS`), and can be reset from the
  banner. A visitor can never reach another visitor's data, even by guessing
  ids — every lookup is scoped by owner.
- **The owner space.** A request carrying `X-PawPal-Owner-Key` equal to
  `PAWPAL_OWNER_KEY` acts for the persistent, non-expiring owner space. A wrong
  key is refused (401), never downgraded to a demo; with no key configured
  there is no owner space (503). It is a shared secret, not an account system.
  The browser keeps it in `sessionStorage`, so it disappears with the tab.

**Which AI a request uses** follows from that (`api/deps.py::get_llm_client`):
demo visitors extract and ask with the free, deterministic rule-based model, so
the public demo works end to end and costs nothing; only the owner space uses
Claude, when `PAWPAL_LLM_PROVIDER=claude` and `ANTHROPIC_API_KEY` are set. There
is no other path to the Claude client. Never reuse `ANTHROPIC_API_KEY` as the
owner key.

"Today" is always the visitor's: the frontend sends its local wall-clock time
with every request (`X-PawPal-Client-Now`, `api/clock.py`), so schedules,
reminder status and new tasks follow the visitor's calendar, not the server's
(UTC in production).

---

## Deployment

Production runs serverless on AWS at `pawpal.manushri.dev`: CloudFront serves
the build from a private S3 bucket and routes `/api/*` to API Gateway and one
Python Lambda running this same FastAPI app (via Mangum); data lives in one
DynamoDB table; document chunks are stored alongside records so Ask survives
restarts. Everything is defined in [`infra/`](infra/) (AWS SAM) and deployed by
GitHub Actions with OIDC — no stored AWS keys. The runbook, limits and cost
table are in [`infra/README.md`](infra/README.md). Docker remains a
self-contained alternative (SQLite on a volume).

---

## Sample interactions

Below are real outputs from `python demo_pawpal_ai.py` (mock provider).

### 1. A valid vaccine document → proposed records + reminder

**Input:** `data/sample_documents/max_vaccine.pdf` (contains
`Rabies vaccine administered 2025-03-01. Next due 2026-03-01.`)

```text
Extracted 4 PENDING record(s):
  • vaccination  (confidence 1.0)
      vaccine_name: Rabies        [source demo_max#chunk-0: "administered today: Rabies vaccine…"]
      administered_date: 2025-03-01 [source demo_max#chunk-0: "Date of visit: 2025-03-01…"]
      due_date: 2026-03-01        [source demo_max#chunk-0: "Next due 2026-03-01…"]
      clinic: (not found)
      veterinarian: (not found)
...
Human approves → 🔔 Rabies (vaccination): due 2026-03-01 (current); alerts [30, 14, 7, 1, 0] days before
```

Every kept field carries a **citation**; unstated fields are `(not found)`, not guessed.

### 2. A document with a missing due date → abstain, no invented reminder

**Input:** `Patient: Luna\nFVRCP vaccine administered 2025-06-10. Booster interval not specified.`

```text
Extracted 1 record(s)
  • vaccination: administered_date=2025-06-10, due_date=(not found)
Missing important fields (left blank, not guessed): vaccination[FVRCP].due_date
→ No reminder is generated. The system asks you to confirm the interval.
```

The baseline "guess +1 year" behavior is explicitly suppressed — see
[`evaluation/evaluation_ablation.md`](evaluation/evaluation_ablation.md).

### 3. Two conflicting vaccine dates → conflict warning, reminder blocked

**Input:** two Max rabies records, administered `2025-03-01` vs `2025-02-20`.

```text
⛔ CONFLICT vaccination.administered_date: '2025-03-01' vs '2025-02-20'
⛔ CONFLICT vaccination.due_date: '2026-03-01' vs '2026-02-20'
Rabies reminders after conflict: blocked (2 records); other records still scheduled.
```

The system refuses to pick a winner and **blocks reminders** for the conflicting
records until a human resolves it.

### Guardrails in action (Q&A)

```text
Q: When is Max's rabies vaccine due?     → [ANSWERED] grounded in demo_max#chunk-0
Q: What is the capital of France?        → [ABSTAINED] "not enough evidence in the records"
Q: What medicine should I give my dog?   → [REFUSED]   "I can't diagnose or prescribe…"
```

---

## Design decisions

- **Why RAG?** Grounding every extracted value in a retrieved passage is what
  lets the deterministic layer *verify* the AI and drop anything unsupported —
  the mechanism that prevents hallucinated dates/dosages. The retrieval ablation
  (`k=0` → 0 records, `k=4` → full extraction) shows retrieval genuinely drives
  output.
- **Why human approval?** These are medical records; an LLM extraction is a
  *proposal*, not a fact. Approval is enforced before any save or reminder.
- **Why deterministic dates/reminders?** Off-by-one errors in due dates cause
  real harm; that logic must be exact and testable, not model-generated.
- **Why a pure-Python vector store?** Reproducibility. A neural/compiled vector
  DB breaks `pip install` on stock Windows/Python 3.13; local hashing embeddings
  need no compiler, no download, no key. The `VectorStore` interface is swappable
  if you later want neural embeddings.
- **Why SQLite + mock provider?** Zero-setup persistence and a fully offline,
  key-free demo/test/eval path — so another person can run everything.
- **Trade-offs / postponed:** no real fine-tuning (few-shot + grounding instead),
  no multi-pet-per-document splitting, no notification delivery, and no user
  accounts (anonymous sandboxes plus one owner key instead) — see `model_card.md`.

---

## Testing summary

- **430 tests** (`pytest -q`), in these layers:
  - **86 scheduler-domain** (`test_pawpal.py` 41, `test_edge_cases.py` 45) —
    `pawpal_system.py`'s tasks, pets, priorities, recurrence and conflicts.
  - **70 PawPal AI** (`test_pawpal_ai.py`) — document validation and size
    limits, extraction, evidence grounding, invalid dates, contradiction
    detection, reminder rules, the approval guardrail, prompt-injection
    handling, LLM-failure + retry-limit paths, Claude client limits, user-safe
    LLM error messages and log redaction, and an end-to-end
    upload→approve→reminder flow.
  - **75 API** (`test_api_scheduler.py` 42, `test_api_health.py` 19,
    `test_ai_access.py` 14) — every route against a `TestClient` with an
    isolated backend; which model demo visitors and the owner get, and that no
    wrong key and no vendor error text ever gets through.
  - **46 sessions and isolation** (`test_sessions.py` 26, `test_demo_seed.py`
    12, `test_retrieval_persistence.py` 8) — two visitors attacking every by-id
    endpoint with each other's ids, expiry, the owner space, reset, migration of
    pre-session databases, the seeded sandbox, and Ask answering identically
    after the whole backend is rebuilt from storage.
  - **76 storage and correctness** (`test_repository_contract.py` 45,
    `test_correctness_fixes.py` 31) — the storage contract on SQLite *and*
    DynamoDB, the visitor's clock, atomic recurring completion under
    concurrency, race-free conflicts, stdout logging.
  - **33 AWS** (`test_lambda_handler.py` 21, `test_infra.py` 12) — real API
    Gateway events through the Lambda handler (cookies, base64 uploads, SSM
    secrets, origin check, the payload budget) and the infrastructure template,
    including the CloudFront Function run in node.
  - **44 serving and startup** (`test_spa_serving.py` 41, `test_app_startup.py`
    3) — the SPA fallback, `/api` never shadowed, no path traversal, and the
    new-empty-database warning.
- **Evaluation: 17/17 reliability cases pass** (`evaluation/run_eval.py`); see
  [`evaluation/evaluation_report.md`](evaluation/evaluation_report.md).
  Highlights: correct abstention on missing-due-date cases, 0 unsupported values
  saved, prompt-injection flagged and its embedded instructions ignored, and 0
  reminders from unapproved records.
- **What guardrails improved:** the field-level evidence check removes fabricated
  values (baseline invents a due date; grounded pipeline returns null — see the
  ablation), and the approval gate + conflict-blocking stop unverified or
  contradictory data from producing reminders.
- **Known limitations:** the offline `mock` extractor is rule-based (weaker than
  Claude on unusual document layouts); multiple pets in one document are all
  attributed to the active pet pending human correction.

## Reflection (short)

Building this reinforced that **an LLM's output is a hypothesis to verify, not a
result to trust** — the reliability came almost entirely from the deterministic
checks *around* the model (evidence grounding, schema validation, human
approval), not from the prompt alone. The full responsible-AI reflection —
including a helpful vs. flawed AI suggestion and how they were verified — is in
[`model_card.md`](model_card.md).

---

## Repository layout

```
api/                       FastAPI backend — every route under /api
  main.py                  app factory, /api/healthz, production SPA serving, middleware
  sessions.py              demo-visitor cookie sessions and the owner space
  deps.py                  owner-bound repository, per-request model choice, services
  clock.py                 the visitor's local "today" (X-PawPal-Client-Now)
  repositories/            storage contract + SQLite and DynamoDB backends
  demo/                    seeded sandbox snapshot and its per-visitor rewrite
  lambda_handler.py        AWS Lambda entry point (Mangum); secrets.py, origin.py
  routers/                 session, owner, pets, tasks, schedule, health
  services/                scheduler_service, health_service — domain glue
  schemas/                 Pydantic request/response models
infra/                     AWS SAM templates (app, certificate, GitHub OIDC) + runbook
scripts/                   demo seed builder, Lambda staging, frontend deploy, DNS, smoke test
frontend/                  Vite + React + TypeScript SPA; landing page at /, the app at /app and /app/health
  src/features/landing/    Landing page — what PawPal+ is, and the way into the app
  src/features/scheduler/  Scheduler UI (pets, tasks, daily schedule, overlaps)
  src/features/health/     Health-records UI (upload, review, reminders, ask, audit)
  src/features/session/    Session gate and the demo/owner banner (Reset demo)
  src/components/          Shared design-system pieces (Card, Button, Tag, …)
  src/styles/              tokens.css / global.css — the palette
  src/api/                 Typed fetch clients mirroring the Pydantic schemas
pawpal_system.py           Canonical domain model (scheduling)
pawpal_ai/                 The AI system (config, documents, chunking, vectorstore,
                           llm, prompts, extraction_agent, evidence, qa, reminders,
                           contradictions, guardrails, storage, logging)
Dockerfile                 Multi-stage build (Node bundles the SPA → Python runs uvicorn)
.github/workflows/ci.yml   CI (pytest x2 storages, evaluation, frontend, Docker) + OIDC deploy to AWS
requirements.txt           Runtime dependencies (all the image installs)
requirements-dev.txt       + test tooling, for local development and CI
data/sample_documents/     Synthetic vet documents (no real PII)
evaluation/                run_eval.py, ablation.py, cases + generated reports
docs/system_architecture.mmd
tests/                     430 tests
model_card.md              Responsible-AI reflection & limitations
ai_interactions.md         Agent reasoning traces
MIGRATION_PLAN.md          The Streamlit → FastAPI/React migration, phase by phase
demo_pawpal_ai.py          End-to-end CLI demo
main.py                    The original pre-web PawPal+ walkthrough script
```
