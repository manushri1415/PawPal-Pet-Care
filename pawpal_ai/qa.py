"""Retrieval-grounded Q&A over a pet's uploaded documents.

Same RAG spine as extraction: retrieve passages from the local vector store,
then answer *only* from them. Two guardrails wrap the call:

- **Refuse medical advice** (diagnosis/prescription/treatment) up front.
- **Abstain** when retrieval returns nothing relevant — the answer says there
  is not enough evidence rather than inventing one.

Every answer carries citations (the retrieved chunks it was grounded in) so the
UI can show the source behind each response.
"""

from __future__ import annotations

import re
from typing import Optional

from pawpal_ai.guardrails import REFUSAL_MESSAGE, is_medical_advice_request
from pawpal_ai.health_models import QAAnswer, SourceEvidence
from pawpal_ai.llm import LLMClient, LLMError
from pawpal_ai.logging_setup import log_event
from pawpal_ai.vectorstore import RetrievedChunk, VectorStore

# Below this top-score, we treat retrieval as "no relevant evidence" and abstain.
_MIN_RELEVANCE = 0.08


def answer_question(
    question: str,
    store: VectorStore,
    llm: LLMClient,
    *,
    k: int = 4,
    document_id: Optional[str] = None,
) -> QAAnswer:
    """Answer ``question`` from retrieved passages, or refuse/abstain."""
    log_event("qa_started", provider=getattr(llm, "provider", "?"))

    if is_medical_advice_request(question):
        return QAAnswer(question=question, answer=REFUSAL_MESSAGE, refused=True)

    retrieved = store.retrieve(question, k=k, document_id=document_id)
    top = retrieved[0].score if retrieved else 0.0
    if not retrieved or top < _MIN_RELEVANCE:
        log_event("qa_abstained", top_score=round(top, 3))
        return QAAnswer(
            question=question,
            answer="I don't have enough evidence in the uploaded records to answer that.",
            abstained=True,
            citations=[_cite(rc) for rc in retrieved],
        )

    try:
        text = _redact_internal_source_ids(llm.answer(question, retrieved))
    except LLMError as exc:
        log_event("qa_error", error=str(exc)[:80])
        return QAAnswer(
            question=question,
            answer="Sorry — I couldn't process that question right now. Please try again.",
            abstained=True,
        )

    log_event("qa_completed", citations=len(retrieved))
    return QAAnswer(
        question=question,
        answer=text,
        citations=[_cite(rc) for rc in retrieved],
    )


def _cite(rc: RetrievedChunk) -> SourceEvidence:
    return SourceEvidence(
        document_id=rc.chunk.document_id,
        chunk_id=rc.chunk.chunk_id,
        section=rc.chunk.section,
        supporting_text=rc.chunk.text[:160],
        match_score=round(rc.score, 3),
    )


_INTERNAL_SOURCE_RE = re.compile(
    r"\s*\[(?:doc_[A-Za-z0-9_-]+|[A-Za-z0-9_-]+)#chunk-\d+\]"
)


def _redact_internal_source_ids(text: str) -> str:
    return _INTERNAL_SOURCE_RE.sub("", text).strip()
