# LangChain — Chat Models

> **Part 3 of the LangChain deep-dive.** The `BaseChatModel`
> interface, the `bind_tools` / `with_structured_output` / `with_retry`
> methods, how Strata uses `ChatOpenAI` pointed at LiteLLM.

A chat model takes a list of messages and returns an `AIMessage`
(or an iterator of `AIMessageChunk`s if streaming). Strata's
default is `ChatOpenAI` (from `langchain_openai`) pointed at
LiteLLM's OpenAI-compatible endpoint.

---

## 1. `BaseChatModel` — the abstract base

`BaseChatModel` (in `langchain_core.language_models`) is the
abstract class all chat models inherit from. The relevant
subclasses Strata touches:

| Class | Module | Use |
|---|---|---|
| `ChatOpenAI` | `langchain_openai` | OpenAI, or any OpenAI-compatible endpoint (LiteLLM, vLLM, Ollama in OpenAI mode). **Strata's default.** |
| `ChatBedrock` | `langchain_aws` | Bedrock directly. **Not used by Strata** (we go through LiteLLM). |
| `ChatAnthropic` | `langchain_anthropic` | Anthropic directly. Not used. |
| `ChatOllama` | `langchain_ollama` | Local Ollama. Useful for offline dev. |
| `ChatVertexAI` | `langchain_google_vertexai` | GCP Vertex. Not used. |
| `FakeListChatModel` | `langchain_core.language_models.fake_chat_models` | Tests only. See `08-testing-and-pitfalls.md`. |

All of these expose the same `Runnable` interface (invoke,
stream, batch, ainvoke, astream, abatch). All support
`bind_tools`, `with_structured_output`, `with_retry`,
`with_fallbacks`.

---

## 2. `ChatOpenAI` pointed at LiteLLM

This is Strata's setup. The `base_url` argument redirects the
OpenAI SDK to LiteLLM.

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="nova-pro",                           # the LiteLLM model_list alias
    base_url="http://litellm:4000/v1",          # LiteLLM is OpenAI-compatible
    api_key=os.environ["LITELLM_API_KEY"],      # the master key in Phase 2
    temperature=0.2,
    max_tokens=2048,
    timeout=60,
    max_retries=2,
    streaming=True,
)
```

**Two things to internalize:**

1. **`model` is the alias from LiteLLM's `model_list`**, not the
   Bedrock model id. LiteLLM translates. See
   [`litellm.md`](../litellm.md#2-the-model_list-config).
2. **`base_url` must end in `/v1`.** The OpenAI SDK appends
   `/chat/completions` (or `/embeddings`) to whatever you pass.
   If you pass `http://litellm:4000` (no `/v1`), the SDK will
   call `http://litellm:4000/chat/completions` and LiteLLM
   returns 404.

### Common kwargs

| Kwarg | Type | Default | What |
|---|---|---|---|
| `model` | `str` | (required) | LiteLLM alias. |
| `temperature` | `float` | provider default | 0 = deterministic, 1 = creative. Strata uses 0.2. |
| `max_tokens` | `int` | provider default | Cap on output tokens. 2048 is fine for chat. |
| `timeout` | `float` | provider default | HTTP timeout in seconds. 60s handles most calls. |
| `max_retries` | `int` | `6` for OpenAI, varies | The SDK retries transient errors (429, 5xx). |
| `streaming` | `bool` | `False` | Whether `stream`/`astream` yield chunks. |
| `api_key` | `str` | env | Auth. |
| `base_url` | `str` | OpenAI's | Override. |
| `model_kwargs` | `dict` | `{}` | Pass through provider-specific args. |
| `tiktoken_model_name` | `str` | `model` | Which tokenizer to use for token counting (relevant for `trim_messages`). |

### Provider-specific params via `model_kwargs`

Anything the provider supports but LangChain doesn't abstract:

```python
model = ChatOpenAI(
    model="nova-pro",
    base_url="...",
    api_key="...",
    model_kwargs={
        "top_p": 0.9,
        "presence_penalty": 0.1,
        "extra_body": {"anthropic_version": "..."},   # passed through to Anthropic via LiteLLM
    },
)
```

