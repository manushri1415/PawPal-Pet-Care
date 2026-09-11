"""LLM abstraction: one interface, three behaviors.

- :class:`MockLLM` — deterministic, rule-based extraction/QA over the retrieved
  passages. No API key, no network. Powers the demo, the tests, and the eval
  harness so the whole system is reproducible with zero credentials. It is a
  genuine (if simple) extractor: it reads the *retrieved* text and returns
  structured output, so retrieval still drives its behavior.
- :class:`ClaudeLLM` — the real model via the Anthropic SDK using structured
  output (``messages.parse``). Used to process genuinely new documents.
- :class:`FailingLLM` — always raises; used by tests to exercise the API-failure
  and retry-limit paths.

All three return a validated :class:`ExtractionEnvelope` from ``extract`` or
raise :class:`LLMError`; ``answer`` returns plain text.
"""

from __future__ import annotations

import re
from typing import Optional, Protocol

from pawpal_ai.config import Settings
from pawpal_ai.health_models import (
    ExtractedAppointment,
    ExtractedMedication,
    ExtractedVaccination,
    ExtractionEnvelope,
)
from pawpal_ai.logging_setup import log_event
from pawpal_ai.prompts import (
    SYSTEM_EXTRACTION,
    SYSTEM_QA,
    build_extraction_prompt,
    build_qa_prompt,
)
from pawpal_ai.vectorstore import RetrievedChunk


class LLMError(RuntimeError):
    """Raised when the LLM call fails or returns unusable output.

    ``str(exc)`` is, by construction, always a short message safe to log or
    show a user directly -- never raw vendor/SDK exception text, which can
    echo fragments of the model's raw response (see UPGRADES.md #2). Chain
    the original exception with ``from exc`` (every raise site here does) so
    the real detail is still available server-side via ``exc.__cause__`` /
    the traceback, without ever being formatted into this message.
    """

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


_GENERIC_LLM_ERROR_MESSAGE = "The AI service had a problem processing this. Please try again."


def safe_error_message(exc: Exception) -> str:
    """A short message safe to log or show a user for any exception raised
    from an LLM call.

    ``LLMError`` messages are already vetted safe. Callers also catch
    exceptions broader than ``LLMError`` on purpose (a network timeout, an
    SDK-internal error, a parsing edge case -- see UPGRADES.md #1.8) so a
    crash degrades gracefully instead of taking down the run; those can
    carry arbitrary vendor/SDK text, so they're mapped to a generic message
    instead of being surfaced via ``str(exc)``.
    """
    if isinstance(exc, LLMError):
        return str(exc)
    return _GENERIC_LLM_ERROR_MESSAGE


def _is_auth_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    exc_name = type(exc).__name__.lower()
    return status_code in {401, 403} or "auth" in exc_name or "permission" in exc_name


class LLMClient(Protocol):
    provider: str

    def extract(
        self, chunks: list[RetrievedChunk], use_fewshot: bool = True, feedback: str = ""
    ) -> ExtractionEnvelope: ...

    def answer(self, question: str, chunks: list[RetrievedChunk]) -> str: ...


# --------------------------------------------------------------------------- #
# Mock (rule-based) implementation
# --------------------------------------------------------------------------- #

_VACCINE_KEYWORDS = [
    "rabies", "distemper", "parvovirus", "parvo", "bordetella", "dhpp", "dappv",
    "dapp", "fvrcp", "leptospirosis", "lepto", "lyme", "canine influenza",
    "feline leukemia", "felv", "adenovirus",
]
# Synonyms that name the same shot; keep one record when several co-occur
# (e.g. "Distemper (DHPP)" should not become two vaccinations).
_VACCINE_CANON = {
    "dhpp": "distemper", "dappv": "distemper", "dapp": "distemper",
    "parvo": "parvovirus", "lepto": "leptospirosis", "felv": "feline leukemia",
}
_DATE_TOKEN = r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})"
_DATE_RE = re.compile(_DATE_TOKEN, re.IGNORECASE)


def _date_tokens(text: str) -> list[str]:
    return [m.group(0).strip() for m in _DATE_RE.finditer(text)]


