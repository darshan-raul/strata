# LangChain

The Python SDK that gives Strata standardized interfaces to chat
models, prompts, output parsers, tools, and the runnable
composition language. LangGraph sits **on top** of LangChain; you
can't really understand one without the other. Read this file
first, then dive into the parts you need below.

Strata uses LangChain in two narrow places:

1. **Chat models** — `langchain_openai.ChatOpenAI` pointed at
   LiteLLM (see [`litellm.md`](litellm.md)). We never import a
   vendor SDK directly.
2. **Tools** — `@tool` decorator and `StructuredTool`. See the
   tools file and the [`langgraph/`](langgraph/) deep-dive for
   the orchestration side.

That's it. We do not use LangChain's chains, agents (the legacy
`AgentExecutor`), memory, document loaders, or vector stores. We
use LangGraph for orchestration and Qdrant directly (through
`retriever-service`) for retrieval.

---

## How this doc is organized

The deep-dive is split across 8 focused files. Read in order for
a full mental model, or jump to a single file for a reference.

| File | What it covers |
|---|---|
| [01-mental-model.md](langchain/01-mental-model.md) | Package layout, the `Runnable` protocol, LCEL, why LangGraph instead of chains, versioning. |
| [02-messages.md](langchain/02-messages.md) | All message types, the `id` correlation key, `AIMessage` internals, `ToolMessage`, streaming chunks, the alternation invariant. |
| [03-chat-models.md](langchain/03-chat-models.md) | `ChatOpenAI` pointed at LiteLLM, `bind_tools` / `with_structured_output` / `with_retry` / `with_fallbacks`, `astream_events` deep dive. |
| [04-tools.md](langchain/04-tools.md) | `@tool` decorator deep, `StructuredTool.from_function`, `BaseTool` subclassing, `InjectedToolArg`, error handling, `Command` returns. |
| [05-prompts-and-parsers.md](langchain/05-prompts-and-parsers.md) | `ChatPromptTemplate`, `MessagesPlaceholder`, `partial`, `FewShotPromptTemplate`, `PydanticOutputParser`, retry parsers. |
| [06-runnables-and-streaming.md](langchain/06-runnables-and-streaming.md) | `Runnable` deep: `RunnableParallel`, `RunnablePassthrough`, `RunnableBranch`, `RunnableWithFallbacks`, `astream_events` full taxonomy. |
| [07-caching-memory-tracing.md](langchain/07-caching-memory-tracing.md) | Caching, why we don't use LangChain memory, LangSmith, `BaseCallbackHandler`, custom callbacks. |
| [08-testing-and-pitfalls.md](langchain/08-testing-and-pitfalls.md) | `FakeListChatModel`, graph tests, async tool tests, package migration notes. |

For the orchestration layer, see [`langgraph.md`](langgraph.md)
and the [`langgraph/`](langgraph/) deep-dive.

---

## What Strata actually uses (one-paragraph summary)

`langchain_core.messages` (`SystemMessage`, `HumanMessage`,
`AIMessage`, `ToolMessage`) and `langchain_core.tools.tool`
(the `@tool` decorator). `langchain_openai.ChatOpenAI` pointed
at LiteLLM with `bind_tools([...])`. `langgraph.prebuilt` for
`ToolNode` and `tools_condition`. That's the whole surface. The
rest of LangChain is reference material — read it to understand
what you're choosing not to use, and to recognize the patterns
when you read tutorials or other projects' code.

---

## The one mental model

LangChain is a collection of **interfaces** and a
**serialization format**, with provider packages that implement
the interfaces. The single most important interface is
`Runnable`. Everything in LangChain is a `Runnable`, and the `|`
operator composes them.

```
input → runnable.invoke(input) → output
       runnable.stream(input)  → iterator of output chunks
       runnable.batch([inputs]) → list of outputs
```

When you compose runnables with `|`, you get a `RunnableSequence`
(a "chain"). Chains are great for linear flows; they fall over
for agentic flows with cycles. Use LangGraph for those.

---

## How Strata uses this

- **Phase 2:** `langchain_core.messages` and
  `langchain_core.tools.tool`. `langchain_openai.ChatOpenAI`
  pointed at LiteLLM. `langgraph.prebuilt` (`ToolNode`,
  `tools_condition`).
- **Phase 3+:** Same. Tools become async and call the orchestrator
  over HTTP.
- **Phase 4+:** Add `with_structured_output` for the RAG
  "did the docs answer this?" check.
- **Phase 6+:** `langgraph_checkpoint_postgres.PostgresSaver`
  for production. `langgraph_checkpoint_sqlite` for local dev.

---

## What to read next

- **[`langgraph.md`](langgraph.md)** — the orchestration layer.
- **[`langchain/01-mental-model.md`](langchain/01-mental-model.md)**
  — the package layout and the full `Runnable` story.
- **[`langchain/02-messages.md`](langchain/02-messages.md)** —
  messages, the atom of the agent loop.
- **[`litellm.md`](litellm.md)** — the model layer between
  LangChain and Bedrock.
- **[`strata/agent-architecture.md`](strata/agent-architecture.md)**
  — how Strata uses all of this.
- LangChain docs: <https://python.langchain.com/docs/introduction/>
- LangChain conceptual guide: <https://python.langchain.com/docs/concepts/>
