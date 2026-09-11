"""PawPal AI reliability evaluation harness.

Runs the labeled cases in ``evaluation_cases.json`` through the real pipeline
(default: mock provider, no API key -> fully reproducible), scores each one,
prints a pass/fail summary, and writes:

  - evaluation_results.json   (machine-readable, per-case + metrics)
  - evaluation_report.md      (human-readable table + summary)

Usage::

    python evaluation/run_eval.py          # mock provider (default)
    python evaluation/run_eval.py --live    # use Claude if a key is configured

This doubles as the "test harness" bonus: it evaluates multiple predefined
inputs and prints a summary score.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

# Allow running as `python evaluation/run_eval.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pawpal_ai.config import get_settings  # noqa: E402
from pawpal_ai.contradictions import conflicted_record_ids, detect_conflicts  # noqa: E402
from pawpal_ai.documents import ingest_bytes, ingest_path, ingest_text  # noqa: E402
from pawpal_ai.extraction_agent import extract_records  # noqa: E402
from pawpal_ai.health_models import RecordType, ReviewStatus  # noqa: E402
from pawpal_ai.llm import build_llm  # noqa: E402
from pawpal_ai.pipeline import approve_and_schedule  # noqa: E402
from pawpal_ai.qa import answer_question  # noqa: E402
from pawpal_ai.reminders import compute_care_status  # noqa: E402
from pawpal_ai.textutils import parse_date  # noqa: E402
from pawpal_ai.vectorstore import VectorStore  # noqa: E402

HERE = Path(__file__).resolve().parent
CASES_PATH = HERE / "evaluation_cases.json"


def _ingest(case: dict):
    if "input_file" in case:
        return ingest_path(case["input_file"])
    if "input_bytes_ascii" in case:
        return ingest_bytes(case["input_bytes_ascii"].encode("ascii"), case.get("filename", "x.md"))
    return ingest_text(case["input_text"])


def _extract(case, llm, doc_id="d"):
    doc = _ingest(case)
    store = VectorStore()
    return doc, extract_records(doc, "pet", llm, document_id=doc_id, store=store), store


# --- per-kind scorers: each returns (passed: bool, detail: str) -----------

def score_extraction(case, llm):
    doc, res, _ = _extract(case, llm)
    exp = case["expect"]
    checks = []
    if "min_records" in exp:
        checks.append(len(res.records) >= exp["min_records"])
    if "exact_records" in exp:
        checks.append(len(res.records) == exp["exact_records"])
    vacc = [r for r in res.records if r.record_type == RecordType.VACCINATION]
    meds = [r for r in res.records if r.record_type == RecordType.MEDICATION]
    if "min_vaccinations" in exp:
        checks.append(len(vacc) >= exp["min_vaccinations"])
    if "min_medications" in exp:
        checks.append(len(meds) >= exp["min_medications"])
    if exp.get("medication_has_dosage"):
        checks.append(any(m.fields.get("dosage") for m in meds))
    if "vaccine_has_due" in exp:
        has_due = any(r.fields.get("due_date") for r in vacc)
        checks.append(has_due == exp["vaccine_has_due"])
    if exp.get("missing_includes_due"):
        checks.append(any("due_date" in m for m in res.missing_fields))
    if exp.get("no_unsupported"):
        checks.append(len(res.unsupported_fields) == 0)
    if "injection_flagged" in exp:
        checks.append(res.injection_flagged == exp["injection_flagged"])
    if "due_not_in" in exp:
        checks.append(all(r.fields.get("due_date") != exp["due_not_in"] for r in res.records))
    if "due_in" in exp:
        checks.append(any(r.fields.get("due_date") == exp["due_in"] for r in res.records))
    detail = f"records={len(res.records)} unsupported={len(res.unsupported_fields)} injection={res.injection_flagged}"
    return all(checks), detail


def score_extraction_status(case, llm):
    doc, res, _ = _extract(case, llm)
    today = parse_date(case.get("today")) or date.today()
    statuses = []
    for r in res.records:
        due = parse_date(r.fields.get("due_date"))
        statuses.append(compute_care_status(due, today).value)
    passed = case["expect"]["care_status"] in statuses
    return passed, f"statuses={statuses}"


def score_contradiction(case, llm):
    all_records = []
    for i, text in enumerate(case["inputs"]):
        doc = ingest_text(text)
        store = VectorStore()
        res = extract_records(doc, "pet", llm, document_id=f"c{i}", store=store)
        all_records.extend(res.records)
    conflicts = detect_conflicts(all_records)
    exp = case["expect"]
    checks = []
    if "min_conflicts" in exp:
        checks.append(len(conflicts) >= exp["min_conflicts"])
    if "exact_conflicts" in exp:
        checks.append(len(conflicts) == exp["exact_conflicts"])
    if exp.get("reminders_blocked"):
        blocked = conflicted_record_ids(all_records)
        reminders, _c, _b = approve_and_schedule(all_records, today=date(2025, 7, 1))
        # None of the conflicted rabies records should have produced a reminder.
        checks.append(all(r.record_id not in blocked for r in all_records if r.record_id in [x.record_id for x in reminders]))
    return all(checks), f"conflicts={len(conflicts)}"


def score_qa(case, llm):
    doc = ingest_text(case["input_text"])
    store = VectorStore()
    store.add(_chunks(doc.text))
    ans = answer_question(case["question"], store, llm, pet_id="pet", k=4)
    exp = case["expect"]
    checks = []
    if "abstained" in exp:
        checks.append(ans.abstained == exp["abstained"])
    if "refused" in exp:
        checks.append(ans.refused == exp["refused"])
    if exp.get("has_citations"):
        checks.append(len(ans.citations) > 0)
    return all(checks), f"abstain={ans.abstained} refused={ans.refused} cites={len(ans.citations)}"


def score_ingest_reject(case, llm):
    doc = _ingest(case)
    passed = (not doc.ok) == case["expect"]["rejected"]
    return passed, f"ok={doc.ok} err={doc.error}"


def score_guardrail_reminder(case, llm):
    doc = ingest_text(case["input_text"])
    store = VectorStore()
    res = extract_records(doc, "pet", llm, document_id="g", store=store)
    records = res.records
    if case.get("approve"):
        for r in records:
            r.review_status = ReviewStatus.APPROVED
        reminders, _c, _b = approve_and_schedule(records, today=date(2025, 7, 1))
    else:
        # Not approved: reminders must NOT be generated.
        from pawpal_ai.reminders import generate_reminders
        reminders = generate_reminders(records, today=date(2025, 7, 1))
    exp = case["expect"]
    checks = []
    if "reminders" in exp:
        checks.append(len(reminders) == exp["reminders"])
    if "min_reminders" in exp:
        checks.append(len(reminders) >= exp["min_reminders"])
    return all(checks), f"reminders={len(reminders)} approved={bool(case.get('approve'))}"


def _chunks(text):
    from pawpal_ai.chunking import chunk_text
    return chunk_text(text, "qa", "pet")


_SCORERS = {
    "extraction": score_extraction,
    "extraction_status": score_extraction_status,
    "contradiction": score_contradiction,
    "qa": score_qa,
    "ingest_reject": score_ingest_reject,
    "guardrail_reminder": score_guardrail_reminder,
}


def run(live: bool = False) -> dict:
    if not live:
        os.environ["PAWPAL_LLM_PROVIDER"] = "mock"
    settings = get_settings()
    llm = build_llm(settings)
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]

    results = []
    for case in cases:
        scorer = _SCORERS[case["kind"]]
        try:
            passed, detail = scorer(case, llm)
        except Exception as exc:  # a crash is a failure, not a stack trace
            passed, detail = False, f"ERROR {type(exc).__name__}: {exc}"
        results.append({"id": case["id"], "kind": case["kind"], "passed": passed, "detail": detail})

    return _summarize(results, provider=llm.provider)


def _summarize(results: list[dict], provider: str) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    # Metric buckets derived from the cases (illustrative but real).
    def rate(kinds):
        subset = [r for r in results if r["kind"] in kinds]
        return (sum(1 for r in subset if r["passed"]) / len(subset)) if subset else None

    metrics = {
        "cases_total": total,
        "cases_passed": passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "extraction_pass_rate": rate({"extraction", "extraction_status"}),
        "contradiction_detection_rate": rate({"contradiction"}),
        "qa_abstention_and_refusal_rate": rate({"qa"}),
        "guardrail_success_rate": rate({"ingest_reject", "guardrail_reminder"}),
        "provider": provider,
    }
    return {"results": results, "metrics": metrics}


def write_artifacts(report: dict) -> None:
    (HERE / "evaluation_results.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    m = report["metrics"]
    lines = [
        "# PawPal AI — Evaluation Report",
        "",
        f"Provider: **{m['provider']}**  |  Passed **{m['cases_passed']}/{m['cases_total']}** "
        f"({m['pass_rate'] * 100:.0f}%)",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| ------ | ----- |",
    ]
    for key in [
        "pass_rate",
        "extraction_pass_rate",
        "contradiction_detection_rate",
        "qa_abstention_and_refusal_rate",
        "guardrail_success_rate",
    ]:
        val = m[key]
        lines.append(f"| {key} | {val if val is not None else 'n/a'} |")
    lines += [
        "",
        "## Per-case results",
        "",
        "| Case | Kind | Result | Detail |",
        "| ---- | ---- | ------ | ------ |",
    ]
    for r in report["results"]:
        mark = "PASS" if r["passed"] else "FAIL"
        lines.append(f"| {r['id']} | {r['kind']} | {mark} | {r['detail']} |")
    lines.append("")
    (HERE / "evaluation_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PawPal AI reliability evaluation.")
    parser.add_argument("--live", action="store_true", help="use Claude if configured")
    args = parser.parse_args()

    report = run(live=args.live)
    write_artifacts(report)

    m = report["metrics"]
    print("=" * 60)
    print(f"PawPal AI evaluation ({m['provider']} provider)")
    print("=" * 60)
    for r in report["results"]:
        print(f"  [{'PASS' if r['passed'] else 'FAIL'}] {r['id']:<38} {r['detail']}")
    print("-" * 60)
    print(f"  TOTAL: {m['cases_passed']}/{m['cases_total']} passed ({m['pass_rate'] * 100:.0f}%)")
    print(f"  extraction={m['extraction_pass_rate']}  contradiction={m['contradiction_detection_rate']}")
    print(f"  qa={m['qa_abstention_and_refusal_rate']}  guardrails={m['guardrail_success_rate']}")
    print(f"  artifacts -> evaluation/evaluation_results.json, evaluation/evaluation_report.md")
    return 0 if m["cases_passed"] == m["cases_total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
