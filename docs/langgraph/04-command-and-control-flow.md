# LangGraph — `Command` & Control Flow

> **Part 4 of the LangGraph deep-dive.** `Command(goto, update,
> graph, resume)`, dynamic routing from inside a node, the
> `interrupt()` function (v0.2+), static interrupts
> (`interrupt_before` / `interrupt_after`).

Most of LangGraph is "edges are declared up front, the
framework picks which one to take." `Command` is the escape
hatch: a node can return a value that says "actually, go
*here* and update *these* fields." It also handles HITL: a
node can pause the graph with `interrupt()` and resume later
via `Command(resume=...)`.

---

## 1. `Command` — the return value

```python
from langgraph.types import Command
from langgraph.graph import END

def my_node(state: AgentState) -> Command:
    return Command(
        goto="summarize",    # next node
        update={"messages": [SystemMessage(content="...")]},    # partial state update
    )
```

`Command` is a return value that combines:

- **`goto`**: where to go next. A string node name, `END`, or
  a list of `Send` instances.
- **`update`**: the partial state update (same as a dict return).
- **`graph`**: `Command.PARENT` to route in the parent graph
  (subgraph case).
- **`resume`**: the value to resume an `interrupt()` (HITL case).

You can return a `Command` instead of a dict from any node.

### `Command` vs. a dict return

| | Dict return | `Command` |
|---|---|---|
| Partial state update | ✅ | ✅ |
| Specify next node | ❌ (edges decide) | ✅ |
| Go to a dynamic node | ❌ | ✅ |
| Resume from interrupt | ❌ | ✅ |
| Reach parent graph | ❌ | ✅ (`Command.PARENT`) |

Use a dict return for the common case. Use `Command` when you
need to do something the static edges can't.

---

## 2. Dynamic routing — `Command(goto=...)`

```python
def triage_node(state: AgentState) -> Command:
    last_msg = state["messages"][-1].content.lower()
    if "delete" in last_msg or "provision" in last_msg:
        return Command(goto="mutation_handler")
    return Command(goto="info_handler")
```

A node that decides which path to take, dynamically. The
target node must exist in the graph. The static edges from
`triage_node` are bypassed for this invocation.

### Combining `goto` and `update`

```python
def triage_node(state: AgentState) -> Command:
    return Command(
        goto="mutation_handler",
        update={
            "messages": [SystemMessage(content="Routing to mutation handler.")],
            "pending_action": {"type": "needs_confirmation", "action": "..."},
        },
    )
```

The next node sees the updated state. Standard semantics.

### `Command(goto=[...])` — multiple targets (fan-out)

```python
def fanout_node(state: AgentState) -> Command:
    return Command(
        goto=[
            Send("process_item", {"item": state["items"][0]}),
            Send("process_item", {"item": state["items"][1]}),
        ],
    )
```

`Send` instances in `goto` for map-reduce. See
[06-subgraphs-and-map-reduce.md](06-subgraphs-and-map-reduce.md)
for the full pattern.

### `Command(goto=END)`

```python
def early_exit(state: AgentState) -> Command:
    return Command(
        goto=END,
        update={"messages": [AIMessage(content="Sorry, can't help with that.")]},
    )
```

`END` is a sentinel. The graph stops; the final state is
returned.

---

## 3. `Command.PARENT` — reaching the parent graph

In a subgraph (a compiled `StateGraph` used as a node in
another), the subgraph has its own state. To update the
**parent's** state, use `Command.PARENT`:

```python
# Inside the subgraph
def child_node(state: ChildState) -> Command:
    return Command(
        goto="end_subgraph",
        update={
            "child_field": "new value",    # child's state
        },
        graph=Command.PARENT,    # also update parent's state
    )
```

The `update` applies to the child's state. The `graph=Command.PARENT`
part is a separate update that applies to the parent's state.
You'd need to provide both updates (or use two `Command`s in a
list — see below).

In practice, the cleanest pattern is to return a list of
`Command`s:

```python
def child_node(state: ChildState) -> list[Command]:
    return [
        Command(update={"child_field": "new"}),    # child
        Command(
            update={"parent_field": "new"},         # parent
            graph=Command.PARENT,
        ),
    ]
```

The first `Command` updates the child's state. The second
updates the parent's state via `Command.PARENT`. Both apply.

---

## 4. `interrupt()` — pause the graph (HITL)

The `interrupt()` function is a v0.2+ feature that lets a
node pause the graph and wait for external input. The
external input is provided via `Command(resume=...)` on the
next invocation.

