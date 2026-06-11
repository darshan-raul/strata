# LangChain — Messages

> **Part 2 of the LangChain deep-dive.** Messages are the atom of
> the agent loop. Every chat-model call is "send these messages,
> get back a new message." Read this carefully.

The whole point of `langchain_core.messages` is to give the
ecosystem **a single, typed shape** for "a thing in a
conversation." The model sees a list of these. The model returns
one of these. Tools return values that get wrapped in one of these.

---

## 1. The five message types

```python
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    AIMessageChunk,
    ToolMessage,
    ToolCall,                  # typed dict, not a Message
    ToolCallChunk,             # streaming variant
    RemoveMessage,             # for explicit deletion
    FunctionMessage,           # LEGACY — do not use
)
```

| Type | Who produces it | What it carries |
|---|---|---|
| `SystemMessage` | the developer | behavior instructions, persona, hard rules |
| `HumanMessage` | the user | the prompt (or a multi-modal payload) |
| `AIMessage` | the model | text content + `tool_calls` + usage metadata |
| `ToolMessage` | a tool | the result of a tool call, keyed by `tool_call_id` |
| `RemoveMessage` | you (or the framework) | says "delete the message with this id from state" |

The model never sees a `ToolMessage` without a preceding
`AIMessage` that requested it. If it does, the model will get
confused or refuse. LangGraph's `ToolNode` enforces this for you.
If you ever build the state by hand, respect the alternation:

```
HumanMessage → AIMessage → ToolMessage → AIMessage → ToolMessage → AIMessage
```

There is no `AssistantMessage` — it's `AIMessage`. The
`FunctionMessage` is the pre-tool-calls era; use `ToolMessage`
instead. LangChain still exports it for backward compat.

---

## 2. Anatomy of a `SystemMessage`

The system message is the only one you, the developer, author
freely. It shapes the model's behavior.

```python
from langchain_core.messages import SystemMessage

sys = SystemMessage(content="You are Strata, an EKS ops copilot. "
                            "Always call list_clusters before answering "
                            "questions about clusters.")
```

What the model sees:

```json
{
  "role": "system",
  "content": "You are Strata, an EKS ops copilot. ..."
}
```

**Strata's Phase 2 pattern:** a literal `SystemMessage` constructed
once in `graph.py` and prepended to the user message on every
turn. Don't template it from a `ChatPromptTemplate` until you have
variables that change (per-user instructions, per-cluster context,
etc.) — that lands in Phase 5+.

**Common pattern for RAG:** inject retrieved context as a system
message, *not* a human message, so the model treats it as
instructions, not user input.

```python
return {
  "messages": [
    SystemMessage(content=f"Use these docs to answer:\n\n{docs}"),
    # ... existing conversation ...
  ]
}
```

---

## 3. Anatomy of a `HumanMessage`

```python
from langchain_core.messages import HumanMessage

HumanMessage(content="list my clusters")
```

**The `id` field.** Every message has an `id`. The
`add_messages` reducer uses it to deduplicate. By default,
LangChain assigns a UUID when you construct the message, but you
can override:

```python
HumanMessage(content="...", id="user-msg-1")
```

Why you'd set it explicitly: you're replaying a logged
conversation and want the IDs to match. Or you're restoring from
a database and want stable IDs.

**Multi-modal content.** The `content` field is typed as `str |
list[content blocks]`. For images:

```python
HumanMessage(content=[
    {"type": "text", "text": "What's in this screenshot?"},
    {"type": "image_url", "image_url": {"url": "https://..."}},
])
```

This is the OpenAI multimodal format. Bedrock via LiteLLM
translates it. Strata does not use multi-modal in Phase 2, but
the schema is here for Phase 6+ (EKS dashboard screenshots, log
diagrams).

**`example=True`.** Marks this message as a few-shot example.
The model treats it as part of the prompt, not the live
conversation. Used with `with_structured_output` for
structured-output few-shotting.

---

## 4. Anatomy of an `AIMessage` — the big one

`AIMessage` is what the model returns. It carries:

