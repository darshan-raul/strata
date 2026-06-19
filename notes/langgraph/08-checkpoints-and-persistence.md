# LangGraph — Checkpoints & Persistence

> **Part 8 of the LangGraph deep-dive.** `MemorySaver`,
> `SqliteSaver`, `PostgresSaver`, threads, `get_state`,
> `get_state_history`, time travel via `update_state`,
> durability modes (v0.3+).

A checkpointer is what makes a LangGraph graph **durable**:
state is saved to a backend after every node, so the graph
can be paused, resumed, and rewound. Phase 2 doesn't use a
checkpointer (state lives in memory for the duration of one
HTTP request). Phase 6+ uses `PostgresSaver` for production.

---

## 1. Why a checkpointer

Without one:

```python
result = graph.invoke(input)
# State lives in memory. Next call: new state. No history.
```

With one:

```python
graph = builder.compile(checkpointer=MemorySaver())

result = graph.invoke(input, config={"configurable": {"thread_id": "user-42"}})
# State saved. Next call with the same thread_id: continues from where it left off.

state = graph.get_state({"configurable": {"thread_id": "user-42"}})
# Read the current state.

for s in graph.get_state_history({"configurable": {"thread_id": "user-42"}}):
    # Walk the history. Time travel.
    ...
```

The checkpointer is what enables:

- **Multi-turn conversations** — same `thread_id` across
  invocations.
- **Human-in-the-loop** — `interrupt()` saves state; resume
  later.
- **Time travel** — `get_state_history`, `update_state`.
- **Production durability** — restart the agent-service,
  conversations continue from the last checkpoint.

---

## 2. The checkpointer implementations

| Class | Backend | When to use |
|---|---|---|
| `MemorySaver` | Python dict | Dev, tests, single-process. Lost on restart. |
| `SqliteSaver` | SQLite file | Local dev with persistence. Single-process. |
| `AsyncSqliteSaver` | SQLite (async API) | Same, async. |
| `PostgresSaver` | Postgres | Production, multi-process, multi-host. |
| `AsyncPostgresSaver` | Postgres (async API) | Same, async. |

### `MemorySaver` — dev / Phase 2

```python
from langgraph.checkpoint.memory import MemorySaver

graph = builder.compile(checkpointer=MemorySaver())
```

State is in a `dict[thread_id, State]`. Lost on restart. Good
for tests, demos, single-process dev. Strata's Phase 2 doesn't
use this (no multi-turn); Phase 2's graph lives for one HTTP
request.

### `SqliteSaver` — local dev with persistence

```python
from langgraph.checkpoint.sqlite import SqliteSaver

graph = builder.compile(checkpointer=SqliteSaver.from_conn_string("checkpoints.db"))
```

The SQLite file is on disk. Survives restarts. Useful for
"the dev loop survived my Ctrl-C." Async variant:
`AsyncSqliteSaver`.

### `PostgresSaver` — production

```python
from langgraph.checkpoint.postgres import PostgresSaver

graph = builder.compile(
    checkpointer=PostgresSaver.from_conn_string(
        "postgresql://user:pass@host:5432/langgraph"
    )
)
```

CloudNativePG-managed Postgres in-cluster. Shared across all
agent-service replicas. The checkpointer table gets created
automatically on first use.

For Strata Phase 6+: a `Secret` resource with the Postgres
DSN, mounted as `LANGGRAPH_CHECKPOINT_DB_URL`. The
agent-service Deployment sets the env var.

#### `AsyncPostgresSaver` — async API

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(...) as cp:
    graph = builder.compile(checkpointer=cp)
    result = await graph.ainvoke(input, config)
```

The async variant is what the FastAPI app uses. Same backend,
async API.

### Migration setup

The `PostgresSaver` creates the required tables on first use
(via `cp.setup()`). For production, run this once at
deployment time:

```python
async with AsyncPostgresSaver.from_conn_string(...) as cp:
    await cp.setup()
