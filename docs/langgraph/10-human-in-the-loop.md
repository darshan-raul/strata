# LangGraph — Human-in-the-Loop

> **Part 10 of the LangGraph deep-dive.** The `interrupt()`
> function, `Command(resume=...)`, static interrupts,
> multi-interrupt flows, and Strata's Phase 6 mutation-tool
> confirmation pattern.

Human-in-the-loop (HITL) is letting the graph pause, ask a
human for input, and resume when the human responds. LangGraph
implements this via `interrupt()` (dynamic, inside a node) and
`interrupt_before` / `interrupt_after` (static, compile-time).
The checkpointer is what makes the pause durable.

---

## 1. The pattern

```
graph.run()
    │
    ▼
  call_model  ──►  mutation_handler  ──►  interrupt({prompt})  ──► [PAUSED]
                                                                    │
                                                              user_response
                                                                    │
                                                                    ▼
                                              graph.invoke(Command(resume=user_response))
                                                                    │
                                                                    ▼
                                                       mutation_handler resumes
                                                                    │
                                                                    ▼
                                                       execute_mutation
                                                                    │
                                                                    ▼
                                                                  END
```

The graph pauses. The user responds (in the CLI, in the web
UI, in a webhook handler). A new `invoke` resumes from the
pause with the response.

---

## 2. `interrupt()` — the dynamic form

```python
from langgraph.types import interrupt, Command

def mutation_handler(state: AgentState) -> Command:
    # The model wants to do something destructive.
    # Pause and ask the user.
    response = interrupt({
        "type": "confirm_mutation",
        "action": state["pending_action"],
        "message": f"Allow this action? {state['pending_action']}",
    })
    
    if response == "allow":
        return Command(goto="execute_mutation")
    elif response == "deny":
        return Command(
            goto=END,
            update={"messages": [AIMessage(content="OK, not doing that.")]},
        )
    else:    # e.g. "modify"
        return Command(goto="modify_action")
```

`interrupt(value)`:

1. Saves the current graph state to the checkpointer.
2. Returns the graph to the caller. The result has
   `__interrupt__` populated.
3. The graph is **paused** — no more nodes run.
4. The caller eventually invokes
   `graph.invoke(Command(resume=user_response), config)`.
5. The graph resumes from the `interrupt()` call. The
   `user_response` is the return value of `interrupt()`.
6. The node continues.

### Why this works

The checkpointer saves the state mid-node. The node function
is suspended (in the sense that Python returns from
`invoke` and the caller can do other things). When the
caller invokes again with `Command(resume=...)`, the
framework re-runs the node from the start — but the
`interrupt()` call returns the resume value this time
instead of pausing.

The framework handles this transparently. The node doesn't
need to know whether it's the first run or a resume; the
`interrupt()` call is the only thing that branches.

### `interrupt()` requires a checkpointer

```python
graph = builder.compile(
    checkpointer=MemorySaver(),    # required for interrupt
)
```

Without a checkpointer, the pause has nowhere to save state.
The compile succeeds, but `interrupt()` errors at runtime.

---

## 3. The `__interrupt__` field

When the graph pauses, the `invoke` result includes:

```python
result = graph.invoke(input, config)
# result["__interrupt__"] = (Interrupt(value={"type": "confirm_mutation", ...}, id="..."),)
```

The `Interrupt` object has:

- `value` — what was passed to `interrupt()`.
- `id` — the unique id of this interrupt (for tracking).
- `when` — when it was created.

The caller inspects this to know what to show the user.

```python
# CLI:
result = graph.invoke(input, config)
if "__interrupt__" in result:
    for interrupt_obj in result["__interrupt__"]:
        print(f"Graph paused: {interrupt_obj.value['message']}")
        user_response = input("Allow? (yes/no): ")
        # Resume:
        graph.invoke(Command(resume=user_response), config)
```

### `astream` with `interrupt()`

```python
async for event in graph.astream_events(input, config, version="v2"):
    if event["event"] == "__interrupt__":
        prompt = event["value"]
        # Show the user
        ...
```

The stream ends with `__interrupt__`. The caller processes it
and resumes with a separate `invoke`.

---

## 4. Resuming — `Command(resume=...)`

```python
graph.invoke(
    Command(resume="allow"),
    config={"configurable": {"thread_id": "user-42"}},
)
```

The graph resumes from the `interrupt()` call. The `resume`
value is what `interrupt()` returns.

### The thread id is the link

The `config` (specifically `configurable.thread_id`) ties the
pause to the resume. Without the same thread id, the resume
doesn't find the paused run.

For Strata's CLI: the `thread_id` is the conversation id.
For the web UI: same. The same id used to start the
conversation is the one used to resume.

### Resuming from a different process

The resume can come from a different process — webhook
handler, CLI in another terminal, admin tool — as long as it
has the same `thread_id` and access to the same checkpointer
backend.

