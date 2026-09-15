# PawPal — Upgrade & Hardening Plan

Full-repo review of `pawpal_system.py`/`app.py` (the original scheduler), `pawpal_ai/` +
`pages/1_Health_Records.py` (the RAG health-records system), `data/`, `tests/`, and the
project docs — done with an eye toward three goals: (1) fix real bugs, (2) get this to a
place where it can run as a live, S3-backed multi-user website, and (3) make the repo read
as deliberate engineering work rather than a bootcamp deliverable. Every finding below cites
the exact file and line so it's checkable, not just asserted.

**Read this in priority order — don't jump to the S3 section first.** Items in Priority 0
actively hurt you *today* (a possible PII leak, a repo that visibly says "class project" in
its own git history); items in Priority 1 are real bugs that would misbehave the moment more
than one user touches this app, which is exactly what an S3-backed deployment implies.

---

## Priority 0 — Do these before showing the repo to anyone

### 0.1 Likely real PII committed to `ai_interactions.md`
`ai_interactions.md:23,31,38,45,52,59,69,79,89,99,109` contains extraction-trace entries for
filenames that are **not** the synthetic samples in `data/sample_documents/`:

```
<pet-name>_<surname>_checkout_documents__2024__02__20__13__14__22_65d5081ea6da8_1.pdf
<pet-name>_<surname>_checkout_documents__2024__02__20__13__14__33_65d508291da25_1.pdf
```
(redacted here — the real filenames named a pet and a surname; see the fix commit for the
exact strings scrubbed from git history)

That naming pattern (`<pet-name>_<surname>_checkout_documents__<timestamp>_<hash>_1.pdf`) is
a "download my documents" export format from a pet-insurance/vet portal — i.e. this looks
like a real personal document that got uploaded while testing the live Claude provider, and
the trace (including the filename) was written straight into a tracked file and committed
(commit `d2d490d`, "Commit remaining local source changes"). This directly contradicts
`model_card.md:44-46` ("All sample documents ... are synthetic ... No third-party or real
user documents were used") — true for `data/sample_documents/`, not true for what's actually
sitting in `ai_interactions.md`.

Root cause: `logging_setup.py` has a redaction denylist for the structured JSON logs, but
`extraction_agent.py:68-72` (`append_trace`) writes to `ai_interactions.md` through a
completely separate, unredacted path that dumps `doc.filename` verbatim
(`extraction_agent.py:204`, `Tracer.title`). Redaction was implemented for one output
channel and forgotten on the other.

**Action:**
- Remove the affected entries from `ai_interactions.md` and regenerate it with
  `python demo_pawpal_ai.py` (sample docs only, per the file's own header instruction at
  line 11).
- Rewrite git history to remove the real filename from every commit that touched it
  (`git filter-repo` or BFG — editing the current file isn't enough, the string stays in
  history and in any fork/clone already made).
- Fix `append_trace`/`Tracer` to redact or hash filenames before writing, so this can't
  recur.

### 0.2 Git history reads as a graded class assignment
```
1c73efe Merge pull request #28 from codepath/claude/add-ai-grading-scaffold
9ca297d Add AI grading scaffold: ai_interactions.md, diagrams/uml_draft.mmd, README sections
4c55912 Rename uml_draft.mmd to uml.mmd to match grading expectation
6688e51 Use generic walkthrough prompts instead of specific examples
2279296 Make screenshot/video optional alongside required demo walkthrough
639ce1c Use format-only placeholders in walkthrough and UML skeleton
```
Anyone running `git log` sees a PR merged from a branch literally named
`codepath/claude/add-ai-grading-scaffold`, plus several commits whose entire purpose is
"satisfy the rubric." That's confirmed in the code itself —
`extraction_agent.py:16-17`: *"...appended to `ai_interactions.md` (the committed reasoning
trace **the rubric rewards**)."* This is a much bigger "this is coursework" signal than
anything about code quality. This is also almost certainly the single largest contributor to
"it looks so much like AI" — it's not that the code looks AI-written, it's that the repo's
own history and docstrings say "this was built to satisfy an AI-usage grading rubric."

