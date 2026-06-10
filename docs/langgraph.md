# LangGraph

The state-machine library that sits on top of LangChain. Strata's
agent loop is a LangGraph `StateGraph`: a typed state, nodes that
update it, and conditional edges that route between them.

Read this after `docs/langchain.md` — LangGraph assumes you understand
messages, `BaseChatModel`, and `BaseTool`.

---

## 1. Mental model

A LangGraph graph is **a typed state + a set of nodes + a set of
edges**. Nodes are functions. Edges are either fixed (`A → B`) or
conditional (`A → B if X else C`). The state is a typed dict (or
TypedDict) that gets passed to every node.

Each node returns a **partial state update** (a dict). The framework
merges that update into the state using **reducers** (one per field).
When all is said and done, you've got a state machine that:

1. Starts with the initial state.
2. Runs the entry-point node.
3. Each node returns a partial update.
4. The graph merges the update and picks the next node from the
   outgoing edges (using the conditional function if applicable).
5. Reaches `END` and returns the final state.

The crucial thing: **nodes are stateless**. They read from the state,
return a partial update, and the framework does the merging. This
makes the graph testable, resumable, and inspectable.

```mermaid
flowchart LR
    START([START]) --> think[call_model]
    think -->|"has tool_calls"| tools[ToolNode]
    think -->|"no tool_calls"| END1([END])
    tools --> think
```

---

## 2. State

State is a `TypedDict` with one or more fields, each annotated with a
**reducer** that controls how partial updates merge into existing
state.

```python
from typing import Annotated
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_id: str
    thread_id: str
```

### Reducers

A reducer is a function `(current_value, update) -> new_value`. The
default reducer overwrites. `add_messages` (the one you almost always
want for `messages`) **appends** and de-duplicates by `id`.

The signature of `add_messages` is:

```python
def add_messages(left: list, right: list | BaseMessage) -> list:
    """Append right to left, replacing any message in left whose id
    matches an id in right."""
```

Why this matters: when a node returns `{"messages": [AIMessage(...)]}`,
the framework appends to the existing messages list. When you use the
default reducer (or no reducer), your single message would *replace*
the entire history, which is wrong for chat.

### `total=False`

`total=False` on the `TypedDict` means **all keys are optional** —
nodes can return partial updates without supplying every field. This
is the right default for state machines.

If a key has no reducer and you return it from multiple nodes, the
last-write wins. If a key has `add_messages` (or any reducer), the
reducer decides.

---

## 3. Nodes

A node is a function `(state: State) -> dict | Command`:

```python
def call_model(state: AgentState) -> dict:
    messages = state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}    # partial update
```

A node can also return a `Command` (covered in §6 — used for dynamic
control flow, e.g. "go to this node and update these fields").

### Reading state

`state` is whatever the framework is passing you, which is the
current merged state. Read fields by key:

```python
last = state["messages"][-1]
```

### Returning a partial update

Return a dict with **only the fields you want to change**. Fields you
omit are not touched. The framework applies the reducer for each
field you return.

```python
return {"messages": [AIMessage(content="...")]}
```

If you return a bare `BaseMessage` instead of a list, LangGraph wraps
it: `{"messages": [returned_message]}`. Same behavior.

### Side effects

Nodes can do anything (DB calls, HTTP, log) but should not mutate
state in place. Mutating `state["messages"]` is a footgun; the
framework owns the state object.

---

## 4. Edges

### Fixed edges

```python
graph.add_edge(START, "call_model")
graph.add_edge("tools", "call_model")
```

### Conditional edges

```python
from langgraph.graph import END

def should_continue(state) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END

graph.add_conditional_edges("call_model", should_continue, {
    "tools": "tools",
    END: END,
})
```

The third argument (a `path_map`) is optional but **strongly
recommended** — it makes the graph self-documenting.

### `tools_condition`

`langgraph.prebuilt.tools_condition` is the standard router for
tool-calling. Given the last message, it returns `"tools"` if there
are tool calls, else `END`. Strata uses it:

```python
from langgraph.prebuilt import tools_condition, ToolNode

graph.add_conditional_edges(
    "call_model",
    tools_condition,
    {"tools": "tools", END: END},
)
```

It's literally:

```python
def tools_condition(state) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END
```

