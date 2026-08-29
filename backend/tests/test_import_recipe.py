from pathlib import Path
from types import SimpleNamespace

import pytest

import app.ai as ai_module
import app.images as images_module
import app.routers.import_recipe as import_recipe_module


class FakeResponse:
    def __init__(self, text="", content=b"", headers=None):
        self.text = text
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self):
        pass


class FakeAsyncClient:
    """Stands in for httpx.AsyncClient so tests never hit the network.

    Serves `fetch_text` for the page GET; a request to `image_url` (if set)
    gets `image_content` with an image content-type instead, so the cover-image
    download path can be exercised offline.
    """

    fetch_text = "<html>fake recipe page</html>"
    fetch_error = None
    image_url = None
    image_content = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
    image_content_type = "image/jpeg"
    image_error = None
    requested_urls: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None):
        FakeAsyncClient.requested_urls.append(url)
        if self.image_url is not None and url == self.image_url:
            if self.image_error:
                raise self.image_error
            return FakeResponse(
                content=self.image_content,
                headers={"content-type": self.image_content_type},
            )
        if self.fetch_error:
            raise self.fetch_error
        return FakeResponse(text=self.fetch_text)


class FakeAnthropicClient:
    """Stands in for anthropic.AsyncAnthropic so tests never call the real API."""

    reply_text = '{"name": "Test Recipe"}'
    stop_reason = "end_turn"
    last_user_content = None

    def __init__(self, *args, **kwargs):
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        FakeAnthropicClient.last_user_content = kwargs["messages"][0]["content"]
        return SimpleNamespace(
            content=[SimpleNamespace(text=self.reply_text)],
            stop_reason=self.stop_reason,
        )


def _patch(monkeypatch, *, reply_text=None, stop_reason="end_turn", fetch_text=None):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # The page fetch lives in import_recipe; the cover-image download in app.images.
    monkeypatch.setattr(import_recipe_module, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))
    monkeypatch.setattr(images_module, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))
    if reply_text is not None:
        FakeAnthropicClient.reply_text = reply_text
    if fetch_text is not None:
        FakeAsyncClient.fetch_text = fetch_text
    FakeAnthropicClient.stop_reason = stop_reason
    monkeypatch.setattr(ai_module.anthropic, "AsyncAnthropic", FakeAnthropicClient)


RECIPE_LD = """{
  "@context": "https://schema.org", "@type": "Recipe",
  "name": "Griekse ovenschotel", "totalTime": "PT40M", "recipeYield": "4",
  "recipeIngredient": ["1 middelgrote ui", "250 g winterpeen"],
  "recipeInstructions": [
    {"@type": "HowToStep", "position": 1, "text": "Verwarm de oven voor."}
  ]
}"""

PAGE_WITH_LD = (
    '<html><head><meta property="og:title" content="Griekse ovenschotel">'
    + ("<span>filler</span>" * 5000)  # push the JSON-LD past any byte cap
    + '<script type="application/ld+json">' + RECIPE_LD + "</script>"
    + "</head><body>spa shell</body></html>"
)


@pytest.fixture(autouse=True)
def _reset_fakes():
    """Class-attr fakes leak state between tests — restore defaults each time."""
    yield
    FakeAsyncClient.fetch_text = "<html>fake recipe page</html>"
    FakeAsyncClient.fetch_error = None
    FakeAsyncClient.image_url = None
    FakeAsyncClient.image_content = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
    FakeAsyncClient.image_content_type = "image/jpeg"
    FakeAsyncClient.image_error = None
    FakeAsyncClient.requested_urls = []
    FakeAnthropicClient.reply_text = '{"name": "Test Recipe"}'
    FakeAnthropicClient.stop_reason = "end_turn"
    FakeAnthropicClient.last_user_content = None


def test_import_fails_without_api_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 500
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_import_fails_on_unreachable_url(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    FakeAsyncClient.fetch_error = RuntimeError("connection refused")
    monkeypatch.setattr(import_recipe_module, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))
    try:
        resp = client.post("/import/", json={"url": "https://example.com/recipe"})
        assert resp.status_code == 400
    finally:
        FakeAsyncClient.fetch_error = None


def test_import_fails_on_invalid_ai_json(client, monkeypatch):
    _patch(monkeypatch, reply_text="not valid json")
    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 502
    assert "geen recept" in resp.json()["detail"]


def test_import_fails_when_ai_truncated_at_max_tokens(client, monkeypatch):
    _patch(monkeypatch, reply_text='{"name": "Half a rec', stop_reason="max_tokens")
    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 502
    assert "te lang" in resp.json()["detail"]