```python
from langgraph.types import interrupt, Command

def mutation_handler(state: AgentState) -> Command:
    # The model wants to do something destructive.
    # Ask the user to confirm.
    confirmation = interrupt({
        "type": "confirm_mutation",
        "action": state["pending_action"],
        "message": "Allow this cluster to be deleted?",
    })
    
    if confirmation == "allow":
        # The user said yes. Proceed with the mutation.
        return Command(goto="execute_mutation")
    else:
        # The user said no. Skip and inform.
        return Command(
            goto=END,
            update={"messages": [AIMessage(content="OK, not deleting.")]},
        )
```

`interrupt(value)`:

1. Saves the current graph state to the checkpointer.
2. Returns the graph to the caller with a `__interrupt__` field.
3. The graph is **paused** — no more nodes run.
4. The caller eventually invokes `graph.invoke(Command(resume=user_response))`.
5. The graph resumes from the `interrupt()` call, with
   `user_response` as the return value of `interrupt()`.
6. The next node runs.

### `interrupt(value)` vs `interrupt_before=["node"]`

| | `interrupt()` | `interrupt_before` / `interrupt_after` |
|---|---|---|
| Where | Inside a node | Compile-time, on specific nodes |
| Value | The `value` is returned when resumed | None (just pause) |
| Resumed with | `Command(resume=value)` | `None` (just continue) |
| Use case | "Ask the user a specific question" | "Pause for any reason" |

Strata's Phase 6 mutation-tool flow uses `interrupt()` — the
user gets a specific confirmation prompt. Phase 2 doesn't use
interrupts at all.

### Multiple interrupts in one run

```python
def node_with_two_interrupts(state):
    a = interrupt({"q": "what's your name?"})
    b = interrupt({"q": f"hello {a}, what's your age?"})
    return {"a": a, "b": b}
```

The graph pauses twice. The first `Command(resume="darshan")`
returns `"darshan"` from the first `interrupt`. The second
`Command(resume=42)` returns `42` from the second.

The state between pauses is preserved by the checkpointer. The
graph resumes from where it left off.

### `__interrupt__` in the result

When the graph pauses, the `invoke` result has a `__interrupt__`
field:

```python
result = graph.invoke(input_state, config={"configurable": {"thread_id": "..."}})
# result["__interrupt__"] = (Interrupt(value={"q": "..."}, id="..."),)
```

The caller inspects this to know what to show the user. The
`id` is needed for resumption (or you can rely on the
`thread_id` + position in the run).

### Resuming

```python
# In the CLI / web:
graph.invoke(
    Command(resume="allow"),
    config={"configurable": {"thread_id": "user-42"}},
)
```

The graph resumes from the `interrupt()` call. The next
invocation returns the final state.

---

## 5. Static interrupts — `interrupt_before` / `interrupt_after`

```python
app = graph.compile(
    interrupt_before=["mutation_handler"],
    interrupt_after=["summarize"],
)
```

These are compile-time pauses. After the named node, the
graph pauses. Resume with `None` (no value needed).

```python
# Run the graph:
result = app.invoke(input_state, config)
# Paused before mutation_handler.

# Inspect state, get user approval, then:
app.invoke(None, config)    # resume
```

`None` for `invoke` means "continue from where we paused."
The checkpointer knows which node is next.

### Use case

Static interrupts are useful for "always pause at this node
for safety." Strata's Phase 6 might use `interrupt_before` on
a `delete_cluster` handler as a safety net, in addition to
the explicit `interrupt()` prompt.

---

## 6. `Command(resume=...)` — the resume mechanism

```python
graph.invoke(
    Command(resume=user_input),
    config={"configurable": {"thread_id": "user-42"}},
)
```

`Command(resume=value)` is how you tell a paused graph to
continue. The `value` is the return value of the
`interrupt()` call.

### Resuming with structured data

```python
graph.invoke(
    Command(resume={"action": "allow", "reason": "user-confirmed"}),
    config={"configurable": {"thread_id": "user-42"}},
)
```

`interrupt({"q": "..."})` is called with a dict, so the
resume value can be a dict too.

### `Command(resume=...)` from a webhook

The HTTP request that resumes the graph doesn't have to come
from the same client that started it. Webhook handlers, CLI
commands, async jobs — all can invoke
`graph.invoke(Command(resume=...))` on the same `thread_id`.

For Strata's Phase 6 confirmation flow:

1. User types "delete cl-001" in the CLI.
2. The graph runs, calls the `mutation_handler` node, hits
   `interrupt()`.
3. The CLI shows the prompt and returns. The graph is paused.
4. User types "yes" (in a separate command? in the same
   session? — Phase 6 design decision).
