# LangChain — Tools (`@tool`, `StructuredTool`, `BaseTool`)

> **Part 4 of the LangChain deep-dive.** A tool is a function
> with a name, a description, and an argument schema. The LLM
> picks tools based on their description. The docstring is the
> API contract.

A LangChain "tool" is a `BaseTool` subclass with:

- `name` — what the model calls it by.
- `description` — what the model sees in its prompt. The
  **docstring** of an `@tool`-decorated function.
- `args_schema` — a Pydantic model describing the arguments.
  Derived from the function's type annotations.

When you `bind_tools([...])` on a chat model, each tool's name,
description, and args_schema get serialized into the model's API
request. The model decides which tool to call based on the
description and the user's prompt.

---

## 1. `@tool` — the decorator

```python
from langchain_core.tools import tool

@tool
def get_cluster_status(cluster_id: str) -> dict:
    """Get the current status of one EKS cluster by its id.

    Use this when the user asks for the status of a specific
    cluster, e.g. "what's the status of demo?" or "is cl-001
    ready?". Returns READY / PROVISIONING / DELETING / FAILED.

    Returns NOT_FOUND if the id is unknown.
    """
    return {"id": cluster_id, "status": "READY"}
```

What the model sees (after JSON schema generation):

```json
{
  "name": "get_cluster_status",
  "description": "Get the current status of one EKS cluster by its id. Use this when the user asks for the status of a specific cluster, e.g. \"what's the status of demo?\" or \"is cl-001 ready?\". Returns READY / PROVISIONING / DELETING / FAILED.\n\nReturns NOT_FOUND if the id is unknown.",
  "parameters": {
    "type": "object",
    "properties": {
      "cluster_id": {"type": "string"}
    },
    "required": ["cluster_id"]
  }
}
```

### What `@tool` does and does NOT do

**Does:**
- Builds the JSON schema from the type annotations.
- Wraps the function in a `StructuredTool`.
- Surfaces the function's name, docstring, and signature to the
  LLM.
- Validates arguments against the schema when invoked.

**Does NOT:**
- Handle async (use the `coroutine` argument or the
  `parse_docstring` approach — see below).
- Apply retries, timeouts, or error formatting.
- Validate the return type. The model's only view of the result
  is `ToolMessage.content` (a string).
- Add `id` to `AIMessage.tool_calls` (the model does that).

---

## 2. The docstring is the API

Because the LLM picks tools based on the description, your
**docstring is the API contract** between you and the model. A
bad docstring means the model calls the wrong tool, or doesn't
call a tool when it should.

### Conventions

- **One-line summary first.** "Get the current status of one
  EKS cluster by its id."
- **"Use this when..." clause.** Describes the *intent*, not
  the mechanics. "Use this when the user asks for the status of
  a specific cluster."
- **Examples in the user voice.** 'E.g. "what\'s the status of
  demo?", "is cl-001 ready?"'. The model uses these as few-shot
  hints for when to call the tool.
- **Return shape if not obvious.** "Returns READY /
  PROVISIONING / DELETING / FAILED."
- **Edge cases.** "Returns NOT_FOUND if the id is unknown."

### Docstring parsing styles

`@tool` (and `StructuredTool.from_function(...)`) can parse
several docstring formats. The default is the "first paragraph
becomes the description" approach — the entire docstring is the
description.

For more structure, set `parse_docstring=True` and use a
recognized format (Google, NumPy, Sphinx):

```python
@tool(parse_docstring=True)
def get_cluster_status(cluster_id: str) -> dict:
    """Get the current status of one EKS cluster.

    Args:
        cluster_id: The cluster id (e.g. "cl-001").

    Returns:
        A dict with keys: id, status, last_updated, region.

    Raises:
        ValueError: if cluster_id is empty.
    """
    return {"id": cluster_id, "status": "READY"}
```

With `parse_docstring=True`, LangChain splits the docstring and
uses the short summary as the description and the `Args` /
`Returns` sections as additional structured info.

For Strata's Phase 2, the default behavior (whole docstring as
description) is fine. Switch to `parse_docstring=True` when you
have a tool with a long docstring and you want the description
to be a tight one-liner.

---

## 3. The argument schema

`@tool` reads the function's type annotations and generates a
JSON schema via Pydantic. Common cases:

