# AI Interaction & Agent Reasoning Traces

This file captures the **agent's intermediate reasoning traces** for the PawPal
AI extraction workflow (the "plan → act → check → revise" loop in
`pawpal_ai/extraction_agent.py`). Traces are appended automatically whenever a
document is processed with `write_trace=True` (the Streamlit **Upload** tab and
`demo_pawpal_ai.py` do this). Each trace shows the retrieval plan, which chunks
were retrieved, the grounded/unsupported fields per attempt, and the final
hand-off to human review.

> Regenerate the traces below anytime with: `python demo_pawpal_ai.py`

---

## Extraction trace — max_vaccine.pdf (2026-08-02 16:19)

1. PLAN: chunked document into 1 chunks; queries = ['vaccination', 'medication', 'appointment']
2. ACT: retrieved chunks ['demo_max#chunk-0'] (retrieval drives what the model sees)
3. CHECK attempt 1: 4 grounded record(s); 0 unsupported field(s) dropped.
4. CHECK: missing important fields -> ['appointment[Wellness Exam].appointment_date']
5. DONE: 4 record(s) PENDING human review after 1 attempt(s).
