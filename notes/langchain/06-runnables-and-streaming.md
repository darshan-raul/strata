# LangChain — Runnables & Streaming

> **Part 6 of the LangChain deep-dive.** The full `Runnable`
> protocol, the composition primitives (`RunnableParallel`,
> `RunnablePassthrough`, `RunnableBranch`, `RunnableWithFallbacks`),
> and the streaming/event APIs.

Everything in LangChain is a `Runnable`. The `|` operator
composes them. The composition primitives let you build
non-trivial data flow (fan-out, fan-in, conditional routing,
fallback) **without a graph**. For control flow with cycles
(agent loops), use LangGraph. For everything else, runnables
are enough.

---

## 1. The full `Runnable` interface

```python
class Runnable(Generic[Input, Output]):
    # Sync
    def invoke(self, input: Input, config: RunnableConfig | None = None) -> Output: ...
    def stream(self, input: Input, config: RunnableConfig | None = None) -> Iterator[Output]: ...
    def batch(self, inputs: list[Input], config: RunnableConfig | None = None) -> list[Output]: ...

    # Async
    async def ainvoke(self, input: Input, config: RunnableConfig | None = None) -> Output: ...
    async def astream(self, input: Input, config: RunnableConfig | None = None) -> AsyncIterator[Output]: ...
    async def abatch(self, inputs: list[Input], config: RunnableConfig | None = None) -> list[Output]: ...

    # Lifecycle / inspection
    def with_config(self, config: RunnableConfig) -> Runnable: ...
    def with_retry(self, **kwargs) -> Runnable: ...
    def with_fallbacks(self, fallbacks: list[Runnable], **kwargs) -> Runnable: ...
    def with_listeners(self, **kwargs) -> Runnable: ...
    def with_alisteners(self, **kwargs) -> Runnable: ...
    def bind(self, **kwargs) -> Runnable: ...
    def assign(self, **kwargs) -> Runnable: ...
    def pick(self, keys: str | list[str]) -> Runnable: ...
    def transform(self, iterator: AsyncIterator[Input]) -> AsyncIterator[Output]: ...
    def atransform(self, iterator: AsyncIterator[Input]) -> AsyncIterator[Output]: ...
    def stream_log(self, ...) -> Iterator[RunLogPatch]: ...
    def astream_log(self, ...) -> AsyncIterator[RunLogPatch]: ...
    def astream_events(self, ...) -> AsyncIterator[StreamEvent]: ...
```

Twelve-ish methods. Every provider, prompt, parser, tool, and
chain implements them. This is the contract.

### The sync/async matrix

| Need | Sync | Async |
|---|---|---|
| One call, get result | `invoke` | `ainvoke` |
| One call, get chunks | `stream` | `astream` |
| Many calls (sequential default) | `batch` | `abatch` |
| Many calls, max concurrency | `batch(..., config={"max_concurrency": N})` | `abatch(...)` |
| Iterate over many calls | `batch_as_completed` | `abatch_as_completed` |
| Lifecycle events | `astream_events` | `astream_events` |
| Structured event log | `astream_log` | `astream_log` |
| Transform an iterator | `transform` | `atransform` |

Inside FastAPI handlers, prefer async. Inside tests, sync is
fine.

---

## 2. The composition primitives

### `RunnableLambda` — wrap a function

```python
from langchain_core.runnables import RunnableLambda

strip = RunnableLambda(lambda x: x.strip())
chain = prompt | model | strip
```

A `RunnableLambda` is the most basic wrapper. Use it to
shoehorn a plain function into the `Runnable` system.

### `RunnablePassthrough` — return input unchanged

```python
from langchain_core.runnables import RunnablePassthrough

chain = RunnablePassthrough() | some_step
# The output of some_step is the same as the input.
```

Used in RAG's classic "context + question" pattern:

```python
from langchain_core.runnables import RunnablePassthrough

chain = (
    RunnablePassthrough.assign(context=lambda x: retriever.invoke(x["question"]))
    | prompt
    | model
    | StrOutputParser()
)
# Input: {"question": "What is EKS?"}
# After assign: {"question": "What is EKS?", "context": [...]}
# prompt sees both; formats a "context: ...\nquestion: ..." message.
```

### `RunnablePassthrough.assign(...)` — add to a dict

`assign` is a method on any `Runnable` that takes a dict and
returns a dict. It adds (or overrides) keys:

```python
chain = (
    RunnablePassthrough.assign(
        context=lambda x: retriever.invoke(x["question"]),
        timestamp=lambda _: datetime.now().isoformat(),
    )
    | prompt
    | model
    | parser
)
```

The lambda receives the current dict and returns a value to
assign.

### `RunnableParallel` — fan-out

