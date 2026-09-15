"""Pydantic I/O models for the visitor-session surface (/api/session)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class SessionInfo(BaseModel):
    # "demo": an anonymous, seeded sandbox private to this browser that
    # expires. "owner": the persistent space unlocked by the owner key.
    kind: Literal["demo", "owner"]
    # When the demo sandbox and everything in it is deleted (UTC). None for
    # the owner space, which never expires.
    expires_at: Optional[datetime] = None
    # The model extraction and Ask run on for this session: "mock" is
    # PawPal's free rule-based extractor (every demo sandbox), "claude" the
    # live model (the owner space, when the server is configured for it).
    ai_provider: Literal["mock", "claude"] = "mock"