| Field | Type | What |
|---|---|---|
| `content` | `str \| list[content blocks]` | The model's text response. May be empty if the model only called tools. |
| `tool_calls` | `list[ToolCall]` | Structured tool-call requests. Empty list if no tools called. |
| `invalid_tool_calls` | `list[InvalidToolCall]` | Tool calls the model tried to make but that failed parsing. Strata doesn't see these in normal flow; `bind_tools` filters them. |
| `id` | `str` | Correlation id. |
| `name` | `str \| None` | Optional: custom name for the message (e.g. "assistant_with_tools"). |
| `usage_metadata` | `UsageMetadata` | Token counts (input, output, total) — populated when the API returns them. |
| `response_metadata` | `dict` | Provider-specific response metadata (model id, finish reason, logprobs, etc.). |
| `additional_kwargs` | `dict` | Provider-specific extras you can pass to the model. |

Example after the model decides to call a tool:

```python
AIMessage(
    content="",
    tool_calls=[
        ToolCall(
            name="list_clusters",
            args={},
            id="call-abc123",
        ),
    ],
    usage_metadata={"input_tokens": 87, "output_tokens": 12, "total_tokens": 99},
    response_metadata={"model_name": "amazon.nova-pro-v1:0", "finish_reason": "tool_calls"},
)
```

### The `id` is a correlation key — pay attention

The model issues a `tool_call_id` (e.g. `call-abc123`). The
`ToolMessage` you build in response **must** carry that same id:

```python
ToolMessage(
    content='[{"id": "cl-001", ...}]',
    name="list_clusters",
    tool_call_id="call-abc123",   # must match
)
```

If the ids don't match, the model has no way to know which
tool call the result answers. LangGraph's `ToolNode` does this
for you. If you ever build `ToolMessage`s by hand, double-check.

### `tool_calls` vs `content`

The model can do both at once: emit text *and* call tools. Some
providers do this; some don't. Nova Pro usually emits
`content=""` and only fills `tool_calls`. Anthropic models
sometimes narrate ("Let me check your clusters...") then call.

If you stream and the model is doing both, you'll see `content`
chunks interleaved with `tool_call_chunks`. Accumulate them
separately.

### `usage_metadata` — the cost story

Most providers return token counts. LangChain normalizes:

```python
AIMessage.usage_metadata = {
    "input_tokens": 87,
    "output_tokens": 12,
    "total_tokens": 99,
    "input_token_details": {"cache_read": 0, "cache_creation": 0},  # newer providers
}
```

You can sum across an entire conversation to compute cost. Strata
defers per-request cost tracking to Phase 5+; the metadata is
already in the message.

### `response_metadata` — provider-specific

`response_metadata` is the dump-everything-the-provider-returned
bag. Common keys:

- `model_name` — the actual model id, not the alias
- `finish_reason` — `stop`, `length`, `tool_calls`, `content_filter`
- `system_fingerprint` (OpenAI)
- `logprobs` (when requested)

You can use `finish_reason == "length"` to detect truncated
responses and trigger a retry with a longer budget.

### `additional_kwargs` — sending extras

Pass provider-specific params that LangChain doesn't abstract:

```python
AIMessage(
    content="...",
    additional_kwargs={"tools": [{"google_search": {}}]},   # Gemini-style
)
```

Or send a request with them:

```python
model.invoke(messages, additional_kwargs={"top_k": 50})
```

For Strata, you almost never need this — the parameters you care
about (`temperature`, `max_tokens`, `top_p`) have first-class
kwargs on `ChatOpenAI`.

---

## 5. `AIMessageChunk` — streaming

When you call a model with `streaming=True`, you get back an
iterator of `AIMessageChunk` objects. Each chunk has the same
shape as `AIMessage` but only carries the **delta** for that
chunk.

```python
model = ChatOpenAI(..., streaming=True)
for chunk in model.stream(messages):
    print(chunk.content, end="", flush=True)
```

`chunk.content` is a `str` (or empty). `chunk.tool_call_chunks`
is a list of partial tool-call deltas — they may arrive over
several chunks. To reconstruct the full `AIMessage`, accumulate:

