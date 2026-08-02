"""End-to-end CLI demo of the PawPal AI pipeline (no API key needed).

Runs a sample vet document through the full workflow and prints each stage, so
you can see the system working end-to-end from the terminal::

    python demo_pawpal_ai.py

Also appends the agent's reasoning trace to ``ai_interactions.md``.
"""

from __future__ import annotations

from datetime import date

from pawpal_ai.config import get_settings
from pawpal_ai.documents import ingest_path, ingest_text
from pawpal_ai.extraction_agent import append_trace
from pawpal_ai.health_models import ReviewStatus
from pawpal_ai.llm import build_llm
from pawpal_ai.pipeline import approve_and_schedule, process_document
from pawpal_ai.qa import answer_question
from pawpal_ai.vectorstore import VectorStore

RULE = "=" * 64


def banner(title: str) -> None:
    print(f"\n{RULE}\n{title}\n{RULE}")


def show_records(records) -> None:
    for rec in records:
        print(f"  • {rec.record_type.value}  (confidence {rec.confidence})")
        for f, v in rec.fields.items():
            if v is None:
                print(f"      {f}: (not found)")
            else:
                ev = rec.evidence.get(f)
                cite = f"  [source {ev.chunk_id}: “{ev.supporting_text[:40]}…”]" if ev else ""
                print(f"      {f}: {v}{cite}")


def main() -> None:
    settings = get_settings()
    llm = build_llm(settings)
    store = VectorStore()

    banner(f"PawPal AI demo — provider: {llm.provider}")

    # 1) A clean vaccine document -> proposed records + reminder.
    banner("1) Upload a vaccine document (Max)")
    doc = ingest_path("data/sample_documents/max_vaccine.pdf")
    print(f"Ingested {doc.filename}: ok={doc.ok}, {doc.char_count} chars, injection={doc.injection_flagged}")
    processed = process_document(doc, "max", llm, settings, store=store, document_id="demo_max")
    append_trace(processed.tracer)
    print(f"\nExtracted {len(processed.result.records)} PENDING record(s):")
    show_records(processed.result.records)

    banner("2) Human approves the records, system schedules reminders")
    for rec in processed.result.records:
        rec.review_status = ReviewStatus.APPROVED
    reminders, conflicts, blocked = approve_and_schedule(processed.result.records, today=date(2025, 7, 1))
    print(f"Conflicts: {len(conflicts)}, blocked: {len(blocked)}")
    for rem in reminders:
        print(f"  🔔 {rem.label}: due {rem.due_date} ({rem.care_status.value}); alerts {rem.offsets_days} days before")

    # 3) A second, conflicting Max record -> contradiction warning, reminder blocked.
    banner("3) A conflicting Max record arrives")
    doc2 = ingest_path("data/sample_documents/max_vaccine_conflicting.txt")
    processed2 = process_document(doc2, "max", llm, settings, store=store, document_id="demo_max2")
    all_records = processed.result.records + processed2.result.records
    for r in all_records:
        r.review_status = ReviewStatus.APPROVED
    reminders2, conflicts2, blocked2 = approve_and_schedule(all_records, today=date(2025, 7, 1))
    for c in conflicts2:
        print(f"  ⛔ CONFLICT {c.record_type.value}.{c.field}: '{c.value_a}' vs '{c.value_b}'")
    print(f"  Rabies reminders after conflict: blocked ({len(blocked2)} records); "
          f"{len(reminders2)} reminder(s) still generated for non-conflicting records.")

    # 4) Grounded Q&A + abstention + refusal.
    banner("4) Ask questions (grounded, with abstention + refusal guardrails)")
    for q in [
        "When is Max's rabies vaccine due?",
        "What is the capital of France?",
        "What medicine should I give my dog?",
    ]:
        ans = answer_question(q, store, llm, k=settings.retrieval_k)
        tag = "REFUSED" if ans.refused else ("ABSTAINED" if ans.abstained else "ANSWERED")
        print(f"\n  Q: {q}\n  [{tag}] {ans.answer[:100]}")
        if ans.citations:
            print(f"  sources: {[c.chunk_id for c in ans.citations]}")

    banner("Done — trace appended to ai_interactions.md")


if __name__ == "__main__":
    main()