But it's a stable, tested, supported thing — use it instead of
re-implementing.

---

## 5. `ToolNode`

`ToolNode` is the standard node that **executes a list of tools based
on the last `AIMessage`'s `tool_calls`** and appends `ToolMessage`s
to the state.

```python
from langgraph.prebuilt import ToolNode

graph.add_node("tools", ToolNode([list_clusters, get_cluster_status, ...]))
```

What it does, mechanically:

1. Looks at the last message in state.
2. If it's an `AIMessage` with `tool_calls`, iterates them.
3. For each `tool_call`, finds the matching tool by name, calls
   `tool.invoke(tool_call["args"])`, and wraps the result in a
   `ToolMessage(tool_call_id=tool_call["id"], content=..., name=...)`.
4. Appends all the `ToolMessage`s to state.
5. Returns `{"messages": [the_tool_messages]}`.

If a tool's name is unknown, the result is a `ToolMessage` with an
error string. If the arguments fail validation, same. The framework
keeps the loop going — the model sees the error and can retry or
explain.

### Async tools

`ToolNode` is async-aware. If your tool is `async def`, it awaits. If
your tool is sync, it runs in a thread pool (via `asyncio.to_thread`
under the hood). Mixed lists work.

### Handling errors in tools

`ToolNode(handle_tool_errors=True)` (the default in recent versions)
catches exceptions and returns them as a `ToolMessage` with an error
content. The model sees the error and can react. To customize, pass
a `str` (used as the error message) or a `callable(exception) -> str`
(for custom formatting).

---

## 6. The graph in Strata

`app/graph.py`:

```python
def build_graph():
    tools = _build_tools()
    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges(
        "call_model",
        tools_condition,
        {"tools": "tools", END: END},
    )
    graph.add_edge("tools", "call_model")
    return graph.compile()
```

The compiled graph has `invoke`, `stream`, `astream`, `ainvoke`
methods.

### `invoke({"messages": [...]})` — the simple case

```python
result = graph.invoke({"messages": [HumanMessage(content="list my clusters")]})
# result["messages"] is the full conversation, including all tool calls and results
```

`invoke` runs the graph synchronously and returns the final state.

### `stream(...)` — for incremental output

```python
for event in graph.stream({"messages": [HumanMessage(...)]}):
    print(event)
```

`stream` yields events as the graph runs. The format depends on
`stream_mode`:

- `"values"` — the full state after each node.
- `"updates"` — partial updates from each node (the most useful).
- `"messages"` — only `AIMessage` and `ToolMessage` chunks, suitable
  for chat UIs.
- `"events"` — fine-grained node lifecycle events (start, end,
  errors).

For Strata's NDJSON streaming in `app/main.py`, Phase 2 just calls
`invoke` and walks the final `messages` list. Phase 5+ will use
`astream(stream_mode="messages")` for true token streaming.

---

## 7. Checkpointing (deferred to Phase 6)

By default, a LangGraph graph holds state in memory for the
**duration of one invocation**. To persist state across invocations
(multi-turn conversations, human-in-the-loop), you attach a
**checkpointer**.

```python
from langgraph.checkpoint.memory import MemorySaver

graph = build_graph().compile(checkpointer=MemorySaver())

# Now you need a thread_id in config:
result = graph.invoke(
    {"messages": [HumanMessage(content="list my clusters")]},
    config={"configurable": {"thread_id": "user-123"}},
)
```

`MemorySaver` keeps state in a dict (lost on restart). For production:

- `langgraph-checkpoint-postgres` — Postgres-backed (this is what
  Strata will use in Phase 6+, via CloudNativePG).
- `langgraph-checkpoint-sqlite` — SQLite, useful for local dev.

Checkpoints work in concert with `interrupt_before` and
`interrupt_after` to implement **human-in-the-loop**. Strata's
mutation-tool confirmation flow in Phase 6 uses this.

### Phase 2 — no checkpointer

`app/graph.py` does NOT compile with a checkpointer. State lives
for the duration of one HTTP request. This is intentional — it
forces the model to be self-contained per turn and avoids the
"what does the LLM see from prior turns?" problem during early
development.

---

## 8. Common patterns

### Conditional retrieval (Phase 4)

The RAG `retrieve` node goes before `call_model`:

