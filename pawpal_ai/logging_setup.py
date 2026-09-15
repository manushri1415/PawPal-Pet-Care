"""Structured, privacy-preserving logging for PawPal AI.

We log *events* as JSON lines (one object per line) to ``logs/app.log`` with a
size-capped rotating handler. The golden rule: **never log document text,
medication instructions, API keys, or PII** — only IDs, counts, booleans, and
short enum-like status strings. A small redactor scrubs a denylist of keys and
truncates anything suspiciously long as a backstop.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from typing import Any

from pawpal_ai.config import get_settings

_LOGGER_NAME = "pawpal_ai"
_CONFIGURED = False

# Keys whose values must never reach the log, even if a caller passes them.
_REDACT_KEYS = {
    "text",
    "content",
    "document_text",
    "raw_text",
    "supporting_text",
    "instructions",
    "dosage",
    "notes",
    "api_key",
    "anthropic_api_key",
    "authorization",
    "prompt",
    "answer",
    "email",
    "phone",
    "name",
    # `error`/`error_message` carry `str(exc)` at call sites like
    # extraction_agent.py and qa.py. LLMError messages are vetted safe (see
    # pawpal_ai/llm.py), but the broader `except Exception` those call sites
    # use as a safety net can still catch an SDK-internal or parsing error
    # whose text echoes fragments of the model's raw response -- exactly the
    # kind of thing this log must never carry. `error_type` (the exception's
    # class name) is unaffected and stays out of this denylist.
    "error",
    "error_message",
}
_MAX_VALUE_LEN = 200


class JsonLineFormatter(logging.Formatter):
    """Render each record as a single compact JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload["fields"] = _redact(fields)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _redact(fields: dict[str, Any]) -> dict[str, Any]:
    """Drop/redact sensitive values so private data never lands in the log."""
    clean: dict[str, Any] = {}
    for key, value in fields.items():
        if key.lower() in _REDACT_KEYS:
            clean[key] = "[REDACTED]"
            continue
        if isinstance(value, str) and len(value) > _MAX_VALUE_LEN:
            # Backstop: truncate long free text (likely document content).
            clean[key] = value[:40] + f"...[+{len(value) - 40} chars]"
        elif isinstance(value, dict):
            clean[key] = _redact(value)
        else:
            clean[key] = value
    return clean


def _configure() -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger(_LOGGER_NAME)
    if _CONFIGURED:
        return logger
    settings = get_settings()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        settings.resolved_log_path(),
        maxBytes=1_000_000,  # 1 MB per file
        backupCount=3,  # keep 3 rotations => bounded retention
        encoding="utf-8",
    )
    handler.setFormatter(JsonLineFormatter())
    # Avoid duplicate handlers if _configure is somehow reached twice.
    if not logger.handlers:
        logger.addHandler(handler)
    _CONFIGURED = True
    return logger


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log a structured event. ``fields`` are redacted before writing.

    Example::

        log_event("document_accepted", document_id=doc_id, chars=len(text))
    """
    logger = _configure()
    logger.log(level, event, extra={"fields": fields})


def get_logger() -> logging.Logger:
    return _configure()
