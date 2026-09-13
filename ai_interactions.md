# AI Interaction & Agent Reasoning Traces

This file captures the **agent's intermediate reasoning traces** for the PawPal
AI extraction workflow (the "plan → act → check → revise" loop in
`pawpal_ai/extraction_agent.py`). Each trace shows the retrieval plan, which
chunks were retrieved, the grounded/unsupported fields per attempt, and the
final hand-off to human review.

**What writes here:** `demo_pawpal_ai.py` alone, which calls `append_trace()`
explicitly on the trace from the document it walks through. The web app does
not: the only other writer is `process_document(..., write_trace=True)`, and
`api/services/health_service.py` never passes that flag — so uploading a
document through the UI records nothing in this file. That is deliberate. This
is a committed narrative artifact regenerated from synthetic samples, not a
runtime log (the runtime log is the redaction-aware JSON one in `logs/`), and
appending real uploads to a tracked file is exactly how a real filename leaked
into it once before — see `UPGRADES.md` §0.1.

> Regenerate the traces below anytime with: `python demo_pawpal_ai.py`

---

## Extraction trace — document-03c1b8396d.pdf (2026-09-11 16:43)

1. PLAN: chunked document into 1 chunks; queries = ['vaccination', 'medication', 'appointment']
2. ACT: retrieved chunks ['demo_max#chunk-0'] (retrieval drives what the model sees)
3. CHECK attempt 1: 4 grounded record(s); 0 unsupported field(s) dropped.
4. CHECK: missing important fields -> ['appointment[Wellness Exam].appointment_date']
5. DONE: 4 record(s) PENDING human review after 1 attempt(s).