```python
from langchain_core.runnables import RunnableParallel

chain = RunnableParallel(
    summary=summarize_chain,
    details=detail_chain,
    sentiment=sentiment_chain,
)
# Input: a single text
# Output: {"summary": "...", "details": "...", "sentiment": "..."}
```

The three sub-runnables run **in parallel** (or as parallel as
the executor allows). The output dict has all three keys.

You can also write this as a dict literal — `RunnableParallel` is
the dict form:

```python
chain = prompt | model | RunnableParallel(
    summary=summary_prompt | summary_model,
    details=details_prompt | details_model,
)
```

### `RunnableMap` — alias for `RunnableParallel`

Historical name. Same thing. Prefer `RunnableParallel`.

### `RunnableBranch` — pick a runnable by condition

```python
from langchain_core.runnables import RunnableBranch

chain = RunnableBranch(
    (lambda x: x["type"] == "code", code_chain),
    (lambda x: x["type"] == "math", math_chain),
    default_chain,    # the else
)
```

The first condition that returns `True` wins. If none match and
no default is given, the input passes through unchanged.

Use it for "if input has shape X, do Y, else do Z." Within a
graph, you usually do this with `add_conditional_edges` instead.

### `RunnableWithFallbacks` — graceful degradation

```python
primary = primary_model.with_retry(stop_after_attempt=3)
fallback = fallback_model
chain = primary.with_fallbacks([fallback])
```

If `primary.invoke(...)` raises, the fallback is tried.
Multiple fallbacks are tried in order.

```python
chain = primary.with_fallbacks(
    [backup1, backup2, backup3],
    exceptions_to_handle=(openai.RateLimitError, openai.APITimeoutError),
)
```

`exceptions_to_handle` defaults to `(Exception,)` — any error
triggers fallback. Narrow this to avoid masking real bugs.

### `Runnable.bind(...)` — partial kwargs

```python
chain = prompt | model.bind(stop=["\n\n"])
# Equivalent to model.invoke(messages, stop=["\n\n"]) for every call.
```

Use `bind` to set per-call kwargs without rebuilding the chain.
You can bind any kwarg the underlying runnable accepts.

### `Runnable.with_config(...)` — set `RunnableConfig`

```python
chain = (prompt | model | parser).with_config(
    tags=["prod"],
    metadata={"user_id": "user-42"},
    max_concurrency=10,
)
```

Per-run config without modifying the chain itself.

### `Runnable.assign(...)` — add to dict output

Same idea as `RunnablePassthrough.assign(...)` but on any
`Runnable` that returns a dict. Adds new keys to the output.

```python
chain = (
    prompt
    .assign(revised=lambda x: revise(x["draft"]))
    .assign(final=lambda x: finalize(x["revised"]))
)
```

---

## 3. `RunnableConfig` — the thread that ties it all together

`RunnableConfig` is passed to every `invoke`/`stream`/etc. It
carries:

```python
class RunnableConfig(TypedDict, total=False):
    tags: list[str]
    metadata: dict[str, Any]
    callbacks: list[BaseCallbackHandler]
    run_name: str
    max_concurrency: int | None
    recursion_limit: int
    configurable: dict[str, Any]
    run_id: UUID | None
    parent_run_id: UUID | None
```

In a graph, LangGraph fills most of this for you. In a chain,
you fill it in the call site.

### Accessing `RunnableConfig` inside a runnable

```python
from langchain_core.runnables import RunnableLambda, RunnableConfig

@RunnableLambda
def my_step(x, config: RunnableConfig):
    user_id = config["configurable"].get("user_id")
    return do_thing(x, user_id=user_id)
```

The second arg to any `RunnableLambda` is the config. Use it to
pull per-call context (user id, thread id, request id).

### Inside a tool

```python
from langchain_core.tools import tool

@tool
async def list_my_clusters(config: RunnableConfig) -> str:
    """List the current user's clusters."""
    user_id = config["configurable"]["user_id"]
    return await db.fetch_clusters(user_id)
```

The tool gets the config too. This is how `InjectedToolArg`
gets resolved.

---

## 4. `bind` vs `with_config` vs `with_retry` vs `with_fallbacks`

| Method | What | When |
|---|---|---|
| `bind(**kwargs)` | Set call-time kwargs that get passed to every invocation. | `stop`, `temperature`, `tools`. |
| `with_config(config)` | Set `RunnableConfig` for every invocation. | Tags, metadata, callbacks. |
| `with_retry(...)` | Wrap with retry logic. | Transient errors (429, timeout). |
| `with_fallbacks([...])` | Wrap with fallback. | Provider outage, model swap. |

You can stack them:

```python
chain = (
    model
    .bind(stop=["\n\n"])
    .with_config(tags=["prod"])
    .with_retry(stop_after_attempt=3)
    .with_fallbacks([fallback_model])
)
```

