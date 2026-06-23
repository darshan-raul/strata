# LangGraph — State & Reducers

> **Part 2 of the LangGraph deep-dive.** The `TypedDict` state
> schema, channel semantics, the `add_messages` reducer, custom
> reducers, `state_schema` / `input_schema` / `output_schema`,
> and the runtime `Context` separate from state.

State is the only thing that flows through the graph. Every
node reads from it and returns a partial update. The framework
merges the update using **reducers** (one per state field). This
file is about how the state schema and reducers work.

---

## 1. The state schema — `TypedDict`

```python
from typing import Annotated
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_id: str
    thread_id: str
    pending_action: dict | None
```

`TypedDict` because Python's structural typing plays well with
Pydantic and because the keys are strings, which is what
LangGraph needs.

### `total=False` — all keys are optional

With `total=False`, a node can return a partial update
containing only some fields, and the framework doesn't error
about missing keys. This is the right default for state
machines.

If you use `total=True` (the default for `TypedDict`), every
key is required and the framework checks for completeness on
every update. This is the right choice for a strict schema but
is usually more trouble than it's worth.

### The `Annotated[T, reducer]` syntax

```python
class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_id: str
```

`Annotated[T, reducer]` is how you attach a reducer to a field.
The reducer is a function `(current, update) -> new` that
decides how a partial update merges into the existing value.

Without `Annotated` (i.e. `messages: list`), the default reducer
is "overwrite." For a `messages` field, that's almost always
wrong — you'd lose the conversation history on every node.

---

## 2. `add_messages` — the standard message reducer

```python
from langgraph.graph.message import add_messages

class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
```

The signature:

```python
def add_messages(
    left: list[BaseMessage],
    right: list[BaseMessage] | BaseMessage | RemoveMessage,
) -> list[BaseMessage]:
    """Append right to left. If right is a single message, wrap it.
    If right contains a RemoveMessage, delete the matching id.
    Deduplicate by id: if a message in right has the same id as
    one in left, the right one wins (replaces)."""
```

### What it does

| Update | Effect |
|---|---|
| `[HumanMessage(content="hi")]` | Append to `left`. |
| `HumanMessage(content="hi")` (single) | Wrap in list, append. |
| `[AIMessage(content="x", id="m-1")]` where `left` already has `id="m-1"` | Replace the old message in `left` with the new one. |
| `[RemoveMessage(id="m-1")]` | Delete `id="m-1"` from `left`. |
| `[AIMessageChunk(content="ab"), AIMessageChunk(content="cd")]` | Accumulate (use `+` on chunks) and append the merged `AIMessage`. |

### Why dedup matters

Streaming emits `AIMessageChunk`s. The accumulator merges them
into a single `AIMessage` with one `id`. If the framework
appended chunks individually, you'd have N messages in the
state, one per chunk. `add_messages` de-duplicates by `id` so
only the merged one survives.

### Why `RemoveMessage` matters

In a long-running conversation, the message list grows. To
trim, append a `RemoveMessage` with the `id` of the message to
delete. `add_messages` honors it.

```python
def trim(state):
    msgs = state["messages"]
    return {"messages": [RemoveMessage(id=m.id) for m in msgs[:-10]]}
```

### Why `RemoveMessage` is a message, not a state field

A separate "trash" field would be awkward — the framework
would have to read it and clean up after every node. Using a
`RemoveMessage` makes "delete this" part of the message
semantics; the reducer handles it inline.

### Initial state and `add_messages`

The initial state for an invocation is whatever the caller
passes. `add_messages` merges it with the existing state
(checkpointed state, if a checkpointer is in use). For a fresh
invocation with no checkpointer, "existing" is empty, so the
initial messages just become the state's `messages`.

---

## 3. `MessagesState` — the prebuilt

```python
from langgraph.graph import MessagesState

class MyState(MessagesState):
    user_id: str
    # `messages` is inherited with the add_messages reducer
```

`MessagesState` is a prebuilt `TypedDict` with the `messages`
field already configured. Use it for the common case where
your state is "messages + a few extra fields."

---

## 4. Custom reducers

```python
def merge_dicts(left: dict, right: dict) -> dict:
    return {**left, **right}    # right wins on key collisions

class State(TypedDict, total=False):
    config: Annotated[dict, merge_dicts]
```

Custom reducers are useful for:

- **Merge dicts** — accumulate config from multiple nodes.
- **Append to a list** — a general "add to list" reducer (not
  just messages).
- **Custom overwrite logic** — e.g. "always take the larger
  value."
- **Concat strings** — accumulate a log.

The signature is `(current, update) -> new`. The framework
calls it with the current state value and the new partial.

### Operator reducers

