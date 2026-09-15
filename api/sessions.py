"""Who a request acts for: an anonymous demo visitor, or the owner.

PawPal has no accounts, but it is public, so the old single-user assumption --
every request reads and writes the one ``"owner"`` row -- would have handed
every visitor the same pets, records and audit trail. Instead each request is
resolved to an :class:`OwnerContext` and every storage call goes through a
repository bound to that owner (api/repositories/base.py).

**Demo visitors.** The first API request without a session gets a new one: a
256-bit random token from ``secrets``, set as an ``HttpOnly``, ``SameSite=Lax``
cookie scoped to ``/api`` (``Secure`` when ``PAWPAL_COOKIE_SECURE`` is on, as it
is in production), and a sandbox seeded from the demo dataset (api/demo/). The
owner id is a SHA-256 of the token, never the token itself, so an owner id
appearing in a log or a response grants nothing. Sessions last
``PAWPAL_DEMO_TTL_HOURS`` (default 48) from creation. Expiry is checked on every
request against the stored expiry time -- DynamoDB's TTL can take days to
physically delete an item, and a sandbox must read as gone the moment it
expires, not whenever cleanup gets to it. An expired or unknown cookie simply
starts a new sandbox.

**The owner.** A request carrying ``X-PawPal-Owner-Key`` equal to
``PAWPAL_OWNER_KEY`` acts for the persistent owner space: fixed id ``"owner"``
(the id the single-user app always used, so existing local data lands there),
no expiry. A key that does not match is refused with 401 rather than quietly
treated as a demo visit, so a mistyped key is noticed -- and it can never reach
the owner's data or anything the owner key unlocks. With no key configured on
the server, owner access is unavailable (503).

The cookie is emitted by :class:`SessionCookieMiddleware`, not by the
dependency's ``Response``: a dependency's response headers are lost when the
endpoint raises, and a visitor whose first request is a 404 must still get the
session that request created.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from api.backend import get_demo_seeder, get_storage_backend
from api.clock import ClientClock, get_client_clock
from api.demo.seed import DemoSeeder
from api.repositories.base import KIND_DEMO, KIND_OWNER, OwnerRecord, StorageBackend

SESSION_COOKIE = "pawpal_session"
OWNER_KEY_HEADER = "X-PawPal-Owner-Key"
# The single-user app's owner row id; see the module docstring.
OWNER_SPACE_ID = "owner"

_STATE_KEY = "pawpal_session_cookie"
# secrets.token_urlsafe(32): 32 random bytes, 43 url-safe base64 characters.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}")

_log = logging.getLogger("pawpal.sessions")


def demo_ttl_seconds() -> int:
    try:
        hours = float(os.getenv("PAWPAL_DEMO_TTL_HOURS", "48"))
    except ValueError:
        hours = 48.0
    return int(min(max(hours, 1.0), 7 * 24) * 3600)


def cookie_secure() -> bool:
    return os.getenv("PAWPAL_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}


def configured_owner_key() -> str:
    return os.getenv("PAWPAL_OWNER_KEY", "").strip()


def owner_key_matches(provided: Optional[str]) -> bool:
    """Constant-time comparison against PAWPAL_OWNER_KEY; False when either is empty."""
    configured = configured_owner_key()
    if not configured or not provided:
        return False
    return secrets.compare_digest(provided.strip().encode("utf-8"), configured.encode("utf-8"))


def demo_owner_id(token: str) -> str:
    return "demo_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def _now_epoch() -> int:
    return int(time.time())


@dataclass(frozen=True)
class OwnerContext:
    owner: OwnerRecord
    session_token: Optional[str] = field(default=None, repr=False)

    @property
    def owner_id(self) -> str:
        return self.owner.owner_id

    @property
    def kind(self) -> str:
        return self.owner.kind

    @property
    def expires_at(self) -> Optional[int]:
        return self.owner.expires_at

    @property
    def is_owner(self) -> bool:
        return self.owner.kind == KIND_OWNER


def _queue_cookie(request: Request, token: str, expires_at: int) -> None:
    request.state.__setattr__(_STATE_KEY, (token, max(0, expires_at - _now_epoch())))


def session_cookie_header(token: str, max_age: int) -> str:
    parts = [f"{SESSION_COOKIE}={token}", "Path=/api", f"Max-Age={max_age}", "HttpOnly", "SameSite=Lax"]
    if cookie_secure():
        parts.append("Secure")
    return "; ".join(parts)


def _seed(backend: StorageBackend, seeder: Optional[DemoSeeder], owner: OwnerRecord, clock: ClientClock) -> None:
    if seeder is not None:
        # Seeded on the visitor's own today, so the sample reminders' "due in
        # N days" are counted from their calendar, not the server's.
        seeder.seed(backend, owner, clock.today)
    else:
        backend.create_owner(owner)


def start_demo_session(
    request: Request, backend: StorageBackend, seeder: Optional[DemoSeeder], clock: ClientClock
) -> OwnerContext:
    now = _now_epoch()
    try:
        backend.purge_expired(now)
    except Exception:  # cleanup is best-effort; expiry is enforced on read
        _log.exception("Purging expired demo sessions failed")
    token = secrets.token_urlsafe(32)
    owner = OwnerRecord(owner_id=demo_owner_id(token), kind=KIND_DEMO, expires_at=now + demo_ttl_seconds())
    _seed(backend, seeder, owner, clock)
    _queue_cookie(request, token, owner.expires_at)  # type: ignore[arg-type]
    return OwnerContext(owner=owner, session_token=token)


def reset_demo_session(
    request: Request,
    ctx: OwnerContext,
    backend: StorageBackend,
    seeder: Optional[DemoSeeder],
    clock: ClientClock,
) -> OwnerContext:
    """Delete the sandbox and seed it afresh under the same session, with a
    renewed expiry. Only ever touches this visitor's own owner id."""
    if ctx.is_owner or not ctx.session_token:
        raise ValueError("only a demo session can be reset")
    owner = OwnerRecord(owner_id=ctx.owner_id, kind=KIND_DEMO, expires_at=_now_epoch() + demo_ttl_seconds())
    backend.delete_owner(ctx.owner_id)
    _seed(backend, seeder, owner, clock)
    _queue_cookie(request, ctx.session_token, owner.expires_at)  # type: ignore[arg-type]
    return OwnerContext(owner=owner, session_token=ctx.session_token)


