import io
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.images as images_module
from tests.conftest import make_recipe


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    """An isolated UPLOAD_DIR (a subdir, so the conftest test.db doesn't count)."""
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setattr(images_module, "UPLOAD_DIR", d)
    return d


# --- POST /recipes/image (file upload) --------------------------------------

def test_upload_recipe_image_stores_file_and_returns_path(client, uploads):
    resp = client.post(
        "/recipes/image",
        files={"file": ("dish.png", io.BytesIO(b"fake-png-bytes"), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    image_path = resp.json()["image_path"]
    assert image_path.startswith("/uploads/") and image_path.endswith(".png")
    assert (uploads / Path(image_path).name).read_bytes() == b"fake-png-bytes"


def test_upload_recipe_image_rejects_non_image(client, uploads):
    resp = client.post(
        "/recipes/image",
        files={"file": ("notes.txt", io.BytesIO(b"just text"), "text/plain")},
    )
    assert resp.status_code == 400
    assert "afbeelding" in resp.json()["detail"].lower()
    assert list(uploads.iterdir()) == []


def test_upload_recipe_image_falls_back_to_extension_for_octet_stream(client, uploads):
    resp = client.post(
        "/recipes/image",
        files={"file": ("photo.jpeg", io.BytesIO(b"bytes"), "application/octet-stream")},
    )
    assert resp.status_code == 200
    assert resp.json()["image_path"].endswith(".jpg")


def test_upload_recipe_image_rejects_oversize(client, uploads, monkeypatch):
    monkeypatch.setattr(images_module, "MAX_IMAGE_BYTES", 8)
    resp = client.post(
        "/recipes/image",
        files={"file": ("big.jpg", io.BytesIO(b"x" * 99), "image/jpeg")},
    )
    assert resp.status_code == 400
    assert "te groot" in resp.json()["detail"]


def test_uploaded_recipe_image_persists_through_create(client, uploads):
    image_path = client.post(
        "/recipes/image",
        files={"file": ("dish.webp", io.BytesIO(b"webp"), "image/webp")},
    ).json()["image_path"]

    recipe = make_recipe(client, image_path=image_path)
    assert recipe["image_path"] == image_path
    assert recipe["cover_photo"] == image_path


# --- POST /recipes/image-from-url ------------------------------------------

class _FakeResponse:
    def __init__(self, content=b"", headers=None):
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self):
        pass


class _FakeClient:
    content = b"jpeg-bytes"
    content_type = "image/jpeg"
    error = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        if self.error:
            raise self.error
        return _FakeResponse(self.content, {"content-type": self.content_type})


@pytest.fixture()
def fake_image_http(monkeypatch, uploads):
    monkeypatch.setattr(images_module, "httpx", SimpleNamespace(AsyncClient=_FakeClient))
    yield
    _FakeClient.content = b"jpeg-bytes"
    _FakeClient.content_type = "image/jpeg"
    _FakeClient.error = None


def test_recipe_image_from_url_downloads_and_returns_path(client, fake_image_http, uploads):
    resp = client.post("/recipes/image-from-url", json={"url": "https://img.example/a.jpg"})
    assert resp.status_code == 200, resp.text
    image_path = resp.json()["image_path"]
    assert image_path.endswith(".jpg")
    assert (uploads / Path(image_path).name).read_bytes() == b"jpeg-bytes"


def test_recipe_image_from_url_400s_on_non_image(client, fake_image_http):
    _FakeClient.content_type = "text/html"
    resp = client.post("/recipes/image-from-url", json={"url": "https://img.example/nope"})
    assert resp.status_code == 400
    assert "URL" in resp.json()["detail"]


def test_recipe_image_from_url_400s_on_network_error(client, fake_image_http):
    _FakeClient.error = RuntimeError("dns failure")
    resp = client.post("/recipes/image-from-url", json={"url": "https://img.example/a.jpg"})
    assert resp.status_code == 400
