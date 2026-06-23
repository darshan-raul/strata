# LangGraph — Streaming

> **Part 7 of the LangGraph deep-dive.** All the `stream_mode`
> values (`values`, `updates`, `messages`, `events`, `custom`,
> `debug`), how to map graph events to Strata's NDJSON wire
> format and to SSE, subgraph streaming with `subgraphs=True`.

Streaming is how a chat UI sees tokens as they arrive. LangGraph
has multiple streaming modes, each emitting a different shape.
This file covers all of them, plus the mapping to Strata's wire
formats.

---

## 1. The streaming API

The compiled graph has:

```python
graph.stream(input, config, **kwargs)              # sync
graph.astream(input, config, **kwargs)             # async
graph.stream_events(input, config, version="v2")   # legacy
graph.astream_events(input, config, version="v2")  # the right one
```

`stream` / `astream` take a `stream_mode` kwarg. `astream_events`
is a different (more powerful) API. Both are useful.

---

## 2. `stream_mode="values"` — full state after each node

```python
for state in graph.stream(input, stream_mode="values"):
    print(state["messages"][-1])
```

Yields the **full merged state** after each node completes.
The final yield is the final state.

```python
# Example:
# 1. After START → call_model:  {"messages": [Human, AIMessage(tool_call)]}
# 2. After call_model → tools:  {"messages": [Human, AIMessage(tool_call), ToolMessage]}
# 3. After tools → call_model:  {"messages": [Human, AIMessage(tool_call), ToolMessage, AIMessage(answer)]}
# 4. END:                       {"messages": [Human, AIMessage(tool_call), ToolMessage, AIMessage(answer)]}
```

The shape: each yield is a dict matching the state schema. The
`messages` field is the full list so far.

### When to use

"Show me the full state after every node." Useful for
debugging, less useful for the chat UI (the UI wants tokens,
not full states).

---

## 3. `stream_mode="updates"` — partial updates per node

```python
for update in graph.stream(input, stream_mode="updates"):
    print(update)
```

Yields the **partial update** that each node returned. Most
useful for "what did each node produce?"

```python
# Example:
# {"call_model": {"messages": [AIMessage(tool_call)]}}
# {"tools":      {"messages": [ToolMessage]}}
# {"call_model": {"messages": [AIMessage(answer)]}}
```

The outer key is the **node name**. The inner value is the
partial update. If a node returned nothing (empty dict), it's
not yielded.

### When to use

Debugging ("did the call_model node produce the right
AIMessage?"). Tool-call tracking ("show me the tool result as
soon as it arrives"). Less useful for the chat UI (no token
streaming).

---

## 4. `stream_mode="messages"` — `AIMessageChunk` per chunk

```python
async for message_chunk, metadata in graph.astream(input, stream_mode="messages"):
    print(message_chunk.content, end="")
```

Yields `(message_chunk, metadata)` tuples. `message_chunk` is
an `AIMessageChunk` (from streaming the model). `metadata` is
a dict with the source node name, run id, etc.

```python
# Example:
# (AIMessageChunk(content="You"), {"langgraph_node": "call_model", "ls_provider": "openai", ...})
# (AIMessageChunk(content=" have"), {"langgraph_node": "call_model", ...})
# (AIMessageChunk(content=" 3"), {"langgraph_node": "call_model", ...})
# ...
# (AIMessageChunk(content=""), tool_call_chunks=[...], {"langgraph_node": "call_model", ...})
```

This is the **chat-UI mode**. The UI gets tokens as the model
emits them. The metadata tells you which node produced the
chunk (always `call_model` for tokens, but useful for
filtering).

### Streaming with the tool-call loop

The "messages" mode streams **all** messages, not just the
final answer's. During the tool-call loop, the model might
emit a chunk that includes a `tool_call_chunks` field. The
UI should accumulate these and only display text content.

```python
full_ai_message = None
async for chunk, metadata in graph.astream(input, stream_mode="messages"):
    if full_ai_message is None:
        full_ai_message = chunk
    else:
        full_ai_message = full_ai_message + chunk
    
    if chunk.content:
        await websocket.send(chunk.content)
    if chunk.tool_call_chunks:
        # The model is calling a tool; don't display text.
        # Show "calling tool X..." in the UI instead.
        pass
```

`AIMessageChunk + AIMessageChunk` accumulates via the
overloaded `+` operator.

---

## 5. `stream_mode="events"` — fine-grained lifecycle