**Action:** before pointing a recruiter at this repo, either (a) rewrite the history
(`git filter-repo` to reword commits / squash the scaffold-era commits into one
"Initial PawPal+ scaffold" commit), or (b) start a clean `main` from a single fresh commit
that carries today's tree without the old history, and push the detailed history to an
`archive/coursework-history` branch if you want to keep it for yourself. Also drop the
"the rubric rewards" phrase from `extraction_agent.py:17` and rewrite `reflection.md` (see
§6.2) and the vague final commit message `d2d490d "Commit remaining local source changes"`.

### 0.3 `.env.example` doesn't exist
`README.md:97` tells the reader to run `copy .env.example .env`, but no `.env.example` is
tracked in the repo (verified with `git ls-files`). Anyone following the README hits a
missing-file error on step 4. Add a real `.env.example` with every key from
`pawpal_ai/config.py:88-97` (`PAWPAL_LLM_PROVIDER`, `PAWPAL_MODEL`, `ANTHROPIC_API_KEY`,
`PAWPAL_RETRIEVAL_K`, `PAWPAL_MAX_ATTEMPTS`, `PAWPAL_EVIDENCE_THRESHOLD`,
`PAWPAL_DUE_SOON_DAYS`, `PAWPAL_DB_PATH`, `PAWPAL_CHROMA_PATH`, `PAWPAL_LOG_PATH`) set to
safe defaults/blank.

### 0.4 Untracked `.claude/` at the repo root
The primary checkout has an untracked `.claude/` directory (this review's own worktree lives
under it). Add `.claude/` to `.gitignore` now, before it's ever accidentally committed — a
public repo with a committed AI-agent config folder is its own "built by an AI tool" tell,
independent of everything else in this document.

---

## Priority 1 — Correctness bugs in the RAG pipeline (`pawpal_ai/`)

These matter beyond "code quality" because they're the exact bugs that turn into real
incidents the moment this becomes a multi-user, S3-backed app.

### 1.1 Cross-pet (and, after S3, cross-user) data leakage in Q&A — the most important fix
- `pawpal_ai/vectorstore.py:49-63` — `Chunk`/`RetrievedChunk` carry only `document_id`, no
  `pet_id` or owner/tenant concept at all.
- `pawpal_ai/vectorstore.py:89-109` (`VectorStore.retrieve`) filters by a single optional
  `document_id`, applied *after* scoring every chunk ever added to the store.
- `pawpal_ai/qa.py:29-45` (`answer_question`) takes an optional `document_id` that defaults
  to `None` (no filtering).
- `pages/1_Health_Records.py:43` creates **one `VectorStore` per browser session**
  (`ss.setdefault("vstore", VectorStore())`), shared across every pet the owner manages, and
  the real call site at `pages/1_Health_Records.py:475` calls `answer_question(q,
  st.session_state.vstore, llm, k=SETTINGS.retrieval_k)` — **no `document_id` is ever
  passed.**

Net effect: in a session managing two pets, a question about Pet B can retrieve and answer
from Pet A's medical text, with citations that look legitimate. The extraction path scopes
correctly (`extraction_agent.py:79-89,215` always passes a `document_id`); only Q&A doesn't.
`tests/test_pawpal_ai.py`'s `TestQA` only ever builds a store with one document, so this is
invisible to CI.

This is not just a two-pet-in-one-session bug — it's the exact gap that becomes
**cross-account data leakage between different real users** the moment documents/vectors
move into shared storage for a live website. **Fix this before any S3/multi-tenant work,
not after** — thread a `pet_id`/`owner_id` through `Chunk`, `VectorStore.retrieve`, and
`answer_question`, and make the caller pass it (not optional).

### 1.2 Duplicate `chunk_id`s from the hard-split path
`pawpal_ai/chunking.py:44-70` — chunks are first numbered by position in a first pass
(`idx`), then a second pass hard-splits any oversized block and numbers the pieces by
`len(final)` at insertion time. If an earlier chunk gets split first, a later untouched
chunk's original `idx`-based id can collide with a split piece's id. Real PDF text (no blank
lines) is exactly what triggers the hard-split branch, so this isn't a rare edge case for
actual vet documents. `extraction_agent._retrieve_all()` (`extraction_agent.py:79-89`) dedups
retrieved chunks by `chunk_id` in a dict, so a collision can silently drop a distinct chunk —
which can make a real field wrongly look "unsupported" and get dropped from a record. No test
exercises the hard-split branch.

