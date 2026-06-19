# LangGraph — `ToolNode` & `tools_condition`

> **Part 5 of the LangGraph deep-dive.** The `ToolNode` in depth
> (parallel tool calls, error handling, async), `tools_condition`
> (the standard router), and when to write your own router.

The standard agent loop is:

```
call_model → (has tool_calls?) → ToolNode → call_model
            ↘ (no tool_calls?) → END
```

`ToolNode` is the prebuilt that runs the tools. `tools_condition`
is the prebuilt that decides whether to route to `ToolNode` or
`END`. Together they're the most common LangGraph pattern in
existence.

---

## 1. `ToolNode` — the prebuilt

```python
from langgraph.prebuilt import ToolNode

tool_node = ToolNode(tools=[list_clusters, get_cluster_status, ...])
graph.add_node("tools", tool_node)
```

`tools` is a list of LangChain `BaseTool` objects. Usually
`@tool`-decorated functions. `ToolNode` accepts any list of
tools, including `StructuredTool.from_function(...)` and
`BaseTool` subclasses.

### What it does, mechanically

1. Read the last `AIMessage` from state.
2. If it has `tool_calls`, iterate them in order.
3. For each `tool_call`:
   - Look up the tool by name.
   - Call `tool.invoke(tool_call["args"])`.
   - Wrap the result in `ToolMessage(content=str(result), name=tool_name, tool_call_id=tool_call["id"])`.
4. Append all `ToolMessage`s to state (via `add_messages`).
5. Return `{"messages": [the_tool_messages]}`.

If the tool name is unknown, the `ToolMessage` has an error
string. If the args fail validation, same. The graph keeps
running — the model sees the error and can react.

### Default options

```python
ToolNode(
    tools,
    name="tools",                              # node name in the graph
    handle_tool_errors=True,                   # convert exceptions to ToolMessage
    messages_key="messages",                   # which state field holds the messages
)
```

| Option | Default | What |
|---|---|---|
| `name` | `"tools"` | The node's name. Visible in events. |
| `handle_tool_errors` | `True` (recent versions) | If `True`, exceptions become `ToolMessage(status="error", content="<error>")`. If `False`, the exception propagates and the graph crashes. |
| `messages_key` | `"messages"` | The state field that holds the message list. Use a different name if your state field isn't `messages`. |

### `handle_tool_errors` details

```python
# True (default) — catch all exceptions:
ToolNode(tools, handle_tool_errors=True)
# An exception becomes:
# ToolMessage(content="Error: <message>", name="<tool_name>", tool_call_id="<id>", status="error")

# False — let exceptions propagate:
ToolNode(tools, handle_tool_errors=False)
# The graph run fails with the exception.

# A static string — use this for all errors:
ToolNode(tools, handle_tool_errors="The cluster service is down. Try again later.")
# All errors get the same content. Less informative.

# A callable — custom format:
ToolNode(tools, handle_tool_errors=lambda e: f"Tool failed: {type(e).__name__}: {e}")
# Or with a logger:
def my_format(e: Exception) -> str:
    log.error("tool failed", exc_info=e)
    return f"Tool failed: {e}"
ToolNode(tools, handle_tool_errors=my_format)
```

Strata's Phase 2: default `handle_tool_errors=True` is fine.
The model sees the error string and can decide what to do
(retry, give up, tell the user).

### `messages_key`

If your state has `messages: Annotated[list, add_messages]`
under the key `"messages"`, the default works. If you use a
custom name:

```python
class State(TypedDict, total=False):
    history: Annotated[list, add_messages]

ToolNode(tools, messages_key="history")
```

Rarely needed. Strata uses `messages`.

---

## 2. Parallel tool calls

If the model emits multiple `tool_calls` in one `AIMessage`,
`ToolNode` processes them in order. The result is N
`ToolMessage`s appended to state in the same order.

```python
AIMessage(
    content="",
    tool_calls=[
        ToolCall(name="list_clusters", args={}, id="call-1"),
        ToolCall(name="get_cluster_status", args={"cluster_id": "cl-001"}, id="call-2"),
    ],
)
```

`ToolNode` runs `list_clusters` and `get_cluster_status`. The
state ends up with:

```python
ToolMessage(content="[...]", name="list_clusters", tool_call_id="call-1")
ToolMessage(content="{...}", name="get_cluster_status", tool_call_id="call-2")
```

The next model call sees both results and can reason across
them.

### Async parallelism

Async tools can run concurrently. `ToolNode` uses
`asyncio.gather` for async tools. Sync tools run in
`asyncio.to_thread` (a thread pool), so mixed lists work:

```python
# Both async
@tool
async def list_clusters() -> list[dict]: ...

@tool
async def get_status(cluster_id: str) -> dict: ...

# These run in parallel when the model calls both in one AIMessage.
```

