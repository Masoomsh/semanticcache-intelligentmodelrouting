# Semantic Cache and Model Router

A FastAPI service that exposes an OpenAI-style chat endpoint, uses Ollama for
embeddings and model inference, stores semantically similar responses in
Pinecone, and records cache, cost, and experiment metrics in SQLite.

## Run

1. Install the project and development dependencies: `pip install -e ".[dev]"`.
2. Copy `.env.example` to `.env` and set
   `PINECONE_API_KEY`, create a Pinecone index with the embedding model's vector
   dimension, and pull the configured Ollama models.
3. Start the API: `uvicorn semantic_router.main:app --reload`.
4. Install the optional frontend dependency: `pip install -e ".[frontend]"`.
5. Start the Streamlit frontend in a second terminal:
   `streamlit run streamlit_app.py`.
6. Run tests: `pytest`.

The Streamlit app connects to the FastAPI service at `STREAMLIT_API_URL`
(default `http://127.0.0.1:8011`). Start FastAPI on port 8011 before using the UI. The UI
provides chat, cache bypass, routed-model/cache status,
quality feedback, the cache/cost/A/B dashboard, and a visual architecture
diagram. The chat view displays only the latest question and answer; earlier
turns may remain as model context but are not shown. The backend does not
support streaming responses, so the UI displays each response when generation
finishes.

At startup the API connects to the configured Pinecone index, initializes the
Ollama client, and verifies that the Ollama embedding dimension matches the
index. `/health` is a liveness endpoint; `/health/ready` reports readiness
after those dependencies have initialized successfully.

The live Pinecone/Ollama integration test is opt-in because it writes a
temporary vector to the configured index. Run it in PowerShell with
`$env:TEST_PINECONE_LIVE="1"; pytest -q tests/test_pinecone.py`. It uses a
unique temporary namespace and deletes that namespace after the test.

The cache uses vector similarity, a configurable score threshold, request-scope
filters, and `expires_at` metadata. Cache entries are shared across clients
within the configured Pinecone namespace and matching request scope. Pinecone
does not expire vectors automatically: expired items are excluded from reads and can be
removed later with a Pinecone metadata-filter cleanup job. Responses larger
than `CACHE_MAX_RESPONSE_CHARS` are returned but not cached.

On Windows, the application uses the system certificate store for outbound TLS
connections so Pinecone works with certificates trusted by the machine without
disabling certificate verification.

The cache detects Pinecone's index schema when it connects. Standard vector
indexes use the vector upsert/query API; schema-based indexes with one dense
vector field use the documents upsert/search API and that field's configured
name.

`POST /v1/chat/completions` accepts `x-cache-bypass: true` and
`Cache-Control: no-cache` or `no-store` to skip both cache reads and writes.
Streaming is explicitly not supported. `/dashboard` reports cache hit rate
and per-arm experiment metrics;
`/reports/cost` returns baseline-versus-routed cost estimates. Configure
`MODEL_PRICES_JSON` as model-name keys with `input_per_million` and
`output_per_million` USD rates to enable meaningful cost comparisons. Without
prices, cost reduction is reported as unknown rather than fabricated.

Enable the randomized A/B split with `AB_TEST_ENABLED=true` and set
`AB_TEST_TREATMENT_PERCENT`. Control requests use `OLLAMA_BASELINE_MODEL`;
treatment requests use the complexity-based router. Send a 1-to-5 quality
rating to `POST /v1/feedback` with the response's `x-request-id` to compare
quality by arm. The 25-40% reduction shown in reports is a target, not a
guaranteed outcome; validate with representative traffic and feedback.

`ROUTING_RULES_JSON` optionally accepts ordered custom regex rules, for
example `[{"category":"coding","pattern":"\\b(python|typescript)\\b"}]`.
Custom rules run before the built-in coding and reasoning rules; unmatched
requests are classified as simple. Optionally set `MODEL_CANDIDATES_JSON` to
category-keyed arrays of models that are adequate for that category; treatment
traffic picks the lowest configured input-plus-output price from that array.
Without candidate arrays, the configured simple, reasoning, and coding models
are used as the respective tier defaults.

Open `/dashboard/ui` for the live dashboard. The `/dashboard` and
`/reports/cost` endpoints expose the corresponding JSON metrics. The router
selects the model based on query complexity and experiment arm; a caller's
OpenAI-compatible `model` field does not override routing.

## API example

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8011/v1/chat/completions `
  -Headers @{"Content-Type"="application/json"; "x-cache-bypass"="true"} `
  -Body '{"messages":[{"role":"user","content":"Summarize semantic caching"}]}'
```

Cache entries are shared across clients using the same Pinecone namespace and
request scope. Avoid caching responses containing user-specific or sensitive
data unless the application handles that isolation separately.