### 1.3 Evidence citation spans can point at the wrong text
`pawpal_ai/evidence.py:73-88` finds a match index inside `normalize_text(chunk_text)`
(whitespace-collapsed, `textutils.py:61-62`) but slices the **original** `chunk_text` at that
same offset. Any whitespace run that collapses to fewer characters shifts every later offset,
so `SourceEvidence.supporting_text` — the citation this whole system is built around — can
point at a misaligned or wrong snippet. Only citation *presence* is tested
(`test_grounded_records_with_citations`), never its content, so this is invisible to CI.

### 1.4 Short values can be grounded by accident
`pawpal_ai/evidence.py:73-77` — plain substring match with no word-boundary check, scored a
flat `1.0`. A short/generic value (a 1–2 digit dosage, a short clinic code) can match inside
an unrelated substring (e.g. dosage `"10"` matching the `"10"` in date `"2025-03-10"`),
grounding a wrong value at maximum confidence. Undermines the "nothing unsupported reaches
storage" guarantee the module claims.

### 1.5 Locale-ambiguous / two-digit-year date parsing
`pawpal_ai/textutils.py:21,44-49` — `_SLASH_RE` assumes US `M/D/Y` ordering (a non-US
`25/12/2025` fails to parse rather than being flagged ambiguous), and any two-digit year is
unconditionally promoted to the 2000s (`03/15/50` → `2050`, not `1950`). A garbled date
silently becomes a plausible-looking future date that flows straight into
`compute_care_status` as CURRENT. Untested beyond canonical unambiguous inputs.

### 1.6 Contradiction detection has no per-pet isolation of its own
`pawpal_ai/contradictions.py:34-36,51-57,88-93` — `_key()` buckets only by
`(record_type, normalized name)`; `pet_id` is never part of the key. Two different pets both
vaccinated for "Rabies" on different dates, if ever passed into the same list, would be
reported as contradicting each other and have reminders blocked for both. The only current
caller (`pages/1_Health_Records.py:417-419`) happens to pre-filter by pet, so it's latent —
but the function has no defense-in-depth of its own, unlike `VectorStore.retrieve`'s
`document_id` filter.

### 1.7 Guardrail regex both over- and under-triggers
`pawpal_ai/guardrails.py:17-22`, used at `pawpal_ai/qa.py:40`. Under-triggers: a rephrased
diagnosis question ("why does my dog keep vomiting?") passes through untouched.
Over-triggers: a legitimate question about an *already-recorded* prescription — "when should
I give the Amoxicillin today?" — matches `should i (give|...)` and gets hard-refused, even
though answering it from the pet's own extracted medication schedule is exactly what this app
should safely do. Only the canonical textbook example is tested.

### 1.8 Overly narrow exception handling around the one call that's actually external
`pawpal_ai/extraction_agent.py:233-235` and `pawpal_ai/qa.py:54-56` only catch `LLMError`.
Any other exception (network timeout, an SDK-internal error, a parsing edge case not already
translated to `LLMError`) propagates uncaught and crashes the whole Streamlit run instead of
degrading gracefully — the one spot in the codebase where a broader catch is actually
justified is the narrowest one.

---

## Priority 2 — Security, beyond the leak already in Priority 0

- **Logging redaction is exact-key-match, and one real call site already bypasses it.**
  `logging_setup.py`'s `_REDACT_KEYS` denylist doesn't include `error`, so
  `extraction_agent.py:239` / `qa.py:57` (`log_event("...", error=str(exc)[:80])`) can leak
  up to 80 unredacted characters of an underlying LLM error message — which for JSON-parse
  failures often echoes fragments of the model's raw response.
- **Filenames aren't sanitized anywhere**, and there's currently no code path that persists
  raw uploaded bytes to disk at all (`ingest_bytes` only extracts text; `storage.py` stores
  `filename` as a DB string, never as a path). That's fine today, but if a future S3 upload
  path uses `doc.filename` directly as the object key, it becomes both a path-injection risk
  and the exact mechanism that caused the 0.1 leak. Decide this now: **generate opaque S3
  keys server-side (e.g. `uploads/{owner_id}/{uuid4()}{ext}`), store the original filename
  only as sanitized object metadata.**