```

In the Strata Deployment, this is a Job that runs once at
install time.

---

## 3. Threads — `thread_id` and the `configurable` dict

Every persistent invocation has a `thread_id` in its config:

```python
config = {"configurable": {"thread_id": "user-42"}}
result = graph.invoke(input, config)
```

The checkpointer keys on `thread_id`. Different threads have
different state. The thread id is opaque — a user id, a
session id, a conversation id, whatever makes sense.

### Multiple threads per user

```python
config_session_1 = {"configurable": {"thread_id": "user-42:session-1"}}
config_session_2 = {"configurable": {"thread_id": "user-42:session-2"}}
```

Strata's CLI uses a thread id per conversation. The web UI
(Phase 5+) does the same. The checkpointer doesn't care
about the format.

### `configurable` namespace

The `configurable` dict is the public namespace for "things
that get looked up at runtime." Beyond `thread_id`, you can
put:

- `user_id` — for the runtime context to read.
- `model_name` — for `configurable_fields` on a model.
- Custom keys your nodes/tools read via `runtime.config["configurable"]`.

The checkpointer uses `thread_id`. Other keys are ignored by
the checkpointer but visible to nodes and tools.

---

## 4. Reading state — `get_state`

```python
state = graph.get_state({"configurable": {"thread_id": "user-42"}})
# state.values        — the current state dict
# state.next          — tuple of next nodes to run
# state.config        — the config used
# state.metadata      — checkpoint metadata (step, run_id, etc.)
# state.created_at    — when the checkpoint was created
# state.parent_config — the previous checkpoint's config
# state.tasks         — pending tasks (for interrupted runs)
# state.interrupts    — tuple of (Interrupt(value, id)) for paused runs
```

`state.values` is what you usually want. The full state
dict, same shape as the `state_schema`.

### `state.next` — what runs next

```python
state = graph.get_state(config)
print(state.next)    # ('call_model',) — call_model is next
                     # ()              — graph has ended
                     # ('mutation_handler',) — paused before mutation_handler
                     # (Interrupt(...),)     — paused at an interrupt
```

`state.next` is empty if the graph ended. It's a tuple of
node names if the graph is in the middle of a run. If the
graph was compiled with `interrupt_before`, the next node
is the one the graph would run, and the run is paused.

### `state.interrupts` — paused for HITL

```python
state = graph.get_state(config)
if state.interrupts:
    for interrupt_obj in state.interrupts:
        prompt = interrupt_obj.value    # what was passed to interrupt()
        interrupt_id = interrupt_obj.id
        # Show the user the prompt
```

This is the public API for "the graph is paused, what do I
show the user?"

---

## 5. Walking history — `get_state_history`

```python
history = list(graph.get_state_history({"configurable": {"thread_id": "user-42"}}))
```

Returns the checkpoints in reverse chronological order (newest
first). Each checkpoint is a `StateSnapshot` with the same
fields as `get_state`.

Use cases:

- **UI "show me the last 10 messages"** — read the current
  state.
- **Debugging "when did the model call that tool?"** — walk
  the history, find the checkpoint where the tool call
  happened.
- **Time travel "rewind to before the mutation"** — see
  below.

### Filtering the history

```python
for s in graph.get_state_history(config, limit=10):
    print(s.created_at, s.next)
```

`limit` truncates. There's no built-in filter by date or by
node; iterate and filter in Python.

---

## 6. Time travel — `update_state`

```python
# Rewind the conversation to before a specific message:
state = graph.get_state(config)
# Find the checkpoint that has the message you want to remove:
target = next(s for s in graph.get_state_history(config) if has_bad_message(s))

# Update the state at that checkpoint:
graph.update_state(
    target.config,
    values={"messages": [RemoveMessage(id="bad-msg-id")]},
)
```

`update_state(config, values)` writes a new state at the
given checkpoint. The next `graph.invoke(...)` with the same
thread id starts from this new state.

This is the "rewind and re-run" pattern. The checkpointer
treats the new state as a new checkpoint in the history.

### `update_state` with `as_node`

```python
graph.update_state(
    config,
    values={"messages": [AIMessage(content="...", tool_calls=[ToolCall(name="list_clusters", args={}, id="forced-1")])]},
    as_node="call_model",    # pretend this update came from call_model
)
```

`as_node` makes the update look like it was produced by a
specific node. The graph then routes from that node
(according to the conditional edge). Useful for "I want the
graph to think this came from the model" (e.g. seeding a
conversation with a fake AI response).

### `update_state` for testing

In tests, `update_state` lets you set up a state without
running the graph:

```python
def test_resume_from_interrupt():
    # Set up the state as if the graph had paused at the interrupt
    graph.update_state(
        config,
        values={"messages": [HumanMessage(content="delete cl-001")]},
        as_node="__start__",
    )
    # Now invoke: the graph runs from this state, hits the interrupt.
    result = graph.invoke(None, config)
    # Verify the prompt
    assert result["__interrupt__"][0].value["type"] == "confirm_mutation"
