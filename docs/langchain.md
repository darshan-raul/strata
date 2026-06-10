# LangChain

The Python SDK that gives us standardized interfaces to LLMs, prompts,
output parsers, tools, and the runnable composition language. LangGraph
sits *on top* of LangChain; you can't really understand one without the
other, so read this first.

Strata uses LangChain in two narrow places:

1. **Chat models** — `langchain_openai.ChatOpenAI` pointed at LiteLLM
   (see `app/providers/litellm_provider.py`). We never import a vendor
   SDK directly.
2. **Tools** — `@tool` decorator and `StructuredTool`. See
   `app/tools/*.py` and the `langgraph.md` doc for the graph side.

That's it. We do not use LangChain's chains, agents (the legacy
`AgentExecutor`), memory, document loaders, or vector stores. We use
LangGraph for orchestration and Qdrant directly for retrieval.

---

## 1. Mental model

LangChain is mostly a collection of interfaces and a serialization
format (`langchain-core` plus a small set of provider packages like
`langchain-openai`, `langchain-anthropic`, `langchain-aws`).

The base interface is `Runnable`:

```
input → runnable.invoke(input) → output
       runnable.stream(input)  → iterator of output chunks
       runnable.batch([inputs]) → list of outputs
```

Everything that takes input and produces output is a `Runnable`: chat
models, prompts, output parsers, retrievers, tools. You compose them
with the `|` operator (LCEL — LangChain Expression Language):

```python
chain = prompt | model | output_parser
result = chain.invoke({"topic": "EKS"})
```

Strata does not use LCEL chains (LangGraph replaces them), but you'll
see LCEL in tutorials. The mental model is: a chain is a function of
functions. A graph is a chain with branches and cycles.

---

## 2. Messages

`langchain_core.messages` is the most important module in LangChain.
Everything revolves around the message types. The agent loop is just:
append messages, send to model, append response, repeat.

```python
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    AIMessageChunk,    # streaming token
    ToolCall,          # structured tool-call request inside an AIMessage
)
```

### Roles

| Type | Who | What it carries |
|---|---|---|
| `SystemMessage` | developer | behavior instructions, persona, hard rules |
| `HumanMessage` | user | the prompt |
| `AIMessage` | assistant | model response — text content AND `tool_calls` |
| `ToolMessage` | tool | result of a tool call, keyed by `tool_call_id` |
| `FunctionMessage` | (legacy) | old tool-result type, use `ToolMessage` |

### How an AIMessage encodes tool calls

When the model wants to call a tool, the response is an `AIMessage`
whose `content` may be empty and whose `tool_calls` is a non-empty list:

```python
AIMessage(
    content="",
    tool_calls=[
        ToolCall(name="list_clusters", args={}, id="call-abc123"),
    ],
)
```

The `id` is the **correlation key**. When you build the `ToolMessage`
result, you set its `tool_call_id="call-abc123"`. LangGraph and the
model itself use this to know which tool call the result answers. If
you mismatch the id, the conversation state is corrupted.

### How a ToolMessage answers a tool call

```python
ToolMessage(
    content='[{"id": "cl-001", ...}]',   # string! content is always a string
    name="list_clusters",
    tool_call_id="call-abc123",
)
```

The `content` is a string. If your tool returns a Python object, you
must serialize it (`json.dumps`, `str()`, or `pydantic.model_dump_json`).

### The alternation invariant

The model never sees a `ToolMessage` without a preceding `AIMessage`
that requested it. If it does, the model will get confused or refuse.
LangGraph's `ToolNode` enforces this for you. If you ever build the
state by hand, respect the alternation:

```
HumanMessage → AIMessage → ToolMessage → AIMessage → ToolMessage → AIMessage
```

### Streaming

When the model is invoked with `streaming=True`, the response is an
iterator of `AIMessageChunk` objects. Each chunk has the same shape as
an `AIMessage` (so you can `.content` it) but only carries the
delta for that chunk. To reconstruct the full `AIMessage`, accumulate
chunks: `chunk.content` concatenates, `chunk.tool_call_chunks` carries
partial tool-call arguments. Strata does not stream yet (Phase 2 emits
the final state as NDJSON); Phase 5+ uses LangGraph's `astream`.

---

## 3. Chat models

`BaseChatModel` is the abstract base. The concrete types you'll touch
in Strata are `ChatOpenAI` (used as the LiteLLM adapter) and
`ChatBedrock` (NOT used — we go through LiteLLM).

