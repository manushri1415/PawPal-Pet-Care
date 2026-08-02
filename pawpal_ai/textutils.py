"""Small shared text/date helpers used across extraction, evidence, reminders.

Kept deterministic and dependency-free (no dateutil) so behavior is identical
in mock and live modes and reproducible in tests.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_ISO_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_WORD_RE = re.compile(
    r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE
)


def parse_date(text: Optional[str]) -> Optional[date]:
    """Parse the first date found in ``text`` in ISO, M/D/Y, or 'Month D, YYYY'
    form. Returns None if nothing valid is found (so callers never fabricate)."""
    if not text:
        return None
    text = text.strip()

    m = _ISO_RE.search(text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _WORD_RE.search(text)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        if month:
            return _safe_date(int(m.group(3)), month, int(m.group(2)))

    m = _SLASH_RE.search(text)
    if m:
        year = int(m.group(3))
        if year < 100:
            year += 2000
        return _safe_date(year, int(m.group(1)), int(m.group(2)))

    return None


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))
