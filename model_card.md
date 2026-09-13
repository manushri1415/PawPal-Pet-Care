# Model Card — PawPal AI

## System purpose

PawPal AI organizes a pet's existing veterinary documents into structured,
source-cited health records and generates deterministic reminders. It is an
**organization and reminder tool**, not a diagnostic or clinical decision-making
system.

## Intended users

Pet owners managing vaccination, medication, and appointment records for their
own pets, extending the PawPal+ scheduler.

## Intended use

- Extracting structured facts (vaccine names/dates, medication dosage/frequency,
  appointment dates) that are **explicitly present** in an uploaded document.
- Answering questions about a pet's uploaded records, grounded in retrieved
  passages, with citations.
- Generating reminders **only** from due dates that are explicit in a document
  or an interval the user confirms.

## Out-of-scope use

- Diagnosis, prescription, or new-treatment recommendations (explicitly refused
  — see `guardrails.py::is_medical_advice_request`).
- Inferring a due date, dosage, frequency, or duration from general veterinary
  knowledge when it is not stated in the document.
- Legal/insurance recordkeeping, multi-user access control, or any use beyond a
  single owner's informational reference.

## Model / API used

- **Default (mock):** a deterministic, rule-based extractor
  (`pawpal_ai/llm.py::MockLLM`) — no API key, fully reproducible. It still reads
  the *retrieved* passages, so retrieval genuinely drives its output.
- **Optional (live):** Anthropic **`claude-haiku-4-5`** via `messages.parse`
  structured output (`pawpal_ai/llm.py::ClaudeLLM`), used to process new
  documents. Configurable via `PAWPAL_MODEL`.

## Data and document sources

All sample documents in `data/sample_documents/` are **synthetic**, authored for
this project, and contain no real medical data or personally identifying
information. No third-party or real user documents were used.

## RAG design

Documents are chunked (`chunking.py`) with provenance metadata, embedded with a
deterministic local feature-hashing embedding (`vectorstore.py` — no model
download, no key), and retrieved by cosine similarity for each extraction
concept (vaccination / medication / appointment) and for Q&A. Every non-null
extracted field must be independently supported by a retrieved passage
(`evidence.py`) or it is dropped; this is what stops fabricated values from
reaching storage.

**Proof retrieval changes behavior** (`evaluation/ablation.py`):

| retrieval k | records extracted |
|---|---|
| 0 | 0 |
| 2 | 4 |
| 4 | 4 |

**Proof grounding/specialization prevents fabrication:** a baseline extractor
that guesses a due date (administered date + 1 year) vs the specialized
grounded pipeline, on a document with an administered date but no due date:

| system | invented a due date? |
|---|---|
| Baseline (guesses +1 year) | **Yes** — `2026-06-10` |
| Specialized grounded pipeline | **No** — `null`, flagged missing |

Full output: [`evaluation/evaluation_ablation.md`](evaluation/evaluation_ablation.md).

## Reliability evaluation

`evaluation/run_eval.py` runs 17 labeled cases (mock provider, reproducible with
no key) covering clean extraction, missing/ambiguous dates, irrelevant content,
prompt injection, contradictions, duplicate documents, unsupported/empty files,
answerable/unanswerable/advice-seeking questions, and the approval-gates-reminders
guardrail. **Result: 17/17 passed (100%)** — see
[`evaluation/evaluation_report.md`](evaluation/evaluation_report.md) for the
per-case table and computed metrics (extraction, contradiction-detection, QA
abstention/refusal, and guardrail success rates all measured at 1.0 on this
suite). The 250-test pytest suite (`tests/test_pawpal_ai.py`,
`tests/test_pawpal.py`, `tests/test_edge_cases.py`, `tests/test_api_scheduler.py`,
`tests/test_api_health.py`, `tests/test_ai_gate.py`, `tests/test_spa_serving.py`)
locks in the same behaviors as regression tests.

## Known limitations

- The offline **mock** extractor is regex/keyword-based; it is reliable on the
  clearly-labeled sample documents but weaker than a real LLM on unusual
  document layouts, handwriting-derived OCR text, or non-English documents.
- **Multi-pet documents** are extracted but all attributed to the currently
  active pet in the UI; the system flags a name mismatch but doesn't yet
  auto-split records per pet.
- **Contradiction detection** compares same-type, same-name records only; it
  will not catch a contradiction expressed under a different vaccine synonym
  the canonicalization table doesn't know.
- **No fine-tuning was performed.** "Specialization" here means few-shot
  structured prompting plus the deterministic grounding layer, not a trained
  model — a genuine, cheaper way to constrain behavior for this scope.
- The local hashing-embedding retriever is weaker than a neural embedding model
  on paraphrase-heavy queries; it works well here because vet documents reuse
  the vocabulary of the question (e.g. "due date", "dosage").