### `ChatOpenAI` pointed at LiteLLM

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="nova-pro",                      # the model_list entry name in LiteLLM
    base_url="http://litellm:4000/v1",     # LiteLLM is OpenAI-compatible
    api_key=os.environ["LITELLM_API_KEY"],
    temperature=0.2,
    streaming=True,
)
```

Two things to internalize:

1. **The `model` parameter is the name as registered in LiteLLM's
   `model_list`**, not the Bedrock model id. LiteLLM translates. See
   `docs/litellm.md`.
2. **`base_url` must end in `/v1`**. The OpenAI SDK appends
   `/chat/completions` to whatever you pass.

### `.bind_tools(...)` and `tools_condition`

`.bind_tools(tools)` returns a new `Runnable` that, when invoked, will
emit `AIMessage`s with `tool_calls` populated. The `tools` argument is
a list of LangChain `BaseTool` objects — exactly what `@tool` produces.

```python
llm = ChatOpenAI(...).bind_tools([list_clusters, get_cluster_status, ...])
```

The model receives the tools' **JSON schemas** (derived from the
function's type annotations and docstring). The docstring is the tool
**description** that the model sees in its system prompt. This is why
docstring quality matters.

`tools_condition` (in `langgraph.prebuilt`) is the standard router
function for `add_conditional_edges` — given the last message, it
returns the string `"tools"` if there are tool calls, else `END`. See
`docs/langgraph.md`.

### `invoke` vs `stream` vs `astream`

- `invoke(input)` — synchronous, returns the final `AIMessage`. Use in
  tests and in graph nodes.
- `stream(input)` — synchronous generator of chunks. Use when you need
  to forward tokens to a UI in real time.
- `astream(input)` — async generator. Use inside FastAPI.

For Strata's `POST /chat`, Phase 2 calls `invoke` synchronously and
streams the final state as NDJSON. Phase 5+ switches to `astream` for
true token streaming.

---

## 4. Tools (`@tool`)

A LangChain `Tool` is just a function with a name, a description, and
an argument schema. `@tool` is a decorator that turns a function into a
`StructuredTool`.

```python
from langchain_core.tools import tool

@tool
def get_cluster_status(cluster_id: str) -> dict:
    """Get the current status of one EKS cluster by its id.

    Use this when the user asks for the status of a specific cluster.
    """
    return {"id": cluster_id, "status": "READY"}
```

The decorator reads the function signature and docstring to build a
JSON schema that the model sees. What the model sees:

```json
{
  "name": "get_cluster_status",
  "description": "Get the current status of one EKS cluster by its id. Use this when the user asks for the status of a specific cluster.",
  "parameters": {
    "type": "object",
    "properties": {"cluster_id": {"type": "string"}},
    "required": ["cluster_id"]
  }
}
```

### What `@tool` does and does NOT do

✅ **Does:**
- Builds the JSON schema from annotations.
- Wraps the function in a `StructuredTool`.
- Surfaces the function's name, docstring, and signature to the LLM.
- Validates arguments against the schema when invoked.

❌ **Does NOT:**
- Handle async (use `@tool(coroutine=...)` if your tool is `async def`).
- Apply retries, timeouts, or error formatting.
- Validate return types (the model's only view of the result is the
  `ToolMessage.content` string).

### Tool docstrings are the API

Because the LLM picks tools based on the description, your docstring
is the **API contract** between you and the model. A bad docstring
means the model calls the wrong tool. Conventions:

- One-line summary first.
- "Use this when..." clause — describes the *intent*, not the
  mechanics.
- Describe the shape of the return value if it's not obvious.
- Mention edge cases: "Returns NOT_FOUND if the id is unknown."

### Returning a Pydantic model

You can return a Pydantic model from a tool. LangChain serializes it
via `model_dump_json()`:

```python
class ClusterStatus(BaseModel):
    id: str
    status: str

@tool
def get_status(cluster_id: str) -> ClusterStatus:
    """..."""
    return ClusterStatus(id=cluster_id, status="READY")
```

The model receives the JSON. Strata's tools currently return `dict`s
(`model.model_dump()`) for simplicity, but the Pydantic form is fine
too.

### Async tools

If your tool is I/O-bound (Phase 3+ HTTP calls to the orchestrator),
make it async:

```python
@tool
async def get_cluster_status(cluster_id: str) -> dict:
    """..."""
    async with httpx.AsyncClient() as c:
        r = await c.get(f"http://orchestrator:8080/clusters/{cluster_id}")
        return r.json()
```

`ToolNode` awaits async tools correctly.

### Invoking a tool directly (for tests)

`@tool` produces a `StructuredTool` with an `.invoke(args)` method
that takes a dict of arguments:

```python
out = get_cluster_status.invoke({"cluster_id": "cl-001"})
# returns {"id": "cl-001", "status": "READY", ...}
```

You can also call `await get_cluster_status.ainvoke(...)` for async.

---

## 5. Prompts

Strata uses a literal `SystemMessage` in `app/graph.py`'s
`call_model` node. We don't use `ChatPromptTemplate` because the
system prompt is a constant string and the user message is just the
last human turn. If you ever need templated prompts (e.g. variables
from Postgres, role-based instructions), `ChatPromptTemplate` is the
right tool.

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant for {domain}."),
    ("placeholder", "{messages}"),   # the conversation history
])

chain = prompt | model
```

