# LangGraph — Subgraphs & Map-Reduce

> **Part 6 of the LangGraph deep-dive.** Composing graphs as
> nodes, state isolation and mapping, `Command.PARENT`, the
> `Send` pattern for fan-out, and parallel branch joining.

When a single `StateGraph` isn't enough — because you have
recurring sub-flows, multi-agent hand-offs, or map-reduce over
a list — you reach for subgraphs and `Send`. This file covers
both.

---

## 1. Subgraphs — a graph as a node

A compiled `StateGraph` can be added to another graph as a
node. The inner graph has its own state, its own nodes, its
own edges. The outer graph sees it as a black box.

```python
# Inner graph
subgraph = StateGraph(SubState)
subgraph.add_node("a", node_a)
subgraph.add_node("b", node_b)
subgraph.add_edge(START, "a")
subgraph.add_edge("a", "b")
subgraph.add_edge("b", END)
sub_app = subgraph.compile()

# Outer graph
graph = StateGraph(OuterState)
graph.add_node("run_sub", sub_app)    # subgraph as a node
graph.add_edge(START, "run_sub")
graph.add_edge("run_sub", END)

app = graph.compile()
```

When the outer graph runs, it reaches `run_sub`, which is
itself a graph. The inner graph runs to completion. The outer
graph continues.

### State isolation

The inner graph has its own `State` schema. The fields don't
have to match the outer graph's. The inner graph doesn't see
the outer graph's state by default.

```python
class OuterState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_id: str

class SubState(TypedDict, total=False):
    docs: list[dict]
    summary: str
```

The inner graph sees only `docs` and `summary`. The outer
graph sees only `messages` and `user_id`. They share the
messages reducer because both use `add_messages`, but the
field is "messages" in both, so the framework's reducer
machinery works.

### State mapping — `input` and `output` schemas (0.3+)

If the inner and outer states are different, you need to
map between them. The cleanest way (0.3+) is `input` and
`output` on the `add_node` call:

```python
class OuterState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    docs: list[dict]
    user_id: str

class SubInputState(TypedDict, total=False):
    docs: list[dict]    # only this field
    user_id: str

class SubOutputState(TypedDict, total=False):
    summary: str
    used_user_id: str

subgraph = StateGraph(SubState, input=SubInputState, output=SubOutputState)
# ... build the subgraph ...

graph.add_node(
    "run_sub",
    subgraph.compile(),
    input=lambda outer: {"docs": outer["docs"], "user_id": outer["user_id"]},
    output=lambda sub: {"summary": sub["summary"]},
)
```

The `input` callable maps outer state → subgraph input. The
`output` callable maps subgraph output → outer state. The
framework applies these on entry and exit.

### The legacy way — `Command.PARENT`

Before `input` / `output` were added, the way to map was via
`Command.PARENT`:

```python
def sub_node(state: SubState) -> list[Command]:
    # do work
    return [
        Command(update={"summary": "..."}),       # update sub state
        Command(
            update={"summary": "..."},
            graph=Command.PARENT,                  # update parent state
        ),
    ]
```

This is still supported. The `input` / `output` form is
cleaner for "I have a known input/output shape." The
`Command.PARENT` form is for "I want to dynamically update
both states from inside the subgraph."

### State isolation gotcha

If both graphs use the same field name (e.g. `messages`), the
inner graph's updates to that field merge with the outer
graph's state via the outer graph's reducer. So messages
flow in and out. If you want strict isolation, use different
field names.

For Strata, the message field is "messages" everywhere, so
messages flow naturally. The RAG subgraph (Phase 4+) reads
the user query from the parent's `messages` and writes
retrieved docs back. The parent's `add_messages` reducer
handles it.

---

## 2. `Command.PARENT` — reaching the parent

```python
def child_node(state: SubState) -> list[Command]:
    return [
        Command(update={"summary": "..."}),           # child state
        Command(
            update={"summary_for_parent": "..."},
            graph=Command.PARENT,                     # parent state
        ),
    ]
```

`Command.PARENT` is a special sentinel. The `update` applies
to the parent graph's state. The `goto` (if set) routes in
the parent graph.

Multiple `Command`s in a list are applied in order.

### When to use `Command.PARENT`

- The subgraph needs to mutate the parent state in a way
  that can't be expressed with `input` / `output` schemas.
