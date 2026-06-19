# LangGraph — Nodes & Edges

> **Part 3 of the LangGraph deep-dive.** `add_node` (with
> metadata, retry, cache), `add_edge` (fixed, from `START` /
> `END`), conditional edges, the `path_map`, and the `Send`
> primitive for map-reduce.

A LangGraph graph is **nodes + edges**. Nodes are functions.
Edges connect them. This file is about how to add them and what
options you have.

---

## 1. `add_node` — the basic form

```python
graph.add_node("call_model", call_model)
```

The first argument is the **node name** (a string). The second
is the **callable**. The callable is one of:

- A function `(state) -> dict | Command`
- An async function `(state) -> dict | Command`
- A `Runnable` (anything with `invoke` / `ainvoke`)
- A compiled `StateGraph` (subgraph)
- A `RunnableLambda` wrapping any of the above

The node name must be unique within the graph. Use
`snake_case` for readability.

### Node names appear in events

When you `astream_events`, the `name` field is the node name:

```python
async for event in graph.astream_events(...):
    if event["event"] == "on_chain_start":
        print(event["name"])    # "call_model", "tools", etc.
```

Use clear, descriptive names. "summarize" is better than "node_2."

### `add_node` with metadata

```python
graph.add_node(
    "call_model",
    call_model,
    metadata={"description": "Calls the LLM with the current messages."},
)
```

Metadata shows up in the graph spec and in tracing. Use it to
document the node.

### `add_node` with `retry` and `cache_policy` (0.3+)

```python
from langgraph.types import RetryPolicy, CachePolicy

graph.add_node(
    "call_external_api",
    call_external_api,
    retry=RetryPolicy(
        max_attempts=3,
        initial_interval=1.0,
        backoff_factor=2.0,
        max_interval=10.0,
        jitter=True,
        retry_on=lambda e: isinstance(e, httpx.HTTPError),
    ),
    cache_policy=CachePolicy(
        ttl=300,    # 5 minutes
        key_func=lambda state: (state["messages"][-1].content,),
    ),
)
```

**`RetryPolicy`:** retries the node on certain exceptions, with
exponential backoff. The `retry_on` callable decides which
exceptions to retry.

**`CachePolicy`:** caches the node's result for `ttl` seconds.
The `key_func` decides the cache key. On a cache hit, the node
isn't re-run; the cached result is returned. Useful for
"this is the same query, don't re-embed."

Strata doesn't use these in Phase 2. Phase 4+ uses `cache_policy`
on the `retrieve` node to avoid re-embedding the same query
within a short window.

### Multiple ways to add the same function

```python
# Different names, same function (rare):
graph.add_node("summarize_short", summarize)
graph.add_node("summarize_long", summarize)    # same fn, different config later
```

You can add the same function under different names. Each name
is a separate node in the graph.

---

## 2. The node signature

A node can take various combinations of arguments:

```python
# 1. Just state
def node1(state: State) -> dict: ...

# 2. State + config
def node2(state: State, config: RunnableConfig) -> dict: ...

# 3. State + runtime context
def node3(state: State, runtime: Runtime[Context]) -> dict: ...

# 4. All three
def node4(state: State, config: RunnableConfig, runtime: Runtime[Context]) -> dict: ...

# 5. None — for a Runnable that's already a `Runnable`
graph.add_node("passthrough", RunnablePassthrough())
```

The framework inspects the type annotations and fills in the
right arguments. You can name them however you want.

### `inspect` vs `runtime`

`runtime: Runtime[Context]` is the modern way to access
"things from outside the graph." The runtime context is set
via `graph.invoke(input, context=Context(...))`.

For older code, `config: RunnableConfig` and
`config["configurable"]` is the same idea.

### Reading `state` vs writing to it

Inside a node, `state` is **read-only** conceptually (don't
mutate it). You **return** the partial update.