5. The CLI invokes `graph.invoke(Command(resume="yes"))`.
6. The graph resumes, sees "yes", routes to
   `execute_mutation`.
7. The mutation happens, the graph ends.

The `thread_id` is what ties (2) to (5). Use the CLI session
id or a per-conversation id.

---

## 7. `Command` from a tool

A tool can return a `Command`:

```python
from langgraph.types import Command
from langchain_core.tools import tool

@tool
def lookup_docs(query: str) -> Command:
    """Look up docs that might help answer the user's question."""
    docs = retriever.invoke(query)
    if not docs:
        return Command(
            goto="call_model",
            update={"messages": [SystemMessage(content="No relevant docs found.")]},
        )
    return Command(
        goto="call_model",
        update={"messages": [SystemMessage(content=f"Use these docs: {docs}")]},
    )
```

The tool effectively becomes a node. The model "calls" the
tool; the tool returns a `Command` that routes the graph.

This is the cleanest way to do "after retrieval, route back to
the model with the retrieved docs in context." Compare to the
alternative (a separate `retrieve` node and a conditional edge):

```python
# Alternative: separate node
def retrieve_node(state) -> Command:
    docs = retriever.invoke(state["messages"][-1].content)
    if not docs:
        return Command(goto="call_model")
    return Command(
        goto="call_model",
        update={"messages": [SystemMessage(content=f"Use these docs: {docs}")]},
    )

graph.add_node("retrieve", retrieve_node)
graph.add_conditional_edges(START, should_retrieve, {"retrieve": "retrieve", "call_model": "call_model"})
```

The "tool returns `Command`" form is more idiomatic for RAG
(the retrieval is something the model *decides* to do). The
"separate node" form is better for retrieval that should
*always* happen.

---

## 8. `Command` and reducers

The `update` in a `Command` goes through the same reducers as
a dict return. `add_messages` appends. `operator.add` on a
list concatenates. Custom reducers run as usual.

If the `update` is a single `BaseMessage`, `add_messages`
wraps it in a list. Same as a dict return.

---

## 9. Common pitfalls

1. **`Command.PARENT` is the only way to reach the parent
   graph.** Don't try to mutate the parent's state from
   inside a subgraph without it.
2. **`interrupt()` requires a checkpointer.** Without one, the
   graph has no place to save state. Compile fails.
3. **`Command(resume=value)` returns value from `interrupt()`,
   not the next node's return.** `interrupt({"q": "..."})` →
   `Command(resume="answer")` → node continues, `interrupt()`
   returns `"answer"`.
4. **Multiple `interrupt()` calls in one run** each require a
   separate `Command(resume=...)`. The graph pauses and
   resumes once per `interrupt()`.
5. **`Command(goto="non_existent_node")` fails at runtime.**
   The graph can't find the node. Use a conditional edge or
   `add_node` for the target.
6. **`Command` and conditional edges interact in surprising
   ways.** If a node has both a fixed edge and returns
   `Command(goto="X")`, the `Command` wins. If a node has a
   conditional edge and returns `Command(goto="Y")`, the
   `Command` still wins. `Command` overrides edges.
7. **`interrupt()` inside a tool** is allowed but unusual.
   The tool pauses, the graph pauses, the user is asked. If
   you need this, design carefully — usually it's better to
   use a dedicated node.
8. **Resume requires the same `config["configurable"]`.** The
   `thread_id` (or whatever the checkpointer keys on) must
   match between pause and resume.
9. **`Command` from a tool's `ToolMessage` doesn't go to
   `ToolNode` first.** The tool's return is the `ToolMessage`
   content (or the `Command`). The graph applies the
   `Command` and routes.
10. **Static `interrupt_before` + `interrupt()` is redundant.**
    Pick one form of interruption per node.

---

## 10. What to read next

- [05-toolnode-and-tools_condition.md](05-toolnode-and-tools_condition.md)
  — the standard `ToolNode` and `tools_condition` flow.
- [06-subgraphs-and-map-reduce.md](06-subgraphs-and-map-reduce.md)
  — `Command.PARENT` and the `Send` pattern.
- [08-checkpoints-and-persistence.md](08-checkpoints-and-persistence.md)
  — the checkpointer that makes `interrupt()` and `Command`
  durable.
- [10-human-in-the-loop.md](10-human-in-the-loop.md) — the full
  HITL pattern with webhooks, polling, and multi-user.
- LangGraph `Command` API: <https://langchain-ai.github.io/langgraph/reference/types/#langgraph.types.Command>
