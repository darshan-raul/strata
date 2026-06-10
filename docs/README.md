# Strata docs

Reference documentation for the technologies Strata is built on
and the project's own architecture. Read these in order if you're
new to the project; jump to a specific doc if you know what you
need.

---

## Learning order

If you're new to the agentic-AI stack, read in this order:

1. **[langchain.md](./langchain.md)** — chat models, messages, tools,
   the `Runnable` protocol, output parsers. The base layer.
2. **[langgraph.md](./langgraph.md)** — state machines on top of
   LangChain. `StateGraph`, `ToolNode`, `tools_condition`,
   checkpointers. The orchestration layer.
3. **[litellm.md](./litellm.md)** — the OpenAI-compatible proxy that
   sits between Strata and the actual LLM providers. The model
   layer.
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

| Topic | Doc | Phase | What it covers |
|---|---|---|---|
| LangChain | [langchain.md](./langchain.md) | 2+ | Chat models, messages, tools, runnables, output parsers |
| LangGraph | [langgraph.md](./langgraph.md) | 2+ | StateGraph, ToolNode, conditional edges, checkpointers |
| LiteLLM | [litellm.md](./litellm.md) | 2+ | model_list, embeddings, retries, provider swap |
| AWS Bedrock | [bedrock.md](./bedrock.md) | 2+ | Nova Pro, Titan v2, SigV4, regions, IAM |
| RAG | [rag.md](./rag.md) | 4+ | Qdrant, retriever-service, rag-indexer, the retrieve node |
| Next.js | [nextjs.md](./nextjs.md) | 5+ | App Router, server components, server actions, streaming |
| Strata architecture | [strata/agent-architecture.md](./strata/agent-architecture.md) | 2+ | The graph, the two services, the k8s surface |

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