```python
def should_retrieve(state) -> str:
    last_msg = state["messages"][-1]
    if isinstance(last_msg, HumanMessage):
        text = last_msg.content.lower()
        if any(kw in text for kw in ["how do i", "what is", "why does", "docs"]):
            return "retrieve"
    return "call_model"

graph.add_conditional_edges(START, should_retrieve, {
    "retrieve": "retrieve",
    "call_model": "call_model",
})
```

Or use a `Command` from the retrieve node to decide:

```python
def retrieve_node(state) -> Command:
    docs = retriever.invoke(state["messages"][-1].content)
    if not docs:
        return Command(goto="call_model")
    return Command(
        goto="call_model",
        update={"messages": [SystemMessage(content=f"Use these docs: {docs}")]},
    )
```

### Human-in-the-loop confirmation (Phase 6)

For mutation tools (provision_cluster, delete_cluster), the standard
pattern is:

1. The LLM calls a tool marked as `requires_confirmation=True`.
2. The graph's conditional edge routes to a `confirm` node instead
   of `ToolNode`.
3. The `confirm` node returns a `Command(goto=__end__, update=...)`
   that pauses the graph and writes a pending action to Postgres.
4. The CLI/web UI shows the user the action; they approve/deny.
5. The user's response triggers a NEW invocation of the graph with
   the previous thread_id, which resumes from the checkpoint.

This is the "wait for human" pattern that LangGraph supports via
`interrupt` and `Command(resume=...)`. See Phase 6 design in
`AGENTS.md §7`.

### Subgraphs

For deeply nested agent flows, you can compile a graph and use it as
a node in another graph. Strata doesn't do this in Phase 2; the
RAG `retrieve` node in Phase 4 is just a function call to the
retriever HTTP API, not a subgraph.

---

## 9. Common pitfalls (in this codebase)

1. **`@tool` is imported from `langchain_core.tools`, not
   `langchain.tools`.** The latter is a legacy compatibility module.
2. **`tools_condition` lives in `langgraph.prebuilt`**, not
   `langgraph.graph`. Same with `ToolNode`.
3. **`StateGraph` (capital S) is the public name; the lowercase
   `state_graph` was a 0.0.x alias.** Use `StateGraph`.
4. **Reducers run on every partial update.** If you return
   `{"messages": some_message}`, `add_messages` is what decides
   whether it's appended. If you want to *replace* the history,
   you need a custom reducer or to clear the field first.
5. **`ToolNode` returns a list of `ToolMessage`s**, one per
   `tool_call`. If the LLM made three parallel tool calls, the
   node produces three messages.
6. **Compiled graphs are reusable**. Build once at module scope,
   call `.invoke` per request. Don't re-compile per request — the
   `StateGraph` setup is fast but `compile` is non-trivial.
7. **`invoke` is synchronous.** Inside an async FastAPI handler,
   either use `await graph.ainvoke(...)` or wrap in
   `asyncio.to_thread(graph.invoke, ...)`. Strata's `app/main.py`
   uses sync `invoke` for Phase 2 (the graph is fast and the
   endpoint streams from the final state); we'll move to `astream`
   in Phase 5+.

---

## 10. Debugging tips

- **`graph.get_graph().print_ascii()`** prints the graph topology
  in ASCII. Useful in a REPL.
- **`graph.get_graph().to_json()`** gives a JSON spec you can
  render with Mermaid via the `langchain` CLI.
- **`graph.stream(..., stream_mode="updates")`** shows partial
  updates per node — what each node returned. Best for "the model
  isn't getting the tool result" type bugs.
- **`graph.stream(..., stream_mode="values")`** shows the full
  state after each node — useful for "the state is getting
  corrupted" type bugs.
- **Add a print/log in your `call_model` node** to see what the
  model actually received. The system prompt is in the messages;
  log it once to verify.

---

## 11. What to read next

- `docs/langchain.md` — read first if you haven't.
- `docs/litellm.md` — the model layer between LangChain and
  Bedrock.
- `docs/strata/agent-architecture.md` — the project-specific
  graph topology and why.
- LangGraph docs: <https://langchain-ai.github.io/langgraph/>
- LangGraph concepts: <https://langchain-ai.github.io/langgraph/concepts/>
