import json
from types import SimpleNamespace

import pytest

import app.ai as ai_module
from app.health import grade
from tests.conftest import make_recipe


class FakeAnthropicClient:
    """Configurable stand-in for anthropic.AsyncAnthropic."""

    reply = {"score": 72, "rationale": "Veel groente, maar witte pasta en feta.", "tip": "Kies volkoren orzo."}
    stop_reason = "end_turn"
    calls = 0

    def __init__(self, *args, **kwargs):
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        FakeAnthropicClient.calls += 1
        text = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
        return SimpleNamespace(
            content=[SimpleNamespace(text=text)],
            stop_reason=self.stop_reason,
        )


@pytest.fixture(autouse=True)
def _fake_ai(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai_module.anthropic, "AsyncAnthropic", FakeAnthropicClient)
    yield
    FakeAnthropicClient.reply = {"score": 72, "rationale": "ok", "tip": "ok"}
    FakeAnthropicClient.stop_reason = "end_turn"
    FakeAnthropicClient.calls = 0


def test_grade_bands():
    assert [grade(s) for s in (100, 80, 79, 65, 64, 50, 49, 35, 34, 0)] == \
        ["A", "A", "B", "B", "C", "C", "D", "D", "E", "E"]
    assert grade(None) is None


def test_health_review_scores_and_persists(client):
    recipe = make_recipe(client)
    FakeAnthropicClient.reply = {"score": 82, "rationale": "Peulvruchten en groente.", "tip": "Minder zout."}

    resp = client.post(f"/recipes/{recipe['id']}/health-review")
    assert resp.status_code == 200
    body = resp.json()
    assert body["health_score"] == 82
    assert body["health_grade"] == "A"
    assert body["health_rationale"] == "Peulvruchten en groente."
    assert body["health_tip"] == "Minder zout."
    assert body["health_scored_at"] is not None

    # persisted — visible on a plain GET too
    assert client.get(f"/recipes/{recipe['id']}").json()["health_score"] == 82


def test_health_review_rejects_out_of_range_score(client):
    recipe = make_recipe(client)
    FakeAnthropicClient.reply = {"score": 240, "rationale": "x", "tip": "y"}
    resp = client.post(f"/recipes/{recipe['id']}/health-review")
    assert resp.status_code == 502


def test_health_review_missing_api_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    recipe = make_recipe(client)
    resp = client.post(f"/recipes/{recipe['id']}/health-review")
    assert resp.status_code == 500


def test_health_review_404_for_unknown_recipe(client):
    assert client.post("/recipes/999/health-review").status_code == 404


def test_bulk_scores_only_unscored(client):
    a = make_recipe(client, name="A")
    b = make_recipe(client, name="B")
    client.post(f"/recipes/{a['id']}/health-review")  # a is now scored
    FakeAnthropicClient.calls = 0

    resp = client.post("/recipes/health-review/bulk")
    assert resp.status_code == 200
    assert resp.json() == {"scored": 1, "failed": 0, "total": 1}
    assert FakeAnthropicClient.calls == 1  # only b
    assert client.get(f"/recipes/{b['id']}").json()["health_grade"] is not None


def test_bulk_counts_failures_without_aborting(client):
    make_recipe(client, name="A")
    make_recipe(client, name="B")
    FakeAnthropicClient.reply = "not json"

    resp = client.post("/recipes/health-review/bulk")
    assert resp.json() == {"scored": 0, "failed": 2, "total": 2}
