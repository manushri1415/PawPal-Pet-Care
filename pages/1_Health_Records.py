"""PawPal AI - Health Records page (Streamlit multipage).

This is the new applied-AI surface, added as a separate page so the original
PawPal+ scheduler in ``app.py`` (and its AppTest regression tests) stay
untouched. Full workflow: upload/paste a vet document -> agentic RAG extraction
-> human review (approve/edit/reject) -> deterministic reminders + conflict
warnings -> ask grounded questions.

Runs in the default ``mock`` provider with no API key.
"""

from __future__ import annotations

import re
from datetime import date

import streamlit as st

from pawpal_ai.config import get_settings
from pawpal_ai.contradictions import conflicted_record_ids, detect_conflicts
from pawpal_ai.documents import ingest_bytes, ingest_text
from pawpal_ai.health_models import CareStatus, ReviewStatus
from pawpal_ai.llm import build_llm
from pawpal_ai.pipeline import process_document
from pawpal_ai.qa import answer_question
from pawpal_ai.reminders import generate_reminders
from pawpal_ai.storage import init_db
from pawpal_ai.textutils import parse_date
from pawpal_ai.vectorstore import VectorStore

st.set_page_config(page_title="PawPal AI Health Records", layout="wide")

SETTINGS = get_settings()


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("health_pets", {})  # pet_id -> name
    ss.setdefault("selected_pet", None)
    ss.setdefault("vstore", VectorStore())
    ss.setdefault("pending", {})  # record_id -> HealthRecord (awaiting review)
    ss.setdefault("db", init_db(SETTINGS.resolved_db_path()))


_init_state()
llm = build_llm(SETTINGS)


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.title("PawPal AI Pet Health Records")
st.caption(
    "Upload veterinary documents; AI proposes structured records grounded in the "
    "source text. You approve them before anything is saved or scheduled."
)


# --------------------------------------------------------------------------- #
# Sidebar: pet management
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("Pets")
    new_pet = st.text_input("Add a pet", key="new_pet_name", placeholder="e.g. Max")
    if st.button("Add pet", key="add_health_pet") and new_pet.strip():
        import uuid

        pid = f"pet_{uuid.uuid4().hex[:8]}"
        st.session_state.health_pets[pid] = new_pet.strip()
        st.session_state.selected_pet = pid
        st.rerun()

    pets = st.session_state.health_pets
    if pets:
        options = list(pets.keys())
        st.session_state.selected_pet = st.selectbox(
            "Active pet",
            options,
            index=options.index(st.session_state.selected_pet)
            if st.session_state.selected_pet in options
            else 0,
            format_func=lambda pid: pets[pid],
            key="pet_selector",
        )
    else:
        st.caption("Add a pet to begin.")

    st.divider()
    st.caption("Settings")
    st.code(
        f"provider={llm.provider}\nk={SETTINGS.retrieval_k}\n"
        f"max_attempts={SETTINGS.max_attempts}\n"
        f"evidence_threshold={SETTINGS.evidence_threshold}\n"
        f"due_soon_days={SETTINGS.due_soon_days}",
        language="ini",
    )


pet_id = st.session_state.selected_pet
if not pet_id:
    st.warning("Add and select a pet in the sidebar to start.")
    st.stop()

pet_name = st.session_state.health_pets[pet_id]
db = st.session_state.db


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _record_title(rec) -> str:
    return f"{_record_name(rec)} - {rec.record_type.value}"


def _record_name(rec) -> str:
    name = (
        rec.fields.get("vaccine_name")
        or rec.fields.get("medication_name")
        or rec.fields.get("purpose")
        or "record"
    )
    return str(name)


def _render_fields(rec) -> None:
    for fname, value in rec.fields.items():
        if value is None:
            st.markdown(f"- **{fname}**: _not found_")
            continue
        ev = rec.evidence.get(fname)
        badge = f" `score {ev.match_score}`" if ev else ""
        st.markdown(f"- **{fname}**: {value}{badge}")
        if ev:
            st.caption(f"{_source_label(ev)}: \"{ev.supporting_text}\"")


_RAW_SOURCE_RE = re.compile(
    r"\s*\[(?:doc_[A-Za-z0-9_-]+|[A-Za-z0-9_-]+)#chunk-\d+\]"
)


def _source_label(source, label: str = "Source") -> str:
    section = getattr(source, "section", None) or "record excerpt"
    return f"{label} - {section}"


def _friendly_answer(text: str) -> str:
    return _RAW_SOURCE_RE.sub("", text).strip()