Strata rarely needs this. The provider-specific knobs you care
about (`temperature`, `max_tokens`) have first-class kwargs.

---

## 3. `bind_tools` — exposing tools to the model

`bind_tools(tools)` returns a new `Runnable` that, when invoked,
emits `AIMessage`s with `tool_calls` populated. The `tools`
argument is a list of LangChain `BaseTool` objects — exactly
what `@tool` produces.

```python
from app.tools import (
    list_clusters, get_cluster_status, get_cluster_logs,
    provision_cluster, delete_cluster,
)

llm = ChatOpenAI(...).bind_tools([
    list_clusters, get_cluster_status, get_cluster_logs,
    provision_cluster, delete_cluster,
])

response = llm.invoke(messages)
# response is an AIMessage. If the model wants to call a tool,
# response.content == "" and response.tool_calls is non-empty.
```

### What the model sees

The model's API request includes a `tools` array. Each tool is
serialized to the provider's format. For OpenAI-compatible:

```json
{
  "type": "function",
  "function": {
    "name": "list_clusters",
    "description": "List all EKS clusters owned by the current user...",
    "parameters": {
      "type": "object",
      "properties": {},
      "required": []
    }
  }
}
```

`description` comes from the tool's **docstring** (first paragraph
or the whole thing depending on the parser). `parameters` comes
from the function's type annotations, parsed via Pydantic. See
`04-tools.md` for the full schema-generation story.

### `bind_tools` options

```python
llm.bind_tools(
    tools,
    *,
    tool_choice="auto",                # "auto" | "any" | "tool_name" | {"type": "function", "function": {"name": "list_clusters"}}
    strict=True,                       # OpenAI strict mode (structured args)
    parallel_tool_calls=True,          # allow the model to call multiple tools in one turn
    **kwargs,                          # passed to the provider
)
```

| `tool_choice` | Behavior |
|---|---|
| `"auto"` (default) | The model decides whether to call a tool. |
| `"any"` | The model must call at least one tool (any of them). |
| `"none"` | The model is not allowed to call a tool. |
| `"list_clusters"` | The model must call that specific tool. |
| `{"type": "function", "function": {"name": "list_clusters"}}` | Same as the string form. |

Strata's Phase 2 uses the default `"auto"`. Phase 6+ uses
`"any"` for the mutation-tool confirmation flow (force the
model to commit to a tool, then we route through confirmation).

### `strict=True` — OpenAI's structured-args mode

OpenAI supports a stricter tool schema where the model can only
emit arguments that match the schema exactly (no extra keys,
correct types, all required fields present). LiteLLM passes this
through for OpenAI. Bedrock via LiteLLM does not always honor it.

For Strata's mocked Phase 2 tools, you don't need this. For real
orchestrator calls in Phase 3+ where the args feed into a Pydantic
request body, this is worth enabling.

### `parallel_tool_calls`

`True` (default for OpenAI) lets the model emit multiple
`tool_calls` in one `AIMessage`. For example, "list my clusters
and get the status of the oldest one" might emit
`[list_clusters, get_cluster_status]` simultaneously. `ToolNode`
executes them all and emits N `ToolMessage`s in order.

For a phase-1 model, parallel calls are a free win. For a
phase-1 dev, they make tests harder to write (order matters).
Set `parallel_tool_calls=False` in tests if you need determinism.

---

## 4. `with_structured_output` — force the model to return a schema

If you don't want tool calls but want a typed response, use
`with_structured_output(schema)`. The model is forced to return
data matching the schema.

```python
from pydantic import BaseModel

class ClusterSummary(BaseModel):
    count: int
    oldest: str
    newest: str

structured = ChatOpenAI(...).with_structured_output(ClusterSummary)
result = structured.invoke("List my clusters and tell me about them.")
# result is a ClusterSummary instance, not an AIMessage
```

### Supported schemas

- A `TypedDict` (returns a dict)
- A Pydantic `BaseModel` (returns an instance)
- A JSON schema (returns a dict matching the schema)
- An `Enum` (returns an enum member)

### How it works under the hood

LangChain does one of:

