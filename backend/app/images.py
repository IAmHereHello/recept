"""Shared cover-image handling for recipes.

Both the URL importer and the manual "add image" picker land here: a remote
image is downloaded, an uploaded file is validated, and either way the bytes
are written to UPLOAD_DIR as "<uuid><ext>" and served by the /uploads static
mount — the same store as cook-session photos.
"""
import uuid
import logging
from pathlib import Path
from urllib.parse import urljoin

import aiofiles
import httpx

from app.config import UPLOAD_DIR

logger = logging.getLogger("app.images")

# Accepted content types, mapped to the extension the file is saved with.
# Anything else (SVG, an HTML error page, a PDF, ...) is rejected.
IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "image/heic": ".heic",
    "image/heif": ".heic",
}
_EXTENSIONS = set(IMAGE_CONTENT_TYPES.values()) | {".jpeg"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class ImageError(ValueError):
    """Raised by save_upload for a file that isn't an accepted image."""


async def _write(data: bytes, ext: str) -> str:
    filename = f"{uuid.uuid4()}{ext}"
    async with aiofiles.open(UPLOAD_DIR / filename, "wb") as f:
        await f.write(data)
    return f"/uploads/{filename}"


async def download_image(url: str, *, base_url: str | None = None) -> str | None:
    """Fetch a remote image into UPLOAD_DIR and return its "/uploads/..." path.

    Returns None on any failure (bad URL, non-image content, too large, network
    error) so callers can decide whether that's fatal (manual picker → 400) or
    merely means "no image" (importer → best-effort).
    """
    resolved = urljoin(base_url, url) if base_url else url
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(resolved, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            ext = IMAGE_CONTENT_TYPES.get(content_type)
            if ext is None:
                logger.info("Rejected image with content-type %r (%s)", content_type, resolved)
                return None
            data = resp.content
            if not data or len(data) > MAX_IMAGE_BYTES:
                logger.info("Rejected image of %d bytes (%s)", len(data or b""), resolved)
                return None
    except Exception as e:
        logger.warning("Could not download image %s: %s", resolved, e)
        return None
    return await _write(data, ext)


async def save_upload(raw: bytes, content_type: str | None, filename: str | None) -> str:
    """Persist an uploaded image file, returning its "/uploads/..." path.

    Raises ImageError if it isn't an accepted image type or is too large / empty.
    """
    ct = (content_type or "").split(";")[0].strip().lower()
    ext = IMAGE_CONTENT_TYPES.get(ct)
    if ext is None and filename:
        # Some browsers send application/octet-stream — trust the extension then.
        suffix = Path(filename).suffix.lower()
        if suffix in _EXTENSIONS:
            ext = ".jpg" if suffix == ".jpeg" else suffix
    if ext is None:
        raise ImageError("Alleen JPG, PNG, WebP, GIF, AVIF of HEIC afbeeldingen zijn toegestaan.")
    if not raw:
        raise ImageError("De afbeelding is leeg.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageError("De afbeelding is te groot (max 8 MB).")
    return await _write(raw, ext)
