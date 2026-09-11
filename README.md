# 🐾 PawPal AI — Pet Health Record & Reminder Assistant

PawPal AI turns messy veterinary paperwork into **verified, source-cited health
records and reliable reminders**. You upload a vet document (PDF/DOCX/TXT) or
paste text; a retrieval-augmented, multi-step AI agent proposes structured
records **grounded in the exact source passages**; you approve, edit, or reject
each one; and deterministic Python turns the approved facts into reminders and
contradiction warnings — never inventing a due date, dosage, or frequency.

> **Runs with no API key.** The default `mock` provider makes the entire app,
> its 118 tests, and the evaluation harness reproducible offline. A key is only
> needed to process brand-new documents with the live Claude model.

---

## The original project: PawPal+

This project **extends PawPal+**, an object-oriented pet-care scheduler built in
an earlier module. PawPal+ lets an owner manage pets and recurring care tasks
(walks, feeding, meds), sort tasks by priority/time, detect scheduling
conflicts, and generate a prioritized daily schedule through a Streamlit UI. Its
domain layer (`pawpal_system.py`) and ~81 pytest tests are preserved and still
run; PawPal+ is now the **Scheduler** page (`app.py`).

**What PawPal AI adds:** a whole health-record subsystem — document ingestion,
RAG-based agentic extraction, human review, source citations, contradiction
detection, and a deterministic reminder engine — on the new **Health Records**
page. Where PawPal+ relied on manual task entry, PawPal AI reads the documents.

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
Contradiction check → Human review → SQLite → Reminder engine → Dashboard
                                          ↘ RAG Q&A ↗        ↘ Reliability evaluator
```

| Concern | Where | Kind |
|---|---|---|
| Interpret documents, answer questions | `llm.py`, `qa.py` | **AI** |
| Retrieval (embeddings + vector store) | `vectorstore.py` | local, no key |
| Schema, dates, status, reminders, conflicts, persistence | `health_models.py`, `reminders.py`, `contradictions.py`, `storage.py` | **Deterministic** |
| Approve/edit/reject before save | `pages/1_Health_Records.py` | **Human review** |
| Evidence grounding, injection framing, approval gate, refusal | `evidence.py`, `guardrails.py`, `documents.py` | **Guardrails** |
| Reliability metrics + ablations | `evaluation/` | **Evaluation** |

**Why these choices:** RAG grounds every value in a real passage so the model
can't hallucinate; human approval is required because these are medical records;
deterministic Python owns dates/reminders because those are safety-critical and
must be exact; the vector store is a dependency-light pure-Python implementation
(local hashing embeddings + cosine) so the project builds on any machine with no
C++ compiler and no model download (a heavier DB like Chroma needs to compile
native wheels, which fails on stock Windows/Python 3.13). SQLite gives
zero-setup persistence.

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

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment (optional — defaults work with no key)
copy .env.example .env         # Windows  (cp on macOS/Linux)
#   leave PAWPAL_LLM_PROVIDER=mock to run offline with no key, or set
#   PAWPAL_LLM_PROVIDER=claude and ANTHROPIC_API_KEY=... for live extraction

# 5. (First run) generate the binary sample documents
python data/sample_documents/generate_samples.py
#   The SQLite DB is created automatically on first use.

# 6. Run the app  (top nav bar: Dashboard = Scheduler, Health Records)
streamlit run streamlit_app.py

# 7. Run the tests
pytest -q

# 8. Run the reliability evaluation (prints a pass/fail summary)
python evaluation/run_eval.py
python evaluation/ablation.py

# 9. Run the end-to-end CLI demo
python demo_pawpal_ai.py
```

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
  no multi-pet-per-document splitting, no notification delivery, no access
  control — see `model_card.md`.

---

## Testing summary

- **118 tests pass** (`pytest -q`): 81 original PawPal+ scheduler tests + 37 new
  PawPal AI tests covering document validation, extraction, evidence grounding,
  invalid dates, contradiction detection, reminder rules, the approval guardrail,
  prompt-injection handling, LLM-failure + retry-limit paths, and an end-to-end
  upload→approve→reminder flow.
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
streamlit_app.py           Entry point — top nav bar routing between the two pages below
app.py                     PawPal+ scheduler — "Dashboard" tab
pages/1_Health_Records.py  PawPal AI health-record UI — "Health Records" tab
pawpal_system.py           Canonical domain model (scheduling)
pawpal_ai/                 The AI system (config, documents, chunking, vectorstore,
                           llm, prompts, extraction_agent, evidence, qa, reminders,
                           contradictions, guardrails, storage, logging)
data/sample_documents/     Synthetic vet documents (no real PII)
evaluation/                run_eval.py, ablation.py, cases + generated reports
docs/system_architecture.mmd
tests/                     118 tests
model_card.md              Responsible-AI reflection & limitations
ai_interactions.md         Agent reasoning traces
demo_pawpal_ai.py          End-to-end CLI demo
```