1. **Tool calling** — converts the schema to a tool definition and
   uses `bind_tools` under the hood. Then parses the tool call's
   `args` field as the schema. (OpenAI, Anthropic, etc.)
2. **JSON mode** — sends a `response_format={"type": "json_object"}`
   parameter and instructs the model via prompt. Less reliable.
3. **Provider-native structured output** — OpenAI's
   `strict_tools`, Anthropic's tool use with input schema, etc.
   Highest reliability when available.

For Strata, `with_structured_output` is useful in two places:
- The RAG "did the docs answer this?" check (Phase 4+).
- The mutation-tool confirmation payload (Phase 6+) — the model
  returns a structured "what I'm about to do and why."

### `include_raw=True`

```python
structured = model.with_structured_output(ClusterSummary, include_raw=True)
result = structured.invoke(messages)
# result is {"raw": AIMessage, "parsed": ClusterSummary | None, "parsing_error": Exception | None}
```

`include_raw=True` is the diagnostic mode: it gives you the raw
`AIMessage` *and* the parsed result *and* any parse error. Use it
in tests and in early development; turn it off for production.

---

## 5. `with_retry` — automatic retries

```python
from langchain_core.runnables import RunnableConfig

model = ChatOpenAI(...).with_retry(
    stop_after_attempt=3,
    wait_exponential_jitter=True,
    exponential_jitter_params={"initial": 1, "max": 10},
    retry_if_exception_type=(openai.APITimeoutError, openai.RateLimitError),
)
```

The retry is on the `Runnable` level — it wraps `invoke` /
`ainvoke`. It does **not** re-run the node; from the graph's
perspective it's one call.

Strata mostly delegates retries to LiteLLM
(`router_settings.num_retries`). Adding `with_retry` on top is
double-counting. Use one or the other.

### When to use `with_retry` vs LiteLLM retries

- **Use LiteLLM retries** when you want a single place to
  configure retries for all models. Strata does this.
- **Use `with_retry`** when you want per-call control — e.g.
  one tool is HTTP-bound and should retry on
  `httpx.ConnectError`; another is CPU-bound and shouldn't
  retry at all.

---

## 6. `with_fallbacks` — graceful degradation

```python
primary = ChatOpenAI(model="nova-pro", base_url=..., api_key=...)
fallback = ChatOpenAI(model="claude-3-5-haiku", base_url=..., api_key=...)

model = primary.with_fallbacks([fallback])
```

If `primary.invoke(...)` raises, LangChain catches and tries
`fallback`. The caller never sees the failure (unless the
fallback also fails).

Strata's Phase 2 has one model in the LiteLLM `model_list`.
Phase 6+ adds a fallback in LiteLLM's `router_settings.fallbacks`.
**Don't** stack fallbacks on both layers.

### `with_fallbacks` with a list

```python
model = primary.with_fallbacks([fallback1, fallback2, fallback3])
```

Tries them in order. The first one that succeeds wins.

### `exceptions_to_handle`

```python
model = primary.with_fallbacks(
    [fallback],
    exceptions_to_handle=(openai.RateLimitError,),
)
```

By default, all exceptions trigger fallback. You can narrow.

---

## 7. `configurable_fields` and `configurable_alternatives`

The "swap the model at runtime" feature.

```python
from langchain_core.runnables import ConfigurableField

model = ChatOpenAI(
    model="nova-pro",
    base_url=...,
    api_key=...,
).configurable_fields(
    model=ConfigurableField(id="model_name"),
)

# At call time:
result = model.with_config(configurable={"model_name": "claude-3-5-haiku"}).invoke(messages)
```

`configurable_alternatives` swaps the whole model:

```python
from langchain_core.runnables import ConfigurableAlternatives

model = ChatOpenAI(...).configurable_alternatives(
    ConfigurableField(id="llm"),
    default_key="nova-pro",
    haiku=ChatOpenAI(model="claude-3-5-haiku", base_url=..., api_key=...),
    opus=ChatAnthropic(model="claude-3-opus", ...),
)

# At call time:
result = model.with_config(configurable={"llm": "haiku"}).invoke(messages)
```

Strata does not use this in Phase 2. The `model_list` in
LiteLLM is the runtime swap point. But this is the right tool
if you want per-user model choice without rebuilding the
Deployment.