```python
@tool
def simple(x: str) -> str:
    """..."""
# schema: {"properties": {"x": {"type": "string"}}, "required": ["x"]}

@tool
def optional_arg(x: str, y: int = 5) -> dict:
    """..."""
# schema: {"properties": {"x": {"type": "string"}, "y": {"type": "integer", "default": 5}}, "required": ["x"]}

@tool
def with_enum(status: Literal["READY", "PROVISIONING", "FAILED"]) -> dict:
    """..."""
# schema: {"properties": {"status": {"enum": ["READY", "PROVISIONING", "FAILED"], "type": "string"}}, "required": ["status"]}

@tool
def nested(req: CreateClusterRequest) -> CreateClusterResponse:
    """..."""
# schema: {"properties": {"req": {"$ref": "#/$defs/CreateClusterRequest", ...}}, ...}
```

### Supported types

- Primitives: `str`, `int`, `float`, `bool`
- `list[T]`, `dict[K, V]`, `Optional[T]`, `Union[A, B]`
- `Literal["a", "b", "c"]` (becomes an `enum`)
- `Enum` subclasses
- Pydantic `BaseModel` (becomes a nested `$ref`)
- `TypedDict` (treated like a dict)
- `datetime.date`, `datetime.datetime` (ISO-8601 strings)

### `args_schema` override

If the inferred schema is wrong (or you want to add a
description for a parameter that has no docstring entry):

```python
from pydantic import BaseModel, Field

class GetClusterStatusArgs(BaseModel):
    cluster_id: str = Field(description="The EKS cluster id, e.g. 'cl-001'.")

@tool("get_cluster_status", args_schema=GetClusterStatusArgs)
def get_cluster_status(cluster_id: str) -> dict:
    """Get the current status of one EKS cluster by its id."""
    return {"id": cluster_id, "status": "READY"}
```

The `Field(description=...)` shows up in the schema and the
model uses it to know what to pass.

### `extra` parameters and `configurable_fields`

For advanced cases — args that come from runtime context, not
the LLM — use `InjectedToolArg` (see §6 below).

---

## 4. Returning values

The tool's return value gets wrapped in a `ToolMessage` with
`content=str(return_value)`. The model only sees the string.

### Returning a `dict`

```python
@tool
def list_clusters() -> list[dict]:
    """..."""
    return [{"id": "cl-001", "name": "demo", "status": "READY"}]
# ToolMessage(content=str([{...}])  — uses __repr__ / __str__ of the list
```

⚠️ `str([...])` is *not* JSON. The model sees `'[{"id": "cl-001"...}]'`
which looks JSON-ish but isn't guaranteed to be. **Always serialize
explicitly.**

### Returning a Pydantic model

```python
from pydantic import BaseModel

class Cluster(BaseModel):
    id: str
    name: str
    status: str

@tool
def list_clusters() -> list[Cluster]:
    """..."""
    return [Cluster(id="cl-001", name="demo", status="READY")]
```

The model's behavior depends on which version of LangChain you
use:

- **Modern (recommended):** `StructuredTool` calls
  `model.model_dump_json()` on the return value. You get valid
  JSON in `ToolMessage.content`.
- **Older / different version:** it may call `str()` on the
  model. You get a Pydantic repr, not JSON.

To be safe, serialize explicitly:

```python
@tool
def list_clusters() -> str:
    """..."""
    clusters = [Cluster(id="cl-001", ...)]
    return json.dumps([c.model_dump() for c in clusters])
```

### Returning a `Command` — the "I changed the route" pattern

A tool can return a `Command` (from `langgraph.types`) instead
of a value. The `Command` is applied to the graph state and can
change the next node.

```python
from langgraph.types import Command
from langchain_core.messages import ToolMessage

@tool
def lookup_and_continue(query: str) -> Command:
    """..."""
    docs = retriever.invoke(query)
    return Command(
        goto="call_model",
        update={
            "messages": [
                SystemMessage(content=f"Use these docs: {docs}"),
            ],
        },
    )
```

This is the clean way to do "after this tool runs, inject
context and re-run the model." Strata's Phase 4 RAG `retrieve`
node can be written either as a node (a function on state) or
as a tool that returns a `Command` — the latter is sometimes
cleaner when the model should call retrieval explicitly.

### Returning a `ToolMessage` directly

If you need fine control over the wrapping:

```python
@tool
def get_cluster_status(cluster_id: str) -> ToolMessage:
    """..."""
    return ToolMessage(
        content=json.dumps({"id": cluster_id, "status": "READY"}),
        name="get_cluster_status",
        tool_call_id="ignored-here",   # ToolNode overrides
    )
```

The `ToolNode` will use your `content` and `name` but override
`tool_call_id` to match the actual `tool_call.id` from the
`AIMessage`. Useful when you need to set `status="error"` or
include an `artifact`.

---

## 5. Async tools

If your tool is I/O-bound (Phase 3+ HTTP calls to the
orchestrator), make it `async def`:

