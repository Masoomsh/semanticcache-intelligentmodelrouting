from fastapi.testclient import TestClient

from semantic_router.analytics import AnalyticsStore
from semantic_router.api import create_app
from semantic_router.config import Settings


class FakeCache:
    def __init__(self):
        self.entries = {}

    async def lookup(self, vector, scope_id):
        return self.entries.get(scope_id)

    async def store(self, vector, scope_id, category, model, entry):
        self.entries[scope_id] = entry


class FakeOllama:
    def __init__(self):
        self.chat_calls = 0
        self.embed_calls = 0

    async def embed(self, model, text):
        self.embed_calls += 1
        return [0.1, 0.2, 0.3]

    async def chat(self, model, messages, options):
        self.chat_calls += 1
        return {
            "message": {"content": "answer"},
            "prompt_eval_count": 8,
            "eval_count": 3,
        }

    async def close(self):
        pass


def test_semantic_cache_headers_and_dashboard():
    settings = Settings(
        simple_model="small",
        reasoning_model="medium",
        coding_model="coder",
        baseline_model="large",
        model_prices={
            "small": {"input_per_million": 1, "output_per_million": 2},
            "large": {"input_per_million": 2, "output_per_million": 4},
        },
    )
    ollama = FakeOllama()
    analytics = AnalyticsStore(":memory:")
    app = create_app(settings, FakeCache(), ollama, analytics)
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    payload = {"messages": [{"role": "user", "content": "What is 2 + 2?"}]}

    first = client.post("/v1/chat/completions", json=payload)
    second = client.post("/v1/chat/completions", json=payload)
    bypassed = client.post(
        "/v1/chat/completions", json=payload, headers={"x-cache-bypass": "true"}
    )
    no_store = client.post(
        "/v1/chat/completions", json=payload, headers={"Cache-Control": "no-store"}
    )

    assert first.status_code == second.status_code == bypassed.status_code == no_store.status_code == 200
    assert first.headers["x-cache"] == "MISS"
    assert second.headers["x-cache"] == "HIT"
    assert bypassed.headers["x-cache"] == "BYPASS"
    assert no_store.headers["x-cache"] == "BYPASS"
    assert ollama.chat_calls == 3
    assert ollama.embed_calls == 2
    assert client.get("/dashboard").json()["cache_hit_rate"] == 0.25
    dashboard = client.get("/dashboard/ui")
    assert dashboard.status_code == 200
    assert "Cache hit rate" in dashboard.text
    client.close()
