"""In production the API answers only requests that came through CloudFront.

API Gateway's own ``execute-api`` URL is public. CloudFront adds a secret
header (``X-PawPal-Origin-Verify``) to every request it forwards to the API,
and this middleware refuses any request without the right value -- so the
site's single origin, its HTTPS and caching rules, and the session cookie's
scoping to that one domain cannot be sidestepped by calling API Gateway
directly.

It is on only when the deployment configures it (the secret, or the SSM
parameter it is loaded from), and then it fails closed: configured but not
loaded refuses everything rather than letting everything through.
"""

from __future__ import annotations

import json
import os
import secrets as _secrets
from typing import Optional

ORIGIN_VERIFY_HEADER = b"x-pawpal-origin-verify"


def origin_verify_required() -> bool:
    return bool(
        os.getenv("PAWPAL_ORIGIN_VERIFY_SECRET", "").strip() or os.getenv("PAWPAL_ORIGIN_VERIFY_PARAMETER", "").strip()
    )


class OriginVerifyMiddleware:
    def __init__(self, app, secret: Optional[str]):
        self.app = app
        self._secret = (secret or "").strip().encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        provided = b""
        for name, value in scope.get("headers", []):
            if name.lower() == ORIGIN_VERIFY_HEADER:
                provided = value
                break
        if self._secret and _secrets.compare_digest(provided, self._secret):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"detail": "Forbidden"}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})
