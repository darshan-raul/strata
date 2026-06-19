# Strata docs

Reference documentation for the technologies Strata is built on
and the project's own architecture. Read these in order if you're
new to the project; jump to a specific doc if you know what you
need.

---

## Learning order

If you're new to the agentic-AI stack, read in this order:

1. **[langchain.md](./langchain.md)** + the
   **[langchain/](./langchain/)** deep-dive — chat models,
   messages, tools, the `Runnable` protocol, output parsers,
   runnables, streaming, caching, tracing, testing. The base
   layer.
2. **[langgraph.md](./langgraph.md)** + the
   **[langgraph/](./langgraph/)** deep-dive — state machines on
   top of LangChain. `StateGraph`, `ToolNode`,
   `tools_condition`, `Command`, checkpointers, `interrupt()`,
   subgraphs, HITL, streaming, memory stores. The orchestration
   layer.
3. **[litellm.md](./litellm.md)** — the OpenAI-compatible proxy
   that sits between Strata and the actual LLM providers. The
   model layer.
4. **[bedrock.md](./bedrock.md)** — what's behind LiteLLM in our
   default config. Nova Pro, Titan v2, SigV4 auth. The provider
   layer.
5. **[rag.md](./rag.md)** — retrieval-augmented generation, the
   retriever-service, Qdrant, the `retrieve` node. The context
   layer.
6. **[nextjs.md](./nextjs.md)** — the web UI in Phase 5+. App
   Router, server components, server actions, streaming. The
   presentation layer.

Then read the project-specific doc:

7. **[strata/agent-architecture.md](./strata/agent-architecture.md)** —
   how all of the above fit together in Strata. The graph, the
   two services, the k8s manifests, the NDJSON wire format.

---

## By topic

| Topic | Doc(s) | Phase | What it covers |
|---|---|---|---|
| LangChain | [langchain.md](./langchain.md), [langchain/](./langchain/) | 2+ | The full LangChain surface: package layout, messages, chat models, tools, prompts, runnables, streaming, caching, tracing, testing. |
| LangGraph | [langgraph.md](./langgraph.md), [langgraph/](./langgraph/) | 2+ | The full LangGraph surface: state, reducers, nodes, edges, `Command`, `ToolNode`, subgraphs, streaming, checkpointers, memory store, HITL, deployment, pitfalls. |
| LiteLLM | [litellm.md](./litellm.md) | 2+ | model_list, embeddings, retries, master key, virtual keys, provider swap. |
| AWS Bedrock | [bedrock.md](./bedrock.md) | 2+ | Nova Pro, Titan v2, SigV4, regions, IAM, Converse API, streaming, throttling, cost. |
| RAG | [rag.md](./rag.md) | 4+ | Qdrant, retriever-service, rag-indexer, the retrieve node. |
| Next.js | [nextjs.md](./nextjs.md) | 5+ | App Router, server components, server actions, streaming tokens, auth, forms, Tailwind, shadcn/ui, pnpm. |
| Strata architecture | [strata/agent-architecture.md](./strata/agent-architecture.md) | 2+ | The graph, the two services, the k8s surface, NDJSON wire format, what's deferred. |

---

## The langchain/ deep-dive

8 focused files. Read in order for a full mental model, or jump
to a single file for a reference.

| File | What it covers |
|---|---|
| [langchain/01-mental-model.md](./langchain/01-mental-model.md) | Package layout, the `Runnable` protocol, LCEL, why LangGraph instead of chains, versioning. |
| [langchain/02-messages.md](./langchain/02-messages.md) | All message types, the `id` correlation key, `AIMessage` internals, `ToolMessage`, streaming chunks, the alternation invariant. |
| [langchain/03-chat-models.md](./langchain/03-chat-models.md) | `ChatOpenAI` pointed at LiteLLM, `bind_tools` / `with_structured_output` / `with_retry` / `with_fallbacks`, `astream_events` deep dive. |
| [langchain/04-tools.md](./langchain/04-tools.md) | `@tool` decorator deep, `StructuredTool.from_function`, `BaseTool` subclassing, `InjectedToolArg`, error handling, `Command` returns. |
| [langchain/05-prompts-and-parsers.md](./langchain/05-prompts-and-parsers.md) | `ChatPromptTemplate`, `MessagesPlaceholder`, `partial`, `FewShotPromptTemplate`, `PydanticOutputParser`, retry parsers. |
| [langchain/06-runnables-and-streaming.md](./langchain/06-runnables-and-streaming.md) | `Runnable` deep: `RunnableParallel`, `RunnablePassthrough`, `RunnableBranch`, `RunnableWithFallbacks`, `astream_events` full taxonomy. |
| [langchain/07-caching-memory-tracing.md](./langchain/07-caching-memory-tracing.md) | Caching, why we don't use LangChain memory, LangSmith, `BaseCallbackHandler`, custom callbacks. |
| [langchain/08-testing-and-pitfalls.md](./langchain/08-testing-and-pitfalls.md) | `FakeListChatModel`, graph tests, async tool tests, package migration notes. |