def _format_date(value: date) -> str:
    return value.strftime("%b %d, %Y").replace(" 0", " ")


def _display_value(value: str) -> str:
    return str(value).replace("_", " ").title()


_FIELD_LABELS = {
    "vaccine_name": "Vaccine",
    "administered_date": "Given",
    "due_date": "Due",
    "medication_name": "Medication",
    "dosage": "Dosage",
    "frequency": "Frequency",
    "duration": "Duration",
    "purpose": "Purpose",
    "appointment_date": "Appointment",
    "clinic": "Clinic",
    "veterinarian": "Veterinarian",
}

_FIELD_ORDER = {
    "vaccination": ["vaccine_name", "administered_date", "due_date", "clinic", "veterinarian"],
    "medication": ["medication_name", "dosage", "frequency", "duration", "clinic"],
    "appointment": ["purpose", "appointment_date", "clinic"],
}


def _field_label(field_name: str) -> str:
    return _FIELD_LABELS.get(field_name, _display_value(field_name))


def _format_field_value(field_name: str, value: str) -> str:
    parsed = parse_date(value) if "date" in field_name else None
    if parsed:
        return _format_date(parsed)
    return str(value)


def _ordered_fields(rec) -> list[tuple[str, str]]:
    values = {k: v for k, v in rec.fields.items() if v not in (None, "")}
    order = _FIELD_ORDER.get(rec.record_type.value, list(values))
    ordered = [(field, values[field]) for field in order if field in values]
    ordered += [(field, value) for field, value in values.items() if field not in order]
    return ordered


def _approved_badge() -> str:
    return (
        "<span style='display:inline-block;padding:0.16rem 0.55rem;border-radius:999px;"
        "font-size:0.82rem;font-weight:700;color:#35c27c;background:rgba(53, 194, 124, 0.14);"
        "border:1px solid rgba(53, 194, 124, 0.28);'>Approved</span>"
    )


def _source_excerpt(source) -> str:
    if not source:
        return ""
    return _friendly_answer(getattr(source, "supporting_text", "") or "").strip().strip('"')


def _render_approved_record(rec) -> None:
    with st.container(border=True):
        title_col, badge_col = st.columns([4, 1])
        with title_col:
            st.markdown(f"### {_record_name(rec)}")
            st.caption(_display_value(rec.record_type.value))
        with badge_col:
            st.markdown(_approved_badge(), unsafe_allow_html=True)

        fields = _ordered_fields(rec)
        for row_start in range(0, len(fields), 3):
            cols = st.columns(3)
            for col, (field_name, value) in zip(cols, fields[row_start : row_start + 3]):
                with col:
                    st.caption(_field_label(field_name))
                    st.markdown(f"**{_format_field_value(field_name, value)}**")

        sourced = [
            (field_name, rec.evidence[field_name])
            for field_name, _ in fields
            if field_name in rec.evidence
        ]
        if sourced:
            with st.expander("Source details"):
                for field_name, source in sourced:
                    excerpt = _source_excerpt(source)
                    if excerpt:
                        st.caption(f"{_field_label(field_name)}: \"{excerpt}\"")


def _status_badge(status: CareStatus) -> str:
    styles = {
        CareStatus.OVERDUE: ("Overdue", "#ff3b5f", "rgba(255, 59, 95, 0.14)"),
        CareStatus.DUE_SOON: ("Due soon", "#f6a531", "rgba(246, 165, 49, 0.14)"),
        CareStatus.CURRENT: ("Current", "#35c27c", "rgba(53, 194, 124, 0.14)"),
        CareStatus.UNKNOWN: ("Unknown", "#9aa0aa", "rgba(154, 160, 170, 0.14)"),
    }
    label, color, bg = styles.get(status, styles[CareStatus.UNKNOWN])
    return (
        f"<span style='display:inline-block;padding:0.16rem 0.55rem;border-radius:999px;"
        f"font-size:0.82rem;font-weight:700;color:{color};background:{bg};"
        f"border:1px solid {color}33;'>{label}</span>"
    )


def _relative_due_text(due: date, today: date) -> str:
    days = (due - today).days
    if days == 0:
        return "Due today"
    if days < 0:
        return f"{abs(days)} days overdue"
    if days == 1:
        return "Due tomorrow"
    return f"Due in {days} days"


def _format_offsets(offsets: list[int]) -> str:
    labels = []
    for days in sorted(offsets, reverse=True):
        if days == 0:
            labels.append("on the due date")
        elif days == 1:
            labels.append("1 day before")
        else:
            labels.append(f"{days} days before")
    return ", ".join(labels)