```python
full: AIMessage | None = None
for chunk in model.stream(messages):
    full = chunk if full is None else full + chunk
# full is now the complete AIMessage
```

The `+` operator on `AIMessage` and `AIMessageChunk` is
overloaded to merge them.

**In a graph**, you don't do this manually. `astream(stream_mode="messages")`
yields `(message_chunk, metadata)` tuples and LangGraph handles
the accumulation if you ask for `stream_mode="values"`.

---

## 6. Anatomy of a `ToolMessage`

```python
from langchain_core.messages import ToolMessage

ToolMessage(
    content='[{"id": "cl-001", "name": "demo", "status": "READY"}]',
    name="list_clusters",
    tool_call_id="call-abc123",
)
```

Three required fields, two optional:

| Field | Type | What |
|---|---|---|
| `content` | `str` | **Always a string.** The model's only view of the result. |
| `name` | `str` | The tool name (for the model's benefit; doesn't have to match the actual tool's name). |
| `tool_call_id` | `str` | Correlation id. Must match an `AIMessage.tool_calls[i].id`. |
| `tool_call_id` ... wait, that's the same | | |
| `status` | `str` (default `"success"`) | "success" or "error". Affects how the model interprets it. |
| `artifact` | `Any` | A non-string payload (e.g. a DataFrame, an image) for downstream use. The model doesn't see it. |

### `content` is always a string

The single most common bug in agent code:

```python
# WRONG — model will see the repr, not the data
ToolMessage(content=[{"id": "cl-001"}], ...)

# RIGHT
ToolMessage(content=json.dumps([{"id": "cl-001"}]), ...)

# ALSO RIGHT (Pydantic v2)
ToolMessage(content=ClusterList.model_validate(rows).model_dump_json(), ...)
```

If your tool returns a Pydantic model directly, LangChain's
`StructuredTool.invoke` calls `model_dump_json()` on the return
value. But if you build the `ToolMessage` by hand (e.g. in a
custom `ToolNode`-like wrapper), **you** must serialize.

### `status="error"` — telling the model something went wrong

```python
ToolMessage(
    content="Cluster cl-001 not found.",
    name="get_cluster_status",
    tool_call_id="call-abc123",
    status="error",
)
```

The model sees the error and can react. Use this instead of
raising — raising kills the graph run, erroring-in-content keeps
the agent loop alive.

### `artifact` — bypassing the model's view

The model only reads `content` (string). For data the model
*shouldn't* see (large blobs, images) but that downstream code
needs:

```python
ToolMessage(
    content="Image returned (1024x768).",
    name="get_screenshot",
    tool_call_id="call-xyz",
    artifact=PILImage.open(...),   # available to your code, not the model
)
```

Strata doesn't use this in Phase 2. The pattern is useful for
"return a chart the UI will render, not the data the model
parses."

---

## 7. `RemoveMessage` — explicit deletion

In a stateful graph, the message list grows forever. To prune,
append a `RemoveMessage`:

```python
from langgraph.graph.message import RemoveMessage

def trim(state):
    # keep only the last 10 messages
    msgs = state["messages"]
    return {"messages": [RemoveMessage(id=m.id) for m in msgs[:-10]]}
```

The `add_messages` reducer honors `RemoveMessage` and deletes
matching ids.

**Strata's approach:** when using a checkpointer, use `trim_messages`
from `langchain_core.messages` rather than `RemoveMessage` —
it's a one-shot helper:

```python
from langchain_core.messages import trim_messages

trimmed = trim_messages(
    messages,
    max_tokens=4000,
    token_counter=model,   # uses the model's tokenizer
    strategy="last",
)
```

`strategy="last"` keeps the most recent N tokens. `strategy="first"`
keeps the oldest. Use `start_on="human"` to always start with a
`HumanMessage` (you never want to send an `AIMessage` as the
first message to a model).

---

## 8. `FunctionMessage` — legacy, do not use

Pre-2024 LangChain had `HumanMessage`, `AIMessage`, and
`FunctionMessage`. Then OpenAI introduced "tools" and the world
moved. The mapping:

- Old `function_call` field on `AIMessage` → new `tool_calls` field.
- Old `FunctionMessage` (the result) → new `ToolMessage`.

LangChain still exports `FunctionMessage` for back-compat with
OpenAI's `function_call` API and older agents. **Do not use it.**
If you see it in a tutorial, the tutorial is old.

---

## 9. The message lifecycle in Strata

A single `POST /chat` call in Phase 2 walks these steps:

```
1. Receive {"message": "list my clusters"}.
2. Build initial state:
     {"messages": [
         SystemMessage(content=SYSTEM_PROMPT),
         HumanMessage(content="list my clusters"),
     ]}
3. Graph node `call_model`:
     response = llm.bind_tools(tools).invoke(state["messages"])
   → AIMessage(content="", tool_calls=[list_clusters])
4. add_messages reducer appends the AIMessage.
5. Conditional edge → ToolNode.
6. ToolNode invokes list_clusters, gets [{"id": "cl-001", ...}].
7. ToolNode builds:
     ToolMessage(content='[{"id": "cl-001", ...}]',
                name="list_clusters",
                tool_call_id="<from step 3>")
8. add_messages appends the ToolMessage.
9. Conditional edge → call_model (loop).
10. call_model sees the tool result, emits a final AIMessage
    with content="You have 3 clusters: ..."
11. add_messages appends.
12. Conditional edge → END.
13. app/main.py walks state["messages"], emits NDJSON.
```

`add_messages` is the only thing touching the message list. You
never `state["messages"].append(...)` by hand.

---

## 10. How Strata uses this

**Today (Phase 2):** All five message types in this doc are
emitted by the graph. The `id` field is set by LangChain
automatically; you never construct it. `usage_metadata` is
populated by the model response; we don't act on it yet but it's
there. `RemoveMessage` is unused (no checkpointer, so no
accumulation).

**Phase 4+:** RAG injects retrieved docs as a `SystemMessage`
before `call_model`. The `retrieve` node builds the system
message and returns a partial state update.

**Phase 6+:** With a checkpointer, the message list can grow
arbitrarily. Use `trim_messages` before sending to the model.
Add a `MemoryStore` to read prior facts and inject them as a
`SystemMessage`. See `langgraph/09-memory-store.md`.

---

## 11. Common pitfalls

1. **`ToolMessage.content` must be a string.** Pydantic models,
   dicts, lists — all must be `model_dump_json()` /
   `json.dumps()` / `str()` first.
2. **Mismatched `tool_call_id`.** If the `ToolMessage`'s id
   doesn't match an `AIMessage.tool_calls[i].id`, the model has
   no correlation and the conversation breaks. `ToolNode` gets
   this right; if you write your own, you must.
3. **Mutating `state["messages"]` in place.** Don't. The
   framework owns the state object. Always return a partial
   update.
4. **Sending `AIMessage(content="", tool_calls=[...])` to the
   model as input.** The model handles it, but if you build
   state by hand, double-check the alternation invariant.
5. **Forgetting `id` on streamed messages.** When you
   accumulate `AIMessageChunk`s, the resulting `AIMessage` has
   an id (from the first chunk). If the chunks don't carry ids,
   the merged message gets a fresh one and downstream correlation
   breaks.
6. **`content=[]` vs `content=""` for tool-only `AIMessage`.**
   Both are legal. Nova Pro and OpenAI both return `""` by
   convention. Some old code uses `[]`.
7. **Treating `FunctionMessage` as the result type.** Legacy.
   Use `ToolMessage`.

---

## 12. What to read next

- `03-chat-models.md` — the model layer, including how `bind_tools`
  produces `AIMessage.tool_calls`.
- `04-tools.md` — building tools that return values that become
  `ToolMessage.content`.
- `../langgraph/02-state-and-reducers.md` — `add_messages` and
  how the framework handles the list.
- LangChain messages API: <https://api.python.langchain.com/en/stable/messages.html>