```python
def call_model(state: AgentState) -> dict:
    response = llm.invoke(state["messages"])   # read
    return {"messages": [response]}            # write
```

---

## 3. The `START` and `END` symbols

```python
from langgraph.graph import StateGraph, START, END

graph = StateGraph(State)
graph.add_edge(START, "call_model")          # graph entry point
graph.add_edge("summarize", END)             # graph exit point
```

`START` is the entry of the graph — every graph has exactly
one edge from `START` (in the simple case). `END` is the
exit. Nodes can have multiple outgoing edges to `END`
(impossible) or multiple incoming edges from `START`
(impossible). One of each.

### Conditional edges from `START`

```python
def route_start(state) -> str:
    last_msg = state["messages"][-1]
    if "logs" in last_msg.content.lower():
        return "fetch_logs"
    return "call_model"

graph.add_conditional_edges(START, route_start, {
    "fetch_logs": "fetch_logs",
    "call_model": "call_model",
})
```

The graph starts, asks the router which node to run, runs it.
This is the entry-point conditional edge. Strata's Phase 4
RAG uses this: "if the user asked a 'what' or 'how' question,
retrieve docs first; else go to call_model."

---

## 4. Fixed edges — `add_edge`

```python
graph.add_edge("call_model", "tools")           # A → B
graph.add_edge("tools", "call_model")           # B → A (creates the cycle)
graph.add_edge(START, "call_model")             # entry
graph.add_edge("summarize", END)                # exit
```

Fixed edges mean "after the source node runs, always go to
the target node." No condition. The source is done; the
target runs.

### Acyclic and cyclic graphs

Acyclic: no cycles, every node runs at most once. This is a
DAG (directed acyclic graph). For DAGs, the graph is a
"pipeline."

Cyclic: a back-edge exists. The agent loop is cyclic:
`call_model → tools → call_model → tools → ...`. To avoid
infinite loops, LangGraph enforces `recursion_limit` (default
25). Bump it or design for termination.

### Multiple edges out of one node

A node can have multiple outgoing edges, but exactly one
must be taken per invocation. That's a conditional edge:

```python
graph.add_conditional_edges(
    "call_model",
    should_continue,
    {"tools": "tools", END: END},
)
```

You can't have two fixed edges out of one node — that's
unconditional branching, which is the conditional edge's job.

### Multiple edges into one node

A node can have multiple incoming edges. All paths lead to
the same node. The node runs once per arrival.

For the agent loop, both `START → call_model` and
`tools → call_model` are incoming edges to `call_model`. After
either path, `call_model` runs.

---

## 5. Conditional edges — `add_conditional_edges`

```python
def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END

graph.add_conditional_edges(
    "call_model",
    should_continue,
    {"tools": "tools", END: END},    # path_map
)
```

The path function `(state) -> str` returns the name of the
next node. The path map translates those names to actual
node names. (The path map is optional but recommended.)

### Path map (optional but recommended)

```python
# Without a path map:
graph.add_conditional_edges("call_model", should_continue)
# The returned strings ("tools", END) must be exact node names.

# With a path map:
graph.add_conditional_edges(
    "call_model",
    should_continue,
    {"tools": "tools", END: END},
)
# The returned strings ("tools", END) are translated via the map.
# If the return value isn't in the map, an error.
```

The path map is **self-documenting** — the graph spec shows
exactly which values the router can return and where they go.
Without the map, you have to read the router function to know
the possible outputs.

### `END` in the path map

`END` is a sentinel, not a node. The path map can include
`END: END` (no translation) to allow the router to return
`END` and the graph to stop.

### Returning multiple values

The path function returns a single string (or a `Send` list
for map-reduce — see below). For complex routing, write the
function clearly.

### Conditional edges in a chain

You can chain conditional edges:

```
call_model → (has tools?) → tools
                          ↘ summarize
tools → call_model
summarize → END
```

To express "after `call_model`, if there are tool calls go
to `tools`, else go to `summarize`":