```python
async for event in graph.astream_events(input, config, version="v2"):
    print(event)
```

`astream_events` is the **observability API**. Yields lifecycle
events from every component. See
[`../langchain/06-runnables-and-streaming.md`](../langchain/06-runnables-and-streaming.md#5-astream_events--the-full-event-stream)
for the full event taxonomy.

In a graph, you get events from:

- The graph itself (`on_chain_start`, `on_chain_end`).
- Each node that runs (`on_chain_start` with the node name).
- The chat model inside `call_model` (`on_chat_model_start`,
  `on_chat_model_stream`, `on_chat_model_end`).
- The tools inside `ToolNode` (`on_tool_start`, `on_tool_end`).
- Anything else (retrievers, parsers, prompts).

This is the most powerful streaming API. Use it to drive a
real-time UI that shows tokens, tool calls, tool results, and
node transitions.

---

## 6. `stream_mode="custom"` — `get_stream_writer` events

```python
async for event in graph.astream(input, stream_mode="custom"):
    print(event)
```

Yields events emitted by `get_stream_writer()` from inside a
node:

```python
from langgraph.config import get_stream_writer

def my_node(state):
    writer = get_stream_writer()
    writer({"event": "validation_failed", "details": "..."})
    return state
```

Use this for application-level signals ("validation failed",
"rate limit hit", "I started a background job") that aren't
covered by the model's tool events.

### Multiple writers per node

```python
def my_node(state):
    writer = get_stream_writer()
    writer({"step": 1})
    do_thing()
    writer({"step": 2})
    return state
```

Each `writer(...)` call emits one event. The stream is
ordered: step 1, then step 2.

### `custom` mode vs. `astream_events`

`custom` mode is a simpler surface. Use it when you want a
clean stream of "things the node is telling me" without the
full event taxonomy.

`astream_events` is for when you want everything (model
events, tool events, node events, custom events).

---

## 7. `stream_mode="debug"` — max verbosity

```python
async for event in graph.astream(input, stream_mode="debug"):
    print(event)
```

`debug` mode emits a `DebugEvent` per step with:
- The current state.
- The next node.
- The checkpoint info.
- The events.

Use it for low-level debugging when other modes don't tell
you enough. It's noisy; not for production.

---

## 8. Multiple `stream_mode` at once

```python
async for event in graph.astream(
    input, config, stream_mode=["values", "messages"]
):
    print(event)
```

`stream_mode` accepts a list. Each yield is a `(mode, value)`
tuple:

```python
("values", state_dict)
("messages", (chunk, metadata))
("values", state_dict)
("messages", (chunk, metadata))
```

Useful for "I want both the full state (for `values` mode)
and the per-token chunks (for `messages` mode)."

The events are interleaved as they occur. The order is
deterministic but not guaranteed to be strictly grouped by
mode.

---

## 9. Filtering events

For `astream_events`:

```python
async for event in graph.astream_events(
    input, config, version="v2",
    include_names=["call_model"],
    include_types=["chat_model", "tool"],
    exclude_tags=["debug"],
):
    ...
```

| Param | What |
|---|---|
| `include_names` | Only events from this node / runnable. |
| `include_types` | Only events of this type ("chat_model", "tool", "chain", "retriever", "parser", "prompt"). |
| `include_tags` | Only events tagged with these. |
| `exclude_*` | The same, but exclusion. |

Filter aggressively. A single graph run can emit thousands of
events. UI code wants only the chat model and tool events.

### `subgraphs=True` — include subgraph events

```python
async for event in graph.astream_events(
    input, config, version="v2", subgraphs=True,
):
    # Subgraph events have a parent_run_id matching the subgraph node.
    ...
```

`subgraphs=True` surfaces events from inside subgraphs. The
`parent_ids` field on each event traces the hierarchy.

---

## 10. Mapping to Strata's NDJSON wire format

Strata's Phase 2 wire format is one JSON object per line:

```json
{"type": "token", "text": "..."}
{"type": "tool_call", "name": "...", "args": {}}
{"type": "tool_result", "name": "...", "result": ...}
{"type": "done"}
```

The mapping from `astream_events` to NDJSON:

```python
async def stream_chat_to_ndjson(graph, input_state, config):
    yield ndjson({"type": "start"})

    async for event in graph.astream_events(
        input_state, config, version="v2",
        include_types=["chat_model", "tool"],
    ):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            text = event["data"]["chunk"].content
            if text:
                yield ndjson({"type": "token", "text": text})
        elif kind == "on_chat_model_end":
            # Optional: include usage in the stream
            u = event["data"]["output"].usage_metadata or {}
            yield ndjson({
                "type": "usage",
                "input_tokens": u.get("input_tokens", 0),
                "output_tokens": u.get("output_tokens", 0),
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

The CLI consumes this stream line by line. The web UI (Phase 5+)
consumes it via fetch + ReadableStream.

---

## 11. Mapping to SSE (Phase 5+ web UI)

The Next.js web UI in Phase 5+ uses Server-Sent Events. The
mapping is similar to NDJSON, but each event is `data: <json>\n\n`:

```python
async def stream_chat_to_sse(graph, input_state, config):
    yield f"data: {json.dumps({'type': 'start'})}\n\n"

    async for event in graph.astream_events(
        input_state, config, version="v2",
        include_types=["chat_model", "tool"],
    ):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            text = event["data"]["chunk"].content
            if text:
                yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
        # ... etc ...

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
```

The FastAPI handler returns `StreamingResponse(stream_chat_to_sse(...), media_type="text/event-stream")`.

### Why SSE for the web, NDJSON for the CLI

- **SSE** is the browser-native event-stream format. `EventSource`
  consumes it directly.
- **NDJSON** is the easiest to consume from `curl` or a CLI.
  The Typer CLI in Phase 5+ reads NDJSON line by line.

The mapping is the same; only the framing differs.

---

## 12. The `get_stream_writer` pattern

```python
from langgraph.config import get_stream_writer

def my_node(state):
    writer = get_stream_writer()
    writer({"phase": "starting"})
    # ... work ...
    writer({"phase": "validation", "result": "ok"})
    return state
```

The writer is available inside any node. The events go to
whichever stream mode the caller is using (`custom` for pure
custom, `events` for everything).

In the `astream_events` API, the writer's events come through
as `on_custom_event` events.

---

## 13. Streaming during interrupts

If the graph hits an `interrupt()`, the stream ends with
`__interrupt__` data:

```python
async for event in graph.astream_events(input, config, version="v2"):
    if event["event"] == "__interrupt__":
        # The graph paused. Show the user a prompt.
        prompt = event["value"]
        ...
```

For Strata's Phase 6 confirmation flow, the CLI sees
`__interrupt__` and shows the user the prompt. The user
responds, and a separate `graph.invoke(Command(resume=...))`
resumes. The new invocation streams the rest.

---

## 14. Common pitfalls

1. **`astream_events` requires `version="v2"`.** Omitting it
   defaults to the legacy `"v1"` API, which is being removed.
2. **`stream_mode="messages"` only works with `astream`**,
   not `stream`. Sync version doesn't yield chunks.
3. **Filtering by `include_types` is a substring match.**
   `"chain"` matches `"chat_model_chain"`. Be specific.
4. **The `messages` mode emits all messages, not just the
   final answer.** During the tool-call loop, you see chunks
   for the tool-call AIMessage. Filter by `metadata["langgraph_node"]`
   or accumulate chunks via `+`.
5. **`stream_mode="debug"` is noisy** and includes every
   internal step. Don't use it in production.
6. **`subgraphs=True` on a deep graph** emits events from
   every nested level. Filter carefully.
7. **NDJSON framing** — the server flushes after each line.
   The CLI expects exactly one JSON object per line. Don't
   add newlines in the middle.
8. **SSE framing** — each event is `data: <json>\n\n`. The
   `\n\n` is required (separates events).
9. **`get_stream_writer` is None outside a graph run.** If
   you call it from a non-node context, you get `None`.
   Always call it from inside a node.
10. **The stream ends with `done`, not with the final
    state.** Make sure your consumer handles the `done` event
    distinctly (it might want to update the conversation
    list, scroll to bottom, etc.).

---

## 15. What to read next

- [`../langchain/06-runnables-and-streaming.md`](../langchain/06-runnables-and-streaming.md#5-astream_events--the-full-event-stream)
  — the underlying `astream_events` API.
- [04-command-and-control-flow.md](04-command-and-control-flow.md)
  — streaming and `interrupt()` together.
- [08-checkpoints-and-persistence.md](08-checkpoints-and-persistence.md)
  — the checkpointer that makes streaming resumable.
- [10-human-in-the-loop.md](10-human-in-the-loop.md) — the
  confirmation flow, end to end.
- LangGraph streaming: <https://langchain-ai.github.io/langgraph/concepts/streaming/>
