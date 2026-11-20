"""Route-level tests for the /comic/upload proxy to the comic-trip-agent service.

The upstream service is replaced by an httpx MockTransport, so no network call is
made: each test decides what the comic service answers (or how it fails) and
checks what the frontend gets back.
"""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import comic as comic_route
from app.config import settings

UPSTREAM = "http://comic.test"

UPSTREAM_OK = {
    "tripId": "abc",
    "title": "THE GALATA CAPER",
    "style": "anime",
    "pictures": [{
        "tripId": "abc",
        "image": {
            "name": "https://storage.googleapis.com/b/comic_trip_app/comic_trip_user/abc/x.png/0",
            "imageBytes": None,
            "mimeType": "image/png",
        },
        "details": {"description": "A tower", "location": "Galata Tower, Istanbul"},
        "pointsOfInterest": "- **Galata Bridge**",
    }],
    "failed": [{"file": "b.png", "reason": "no_image"}],
}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(comic_route.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def comic_settings():
    original = (settings.comic_service_url, settings.comic_service_timeout_seconds)
    settings.comic_service_url = UPSTREAM + "/"
    settings.comic_service_timeout_seconds = 330.0
    yield
    settings.comic_service_url, settings.comic_service_timeout_seconds = original


@pytest.fixture
def upstream(monkeypatch):
    """Routes the proxy's outgoing requests to `upstream.handler`; records them."""

    class Upstream:
        handler = staticmethod(lambda request: httpx.Response(200, json=UPSTREAM_OK))
        requests: list = []
        timeouts: list = []

    real_client = httpx.AsyncClient

    def fake_client(**kwargs):
        Upstream.timeouts.append(kwargs.get("timeout"))

        def handle(request):
            Upstream.requests.append(request)
            return Upstream.handler(request)

        return real_client(transport=httpx.MockTransport(handle), **kwargs)

    Upstream.requests = []
    Upstream.timeouts = []
    monkeypatch.setattr(comic_route.httpx, "AsyncClient", fake_client)
    return Upstream


def upload(client, *files, style=None):
    files = files or (("a.png", b"\x89PNG-a", "image/png"),)
    data = {"style": style} if style is not None else None
    return client.post("/comic/upload", files=[("file", f) for f in files], data=data)


def picture(url):
    return {
        "image": {"name": url, "mimeType": "image/png"},
        "details": {"description": "d", "location": "l"},
        "pointsOfInterest": "",
    }


def test_success_is_reshaped_for_the_frontend(client, upstream):
    resp = upload(client)

    assert resp.status_code == 200
    assert resp.json() == {
        "tripId": "abc",
        "title": "THE GALATA CAPER",
        "style": "anime",
        "pictures": [{
            "imageUrl": "https://storage.googleapis.com/b/comic_trip_app/comic_trip_user/abc/x.png/0",
            "description": "A tower",
            "location": "Galata Tower, Istanbul",
            "pointsOfInterest": "- **Galata Bridge**",
        }],
        "failed": [{"file": "b.png", "reason": "no_image"}],
    }


def test_every_photo_is_forwarded_as_a_file_part(client, upstream):
    upload(client, ("a.png", b"AAA", "image/png"), ("b.jpg", b"BBB", "image/jpeg"))

    [request] = upstream.requests
    assert str(request.url) == UPSTREAM + "/api/mission-control/upload"  # trailing slash trimmed
    body = request.read()
    assert body.count(b'name="file"') == 2
    assert b'filename="a.png"' in body and b"AAA" in body
    assert b'filename="b.jpg"' in body and b"BBB" in body
    assert b"Content-Type: image/jpeg" in body


def test_upstream_timeout_is_longer_than_the_comic_service_allows(client, upstream):
    upload(client)

    [timeout] = upstream.timeouts
    # The comic service may take up to ~300s; the proxy must not give up first.
    assert timeout.read == 330.0
    assert timeout.connect == 10.0


def test_all_photos_failed_passes_on_the_per_photo_reasons(client, upstream):
    upstream.handler = lambda request: httpx.Response(502, json={
        "error": "all_failed", "failed": [{"file": "a.png", "reason": "rate_limited"}]})

    resp = upload(client)

    assert resp.status_code == 502
    assert resp.json() == {"error": "all_failed", "failed": [{"file": "a.png", "reason": "rate_limited"}]}


def test_upstream_error_text_is_not_passed_on(client, upstream):
    upstream.handler = lambda request: httpx.Response(500, text="Failed to save trip to Firestore: secret-detail")

    resp = upload(client)

    assert resp.status_code == 502
    assert resp.json() == {"error": "comic_failed"}
    assert "secret-detail" not in resp.text


def test_upstream_timeout_returns_504(client, upstream):
    def time_out(request):
        raise httpx.ReadTimeout("slow", request=request)

    upstream.handler = time_out

    resp = upload(client)

    assert resp.status_code == 504
    assert resp.json() == {"error": "comic_timeout"}


def test_upstream_unreachable_returns_502(client, upstream):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    upstream.handler = refuse

    resp = upload(client)

    assert resp.status_code == 502
    assert resp.json() == {"error": "comic_unavailable"}


def test_not_configured_returns_503_without_calling_upstream(client, upstream):
    settings.comic_service_url = ""

    resp = upload(client)

    assert resp.status_code == 503
    assert resp.json() == {"error": "comic_not_configured"}
    assert upstream.requests == []


def test_non_image_is_rejected_without_calling_upstream(client, upstream):
    resp = upload(client, ("notes.txt", b"hello", "text/plain"))

    assert resp.status_code == 400
    assert resp.json() == {"error": "not_an_image"}
    assert upstream.requests == []


def test_too_many_files_are_rejected_without_calling_upstream(client, upstream):
    files = [(f"p{i}.png", b"x", "image/png") for i in range(comic_route.MAX_FILES + 1)]

    resp = upload(client, *files)

    assert resp.status_code == 400
    assert resp.json() == {"error": "too_many_files"}
    assert upstream.requests == []


def test_no_files_is_rejected(client, upstream):
    resp = client.post("/comic/upload")

    assert resp.status_code == 400
    assert resp.json() == {"error": "no_files"}
    assert upstream.requests == []


def test_style_is_forwarded_and_defaults_to_comic(client, upstream):
    upload(client)
    upload(client, style=" Anime ")

    first, second = (r.read() for r in upstream.requests)
    assert b'name="style"\r\n\r\ncomic\r\n' in first
    assert b'name="style"\r\n\r\nanime\r\n' in second


def test_unknown_style_is_rejected_without_calling_upstream(client, upstream):
    resp = upload(client, style="oil")

    assert resp.status_code == 400
    assert resp.json() == {"error": "unknown_style"}
    assert upstream.requests == []


def test_oversized_file_is_rejected_without_calling_upstream(client, upstream):
    big = ("big.png", b"x" * (comic_route.MAX_FILE_BYTES + 1), "image/png")

    resp = upload(client, ("a.png", b"ok", "image/png"), big)

    assert resp.status_code == 413
    assert resp.json() == {"error": "file_too_large"}
    assert upstream.requests == []


def test_non_http_image_urls_become_failures(client, upstream):
    good = "https://storage.googleapis.com/b/x.png/0"
    upstream.handler = lambda request: httpx.Response(200, json={
        "tripId": "t1", "title": "T", "style": "comic",
        "pictures": [picture("javascript:alert(1)"), picture(good)], "failed": []})

    resp = upload(client)

    assert resp.status_code == 200
    body = resp.json()
    assert [p["imageUrl"] for p in body["pictures"]] == [good]
    assert body["failed"] == [{"file": "", "reason": "bad_image_url"}]


def test_all_image_urls_bad_is_all_failed(client, upstream):
    upstream.handler = lambda request: httpx.Response(200, json={
        "tripId": "t1", "title": "T", "style": "comic",
        "pictures": [picture("data:image/png;base64,AAAA")], "failed": []})

    resp = upload(client)

    assert resp.status_code == 502
    assert resp.json() == {"error": "all_failed", "failed": [{"file": "", "reason": "bad_image_url"}]}


def test_upstream_unknown_style_maps_to_400(client, upstream):
    upstream.handler = lambda request: httpx.Response(400, json={
        "error": "unknown_style", "styles": ["comic"]})

    resp = upload(client)

    assert resp.status_code == 400
    assert resp.json() == {"error": "unknown_style"}


def test_router_is_mounted_under_api():
    from app.api.main import app

    assert "/api/comic/upload" in {getattr(route, "path", "") for route in app.routes}


def test_total_size_cap_is_below_the_comic_service_body_limit():
    # comic-trip-agent: quarkus.http.limits.max-body-size=100M; leave room for multipart overhead.
    assert comic_route.MAX_TOTAL_BYTES == 95 * 1024 * 1024
    assert comic_route.MAX_TOTAL_BYTES < 100 * 1024 * 1024


def test_too_large_in_total_is_rejected_without_calling_upstream(client, upstream, monkeypatch):
    monkeypatch.setattr(comic_route, "MAX_TOTAL_BYTES", 10)

    resp = upload(client, ("a.png", b"123456", "image/png"), ("b.png", b"123456", "image/png"))

    assert resp.status_code == 413
    assert resp.json() == {"error": "total_too_large"}
    assert upstream.requests == []


def test_upstream_413_is_reported_as_too_large(client, upstream):
    upstream.handler = lambda request: httpx.Response(413, text="Request Entity Too Large")

    resp = upload(client)

    assert resp.status_code == 413
    assert resp.json() == {"error": "total_too_large"}