```

---

## 7. `durability` modes (v0.3+)

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

For Strata's Phase 6+ mutation-tool flow, `"sync"` is the
right choice (you don't want to lose the state mid-conversation).
For high-throughput but loss-tolerant flows (e.g. RAG with
lots of retrieve calls), `"async"` is fine.

---

## 8. What gets persisted

For a typical `AgentState` with `messages: Annotated[list, add_messages]`:

```json
{
  "thread_id": "user-42",
  "checkpoint_id": "...",
  "parent_checkpoint_id": "...",
  "values": {
    "messages": [...],
    "user_id": "user-42",
    "thread_id": "user-42"
  },
  "next": ["call_model"],
  "metadata": {
    "step": 3,
    "runs": [{"id": "...", "name": "call_model"}]
  }
}
```

The full state is stored. The reducers determine what
`values["messages"]` contains.

### What's NOT persisted

- The runtime context (`runtime.context`). It's passed per
  invocation, not stored.
- The compiled graph. It must be rebuilt on restart.
- The checkpointer object. It must be re-initialized on
  restart (the tables persist; the in-process client doesn't).

---

## 9. Async vs sync

| | Sync | Async |
|---|---|---|
| `MemorySaver` | `MemorySaver()` | (no async variant) |
| `SqliteSaver` | `SqliteSaver.from_conn_string(...)` | `AsyncSqliteSaver.from_conn_string(...)` |
| `PostgresSaver` | `PostgresSaver.from_conn_string(...)` | `AsyncPostgresSaver.from_conn_string(...)` |
| `invoke` | `graph.invoke(...)` | `graph.ainvoke(...)` |
| `get_state` | `graph.get_state(...)` | `graph.aget_state(...)` |
| `get_state_history` | `graph.get_state_history(...)` | `graph.aget_state_history(...)` |
| `update_state` | `graph.update_state(...)` | `graph.aupdate_state(...)` |

For FastAPI, use the async variants.

---

## 10. Checkpoint namespaces

The checkpointer has a concept of namespaces for organizing
checkpoints (e.g. one per workflow type). Set via the
config:

```python
config = {
    "configurable": {
        "thread_id": "user-42",
        "checkpoint_ns": "agent-v1",
    }
}
```

Namespaces are useful when one thread id is used for multiple
graphs (e.g. user-42's "main agent" vs "summarization agent").
Strata doesn't need this in Phase 2-6.

---

## 11. Common pitfalls

1. **Forgetting `config={"configurable": {"thread_id": ...}}`.**
   Without a thread id, the checkpointer errors (or, for
   `MemorySaver`, silently uses a default).
2. **Different thread ids for the same conversation.** A
   typo or a code change silently breaks persistence. Make
   sure the CLI / web / API agree on the format.
3. **State field not JSON-serializable.** The checkpointer
   stores state as JSON. Pydantic models, datetime, custom
   classes — must be JSON-serializable, or the checkpoint
   write fails.
4. **Checkpointer not initialized.** `PostgresSaver` requires
   `cp.setup()` (creates the tables). Without it, the first
   write fails.
5. **`update_state` with `as_node` for nodes that don't
   exist.** The graph can't "pretend" the update came from
   a non-existent node. Compile error.
6. **`durability="exit"` for HITL flows.** The graph ends
   after an interrupt. If the checkpointer doesn't write
   intermediate state, the interrupt can't be resumed. Use
   `"sync"` or `"async"`.
7. **Async/sync mismatch.** If you compiled with
   `AsyncPostgresSaver`, use `ainvoke`. Mixing fails.
8. **`MemorySaver` is lost on restart.** Don't use it for
   production conversations.
9. **`SqliteSaver` is single-process.** Two agent-service
   replicas writing to the same SQLite file corrupt it. Use
   `PostgresSaver` for multi-replica deployments.
10. **`get_state` returns a snapshot, not a live view.** If
    the state changes (another invocation on the same
    thread), the snapshot is stale.

---

## 12. What to read next

- [09-memory-store.md](09-memory-store.md) — long-term memory
  across threads.
- [10-human-in-the-loop.md](10-human-in-the-loop.md) — the
  HITL flow, end to end.
- [11-deployment-and-debug.md](11-deployment-and-debug.md) —
  production deployment, debugging.
- LangGraph persistence: <https://langchain-ai.github.io/langgraph/concepts/persistence/>
