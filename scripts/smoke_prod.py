"""Production smoke test for a deployed PawPal (CloudFront + S3 + API Gateway + Lambda).

    python scripts/smoke_prod.py https://pawpal.manushri.dev
    PAWPAL_SMOKE_OWNER_KEY=... python scripts/smoke_prod.py https://pawpal.manushri.dev --owner

Walks the site the way two visitors would: static pages and caching, the demo
session and its seeded data, isolation between two cookie jars, scheduler and
health features end to end on the free model, Reset, and the API's JSON 404.
``--owner`` also checks the owner space with the key from
PAWPAL_SMOKE_OWNER_KEY (and, with ``--claude``, makes one real Claude
extraction and one Ask -- these cost money).

Leaves nothing behind but two demo sandboxes, which expire on their own. The
owner-space checks create one pet named "Smoke test" and delete it again.
Exit status is the number of failed checks.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime


class Visitor:
    def __init__(self, base: str, headers: dict | None = None):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.headers = headers or {}

    def request(self, method: str, path: str, body=None, form: dict | None = None, raw: bool = False):
        data = None
        headers = {"X-PawPal-Client-Now": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), **self.headers}
        if body is not None:
            data = json.dumps(body).encode()
            headers["content-type"] = "application/json"
        elif form is not None:
            boundary = "----smoke" + str(int(time.time() * 1000))
            parts = [
                f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in form.items()
            ]
            data = ("".join(parts) + f"--{boundary}--\r\n").encode()
            headers["content-type"] = f"multipart/form-data; boundary={boundary}"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=35) as resp:
                payload = resp.read()
                return resp.status, dict(resp.headers), payload if raw else _decode(payload)
        except urllib.error.HTTPError as err:
            payload = err.read()
            return err.code, dict(err.headers), payload if raw else _decode(payload)

    def session_cookie(self):
        return next((c for c in self.jar if c.name == "pawpal_session"), None)


def _decode(payload: bytes):
    try:
        return json.loads(payload) if payload else None
    except ValueError:
        return payload.decode("utf-8", "replace")


class Checks:
    def __init__(self):
        self.failures = []

    def __call__(self, name: str, ok: bool, detail: object = "") -> bool:
        print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  -> {str(detail)[:300]}"))
        if not ok:
            self.failures.append(name)
        return ok


def header(headers: dict, name: str) -> str:
    return next((v for k, v in headers.items() if k.lower() == name.lower()), "")


def run(base: str, owner: bool, claude: bool) -> int:
    check = Checks()
    anon = Visitor(base)

    # -- static site ---------------------------------------------------------
    for path in ("/", "/app", "/app/health"):
        status, headers, body = anon.request("GET", path, raw=True)
        check(f"GET {path} serves the app shell", status == 200 and b'<div id="root">' in body, status)
        check(f"GET {path} is not cached", "no-cache" in header(headers, "cache-control"), header(headers, "cache-control"))
    _, _, index = anon.request("GET", "/", raw=True)
    asset = next((part.split('"')[0] for part in index.decode().split('src="/assets/')[1:]), None)
    if check("index.html references a hashed bundle", bool(asset), index[:200]):
        status, headers, _ = anon.request("GET", f"/assets/{asset}", raw=True)
        check("hashed bundle is immutable", status == 200 and "immutable" in header(headers, "cache-control"),
              (status, header(headers, "cache-control")))
    status, _, body = anon.request("GET", "/assets/definitely-not-a-bundle-000.js", raw=True)
    check("a missing bundle is a 404, not the app shell", status == 404 and b'<div id="root">' not in body, status)
    status, headers, _ = anon.request("GET", "/", raw=True)
    check("security headers present", "max-age" in header(headers, "strict-transport-security"), headers)

    # -- API basics ------------------------------------------------------------
    status, headers, body = anon.request("GET", "/api/healthz")
    check("API health", status == 200 and body == {"status": "ok"}, (status, body))
    status, headers, body = anon.request("GET", "/api/nope")
    check("unknown API path is a JSON 404", status == 404 and isinstance(body, dict) and body.get("detail") == "Not Found",
          (status, body))

    # -- demo session ----------------------------------------------------------
    alice, bob = Visitor(base), Visitor(base)
    status, _, session = alice.request("GET", "/api/session")
    check("demo session created", status == 200 and session.get("kind") == "demo" and session.get("ai_provider") == "mock",
          (status, session))
    cookie = alice.session_cookie()
    check("session cookie is Secure and HttpOnly",
          bool(cookie) and cookie.secure and cookie.has_nonstandard_attr("HttpOnly"), cookie)

    _, _, pets = alice.request("GET", "/api/pets")
    check("seeded pets", sorted(p["name"] for p in pets or []) == ["Bella", "Luna", "Max"], pets)
    max_pet = next((p for p in pets or [] if p["name"] == "Max"), None)

    status, _, pet = alice.request("POST", "/api/pets", {"name": "Smoke", "pet_type": "dog", "age": 2})
    check("create pet", status == 201, (status, pet))
    status, _, task = alice.request(
        "POST", "/api/tasks",
        {"name": "Smoke walk", "category": "exercise", "duration": 20, "pet_id": pet["pet_id"], "frequency": "daily",
         "scheduled_time": "09:00"},
    )
    check("create recurring task", status == 201, (status, task))
    status, _, done = alice.request("POST", f"/api/tasks/{task['task_id']}/complete")
    check("complete task creates next occurrence", status == 200 and done.get("next_occurrence"), (status, done))
    status, _, plan = alice.request("POST", "/api/schedule/generate")
    today = datetime.now().strftime("%Y-%m-%d")
    check("schedule generated for local today",
          status == 200 and plan["schedule"] and all(i["start"].startswith(today) for i in plan["schedule"]), (status, plan))
    status, _, overlaps = alice.request("GET", "/api/tasks/overlaps")
    check("overlap warnings", status == 200 and overlaps["overlaps"], overlaps)

    # -- isolation ---------------------------------------------------------------
    bob.request("GET", "/api/session")
    status, _, _ = bob.request("GET", f"/api/pets/{pet['pet_id']}")
    check("another visitor cannot read the pet", status == 404, status)
    status, _, _ = bob.request("PATCH", f"/api/tasks/{task['task_id']}", {"name": "pwned"})
    check("another visitor cannot edit the task", status == 404, status)
    _, _, bob_pets = bob.request("GET", "/api/pets")
    check("another visitor has their own sandbox", "Smoke" not in [p["name"] for p in bob_pets or []], bob_pets)

    # -- health records on the free model ------------------------------------------
    if max_pet:
        status, _, care = alice.request("POST", f"/api/health/pets/{max_pet['pet_id']}/schedule-care")
        check("seeded reminders and conflict", status == 200 and care["reminders"] and care["conflicts"], (status, care))
        if care.get("conflicts"):
            conflict_id = care["conflicts"][0]["conflict_id"]
            status, _, resolved = alice.request("POST", f"/api/health/conflicts/{conflict_id}/resolve")
            check("resolve conflict", status == 200 and resolved.get("resolved") is True, (status, resolved))
        status, _, answer = alice.request("POST", f"/api/health/pets/{max_pet['pet_id']}/ask",
                                          {"question": "When is the distemper vaccine due?"})
        check("Ask about seeded records", status == 200 and answer.get("citations") and not answer.get("abstained"),
              (status, answer))
    status, _, extracted = alice.request(
        "POST", f"/api/health/pets/{pet['pet_id']}/documents:extract",
        form={"text": "Patient: Smoke\nRabies vaccine administered 2026-01-10. Next due 2027-01-10.\n"},
    )
    records = (extracted or {}).get("result", {}).get("records", []) if isinstance(extracted, dict) else []
    check("extract pasted text", status == 200 and records, (status, extracted))
    if records:
        status, _, approved = alice.request("POST", f"/api/health/records/{records[0]['record_id']}/approve")
        check("approve record", status == 200 and approved.get("review_status") == "approved", (status, approved))
        status, _, answer = alice.request("POST", f"/api/health/pets/{pet['pet_id']}/ask",
                                          {"question": "When is the rabies vaccine due?"})
        check("Ask about the new document", status == 200 and answer.get("citations"), (status, answer))
    status, _, audit = alice.request("GET", "/api/health/audit")
    check("audit trail", status == 200 and audit, (status, audit))

    status, _, reset = alice.request("POST", "/api/session/reset")
    _, _, after = alice.request("GET", "/api/pets")
    check("reset demo restores the seed", status == 200 and sorted(p["name"] for p in after or []) == ["Bella", "Luna", "Max"],
          (status, after))
    _, _, bob_after = bob.request("GET", "/api/pets")
    check("reset did not touch the other visitor", bob_after == bob_pets, bob_after)

    # -- owner space --------------------------------------------------------------
    if owner:
        key = os.environ.get("PAWPAL_SMOKE_OWNER_KEY", "")
        if check("PAWPAL_SMOKE_OWNER_KEY is set", bool(key)):
            wrong = Visitor(base, {"X-PawPal-Owner-Key": "not-the-key"})
            status, _, _ = wrong.request("GET", "/api/session")
            check("a wrong owner key is refused", status == 401, status)
            me = Visitor(base, {"X-PawPal-Owner-Key": key})
            status, _, session = me.request("GET", "/api/session")
            check("owner space opens", status == 200 and session.get("kind") == "owner" and session.get("expires_at") is None,
                  (status, session))
            if claude:
                check("owner space uses Claude", session.get("ai_provider") == "claude", session)
                status, _, smoke_pet = me.request("POST", "/api/pets", {"name": "Smoke test", "pet_type": "dog", "age": 1})
                started = time.monotonic()
                status, _, extracted = me.request(
                    "POST", f"/api/health/pets/{smoke_pet['pet_id']}/documents:extract",
                    form={"text": "Patient: Smoke\nRabies vaccine administered 2026-01-10. Next due 2027-01-10.\n"},
                )
                elapsed = time.monotonic() - started
                check(f"Claude extraction ({elapsed:.1f}s)", status == 200 and not extracted["result"].get("fatal_error"),
                      (status, extracted))
                status, _, answer = me.request("POST", f"/api/health/pets/{smoke_pet['pet_id']}/ask",
                                               {"question": "When is the rabies vaccine due?"})
                check("Claude Ask", status == 200 and answer.get("citations"), (status, answer))
                me.request("DELETE", f"/api/pets/{smoke_pet['pet_id']}?force=true")

    print(f"\n{len(check.failures)} failed" + (f": {check.failures}" if check.failures else ""))
    return len(check.failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--owner", action="store_true", help="also check the owner space (PAWPAL_SMOKE_OWNER_KEY)")
    parser.add_argument("--claude", action="store_true", help="with --owner: one real Claude extraction and Ask")
    args = parser.parse_args()
    return min(run(args.base_url, args.owner, args.claude), 100)


if __name__ == "__main__":
    sys.exit(main())