```python
@tool
async def get_cluster_status(cluster_id: str) -> dict:
    """..."""
    async with httpx.AsyncClient() as c:
        r = await c.get(f"http://orchestrator:8080/clusters/{cluster_id}")
        return r.json()
```

`ToolNode` awaits async tools correctly. If your tool is sync,
`ToolNode` runs it in a thread pool (via `asyncio.to_thread`).
Mixed lists work — the async ones await, the sync ones go to
the pool.

**Gotcha:** if you decorate an `async def` with `@tool` and try
to call it sync, you'll get a coroutine warning. Use
`@tool(coroutine=...)` (older API) or just `await tool.ainvoke(...)`.

---

## 6. Injected tool arguments — args that don't come from the LLM

Sometimes a tool needs an argument the model can't supply:
`user_id`, `db_session`, `http_client`, etc. Use
`InjectedToolArg` to mark a parameter as injected at runtime.

```python
from langchain_core.tools import tool, InjectedToolArg
from typing import Annotated

def get_user_clusters(
    user_id: Annotated[str, InjectedToolArg()],
) -> list[dict]:
    """List the EKS clusters owned by the current user."""
    # user_id is filled in by the tool's caller, not by the LLM
    return db.query("SELECT * FROM clusters WHERE user_id = $1", user_id)

# To invoke:
tool.invoke(
    {},                            # no args from the LLM
    config={"configurable": {"user_id": "user-42"}},
)
```

`InjectedToolArg` is hidden from the JSON schema the model sees.
The model doesn't try to fill it. The runtime must provide it
via `config["configurable"]` or by passing it as a kwarg to
`tool.invoke(...)`.

**`Annotated[str, InjectedToolArg()]`** is the standard form.
There's also `InjectedToolCallId` for the special case of "give
me the current tool call's id" (useful for logging).

Strata's Phase 4+ tools will use this for `user_id` and the
httpx client. The orchestrator's `MOCK_USER` middleware provides
`user_id`; the tool reads it via `runtime.config["configurable"]`
and looks up the data.

---

## 7. Error handling in tools

`ToolNode(handle_tool_errors=True)` (default in recent versions)
catches exceptions and returns them as a `ToolMessage` with
`status="error"` and the exception message in `content`. The
model sees the error and can react (retry, explain, ask the
user, give up).

```python
@tool
def get_cluster_status(cluster_id: str) -> dict:
    """..."""
    if cluster_id not in KNOWN_CLUSTERS:
        raise KeyError(f"Cluster {cluster_id} not found")
    return {"id": cluster_id, "status": "READY"}
```

If the model calls this with an unknown id, `ToolNode` catches
the `KeyError` and emits:

```python
ToolMessage(
    content="Error: Cluster cl-999 not found",
    name="get_cluster_status",
    tool_call_id="...",
    status="error",
)
```

The model sees this and can say "I don't see a cluster with id
cl-999 — did you mean cl-001?" or call `list_clusters` to find
the right one.

### Custom error formatting

```python
ToolNode(tools, handle_tool_errors=lambda e: f"Tool error: {e}")
# or
ToolNode(tools, handle_tool_errors="The cluster service is down. Try again later.")
```

The `callable` form lets you format the error your way. The
`str` form is a static message for all errors.

### When to raise vs. return error

- **Raise** for programmer errors (the model passed a value
  that broke your code; you want to know). `ToolNode` will
  convert it to a `ToolMessage` with `status="error"`.
- **Return error string** for business errors (the model
  correctly asked for a cluster that doesn't exist; the
  response is a normal "no, that cluster doesn't exist").

Strata's pattern: raise `ValueError` or `KeyError` for "the
data isn't there." Let `ToolNode` wrap it. The model gets the
error and either tries a different id or tells the user.

---

## 8. `StructuredTool.from_function` — the factory

For programmatic construction (e.g. you generate tools at
runtime):

```python
from langchain_core.tools import StructuredTool

def my_get_cluster_status(cluster_id: str) -> dict:
    """Get the current status of one EKS cluster by its id."""
    return {"id": cluster_id, "status": "READY"}

tool = StructuredTool.from_function(
    func=my_get_cluster_status,
    name="get_cluster_status",
    description="Get the current status of one EKS cluster by its id.",
    return_direct=False,
    parse_docstring=False,
    infer_schema=True,
    response_format="content",     # how to format the return value
)
```

`response_format` controls what gets put in `ToolMessage.content`:

- `"content"` (default) — serialize the return value to a string.
- `"content_and_artifact"` — `content` is the string repr, `artifact` is
  the raw value. Useful for "I have a list of dicts; the model
  sees a JSON string, my code sees the list."

