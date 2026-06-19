# LangGraph — Deployment & Debug

> **Part 11 of the LangGraph deep-dive.** `recursion_limit`,
> `durability` modes, the LangGraph CLI (`langgraph dev`,
> `langgraph build`), LangGraph Studio, debugging recipes, and
> common runtime errors.

This file covers the operational side: how to run a graph
in dev, how to debug when it goes wrong, and how to package
for deployment.

---

## 1. `recursion_limit` — the cycle guard

```python
app = graph.compile(recursion_limit=50)
```

The graph stops if it has executed more than `recursion_limit`
super-steps. Default is 25. A "super-step" is one node
execution; conditional edges that produce multiple targets
count once per target.

### When you hit it

```python
graph.GraphRecursionError: Recursion limit of 25 reached without convergence.
```

The graph has run too many nodes. Either:

- The agent loop is genuinely looping (the model keeps
  calling tools without converging).
- The cycle is intentional but `recursion_limit` is too low
  for your use case.

### How to fix

For runaway loops:

- Check the model's tool calls. If it's calling `list_clusters`
  repeatedly, the prompt might be wrong.
- Add a "give up after N attempts" node that returns
  `Command(goto=END)`.
- Use `with_structured_output` to force the model to commit
  to a final answer.

For legitimate long cycles:

- Bump `recursion_limit` to a higher value.
- Or: design the graph to terminate naturally (a node that
  decides "done" based on a counter).

### Per-invocation override

```python
result = graph.invoke(input, config={"recursion_limit": 100})
```

The kwarg overrides the compile-time default.

### Strata's plan

Phase 2: no checkpointer, no `recursion_limit` overrides
needed. The graph runs synchronously per request; if it
loops, the request times out.

Phase 6+: set `recursion_limit=50` (slightly above the
default). The mutation-tool flow has a max of 1 confirmation
cycle; the RAG retrieve node runs at most once. Loops
shouldn't exceed 10 nodes in normal flow.

---

## 2. `durability` modes (v0.3+)

```python
app = graph.compile(
    checkpointer=cp,
    durability="sync",    # "sync" | "async" | "exit"
)
```

| Mode | When checkpoints are written |
|---|---|
| `"sync"` (default) | After every node, synchronously. Slower but durable. |
| `"async"` | In the background. Faster; small window of state loss on crash. |
| `"exit"` | Only when the graph exits. Fastest; no intermediate state. |

### When to use which

- **`"sync"`** — HITL flows, financial transactions,
  anything where losing a state mid-run is unacceptable.
- **`"async"`** — high-throughput RAG, batch processing.
- **`"exit"`** — when you only care about the final state
  (e.g. one-shot generation).

Strata's Phase 6+ plan: `"sync"` for the agent-service.
The checkpointer writes are fast (Postgres on local network
in-cluster), and the durability is worth the small latency.

---

## 3. `langgraph dev` — the local dev server

```bash
langgraph dev
```

Spins up a local server that:

- Loads `langgraph.json` (graph config).
- Serves the graph over HTTP (OpenAI-compatible and
  LangGraph-specific).
- Hosts LangGraph Studio (visual debugger) on
  <http://localhost:8123>.

`langgraph.json` lists the graphs to serve:

```json
{
  "graphs": {
    "agent": "./app/graph.py:graph"
  },
  "env": ".env",
  "python_version": "3.12",
  "dependencies": ["."]
}
```

`"agent": "./app/graph.py:graph"` says "import `graph` from
`app/graph.py` and serve it as `agent`."

### `langgraph dev` vs. `make chat`

For Strata's Phase 2, `make chat` does the manual thing:
`kubectl port-forward + curl`. `langgraph dev` would be
similar but with a UI.

Phase 5+ might use `langgraph dev` as the dev-loop target.
For Phase 2, the k8s manifests + port-forward is the
target.

### `langgraph build` — Docker image

```bash
langgraph build -t my-graph:latest
```

Builds a Docker image with the graph + dependencies. The
image exposes a FastAPI server that runs the graph.

Used for LangGraph Platform (managed deployment). Strata
doesn't use this — we deploy the agent-service as a
standard k8s Deployment.

---

## 4. LangGraph Studio

The visual debugger. Connect to a running graph server
(local or remote), see:

- The graph topology (Mermaid rendering).
- The state at each step.
- The full event stream.
- Time travel controls (rewind to a checkpoint, re-run from
  there).
