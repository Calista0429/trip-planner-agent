"""Comic trip routes: a proxy to the separately deployed comic-trip-agent service.

The comic service (Java/Quarkus, Gemini, GCS, Firestore) turns travel photos into
album pictures (comic, watercolor, retro film or anime style) with a description, location and nearby points of interest. This
route forwards the upload and reshapes the answer, so the frontend:

- talks to one origin and never needs GCP credentials or the service's address;
- gets a flat, stable shape instead of the Java records;
- never sees the upstream's raw error text, only short error codes.
"""

from typing import Any, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from ...config import get_settings

router = APIRouter(prefix="/comic", tags=["Comic"])

UPSTREAM_UPLOAD_PATH = "/api/mission-control/upload"
MAX_FILES = 10
MAX_FILE_BYTES = 15 * 1024 * 1024
# The comic service refuses bodies over 100MB (quarkus.http.limits.max-body-size);
# stay below it with room for the multipart framing.
MAX_TOTAL_BYTES = 95 * 1024 * 1024
ALLOWED_MIME_PREFIX = "image/"
# Album styles the comic service knows (comictrip.AlbumStyle); checked here so a
# typo never reaches the paid image model.
STYLES = ("comic", "watercolor-journal", "retro-film", "anime")
DEFAULT_STYLE = "comic"
BAD_IMAGE_URL = {"file": "", "reason": "bad_image_url"}


def _error(status: int, code: str, failed: List[dict] | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": code}
    if failed is not None:
        body["failed"] = failed
    return JSONResponse(status_code=status, content=body)


def _picture(raw: dict) -> dict:
    image = raw.get("image") or {}
    details = raw.get("details") or {}
    return {
        "imageUrl": image.get("name") or "",
        "description": details.get("description") or "",
        "location": details.get("location") or "",
        "pointsOfInterest": raw.get("pointsOfInterest") or "",
    }


def _is_web_url(url: str) -> bool:
    # Only http(s) may reach an <img src>; anything else (javascript:, data:) is dropped.
    return urlparse(url).scheme in ("http", "https")


def _failed(raw: Any) -> List[dict]:
    if not isinstance(raw, list):
        return []
    return [
        {"file": str(item.get("file", "")), "reason": str(item.get("reason", "internal"))}
        for item in raw
        if isinstance(item, dict)
    ]


@router.post("/upload", summary="把旅行照片生成相册")
async def upload_photos(
    file: Optional[List[UploadFile]] = File(None),
    style: Optional[str] = Form(None),
):
    settings = get_settings()
    base_url = settings.comic_service_url.strip().rstrip("/")
    if not base_url:
        return _error(503, "comic_not_configured")

    files = file or []
    if not files:
        return _error(400, "no_files")
    if len(files) > MAX_FILES:
        return _error(400, "too_many_files")
    if any(not (f.content_type or "").startswith(ALLOWED_MIME_PREFIX) for f in files):
        return _error(400, "not_an_image")
    album_style = (style or "").strip().lower() or DEFAULT_STYLE
    if album_style not in STYLES:
        return _error(400, "unknown_style")

    parts = []
    total = 0
    for f in files:
        # Read one byte past the limit: enough to know it is too big without
        # holding an arbitrarily large upload in memory.
        content = await f.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            return _error(413, "file_too_large")
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            return _error(413, "total_too_large")
        parts.append(("file", (f.filename or "photo", content, f.content_type)))

    timeout = httpx.Timeout(settings.comic_service_timeout_seconds, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.post(
                base_url + UPSTREAM_UPLOAD_PATH, data={"style": album_style}, files=parts
            )
    except httpx.TimeoutException:
        logger.warning("Comic service timed out after {}s", settings.comic_service_timeout_seconds)
        return _error(504, "comic_timeout")
    except httpx.HTTPError as exc:
        logger.error("Comic service unreachable: {!r}", exc)
        return _error(502, "comic_unavailable")

    try:
        body = upstream.json()
    except ValueError:
        body = None

    if upstream.status_code == 200 and isinstance(body, dict):
        failed = _failed(body.get("failed"))
        pictures = []
        for raw in body.get("pictures") or []:
            if not isinstance(raw, dict):
                continue
            picture = _picture(raw)
            if _is_web_url(picture["imageUrl"]):
                pictures.append(picture)
            else:
                failed.append(dict(BAD_IMAGE_URL))
        if not pictures:
            return _error(502, "all_failed", failed)
        return {
            "tripId": body.get("tripId", ""),
            "title": body.get("title", ""),
            "style": body.get("style") or album_style,
            "pictures": pictures,
            "failed": failed,
        }

    # Every photo failed: pass on the per-photo reasons, which are client-safe codes.
    if upstream.status_code == 502 and isinstance(body, dict) and body.get("error") == "all_failed":
        return _error(502, "all_failed", _failed(body.get("failed")))

    if upstream.status_code == 413:
        return _error(413, "total_too_large")

    if upstream.status_code == 400 and isinstance(body, dict) and body.get("error") == "unknown_style":
        return _error(400, "unknown_style")

    # Anything else (e.g. a 500 whose body is the upstream's own message): log it, return a code.
    logger.error("Comic service failed with {}: {}", upstream.status_code, upstream.text[:500])
    return _error(502, "comic_failed")