- **Raw vendor errors reach the end user.** `pages/1_Health_Records.py:344` —
  `st.error(f"Extraction failed: {fatal_error}")` — shows raw exception text (e.g. `"Claude
  API error: Error code: 401 - {'type': 'error', ...}"`, visible in
  `ai_interactions.md:63-66`) straight to the user, exposing backend/provider internals.
  Map `LLMError` to a short, user-safe message and log the raw detail server-side only.
- **`unsafe_allow_html` is safe today only by accident of placement.** ~~All three call
  sites (`pages/1_Health_Records.py:223,450`, `app.py:313`) currently render only
  internally-constructed badge strings, never LLM/user-derived fields~~ — **update, dashboard
  redesign:** the app now has several more `unsafe_allow_html` call sites (a shared brand
  mark, pet cards, a sidebar owner summary, a Settings panel), and this time every
  interpolated user- or config-derived value (`pet.name`, `task.name`, `owner.name`,
  `llm.provider`) is passed through `html.escape()` first, including the one pre-existing
  gap this note originally flagged (`task.name` in `app.py`'s task-row markdown was
  unescaped; it now isn't). Still true that nothing *enforces* this boundary — a future edit
  could reintroduce an unescaped interpolation with no guardrail to catch it. Wrapping this
  in one helper that only accepts an enum/known-value, or escapes by default, remains worth
  doing.
- **`hashlib.md5()` without `usedforsecurity=False`.** `vectorstore.py:39` — on a FIPS-mode
  OpenSSL build (plausible on some AWS AMIs), plain `hashlib.md5()` raises at runtime. One-line
  fix, worth doing before deployment so it isn't a surprise in prod.

---

## Data layer & storage architecture (current state → S3-ready)

**Today:** `pawpal_ai/storage.py` is a single SQLite file (`Storage.__init__`, line 99-106,
opened with `check_same_thread=False` so Streamlit's threads can share one connection) — fine
for a single-user local demo, not for concurrent multi-user writes. `VectorStore` is
purely in-memory and explicitly **not** persisted (`vectorstore.py:69-72` docstring), rebuilt
per Streamlit session (`pages/1_Health_Records.py:43`). There's no eviction/TTL on it
(`VectorStore` has no `remove()`), so a long-running process (as opposed to a fresh `streamlit
run` per demo) grows memory unboundedly across every upload it's ever seen. Retrieval is also
a full scan over every chunk ever added, `document_id`-filtered only after scoring
(`vectorstore.py:96-109`) — fine for one session's handful of documents, not for a shared
store across many users.

**What "real S3-backed website" actually requires** (in order):

1. **Add owner/tenant scoping everywhere `pet_id` currently isn't enforced** — this is
   Priority 1.1 above, restated: don't build multi-user storage on top of a retrieval layer
   that doesn't already isolate by owner.
2. **Introduce a storage-backend abstraction** (e.g. `pawpal_ai/storage_backend.py` with a
   `LocalDiskBackend` and an `S3Backend` behind one interface), selected via `Settings`, so
   tests keep using local temp dirs and only the deployed app talks to S3.
3. **S3 bucket design:** one bucket, opaque keys
   (`uploads/{owner_id}/{uuid4()}-{sanitized-ext}`), default encryption (SSE-S3), block all
   public access, and use presigned URLs for upload/download rather than routing raw bytes
   through the Streamlit process if you move to a decoupled frontend/backend.
4. **Decide a retention policy for raw bytes.** Right now the app never persists the original
   uploaded file at all — only extracted text and structured fields. Moving to S3 is a bigger
   change than "swap local disk for a bucket": you're adding a new class of stored data
   (original documents) with its own privacy posture, which needs to be reflected in
   `model_card.md`'s current claim of no persistent raw-document storage.
5. **Move the database off single-file SQLite** once there's more than one concurrent writer
   — managed Postgres (RDS/Supabase/Neon) is the natural next step; keep SQLite for local dev
   and tests.
6. **Persist the vector index** (or rebuild it lazily per-document from S3-stored text) so a
   redeploy or horizontal scale-out doesn't silently drop or desync a user's RAG index
   mid-session.
7. **Add real authentication.** There's currently no login/account concept — `Owner` in
   `app.py:36-38` is just typed name + email with no verification, and identity lives only in
   Streamlit session state (`app.py:55-67`). This is the actual prerequisite for "S3 +
   multi-user website," not an optional nice-to-have — without it, nothing isolates one
   visitor's pets/documents from another's except browser session state. Budget real time for
   this; it's the biggest single scope item in this whole plan.
8. Fix `pawpal_ai/extraction_agent.py:68-72` (`append_trace`, hardcoded relative
   `"ai_interactions.md"` path, unrotated, no file locking) — not S3-aware and not safe for
   multiple app instances. Either drop this file entirely for the deployed app (keep it for
   local dev/demo only) or route it through the same storage backend as everything else.

Sample documents themselves are clean: every file in `data/sample_documents/` uses obviously
fake clinic/vet/pet names, and `generate_samples.py` only derives binaries from the two
synthetic `.txt` sources. No changes needed there.

---

## Frontend (`app.py`, `pages/1_Health_Records.py`)

### UX inconsistencies (the two pages feel like two different apps)
- **No loading state on the two actions that hit a real network API.** Neither "Extract
  records" (`pages/1_Health_Records.py:319-372`, which can call live Claude) nor "Ask"
  (`474-486`) wraps its call in `st.spinner(...)`, while `app.py:454-455` — which does purely
  local, synchronous work — explicitly shows one. The real trace log shows this manifesting as
  three sequential failed API calls with zero visual feedback before a raw error appears.
- **Inconsistent confirmation feedback.** Add-pet (`pages/1_Health_Records.py:68-74`) and
  Approve/Reject (`387-396`) rerun with no toast/success message at all, while nearly every
  mutating action in `app.py` (delete pet `129`, delete task `324-325`, update task `404-405`)
  shows one first. A rejected record also just vanishes with no undo.
- **Silent no-op on blank input.** The Extract button explicitly flags a missing input
  (`st.error(...)`, line 326); the Ask button silently does nothing if the question is blank
  (`if st.button("Ask", ...) and q.strip():`, line 474) — no feedback either way.
- **Internal debug config leaked into the UI.** `pages/1_Health_Records.py:92-99` renders raw
  tuning parameters (`provider=`, `k=`, `max_attempts=`, `evidence_threshold=`,
  `due_soon_days=`) via `st.code(...)` directly to the end user — reads as a debug panel left
  in, not a product screen.
- **Page chrome doesn't match.** `app.py:13` sets `page_icon="🐾"` and `layout="centered"`;
  `pages/1_Health_Records.py:31` sets no page icon and uses `layout="wide"` — switching pages
  in the same multipage app feels like two stitched-together apps.
- **Misleading copy not backed by the code.** `pages/1_Health_Records.py:401-404` shows
  "Updated {field}. (Human-authored edits are tracked.)" after a field edit, but the edit only
  mutates the in-memory object — no audit-log call happens until/unless the record is later
  approved (`storage.py`'s only audit-writing methods are `save_document`, `save_record`,
  `set_review_status`, `save_reminder`, `save_conflict` — an edit alone isn't one of them).
  Either wire edits into the audit log or drop the claim.

### Code quality
- **The same "colored pill badge" is hand-built three separate times** with drifting specs:
  `app.py:22-28` (`priority_badge`, `padding:2px 12px; border-radius:12px`),
  `pages/1_Health_Records.py:202-208` and `246-258` (`padding:0.16rem 0.55rem;
  border-radius:999px`). Factor into one shared helper.
- **A citation-cleanup regex is implemented twice.** `pawpal_ai/qa.py:82-88`
  (`_redact_internal_source_ids`) already strips `doc_x#chunk-n` markers from every answer
  before it's returned (applied at `qa.py:55`). `pages/1_Health_Records.py:140-142,150-151`
  re-implements the identical regex and re-applies it to the already-cleaned answer at lines
  477/479/481 — a UI layer that has learned an internal RAG implementation detail it
  shouldn't need to know about. Delete the duplicate; if the business layer's cleanup is
  incomplete somewhere, fix it there.
- **No functions/components** — both `app.py` and `pages/1_Health_Records.py` are long,
  flat, module-level scripts (`pages/1_Health_Records.py:308-499` is five straight-line
  `st.tabs` blocks). Neither is unit-testable independent of Streamlit, and the pattern is
  duplicated rather than factored into a shared page-rendering convention.
- **Schema-adjacent config lives in the wrong file.** `_FIELD_LABELS`/`_FIELD_ORDER`
  (`pages/1_Health_Records.py:162-180`) describe the `health_models.py` schema but live in the
  UI file — adding a field means editing two unrelated files to stay in sync.
- Minor: mid-function `import uuid` (`pages/1_Health_Records.py:69`) instead of at the top;
  unnamed magic numbers (text-area height `140` at line 317, grid chunk size `3` at line 226,
  audit-trail `limit=50` at line 493).

**Keep:** the Review/Reminders/Ask tabs (`pages/1_Health_Records.py:216-289,469-486`) show
real design effort — per-field citations with match scores, human-readable due-date phrasing,
schema-driven field ordering, and status badges that are color **and** text labeled (not
color-only). This tab set is more thoughtfully composed than the scheduler page's equivalent.

---

## Code quality inside `pawpal_ai/` (beyond the correctness bugs above)

- **Three parallel "what happened" channels for one event**: `Tracer`
  (`extraction_agent.py:51-65`, → `ai_interactions.md`), `log_event` (structured JSON), and
  `ExtractionResult.notes = list(tracer.steps)` (`extraction_agent.py:300`) all record
  overlapping human-readable strings for the same run. The module's own docstring says why
  (the rubric — see §0.2); now that this is judged as a product, collapse to one source of
  truth (structured log) and derive the others from it if still needed.
- **Conflict-detection logic implemented twice.** `contradictions.py`'s `detect_conflicts`
  (lines 48-81) and `conflicted_record_ids` (84-104) independently re-implement the same
  bucket-by-`(type, name)` + pairwise-scan logic — a fix to one (e.g. the missing `pet_id` key
  in §1.6) is easy to apply to only one copy.
- **Duplicated constant**: `[30, 14, 7, 1, 0]` appears both as `reminders.py:30`
  (`DEFAULT_OFFSETS`) and as the Pydantic default for `Reminder.offsets_days`
  (`health_models.py:153`) — one should import the other.
- **Dead code that exists to be unit-tested, not to guard anything.** `can_save_record`
  (`guardrails.py:39-48`) is tested (`tests/test_pawpal_ai.py:316-320`) but never called from
  the real save path — `pages/1_Health_Records.py:388-390` sets `review_status = APPROVED`
  and calls `db.save_record` directly, bypassing it. `assert_no_ungrounded_fields`
  (`guardrails.py:51-61`) and `overdue_repeat_dates` (`reminders.py:137-141`) are fully
  written and documented but never called anywhere. Either wire these in or delete them.
- **Rigid, templated module docstrings** — nearly every file in `pawpal_ai/` opens with the
  identical rhetorical shape (bold claim → "why not X" → "guarantees" callout — e.g.
  `vectorstore.py:1-14`, `reminders.py:1-13`, `health_models.py:1-14`). Individually fine,
  but the uniformity across ~12 files reads as "each file was prompted independently," which
  is exactly the tell you're trying to get rid of. Vary the voice, or trim these to what's
  actually load-bearing.
- Minor: a nested list-comprehension membership test in `evaluation/run_eval.py:125`
  (`r.record_id in [x.record_id for x in reminders]`) is harder to read than two named
  variables; `evaluation/ablation.py:39-53` subclasses `MockLLM` and overrides a
  underscore-prefixed "private" method (acknowledged fragile via its own
  `# type: ignore[override]`), so any refactor of `MockLLM` internals silently breaks the
  ablation script with nothing to catch it.

**Keep and highlight — these are genuinely strong, not AI boilerplate:** the plan→act→
check→revise retry loop's retryable-vs-fatal error distinction
(`extraction_agent.py:240-251`); the evidence-or-null grounding contract that's the real
anti-hallucination mechanism and demonstrably works end-to-end in the tests; `reminders.py`'s
`verify_reminder` re-deriving a date from the source record as a second check
(`reminders.py:95-109`); the proactive log redaction + rotation in `logging_setup.py`; and
the evaluation harness + ablation study (`evaluation/run_eval.py`, `evaluation/ablation.py`),
which actually runs the real pipeline against labeled cases and quantifies claims (retrieval
changes output, grounding prevents fabrication) instead of just asserting them. This last one
in particular is unusual rigor for a portfolio project — see §6 on how to present it.

---

## Test coverage gaps

- `tests/test_edge_cases.py` and `tests/conftest.py` **only** test `pawpal_system` (the
  original scheduler) — despite sitting next to `test_pawpal_ai.py` and being named "edge
  cases," they provide zero coverage of the RAG/extraction system. Easy to assume this file
  covers AI-system edge cases from its name/placement alone; it doesn't.
- No test exercises `chunking.py`'s hard-split path → the `chunk_id` collision bug (§1.2) is
  invisible to CI.
- No test asserts the *content* of `SourceEvidence.supporting_text`, only its presence → the
  span-misalignment bug (§1.3) is invisible to CI.
- No test builds a multi-document/multi-pet `VectorStore` → the cross-pet leak (§1.1) is
  invisible to CI.
- `pawpal_ai/prompts.py` and `pawpal_ai/logging_setup.py` have zero test references anywhere.
- No boundary test around `qa.py`'s `_MIN_RELEVANCE = 0.08` abstention cutoff.
- `textutils.parse_date` is only tested against unambiguous canonical inputs (§1.5 untested).
- No unit tests for `evaluation/run_eval.py`'s scorer functions or `evaluation/ablation.py` —
  a bug in a scorer would only be caught by a human reading printed output.
- No mixed-pet input test for `contradictions.py` (§1.6 untested).
- `reminders.py`'s medication non-reminder path (`_DUE_FIELD[MEDICATION] = None`) has no
  dedicated test, and `overdue_repeat_dates` has none at all.

---

## Making this read as real engineering, not a class project

This is the part that most directly answers "recruiters can see it looks like AI." The
underlying engineering is genuinely solid — grounded RAG extraction, a real evaluation +
ablation harness, a thoughtful human-in-the-loop approval flow. The "looks like AI" read is
coming from **presentation and repo history**, not primarily from the implementation:

1. **Clean up git history and the "rubric" language** — §0.2. This is the highest-leverage
   single change; it's the difference between a recruiter seeing a coherent engineering
   project versus seeing "codepath/claude/add-ai-grading-scaffold" in the second command they
   run.
2. **Delete or merge `IMPLEMENTATION_SUMMARY.md` and `RECURRING_TASKS_GUIDE.md`.** Both
   document the same one-method feature (`Task.calculate_next_due_date`/
   `create_next_occurrence`) with overlapping code samples, heavy emoji section markers
   (✓ 📋 🎯 💡 🧪 📁 🚀 🔮), and near-identical closing lines —
   `IMPLEMENTATION_SUMMARY.md:209` "The system is production-ready! 🎉" and
   `RECURRING_TASKS_GUIDE.md:228` "The recurring task system is now production-ready!" for a
   single method. This is the clearest "unedited AI chat summary pasted into the repo root"
   tell in the whole project. Fold anything worth keeping into one short doc in your own
   voice, or delete both.
3. **Rewrite `reflection.md`.** The section headers are the literal assignment prompt text
   left in place (`reflection.md:14,17-18,80-81,91-92,115-116,128-129,135-136,146,152,157` —
   "Briefly describe your initial UML design," "Did your design change during
   implementation?", etc.). The *answers* underneath are genuinely good and specific — a real
   anecdote about redesigning the UI from a hand sketch, a concrete example prompt, a specific
   account of hitting the ChromaDB/MSVC build issue and verifying it by actually trying the
   install. Turn this into flowing first-person prose organized around what you actually did,
   not the interview questions that prompted it.
4. **Keep and foreground the evaluation harness, the ablation study, and the model card's
   responsible-AI section** — these are the parts of the project real engineers will actually
   respect, and they're rare in portfolio projects. Feature them explicitly in the README's
   opening (not buried at the bottom), e.g. "grounding is measured, not assumed — see the
   retrieval ablation" as a pull-quote.
5. **Ship a live demo link.** Nothing you do to the docs matters as much as a working URL a
   recruiter can click. ~~Even a single-user Streamlit Community Cloud deploy with the mock
   provider (no API key needed) beats any amount of README polish.~~ — **update, post-cutover:**
   Streamlit Community Cloud is no longer a possible target; the app is a FastAPI + React
   container now. The deploy target is any container host that runs an image and injects
   `$PORT` (Cloud Run, Railway, Fly), which the `Dockerfile` already honours. The point itself
   is unchanged, and the mock provider still means the demo needs no API key — note also that
   leaving `PAWPAL_OWNER_KEY` unset on such a deploy is the safe default, not a broken one: the
   two LLM-calling endpoints return 503 rather than standing open to whoever finds the URL.
6. **Add the repo signals experienced engineers look for and this repo currently lacks:** a
   `LICENSE` file, a `pyproject.toml` (or at least pinned versions in `requirements.txt`
   instead of open `>=` ranges), a lint/format config (`ruff`/`black`), and — most
   importantly — **CI**. There's no `.github/workflows/` at all right now; a green "tests
   passing" badge from an Actions run of `pytest -q` is a stronger, cheaper signal than
   anything in the markdown docs.

---

## Deployment roadmap (concrete order of operations)

1. Fix §1.1 (owner/pet scoping through the vector store and Q&A) — do this before anything
   below, since every later step assumes retrieval is already isolated per user.
2. Add `.github/workflows/ci.yml` running `pytest -q` (and a linter) on every PR.
3. ~~Add a `Dockerfile` (the app + `requirements.txt`, `streamlit run app.py --server.port
   $PORT`)~~ **— DONE, though not as sketched here.** Streamlit is gone (see
   `MIGRATION_PLAN.md`), so the image at the repo root is multi-stage instead: a Node stage
   runs `npm run build`, and the Python runtime stage runs
   `uvicorn api.main:app --port ${PORT:-8000}` as a non-root user, serving the JSON API and
   the built SPA from that one port. The goal this step was after — deploy target doesn't
   matter, local/prod parity holds — is met; mount a volume at `/app/data` so the SQLite file
   survives a redeploy.
4. Introduce the storage-backend abstraction (local disk vs. S3) described above; keep tests
   on the local backend.
5. Stand up an S3 bucket per the key/encryption/access design above; wire uploads through it
   behind the new abstraction.
6. Move secrets (`ANTHROPIC_API_KEY`, AWS credentials) out of `.env` for anything beyond local
   dev — AWS Secrets Manager or SSM Parameter Store for the deployed environment; commit the
   new `.env.example` (§0.3) for local dev only.
7. If you need real multi-user isolation (not just a personal single-user deploy), add
   authentication — this is the biggest scope item here, budget for it explicitly rather than
   treating it as an afterthought.
8. Move SQLite to managed Postgres once there's more than one concurrent writer; otherwise a
   single-writer SQLite file is a legitimate, honest choice for a single-user personal deploy
   and doesn't need to change.
9. Add basic observability (structured logs to CloudWatch or similar; optionally Sentry for
   error tracking) — you already have redaction-aware structured logging in
   `logging_setup.py`, this step is mostly "ship it somewhere durable," not "build it."

---

## What's already good (don't lose this while cleaning up)

- The RAG grounding design is real: every non-null extracted field must be independently
  supported by a retrieved passage or it's dropped before it ever reaches storage — this is
  the actual mechanism, not a description of one, and the tests prove it end-to-end.
- The evaluation harness and retrieval ablation are genuine, falsifiable engineering
  artifacts (`evaluation/evaluation_report.md`'s 17/17 case table,
  `evaluation/evaluation_ablation.md`'s k=0-vs-k=4 comparison) — most portfolio projects
  assert their system works; this one measures it.
- The human-in-the-loop approval + audit-log design (`storage.py`'s `audit_log` table,
  written on every save/approve/reject/reminder) is a legitimate, well-reasoned safety
  pattern for a medical-adjacent tool, not boilerplate.
- Prompt-injection handling treats uploaded documents as untrusted data by design
  (`documents.py:23-32`, always-on `<untrusted_document>` framing in `prompts.py:57-67`
  regardless of whether the flag fired) — a real defense-in-depth choice, not an
  afterthought.
- `data/sample_documents/` is legitimately clean synthetic data, and the `.gitignore`
  (`.gitignore:9-16`) shows a deliberate, explained decision about what evaluation artifacts
  to commit versus ignore — that's a real engineering judgment call worth keeping as-is.
- The mock-provider-by-default design (zero-cost, zero-key, fully reproducible tests/demo) is
  a genuinely good architectural call for both grading *and* for letting a recruiter run the
  whole thing with no setup friction — keep this front and center in the README.