### When `@tool` isn't enough

- **You generate tools at runtime** (e.g. one per cluster id).
- **You want to override the name** without renaming the
  function.
- **You're wrapping a class method as a tool.**
- **You need a custom `args_schema` that's hard to express as
  annotations** (rare — usually the `args_schema` parameter on
  `@tool` is enough).

---

## 9. Subclassing `BaseTool`

When `@tool` is too rigid (e.g. the tool needs a long-lived
client, complex config, or non-trivial async setup), subclass
`BaseTool` directly.

```python
from langchain_core.tools import BaseTool
from pydantic import Field

class GetClusterLogsTool(BaseTool):
    name: str = "get_cluster_logs"
    description: str = "Fetch recent pod logs for a cluster."

    args_schema: type[BaseModel] = GetClusterLogsInput

    client: httpx.AsyncClient = Field(exclude=True)   # injected, not serialized

    def _run(self, *, cluster_id: str, since: str = "5m") -> str:
        # sync version
        ...

    async def _arun(self, *, cluster_id: str, since: str = "5m") -> str:
        # async version
        response = await self.client.get(...)
        return response.text
```

The `Field(exclude=True)` pattern is the right way to inject
dependencies that shouldn't be serialized (DB clients, HTTP
clients, etc.).

### When to subclass

- **The tool needs a long-lived dependency** (DB connection,
  HTTP client) that you don't want to construct on every call.
- **The tool's behavior depends on instance state** (e.g. a
  circuit breaker).
- **You're building a tool for a domain with complex validation**
  (multi-step setup, etc.).

Strata's Phase 2 uses `@tool` for everything. Subclassing is
the right move for the orchestrator-backed tools in Phase 3+
where you want to inject an `httpx.AsyncClient`.

---

## 10. `tool_call_id` correlation — the rules

The model emits `AIMessage.tool_calls = [{id: "call-abc123",
name: "list_clusters", args: {}}]`. The framework (or you) must
build a `ToolMessage` with `tool_call_id="call-abc123"`.

**What `ToolNode` does:**

1. Reads the last `AIMessage`'s `tool_calls`.
2. For each, looks up the tool by name.
3. Calls `tool.invoke(tool_call["args"])`.
4. Wraps the return value in a `ToolMessage(tool_call_id=tool_call["id"], ...)`.
5. Appends all `ToolMessage`s to state.

The `id` is opaque to the model; it's just a string the
framework uses for correlation. You can think of it as a foreign
key. If you build `ToolMessage`s by hand (e.g. in a custom
router), the id **must** match.

**If the model makes a parallel call** (two tools in one
`AIMessage`), `ToolNode` produces two `ToolMessage`s with
different ids. The order matches the order in `tool_calls`.

---

## 11. `tool_choice` and forced tool calls

```python
llm.bind_tools([tool], tool_choice="any")           # must call one
llm.bind_tools([tool], tool_choice="tool")          # must call THIS one
```

`tool_choice="any"` is what Strata's Phase 6 mutation-tool
flow uses. The model is forced to commit to *some* tool call,
even if its natural answer would be "just text." The
confirmation node then gates whether the call goes through.

`tool_choice="tool"` with a specific name is used in tests to
lock the model to a particular tool.

For most use cases, `"auto"` (default) is what you want. The
model decides.

---

## 12. Tool versioning and deprecation

Tools evolve. To deprecate one without breaking the model:

```python
@tool
def list_clusters_v2() -> list[dict]:
    """List all EKS clusters (uses v2 of the cluster API). Use this
    INSTEAD OF list_clusters. Same return shape, but with
    `k8s_version` and `created_at` fields."""
    ...
```

The model reads the docstring and picks the right one. To
remove a tool entirely: take it out of the `bind_tools` list.
The model won't see it.

For breaking changes (return shape change), keep the old tool
in the list for a deprecation period, then remove it. Use the
description to nudge the model toward the new one.

---

## 13. The 5 Strata tools (Phase 2, mocked)