The order matters. `bind` happens first (kwargs are baked in).
`with_config` happens next. `with_retry` wraps the call. 
`with_fallbacks` wraps the whole thing.

---

## 5. `astream_events` — the full event stream

`astream_events(version="v2")` is the most powerful streaming
API. It yields **lifecycle events** from every component
involved in a call.

```python
async for event in chain.astream_events(input, version="v2"):
    print(event)
```

Each event is a dict:

```python
{
    "event": "on_chat_model_stream",
    "name": "ChatOpenAI",
    "run_id": "...",
    "parent_ids": [...],
    "tags": [...],
    "metadata": {...},
    "data": {"chunk": AIMessageChunk(...)},
    "created_at": datetime,
}
```

### The full event taxonomy

| Event | Emitted by | `data` |
|---|---|---|
| `on_chat_model_start` | Chat model begins. | `input` (the messages). |
| `on_chat_model_stream` | Chat model emits a chunk. | `chunk` (AIMessageChunk). |
| `on_chat_model_end` | Chat model done. | `output` (AIMessage). |
| `on_llm_start` / `on_llm_stream` / `on_llm_end` | Legacy completion models. | |
| `on_chain_start` | A RunnableSequence / RunnableLambda begins. | `input`. |
| `on_chain_stream` | A chain emits a chunk. | `chunk`. |
| `on_chain_end` | A chain ends. | `output`. |
| `on_tool_start` | A tool begins. | `input` (the args). |
| `on_tool_stream` | A tool emits a chunk. | `chunk`. |
| `on_tool_end` | A tool completes. | `output`. |
| `on_retriever_start` | A retriever begins. | `input` (the query). |
| `on_retriever_end` | A retriever ends. | `output` (the docs). |
| `on_prompt_start` | A ChatPromptTemplate runs. | `input`. |
| `on_prompt_end` | A prompt template completes. | `output` (the formatted prompt). |
| `on_parser_start` | An output parser runs. | `input`. |
| `on_parser_end` | A parser completes. | `output`. |
| `on_custom_event` | Your code emitted a custom event. | Whatever you passed. |
| `on_error` | Something errored. | `error`. |

### Filtering

The events stream is **loud** — a single graph run can emit
thousands. Filter with:

```python
async for event in chain.astream_events(
    input,
    version="v2",
    include_names=["call_model"],          # only this node
    include_types=["chat_model"],          # only chat model events
    include_tags=["prod"],
    exclude_tags=["debug"],
    exclude_types=["parser", "prompt"],
):
    ...
```

| Param | What it filters on |
|---|---|
| `include_names` | The `name` of the runnable (e.g. "call_model", "tools"). |
| `include_types` | The kind: "chat_model", "tool", "chain", "retriever", "parser", "prompt". |
| `include_tags` | The `tags` on the runnable. |
| `exclude_*` | The same, but exclusion. |

### Mapping to NDJSON (Strata's wire format)

```python
async def chat_to_ndjson(graph, input_state, config):
    yield ndjson({"type": "start"})

    async for event in graph.astream_events(
        input_state, config, version="v2",
        include_types=["chat_model", "tool"],
    ):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            yield ndjson({
                "type": "token",
                "text": event["data"]["chunk"].content,
            })
        elif kind == "on_tool_start":
            yield ndjson({
                "type": "tool_call",
                "name": event["name"],
                "args": event["data"]["input"],
            })
        elif kind == "on_tool_end":
            yield ndjson({
                "type": "tool_result",
                "name": event["name"],
                "result": event["data"]["output"],
            })
        elif kind == "on_chat_model_end":
            u = event["data"]["output"].usage_metadata or {}
            yield ndjson({
                "type": "usage",
                "input_tokens": u.get("input_tokens", 0),
                "output_tokens": u.get("output_tokens", 0),
            })

    yield ndjson({"type": "done"})
```

This is the full chat-rail. The UI consumes NDJSON; the
agent-service emits it; the user sees tokens as they arrive.

### `astream_log` — the structured log

`astream_log` yields `RunLogPatch` objects. More structured than
`astream_events` but more verbose. Used internally by LangSmith.
Prefer `astream_events` for app-level streaming.

---

## 6. `stream` vs `astream` for chat

For a chat UI that just wants tokens:

```python
async for chunk in model.astream(messages):
    if chunk.content:
        await websocket.send(chunk.content)
```

Requires `streaming=True` on the model. Chunks are
`AIMessageChunk` objects; concatenate `content` to get the
full text.

For a chat UI that wants tool calls and tokens:

```python
async for event in graph.astream_events(input, config, version="v2"):
    if event["event"] == "on_chat_model_stream":
        ...
    elif event["event"] == "on_tool_start":
        ...
```

`astream_events` is the only API that surfaces both.

---

## 7. `batch` — bulk processing