The default thread pool has a limit; for many parallel calls
you might hit it. For Strata's 5 tools, irrelevant.

### Disabling parallel calls

`llm.bind_tools(tools, parallel_tool_calls=False)`. The model
emits at most one tool call per `AIMessage`. Simpler state
machine. Useful in tests where you want determinism.

---

## 3. `tools_condition` — the standard router

```python
from langgraph.prebuilt import tools_condition

graph.add_conditional_edges(
    "call_model",
    tools_condition,
    {"tools": "tools", END: END},
)
```

`tools_condition` is literally:

```python
def tools_condition(state) -> Literal["tools", "__end__"]:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "__end__"
```

It checks the last message. If it has non-empty `tool_calls`,
return `"tools"`. Otherwise, return `"__end__"` (a string
sentinel for `END`).

The path map `{"tools": "tools", END: END}` is optional but
recommended. The literal `"__end__"` works without it, but
the explicit map is more readable.

### Why use it

It's stable, tested, and the right 95% of the time. If you
need more nuanced routing (e.g. "tool A goes to node X, tool
B goes to node Y"), write your own.

---

## 4. Custom routers

```python
def custom_route(state) -> str:
    last = state["messages"][-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return END
    # Dispatch by tool name:
    tool_name = last.tool_calls[0]["name"]
    if tool_name in {"provision_cluster", "delete_cluster"}:
        return "mutation_tools"      # routes through confirmation
    return "read_tools"               # read-only tools, no confirmation

graph.add_conditional_edges(
    "call_model",
    custom_route,
    {"mutation_tools": "mutation_tools", "read_tools": "read_tools", END: END},
)
```

This is the Strata Phase 6 mutation-tool flow: mutation tools
go through a confirmation node, read tools go straight to
`ToolNode`. The router decides based on tool name.

### Multiple tool calls in one AIMessage

If the model emits `[provision_cluster, list_clusters]` in one
AIMessage, your custom router has to choose. Options:

- Run all in order (one node, like `ToolNode` does).
- Run the read tool, queue the mutation for confirmation.
- Error out: "don't mix mutation and read in one call."

Strata's design (Phase 6): the router checks if any tool
call is a mutation. If so, route to the mutation-confirmation
node, which prompts the user. The read tools don't run until
the user confirms (and the confirmation only applies to the
mutation).

### Router performance

The router runs on every invocation of the source node. Keep
it cheap. Don't make HTTP calls or query the DB in it. Read
the last message, look at its `tool_calls`, return a string.

---

## 5. Errors in tools — the full flow

The model calls a tool. The tool raises. What happens?

```python
@tool
def get_cluster_status(cluster_id: str) -> dict:
    """..."""
    if cluster_id not in KNOWN:
        raise KeyError(f"Cluster {cluster_id} not found")
    return {...}
```

With `ToolNode(tools, handle_tool_errors=True)`:

1. `ToolNode` catches the `KeyError`.
2. Builds `ToolMessage(content="Error: Cluster cl-999 not found", name="get_cluster_status", tool_call_id="call-abc", status="error")`.
3. Appends to state.
4. Graph continues.
5. `call_model` runs again. Sees the `ToolMessage` with
   `status="error"`.
6. The model can:
   - Apologize and tell the user.
   - Try a different tool (e.g. `list_clusters` to find the
     right id).
   - Give up.

This is the **graceful** flow. The user sees a sensible
response. The graph doesn't crash.

### When to raise vs. return error

| | Raise | Return error string |
|---|---|---|
| Model's call was malformed | ✅ | |
| Model's call was valid but the data doesn't exist | either | ✅ |
| The system is down (DB unreachable) | ✅ (network is broken) | |
| Business rule violation (e.g. "can't delete a cluster in use") | either | ✅ |

For most business errors, returning a dict like
`{"status": "NOT_FOUND", "error": "..."}` and letting the
tool's success path produce the `ToolMessage` keeps the flow
consistent. The model reads the error from `content` like any
other tool result.

For system errors (network, DB down), raise. `ToolNode` wraps
it.

---

## 6. `ToolNode` with `ToolCall` validation

If the model emits a tool call with invalid args (e.g. wrong
type), the tool's `args_schema` (Pydantic) rejects it. The
`ToolNode` catches the validation error and produces a
`ToolMessage(status="error")`. The model sees the error and
should try again with correct args.

```python
@tool(args_schema=GetClusterStatusArgs)   # cluster_id: str, required
def get_cluster_status(cluster_id: str) -> dict: ...
```

If the model emits `tool_call={"args": {"cluster_id": 123}}`
(int instead of str), Pydantic rejects. `ToolNode` produces
an error `ToolMessage`. The model tries again with
`{"cluster_id": "123"}`.

This is one of the things that makes the agent loop
self-correcting.

---

## 7. `ToolNode` with the `__end__` (END) sentinel

If a tool returns a `Command(goto=END)`, the `ToolNode` honors
it. The graph stops after the tool runs. The `ToolMessage`
is still in state; the final state is returned to the caller.

Useful for "after this tool, the work is done." Rare.

---

## 8. Returning a `Command` from a tool

```python
@tool
def finish_session() -> Command:
    """End the session."""
    return Command(
        goto=END,
        update={"messages": [AIMessage(content="Goodbye.")]},
    )
```

The tool's return is a `Command`. `ToolNode` applies the
`update` (appends the `AIMessage`) and routes to `END`.

The tool's signature is `() -> Command`, so the LLM has to
call it with no args. The docstring tells the model when to
use it.

---

## 9. When to write your own `ToolNode`-like node

`ToolNode` is the standard. But you might want a custom
version for:

- **Logging every tool call** to a database.
- **Per-tool timeouts** (e.g. long-running tools have 5 min,
  short tools have 30s).
- **Per-tool retry policies** (e.g. retry `provision_cluster`
  3 times, retry `get_logs` 0 times).
- **Rate limiting** (don't call `list_clusters` more than once
  per turn).
- **Pre/post-processing** (e.g. check the user's quota before
  calling `provision_cluster`).

A custom `tool_node(state) -> dict`:

```python
def custom_tool_node(state):
    last = state["messages"][-1]
    tool_messages = []
    for tc in last.tool_calls:
        try:
            result = tool_registry[tc["name"]].invoke(tc["args"])
            tool_messages.append(ToolMessage(
                content=json.dumps(result),
                name=tc["name"],
                tool_call_id=tc["id"],
            ))
            log_tool_call(tc["name"], tc["args"], success=True)
        except Exception as e:
            tool_messages.append(ToolMessage(
                content=f"Error: {e}",
                name=tc["name"],
                tool_call_id=tc["id"],
                status="error",
            ))
            log_tool_call(tc["name"], tc["args"], success=False, error=str(e))
    return {"messages": tool_messages}
```

The standard `ToolNode` is one big switch statement that
delegates per-tool. The custom version can add policy.

Strata's Phase 2 uses the standard `ToolNode`. Phase 6+ might
add a custom version with per-tool timeouts and audit
logging.

---

## 10. Common pitfalls

1. **`tools_condition` is in `langgraph.prebuilt`**, not
   `langgraph.graph`. Easy to typo.
2. **`ToolNode` requires the tool's name to match a registered
   tool.** If the model hallucinates a tool name, the result is
   an error `ToolMessage`. Make sure your tool descriptions
   are accurate.
3. **Parallel tool calls share `handle_tool_errors` config.**
   If one fails, all results are still produced. The model
   sees a mix of successes and errors.
4. **`ToolMessage.content` is always a string.** If your
   tool returns a dict, the framework serializes it (Pydantic
   → JSON, plain dict → `str()`). The str of a dict is the
   Python repr, which is JSON-ish but not guaranteed JSON.
   For guaranteed JSON, use Pydantic models or serialize
   explicitly.
5. **`messages_key` defaults to "messages".** If your state
   has a different field, you must set it.
6. **`tools_condition` looks at the LAST message.** If you
   build a custom state where the last message is something
   else (e.g. a summary), `tools_condition` returns `END`
   because the last message has no `tool_calls`.
7. **`Command(goto=END)` from a tool** ends the graph. The
   `ToolMessage` is in the final state, but no more `call_model`
   runs. Make sure that's what you want.
8. **Tool calls with `status="error"` are not retried
   automatically.** The model has to decide to retry (and
   usually doesn't, unless the error is "transient" and the
   prompt encourages retry).
9. **Async tools + `ToolNode` + sync test** — the test calls
   `graph.invoke(...)`, which awaits the async tools. The
   test must be `async` (use `pytest-asyncio`).
10. **`ToolNode` and the `messages` field** — if your state
    has a different messages field (e.g. `history`), pass
    `messages_key="history"`.

---

## 11. What to read next

- [04-command-and-control-flow.md](04-command-and-control-flow.md)
  — `Command` for tool returns and HITL.
- [06-subgraphs-and-map-reduce.md](06-subgraphs-and-map-reduce.md)
  — subgraphs and `Send`.
- [10-human-in-the-loop.md](10-human-in-the-loop.md) — the
  mutation-tool confirmation flow.
- [08-checkpoints-and-persistence.md](08-checkpoints-and-persistence.md)
  — what happens to tool results across turns.
- LangGraph `ToolNode` API: <https://langchain-ai.github.io/langgraph/reference/prebuilt/#langgraph.prebuilt.tool_node.ToolNode>
