"""Production static/SPA serving: one process serves both the JSON API and the
built frontend (MIGRATION_PLAN.md §6).

`frontend/dist` is a build artifact that exists in neither a fresh checkout nor
CI, so every test here builds a fake dist in tmp_path (index.html + a
content-hashed asset + a root file) and hands it to `create_app` -- no npm
build required, and no test's outcome depends on whether the real
frontend/dist happens to be present on this machine.

Storages are overridden per tmp_path the same way as tests/test_api_scheduler.py
so the API requests used here to prove the catch-all shadows nothing never
touch data/pawpal.db.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from api.deps import get_health_storage, get_scheduler_storage
from api.main import DIST_DIR, _resolve_within, app as default_app, create_app
from api.storage import SchedulerStorage
from pawpal_ai.storage import init_db as init_health_db

# The marker proves a response really is index.html and not, say, a JSON error
# page that happens to be 200.
INDEX_MARKER = "data-pawpal-index"
INDEX_HTML = (
    f"<!doctype html><html {INDEX_MARKER}><head><title>PawPal+</title>"
    '<script type="module" src="/assets/app-abc123.js"></script></head><body></body></html>'
)
ASSET_JS = "export const hello = 'pawpal';\n"
SECRET = "TOP-SECRET-NEVER-OVER-HTTP"


@pytest.fixture
def dist_dir(tmp_path) -> Path:
    """Stand-in for `npm run build` output: a content-hashed bundle under
    assets/, plus a root file of the kind Vite copies straight from public/."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    # newline="\n": without it Windows rewrites the trailing \n as \r\n on
    # disk, and the byte-exact check on the served body below would fail
    # against the fixture rather than against anything the app did.
    (dist / "assets" / "app-abc123.js").write_text(ASSET_JS, encoding="utf-8", newline="\n")
    # The rest of a real bundle's extension spread. .mjs and .woff2 are exactly
    # the two the Windows registry gets wrong (text/plain, and no type at all),
    # so serving them is what proves the mimetypes pinning in api/main.py is
    # actually doing something.
    (dist / "assets" / "app-abc123.css").write_text(":root{color:red}", encoding="utf-8")
    (dist / "assets" / "worker-abc123.mjs").write_text("export default 1;", encoding="utf-8")
    (dist / "assets" / "font-abc123.woff2").write_bytes(b"wOF2\x00not-a-real-font")
    (dist / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    return dist


@pytest.fixture
def dist_without_assets(tmp_path) -> Path:
    """A build that emitted no assets/ directory at all.

    Vite writes one for this app, but a build that inlines everything -- or a
    deploy that copied index.html and not the rest -- does not, and that shape
    used to fail differently from every other missing file.
    """
    dist = tmp_path / "dist-no-assets"
    dist.mkdir()
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    return dist


@pytest.fixture
def secret_file(tmp_path) -> Path:
    """A file beside dist/ but never inside it -- what a traversal would leak."""
    secret = tmp_path / "secret.txt"
    secret.write_text(SECRET, encoding="utf-8")
    return secret


@pytest.fixture
def storages(tmp_path):
    db_path = tmp_path / "test.db"
    scheduler_storage = SchedulerStorage(db_path)
    health_storage = init_health_db(db_path)
    yield scheduler_storage, health_storage
    scheduler_storage.close()
    health_storage.close()


def _client_for(dist: Path, storages) -> TestClient:
    """A full app (all five routers) pointed at `dist`.

    Each test gets its own app instance, so -- unlike the shared module-level
    app the other API tests use -- the overrides need no teardown and a mounted
    dist cannot leak into the next test.
    """
    scheduler_storage, health_storage = storages
    app = create_app(dist_dir=dist)
    app.dependency_overrides[get_scheduler_storage] = lambda: scheduler_storage
    app.dependency_overrides[get_health_storage] = lambda: health_storage
    return TestClient(app)


@pytest.fixture
def client(dist_dir, storages) -> TestClient:
    return _client_for(dist_dir, storages)


@pytest.fixture
def api_only_client(tmp_path, storages) -> TestClient:
    """The fresh-checkout / CI case: the build was never run."""
    return _client_for(tmp_path / "never-built", storages)


class TestServesTheBuild:
    def test_root_serves_index_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert INDEX_MARKER in resp.text

    def test_hashed_asset_served_as_javascript(self, client):
        resp = client.get("/assets/app-abc123.js")
        assert resp.status_code == 200
        # Either spelling is valid and machine-dependent; what matters is that
        # it is not text/plain, which browsers refuse for a module script.
        assert "javascript" in resp.headers["content-type"]
        assert resp.text == ASSET_JS

    def test_root_level_public_file_served_with_its_own_type(self, client):
        resp = client.get("/favicon.svg")
        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers["content-type"]

    @pytest.mark.parametrize(
        ("path", "expected_type"),
        [
            ("/assets/app-abc123.css", "text/css"),
            ("/assets/worker-abc123.mjs", "javascript"),
            ("/assets/font-abc123.woff2", "font/woff2"),
        ],
    )
    def test_every_bundle_extension_gets_a_real_content_type(self, client, path, expected_type):
        # Unpinned, .mjs arrives as text/plain and .woff2 with no type at all on
        # Windows; the browser then refuses the module and ignores the font.
        resp = client.get(path)
        assert resp.status_code == 200
        assert expected_type in resp.headers["content-type"]

    def test_missing_hashed_asset_is_a_404_not_index_html(self, client):
        # A stale index.html asking for a deleted bundle must fail loudly;
        # answering a .js request with HTML produces a syntax error instead.
        resp = client.get("/assets/app-deadbeef.js")
        assert resp.status_code == 404
        assert INDEX_MARKER not in resp.text

    def test_dist_without_assets_dir_404s_rather_than_500ing(self, dist_without_assets, storages):
        """A dist with no assets/ sibling must 404 like any other missing file.

        `check_dir=False` on the mount was not enough on its own: it defers
        StaticFiles' existence check to request time rather than removing it, so
        this shape answered every /assets/* request with a 500 (RuntimeError:
        StaticFiles directory ... does not exist). The mount is now conditional,
        and /assets stays reserved from the SPA fallback so the alternative
        failure -- answering a .js request with index.html at 200 -- cannot
        happen either.
        """
        client = _client_for(dist_without_assets, storages)

        resp = client.get("/assets/app-abc123.js")
        assert resp.status_code == 404
        assert "application/json" in resp.headers["content-type"]
        assert INDEX_MARKER not in resp.text

        # The rest of the build is unaffected: pages still resolve.
        assert INDEX_MARKER in client.get("/").text
        assert INDEX_MARKER in client.get("/app/health").text


class TestCaching:
    def test_hashed_assets_are_immutable(self, client):
        cache_control = client.get("/assets/app-abc123.js").headers["cache-control"]
        assert "immutable" in cache_control
        assert "max-age=31536000" in cache_control

    def test_index_is_never_cached(self, client):
        # A cached index.html pins the browser to asset hashes the next deploy
        # deletes -- the classic blank page after a release.
        assert "no-cache" in client.get("/").headers["cache-control"]

    def test_index_requested_by_name_is_also_not_cached(self, client):
        assert "no-cache" in client.get("/index.html").headers["cache-control"]

    def test_unhashed_root_file_is_not_immutable(self, client):
        # favicon.svg keeps its name across deploys, so it must be revalidated.
        assert "immutable" not in client.get("/favicon.svg").headers["cache-control"]


class TestClientSideRouting:
    def test_hard_refresh_on_spa_route_returns_index(self, client):
        resp = client.get("/app/health")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert INDEX_MARKER in resp.text

    def test_deep_unknown_path_returns_index(self, client):
        # React Router owns the 404 for paths it does not recognise.
        resp = client.get("/app/health/records/12345/edit")
        assert resp.status_code == 200
        assert INDEX_MARKER in resp.text


class TestApiIsNeverShadowed:
    def test_healthz_still_works(self, client):
        resp = client.get("/api/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_real_router_route_still_works(self, client):
        # The catch-all is registered after the routers; if that order ever
        # flips, this turns into index.html at 200.
        resp = client.get("/api/owner")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Pet Owner"

    @pytest.mark.parametrize("path", ["/api/nope", "/api/pets/unknown-id/typo", "/api"])
    def test_unknown_api_path_is_a_json_404(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 404
        # The content type is the point: HTML here means fetch() fails on
        # JSON.parse instead of surfacing the 404.
        assert "application/json" in resp.headers["content-type"]
        assert INDEX_MARKER not in resp.text
        assert "detail" in resp.json()

    def test_openapi_docs_still_reachable(self, client):
        # FastAPI registers /docs and /openapi.json before the catch-all runs.
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200


class TestMethodSemantics:
    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    @pytest.mark.parametrize("path", ["/app/health", "/api/nope"])
    def test_non_get_never_gets_index_html(self, client, method, path):
        resp = client.request(method, path)
        assert resp.status_code == 405
        assert INDEX_MARKER not in resp.text

    def test_wrong_method_on_a_real_endpoint_still_says_405(self, client):
        # The catch-all claims only GET/HEAD, which is what keeps this an
        # accurate 405 instead of a misleading "no such endpoint" 404.
        resp = client.request("DELETE", "/api/owner")
        assert resp.status_code == 405

    def test_head_on_a_spa_route_is_allowed(self, client):
        assert client.head("/app/health").status_code == 200


class TestPathTraversalRefused:
    # Only the percent-encoded forms are meaningful: a literal "/../secret.txt"
    # is collapsed to "/secret.txt" by the client before it is ever sent, so a
    # test written that way would pass without exercising the guard at all.
    # "%2e%2e" and "..%2f" survive decoding and arrive as a real "../".
    @pytest.mark.parametrize(
        "path",
        [
            "/%2e%2e%2fsecret.txt",
            "/..%2fsecret.txt",
            "/%2e%2e%2f%2e%2e%2fsecret.txt",
            "/assets/%2e%2e%2f%2e%2e%2fsecret.txt",
        ],
    )
    def test_encoded_traversal_is_refused(self, client, secret_file, path):
        resp = client.get(path)
        assert resp.status_code == 404
        assert SECRET not in resp.text

    def test_resolver_rejects_escapes_and_accepts_real_files(self, dist_dir, secret_file):
        # The helper is tested directly as well: it is the security boundary,
        # and here it can be checked against inputs no HTTP client will send.
        dist_root = dist_dir.resolve()
        assert _resolve_within(dist_root, "../secret.txt") is None
        assert _resolve_within(dist_root, str(secret_file)) is None
        assert _resolve_within(dist_root, "assets/app-abc123.js") == dist_root / "assets" / "app-abc123.js"


class TestApiOnlyMode:
    def test_api_works_with_no_build_present(self, api_only_client):
        assert api_only_client.get("/api/healthz").json() == {"status": "ok"}
        assert api_only_client.get("/api/owner").status_code == 200

    def test_page_request_explains_the_missing_build(self, api_only_client):
        resp = api_only_client.get("/")
        assert resp.status_code == 503
        assert "application/json" in resp.headers["content-type"]
        assert "npm run build" in resp.json()["detail"]

    def test_spa_route_gets_the_same_hint(self, api_only_client):
        assert api_only_client.get("/app/health").status_code == 503

    def test_unknown_api_path_is_still_a_404(self, api_only_client):
        # A bad endpoint must not be misreported as "the frontend isn't built".
        resp = api_only_client.get("/api/nope")
        assert resp.status_code == 404

    def test_module_level_app_imports_and_serves_the_api(self):
        # What the other 208 tests rely on: importing api.main must work with or
        # without a build, so the dist mount can never be an import-time error.
        assert TestClient(default_app).get("/api/healthz").status_code == 200


def test_dist_dir_is_absolute_and_independent_of_cwd():
    """Resolved from api/main.py's own location, so `uvicorn api.main:app`
    started from a systemd unit or a Docker WORKDIR still finds the build."""
    assert DIST_DIR.is_absolute()
    assert DIST_DIR.parts[-2:] == ("frontend", "dist")
    assert DIST_DIR == Path(api_main.__file__).resolve().parent.parent / "frontend" / "dist"
