"""Environment-driven configuration for PawPal AI.

All tunables live here so the rest of the code never reads ``os.environ``
directly. Values come from the process environment (optionally loaded from a
``.env`` file via python-dotenv). Sensible defaults keep the whole system
runnable with **no configuration and no API key** (the ``mock`` provider).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv is optional at runtime; load a .env if present.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv missing is non-fatal
    pass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of configuration for one run.

    Build instances via :func:`get_settings`, which reads the environment
    freshly each call (so tests can monkeypatch ``os.environ`` between cases).
    """

    llm_provider: str
    model: str
    anthropic_api_key: str
    retrieval_k: int
    max_attempts: int
    evidence_threshold: float
    due_soon_days: int
    db_path: str
    chroma_path: str
    log_path: str

    def resolved_db_path(self) -> Path:
        p = Path(self.db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def resolved_chroma_path(self) -> Path:
        p = Path(self.chroma_path)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def resolved_log_path(self) -> Path:
        p = Path(self.log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def use_claude(self) -> bool:
        """True only when the operator explicitly opted into the live model
        *and* supplied a key. Otherwise we fall back to the mock provider so the
        app never hard-crashes for lack of credentials."""
        return self.llm_provider == "claude" and bool(self.anthropic_api_key)


def get_settings() -> Settings:
    """Return a fresh Settings snapshot, reading the environment each call."""
    return Settings(
        llm_provider=os.getenv("PAWPAL_LLM_PROVIDER", "mock").strip().lower(),
        model=os.getenv("PAWPAL_MODEL", "claude-haiku-4-5").strip(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        retrieval_k=_int("PAWPAL_RETRIEVAL_K", 4),
        max_attempts=_int("PAWPAL_MAX_ATTEMPTS", 3),
        evidence_threshold=_float("PAWPAL_EVIDENCE_THRESHOLD", 0.5),
        due_soon_days=_int("PAWPAL_DUE_SOON_DAYS", 30),
        db_path=os.getenv("PAWPAL_DB_PATH", "data/pawpal.db"),
        chroma_path=os.getenv("PAWPAL_CHROMA_PATH", "data/chroma"),
        log_path=os.getenv("PAWPAL_LOG_PATH", "logs/app.log"),
    )