def _find_date_after(text: str, keywords: list[str]) -> Optional[str]:
    for kw in keywords:
        m = re.search(kw + r"[^\n]{0,40}?(" + _DATE_TOKEN + r")", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


class MockLLM:
    """Deterministic rule-based extractor over retrieved passages."""

    provider = "mock"

    def extract(
        self, chunks: list[RetrievedChunk], use_fewshot: bool = True, feedback: str = ""
    ) -> ExtractionEnvelope:
        text = "\n".join(rc.chunk.text for rc in chunks)
        log_event("extraction_llm_call", provider="mock", chunks=len(chunks), fewshot=use_fewshot)
        return ExtractionEnvelope(
            pet_name=self._pet_name(text),
            vaccinations=self._vaccinations(text),
            medications=self._medications(text),
            appointments=self._appointments(text),
        )

    def answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        log_event("qa_llm_call", provider="mock", chunks=len(chunks))
        if not chunks:
            return "I don't have enough evidence in the uploaded records to answer that."
        if re.search(r"\b(diagnos|prescrib|should i give|what medicine|treat)\b", question, re.I):
            return (
                "I can only organize the existing records, not give medical advice. "
                "Please consult your veterinarian for diagnosis or treatment questions."
            )
        # Return the most relevant passage as grounded context; the caller adds citations.
        best = chunks[0].chunk
        return f"Based on the records: {best.text[:400]}"

    # -- field extractors --------------------------------------------------
    @staticmethod
    def _pet_name(text: str) -> Optional[str]:
        m = re.search(r"(?:patient|pet|animal|name)\s*[:\-]\s*([A-Z][A-Za-z]+)", text, re.I)
        return m.group(1) if m else None

    def _vaccinations(self, text: str) -> list[ExtractedVaccination]:
        out: list[ExtractedVaccination] = []
        seen: set[str] = set()
        for row in self._vaccination_table_rows(text):
            key = self._vaccine_key(row.vaccine_name or "")
            if key in seen:
                continue
            seen.add(key)
            out.append(row)

        for kw in _VACCINE_KEYWORDS:
            if kw not in text.lower():
                continue
            # Look at the sentence/line mentioning the vaccine.
            window = self._window(text, kw)
            administered = _find_date_after(window, ["given", "administered", "date", kw])
            due = _find_date_after(window, ["due", "next due", "booster", "expires", "valid until"])
            canon = _VACCINE_CANON.get(kw, kw)
            if canon in seen:
                continue
            seen.add(canon)
            name = self._source_vaccine_name(window, kw) or canon.title()
            out.append(
                ExtractedVaccination(
                    vaccine_name=name,
                    administered_date=administered,
                    due_date=due,
                    clinic=self._clinic(window),
                    veterinarian=self._vet(window),
                )
            )
        return out

    def _vaccination_table_rows(self, text: str) -> list[ExtractedVaccination]:
        section = self._vaccination_section(text)
        if not section:
            return []

        due_before_given = self._table_headers_due_before_given(section)
        rows: list[ExtractedVaccination] = []
        lines = [line.strip() for line in section.splitlines() if line.strip()]

        for idx, line in enumerate(lines):
            if not self._line_has_vaccine(line):
                continue

            block_lines = [line]
            for nxt in lines[idx + 1 : idx + 8]:
                if self._line_has_vaccine(nxt) or re.search(
                    r"\b(?:patient|owner|veterinarian|signature|license)\b", nxt, re.I
                ):
                    break
                block_lines.append(nxt)

            block = " ".join(block_lines)
            dates = _date_tokens(block)
            if not dates:
                continue

            name = self._clean_vaccine_label(line)
            if not name:
                continue

            due = dates[0] if due_before_given else (dates[1] if len(dates) > 1 else None)
            administered = dates[1] if due_before_given and len(dates) > 1 else dates[0]
            rows.append(
                ExtractedVaccination(
                    vaccine_name=name,
                    administered_date=administered,
                    due_date=due,
                    clinic=self._clinic(section),
                    veterinarian=self._given_by_from_table_block(block),
                )
            )
        return rows

    def _medications(self, text: str) -> list[ExtractedMedication]:
        out: list[ExtractedMedication] = []
        for m in re.finditer(
            r"([A-Z][a-zA-Z]+(?:cillin|profen|mycin|prazole|cycline|dazole)?)\s+"
            r"(\d+\s?(?:mg|ml|mcg))",
            text,
        ):
            name, dosage = m.group(1), m.group(2)
            window = self._window(text, name)
            out.append(
                ExtractedMedication(
                    medication_name=name,
                    dosage=dosage,
                    frequency=self._frequency(window),
                    duration=self._duration(window),
                    clinic=self._clinic(window),
                )
            )
        return out

    def _appointments(self, text: str) -> list[ExtractedAppointment]:
        out: list[ExtractedAppointment] = []
        seen_dates: set[str] = set()
        for kw in ["wellness exam", "annual exam", "follow-up", "follow up", "recheck", "appointment"]:
            if kw not in text.lower():
                continue
            window = self._window(text, kw)
            appt_date = _find_date_after(window, [kw, "on", "scheduled", "date"])
            # Dedupe: several keywords can describe the same event (e.g.
            # "follow-up appointment on <date>"). Collapse by date when known.
            if appt_date and appt_date in seen_dates:
                continue
            if appt_date:
                seen_dates.add(appt_date)
            out.append(
                ExtractedAppointment(
                    purpose=kw.title(), appointment_date=appt_date, clinic=self._clinic(window)
                )
            )
        return out

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _vaccination_section(text: str) -> str:
        start = re.search(r"\bvaccination details\b", text, re.I)
        if not start:
            has_table_headers = re.search(r"\bitem\b.*\bdue\b.*\bgiven\b", text, re.I | re.S)
            if not has_table_headers:
                return ""
            start_idx = 0
        else:
            start_idx = start.end()

        end = re.search(
            r"\b(?:veterinarian information|signature|patient and owner information)\b",
            text[start_idx:],
            re.I,
        )
        end_idx = start_idx + end.start() if end else len(text)
        return text[start_idx:end_idx]

    @staticmethod
    def _table_headers_due_before_given(section: str) -> bool:
        due = re.search(r"\bdue\b", section, re.I)
        given = re.search(r"\bgiven\b", section, re.I)
        return bool(due and given and due.start() < given.start())

    @staticmethod
    def _line_has_vaccine(line: str) -> bool:
        lower = line.lower()
        return any(kw in lower for kw in _VACCINE_KEYWORDS)

    @staticmethod
    def _vaccine_key(name: str) -> str:
        lower = name.lower()
        for kw in _VACCINE_KEYWORDS:
            if kw in lower:
                return _VACCINE_CANON.get(kw, kw)
        return re.sub(r"[^a-z0-9]+", " ", lower).strip()

    @staticmethod
    def _clean_vaccine_label(text: str) -> str:
        label = _DATE_RE.split(text, maxsplit=1)[0]
        label = re.sub(
            r"^(?:(?:item|due|given by|given|notes)\s*)+",
            "",
            label.strip(),
            flags=re.I,
        )
        label = re.sub(r"\b(?:administered|given|next due|due)\b.*$", "", label, flags=re.I)
        return label.strip(" :-")

    @classmethod
    def _source_vaccine_name(cls, text: str, keyword: str) -> Optional[str]:
        for line in text.splitlines():
            if keyword.lower() not in line.lower():
                continue
            label = cls._clean_vaccine_label(line)
            if label and len(label) <= 80:
                return label
        return None

    @staticmethod
    def _given_by_from_table_block(block: str) -> Optional[str]:
        dates = list(_DATE_RE.finditer(block))
        if len(dates) < 2:
            return None
        tail = block[dates[1].end() :]
        tail = re.split(r"\b(?:lot|expiration|notes)\b", tail, maxsplit=1, flags=re.I)[0]
        m = re.search(
            r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\b",
            tail,
        )
        if not m:
            return None
        name = m.group(1).strip()
        return None if name.lower() in {"lot", "expiration"} else name

    @staticmethod
    def _window(text: str, keyword: str, radius: int = 120) -> str:
        idx = text.lower().find(keyword.lower())
        if idx < 0:
            return text
        return text[max(0, idx - 20) : idx + radius]

    @staticmethod
    def _clinic(text: str) -> Optional[str]:
        m = re.search(r"(?:clinic|hospital|vet(?:erinary)? (?:clinic|hospital))\s*[:\-]?\s*([A-Z][A-Za-z &]+)", text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _vet(text: str) -> Optional[str]:
        m = re.search(r"(?:dr\.?|veterinarian|vet)\s*[:\-]?\s*([A-Z][A-Za-z]+)", text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _frequency(text: str) -> Optional[str]:
        m = re.search(r"(once|twice|three times|\d+\s?times)\s+(?:a|per)?\s?(?:day|daily)|every\s+\d+\s+hours|\b(?:bid|sid|tid|qid)\b", text, re.I)
        return m.group(0) if m else None

    @staticmethod
    def _duration(text: str) -> Optional[str]:
        m = re.search(r"for\s+\d+\s+(?:days|weeks)", text, re.I)
        return m.group(0) if m else None


# --------------------------------------------------------------------------- #
# Failing implementation (tests)
# --------------------------------------------------------------------------- #

class FailingLLM:
    """Always raises — exercises API-failure and retry-limit handling."""

    provider = "failing"

    def extract(self, chunks, use_fewshot: bool = True, feedback: str = "") -> ExtractionEnvelope:
        raise LLMError("simulated LLM failure")

    def answer(self, question: str, chunks) -> str:
        raise LLMError("simulated LLM failure")


# --------------------------------------------------------------------------- #
# Claude implementation
# --------------------------------------------------------------------------- #

class ClaudeLLM:
    """Real Anthropic model using structured output."""

    provider = "claude"

    def __init__(self, settings: Settings):
        self.settings = settings
        try:
            import anthropic  # imported lazily so mock mode needs no dependency
        except ImportError as exc:  # pragma: no cover
            raise LLMError("anthropic package not installed; use PAWPAL_LLM_PROVIDER=mock") from exc
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def extract(
        self, chunks: list[RetrievedChunk], use_fewshot: bool = True, feedback: str = ""
    ) -> ExtractionEnvelope:
        prompt = build_extraction_prompt(chunks, use_fewshot=use_fewshot, feedback=feedback)
        log_event("extraction_llm_call", provider="claude", chunks=len(chunks), fewshot=use_fewshot)
        try:
            resp = self._client.messages.parse(
                model=self.settings.model,
                max_tokens=2000,
                system=SYSTEM_EXTRACTION,
                messages=[{"role": "user", "content": prompt}],
                output_format=ExtractionEnvelope,
            )
        except (
            self._anthropic.AuthenticationError,
            self._anthropic.PermissionDeniedError,
        ) as exc:
            log_event("api_failure", provider="claude", error_type=type(exc).__name__)
            raise LLMError(
                "Claude authentication failed. Check ANTHROPIC_API_KEY.",
                retryable=False,
            ) from exc
        except self._anthropic.APIError as exc:
            log_event("api_failure", provider="claude", error_type=type(exc).__name__)
            if _is_auth_error(exc):
                raise LLMError(
                    "Claude authentication failed. Check ANTHROPIC_API_KEY.",
                    retryable=False,
                ) from exc
            raise LLMError(_GENERIC_LLM_ERROR_MESSAGE) from exc
        if getattr(resp, "stop_reason", None) == "refusal":
            log_event("model_refusal", provider="claude")
            raise LLMError("Model refused the request.")
        parsed = getattr(resp, "parsed_output", None)
        if parsed is None:
            raise LLMError("Model returned no parseable structured output.")
        return parsed

    def answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        prompt = build_qa_prompt(question, chunks)
        log_event("qa_llm_call", provider="claude", chunks=len(chunks))
        try:
            resp = self._client.messages.create(
                model=self.settings.model,
                max_tokens=1000,
                system=SYSTEM_QA,
                messages=[{"role": "user", "content": prompt}],
            )
        except (
            self._anthropic.AuthenticationError,
            self._anthropic.PermissionDeniedError,
        ) as exc:
            log_event("api_failure", provider="claude", error_type=type(exc).__name__)
            raise LLMError(
                "Claude authentication failed. Check ANTHROPIC_API_KEY.",
                retryable=False,
            ) from exc
        except self._anthropic.APIError as exc:
            log_event("api_failure", provider="claude", error_type=type(exc).__name__)
            if _is_auth_error(exc):
                raise LLMError(
                    "Claude authentication failed. Check ANTHROPIC_API_KEY.",
                    retryable=False,
                ) from exc
            raise LLMError(_GENERIC_LLM_ERROR_MESSAGE) from exc
        if getattr(resp, "stop_reason", None) == "refusal":
            return "I can't help with that request. Please consult your veterinarian."
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def build_llm(settings: Settings) -> LLMClient:
    """Factory: pick the provider from settings, falling back to mock."""
    if settings.use_claude():
        try:
            return ClaudeLLM(settings)
        except LLMError:
            log_event("llm_fallback", to="mock", reason="claude_init_failed")
            return MockLLM()
    return MockLLM()