```python
graph.add_conditional_edges(
    "call_model",
    lambda state: "tools" if state["messages"][-1].tool_calls else "summarize",
    {"tools": "tools", "summarize": "summarize"},
)
graph.add_edge("summarize", END)
```

---

## 6. `Send` — map-reduce / dynamic fan-out

Sometimes the next node should run **once per item** in a
list. The "summarize each document then merge" pattern.

```python
from langgraph.types import Send

def route_to_summarize(state: AgentState) -> list[Send]:
    docs = state["retrieved_docs"]
    return [
        Send("summarize_doc", {"doc": doc, "idx": i})
        for i, doc in enumerate(docs)
    ]

graph.add_conditional_edges("retrieve", route_to_summarize, ["summarize_doc"])
graph.add_node("summarize_doc", summarize_one)
```

`Send(node_name, input)` says "run `node_name` with this
input." The `add_conditional_edges` returning a list of
`Send`s fans out the work. After all `Send`s complete, the
graph continues from the next node (the one that has an edge
from `summarize_doc`).

The destination node sees only the input from `Send`, not the
parent state. To access the parent state, use the runtime
context:

```python
def summarize_one(input: dict, runtime: Runtime[Context]) -> dict:
    # input is {"doc": doc, "idx": i}
    doc = input["doc"]
    # runtime.context is the Context passed at graph.invoke
    return {"summaries": [summary]}
```

Or pass the relevant parent-state fields through `Send`:

```python
return [
    Send("summarize_doc", {"doc": doc, "user_id": state["user_id"]})
    for doc in state["retrieved_docs"]
]
```

### Joining the parallel branches

After all `Send` invocations of `summarize_doc` complete, the
graph continues from the next node (whatever has an edge from
`summarize_doc`). The reducer on the target field merges the
results.

```python
class State(TypedDict, total=False):
    docs: list[dict]
    summaries: Annotated[list[str], operator.add]    # concat

def summarize_one(input: dict) -> dict:
    return {"summaries": [f"summary of {input['doc']['id']}"]}

def merge_summaries(state: AgentState) -> dict:
    return {"final_summary": "\n".join(state["summaries"])}
```

If `summaries` has `operator.add`, each `summarize_doc` run
appends. The next node can read `state["summaries"]` as a
list.

### When to use `Send`

- **Map-reduce** over a list of items.
- **Fan-out to multiple agents** in a multi-agent setup.
- **Tool calls that should run in parallel** (rarely — `ToolNode`
  handles parallel tool calls already).
- **Process N retrieved docs in parallel** for RAG summarization
  (Phase 4+).

---

## 7. `add_edge` from a `Send`-returning node

The `Send` mechanism is a special form of conditional edge.
The node that returns a list of `Send`s doesn't have a normal
"this is the next node" — the next nodes are the `Send`
targets. You still need an edge from the `Send`-issuing node
to indicate the end of the parallel phase:

```python
graph.add_conditional_edges("retrieve", route_to_summarize, ["summarize_doc"])
graph.add_node("summarize_doc", summarize_one)
graph.add_edge("summarize_doc", "merge_summaries")    # all branches converge here
```

The `["summarize_doc"]` in the path map is required when
returning `Send`s. It tells the framework which node
definitions the `Send`s target.

---

## 8. Graph construction order

You build the graph by adding nodes and edges, then compile:

```python
graph = StateGraph(AgentState)
graph.add_node("call_model", call_model)
graph.add_node("tools", ToolNode(tools))
graph.add_node("summarize", summarize)

graph.add_edge(START, "call_model")
graph.add_conditional_edges("call_model", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "call_model")

app = graph.compile()
```

The order of `add_node` / `add_edge` calls doesn't matter.
Compile-time checks for:

- All nodes referenced in edges exist.
- All edges are valid (fixed or conditional).
- No orphan nodes (every node is reachable from `START` and
  can reach `END`).