## Safety risks

- **Hallucinated clinical values** — mitigated by null-when-absent prompting +
  mandatory field-level evidence grounding (unsupported values are dropped, not
  surfaced).
- **Prompt injection in uploaded documents** — mitigated by scanning for
  injection patterns, framing all document text as untrusted data inside
  explicit delimiters, and — most importantly — requiring human approval before
  anything is saved, so even a successful injection can't act on the system.
- **Users treating output as medical advice** — mitigated by an explicit refusal
  for diagnosis/prescription/treatment questions and a UI disclaimer.

## Privacy considerations

- Logs (`logging_setup.py`) are structured JSON lines with a hard redaction list
  (document text, medication instructions, prompts/answers, API keys, names,
  emails) and a length-based backstop for anything else unexpectedly long.
  Rotated at 1 MB / 3 backups.
- Sample documents contain no real PII by design.
- SQLite storage is local-only; no telemetry or external logging is performed.

## Bias / failure risks

- The mock extractor's keyword list (vaccine names, medication suffixes) is not
  exhaustive and may under-extract uncommon terms; this is a coverage gap, not
  a systematic bias, and is mitigated by falling back to Claude for real
  documents where quality matters most.
- Date parsing supports ISO, `M/D/Y`, and `Month D, YYYY` formats; a document
  using a different locale's date convention (`D/M/Y`) could be misparsed. This
  is a known, documented limitation rather than a silent failure — invalid
  dates return `None` rather than a wrong date.

## Human-oversight design

Every record starts `PENDING`. Only records a human explicitly marks
`APPROVED` can be persisted for scheduling or generate a reminder
(`guardrails.py::can_save_record`, enforced in `reminders.py::build_reminder`).
Every approval, rejection, save, and reminder is written to an append-only
`audit_log` table (`storage.py`), visible in the app's **Audit** tab.

---

## Responsible-AI reflection

**1. How I collaborated with AI while building this project.** I worked with
Claude Code iteratively, in the order the plan laid out: cleanup and scaffolding
first, then each pipeline stage (documents → chunking → retrieval → LLM
interface → agentic extraction → guardrails/reminders → Q&A → UI → evaluation →
docs), verifying each stage with a real run before moving to the next rather
than writing the whole system and debugging it at the end.

**2. A helpful AI suggestion.** When I raised the "why do we need an API"
question, the AI suggestion to **separate retrieval (which can be 100% local
and free) from the LLM (the one component that actually needs "AI") and give the
LLM two interchangeable implementations — a deterministic mock and a real Claude
client** — was the single most useful design decision in the project. It made
the whole system gradeable/runnable with zero credentials while still keeping a
real AI path for genuine use, which is exactly the reproducibility the rubric
rewards.

**3. A flawed AI suggestion, and what was wrong with it.** The default plan
called for **ChromaDB** as the vector store, based on the (initially reasonable)
assumption that a "real" vector database would look more credible than a
hand-rolled one. In practice, installing it required compiling `chroma-hnswlib`
against Microsoft Visual C++ Build Tools — a compiler that is not installed on
this machine (or a typical grader's machine). The dependency would have made the
project **fail to install out of the box**, directly undermining "runs
reproducibly" and "setup steps are complete." This was flawed not because Chroma
is a bad library, but because reaching for the heaviest available tool for a
task (indexing a handful of short text chunks) ignored the actual reproducibility
constraint.

**4. How I verified or rejected it.** I ran `pip install -r requirements.txt` in
a clean venv and watched it fail with an explicit MSVC error before accepting the
suggestion. I rejected the Chroma dependency and replaced it with a small,
dependency-light module (`vectorstore.py`) — feature-hashing embeddings +
NumPy cosine search — that installs everywhere Python does, verified by
re-running the install and the full test suite (118 passed — the suite's size
at the time; it is 250 today) afterward. I did
not just take the AI's word that the replacement was "good enough"; I ran the
retrieval ablation (`evaluation/ablation.py`) to confirm it still meaningfully
changes extraction behavior (k=0 → 0 records vs k=4 → full extraction), which is
the property that actually matters for the rubric, not the specific library.

**5. Limitations of the final system.** It's still a rule-based mock in the
default mode; the vector store is a simple hashing embedding, not a neural one;
multi-pet documents need human correction; and no real fine-tuning was
performed (few-shot prompting + deterministic grounding stand in for it).

**6. What users should not rely on this system to do.** Diagnose or treat a
pet, decide medication dosages, guarantee that every vaccine due date has been
captured (always cross-check with your vet), or make decisions from an
unapproved (PENDING) record — only approved records are verified by a human and
should be trusted.
