"""GET /api/session and POST /api/session/reset -- the visitor's own sandbox.

The frontend calls GET first, before any other request, so a first visit
creates exactly one demo session instead of one per parallel query.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from api.backend import get_demo_seeder, get_storage_backend
from api.clock import ClientClock, get_client_clock
from api.schemas.session import SessionInfo
from api.sessions import OwnerContext, get_owner_context, reset_demo_session

router = APIRouter(prefix="/api/session", tags=["session"])


def _info(ctx: OwnerContext) -> SessionInfo:
    expires = (
        datetime.fromtimestamp(ctx.expires_at, tz=timezone.utc) if ctx.expires_at is not None else None
    )
    return SessionInfo(kind=ctx.kind, expires_at=expires)


@router.get("", response_model=SessionInfo)
def get_session(ctx: OwnerContext = Depends(get_owner_context)) -> SessionInfo:
    return _info(ctx)


@router.post("/reset", response_model=SessionInfo)
def reset_session(
    request: Request,
    ctx: OwnerContext = Depends(get_owner_context),
    backend=Depends(get_storage_backend),
    seeder=Depends(get_demo_seeder),
    clock: ClientClock = Depends(get_client_clock),
) -> SessionInfo:
    """Wipe this visitor's sandbox and start it again from the seed.

    Only a demo sandbox can be reset. The owner space holds real data and has
    no seed to go back to, so a reset there is refused rather than performed.
    """
    if ctx.is_owner:
        raise HTTPException(status_code=403, detail="Only a demo sandbox can be reset.")
    return _info(reset_demo_session(request, ctx, backend, seeder, clock))