```python
import operator

class State(TypedDict, total=False):
    counter: Annotated[int, operator.add]
    flags:   Annotated[set[str], operator.or_]
```

You can use any binary operator as a reducer. The framework
imports the operator and calls `op(current, update)`. Common
choices:

- `operator.add` — sum ints, concat lists, concat strings.
- `operator.or_` — set union, dict union (bitwise).
- `operator.and_` — set intersection.
- `operator.mul` — multiplication (rare).

**Caveat:** `operator.add` on two lists *concatenates*, not
appends. If you have a list of dicts and want to add one dict,
`operator.add` will give you `[...existing, new_dict]`. That's
the right behavior for "append."

### `OverwriteState` — the escape hatch

```python
from langgraph.types import OverwriteState

def replace_messages(state):
    return {"messages": OverwriteState([HumanMessage(content="fresh start")])}
```

`OverwriteState(value)` says "ignore the current value, just
use this." Use it sparingly. The `add_messages` reducer is
correct 99% of the time; reaching for `OverwriteState` usually
means a design rethink.

### `BinaryOperatorAggregate` — explicit operator reducers

```python
from langgraph.types import BinaryOperatorAggregate

class State(TypedDict, total=False):
    log: Annotated[list[str], BinaryOperatorAggregate(operator.add)]
```

Same as `operator.add` but explicit. Useful for clarity in
team code.

---

## 5. `state_schema`, `input_schema`, `output_schema`

The full state can be split into three schemas:

```python
class FullState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_id: str
    internal_notes: list[str]
    debug_info: dict

class InputState(TypedDict, total=False):
    messages: Annotated[list, add_messages]   # only the input field
    user_id: str

class OutputState(TypedDict, total=False):
    messages: Annotated[list, add_messages]   # the final messages
    # user_id is hidden
    # internal_notes is hidden
    # debug_info is hidden

graph = StateGraph(
    state_schema=FullState,        # the internal state
    input_schema=InputState,       # what callers can pass in
    output_schema=OutputState,     # what's in the result
)
```

- **`state_schema`** — the full state, all fields. Nodes see
  this.
- **`input_schema`** — what callers can pass to
  `graph.invoke(input)`. Stricter than `state_schema`. The
  framework filters input to match this schema before
  applying.
- **`output_schema`** — what's in the result. The framework
  filters the final state to match this schema before
  returning to the caller.

This is the API for "I have private internal state, but I
don't want it in the response." Strata's `debug_info` or
`internal_notes` would be in `state_schema` only, hidden from
callers.

### When to use them

- **Just `state_schema`** — fine for most cases. Strata's
  Phase 2 does this.
- **Adding `output_schema`** — when you want to strip internal
  state from the response (Phase 4+ RAG, where the internal
  state has retrieved docs and citations that shouldn't leak).
- **Adding `input_schema`** — when you want strict input
  validation. Less common.

---

## 6. Runtime context — separate from state

```python
from langgraph.runtime import Runtime
from dataclasses import dataclass

@dataclass
class Context:
    user_id: str
    request_id: str
    db: "Database"

def my_node(state: AgentState, runtime: Runtime[Context]) -> dict:
    # runtime.context is the read-only Context object
    user_id = runtime.context.user_id
    return {"user_id": user_id}
```

The runtime context is **read-only** — it doesn't go through
reducers, doesn't get persisted, and is just there for nodes
that need access to "things from outside the graph"
(connection pools, user id, request id, feature flags).

Differences from state:

| | State | Runtime context |
|---|---|---|
| Mutable | Yes (via reducers) | No |
| Persisted | Yes (with checkpointer) | No |
| Pass to `graph.invoke(input, context=...)` | No | Yes |
| Visible in `get_state` | Yes | No |
| Goes through reducers | Yes | No |

### How to pass context

```python
graph.invoke(
    input_state,
    context=Context(user_id="user-42", request_id="req-123", db=db),
)
```

The `context=` kwarg is the public API. The graph fills in
`runtime.context` for every node.

### Why context, not state

For things that don't change during the graph run (user id,
DB client, request id), the reducer machinery is overhead. The
context is a fast, read-only side-channel.

For things that DO change (the message list, the pending
action, the iteration count), use state.

---

## 7. `config["configurable"]` — another side-channel

Older LangGraph code (and many tutorials) uses
`config["configurable"]` instead of `runtime.context`. Both
work; context is the newer, more typesafe form.

```python
# Old way:
def my_node(state: AgentState, config: RunnableConfig) -> dict:
    user_id = config["configurable"]["user_id"]
    ...

graph.invoke(input_state, config={"configurable": {"user_id": "user-42"}})
```

The configurable dict is also where the checkpointer reads
`thread_id`. Mixed use is common.