- The subgraph's behavior is dynamic (different fields
  updated based on conditions).
- Legacy code (pre-0.3).

Strata's Phase 4+ RAG subgraph uses `Command.PARENT` to
inject retrieved docs into the parent's `messages` after the
retrieval node runs.

---

## 3. `Send` — fan-out for map-reduce

The `Send` primitive (covered briefly in
[03-nodes-and-edges.md](03-nodes-and-edges.md)) is the right
tool for "I have a list of N items, run this node N times in
parallel, then merge."

```python
from langgraph.types import Send

def route_to_summarize(state: AgentState) -> list[Send]:
    docs = state["retrieved_docs"]
    return [
        Send("summarize_doc", {"doc": doc, "idx": i})
        for i, doc in enumerate(docs)
    ]

graph.add_conditional_edges(
    "retrieve",
    route_to_summarize,
    ["summarize_doc"],    # the target node
)
graph.add_node("summarize_doc", summarize_one)
graph.add_edge("summarize_doc", "merge_summaries")
```

### The target node sees only the `Send` payload

```python
def summarize_one(payload: dict) -> dict:
    doc = payload["doc"]
    return {"summaries": [f"summary of {doc['id']}"]}
```

The target node's input is the `Send` payload (the dict you
passed), not the parent state. If the target needs the
parent state, pass the relevant fields through `Send`:

```python
return [
    Send("summarize_doc", {"doc": doc, "user_id": state["user_id"]})
    for doc in state["retrieved_docs"]
]
```

Or use the runtime context:

```python
def summarize_one(payload: dict, runtime: Runtime[Context]) -> dict:
    doc = payload["doc"]
    user_id = runtime.context.user_id
    return {"summaries": [f"summary for {user_id}: {doc['id']}"]}
```

### Joining the parallel branches

After all `Send` invocations of `summarize_doc` complete, the
graph continues from any node that has an edge from
`summarize_doc`. The reducer on the target field merges.

```python
class State(TypedDict, total=False):
    summaries: Annotated[list[str], operator.add]

def merge_summaries(state: AgentState) -> dict:
    return {"final_summary": "\n".join(state["summaries"])}
```

The `summaries` list grows by N (one per `Send`). The
`merge_summaries` node reads it.

### Ordering and concurrency

`Send` invocations run in parallel (as parallel as the
executor allows). The order of results in `state["summaries"]`
is the order of the `Send` list. Use a counter or sort key in
the payload if you need a specific order.

```python
return [
    Send("summarize_doc", {"doc": doc, "idx": i})
    for i, doc in enumerate(docs)
]

def summarize_one(payload):
    return {"summaries": [(payload["idx"], f"summary: {payload['doc']['id']}")]}

def merge_summaries(state):
    ordered = sorted(state["summaries"])    # by idx
    return {"final_summary": "\n".join(s for _, s in ordered)}
```

### Limits

If `Send` returns a list of 1000 `Send`s, the graph runs
1000 invocations of the target node. That's 1000 LLM calls
(if the target calls the LLM). Watch your token bill.

Strata's RAG (Phase 4+) uses `Send` for "summarize each
retrieved doc, then merge." The number of docs is bounded
by the retriever's `top_k` (default 5). Not a concern.

---

## 4. Parallel branches (no `Send`)

Sometimes you want fixed fan-out — a node that triggers two
specific nodes in parallel, both of which feed into a
joiner.

```python
# Graph:
#     start
#       │
#       ▼
#   ┌───┴───┐
#   ▼       ▼
#  left   right
#   │       │
#   └───┬───┘
#       ▼
#     join
#       │
#       ▼
#      END

graph.add_edge(START, "left")
graph.add_edge(START, "right")
graph.add_edge("left", "join")
graph.add_edge("right", "join")
graph.add_edge("join", END)
```

Both `left` and `right` run in parallel after `START`. The
`join` node runs after both complete. The reducer on the
relevant state field merges the results.

This is a DAG (no cycles). The framework runs it as parallel
as it can.

### Conditional parallel branches

```python
def route(state) -> list[str]:
    return ["left", "right"] if some_condition(state) else ["left"]

graph.add_conditional_edges(START, route, ["left", "right"])
```

The conditional edge returns a list of target nodes. The
framework runs all of them in parallel.