The `placeholder` slot is the convention for "inject the entire
conversation history here." It's used heavily in LangGraph
applications where the state contains a `messages` list.

For Strata's `agent-architecture.md` and `agent-system-prompt.md` work
in Phase 6+ (confirmation UX, role-based instructions), the prompt
template will get non-trivial.

---

## 6. Output parsers

`PydanticOutputParser` and `JsonOutputParser` force the model to return
structured output conforming to a schema. We don't use them in Phase 2
(the model returns natural language and the tools return Pydantic
models). For RAG's `retrieve_docs` in Phase 4+, you might want a
structured "did the docs answer this?" check that the model returns
as JSON — that's where `PydanticOutputParser` shines.

```python
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel

class Answer(BaseModel):
    summary: str
    citations: list[str]

parser = PydanticOutputParser(pydantic_object=Answer)

prompt = ChatPromptTemplate.from_messages([...]).partial(
    format_instructions=parser.get_format_instructions(),
)
chain = prompt | model | parser
```

The parser retries on parse failures up to a configurable limit.

---

## 7. Retrievers and vector stores

LangChain has abstractions for vector stores (`VectorStore`) and
retrievers (`BaseRetriever`). Strata does NOT use them — the
`retriever-service` Go service talks to Qdrant directly and exposes
HTTP, and `agent-service` calls that HTTP via `httpx` (Phase 4+).

Why we bypass: centralizes the embedding model choice in the
retriever-service (per the AGENTS.md cross-cutting rule), keeps the
Python side simple, and lets us swap Qdrant for pgvector later without
touching the agent.

You will see LangChain's `VectorStore` and `BaseRetriever` in RAG
tutorials. They are the right tool when you don't have a separate
retrieval service. Strata has one.

---

## 8. Runnables, briefly

`Runnable` is the base protocol. The `|` operator composes them.
`RunnableLambda` wraps a plain function:

```python
from langchain_core.runnables import RunnableLambda

strip = RunnableLambda(lambda x: x.strip())
chain = prompt | model | strip
```

`RunnableConfig` is the runtime config that gets passed down — useful
for things like `tags`, `metadata` (for LangSmith tracing), and
`configurable` (for swapping models at runtime).

Strata does not use LangSmith (yet). If you wire it in, set
`LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY=...` as env vars
on the agent-service Deployment.

---

## 9. Common pitfalls (in this codebase specifically)

1. **Importing `from app.tools import list_clusters` gives you the
   module, not the function.** You need either
   `from app.tools.list_clusters import list_clusters` OR a
   re-export in `app/tools/__init__.py` (Strata does the latter — see
   `app/tools/__init__.py`).
2. **Tool `content` is always a string.** If your tool returns a
   Pydantic model, use `.model_dump_json()` not `.model_dump()`.
3. **`@tool` on a no-argument function**: works fine, but the
   generated schema is empty (`{"properties": {}}`). Don't add a
   fake argument just to satisfy yourself; the model is fine with
   no-arg tools.
4. **`ChatOpenAI` requires `base_url` to end in `/v1`.** LiteLLM
   expects `/v1/chat/completions`, not `/chat/completions`. The
   `litellm_provider.py` does `f"{LITELLM_BASE_URL}/v1"`.
5. **`bind_tools` is on the `Runnable` returned by `ChatOpenAI`, not
   on `ChatOpenAI` itself.** The pattern is
   `llm.bind_tools(tools).invoke(messages)`.
6. **The model name passed to `ChatOpenAI(model=...)` is the
   LiteLLM-side alias**, not the Bedrock model id. If you set
   `model="bedrock/amazon.nova-pro-v1:0"`, LiteLLM will try to look
   that up — it works for direct-Bedrock mode but defeats the
   abstraction. Use the alias from your `model_list` (e.g.
   `"nova-pro"`).

---

## 10. What to read next

- `docs/langgraph.md` — the state machine, ToolNode, streaming, checkpointer.
- `docs/litellm.md` — model_list, embeddings, retries, the proxy.
- `docs/rag.md` — the retriever-service contract, chunking, metadata filtering.
- `docs/strata/agent-architecture.md` — how Strata actually uses all of this.
- LangChain docs: <https://python.langchain.com/docs/introduction/>
- LangChain conceptual guide: <https://python.langchain.com/docs/concepts/>
