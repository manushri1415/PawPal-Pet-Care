"""PawPal AI — Health Records page (Streamlit multipage).

This is the new applied-AI surface, added as a separate page so the original
PawPal+ scheduler in ``app.py`` (and its AppTest regression tests) stay
untouched. Full workflow: upload/paste a vet document -> agentic RAG extraction
-> human review (approve/edit/reject) -> deterministic reminders + conflict
warnings -> ask grounded questions.

Runs in the default ``mock`` provider with no API key.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from pawpal_ai.config import get_settings
from pawpal_ai.contradictions import conflicted_record_ids, detect_conflicts
from pawpal_ai.documents import ingest_bytes, ingest_text
from pawpal_ai.extraction_agent import append_trace
from pawpal_ai.guardrails import can_save_record
from pawpal_ai.health_models import CareStatus, RecordType, ReviewStatus
from pawpal_ai.llm import build_llm
from pawpal_ai.pipeline import process_document
from pawpal_ai.qa import answer_question
from pawpal_ai.reminders import generate_reminders
from pawpal_ai.storage import init_db
from pawpal_ai.vectorstore import VectorStore

st.set_page_config(page_title="PawPal AI — Health Records", page_icon="🩺", layout="wide")

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
    ss.setdefault("last_trace", None)


_init_state()
llm = build_llm(SETTINGS)


# --------------------------------------------------------------------------- #
# Header + provider banner
# --------------------------------------------------------------------------- #
st.title("🩺 PawPal AI — Pet Health Records")
st.caption(
    "Upload veterinary documents; AI proposes structured records grounded in the "
    "source text. You approve them before anything is saved or scheduled."
)

if llm.provider == "mock":
    st.info(
        "**Mock mode (no API key).** Extraction uses a deterministic rule-based "
        "model so the whole app is reproducible offline. Set `PAWPAL_LLM_PROVIDER=claude` "
        "and `ANTHROPIC_API_KEY` in `.env` to process new documents with Claude.",
        icon="🧪",
    )
else:
    st.success(f"**Live mode** — using Claude model `{SETTINGS.model}`.", icon="🤖")


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
    st.warning("👈 Add and select a pet in the sidebar to start.")
    st.stop()

pet_name = st.session_state.health_pets[pet_id]
db = st.session_state.db


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _record_title(rec) -> str:
    name = (
        rec.fields.get("vaccine_name")
        or rec.fields.get("medication_name")
        or rec.fields.get("purpose")
        or "record"
    )
    return f"{name} · {rec.record_type.value}"


def _render_fields(rec) -> None:
    for fname, value in rec.fields.items():
        if value is None:
            st.markdown(f"- **{fname}**: _not found_")
            continue
        ev = rec.evidence.get(fname)
        badge = f" `score {ev.match_score}`" if ev else ""
        st.markdown(f"- **{fname}**: {value}{badge}")
        if ev:
            st.caption(f"↳ source `{ev.chunk_id}` ({ev.section}): “{ev.supporting_text}”")


CARE_ICON = {
    CareStatus.OVERDUE: "🔴",
    CareStatus.DUE_SOON: "🟠",
    CareStatus.CURRENT: "🟢",
    CareStatus.UNKNOWN: "⚪",
}


# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #
tab_upload, tab_review, tab_reminders, tab_ask, tab_audit = st.tabs(
    ["📤 Upload & Extract", "✅ Review", "🔔 Reminders", "💬 Ask", "📋 Audit"]
)


# --- Upload & Extract -----------------------------------------------------
with tab_upload:
    st.subheader(f"Add a document for {pet_name}")
    up = st.file_uploader("Upload PDF / DOCX / TXT", type=["pdf", "docx", "txt"], key="uploader")
    pasted = st.text_area("…or paste veterinary text", height=140, key="paste_area")

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
                st.error(f"❌ {doc.error}")
            else:
                if doc.injection_flagged:
                    st.warning(
                        "⚠️ This document contains prompt-injection-like text. It is treated "
                        "as untrusted data; any embedded instructions are ignored, and you "
                        "still review everything before it is saved.",
                        icon="🛡️",
                    )
                processed = process_document(
                    doc, pet_id, llm, SETTINGS, store=st.session_state.vstore, write_trace=True
                )
                st.session_state.last_trace = processed.tracer.to_markdown()
                db.save_document(pet_id, doc.filename, doc.doc_type, doc.char_count, doc.injection_flagged, processed.document_id)
                for rec in processed.result.records:
                    st.session_state.pending[rec.record_id] = rec
                res = processed.result
                st.success(
                    f"Extracted {len(res.records)} record(s) in {res.attempts} attempt(s). "
                    f"Review them in the **Review** tab."
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

    if st.session_state.last_trace:
        with st.expander("🔍 Agent reasoning trace (plan → act → check)"):
            st.markdown(st.session_state.last_trace)


# --- Review ---------------------------------------------------------------
with tab_review:
    st.subheader("Human review")
    st.caption("Nothing is saved or scheduled until you approve it. Edit values inline if needed.")
    pending = [r for r in st.session_state.pending.values() if r.pet_id == pet_id and r.review_status == ReviewStatus.PENDING]

    if not pending:
        st.info("No records awaiting review. Extract a document in the **Upload** tab.")
    for rec in pending:
        with st.container(border=True):
            st.markdown(f"### {_record_title(rec)}  ·  confidence `{rec.confidence}`")
            _render_fields(rec)
            c1, c2, c3 = st.columns([1, 1, 4])
            if c1.button("✅ Approve", key=f"appr_{rec.record_id}"):
                rec.review_status = ReviewStatus.APPROVED
                db.save_record(rec, document_id="")
                db.set_review_status(rec.record_id, ReviewStatus.APPROVED)
                st.rerun()
            if c2.button("🗑️ Reject", key=f"rej_{rec.record_id}"):
                rec.review_status = ReviewStatus.REJECTED
                db.save_record(rec, document_id="")
                db.set_review_status(rec.record_id, ReviewStatus.REJECTED)
                st.rerun()
            with c3.expander("✏️ Edit a field"):
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
        st.markdown(f"**Approved records ({len(approved)})** — verified ✔️")
        for rec in approved:
            st.markdown(f"- ✔️ {_record_title(rec)}: " + ", ".join(f"{k}={v}" for k, v in rec.grounded_fields().items()))


# --- Reminders ------------------------------------------------------------
with tab_reminders:
    st.subheader("Reminders & care status")
    approved = db.list_records(pet_id, ReviewStatus.APPROVED)
    conflicts = detect_conflicts(approved)
    blocked = conflicted_record_ids(approved)

    if conflicts:
        st.error(f"⛔ {len(conflicts)} unresolved contradiction(s) — reminders are blocked for these until you resolve them.")
        for c in conflicts:
            st.markdown(
                f"- **{c.record_type.value}.{c.field}**: `{c.value_a}` vs `{c.value_b}`"
            )
            if c.source_a:
                st.caption(f"   ↳ A from `{c.source_a.chunk_id}`; B from `{c.source_b.chunk_id if c.source_b else '?'}`")

    reminders = generate_reminders(
        approved, today=date.today(), due_soon_days=SETTINGS.due_soon_days, blocked_record_ids=blocked
    )
    for rem in reminders:
        db.save_reminder(rem)

    if not reminders and not conflicts:
        st.info("No reminders yet. Approve a record that has an explicit due date.")
    for rem in reminders:
        icon = CARE_ICON.get(rem.care_status, "⚪")
        st.markdown(
            f"{icon} **{rem.label}** — due **{rem.due_date.isoformat()}** "
            f"({rem.care_status.value}); alerts at {rem.offsets_days} days before."
        )
        if rem.source:
            st.caption(f"↳ due date grounded in `{rem.source.chunk_id}`: “{rem.source.supporting_text}”")


# --- Ask ------------------------------------------------------------------
with tab_ask:
    st.subheader(f"Ask about {pet_name}'s records")
    st.caption("Answers are grounded only in your uploaded documents, with citations. Medical-advice questions are refused.")
    q = st.text_input("Your question", key="qa_input", placeholder="When is the rabies vaccine due?")
    if st.button("Ask", key="ask_btn") and q.strip():
        ans = answer_question(q, st.session_state.vstore, llm, k=SETTINGS.retrieval_k)
        if ans.refused:
            st.error(ans.answer)
        elif ans.abstained:
            st.warning(ans.answer)
        else:
            st.markdown(f"**Answer:** {ans.answer}")
        if ans.citations:
            with st.expander(f"📎 Sources ({len(ans.citations)})"):
                for c in ans.citations:
                    st.caption(f"`{c.chunk_id}` ({c.section}) — “{c.supporting_text}”")


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
