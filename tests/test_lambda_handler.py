"""The Lambda entry point, driven by API Gateway HTTP API (payload 2.0) events.

These invoke ``api.lambda_handler.handler`` exactly as Lambda does: an event
dict in, a response dict out, with DynamoDB and SSM Parameter Store mocked by
moto. What they pin down is everything that differs from running under
uvicorn: secrets loaded from SSM at import, cookies arriving as the event's
``cookies`` array and leaving as the response's, binary uploads arriving
base64-encoded, the CloudFront origin check, and whether the largest upload
the deployment allows still fits in a Lambda invoke payload.
"""

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from unittest import mock

import boto3
import pytest

from storage_backends import TABLE, moto_dynamodb

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES = REPO_ROOT / "data" / "sample_documents"

OWNER_KEY = "lambda-owner-key"
ORIGIN_SECRET = "cloudfront-origin-secret"
MAX_UPLOAD = 4 * 1024 * 1024
# Lambda's synchronous invoke request payload limit: "6 MB", enforced as
# 6,291,456 bytes. The whole event -- headers, cookies, base64 body -- counts.
LAMBDA_INVOKE_LIMIT = 6 * 1024 * 1024


class LambdaContext:
    function_name = "pawpal-api"
    memory_limit_in_mb = 1024
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:pawpal-api"
    aws_request_id = "00000000-0000-0000-0000-000000000000"

    @staticmethod
    def get_remaining_time_in_millis() -> int:
        return 29_000


def http_api_event(
    method: str,
    path: str,
    *,
    query: str = "",
    headers: dict | None = None,
    cookies: list[str] | None = None,
    body: str | None = None,
    is_base64: bool = False,
    origin_secret: str | None = ORIGIN_SECRET,
) -> dict:
    """An event shaped like the ones CloudFront -> HTTP API -> Lambda delivers."""
    all_headers = {
        "host": "abc123.execute-api.us-east-1.amazonaws.com",
        "user-agent": "Amazon CloudFront",
        "via": "2.0 0123456789abcdef0123456789abcdef.cloudfront.net (CloudFront)",
        "x-amz-cf-id": "A" * 56,
        "x-amzn-trace-id": "Root=1-00000000-000000000000000000000000",
        "x-forwarded-for": "203.0.113.10, 130.176.0.1",
        "x-forwarded-port": "443",
        "x-forwarded-proto": "https",
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "x-pawpal-client-now": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if origin_secret is not None:
        all_headers["x-pawpal-origin-verify"] = origin_secret
    all_headers.update({k.lower(): v for k, v in (headers or {}).items()})
    event = {
        "version": "2.0",
        "routeKey": "ANY /api/{proxy+}",
        "rawPath": path,
        "rawQueryString": query,
        "headers": all_headers,
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "abc123",
            "domainName": "abc123.execute-api.us-east-1.amazonaws.com",
            "domainPrefix": "abc123",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "130.176.0.1",
                "userAgent": "Amazon CloudFront",
            },
            "requestId": str(uuid.uuid4()),
            "routeKey": "ANY /api/{proxy+}",
            "stage": "$default",
            "time": "15/Sep/2026:09:30:00 +0000",
            "timeEpoch": 1_789_464_600_000,
        },
        "isBase64Encoded": is_base64,
    }
    if cookies:
        event["cookies"] = cookies
    if body is not None:
        event["body"] = body
    return event


def multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = "----PawPalBoundary" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, (filename, data, content_type) in files.items():
        head = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        parts.append(head + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _cookie_pairs(response: dict) -> list[str]:
    return [c.split(";", 1)[0] for c in response.get("cookies") or []]


def _json(response: dict):
    return json.loads(response["body"])


@pytest.fixture
def invoke():
    """``invoke(event) -> response`` against a freshly imported handler."""
    env = {
        "AWS_LAMBDA_FUNCTION_NAME": "pawpal-api",
        "PAWPAL_STORAGE_BACKEND": "dynamodb",
        "PAWPAL_DYNAMODB_TABLE": TABLE,
        "PAWPAL_COOKIE_SECURE": "1",
        "PAWPAL_MAX_UPLOAD_BYTES": str(MAX_UPLOAD),
        "PAWPAL_OWNER_KEY_PARAMETER": "/pawpal/test/owner-key",
        "PAWPAL_ORIGIN_VERIFY_PARAMETER": "/pawpal/test/origin-verify",
        "ANTHROPIC_API_KEY_PARAMETER": "/pawpal/test/anthropic-api-key",
        "PAWPAL_LLM_PROVIDER": "mock",
    }
    saved = {name: sys.modules.get(name) for name in ("api.lambda_handler",)}
    from api import backend as backend_module
    from api import deps

    with moto_dynamodb(), mock.patch.dict(os.environ, env):
        for secret in ("PAWPAL_OWNER_KEY", "PAWPAL_ORIGIN_VERIFY_SECRET", "ANTHROPIC_API_KEY"):
            os.environ.pop(secret, None)
        ssm = boto3.client("ssm", region_name="us-east-1")
        ssm.put_parameter(Name="/pawpal/test/owner-key", Value=OWNER_KEY, Type="SecureString")
        ssm.put_parameter(Name="/pawpal/test/origin-verify", Value=ORIGIN_SECRET, Type="SecureString")
        # The Anthropic parameter is deliberately absent: owner space falls back to the free model.
        backend_module.get_storage_backend.cache_clear()
        deps.get_claude_llm.cache_clear()
        sys.modules.pop("api.lambda_handler", None)
        try:
            module = importlib.import_module("api.lambda_handler")
            yield lambda event: module.handler(event, LambdaContext())
        finally:
            backend_module.get_storage_backend.cache_clear()
            deps.get_claude_llm.cache_clear()
            for name, module_obj in saved.items():
                if module_obj is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module_obj


class TestThroughApiGateway:
    def test_healthz(self, invoke):
        resp = invoke(http_api_event("GET", "/api/healthz"))
        assert resp["statusCode"] == 200
        assert _json(resp) == {"status": "ok"}
        assert resp["headers"]["content-type"] == "application/json"

    @pytest.mark.parametrize("secret", [None, "", "wrong-secret"], ids=["missing", "empty", "wrong"])
    def test_requests_that_did_not_come_through_cloudfront_are_refused(self, invoke, secret):
        resp = invoke(http_api_event("GET", "/api/session", origin_secret=secret))
        assert resp["statusCode"] == 403
        assert not resp.get("cookies")  # refused before any session was created

    def test_session_cookie_round_trip_and_seeded_sandbox(self, invoke):
        first = invoke(http_api_event("GET", "/api/session"))
        assert first["statusCode"] == 200
        body = _json(first)
        assert body["kind"] == "demo" and body["ai_provider"] == "mock"
        assert body["max_upload_bytes"] == MAX_UPLOAD
        [set_cookie] = first["cookies"]
        assert set_cookie.startswith("pawpal_session=")
        assert {"HttpOnly", "Secure", "SameSite=Lax", "Path=/api"} <= {p.strip() for p in set_cookie.split(";")}

        cookies = _cookie_pairs(first)
        pets = invoke(http_api_event("GET", "/api/pets", cookies=cookies))
        assert sorted(p["name"] for p in _json(pets)) == ["Bella", "Luna", "Max"]
        assert not pets.get("cookies")  # same session, no new cookie

        created = invoke(
            http_api_event(
                "POST", "/api/pets", cookies=cookies, headers={"content-type": "application/json"},
                body=json.dumps({"name": "Pip", "pet_type": "bird", "age": 1}),
            )
        )
        assert created["statusCode"] == 201
        names = [p["name"] for p in _json(invoke(http_api_event("GET", "/api/pets", cookies=cookies)))]
        assert "Pip" in names

        # A different visitor (no cookie) gets their own sandbox.
        other = invoke(http_api_event("GET", "/api/pets"))
        assert "Pip" not in [p["name"] for p in _json(other)]

    def test_query_strings_reach_the_app(self, invoke):
        cookies = _cookie_pairs(invoke(http_api_event("GET", "/api/session")))
        done = invoke(http_api_event("GET", "/api/tasks", query="status=completed", cookies=cookies))
        assert [t["name"] for t in _json(done)] == ["Refill water fountain"]

    @pytest.mark.parametrize(
        "filename, content_type",
        [
            ("max_vaccine.pdf", "application/pdf"),
            ("bella_meds.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("luna_missing_due.txt", "text/plain"),
        ],
    )
    def test_base64_multipart_upload_extracts_and_can_be_asked_about(self, invoke, filename, content_type):
        cookies = _cookie_pairs(invoke(http_api_event("GET", "/api/session")))
        pet_id = _json(invoke(http_api_event("GET", "/api/pets", cookies=cookies)))[0]["pet_id"]
        body, multipart_type = multipart({}, {"file": (filename, (SAMPLES / filename).read_bytes(), content_type)})

        resp = invoke(
            http_api_event(
                "POST", f"/api/health/pets/{pet_id}/documents:extract", cookies=cookies,
                headers={"content-type": multipart_type},
                body=base64.b64encode(body).decode(), is_base64=True,
            )
        )
        assert resp["statusCode"] == 200, resp["body"][:500]
        extracted = _json(resp)
        assert extracted["doc_type"] == Path(filename).suffix[1:]
        assert extracted["result"]["records"]

        answer = invoke(
            http_api_event(
                "POST", f"/api/health/pets/{pet_id}/ask", cookies=cookies,
                headers={"content-type": "application/json"},
                body=json.dumps({"question": "What vaccine or medication is recorded?",
                                 "document_id": extracted["document_id"]}),
            )
        )
        assert answer["statusCode"] == 200
        assert _json(answer)["citations"]

    def test_pasted_text_as_a_form_field(self, invoke):
        cookies = _cookie_pairs(invoke(http_api_event("GET", "/api/session")))
        pet_id = _json(invoke(http_api_event("GET", "/api/pets", cookies=cookies)))[0]["pet_id"]
        body, multipart_type = multipart({"text": "Rabies vaccine administered 2025-03-01. Next due 2026-03-01."}, {})
        resp = invoke(
            http_api_event(
                "POST", f"/api/health/pets/{pet_id}/documents:extract", cookies=cookies,
                headers={"content-type": multipart_type}, body=base64.b64encode(body).decode(), is_base64=True,
            )
        )
        assert resp["statusCode"] == 200 and _json(resp)["result"]["records"]

    def test_an_upload_over_the_cap_is_refused_with_a_reason(self, invoke):
        cookies = _cookie_pairs(invoke(http_api_event("GET", "/api/session")))
        pet_id = _json(invoke(http_api_event("GET", "/api/pets", cookies=cookies)))[0]["pet_id"]
        body, multipart_type = multipart({}, {"file": ("big.txt", b"x" * (MAX_UPLOAD + 1), "text/plain")})
        resp = invoke(
            http_api_event(
                "POST", f"/api/health/pets/{pet_id}/documents:extract", cookies=cookies,
                headers={"content-type": multipart_type}, body=base64.b64encode(body).decode(), is_base64=True,
            )
        )
        assert resp["statusCode"] == 422
        assert _json(resp)["detail"] == "File exceeds the 4 MB limit."

    @pytest.mark.parametrize("path", ["/api/nope", "/api/health/nope", "/app/health", "/"])
    def test_unknown_paths_are_json_404s(self, invoke, path):
        resp = invoke(http_api_event("GET", path))
        assert resp["statusCode"] == 404
        assert resp["headers"]["content-type"] == "application/json"
        assert _json(resp) == {"detail": "Not Found"}

    def test_the_owner_key_from_ssm_opens_the_owner_space(self, invoke):
        owner = invoke(http_api_event("GET", "/api/session", headers={"x-pawpal-owner-key": OWNER_KEY}))
        assert owner["statusCode"] == 200
        body = _json(owner)
        # No Anthropic parameter exists in this test, so even the owner gets the free model.
        assert body["kind"] == "owner" and body["ai_provider"] == "mock"
        wrong = invoke(http_api_event("GET", "/api/session", headers={"x-pawpal-owner-key": "nope"}))
        assert wrong["statusCode"] == 401


class TestPayloadBudget:
    """The upload cap is set from the invoke payload limit, not guessed.

    The event for the largest allowed upload -- multipart framing, base64's
    4/3 growth, CloudFront's forwarded headers, a session cookie -- must fit
    under 6,291,456 bytes with room to spare, and the old 5 MB cap must not.
    """

    @staticmethod
    def _upload_event_size(file_bytes: int) -> int:
        body, multipart_type = multipart({}, {"file": ("scan.pdf", os.urandom(file_bytes), "application/pdf")})
        event = http_api_event(
            "POST", "/api/health/pets/6f1c2b1e-0000-4000-8000-000000000000/documents:extract",
            cookies=["pawpal_session=" + "A" * 43],
            headers={
                "content-type": multipart_type,
                "content-length": str(len(body)),
                "origin": "https://pawpal.manushri.dev",
                "referer": "https://pawpal.manushri.dev/app/health",
                "x-pawpal-owner-key": "K" * 64,
                "sec-ch-ua": '"Chromium";v="140", "Microsoft Edge";v="140"',
            },
            body=base64.b64encode(body).decode(),
            is_base64=True,
        )
        return len(json.dumps(event).encode("utf-8"))

    def test_the_largest_allowed_upload_fits_with_headroom(self):
        size = self._upload_event_size(MAX_UPLOAD)
        headroom = LAMBDA_INVOKE_LIMIT - size
        assert headroom >= 512 * 1024, f"event is {size} bytes; only {headroom} bytes of headroom"

    def test_the_previous_5_mb_cap_would_not_fit(self):
        assert self._upload_event_size(5 * 1024 * 1024) > LAMBDA_INVOKE_LIMIT


class TestSecretsLoading:
    def test_fills_only_unset_variables_and_never_logs_values(self, caplog):
        from api.secrets import load_secrets_from_ssm

        with moto_dynamodb(), mock.patch.dict(
            os.environ,
            {
                "PAWPAL_OWNER_KEY_PARAMETER": "/p/owner",
                "ANTHROPIC_API_KEY_PARAMETER": "/p/anthropic",
                "PAWPAL_ORIGIN_VERIFY_PARAMETER": "/p/missing",
                "ANTHROPIC_API_KEY": "already-set",
            },
        ):
            os.environ.pop("PAWPAL_OWNER_KEY", None)
            os.environ.pop("PAWPAL_ORIGIN_VERIFY_SECRET", None)
            ssm = boto3.client("ssm", region_name="us-east-1")
            ssm.put_parameter(Name="/p/owner", Value="owner-value", Type="SecureString")
            ssm.put_parameter(Name="/p/anthropic", Value="sk-from-ssm", Type="SecureString")

            loaded = load_secrets_from_ssm(ssm)

            assert loaded == ["PAWPAL_OWNER_KEY"]
            assert os.environ["PAWPAL_OWNER_KEY"] == "owner-value"
            assert os.environ["ANTHROPIC_API_KEY"] == "already-set"
            assert "PAWPAL_ORIGIN_VERIFY_SECRET" not in os.environ
        assert "owner-value" not in caplog.text and "sk-from-ssm" not in caplog.text

    def test_an_unreachable_ssm_loads_nothing(self):
        from api.secrets import load_secrets_from_ssm

        class Broken:
            def get_parameters(self, **kwargs):
                raise RuntimeError("no network")

        with mock.patch.dict(os.environ, {"PAWPAL_OWNER_KEY_PARAMETER": "/p/owner"}):
            os.environ.pop("PAWPAL_OWNER_KEY", None)
            assert load_secrets_from_ssm(Broken()) == []
            assert "PAWPAL_OWNER_KEY" not in os.environ


def test_origin_check_fails_closed_when_its_secret_did_not_load(make_client, monkeypatch):
    from api.main import create_app

    monkeypatch.setenv("PAWPAL_ORIGIN_VERIFY_PARAMETER", "/p/origin")
    monkeypatch.delenv("PAWPAL_ORIGIN_VERIFY_SECRET", raising=False)
    client = make_client(app=create_app(serve_frontend=False))
    assert client.get("/api/healthz").status_code == 403
    assert client.get("/api/healthz", headers={"X-PawPal-Origin-Verify": ""}).status_code == 403