```python
# In a webhook handler, after the user clicks "Allow" in the web UI:
import httpx
response = httpx.post(
    "http://agent-service:8080/resume",
    json={
        "thread_id": "user-42",
        "interrupt_id": "...",
        "response": "allow",
    },
)
```

The agent-service handles the `Command(resume=...)` invocation
on behalf of the webhook. (Strata's actual architecture: a
`POST /resume` endpoint on the orchestrator that proxies to
the agent-service, or a direct call if the webhook has
in-cluster access.)

---

## 5. Multiple interrupts in one run

```python
def node_with_two_questions(state):
    name = interrupt({"q": "what's your name?"})
    age = interrupt({"q": f"hello {name}, what's your age?"})
    return {"name": name, "age": age}
```

The graph pauses twice. Each `Command(resume=...)` resumes
one interrupt:

```python
# First invoke: graph pauses at first interrupt.
result = graph.invoke(input, config)
# result["__interrupt__"] = (Interrupt(value={"q": "what's your name?"}, id="i-1"),)

# First resume: graph runs to the second interrupt, pauses.
graph.invoke(Command(resume="darshan"), config)
# (Paused at second interrupt.)

# Second resume: graph completes.
graph.invoke(Command(resume=42), config)
# (Graph ends, final state returned.)
```

The framework tracks the position. Multiple `Command(resume=...)`
calls in sequence walk the run forward.

### Stateful between pauses

The state is preserved between pauses. The first interrupt's
return value (`"darshan"`) is in the state when the second
interrupt fires. The second prompt uses it.

---

## 6. Static interrupts — `interrupt_before` / `interrupt_after`

```python
app = graph.compile(
    interrupt_before=["mutation_handler"],
    interrupt_after=["summarize"],
)
```

Pause before/after the named nodes, regardless of what the
node does. Resume with `None` (no value needed):

```python
# First run: graph pauses before mutation_handler.
result = app.invoke(input, config)
# result["__interrupt__"] = (Interrupt(value=..., id="..."),)
# state.next = ("mutation_handler",)

# Inspect state, get approval, then:
app.invoke(None, config)
# Resumes; the next node (mutation_handler) runs.
```

### When to use static interrupts

- "Always pause at this node" (a safety net).
- A node that doesn't have a specific prompt but you want
  human oversight anyway.
- A debugging aid (pause after each named node, inspect
  state, step forward manually).

### Static + dynamic

You can use both:

```python
app = graph.compile(
    interrupt_before=["mutation_handler"],    # safety net
)
```

And inside `mutation_handler`:

```python
def mutation_handler(state):
    response = interrupt({"specific prompt": "..."})    # the explicit prompt
    ...
```

The static `interrupt_before` pauses the graph *before*
`mutation_handler` even runs. The dynamic `interrupt()`
inside pauses *during* the node. With both, the static
fires first, then the node runs, then the dynamic fires
when reached.

For Strata, pick one form per node. The dynamic
`interrupt()` is more flexible.

---

## 7. Strata's mutation-tool confirmation flow (Phase 6+)

The end-to-end design:

```python
# app/graph.py
def call_model(state: AgentState) -> dict:
    response = llm.bind_tools(
        tools,
        tool_choice="any",    # force the model to call a tool
    ).invoke(state["messages"])
    return {"messages": [response]}

def custom_route(state: AgentState) -> str:
    last = state["messages"][-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return END
    tool_names = {tc["name"] for tc in last.tool_calls}
    if tool_names & {"provision_cluster", "delete_cluster"}:
        return "confirm_mutation"     # mutation tool: confirm first
    return "tools"                    # read tool: run directly

graph.add_conditional_edges(
    "call_model",
    custom_route,
    {"confirm_mutation": "confirm_mutation", "tools": "tools", END: END},
)

def confirm_mutation(state: AgentState) -> Command:
    last = state["messages"][-1]
    mutation = next(
        tc for tc in last.tool_calls
        if tc["name"] in {"provision_cluster", "delete_cluster"}
    )
    response = interrupt({
        "type": "confirm_mutation",
        "tool": mutation["name"],
        "args": mutation["args"],
        "message": f"Allow {mutation['name']}({mutation['args']})?",
    })
    if response == "allow":
        return Command(goto="tools")    # proceed
    else:
        return Command(
            goto=END,
            update={"messages": [AIMessage(content="Cancelled.")]},
        )

graph.add_node("confirm_mutation", confirm_mutation)
graph.add_node("tools", ToolNode(tools))
graph.add_edge("tools", "call_model")
```

The flow:

1. User says "delete cl-001."
2. `call_model` runs. With `tool_choice="any"`, the model
   emits a tool call (forced). It's `delete_cluster(cl-001)`.
3. `custom_route` sees the mutation tool, routes to
   `confirm_mutation`.
4. `confirm_mutation` calls `interrupt({...})`. The graph
   pauses. The user is shown the prompt.
