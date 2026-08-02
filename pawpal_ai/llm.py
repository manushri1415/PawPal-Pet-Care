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
    """Raised when the LLM call fails or returns unusable output."""


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
            name = canon.title()
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
        except self._anthropic.APIError as exc:
            log_event("api_failure", provider="claude", error_type=type(exc).__name__)
            raise LLMError(f"Claude API error: {exc}") from exc
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
        except self._anthropic.APIError as exc:
            log_event("api_failure", provider="claude", error_type=type(exc).__name__)
            raise LLMError(f"Claude API error: {exc}") from exc
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