```python
results = chain.batch([
    {"input": "question 1"},
    {"input": "question 2"},
    {"input": "question 3"},
])
# results is a list of outputs, one per input.
```

By default, `batch` runs sequentially. For parallel:

```python
results = await chain.abatch(
    inputs,
    config={"max_concurrency": 10},
)
```

`abatch` with `max_concurrency` is the right tool for "I have
100 questions, run them with at most 10 in flight." Strata
doesn't bulk-process queries today, but if you ever do (e.g.
backfilling embeddings for `rag-indexer`), this is the API.

### `batch_as_completed`

```python
for result in chain.batch_as_completed(inputs):
    # result is (index, output) for whichever input finished first
    ...
```

Yields results as they complete, not in input order. Useful
for "show me the first result as soon as it's ready."

---

## 8. Pickling / serialization

`Runnable`s are picklable when their components are picklable.
Chat models, prompts, parsers, tools — all picklable. Custom
`RunnableLambda`s that close over unpicklable state (a
`httpx.AsyncClient`, a DB connection) are not.

For Strata, the graph is built once at module load and never
serialized. The compiled graph is reused per request. No
pickling.

If you ever need to ship a graph as a service (LangGraph
Platform), the platform handles serialization.

---

## 9. Inspecting a `Runnable`

```python
chain.get_graph().print_ascii()
# Prints:
#  +---------------------------------+
#  | Parallel<question,context>Input |
#  +---------------------------------+
#             ***        ***
#            **            **
#           *                *
#  +----------------+   +----------------+
#  | PromptTemplate |   |    Retriever   |
#  +----------------+   +----------------+
#           *                *
#            **            **
#             ***        ***
#          +------------------------+
#          | ChatOpenAI | StrOutput |
#          +------------------------+

chain.get_graph().to_json()
# A JSON spec, renderable as Mermaid.
```

For a graph (LangGraph), `graph.get_graph()` is more elaborate —
it shows nodes and edges. For a chain, you get this kind of
visualization.

---

## 10. Strata's use of runnables

### Today (Phase 2)

- `ChatOpenAI` is a `Runnable`. We call `bind_tools` on it.
- `@tool` is a `Runnable`. We pass it to `bind_tools`.
- `add_messages` reducer in state is a `Runnable` semantically
  (it's the channel's reducer).
- The graph itself is built with `StateGraph` and compiled to a
  `Runnable`-like object with `invoke` / `ainvoke` / `astream`.

### Phase 4+ (RAG)

- `RunnablePassthrough.assign(context=lambda x: retriever.invoke(x["question"]))`
  in the prompt assembly (if we go chain-based for the
  structured-output QA).
- `with_structured_output` for the "did the docs answer this?"
  check.

### Phase 5+ (web UI)

- `astream_events` for token streaming over SSE.
- `with_fallbacks` for graceful degradation.
- `with_retry` for transient errors.

### What Strata does NOT use

- `RunnableSequence` (chains) — the graph replaces them.
- `RunnableParallel` for fan-out — `add_conditional_edges` and
  `Send` do this in graph form.
- `RunnableWithMessageHistory` (legacy) — the checkpointer
  replaces it.

---

## 11. Common pitfalls

1. **`bind` doesn't accept a config object.** It accepts kwargs
   to pass to the underlying runnable. For config, use
   `with_config`.
2. **Stacking `with_retry` and LiteLLM retries** — same as
   chat-model retries, double-counting. Pick one.
3. **`astream_events(version="v2")`** — the `version` argument
   is required and `"v2"` is the right value. `"v1"` is the
   legacy form, mostly removed.
4. **`batch` is sync, sequential by default.** For parallel
   async, use `abatch` with `max_concurrency`.
5. **`RunnablePassthrough` doesn't transform anything.** It
   returns the input. Use it for structure, not for logic.
6. **`with_fallbacks` catches all exceptions by default.** You
   will silently swallow real bugs. Pass `exceptions_to_handle`.
7. **Custom `RunnableLambda`s that close over unpicklable
   state** break serialization. Refactor to pass the state in
   the config.
8. **`astream_events` events come in arbitrary order.** Don't
   rely on `on_tool_start` happening after `on_chat_model_end`
   for the previous tool call. Use the `run_id` and
   `parent_run_id` to reconstruct the hierarchy.
9. **Filtering `astream_events` by `include_types`** is a
   substring match. `"chain"` matches `"chat_model_chain"`. Be
   specific.

---

## 12. What to read next

- `07-caching-memory-tracing.md` — caching chat-model responses,
  LangSmith tracing, callbacks.
- `../langgraph/07-streaming.md` — graph-level streaming, which
  is layered on top of `astream_events`.
- LangChain Runnable concepts: <https://python.langchain.com/docs/concepts/runnables/>