def _reminder_source_excerpt(source) -> str:
    if not source:
        return ""
    text = _friendly_answer(getattr(source, "supporting_text", "") or "")
    return text.strip().strip('"')


def _reminder_name(rem) -> str:
    return re.sub(r"\s+\([^)]+\)$", "", rem.label).strip()


def _result_fatal_error(res) -> str | None:
    fatal = getattr(res, "fatal_error", None)
    if fatal:
        return fatal
    errors = getattr(res, "errors", [])
    if errors and not getattr(res, "records", []):
        return errors[-1]
    return None


# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #
tab_upload, tab_review, tab_reminders, tab_ask, tab_audit = st.tabs(
    ["Upload & Extract", "Review", "Reminders", "Ask", "Audit"]
)


# --- Upload & Extract -----------------------------------------------------
with tab_upload:
    st.subheader(f"Add a document for {pet_name}")
    up = st.file_uploader("Upload PDF / DOCX / TXT", type=["pdf", "docx", "txt"], key="uploader")
    pasted = st.text_area("or paste veterinary text", height=140, key="paste_area")

    if st.button("Extract records", key="extract_btn", type="primary"):
        if up is not None:
            doc = ingest_bytes(up.getvalue(), up.name)
        elif pasted.strip():
            doc = ingest_text(pasted, "pasted-text")
        else:
            doc = None
            st.error("Upload a file or paste some text first.")

        if doc is not None:
            if not doc.ok:
                st.error(doc.error)
            else:
                if doc.injection_flagged:
                    st.warning(
                        "This document contains prompt-injection-like text. It is treated "
                        "as untrusted data; any embedded instructions are ignored, and you "
                        "still review everything before it is saved."
                    )
                processed = process_document(
                    doc, pet_id, llm, SETTINGS, store=st.session_state.vstore
                )
                res = processed.result
                fatal_error = _result_fatal_error(res)
                if fatal_error:
                    st.error(f"Extraction failed: {fatal_error}")
                    st.info(
                        f"The {doc.doc_type.upper()} text was readable ({doc.char_count} characters), "
                        "but no records were created because the model call failed."
                    )
                else:
                    db.save_document(pet_id, doc.filename, doc.doc_type, doc.char_count, doc.injection_flagged, processed.document_id)
                    for rec in res.records:
                        st.session_state.pending[rec.record_id] = rec
                    if res.records:
                        st.success(
                            f"Extracted {len(res.records)} record(s) in {res.attempts} attempt(s). "
                            f"Review them in the **Review** tab."
                        )
                    else:
                        st.warning(
                            f"Read the {doc.doc_type.upper()} ({doc.char_count} characters), "
                            "but did not find supported vaccination, medication, or appointment records."
                        )
                    if res.pet_name_in_document and res.pet_name_in_document.lower() != pet_name.lower():
                        st.warning(
                            f"The document names **{res.pet_name_in_document}**, but the active pet is "
                            f"**{pet_name}**. Double-check the attribution."
                        )
                    if res.missing_fields:
                        st.info("Missing important fields (left blank, not guessed): " + ", ".join(res.missing_fields))
                    if res.unsupported_fields:
                        st.info("Dropped unsupported values (not grounded in the text): " + ", ".join(res.unsupported_fields))


# --- Review ---------------------------------------------------------------
with tab_review:
    st.subheader("Human review")
    st.caption("Nothing is saved or scheduled until you approve it. Edit values inline if needed.")
    pending = [r for r in st.session_state.pending.values() if r.pet_id == pet_id and r.review_status == ReviewStatus.PENDING]

    if not pending:
        st.info("No records awaiting review. Extract a document in the **Upload** tab.")
    for rec in pending:
        with st.container(border=True):
            st.markdown(f"### {_record_title(rec)} - confidence `{rec.confidence}`")
            _render_fields(rec)
            c1, c2, c3 = st.columns([1, 1, 4])
            if c1.button("Approve", key=f"appr_{rec.record_id}"):
                rec.review_status = ReviewStatus.APPROVED
                db.save_record(rec, document_id="")
                db.set_review_status(rec.record_id, ReviewStatus.APPROVED)
                st.rerun()
            if c2.button("Reject", key=f"rej_{rec.record_id}"):
                rec.review_status = ReviewStatus.REJECTED
                db.save_record(rec, document_id="")
                db.set_review_status(rec.record_id, ReviewStatus.REJECTED)
                st.rerun()
            with c3.expander("Edit a field"):
                editable = [f for f in rec.fields]
                fld = st.selectbox("Field", editable, key=f"edit_field_{rec.record_id}")
                newval = st.text_input("New value", value=rec.fields.get(fld) or "", key=f"edit_val_{rec.record_id}")
                if st.button("Apply edit", key=f"apply_{rec.record_id}"):
                    rec.fields[fld] = newval or None
                    st.success(f"Updated {fld}. (Human-authored edits are tracked.)")
                    st.rerun()

    approved = db.list_records(pet_id, ReviewStatus.APPROVED)
    if approved:
        st.divider()
        st.markdown(f"### Approved records ({len(approved)})")
        for rec in approved:
            _render_approved_record(rec)