- Variable inspection.

For Strata's Phase 2, Studio is overkill. The author is
debugging with `print` and the pytest tests. Phase 5+ might
use Studio for "what did the graph do in that conversation?"

---

## 5. `graph.get_graph()` — inspection

```python
# ASCII:
print(graph.get_graph().print_ascii())

# Mermaid:
print(graph.get_graph().draw_mermaid())

# JSON (Studio-compatible):
import json
spec = graph.get_graph().to_json()
```

Use these in a REPL or test failure message. The Mermaid
output is the diagram you'd want in docs.

### `get_state` for the current state

```python
state = graph.get_state(config)
# state.values, state.next, state.interrupts, etc.
```

After an invocation, read the state to verify what happened.
This is the "I just ran the graph, what's the state now?"
query.

---

## 6. `astream_events` for debugging

```python
async for event in graph.astream_events(input, config, version="v2"):
    print(json.dumps({
        "event": event["event"],
        "name": event.get("name"),
        "data_keys": list(event.get("data", {}).keys()),
    }))
```

A wall of events. Filter for what you need:

```python
async for event in graph.astream_events(input, config, version="v2"):
    if event["event"] in ("on_chain_start", "on_chain_end"):
        print(f"{event['event']}: {event['name']}")
    elif event["event"] == "on_chat_model_end":
        u = event["data"]["output"].usage_metadata
        print(f"tokens: {u}")
    elif event["event"] == "on_tool_start":
        print(f"tool call: {event['name']}({event['data']['input']})")
    elif event["event"] == "on_tool_end":
        print(f"tool result: {event['data']['output']}")
```

This is the most powerful debug tool. Use it to see exactly
what the graph did.

---

## 7. Common runtime errors

### `GraphRecursionError`

```python
langgraph.errors.GraphRecursionError: Recursion limit of 25 reached.
```

Cycle is too long. Bump `recursion_limit` or fix the loop.

### `InvalidUpdateError`

```python
langgraph.errors.InvalidUpdateError: At key 'messages': Can receive only one of:
  - BaseMessage
  - dict (with 'messages' key and BaseMessage value)
  - tuple (message, message)
  - list[BaseMessage | dict | tuple]
```

A node returned an invalid `messages` update. Check the
type.

### `NodeInterrupt` (from a static interrupt)

```python
langgraph.errors.NodeInterrupt
```

The graph hit a static `interrupt_before` / `interrupt_after`.
The state has the pause. Inspect with `get_state`, resume
with `app.invoke(None, config)`.

### KeyError in a tool

A tool raised a `KeyError` (or any unhandled exception). With
`handle_tool_errors=True`, the error becomes a `ToolMessage`
in the state and the graph continues. With `False`, the
exception propagates and the graph fails.

### `MessageDidNotHaveToolCallId` (rare)

A `ToolMessage` was added to state without a `tool_call_id`.
The model's next call will be confused. Check that you're
not building `ToolMessage`s by hand.

---

## 8. The "is the graph working?" checklist

When something's wrong, check these in order:

1. **Does the graph compile?** `graph.compile()` should not
   error. Read the error message.
2. **Does the right tool get called?** Use
   `astream_events(..., include_types=["chat_model", "tool"])` to
   see the model's choices.
3. **Does the tool result get back to the model?** The
   `ToolMessage` should appear in the state. Check with
   `get_state(config)` after a run.
4. **Does the model use the result?** The final `AIMessage`
   should reference the tool result. If the model "ignores"
   the tool, the prompt is probably too vague.
5. **Is the system message correct?** The model's behavior
   follows from the system prompt. A typo or missing rule
   produces surprising behavior.
6. **Is `bind_tools` getting the right tools?** If the
   wrong tool is being called, the tool list is wrong.
7. **Is the routing working?** `stream_mode="updates"` shows
   what each node returned. The conditional edge router
   picks the next node. Verify the router's return values.
8. **Is the checkpointer writing?** Use the database
   directly (`psql` for Postgres) to see if checkpoints are
   landing.
9. **Is the LiteLLM proxy up?** `curl http://litellm:4000/health/liveliness`.
10. **Is the model's response sane?** `print(response.content)`
    in `call_model` to see what the model said.

---

## 9. Unit-test debugging

When a test fails:

```python
def test_x():
    result = graph.invoke(input, config)
    # Check the final state
    assert result["messages"][-1].content == "expected"
```

