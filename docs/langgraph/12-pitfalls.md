# LangGraph — Pitfalls

> **Part 12 of the LangGraph deep-dive.** A consolidated list
> of common bugs, version-drift gotchas, and import-path traps
> that bit us (or bit the broader community) and how to avoid
> them.

A focused list of "I lost an hour to this" bugs. Read this once
so you don't lose an hour yourself.

---

## 1. State schema pitfalls

### Forgetting `add_messages` (the most common bug)

```python
# WRONG
class State(TypedDict, total=False):
    messages: list    # no reducer; gets overwritten every node

# RIGHT
from langgraph.graph.message import add_messages
class State(TypedDict, total=False):
    messages: Annotated[list, add_messages]
```

Without the reducer, every node return that includes
`"messages"` overwrites the entire history. The conversation
is lost after the first node.

### Mutating `state` in place

```python
# WRONG
def my_node(state):
    state["messages"].append(AIMessage(content="..."))    # mutation!
    return state

# RIGHT
def my_node(state):
    return {"messages": [AIMessage(content="...")]}
```

The framework owns the state. If you mutate, the reducer
doesn't run, the checkpointer writes the wrong thing, and
downstream nodes see weird state.

### `total=True` when you want partial updates

```python
# If you use total=True (the default), every key is required.
# A node returning {"messages": [...]} but not "user_id" raises
# an InvalidUpdateError.

# Use total=False for flexibility:
class State(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_id: str
```

### State field name collisions across graphs

If a subgraph and parent both use a field named `messages`,
the messages flow through both. The parent's `add_messages`
handles the merging. If you want isolation, use different
field names.

### Non-JSON-serializable state

```python
# WRONG
class State(TypedDict, total=False):
    client: httpx.AsyncClient    # not serializable; checkpointer fails

# RIGHT: pass the client via the runtime context, not state.
```

The checkpointer writes state as JSON. Custom classes
(httpx clients, DB connections, PIL images) don't serialize.

---

## 2. Node pitfalls

### Forgetting `async def` for async tools

```python
# WRONG
@tool
def my_tool() -> dict:    # sync
    return httpx.get(...).json()    # blocks the event loop

# RIGHT
@tool
async def my_tool() -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.get(...)
        return r.json()
```

### Re-compiling per request

```python
# WRONG
async def handler(input):
    app = graph.compile()    # expensive!
    return await app.ainvoke(input)

# RIGHT: compile once at module scope.
app = graph.compile()

async def handler(input):
    return await app.ainvoke(input)
```

`compile()` is non-trivial. It validates edges, constructs
the `Pregel` runtime, etc. Re-compile per request is
needless overhead.

### Side effects in the path function

```python
# WRONG
def route(state) -> str:
    db.query("INSERT INTO audit_log ...")    # runs on every invocation
    return "next_node"

# RIGHT: do side effects in nodes, not routers.
```

The path function runs on every conditional edge. Keep it
cheap. Side effects belong in nodes.

### `cache_policy` with a wrong `key_func`

```python
# WRONG: key_func is too generic
graph.add_node("retrieve", retrieve, cache_policy=CachePolicy(
    ttl=300,
    key_func=lambda state: ("retrieve",),    # same for all states!
))

# RIGHT: key on the input that matters
graph.add_node("retrieve", retrieve, cache_policy=CachePolicy(
    ttl=300,
    key_func=lambda state: ("retrieve", state["messages"][-1].content),
))
```

If `key_func` returns the same value for different states,
the cache returns stale data.

---

## 3. Edge pitfalls

### Two fixed edges out of one node

```python
# WRONG
graph.add_edge("call_model", "tools")
graph.add_edge("call_model", "summarize")    # graph errors

# RIGHT: use a conditional edge
graph.add_conditional_edges("call_model", router, {...})
```

A node has exactly one "next step" per invocation. Use a
conditional edge to pick.

### Path function returns a value not in the path map

```python
# WRONG
def router(state):
    if condition:
        return "tools"      # not in path_map
    return "summarize"

graph.add_conditional_edges("call_model", router, {"tools": "tools"})

# RIGHT: include all possible return values
graph.add_conditional_edges("call_model", router, {
    "tools": "tools",
    "summarize": "summarize",
})
```

The graph errors at runtime if the router returns a value
not in the path map. Use the path map consistently.

### Path function returns a list when not using `Send`

```python
# WRONG
def router(state):
    return ["tools", "summarize"]    # not what you want

# RIGHT: return a single string (or a list of Send)
def router(state):
    if condition:
        return "tools"
    return "summarize"
```

The conditional edge accepts a list only when those are
`Send` instances for map-reduce.

---

## 4. `ToolNode` / tool pitfalls

### `ToolMessage.content` not a string