### Where `configurable` lives

The `config` dict you pass to `graph.invoke(input, config=...)`
threads through every `Runnable` and into the checkpointer and
the tools. The `configurable` key is the namespace for
"things that get looked up at runtime" — model choice, thread
id, prompt variants.

---

## 8. Streaming — `stream` / `astream` / `astream_events`

### `stream` (sync) and `astream` (async)

```python
for chunk in model.stream(messages):
    print(chunk.content, end="", flush=True)
```

`chunk` is an `AIMessageChunk`. `chunk.content` is a string
delta. `chunk.tool_call_chunks` is a list of partial tool-call
deltas.

Requires `streaming=True` on the model constructor (or as a kwarg
per call — `model.invoke(messages, stream=True)` works for some
providers).

### `astream_events` — full event stream

`astream_events(version="v2")` is the **observability-grade**
streaming API. It yields lifecycle events from every component
involved in the call: the chat model, the prompt, the parser,
callbacks, and (in a graph) every node.

```python
async for event in model.astream_events(messages, version="v2"):
    if event["event"] == "on_chat_model_stream":
        print(event["data"]["chunk"].content, end="")
    elif event["event"] == "on_chat_model_end":
        print("\n[done]", event["data"]["output"].usage_metadata)
```

### Event types you'll see

| Event | When | `data` keys |
|---|---|---|
| `on_chat_model_start` | Model call begins. | `input` (messages). |
| `on_chat_model_stream` | A chunk arrived. | `chunk` (AIMessageChunk). |
| `on_chat_model_end` | Model call done. | `output` (AIMessage), `input`. |
| `on_tool_start` | A tool invocation begins. | `input` (the args). |
| `on_tool_end` | A tool call completes. | `output` (the result). |
| `on_chain_start` / `on_chain_end` | A RunnableSequence starts/ends. | `input` / `output`. |
| `on_prompt_start` / `on_prompt_end` | A prompt template ran. | |
| `on_retriever_start` / `on_retriever_end` | A retriever ran. | |
| `on_parser_start` / `on_parser_end` | An output parser ran. | |
| `on_llm_start` / `on_llm_end` | Legacy (non-chat models). | |
| `on_custom_event` | Your code emitted a custom event. | |
| `on_error` | Something errored. | `error`. |

The events come from **all** nested components. A graph run can
emit thousands of events. Filter with `tags` and `name`:

```python
async for event in graph.astream_events(
    input, config, version="v2",
    include_names=["call_model"],   # only events from this node
    include_types=["chat_model"],   # only chat-model events
    include_tags=["prod"],
    exclude_tags=["debug"],
):
    ...
```

### Mapping events to NDJSON (Strata's Phase 2 wire format)

The `app/main.py` in Phase 2 walks the graph's final state, but
Phase 5+ maps events to NDJSON:

```python
async def stream_chat(input_state: AgentState):
    async for event in graph.astream_events(
        input_state, config={"configurable": {"thread_id": "user-42"}},
        version="v2",
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
    yield ndjson({"type": "done"})
```

The mapping from `astream_events` to NDJSON is the cleanest way
to power the chat UI without coupling the UI to LangChain's
internal event names. The full coverage is in
`../langgraph/07-streaming.md`.

---

## 9. `usage_metadata` and cost

`AIMessage.usage_metadata` is set automatically by the model
provider. To compute cost per request, sum the token counts and
multiply by a per-model rate:

```python
def cost_of(response: AIMessage) -> float:
    u = response.usage_metadata or {}
    input_t = u.get("input_tokens", 0)
    output_t = u.get("output_tokens", 0)
    # Nova Pro: $0.0008 / 1k input, $0.0032 / 1k output (as of 2026)
    return (input_t / 1000) * 0.0008 + (output_t / 1000) * 0.0032
```

For a per-conversation cost, sum across all `AIMessage`s in the
state.

**Strata:** Phase 2 doesn't track cost. Phase 5+ adds a callback
that appends cost to a Postgres `usage` table.

### Bedrock-specific: cache tokens

