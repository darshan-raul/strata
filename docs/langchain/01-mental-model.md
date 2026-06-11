# LangChain — Mental Model & Package Layout

> **Part 1 of the LangChain deep-dive.** Start here. Subsequent
> files cover messages, chat models, tools, prompts, runnables,
> streaming, caching, and testing.

LangChain is mostly a collection of **interfaces** and a
**serialization format**, with a small set of provider packages that
implement the interfaces. The single most important interface is
`Runnable`. Everything in LangChain is a `Runnable`, and the `|`
operator composes them.

Strata uses LangChain in two narrow places:

1. **Chat models** — `langchain_openai.ChatOpenAI` pointed at
   LiteLLM (see [`litellm.md`](../litellm.md)). We never import a
   vendor SDK directly.
2. **Tools** — `@tool` decorator and `StructuredTool`. See the tools
   file and the `langgraph/` deep-dive for the orchestration side.

We do **not** use LangChain's chains, the legacy `AgentExecutor`,
memory, document loaders, or vector stores. We use LangGraph for
orchestration and Qdrant directly (through `retriever-service`) for
retrieval.

---

## 1. The package layout

The "import from `langchain`" tutorial form is mostly historical.
Modern LangChain is split across many small packages. You should
import from the most specific one available.

| Package | What it has | When you import from it |
|---|---|---|
| `langchain-core` | `Runnable`, messages, prompts, output parsers, `BaseChatModel` (abstract), tools | Always. This is the foundation. |
| `langchain` | The "metapackage" — pulls in common integrations. Mostly empty in 1.0+. | Almost never. Prefer the specific provider package. |
| `langchain-openai` | `ChatOpenAI`, `OpenAIEmbeddings` | When talking to OpenAI or any OpenAI-compatible endpoint (LiteLLM, vLLM, Ollama's OpenAI mode). |
| `langchain-aws` | `ChatBedrock`, `BedrockEmbeddings` | When talking to Bedrock directly. **Strata does NOT do this.** |
| `langchain-anthropic` | `ChatAnthropic` | Direct Anthropic. Strata goes through LiteLLM, not here. |
| `langchain-ollama` | `ChatOllama` | Local Ollama. Useful for offline dev. |
| `langchain-community` | Everything not promoted to its own package | **Avoid.** Being deprecated; most things have been promoted or are stale. |
| `langgraph` | `StateGraph`, `ToolNode`, checkpointers, stores | The orchestration layer. See `langgraph/`. |
| `langchain-text-splitters` | Recursive character, markdown, code splitters | Phase 4+ RAG. |
| `langsmith` | Tracing client | Optional; only if you wire up LangSmith. |

**Strata's `pyproject.toml` (Phase 2):**

```toml
dependencies = [
  "langchain-core>=0.3",         # Runnable, messages, @tool
  "langchain-openai>=0.3",       # ChatOpenAI pointed at LiteLLM
  "langgraph>=0.2",              # StateGraph, ToolNode, checkpointers
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "httpx>=0.27",                 # for retriever-service calls (Phase 4+)
  "pydantic>=2.7",
]
```

No `langchain` metapackage. No `langchain-aws`. No `langchain-community`.

> **"Latest edge" version pinning note.** As of writing, LangChain
> 1.0 is the new line and the imports tighten further (e.g.
> `from langchain.chat_models import ...` is being collapsed back
> into a single tree). The above works on 0.3.x and 1.x; check
> release notes when bumping.

---

## 2. The `Runnable` protocol

`Runnable` is the abstract base class for everything that takes an
input and produces an output. Chat models, prompts, output parsers,
retrievers, tools — all are `Runnable`s. You invoke them all the
same way.

The interface:

```python
class Runnable(Generic[Input, Output]):
    def invoke(self, input: Input, config: RunnableConfig | None = None) -> Output: ...
    async def ainvoke(self, input: Input, config: RunnableConfig | None = None) -> Output: ...
    def stream(self, input: Input, config: RunnableConfig | None = None) -> Iterator[Output]: ...
    async def astream(self, input: Input, config: RunnableConfig | None = None) -> AsyncIterator[Output]: ...
    def batch(self, inputs: list[Input], config: RunnableConfig | None = None) -> list[Output]: ...
    async def abatch(self, inputs: list[Input], config: RunnableConfig | None = None) -> list[Output]: ...
```

Six methods. Everything in LangChain implements them. (Some methods
on some classes are not implemented efficiently — e.g. `stream` on a
non-streaming model just yields the full result at the end — but
the interface is uniform.)

### What can be a `Runnable`

| Construct | What it wraps |
|---|---|
| `ChatOpenAI(...)` | A chat model. Input = messages, output = `AIMessage`. |
| `ChatPromptTemplate.from_messages([...])` | A prompt template. Input = variables dict, output = `PromptValue` (a list of messages). |
| `StrOutputParser()` | A parser. Input = `AIMessage`, output = `str`. |
| `RunnableLambda(fn)` | A plain Python function. Input = whatever, output = whatever. |
| `RunnablePassthrough()` | Returns its input unchanged. |
| `RunnableParallel({...})` | Runs multiple runnables in parallel on the same input. |
| `RunnableBranch([(cond, run), ...], default)` | Picks a runnable based on a condition. |
| `RunnableWithFallbacks(primary, fallbacks=[...])` | Tries the primary, falls back on error. |
| `@tool` | A function with schema. Has the `Runnable` interface so it composes in chains. |

### The `|` operator — LCEL (LangChain Expression Language)

LCEL is the syntactic sugar for "feed the output of the left side
into the input of the right side." It's a `RunnableSequence` under
the hood.

```python
chain = prompt | model | parser
# is the same as
chain = RunnableSequence(first=prompt, middle=[model], last=parser)
```

`chain.invoke({"topic": "EKS"})` runs the prompt, feeds the result
into the model, feeds the model's output into the parser, returns
the final value.

**Strata does not use chains in production code.** LangGraph
replaces them. But you'll see `prompt | model | parser` all over
LangChain tutorials. Understand it; don't reach for it inside a
graph.

### The `RunnableConfig`

The `config` argument threads through every `Runnable` call. It
carries:

| Field | Purpose |
|---|---|
| `tags` | Labels for filtering. E.g. `tags=["prod", "user-42"]` so LangSmith traces can be filtered. |
| `metadata` | Arbitrary dict for observability. |
| `run_name` | Human-readable name for the run. |
| `max_concurrency` | For `.batch()`. |
| `recursion_limit` | For graphs. |
| `configurable` | The magic bag — `configurable={"thread_id": "..."}` reaches into the checkpointer. |

In a graph, LangGraph fills in `configurable` for you based on
what you pass to `graph.invoke(input, config=...)`. Tools and
nodes access it via `runtime.config` or `RunnableConfig` in the
signature.

---

## 3. Sync vs. async vs. streaming

| Need | Method | When to use |
|---|---|---|
| Fire one call, get the result | `invoke` | Tests, graph nodes (LangGraph handles the threading). |
| Fire one call, get chunks | `stream` | Sync code that wants to forward tokens. |
| Fire one call, get the result, in async context | `ainvoke` | FastAPI handler. |
| Fire one call, get chunks, in async context | `astream` | FastAPI handler streaming tokens. |
| Fire many calls, sequentially | `batch` | Bulk processing. |
| Fire many calls, in parallel, async | `abatch` | Bulk async. |
| Get the full event stream (callbacks, lifecycle) | `astream_events(version="v2")` | UI-side observability. |

For Strata's Phase 2, `POST /chat` calls `graph.invoke(...)`
synchronously and walks the final `messages` list. Phase 5+ moves
to `graph.astream(stream_mode="messages")` for true token streaming.

Inside FastAPI, **always** prefer `ainvoke` / `astream` over
wrapping `invoke` in `asyncio.to_thread`. The thread pool is a
workaround for libraries that don't natively support async, but
LangChain does.

---

## 4. Why LangGraph, not chains

Chains are great for **linear** flows: prompt → model → parser.
They fall over for **agentic** flows where the model decides to
call a tool, the tool result feeds back into the model, and the
model decides again.

The agent loop is:

```
        ┌──────────────┐
        │   START      │
        └──────┬───────┘
               ▼
        ┌──────────────┐
   ┌───►│  call_model  │◄────────┐
   │    └──────┬───────┘         │
   │           │ tool_calls?     │
   │           ▼                 │
   │    ┌──────────────┐         │
   │    │  ToolNode    │─────────┘
   │    └──────────────┘
   │           │ no more tools
   │           ▼
   │    ┌──────────────┐
   │    │     END      │
   │    └──────────────┘
```

You can fake this with chains (a recursive Python function) but
you lose:

- **Durable state.** A LangGraph checkpointer saves the state
  between turns; a Python function lives in memory.
- **Time travel.** `get_state_history` lets you rewind a
  conversation. A Python function can't.
- **Human-in-the-loop.** `interrupt()` pauses the graph until a
  human responds. A Python function blocks the thread.
- **Subgraph composition.** A compiled graph can be a node in
  another graph. A Python function can call another function but
  can't suspend and resume cleanly.
- **Streaming primitives.** `stream_mode="messages"` is built in.
  Doing it yourself means writing an `asyncio` event loop.

Read the LangGraph deep-dive for the full surface.

---

## 5. What LangChain is NOT

- **It is not an LLM.** It's an SDK for talking to LLMs. The LLM
  is a separate service (Bedrock, OpenAI, etc.).
- **It is not an agent framework on its own** (anymore). The
  legacy `AgentExecutor` is deprecated. Agents are built with
  LangGraph.
- **It is not a vector store.** Qdrant, pgvector, Pinecone, etc.
  are separate services. LangChain has thin adapters (`VectorStore`)
  but Strata bypasses them — see `rag.md`.
- **It is not a memory system.** LangChain's "memory" classes
  (`ConversationBufferMemory`, etc.) are legacy abstractions over
  the message list. Use a LangGraph checkpointer instead.

---

## 6. Versioning and what to pin

LangChain moves fast. Pin a minimum version, not an exact version,
and read the changelog when bumping.

| Package | Recommended pin (Strata, mid-2026) | Notes |
|---|---|---|
| `langchain-core` | `>=0.3,<1.0` or `>=1.0` | Breaking changes between minor versions are rare but happen. |
| `langchain-openai` | `>=0.3` | Tracks `openai` SDK. |
| `langgraph` | `>=0.2` | The 0.2 line introduced `interrupt()` and durable execution. |
| `langgraph-checkpoint-postgres` | `>=2.0` | Phase 6+. |
| `langgraph-checkpoint-sqlite` | `>=2.0` | Local dev / tests. |

When in doubt, `uv lock` will resolve to a known-good set. Don't
hand-pin upper bounds unless you've hit a regression.

---

## 7. How Strata uses this

- **Phase 2:** `langchain_core.messages` (`HumanMessage`,
  `AIMessage`, `SystemMessage`, `ToolMessage`) and
  `langchain_core.tools.tool` (the `@tool` decorator).
  `langchain_openai.ChatOpenAI` pointed at LiteLLM.
  `langgraph.prebuilt` (`ToolNode`, `tools_condition`).
- **Phase 3+:** Same. Tools become async and call the orchestrator
  over HTTP.
- **Phase 4+:** Add `langchain_text_splitters` for `docs/` chunking
  in the rag-indexer Go service's Python pre-step (or do it in Go).
- **Phase 6+:** `langgraph_checkpoint_postgres.PostgresSaver` for
  the production checkpointer. `langgraph_checkpoint_sqlite` for
  local dev.

The "what to read next" chain is:

1. `02-messages.md` — the message types are the atom of the agent loop.
2. `03-chat-models.md` — the model layer.
3. `04-tools.md` — `@tool` and the `BaseTool` hierarchy.
4. `../langgraph/01-mental-model.md` — once you have the LangChain
   primitives, you can build a graph.

---

## 8. What to read next (external)

- LangChain v1 docs: <https://python.langchain.com/docs/introduction/>
- LangChain conceptual guide: <https://python.langchain.com/docs/concepts/>
- LCEL cheatsheet: <https://python.langchain.com/docs/how_to/lcel_cheatsheet/>
- Runnable API reference: <https://api.python.langchain.com/en/stable/runnables.html>
- `docs/langchain/02-messages.md` — next in this deep-dive.