---

## The langgraph/ deep-dive

12 focused files. Read in order for a full mental model, or jump
to a single file for a reference.

| File | What it covers |
|---|---|
| [langgraph/01-mental-model.md](./langgraph/01-mental-model.md) | Why a state machine, the four concepts (state, nodes, edges, channels), `compile()` and run, vs. alternatives, package layout, the functional API. |
| [langgraph/02-state-and-reducers.md](./langgraph/02-state-and-reducers.md) | `TypedDict` schemas, `add_messages` reducer, custom reducers, `state_schema` / `input_schema` / `output_schema`, runtime context. |
| [langgraph/03-nodes-and-edges.md](./langgraph/03-nodes-and-edges.md) | `add_node` (with metadata, retry, cache_policy), `add_edge` from `START` / `END`, conditional edges, `path_map`, `Send` for map-reduce. |
| [langgraph/04-command-and-control-flow.md](./langgraph/04-command-and-control-flow.md) | `Command(goto, update, graph, resume)`, dynamic routing, `Command.PARENT`, the `interrupt()` function. |
| [langgraph/05-toolnode-and-tools_condition.md](./langgraph/05-toolnode-and-tools_condition.md) | `ToolNode` deep dive, parallel tool calls, `handle_tool_errors`, `tools_condition` source, custom routers. |
| [langgraph/06-subgraphs-and-map-reduce.md](./langgraph/06-subgraphs-and-map-reduce.md) | Subgraphs as nodes, state isolation, `input` / `output` schemas, `Command.PARENT`, `Send` patterns, parallel branches. |
| [langgraph/07-streaming.md](./langgraph/07-streaming.md) | All `stream_mode` values, `astream_events` deep, mapping to Strata's NDJSON and SSE wire formats. |
| [langgraph/08-checkpoints-and-persistence.md](./langgraph/08-checkpoints-and-persistence.md) | `MemorySaver`, `SqliteSaver`, `PostgresSaver`, `thread_id`, `get_state` / `get_state_history`, time travel via `update_state`, `durability` modes. |
| [langgraph/09-memory-store.md](./langgraph/09-memory-store.md) | `InMemoryStore` / `PostgresStore`, namespace conventions, `put` / `get` / `search`, semantic search, per-user facts. |
| [langgraph/10-human-in-the-loop.md](./langgraph/10-human-in-the-loop.md) | `interrupt()`, `Command(resume=...)`, static interrupts, multi-interrupt flows, Strata's mutation-tool confirmation (Phase 6+). |
| [langgraph/11-deployment-and-debug.md](./langgraph/11-deployment-and-debug.md) | `recursion_limit`, `durability`, LangGraph CLI, Studio, debugging recipes, common runtime errors. |
| [langgraph/12-pitfalls.md](./langgraph/12-pitfalls.md) | A consolidated list of "I lost an hour to this" bugs. |

---

## Companion documents (not in `docs/`)

- **[AGENTS.md](../AGENTS.md)** — the source of truth for the plan,
  locked decisions, and phase status. Read first in any new
  session.
- **[handoff.md](../handoff.md)** — live state across sessions.
  Read second.
- **[README.md](../README.md)** — human-facing project overview.
- **[specs/strata_master_doc.md](../specs/strata_master_doc.md)** —
  historical design doc (Phase 0/1 era, will be rewritten).
- **[specs/sample_app_architecture.md](../specs/sample_app_architecture.md)** —
  the sample Go microservices app that runs on Strata-provisioned
  clusters.

---

## Doc conventions

- All docs are written assuming you're a senior AWS + k8s
  engineer who knows nothing about LangChain, LangGraph, RAG, or
  Bedrock. (That's the original author; if you're past that, the
  early sections may feel slow.)
- Code examples are project-shaped (Strata's actual files, not
  toy examples).
- "Phase 2", "Phase 5", etc. refer to phases in
  [AGENTS.md §4](../AGENTS.md#4-build-phases).
- The word "**carrier**" refers to AWS/k8s infrastructure.
  The word "**product**" refers to the agentic-AI work. The
  design principle is "the agent is the product, the AWS plumbing
  is the carrier."
- Tech-reference docs (langchain/, langgraph/) are written
  against the latest edge of LangChain / LangGraph (1.0+ / 0.3+),
  with older concepts (e.g. `langchain_community`,
  `AgentExecutor`, `ConversationBufferMemory`) called out as
  "legacy / migration notes" so you're not surprised when you
  encounter them in older tutorials.
