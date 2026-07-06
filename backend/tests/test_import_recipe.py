from types import SimpleNamespace
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

    def __init__(self, *args, **kwargs):
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        return SimpleNamespace(content=[SimpleNamespace(text=self.reply_text)])


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
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(import_recipe_module, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))
    FakeAnthropicClient.reply_text = "not valid json"
    monkeypatch.setattr(import_recipe_module, "anthropic", SimpleNamespace(AsyncAnthropic=FakeAnthropicClient))

    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 500
    assert "invalid JSON" in resp.json()["detail"]


def test_import_succeeds_with_valid_ai_json(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(import_recipe_module, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))
    FakeAnthropicClient.reply_text = '{"name": "Imported Dish", "ingredients": [], "steps": []}'
    monkeypatch.setattr(import_recipe_module, "anthropic", SimpleNamespace(AsyncAnthropic=FakeAnthropicClient))

    resp = client.post("/import/", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Imported Dish"