def get_owner_context(
    request: Request,
    backend: StorageBackend = Depends(get_storage_backend),
    seeder: Optional[DemoSeeder] = Depends(get_demo_seeder),
    clock: ClientClock = Depends(get_client_clock),
    owner_key: Optional[str] = Header(default=None, alias=OWNER_KEY_HEADER),
) -> OwnerContext:
    """FastAPI dependency: the owner this request acts for (see module docstring).

    Cached per request by FastAPI, so every dependency that needs it within
    one request sees the same context -- and at most one session is created.
    """
    if owner_key is not None and owner_key.strip():
        if not configured_owner_key():
            raise HTTPException(status_code=503, detail="Owner access is not configured on this server.")
        if not owner_key_matches(owner_key):
            raise HTTPException(status_code=401, detail="Invalid owner key.")
        owner = backend.get_owner(OWNER_SPACE_ID)
        if owner is None:
            owner = OwnerRecord(owner_id=OWNER_SPACE_ID, kind=KIND_OWNER, expires_at=None)
            backend.create_owner(owner)
        return OwnerContext(owner=owner)

    token = request.cookies.get(SESSION_COOKIE)
    if token and _TOKEN_RE.fullmatch(token):
        existing = backend.get_owner(demo_owner_id(token))
        if existing is not None and existing.kind == KIND_DEMO and not existing.is_expired(_now_epoch()):
            return OwnerContext(owner=existing, session_token=token)
    return start_demo_session(request, backend, seeder, clock)


class SessionCookieMiddleware:
    """Pure ASGI middleware that attaches a queued session cookie to whatever
    response the request produced -- success or error alike."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = scope.setdefault("state", {})

        async def send_with_cookie(message):
            if message["type"] == "http.response.start":
                pending = state.get(_STATE_KEY)
                if pending:
                    headers = list(message.get("headers", []))
                    headers.append((b"set-cookie", session_cookie_header(*pending).encode("latin-1")))
                    message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cookie)