If the assertion fails, add print statements to nodes:

```python
def call_model(state: AgentState) -> dict:
    response = llm.invoke(state["messages"])
    print("MODEL SAYS:", response.content)
    print("TOOL CALLS:", response.tool_calls)
    return {"messages": [response]}
```

Or, better, use the fake chat model so the test is
deterministic (see
[`../langchain/08-testing-and-pitfalls.md`](../langchain/08-testing-and-pitfalls.md)).

---

## 10. Production debugging

In production, you don't have `print` statements. Use:

- **Structured logs** — the agent-service logs each node's
  start and end.
- **Metrics** — Prometheus in Phase 6+. Latency, error rate,
  token counts.
- **Tracing** — LangSmith or OTel. See the full request tree.
- **Sampling** — log 1% of requests in full detail, 100% in
  summary. Don't fill your disk with full traces.

For Strata's Phase 6+:
- The agent-service Deployment has a `LOG_LEVEL=INFO` env var.
- A `BaseCallbackHandler` writes `usage_metadata` to Postgres
  for cost tracking.
- LiteLLM is the bottleneck; its logs are the primary debug
  surface for model issues.

---

## 11. Performance tips

- **Avoid re-running nodes unnecessarily.** Use
  `cache_policy` on nodes that are pure functions of their
  input.
- **Stream early.** `astream_events` lets the UI show
  progress while the graph is still running.
- **Use async where it helps.** `ainvoke` and `astream` don't
  block the event loop. For high-concurrency, this is
  significant.
- **Bound the work.** `recursion_limit` is your friend. Don't
  let the model run 1000 tool calls.
- **Tune the model.** A faster model (`gpt-4o-mini`,
  `claude-3-5-haiku`) might be good enough for the read
  path. Reserve the big model for hard queries.
- **Cache the system prompt.** If you're injecting a 4k
  system prompt every turn, prompt caching (Bedrock) saves
  real money.

---

## 12. The dev loop

Strata's Phase 2 dev loop:

```bash
# 1. Apply manifests:
make apply

# 2. Tail logs:
make logs-agent

# 3. Make a request:
make chat
# (This does: port-forward + curl POST /chat)

# 4. Iterate:
# - Edit app/main.py or app/graph.py
# - make build (rebuilds image)
# - make apply-agent (rolls the deployment)
# - make chat
```

The iteration is slower than `langgraph dev` but matches
production deployment. Use `langgraph dev` for quick local
iteration; use the k8s loop for "is this the same as what
will run in production?"

---

## 13. Common pitfalls

1. **`recursion_limit` is per-invocation, not per-graph.** A
   re-invocation with a new config has its own limit.
2. **`durability="exit"` for HITL flows.** The graph doesn't
   write the state at the interrupt. The pause can't be
   resumed. Use `"sync"`.
3. **`langgraph dev` uses a separate env.** The `.env` file
   in your project is loaded; env vars in your shell are
   not. Make sure secrets are in `.env`.
4. **LangGraph Studio requires a running graph server.**
   Connect to `langgraph dev` or to a remote deployment. The
   studio itself is a UI, not a runner.
5. **Mermaid diagrams get long.** For a 20-node graph, the
   Mermaid output is unwieldy. Use subgraphs to group, or
   use `get_subgraph()` to inspect parts.
6. **The state inspector in Studio shows the latest
   checkpoint, not live state.** If the graph is running,
   the inspector might lag.
7. **`stream_mode="debug"` is too verbose for production.**
   The amount of data is overwhelming. Use `"updates"` or
   `"events"` in prod.
8. **The `get_graph()` output is JSON-serializable.** You
   can save it to a file and re-render later. Useful for
   "graph version" tracking in git.

---

## 14. What to read next

- [08-checkpoints-and-persistence.md](08-checkpoints-and-persistence.md)
  — the checkpointer (production durability).
- [10-human-in-the-loop.md](10-human-in-the-loop.md) — the
  HITL flow, end to end.
- [`../langchain/08-testing-and-pitfalls.md`](../langchain/08-testing-and-pitfalls.md)
  — the test patterns that catch graph bugs.
- LangGraph Platform: <https://langchain-ai.github.io/langgraph/concepts/langgraph_platform/>
- LangGraph debugging: <https://langchain-ai.github.io/langgraph/concepts/debugging/>