Strata uses `runtime.context` for new code (Phase 4+); older
code may still use `config["configurable"]`.

---

## 8. Reading state in nodes

A node's signature can be:

```python
# Just state
def node1(state: AgentState) -> dict: ...

# State + config
def node2(state: AgentState, config: RunnableConfig) -> dict: ...

# State + runtime context
def node3(state: AgentState, runtime: Runtime[Context]) -> dict: ...

# All three
def node4(state: AgentState, config: RunnableConfig, runtime: Runtime[Context]) -> dict: ...
```

The framework detects the signature and fills in the right
arguments. You can name the parameters however you like (as
long as the type annotations are correct).

### Reading specific fields

```python
def my_node(state: AgentState) -> dict:
    last_msg = state["messages"][-1]
    user_id = state.get("user_id", "anonymous")
    pending = state.get("pending_action")
    return ...
```

Use `.get(key, default)` for fields that might not be set
(common with `total=False` schemas).

### Don't mutate state

```python
# WRONG
def my_node(state: AgentState) -> dict:
    state["messages"].append(AIMessage(content="..."))    # mutation!
    return state

# RIGHT
def my_node(state: AgentState) -> dict:
    return {"messages": [AIMessage(content="...")]}    # partial update
```

The framework owns the state object. If you mutate it, the
reducer doesn't run, the checkpointer sees the wrong state,
and downstream nodes see your mutations plus their own
updates — undefined behavior.

---

## 9. Returning a partial update

```python
return {"messages": [AIMessage(content="...")]}
```

The returned dict has only the fields the node wants to
change. Fields it omits are not touched.

```python
# This is fine:
return {"messages": [AIMessage(content="...")]}

# This is also fine:
return {"messages": [AIMessage(content="...")], "user_id": "user-42"}

# This is also fine:
return {"messages": AIMessage(content="...")}    # bare message, wrapped by add_messages
```

The framework runs the appropriate reducer for each field
present in the update.

### Bare messages are wrapped

If you return `AIMessage(content="...")`, `add_messages` (or
any list-typed reducer) treats it as `[AIMessage(content="...")]`.
Most reducers do this. If a custom reducer doesn't, wrap
explicitly.

### Returning a list of mixed types

```python
return {
    "messages": [
        SystemMessage(content="Use these docs..."),    # injected context
        RemoveMessage(id="old-msg-id"),                # delete an old message
        AIMessage(content="final answer"),             # the new answer
    ]
}
```

A node can return multiple message updates in one return.
`add_messages` processes them in order: append the new
messages, delete the marked ones. The system message above
would land in state before the AI message, so the model sees
"Use these docs... final answer" — but wait, the model already
produced "final answer" (this is the node return after the
model call). The system message would be a new instruction
that affects the *next* model call.

---

## 10. Common pitfalls

1. **Forgetting `Annotated[list, add_messages]`.** Without
   the reducer, `messages` gets overwritten on every node
   return. Conversation history is lost.
2. **Mutating `state["messages"]` in place.** Don't. The
   framework owns the state.
3. **`total=True` when you want partial updates.** Use
   `total=False` for the common case.
4. **Returning the full state instead of a partial update.**
   Wasteful, breaks the reducer semantics.
5. **Mixing `Runtime` and `config["configurable"]`.** Both
   work; pick one per project. Strata uses `Runtime` for
   new code.
6. **`RemoveMessage` is consumed by `add_messages`.** Once
   applied, the message is gone. Don't use it for "soft
   delete" — use a flag.
7. **Reducers run on every partial update, not just on
   `messages`.** If your field has a side-effecting reducer
   (writes to a DB, say), it runs every time the field is
   in the update. Refactor.
8. **State is JSON-serializable for the checkpointer.**
   If you put a non-serializable object in state (a
   `httpx.AsyncClient`, a `PIL.Image`), the checkpointer
   fails to save. Use the runtime context for those.
9. **`input_schema` filters but doesn't validate.** A
   `TypedDict` is structural. For strict input validation,
   use a Pydantic model (Phase 4+).
10. **Custom reducers must be deterministic.** If they
    depend on external state (time, random), the checkpointer
    can't replay the graph correctly.

---

## 11. What to read next

- [03-nodes-and-edges.md](03-nodes-and-edges.md) — what nodes
  do, what edges do.
- [04-command-and-control-flow.md](04-command-and-control-flow.md)
  — `Command(goto, update, resume)`.
- [08-checkpoints-and-persistence.md](08-checkpoints-and-persistence.md)
  — what gets persisted and how.
- [09-memory-store.md](09-memory-store.md) — long-term memory
  (different from the in-graph state).
- LangGraph state docs: <https://langchain-ai.github.io/langgraph/concepts/low_level/>
