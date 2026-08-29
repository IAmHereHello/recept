from types import SimpleNamespace

import pytest

import app.routers.import_recipe as import_recipe_module


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeAsyncClient:
    """Stands in for httpx.AsyncClient so tests never hit the network."""

    fetch_text = "<html>fake recipe page</html>"
    fetch_error = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None):
        if self.fetch_error:
            raise self.fetch_error
        return FakeResponse(self.fetch_text)


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
    monkeypatch.setattr(import_recipe_module, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))
    if reply_text is not None:
        FakeAnthropicClient.reply_text = reply_text
    if fetch_text is not None:
        FakeAsyncClient.fetch_text = fetch_text
    FakeAnthropicClient.stop_reason = stop_reason
    monkeypatch.setattr(import_recipe_module, "anthropic", SimpleNamespace(AsyncAnthropic=FakeAnthropicClient))


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