def test_import_fails_on_empty_ai_response(client, monkeypatch):
    _patch(monkeypatch, reply_text="   ")
    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 502
    assert "leeg antwoord" in resp.json()["detail"]


def test_import_succeeds_with_valid_ai_json(client, monkeypatch):
    _patch(monkeypatch, reply_text='{"name": "Imported Dish", "ingredients": [], "steps": []}')
    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Imported Dish"


def test_import_tolerates_markdown_fenced_json(client, monkeypatch):
    _patch(monkeypatch, reply_text='```json\n{"name": "Fenced Dish", "steps": []}\n```')
    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Fenced Dish"


def test_import_tolerates_prose_around_json(client, monkeypatch):
    _patch(monkeypatch, reply_text='Here is the recipe:\n{"name": "Prose Dish"}\nHope that helps!')
    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Prose Dish"


def test_import_feeds_jsonld_recipe_to_ai_when_present(client, monkeypatch):
    _patch(
        monkeypatch,
        fetch_text=PAGE_WITH_LD,
        reply_text='{"name": "Griekse ovenschotel", "cook_time": 40, "steps": []}',
    )
    resp = client.post("/import/", json={"url": "https://www.ah.nl/allerhande/recept/R-1"})
    assert resp.status_code == 200
    assert resp.json()["cook_time"] == 40
    sent = FakeAnthropicClient.last_user_content
    assert "JSON-LD" in sent
    assert "recipeInstructions" in sent  # the deep block, not just <head> meta
    assert "250 g winterpeen" in sent


def test_import_passes_through_prep_time_and_step_wait_times(client, monkeypatch):
    _patch(
        monkeypatch,
        reply_text=(
            '{"name": "Ovenschotel", "cook_time": 75, "prep_time": 20, '
            '"steps": [{"sort_order": 1, "description": "Snijd de groenten", "wait_time_minutes": null}, '
            '{"sort_order": 2, "description": "Bak 45 minuten", "wait_time_minutes": 45}]}'
        ),
    )
    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["prep_time"] == 20
    assert body["steps"][1]["wait_time_minutes"] == 45
    # The system prompt tells the model what these fields mean.
    assert "wait_time_minutes" in import_recipe_module.SYSTEM_PROMPT
    assert "totalTime" in import_recipe_module.SYSTEM_PROMPT


def test_import_falls_back_to_html_without_jsonld(client, monkeypatch):
    _patch(
        monkeypatch,
        fetch_text="<html><body><h1>Soep</h1><p>kook alles</p></body></html>",
        reply_text='{"name": "Soep", "steps": []}',
    )
    resp = client.post("/import/", json={"url": "https://blog.example/soep"})
    assert resp.status_code == 200
    assert "this page HTML" in FakeAnthropicClient.last_user_content


def test_find_recipe_jsonld_handles_graph_and_list_wrappers():
    find = import_recipe_module._find_recipe_jsonld
    graph = '<script type="application/ld+json">{"@graph":[{"@type":"WebPage"},{"@type":"Recipe","name":"G"}]}</script>'
    assert find(graph)["name"] == "G"
    listed = '<script type="application/ld+json">[{"@type":"Organization"},{"@type":["Thing","Recipe"],"name":"L"}]</script>'
    assert find(listed)["name"] == "L"
    assert find("<html>no structured data</html>") is None


# --- cover image extraction / download ---------------------------------------

def test_first_image_ref_handles_string_object_and_list():
    ref = import_recipe_module._first_image_ref
    assert ref("https://img.example/a.jpg") == "https://img.example/a.jpg"
    assert ref({"@type": "ImageObject", "url": "https://img.example/b.jpg"}) == "https://img.example/b.jpg"
    assert ref(["https://img.example/c.jpg", "https://img.example/d.jpg"]) == "https://img.example/c.jpg"
    assert ref([{"contentUrl": "https://img.example/e.jpg"}]) == "https://img.example/e.jpg"
    assert ref(None) is None
    assert ref([]) is None


def test_extract_image_url_prefers_jsonld_then_og_image():
    extract = import_recipe_module._extract_image_url
    assert extract({"image": "https://img.example/ld.jpg"}, "<html></html>") == "https://img.example/ld.jpg"
    og = '<html><head><meta property="og:image" content="https://img.example/og.jpg"></head></html>'
    assert extract(None, og) == "https://img.example/og.jpg"
    assert extract({"name": "no image key"}, og) == "https://img.example/og.jpg"
    assert extract(None, "<html>nothing</html>") is None