# --- Reminders ------------------------------------------------------------
with tab_reminders:
    st.subheader("Reminders & care status")
    approved = db.list_records(pet_id, ReviewStatus.APPROVED)
    conflicts = detect_conflicts(approved)
    blocked = conflicted_record_ids(approved)
    today = date.today()

    reminders = generate_reminders(
        approved, today=today, due_soon_days=SETTINGS.due_soon_days, blocked_record_ids=blocked
    )
    for rem in reminders:
        db.save_reminder(rem)

    if conflicts:
        st.error(f"{len(conflicts)} unresolved contradiction(s). Reminders are paused for affected records.")
        for c in conflicts:
            with st.container(border=True):
                st.markdown(
                    f"**Conflicting {_display_value(c.record_type.value)} {_display_value(c.field)}**"
                )
                st.caption(f"{c.value_a} vs {c.value_b}")
                if c.source_a:
                    right = _source_label(c.source_b, "Source B") if c.source_b else "Source B"
                    st.caption(f"{_source_label(c.source_a, 'Source A')}; {right}")

    if not reminders and not conflicts:
        st.info("No reminders yet. Approve a record that has an explicit due date.")

    for rem in sorted(reminders, key=lambda item: item.due_date):
        with st.container(border=True):
            title_col, status_col = st.columns([4, 1])
            with title_col:
                st.markdown(f"### {_reminder_name(rem)}")
                st.caption(_display_value(rem.record_type.value))
            with status_col:
                st.markdown(_status_badge(rem.care_status), unsafe_allow_html=True)

            due_col, timing_col, alerts_col = st.columns([1.1, 1.1, 2])
            with due_col:
                st.caption("Due date")
                st.markdown(f"**{_format_date(rem.due_date)}**")
            with timing_col:
                st.caption("Care status")
                st.markdown(f"**{_relative_due_text(rem.due_date, today)}**")
            with alerts_col:
                st.caption("Reminder alerts")
                st.markdown(f"**{_format_offsets(rem.offsets_days)}**")

            excerpt = _reminder_source_excerpt(rem.source)
            if excerpt:
                with st.expander("Source excerpt"):
                    st.caption(f"\"{excerpt}\"")


# --- Ask ------------------------------------------------------------------
with tab_ask:
    st.subheader(f"Ask about {pet_name}'s records")
    st.caption("Answers are grounded only in your uploaded documents, with citations. Medical-advice questions are refused.")
    q = st.text_input("Your question", key="qa_input", placeholder="When is the rabies vaccine due?")
    if st.button("Ask", key="ask_btn") and q.strip():
        ans = answer_question(q, st.session_state.vstore, llm, pet_id=pet_id, k=SETTINGS.retrieval_k)
        if ans.refused:
            st.error(_friendly_answer(ans.answer))
        elif ans.abstained:
            st.warning(_friendly_answer(ans.answer))
        else:
            st.markdown(f"**Answer:** {_friendly_answer(ans.answer)}")
        if ans.citations:
            with st.expander(f"Sources ({len(ans.citations)})"):
                for idx, c in enumerate(ans.citations, start=1):
                    st.markdown(f"**Source {idx}**")
                    st.caption(f"{c.section or 'record excerpt'} - \"{c.supporting_text}\"")


# --- Audit ----------------------------------------------------------------
with tab_audit:
    st.subheader("Audit trail")
    st.caption("Every save/approval/rejection/reminder is logged (tamper-evident human-oversight record).")
    trail = db.audit_trail(limit=50)
    if not trail:
        st.info("No activity yet.")
    else:
        st.table(
            [{"time": r["created_at"], "event": r["event"], "ref": r["ref_id"], "detail": r["detail"]} for r in trail]
        )
