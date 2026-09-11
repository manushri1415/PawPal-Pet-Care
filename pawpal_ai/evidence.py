"""Field-level source validation and citation building.

This is the deterministic "check" that makes the AI trustworthy: for every value
the LLM proposes, we confirm it is actually supported by a retrieved passage
before we keep it. A value with no supporting passage is treated as
**unsupported** and dropped (nulled) — this is the mechanism that stops
hallucinated dates/dosages from ever reaching storage or reminders.

Matching is intentionally simple and explainable:
- **Dates** are grounded by parsing dates out of the chunk and comparing values.
- **Text** is grounded by normalized-substring match, else token-overlap ratio.
Each accepted field gets a :class:`SourceEvidence` citation (document, chunk,
section, the supporting text span, and a 0..1 match score).
"""

from __future__ import annotations

import re
from typing import Optional

from pawpal_ai.health_models import SourceEvidence
from pawpal_ai.textutils import normalize_text, parse_date, token_set
from pawpal_ai.vectorstore import RetrievedChunk

_DATE_FIELDS = {"administered_date", "due_date", "appointment_date"}

# The date shapes the is_date branch below scans for. Also reused (for
# non-date fields) to blank out date-like text before matching a short
# numeric value, so a 1-2 digit dosage/code can't be "grounded" by a digit
# run that's actually part of an unrelated calendar date (UPGRADES.md #1.4).
_DATE_TOKEN_RE = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}"
)
_SHORT_NUMERIC_LEN = 3


def find_evidence(
    field_name: str,
    value: str,
    chunks: list[RetrievedChunk],
    threshold: float = 0.5,
) -> Optional[SourceEvidence]:
    """Return the best-supporting citation for ``value`` if score >= threshold."""
    if value is None or not str(value).strip() or not chunks:
        return None

    best: Optional[SourceEvidence] = None
    best_score = 0.0
    is_date = field_name in _DATE_FIELDS

    for rc in chunks:
        score, span = _support(field_name, str(value), rc.chunk.text, is_date)
        if score > best_score:
            best_score = score
            best = SourceEvidence(
                document_id=rc.chunk.document_id,
                chunk_id=rc.chunk.chunk_id,
                section=rc.chunk.section,
                supporting_text=span,
                match_score=round(score, 3),
            )
    if best is not None and best_score >= threshold:
        return best
    return None


def _support(field_name: str, value: str, chunk_text: str, is_date: bool) -> tuple[float, str]:
    """Return (score, supporting_span) for a value against one chunk."""
    if is_date:
        target = parse_date(value)
        if target is None:
            return 0.0, ""
        # Scan the chunk for any date token and compare parsed values.
        for m in _DATE_TOKEN_RE.finditer(chunk_text):
            if parse_date(m.group(0)) == target:
                return 1.0, _span(chunk_text, m.start())
        return 0.0, ""

    norm_value = normalize_text(value)
    is_short_numeric = norm_value.isdigit() and len(norm_value) <= _SHORT_NUMERIC_LEN
    # A short all-digit value (dosage, clinic code) is masked against any
    # date-shaped substring in the chunk before matching -- otherwise "10"
    # would be "grounded" by the trailing digits of an unrelated 2025-03-10.
    search_text = _mask_dates(chunk_text) if is_short_numeric else chunk_text
    norm_chunk = normalize_text(search_text)

    if norm_value and norm_value in norm_chunk:
        m = _find_bounded(norm_value, search_text)
        if m is not None:
            return 1.0, _span(chunk_text, m)

    # Fallback: token-overlap (fraction of the value's tokens present in chunk).
    v_tokens = token_set(value)
    if not v_tokens:
        return 0.0, ""
    overlap = len(v_tokens & token_set(search_text)) / len(v_tokens)
    if overlap > 0:
        # Anchor the span on the first shared token.
        first = next(iter(v_tokens & token_set(search_text)))
        idx = norm_chunk.find(first)
        return overlap, _span(chunk_text, max(0, idx))
    return 0.0, ""


def _mask_dates(text: str) -> str:
    """Blank out date-shaped substrings, preserving length/offsets."""
    return _DATE_TOKEN_RE.sub(lambda m: " " * len(m.group(0)), text)


def _find_bounded(norm_value: str, original: str) -> Optional[int]:
    """Locate ``norm_value`` in ``original`` as a whole token (not embedded
    inside a longer word/number, e.g. dosage "5" inside "50mg"), searching the
    real text directly so the returned offset is never shifted by whitespace
    normalization (see UPGRADES.md #1.3 -- the old code found the offset in a
    whitespace-collapsed copy of the text but sliced the original at that same
    offset, which drifts whenever a run of whitespace collapses)."""
    words = norm_value.split(" ")
    pattern = r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b"
    m = re.search(pattern, original, re.IGNORECASE)
    return m.start() if m else None


def _span(text: str, idx: int, radius: int = 60) -> str:
    start = max(0, idx - radius // 3)
    end = min(len(text), idx + radius)
    snippet = text[start:end].strip().replace("\n", " ")
    return snippet