```python
# WRONG
@tool
def my_tool() -> dict:
    return {"foo": "bar"}

# The ToolMessage.content is str({"foo": "bar"}) = "{'foo': 'bar'}"
# (Python repr, not JSON)

# RIGHT
@tool
def my_tool() -> str:
    return json.dumps({"foo": "bar"})
```

Always serialize. Pydantic models are usually handled, but
plain dicts use `str()` which is repr-style. JSON is what
the model expects.

### Tool name hallucination

If the model emits a tool call for a tool not in the
`bind_tools` list, `ToolNode` produces an error `ToolMessage`.
The model sees the error and may try to call the tool again
or apologize.

Make sure your tool descriptions are accurate. If a tool
description is vague, the model might call a similar-named
tool that doesn't exist.

### `handle_tool_errors=False` in production

```python
# WRONG (for prod)
ToolNode(tools, handle_tool_errors=False)
# Any tool exception crashes the graph run.

# RIGHT (default)
ToolNode(tools)    # handle_tool_errors=True is the default
```

`False` is for "I want the exception to propagate, this is
a programmer error." Production: leave the default.

### `messages_key` mismatch

```python
# If your state has:
class State(TypedDict):
    history: Annotated[list, add_messages]    # NOT "messages"

# You need:
ToolNode(tools, messages_key="history")
```

The default `messages_key="messages"` doesn't match a field
named "history." The ToolNode looks at the wrong field and
errors.

---

## 5. `Command` pitfalls

### `Command(goto="non_existent_node")`

```python
# WRONG
def my_node(state):
    return Command(goto="delete_mutation")    # node not added

# RIGHT
graph.add_node("delete_mutation", delete_mutation_fn)
def my_node(state):
    return Command(goto="delete_mutation")
```

The graph can't find the target. Runtime error.

### `Command.PARENT` outside a subgraph

`Command.PARENT` is only valid inside a node that's part of
a subgraph. Calling it from a top-level node is an error.

### `Command(resume=...)` with the wrong type

```python
# If interrupt() expects a string:
interrupt({"q": "..."})
# And you resume with a dict:
Command(resume={"answer": "x"})
# The node sees {"answer": "x"} instead of a string.
# If the node compares response == "allow", it always fails.
```

Match the resume value's shape to the node's expectations.

### Multiple `interrupt()` calls need multiple resumes

Don't try to "skip" a pause with one big `Command(resume={...})`.
Each `interrupt()` is a separate pause; each needs a
separate `Command(resume=...)`.

---

## 6. `interrupt()` pitfalls

### `interrupt()` without a checkpointer

```python
# WRONG
app = graph.compile()    # no checkpointer
def my_node(state):
    interrupt({...})    # runtime error: no checkpointer

# RIGHT
app = graph.compile(checkpointer=MemorySaver())
```

Without a checkpointer, the pause has nowhere to save
state. Always include a checkpointer when using
`interrupt()`.

### Resuming with the wrong `thread_id`

```python
# First invoke (pause):
graph.invoke(input, config={"configurable": {"thread_id": "user-42"}})

# Resume with different thread_id:
graph.invoke(Command(resume="yes"), config={"configurable": {"thread_id": "user-43"}})
# This starts a NEW run, doesn't resume.
```

The thread id is the link. Use the same one.

### Catching `Interrupt` exceptions in user code

The framework's `interrupt()` raises a special exception
internally (something like `GraphInterrupt`). Don't catch
it; the framework needs it to pause.

---

## 7. Streaming pitfalls

### `astream_events` without `version="v2"`

```python
# WRONG (defaults to legacy v1)
async for event in graph.astream_events(input, config):
    ...

# RIGHT
async for event in graph.astream_events(input, config, version="v2"):
    ...
```

`v1` is the legacy API. The error message tells you to
upgrade. Always pass `version="v2"`.

### Filtering `include_types` is substring

```python
# WRONG: include_types=["chain"] matches "chat_model_chain"
include_types=["chain"]

# RIGHT: be specific
include_types=["chat_model", "tool", "retriever"]
```

The filter is a substring match. Be exact or use
`include_names` instead.

### Stream ends with `done` not state

The stream emits events as the graph runs. The final event
is not the final state. If you want the final state, use
`graph.get_state(config)` after the stream.

### NDJSON framing

Each line is one JSON object. Don't put newlines in the
JSON. The CLI parses one line at a time.

### SSE framing

Each event is `data: <json>\n\n`. The `\n\n` is required
(two newlines). Browsers parse on the `\n\n`.

---

## 8. Checkpointer pitfalls

### Different thread ids for the same conversation

A typo or code change silently breaks persistence. The
conversations start fresh. Standardize the thread id format
in a constant.

### `MemorySaver` for production

Lost on restart. Don't use for real conversations. Use
`PostgresSaver`.

### Two replicas writing to `SqliteSaver`

Corruption. SQLite is single-process. For multi-replica
deployments, use `PostgresSaver`.

### Forgetting `cp.setup()`