### Joins — when do they fire?

The join node (`join` in the example) fires when **all**
incoming edges have completed. If `left` and `right` both
have edges to `join`, `join` waits for both.

If only one of them runs (because the conditional edge
returned just `["left"]`), `join` fires after `left` only.

---

## 5. Multi-agent — subgraphs as agents

The cleanest multi-agent pattern: each agent is a compiled
graph with its own state. The orchestrator (another graph)
calls them.

```python
# EKS agent
eks_agent = StateGraph(AgentState)
eks_agent.add_node("call_model", call_eks_model)
eks_agent.add_node("tools", ToolNode(eks_tools))
# ... build the loop ...
eks_app = eks_agent.compile()

# Logs agent
logs_agent = StateGraph(AgentState)
# ... different model, different tools ...
logs_app = logs_agent.compile()

# Orchestrator
orchestrator = StateGraph(OrchestratorState)
orchestrator.add_node("eks_agent", eks_app)
orchestrator.add_node("logs_agent", logs_app)
# ... orchestrator routes to one or the other ...
orchestrator_app = orchestrator.compile()
```

Each agent has its own state (they might have different
fields). The orchestrator routes between them.

For Strata, multi-agent is overkill for the current design.
But if the platform grows (one agent per domain: networking,
security, cost, etc.), the subgraph pattern is the right
shape.

---

## 6. Subgraphs vs. `Send` vs. parallel branches

| Need | Use |
|---|---|
| One node runs N times in parallel, each with different input | `Send` |
| A graph is a node in another graph | Subgraph |
| A node triggers two specific nodes in parallel | Parallel branches (multiple fixed edges) |
| Multi-agent (each agent has its own state) | Subgraph |
| A node should run on a subset of state items | `Send` with filter logic |
| The inner graph has a known input/output shape | Subgraph with `input` / `output` schemas |
| The inner graph mutates the parent state dynamically | `Command.PARENT` |

---

## 7. Debugging subgraph state

`graph.get_state(config)` returns the outer's state. To see
the inner subgraph's state, you need the subgraph's config
(thread id is shared, but the sub-state address is different).

In LangGraph Studio, the state inspector shows both. In
code, `astream_events(..., subgraphs=True)` surfaces subgraph
events with their `parent_ids`.

```python
async for event in graph.astream_events(
    input, config, version="v2", subgraphs=True,
):
    if event["event"] == "on_chain_start":
        print(event["name"], event["parent_ids"])
```

The `parent_ids` trace the hierarchy. Subgraph events have
the subgraph's node id as a parent.

---

## 8. Common pitfalls

1. **State field name collisions** between the inner and
   outer graph merge via the outer's reducer. If you want
   isolation, use different field names.
2. **`Send` is a list, not a single value.** Returning a
   single `Send` from a conditional edge is a no-op. The
   list form is required.
3. **`Send` requires the path map to include the target
   node name.** `add_conditional_edges(source, router, [target_name])`.
4. **The target node of `Send` doesn't see the parent
   state** unless you pass it via the payload or runtime
   context.
5. **Subgraph state isn't visible in `get_state(config)`**
   without a special API. Use `subgraphs=True` in events
   or LangGraph Studio.
6. **`Command.PARENT` from a non-subgraph node is an error.**
   Only valid inside a node that's part of a subgraph.
7. **`input` / `output` schemas on `add_node` (0.3+)** must
   produce dicts that match the subgraph's input/output
   schema. If they don't, the graph errors at runtime.
8. **Subgraph compile is a `Pregel` object** that can be
   added to a parent. Make sure the `add_node` call takes
   the compiled subgraph, not the `StateGraph` instance.
9. **Parallel branches need a joiner.** If both `left` and
   `right` have edges to `END` (no joiner), the graph ends
   after the first one finishes. Add a joiner to wait for
   both.

---

## 9. What to read next

- [04-command-and-control-flow.md](04-command-and-control-flow.md)
  — `Command` for tool returns and `Command.PARENT`.
- [07-streaming.md](07-streaming.md) — streaming subgraphs
  and parallel branches.
- [11-deployment-and-debug.md](11-deployment-and-debug.md) —
  debugging subgraph state.
- LangGraph subgraphs: <https://langchain-ai.github.io/langgraph/concepts/subgraphs/>