Bedrock supports prompt caching. When the model reads from its
cache, the usage metadata includes:

```python
response.usage_metadata = {
    "input_tokens": 100,
    "output_tokens": 20,
    "input_token_details": {
        "cache_read": 80,         # from cache
        "cache_creation": 0,      # newly cached
    },
}
```

The `cache_read` tokens are 90% cheaper (as of Nova Pro pricing).
You don't need to do anything to use Bedrock caching — Bedrock
caches the prefix automatically — but tracking
`input_token_details.cache_read` lets you verify the cache is
hitting.

---

## 10. Strata's model config, end-to-end

The full chain for a `POST /chat` call:

```
app/main.py
    └─ graph.ainvoke({"messages": [HumanMessage(...)]}, config)
        └─ call_model node
            └─ ChatOpenAI(model="nova-pro", base_url="http://litellm:4000/v1", api_key=..., streaming=True)
                .bind_tools(tools)
                .invoke(messages)
                    └─ httpx POST to http://litellm:4000/v1/chat/completions
                        └─ LiteLLM routes to bedrock/amazon.nova-pro-v1:0
                            └─ AWS Bedrock
                                └─ AIMessage
                            └─ translated to OpenAI format
                        └─ returns to agent-service
                    └─ AIMessage with tool_calls
                └─ ToolNode processes tool_calls
                    └─ @tool .invoke(args)
                        └─ mocked return (Phase 2)
                    └─ ToolMessage(tool_call_id=...)
                └─ add_messages appends
            └─ loop until no more tool_calls
        └─ END
    └─ returns final state
```

Every layer is replaceable:

- Swap `ChatOpenAI` for `ChatAnthropic` if LiteLLM is broken for
  OpenAI compatibility on some provider.
- Swap `base_url` to point at vLLM instead of LiteLLM.
- Swap `model` to a different LiteLLM alias to use a different
  provider.

That's the point of the proxy.

---

## 11. Common pitfalls

1. **`base_url` must end in `/v1`**, not `/chat/completions`.
   LiteLLM expects the full OpenAI-compat surface at `/v1`.
2. **`api_key` is required** even if you don't set a master key
   on LiteLLM. `ChatOpenAI` will error without one. Use
   `api_key="sk-no-auth"` if you disable auth.
3. **The model name is the LiteLLM alias**, not the provider-prefixed
   id. Pass `"nova-pro"`, not `"bedrock/amazon.nova-pro-v1:0"`.
4. **`bind_tools` is on the bound `Runnable`**, not on
   `ChatOpenAI` itself. The pattern is
   `llm.bind_tools(tools).invoke(messages)`. Calling
   `ChatOpenAI.bind_tools(...)` directly works (it's a class
   method on the parent), but the resulting runnable ignores
   the constructor args — bug.
5. **`parallel_tool_calls` is on by default for OpenAI.** The
   model may emit two `tool_calls` in one `AIMessage`. Your
   tool code must handle being called twice in one node.
6. **`with_structured_output` swallows the `AIMessage`.** If you
   need the model's reasoning text, use `include_raw=True`.
7. **`max_retries=2` (constructor) + LiteLLM retries** is
   double-counting. Pick one.
8. **`temperature=0` does not make the model deterministic** for
   all providers. Some have non-zero minimums at certain model
   versions. Read the provider's notes.
9. **`stop` sequences are passed via `model_kwargs` or
   `bind(stop=[...])`.** They are not a first-class kwarg.
10. **Bedrock's `count_tokens` is not a chat model method.** To
    get token counts for trimming, use the model itself or
    `tiktoken` for OpenAI-shaped counting.

---

## 12. What to read next

- `04-tools.md` — what `@tool` actually generates and what the
  model sees.
- `05-prompts-and-parsers.md` — `ChatPromptTemplate`,
  `MessagesPlaceholder`, output parsers.
- `06-runnables-and-streaming.md` — the full `Runnable` surface,
  `astream_events` deep dive.
- `../litellm.md` — the model list, embeddings, retries.
- `../bedrock.md` — what's behind LiteLLM in Strata's default
  config.
- LangChain chat models: <https://python.langchain.com/docs/concepts/chat_models/>
