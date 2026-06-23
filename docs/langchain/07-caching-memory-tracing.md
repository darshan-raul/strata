# LangChain — Caching, Memory, Tracing, Callbacks

> **Part 7 of the LangChain deep-dive.** Caching chat-model
> responses (in-memory, SQLite, Redis), the "memory" landscape
> (and why we don't use it), LangSmith tracing, and the
> `BaseCallbackHandler` interface.

LangChain has four cross-cutting concerns that every chat
project touches eventually:

1. **Caching** — repeated queries shouldn't cost twice.
2. **Memory** — the conversation history. (Strata uses a
   checkpointer, not LangChain memory.)
3. **Tracing** — observability of what's running.
4. **Callbacks** — hooks for any of the above plus custom
   metrics.

---

## 1. Caching chat-model responses

`set_llm_cache(...)` installs a global cache. Subsequent calls
with the same `(model, messages, kwargs)` tuple return the
cached result without hitting the model.

### The cache classes

| Class | Backend | When to use |
|---|---|---|
| `InMemoryCache` | Python dict | Dev, tests, single-process. |
| `SQLiteCache` | SQLite file | Single-process, persistent. |
| `RedisCache` | Redis | Multi-process, multi-host. |
| `RedisSemanticCache` | Redis + embeddings | Semantic caching (similar but not identical queries). |
| `GPTCache` | Various | Use if you already have GPTCache. |
| `UpstashRedisCache` | Upstash serverless Redis | Edge / serverless. |

### `InMemoryCache` — dev

```python
from langchain_core.globals import set_llm_cache
from langchain_core.caches import InMemoryCache

set_llm_cache(InMemoryCache())
```

Every chat-model call (in this process) gets cached. Restart
the process, cache is gone.

### `SQLiteCache` — single-host persistent

```python
from langchain_community.cache import SQLiteCache

set_llm_cache(SQLiteCache(database_path=".langchain.db"))
```

Survives restarts. Good for `make chat` iteration in dev.

### `RedisCache` — multi-host

```python
from langchain_community.cache import RedisCache
import redis

set_llm_cache(RedisCache(redis_=redis.Redis.from_url("redis://...")))
```

Shared across all agent-service replicas. Strata's Phase 6+
plan: install Redis in-cluster, point `RedisCache` at it.

### `RedisSemanticCache` — similar-but-not-identical caching

```python
from langchain_community.cache import RedisSemanticCache
from langchain_openai import OpenAIEmbeddings

set_llm_cache(RedisSemanticCache(
    redis_url="redis://...",
    embedding=OpenAIEmbeddings(model="text-embedding-3-small"),
))
```

Caches the *embedding* of the prompt. A new query that's
semantically similar (cosine sim above a threshold) hits the
cache. Useful for "the user asked the same thing in different
words." Strata doesn't use this — it amplifies hallucination
risk because the cached answer might be subtly wrong for the
new query.

### Per-call cache override

```python
from langchain_core.caches import InMemoryCache

result = model.invoke(messages, cache=False)         # bypass cache
result = model.invoke(messages, cache=InMemoryCache()) # use a specific cache
```

Useful in tests to ensure fresh responses.

### What gets cached

The cache key is `(model name, messages, kwargs)`. Two calls
with the same messages and same `temperature` are identical
keys. Two calls with different `temperature` are not.

### What Strata does

- **Phase 2:** No caching. The model is fresh every time; we
  want to see what the model actually returns.
- **Phase 6+:** LiteLLM has its own cache layer (Redis
  configurable). Strata's caching is at the LiteLLM layer, not
  the LangChain layer. If LiteLLM is removed, fall back to
  `RedisCache` here.

---

## 2. "Memory" — the LangChain concept, and why we don't use it

LangChain has a `langchain.memory` module with classes like
`ConversationBufferMemory`, `ConversationSummaryMemory`,
`ConversationBufferWindowMemory`, `VectorStoreRetrieverMemory`,
etc. They all do one of:

1. **Maintain a message list across turns.** The graph's
   checkpointer does this better.
2. **Summarize old turns** to keep the message list short. The
   graph + a custom node does this better.
3. **Store a vector of past turns** for retrieval. The
   `retriever-service` + a `MemoryStore` does this better.

**Strata uses none of these.** The LangGraph checkpointer
(`MemorySaver` in dev, `PostgresSaver` in prod) is the
authoritative conversation store. A `MemoryStore` (cross-thread
facts) is the long-term memory. LangChain's memory classes are
considered legacy.

### Migration path

If you find yourself reaching for `ConversationBufferMemory`,
you actually want:

| LangChain memory | Modern replacement |
|---|---|
| `ConversationBufferMemory` | LangGraph `MemorySaver` + the `messages` state field. |
| `ConversationSummaryMemory` | A custom graph node that summarizes + a checkpointer. |
| `ConversationBufferWindowMemory(k=N)` | `trim_messages(max_tokens=N, strategy="last")` before invoking the model. |
| `VectorStoreRetrieverMemory` | `MemoryStore` (LangGraph) or `retriever-service` with a `memories` collection. |
| `CombinedMemory` (composing multiple) | Multiple `MemoryStore` namespaces in the graph. |

---

## 3. Tracing — LangSmith

LangSmith is LangChain's tracing/observability product. Set two
env vars and every `Runnable` invocation gets traced.

### Setup

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=lsv2_pt_...
export LANGCHAIN_PROJECT=strata-agent-service
```

That's it. Every chat-model call, every tool, every chain run
appears in the LangSmith UI as a tree of spans.

### What gets traced

- All `Runnable.invoke` / `ainvoke` / `stream` / `astream` / `batch`
  / `abatch` calls.
- The full input, full output, latency, token counts.
- Nested events (a chain that calls a model that calls a tool —
  all visible as a tree).
- Custom events emitted by callbacks.

### What Strata does

- **Phase 2-5:** No LangSmith. The project runs locally and
  the author is the only user; console logs are enough.
- **Phase 6+:** Optional. Add `LANGCHAIN_TRACING_V2=true` to
  the agent-service Deployment in `dev` and `staging`
  environments. Never enable in `prod` with PII flowing
  through — every prompt is sent to LangSmith.

### PII / data handling

LangSmith traces the full input/output of every call. If your
prompts contain user data (emails, names, secrets), they go to
LangSmith. Use a `metadata` filter or a redaction callback to
strip PII before tracing. Or don't enable tracing in prod.

The LangSmith `hidden` tag can be set on a runnable to skip
tracing for that subtree:

```python
model.with_config(tags=["hidden"])    # this call is not traced
```

### Alternatives to LangSmith

- **OpenTelemetry** — LangChain emits OTel spans via
  `langchain_core.tracers.otel`. Wire to your own backend.
- **Custom callback** — write a `BaseCallbackHandler` (see
  §4) that writes to Datadog, Honeycomb, etc.
- **LiteLLM's built-in observability** — LiteLLM can log to
  Langfuse, Datadog, etc. directly. Strata's likely path.

---

## 4. Callbacks — the `BaseCallbackHandler` interface

A callback is a Python object with hooks. LangChain invokes
the hooks at lifecycle events. The hooks receive rich context
(input, output, run id, parent run id, tags, metadata).

```python
from langchain_core.callbacks import BaseCallbackHandler

class CostTrackingHandler(BaseCallbackHandler):
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def on_chat_model_end(self, output, *, run_id, parent_run_id, tags, **kwargs):
        u = output.usage_metadata or {}
        self.total_input_tokens += u.get("input_tokens", 0)
        self.total_output_tokens += u.get("output_tokens", 0)
```

### The full hook list

| Hook | When |
|---|---|
| `on_chain_start` | A RunnableSequence / RunnableLambda begins. |
| `on_chain_end` | A chain ends successfully. |
| `on_chain_error` | A chain raised. |
| `on_chat_model_start` | A chat model call begins. |
| `on_chat_model_end` | A chat model call completes. |
| `on_chat_model_error` | A chat model raised. |
| `on_chat_model_stream` | A chat model emits a chunk (token). |
| `on_llm_start` / `on_llm_end` / `on_llm_error` / `on_llm_stream` | Legacy completion models. |
| `on_tool_start` | A tool begins. |
| `on_tool_end` | A tool completes. |
| `on_tool_error` | A tool raised. |
| `on_retriever_start` | A retriever begins. |
| `on_retriever_end` | A retriever completes. |
| `on_retriever_error` | A retriever raised. |
| `on_prompt_start` | A prompt template runs. |
| `on_prompt_end` | A prompt template completes. |
| `on_parser_start` | A parser begins. |
| `on_parser_end` | A parser completes. |
| `on_custom_event` | Your code emitted a custom event. |
| `on_text` | Generic text was emitted (used in some agents). |
| `on_retry` | A retry is about to happen. |

### Using a callback

```python
model.invoke(messages, config={"callbacks": [CostTrackingHandler()]})
```

Or globally:

```python
from langchain_core.globals import set_debug, set_verbose

set_debug(True)    # prints every event
set_verbose(True)  # prints the chain inputs/outputs
```

For the cost tracker, you'd attach it at the graph level so it
sees all calls in one go.

### The async variants

`on_chat_model_end` has an async sibling `on_chat_model_end_async`
(not a real hook — instead, the hook is awaited if the call is
async). If your callback does I/O, define both:

```python
class MyHandler(BaseCallbackHandler):
    def on_chat_model_end(self, output, **kwargs):
        sync_write_to_db(output)

    async def on_chat_model_end_async(self, output, **kwargs):
        await async_write_to_db(output)
```

Actually, no — `BaseCallbackHandler` doesn't have async siblings
per hook. Instead, LangChain detects if the hook is a coroutine
function (`async def`) and awaits it. So just write the hook
async if you need async I/O:

```python
class MyHandler(BaseCallbackHandler):
    async def on_chat_model_end(self, output, **kwargs):
        await db.write(...)
```

### The "writer" pattern for custom events

Inside a graph node, you can emit a custom event:

```python
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

def my_node(state, config: RunnableConfig):
    writer = get_stream_writer()
    writer({"event": "validation_failed", "details": "..."})
    return state
```

The writer feeds into `astream_events` as `on_custom_event`
events. Use it for application-level signals that aren't model
or tool events.

---

## 5. `get_openai_callback` (legacy, OpenAI-only)

```python
from langchain_community.callbacks import get_openai_callback

with get_openai_callback() as cb:
    result = model.invoke(messages)
    print(cb.total_tokens)
    print(cb.total_cost)
```

`get_openai_callback` is a context manager that tracks OpenAI
usage. **It only works for OpenAI**, not Bedrock/Anthropic via
LiteLLM. For Strata, use the `usage_metadata` directly.

---

## 6. Strata's observability plan

| Phase | Tracing | Logging | Metrics |
|---|---|---|---|
| 2 | None. Logs only. | `app.main` loguru/print | None. |
| 3+ | None. | Structured JSON logs to stdout. | None. |
| 5 | Optional LangSmith in dev. | JSON logs to Loki. | None. |
| 6 | LangSmith in dev/staging. | Loki. | Prometheus (latency, token counts, error rate). |

The `BaseCallbackHandler` is the right shape for a custom
"write to Postgres" callback that records every chat-model
call's `usage_metadata` for cost analysis. Lands in Phase 6+.

---

## 7. The "global state" trap

`set_llm_cache(...)` is a **global** setting. It affects every
chat-model call in the process. If you set it once in
`main.py`, every test that imports from `app` also gets the
cache.

For tests, use `cache=False` per call:

```python
def test_my_agent():
    response = model.invoke(messages, cache=False)
    assert response.content == "..."
```

Or set/unset the cache in test fixtures:

```python
@pytest.fixture(autouse=True)
def no_llm_cache():
    from langchain_core.globals import set_llm_cache
    from langchain_core.caches import InMemoryCache
    set_llm_cache(InMemoryCache())    # fresh cache per test
    yield
```

---

## 8. Custom callback for cost tracking — example

```python
from langchain_core.callbacks import BaseCallbackHandler

class CostTracker(BaseCallbackHandler):
    def __init__(self):
        self.calls: list[dict] = []

    def on_chat_model_end(self, output, *, run_id, **kwargs):
        u = output.usage_metadata or {}
        self.calls.append({
            "run_id": str(run_id),
            "model": output.response_metadata.get("model_name"),
            "input_tokens": u.get("input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0),
        })

# Usage:
tracker = CostTracker()
result = graph.invoke(input_state, config={"callbacks": [tracker]})
print(tracker.calls)
# [{"run_id": "...", "model": "amazon.nova-pro-v1:0", "input_tokens": 87, ...}]
```

For Strata's Phase 5+ cost-tracking: wrap the call site, not
the model. The graph emits a `CostTracker.calls` list per
request, which the response includes (or writes to Postgres
asynchronously).

---

## 9. Common pitfalls

1. **LangChain memory classes are legacy.** Don't use them.
2. **LangSmith traces everything**, including any PII in the
   prompt. Use the `hidden` tag or skip in prod.
3. **`set_llm_cache` is global** — affects all chat models in
   the process. Reset in tests.
4. **`InMemoryCache` doesn't share across replicas.** Two
   agent-service pods have two caches. Use `RedisCache` for
   shared caching.
5. **`get_openai_callback` only works for OpenAI**, not for
   LiteLLM (which presents as OpenAI but the actual call is
   Bedrock). Use `usage_metadata` instead.
6. **`BaseCallbackHandler` hooks for async** — LangChain
   awaits if the hook is a coroutine function. Don't define
   both sync and async; pick one.
7. **`on_retry`** is the hook for "a retry is about to happen."
   Use it to log or backoff; don't try to cancel the retry.
8. **`astream_events` is not the same as `callbacks`.** They
   overlap but events is the higher-level API. For
   application-level observability, prefer events; for
   per-call hooks, prefer callbacks.

---

## 10. What to read next

- `08-testing-and-pitfalls.md` — `FakeListChatModel` and other
  testing utilities.
- `../rag.md` — the retriever service and the `retrieve` node
  (no LangChain retrievers used).
- `../litellm.md` — LiteLLM's own cache and observability
  layer.
- LangChain callbacks: <https://python.langchain.com/docs/concepts/callbacks/>
- LangChain caching: <https://python.langchain.com/docs/how_to/llm_caching/>