```python
# app/tools/list_clusters.py
@tool
def list_clusters() -> list[dict]:
    """List all EKS clusters owned by the current user.

    Use this when the user asks "what clusters do I have?",
    "show my clusters", "list clusters", or any variation.
    Returns one row per cluster with id, name, status, region,
    and k8s_version. Status is one of: READY, PROVISIONING,
    DELETING, FAILED.
    """
    return [
        {"id": "cl-001", "name": "demo", "status": "READY",
         "region": "us-west-2", "k8s_version": "1.29"},
        {"id": "cl-002", "name": "staging", "status": "PROVISIONING",
         "region": "us-east-1", "k8s_version": "1.29"},
    ]

# app/tools/get_cluster_status.py
@tool
def get_cluster_status(cluster_id: str) -> dict:
    """Get the current status of one EKS cluster by its id.

    Use this when the user names a specific cluster, e.g. "what's
    the status of demo?" or "is cl-001 ready?". Returns one row
    with id, status, last_updated, region, k8s_version. Status
    is one of: READY, PROVISIONING, DELETING, FAILED.

    If cluster_id is unknown, returns {"status": "NOT_FOUND"}.
    """
    return {"id": cluster_id, "status": "READY", "last_updated": "..."}

# app/tools/get_cluster_logs.py
@tool
def get_cluster_logs(cluster_id: str, since: str = "5m") -> list[str]:
    """Fetch recent pod logs for an EKS cluster.

    Use this when the user asks for "logs", "what's happening in
    cluster X", "show me errors", or "what's failing?". The
    `since` argument is a duration like "5m", "1h", "1d", or
    "30s". Default is "5m".

    Returns a list of log lines (newest last). Empty list if no
    logs in the window.
    """
    return ["[INFO] pod/web-0 started", "[WARN] probe failed"]

# app/tools/provision_cluster.py
@tool
def provision_cluster(name: str, region: str, k8s_version: str = "1.29") -> dict:
    """Provision a new EKS cluster.

    Use this when the user says "create a cluster", "spin up
    EKS in us-west-2", "I need a new cluster", etc.

    Args:
        name: cluster name (lowercase, 1-32 chars, alphanumeric + hyphens)
        region: AWS region, e.g. "us-west-2", "us-east-1"
        k8s_version: Kubernetes version, defaults to "1.29"

    Returns the new cluster's id and status (INITIATED). Provisioning
    takes ~5-7 minutes. Use get_cluster_status to poll.

    Returns INVALID_NAME if name doesn't match the pattern.
    """
    return {"id": "cl-003", "name": name, "status": "INITIATED"}

# app/tools/delete_cluster.py
@tool
def delete_cluster(cluster_id: str) -> dict:
    """Delete an EKS cluster and all its resources.

    Use this when the user says "delete cluster X", "tear down
    cl-001", "remove my demo cluster", etc. DESTRUCTIVE — this
    removes all workloads, data, and the cluster itself. Cannot
    be undone.

    Returns {"id": ..., "status": "DELETING"} on success.
    Returns NOT_FOUND if cluster_id is unknown.
    """
    return {"id": cluster_id, "status": "DELETING"}
```

The docstrings are deliberately shaped like the model will
read them. The `Use this when...` clause is the model-facing
"intent" description. The "Returns NOT_FOUND / INVALID_NAME"
clauses tell the model what to expect.

---

## 14. Common pitfalls

1. **Importing `from langchain.tools import tool` works but is
   legacy.** Use `from langchain_core.tools import tool`.
2. **Returning a Pydantic model** — the framework may serialize
   it as JSON, or as a Pydantic repr, depending on version.
   Serialize explicitly (`model_dump_json()`) to be safe.
3. **`@tool` on a no-argument function** works fine. The schema
   is `{"properties": {}}`. Don't add a fake argument to satisfy
   yourself.
4. **`@tool(coroutine=my_async_fn)`** is the old form. Newer:
   just `async def` the function and decorate with `@tool`.
5. **`ToolMessage.content` is always a string.** If your tool
   returns a dict/list/Pydantic, you must serialize.
6. **Mismatched `tool_call_id`.** The framework gets this right;
   you get it wrong. If you're not using `ToolNode`, double-check.
7. **`handle_tool_errors=False`** is a footgun. Default `True`
   is what you want.
8. **`InjectedToolArg` must be in `Annotated[T, ...]`.** Without
   `Annotated`, it's just a regular arg and the LLM has to
   provide it.
9. **`tool_choice="any"`** forces a tool call but doesn't
   restrict *which* tool. To force a specific tool, use
   `tool_choice="list_clusters"` (or the dict form).
10. **Tool docstrings that lie.** If the docstring says
    "returns X" but the code returns Y, the model gets
    confused. The test is: "would a junior dev, reading
    only the docstring, know what this tool does and when to
    call it?"

---

## 15. What to read next

- `05-prompts-and-parsers.md` — using `MessagesPlaceholder` to
  pass the conversation history to a templated prompt.
- `../langgraph/05-toolnode-and-tools_condition.md` — the
  `ToolNode` mechanics in graph form.
- `../langgraph/10-human-in-the-loop.md` — the mutation-tool
  confirmation flow, Phase 6+.
- LangChain tools: <https://python.langchain.com/docs/concepts/tools/>