5. User says "yes" (in the CLI, in the web UI).
6. The CLI/web invokes `graph.invoke(Command(resume="allow"))`.
7. `confirm_mutation` returns `Command(goto="tools")`.
8. `ToolNode` runs `delete_cluster`. The result is a
   `ToolMessage`.
9. `call_model` runs again. The model sees the result, says
   "Deleted cl-001."
10. The graph ends.

The user has full control. The model can't bypass the
confirmation.

### `tool_choice="any"` is important

Without `tool_choice="any"`, the model might respond "I can't
delete that" and not call the tool. With `any`, the model
*must* call a tool, even if it's the wrong one. The
confirmation node then decides whether to proceed.

If the model calls a non-mutation tool (e.g. `list_clusters`),
the route doesn't go to `confirm_mutation` — it goes to
`tools` directly. The `tool_choice="any"` ensures the model
commits to a tool; the custom router decides whether to
confirm or run.

---

## 8. CLI vs web UI confirmation

### CLI

```bash
$ strata chat
You: delete cl-001

# (Graph pauses; CLI shows the prompt:)
[Strata wants to] delete_cluster(cluster_id="cl-001")
Allow? [y/n/cancel]: y
# (CLI invokes Command(resume="allow"); the graph resumes.)

Strata: Deleted cl-001.
```

The CLI holds the conversation. The `thread_id` is the CLI
session id. The user types "y" inline; the CLI invokes
`graph.invoke(Command(resume="y"))` on the same thread.

### Web UI

```
[Chat panel]
You: delete cl-001
Strata wants to delete cl-001. [Confirm] [Deny]

(User clicks Confirm; the web UI POSTs to /resume.)
```

The web UI holds the conversation id. The "Confirm" click
sends `POST /resume { thread_id, response: "allow" }`. The
agent-service invokes `graph.invoke(Command(resume="allow"))`
on the same thread.

The user might switch tabs / close the browser. When they
come back, the graph is still paused (the checkpointer has
the state). They click Confirm later, and the graph resumes.

### Webhook-based resume

For an out-of-band resume (e.g. an admin clicks "approve"
in a Slack channel):

```python
# In a Slack handler:
@slack_app.action("approve_mutation")
async def handle_approve(ack, action):
    await ack()
    thread_id = action["value"]
    await agent_service.invoke(
        Command(resume="allow"),
        config={"configurable": {"thread_id": thread_id}},
    )
```

The checkpointer backend (Postgres) is shared, so any process
with the thread id can resume.

---

## 9. Polling the state

If the user is on a different device (e.g. they started a
mutation in the web UI, want to approve from their phone),
poll the state:

```python
# In the phone app:
while True:
    state = graph.get_state(config)
    if state.next and not state.tasks:
        # Graph is paused.
        prompt = state.interrupts[0].value
        # Show the prompt
        ...
        break
    await asyncio.sleep(2)
```

The CLI/web can also poll if they want to detect "the graph
is paused" without holding the connection.

---

## 10. Common pitfalls

1. **`interrupt()` without a checkpointer.** Compile succeeds,
   but `interrupt()` errors at runtime. Always include a
   checkpointer when you have `interrupt()`.
2. **The `Command(resume=...)` value doesn't match the
   `interrupt()` expected type.** If `interrupt()` expects a
   string and you pass a dict, the node's resume handler
   errors. Be consistent.
3. **Multiple `interrupt()` calls in one run** require
   multiple `Command(resume=...)` calls. The framework
   tracks position. Don't try to "skip" a pause.
4. **Static + dynamic interrupts on the same node** —
   redundant. Pick one.
5. **Resuming with the wrong `thread_id`** — the framework
   can't find the paused run. The new invocation runs from
   the start instead of resuming.
6. **`interrupt()` inside a tool** — allowed but unusual. The
   tool pauses, the graph pauses, the user is asked. If you
   need this, design carefully. Usually a dedicated
   confirmation node is cleaner.
7. **The pause is not a "no-op" for the LLM.** The model's
   context grows; the checkpointer grows. Long pauses with
   many turns in between are fine but the state is
   accumulating.
8. **Resuming a graph that's been recompiled** — if the
   graph's structure changed between pause and resume, the
   framework can't find the node. Pin the graph spec.
9. **Catching `Interrupt` exceptions in user code** — the
   framework's `interrupt()` raises a special exception
   internally. Don't catch it; it's the framework's
   mechanism for pausing.

---

## 11. What to read next

- [04-command-and-control-flow.md](04-command-and-control-flow.md)
  — `Command` and the resume mechanism.
- [08-checkpoints-and-persistence.md](08-checkpoints-and-persistence.md)
  — the checkpointer that makes pauses durable.
- [11-deployment-and-debug.md](11-deployment-and-debug.md) —
  testing and debugging HITL flows.
- LangGraph HITL: <https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/>