def _ld_with_image(image_json: str) -> str:
    body = RECIPE_LD.replace('"name": "Griekse ovenschotel",', f'"name": "Griekse ovenschotel", "image": {image_json},')
    return (
        '<html><head>'
        + ("<span>filler</span>" * 5000)
        + '<script type="application/ld+json">' + body + "</script>"
        + "</head><body>spa shell</body></html>"
    )


def test_import_downloads_cover_image_from_jsonld(client, monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(images_module, "UPLOAD_DIR", upload_dir)
    _patch(
        monkeypatch,
        fetch_text=_ld_with_image('"https://img.example/dish.jpg"'),
        reply_text='{"name": "Griekse ovenschotel", "steps": []}',
    )
    FakeAsyncClient.image_url = "https://img.example/dish.jpg"

    resp = client.post("/import/", json={"url": "https://www.ah.nl/allerhande/recept/R-1"})
    assert resp.status_code == 200
    image_path = resp.json()["image_path"]
    assert image_path.startswith("/uploads/") and image_path.endswith(".jpg")
    saved = upload_dir / Path(image_path).name
    assert saved.read_bytes() == FakeAsyncClient.image_content


def test_import_uses_og_image_when_jsonld_has_none(client, monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(images_module, "UPLOAD_DIR", upload_dir)
    page = (
        '<html><head><meta property="og:image" content="https://img.example/og.png">'
        '</head><body><h1>Soep</h1></body></html>'
    )
    _patch(monkeypatch, fetch_text=page, reply_text='{"name": "Soep", "steps": []}')
    FakeAsyncClient.image_url = "https://img.example/og.png"
    FakeAsyncClient.image_content_type = "image/png"

    resp = client.post("/import/", json={"url": "https://blog.example/soep"})
    assert resp.status_code == 200
    assert resp.json()["image_path"].endswith(".png")


def test_import_resolves_relative_image_url(client, monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(images_module, "UPLOAD_DIR", upload_dir)
    _patch(
        monkeypatch,
        fetch_text=_ld_with_image('"/media/dish.jpg"'),
        reply_text='{"name": "Griekse ovenschotel", "steps": []}',
    )
    FakeAsyncClient.image_url = "https://site.test/media/dish.jpg"

    resp = client.post("/import/", json={"url": "https://site.test/recepten/ovenschotel"})
    assert resp.status_code == 200
    assert resp.json()["image_path"] is not None
    assert "https://site.test/media/dish.jpg" in FakeAsyncClient.requested_urls


def test_import_skips_non_image_content_type(client, monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(images_module, "UPLOAD_DIR", upload_dir)
    _patch(
        monkeypatch,
        fetch_text=_ld_with_image('"https://img.example/dish.svg"'),
        reply_text='{"name": "Griekse ovenschotel", "steps": []}',
    )
    FakeAsyncClient.image_url = "https://img.example/dish.svg"
    FakeAsyncClient.image_content_type = "image/svg+xml"

    resp = client.post("/import/", json={"url": "https://www.ah.nl/allerhande/recept/R-1"})
    assert resp.status_code == 200
    assert resp.json()["image_path"] is None
    assert list(upload_dir.iterdir()) == []


def test_import_survives_cover_image_download_failure(client, monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(images_module, "UPLOAD_DIR", upload_dir)
    _patch(
        monkeypatch,
        fetch_text=_ld_with_image('"https://img.example/dish.jpg"'),
        reply_text='{"name": "Griekse ovenschotel", "steps": []}',
    )
    FakeAsyncClient.image_url = "https://img.example/dish.jpg"
    FakeAsyncClient.image_error = RuntimeError("connection reset")

    resp = client.post("/import/", json={"url": "https://www.ah.nl/allerhande/recept/R-1"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Griekse ovenschotel"
    assert resp.json()["image_path"] is None


def test_import_skips_oversized_cover_image(client, monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(images_module, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(images_module, "MAX_IMAGE_BYTES", 10)
    _patch(
        monkeypatch,
        fetch_text=_ld_with_image('"https://img.example/huge.jpg"'),
        reply_text='{"name": "Griekse ovenschotel", "steps": []}',
    )
    FakeAsyncClient.image_url = "https://img.example/huge.jpg"
    FakeAsyncClient.image_content = b"x" * 999

    resp = client.post("/import/", json={"url": "https://www.ah.nl/allerhande/recept/R-1"})
    assert resp.status_code == 200
    assert resp.json()["image_path"] is None


def test_import_without_any_image_leaves_image_path_absent(client, monkeypatch):
    _patch(monkeypatch, reply_text='{"name": "Imported Dish", "steps": []}')
    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 200
    assert resp.json().get("image_path") is None