`PostgresSaver.setup()` creates the tables. Without it, the
first write fails with a "relation does not exist" error.

### Async/sync mismatch

```python
# WRONG: compiled with sync saver, called via async
app = graph.compile(checkpointer=PostgresSaver(...))
await app.ainvoke(input, config)    # might fail or deadlock

# RIGHT: match sync/async
app = graph.compile(checkpointer=AsyncPostgresSaver(...))
await app.ainvoke(input, config)
```

The async saver is the right one for FastAPI. The sync saver
is for sync code (tests, scripts).

### State field not JSON-serializable

```python
# WRONG
class State(TypedDict, total=False):
    client: httpx.AsyncClient    # not JSON

# RIGHT
# Pass the client via runtime context, not state.
```

The checkpointer serializes state as JSON. Non-JSON values
fail.

---

## 9. Recursion / cycle pitfalls

### `recursion_limit=25` default is too low

For an agent loop with multiple tool calls, 25 might be
close. Bump to 50 or 100 if you have a legitimate long loop.

### Runaway loops

If the model keeps calling tools without converging, the
graph loops forever (until `recursion_limit`). Diagnose:

- Is the model receiving the right tools?
- Is the system prompt clear about when to stop?
- Are the tool results helpful, or are they confusing the
  model?

Fix: tighten the prompt, add a "give up" node, or use
`with_structured_output` to force a final answer.

---

## 10. Version / package pitfalls

### `langgraph` 0.0.x vs 0.1+ vs 0.2+ vs 0.3+

- **0.0.x** — early API. `state_graph` (lowercase) was the
  alias. Many imports changed.
- **0.1** — first "stable." `StateGraph` (capital S) is the
  public name. `MemorySaver` is the standard checkpointer.
- **0.2** — `interrupt()` function, `Command(resume=...)`,
  `Send` improvements.
- **0.3** — `cache_policy` on `add_node`, `state_schema` /
  `input_schema` / `output_schema`, `durability` modes.

If you see `ImportError` on `langgraph.X`, the package
version is too old or too new. Check the installed version
and the docs.

### `langgraph.prebuilt` is the right home for `ToolNode`

```python
# WRONG
from langgraph.graph import ToolNode    # not there

# RIGHT
from langgraph.prebuilt import ToolNode, tools_condition
```

`ToolNode` and `tools_condition` live in `langgraph.prebuilt`,
not `langgraph.graph`.

### `StateGraph` is capitalized

```python
# WRONG (0.0.x alias)
from langgraph.graph import state_graph

# RIGHT
from langgraph.graph import StateGraph
```

### `@langgraph` decorators (the functional API)

```python
from langgraph.func import entrypoint, task

@entrypoint(checkpointer=...)
def my_agent(messages: list) -> list:
    ...
```

The functional API is an alternative to `StateGraph`. Don't
mix the two in the same graph.

### `langgraph-sdk` for the platform

```python
from langgraph_sdk import get_client
client = get_client(url="https://my-deployment.langgraph.app")
```

`langgraph_sdk` is the client for LangGraph Platform (managed
deployment). Strata doesn't use it.

---

## 11. The "weird state" debugging checklist

When the state is wrong, check:

1. **Is the right reducer attached?** `Annotated[list, add_messages]`.
2. **Are you mutating state in place?** Don't.
3. **Is the node returning a partial update or the full
   state?** Partial update is the right answer.
4. **Is the path function correctly routing?**
   `stream_mode="updates"` shows the routing decisions.
5. **Is the conditional edge returning a string in the
   path map?**
6. **Is the state field name correct in the schema?**
7. **Is the checkpointer writing the right state?** `psql` to
   check.
8. **Is the `add_messages` reducer's `id` correlation
   correct?** Mismatched ids break the conversation.

---

## 12. The "graph won't compile" checklist

When `graph.compile()` errors:

1. **All node names in edges exist.** Add missing nodes.
2. **All conditional edge path map targets exist.** Add
   missing nodes.
3. **No orphan nodes.** Every node is reachable from
   `START` and reaches `END`.
4. **No unreachable nodes.** The graph validates
   reachability.
5. **State schema is valid.** `TypedDict` with
   `Annotated[T, reducer]` for fields with reducers.

---

## 13. What to read next

- The other parts of the LangGraph deep-dive, especially
  [02-state-and-reducers.md](02-state-and-reducers.md),
  [03-nodes-and-edges.md](03-nodes-and-edges.md), and
  [05-toolnode-and-tools_condition.md](05-toolnode-and-tools_condition.md).
- [11-deployment-and-debug.md](11-deployment-and-debug.md) —
  debugging recipes.
- [`../langchain/08-testing-and-pitfalls.md`](../langchain/08-testing-and-pitfalls.md)
  — testing patterns that catch these bugs.
- LangGraph troubleshooting: <https://langchain-ai.github.io/langgraph/concepts/troubleshooting/>