- All conditional edge path-map targets exist.

### Common compile errors

- `Node "X" not found` — you `add_edge("X", ...)` before
  `add_node("X", ...)`. Add the node first, or check spelling.
- `Edge from "X" has no path` — the conditional edge router
  returns a value not in the path map.
- `Cycle without termination` — the graph has a cycle and
  no node sets `recursion_limit` low enough to prevent
  runaway.

---

## 9. Inspecting the graph

```python
app = graph.compile()

# ASCII art:
app.get_graph().print_ascii()
# +-----------+
# | __start__ |
# +-----------+
#       |
#       v
# +-----------+
# | call_model|
# +-----------+
#       |
#       v (tools | __end__)
# ...

# Mermaid:
print(app.get_graph().draw_mermaid())
# graph TD
#     __start__ --> call_model
#     call_model --> tools
#     call_model --> __end__
#     tools --> call_model

# JSON:
import json
print(json.dumps(app.get_graph().to_json(), indent=2))
```

`get_graph()` returns a `Graph` object. The print methods are
handy in a REPL. The JSON is what LangGraph Studio consumes.

---

## 10. Conditional edges from a tool's return

A tool can return a `Command` that includes `goto`:

```python
@tool
def lookup_and_route(query: str) -> Command:
    """..."""
    docs = retriever.invoke(query)
    return Command(
        goto="call_model",
        update={"messages": [SystemMessage(content=f"Use these docs: {docs}")]},
    )
```

This bypasses the standard `tool_call → tool_node → ???`
routing. The tool directly says "next node is `call_model`."
See [04-command-and-control-flow.md](04-command-and-control-flow.md)
for the full `Command` story.

---

## 11. Common pitfalls

1. **Forgetting `START` / `END`.** Every graph has exactly one
   edge from `START` and one or more edges to `END` (or
   conditional edges that can return `END`).
2. **Multiple fixed edges out of one node.** Use a
   conditional edge.
3. **Path function returns a value not in the path map.**
   The graph errors at compile time. Always include a path
   map (recommended).
4. **The path function does expensive work.** It runs on
   every invocation. Keep it cheap.
5. **The path function returns `Send` for a non-fan-out case.**
   Use a string for single-target routing; reserve `Send`
   for map-reduce.
6. **Compile order.** `add_node` before `add_edge` is fine,
   but the symbols must all exist by the time you call
   `compile()`.
7. **Acyclic vs cyclic confusion.** If your graph has a
   cycle (e.g. the agent loop), you need `recursion_limit`
   or termination logic.
8. **Subgraph as a node** — `add_node("sub", subgraph_compiled)`
   works. The subgraph's input/output schemas must be
   compatible. See
   [06-subgraphs-and-map-reduce.md](06-subgraphs-and-map-reduce.md).
9. **`add_node` with `cache_policy`** caches based on
   `key_func(state)`. If `key_func` returns the same key
   for two different states, you get a stale cache hit. Make
   `key_func` exact.
10. **`retry=RetryPolicy(...)`** retries the node, not the
    LLM call inside the node. If your node is "call the
    model and parse the output," the retry re-does the
    whole node. Use `with_retry` on the model itself for
    cheaper retries.

---

## 12. What to read next

- [04-command-and-control-flow.md](04-command-and-control-flow.md)
  — `Command` for dynamic control flow from inside a node.
- [05-toolnode-and-tools_condition.md](05-toolnode-and-tools_condition.md)
  — the standard tool-routing pattern.
- [06-subgraphs-and-map-reduce.md](06-subgraphs-and-map-reduce.md)
  — `Send` for fan-out, subgraphs for nesting.
- [11-deployment-and-debug.md](11-deployment-and-debug.md) —
  `recursion_limit`, debugging cycles.
- LangGraph graph API: <https://langchain-ai.github.io/langgraph/reference/graphs/>
