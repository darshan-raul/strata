# LangGraph — Memory Store

> **Part 9 of the LangGraph deep-dive.** Cross-thread long-term
> memory via `InMemoryStore` and `PostgresStore`, the namespace
> convention (`("memories", user_id)`), `put` / `get` / `search`,
> and how Strata uses it for per-user facts in Phase 6+.

A checkpointer persists state for a single **thread** (one
conversation). A memory store persists state for a single
**user** (across all conversations). They're complementary:
checkpointer = short-term (this conversation), store =
long-term (everything I know about this user).

---

## 1. Short-term vs. long-term memory

| | Checkpointer | Memory store |
|---|---|---|
| Scope | Per thread (one conversation) | Per user (across all conversations) |
| Lifetime | Per conversation | Permanent (until deleted) |
| Shape | The state schema | `(key, value)` items |
| Reads | Automatic (state at the current step) | Explicit (`store.search`) |
| Writes | Automatic (after every node) | Explicit (`store.put`) |
| Use case | Conversation history | "User prefers dark mode"; "User is on the EKS team" |

Strata's Phase 6+ plan: use the checkpointer for the
conversation; use the memory store for user facts (e.g. "user
prefers `us-west-2`"). At the start of each conversation,
read the user's memory store and inject the facts as a
system message.

---

## 2. The store interface

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()    # dev / tests
# or
from langgraph.store.postgres import AsyncPostgresStore
store = AsyncPostgresStore.from_conn_string("postgresql://...")
# production
```

The store API:

```python
await store.put(
    namespace,    # tuple[str, ...]
    key,          # str
    value,        # dict
    index=None,   # optional: the key for search (if different from key)
)

item = await store.get(namespace, key)
# Returns: Item(value=dict, key=str, namespace=tuple, created_at=..., updated_at=...)

results = await store.search(
    namespace,
    query=None,    # for semantic search
    filter=None,   # for metadata filtering
    limit=10,
    offset=0,
)

await store.delete(namespace, key)

# Bulk / admin
async for namespace in store.list_namespaces(prefix=None):
    ...
```

### The namespace convention

Namespaces are tuples. The convention is `(category, *subcategories)`:

```python
# Strata's plan:
("memories", "user-42")                    # user facts
("memories", "user-42", "preferences")     # categorized user facts
("memories", "user-42", "interactions")    # specific interactions

# A different store might use:
("agent", "facts", "user-42")
("docs", "user-42", "saved-searches")
```

The `prefix` argument to `list_namespaces` is a tuple prefix:

```python
async for ns in store.list_namespaces(prefix=("memories", "user-42")):
    # All namespaces under ("memories", "user-42")
    ...
```

### Keys

Keys are strings, unique within a namespace. Use a meaningful
key, not a random UUID:

```python
await store.put(
    ("memories", "user-42"),
    "preferred-region",
    {"value": "us-west-2", "set_at": "2026-06-01T..."},
)
```

To update, `put` again with the same namespace + key. The
new value replaces.

### Values

Values are dicts. Make them self-describing — include metadata
that helps the model interpret them:

```python
await store.put(
    ("memories", "user-42"),
    "eks-experience",
    {
        "level": "expert",
        "context": "User has been working with EKS for 4 years.",
        "set_at": "2026-05-15T...",
    },
)
```

### `index` for semantic search

If your store has embeddings enabled, `index=` controls which
field gets embedded for search:

```python
await store.put(
    ("memories", "user-42"),
    "eks-experience",
    {"level": "expert", "context": "..."},
    index=["context"],    # embed the "context" field for vector search
)
```

`store.search(namespace, query="how experienced is the user?")`
finds the most semantically similar items.

### The store's embeddings

`PostgresStore` uses `pgvector` for vector search. The
embedding model is configured at store creation:

```python
from langchain_openai import OpenAIEmbeddings

store = AsyncPostgresStore.from_conn_string(
    "postgresql://...",
    index={
        "embed": OpenAIEmbeddings(model="text-embedding-3-small"),
        "dims": 1536,
        "fields": ["context"],    # default field to embed
    },
)
```

Or for Strata, point at LiteLLM:

```python
from langchain_openai import OpenAIEmbeddings

store = AsyncPostgresStore.from_conn_string(
    "postgresql://...",
    index={
        "embed": OpenAIEmbeddings(
            model="titan-embed-v2",    # the LiteLLM alias
            base_url="http://litellm:4000/v1",
            api_key=os.environ["LITELLM_API_KEY"],
        ),
        "dims": 1024,
        "fields": ["context"],
    },
)
```

`InMemoryStore` doesn't support semantic search (no embed
configured by default). Use it for tests only.

---

## 3. The store and the graph — wiring them together

```python
from langgraph.graph import StateGraph

graph = StateGraph(State)
graph.add_node("recall", recall_node)
graph.add_node("call_model", call_model_node)
graph.add_edge(START, "recall")
graph.add_edge("recall", "call_model")
graph.add_edge("call_model", END)
compiled = graph.compile(store=store)
```

The `store` argument to `compile` makes the store available
to every node via the runtime context:

```python
def recall_node(state, runtime: Runtime[Context]) -> dict:
    store = runtime.store
    facts = store.search(("memories", state["user_id"]))
    fact_strings = [f"{item.key}: {item.value}" for item in facts]
    return {
        "messages": [
            SystemMessage(content=f"User facts: {fact_strings}"),
            *state["messages"],
        ],
    }
```

The store is the **read** API. The node decides what to do
with the facts (typically inject as a system message).

### Writing to the store from a node

```python
def remember_node(state, runtime: Runtime[Context]) -> dict:
    store = runtime.store
    # The model produced a fact about the user. Persist it.
    new_fact = state["extracted_fact"]
    await store.aput(
        ("memories", state["user_id"]),
        new_fact["key"],
        new_fact["value"],
        index=["context"],
    )
    return state
```

(Or sync `store.put` for non-async nodes.)

### "Wait — I have two stores?"

The checkpointer persists **state** (one thread's data). The
store persists **memories** (cross-thread data). Different
concepts, different backends. You can have a `PostgresSaver`
checkpointer and a `PostgresStore` memory store using the
same Postgres database — they use different tables.

---

## 4. The store and the `prebuilt` tools

LangGraph provides prebuilt tools for the store:

```python
from langgraph.store.base import BaseStore   # for type hints
from langgraph.prebuilt import InjectedStore
from langchain_core.tools import tool

@tool
async def save_user_fact(
    key: str,
    value: dict,
    store: Annotated[BaseStore, InjectedStore()],
) -> str:
    """Save a fact about the current user to long-term memory.

    Use this when the user tells you a preference or fact about
    themselves, e.g. "I prefer us-west-2" or "I'm on the EKS team."
    """
    user_id = ...  # from config
    await store.aput(("memories", user_id), key, value, index=["value"])
    return f"Saved: {key}"

@tool
async def recall_user_facts(
    query: str,
    store: Annotated[BaseStore, InjectedStore()],
) -> str:
    """Recall facts about the current user from long-term memory.

    Use this when you need to know about the user's preferences,
    past interactions, or context.
    """
    user_id = ...
    items = await store.asearch(("memories", user_id), query=query, limit=5)
    return "\n".join(f"{item.key}: {item.value}" for item in items)
```

These become `@tool`s on the agent. The model can save and
recall facts. The `InjectedStore` marker hides the `store`
arg from the LLM's view.

Strata's Phase 6+ plan: a `remember` and `recall` tool pair,
gated to mutation-confirmation flow (so the model can't
silently store arbitrary data).

---

## 5. When to use the store

- **Per-user facts** that should persist across conversations.
- **Per-user documents** (saved searches, bookmarks).
- **Shared facts** (a team's runbooks, available to all
  conversations).
- **Anything that's not the current conversation's state.**

For Strata Phase 6+:

| What | Store? |
|---|---|
| Conversation history | Checkpointer |
| "User prefers `us-west-2`" | Store (`("memories", user_id)`) |
| "Cluster cl-001 is production" | Store (could also be in the orchestrator's Postgres) |
| "The EKS team has 3 on-calls" | Store (`("team", "eks")`) |
| Retrieved docs from RAG | RAG (Qdrant), not the store |
| Workflow run state | Orchestrator's Postgres |

---

## 6. `InMemoryStore` — dev

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
```

A dict. Lost on restart. For tests and demos.

### Index for semantic search

```python
store = InMemoryStore(index={
    "embed": OpenAIEmbeddings(model="..."),
    "dims": 1536,
    "fields": ["context"],
})
```

`InMemoryStore` does support semantic search if you configure
an embed. The cost is each search calls the embedding model.

### Indexing at put time

```python
store.put(
    ("memories", "user-42"),
    "fact-1",
    {"context": "User is an EKS expert.", "value": "..."},
    index=["context"],
)
```

The `index` argument tells the store which fields to embed.
Without it, semantic search on this item returns nothing.

---

## 7. `PostgresStore` — production

```python
from langgraph.store.postgres import AsyncPostgresStore

store = AsyncPostgresStore.from_conn_string(
    "postgresql://user:pass@host:5432/langgraph",
    index={
        "embed": OpenAIEmbeddings(model="titan-embed-v2", base_url=..., api_key=...),
        "dims": 1024,
        "fields": ["context"],
    },
)

# Initialize the tables:
async with store:
    await store.setup()
```

The tables (`store_items`, `store_vectors`) are created on
`setup()`. Run this once at deployment time.

For Strata Phase 6+: the same Postgres as the checkpointer
(different tables). The agent-service Deployment has both
env vars (`LANGGRAPH_CHECKPOINT_DB_URL`,
`LANGGRAPH_STORE_DB_URL`).

---

## 8. `store.search` — the read API

```python
# Exact-key lookup
item = await store.get(namespace, key)

# Filter by metadata (not vector)
items = await store.search(
    namespace,
    filter={"category": "preferences"},
    limit=10,
)

# Semantic search
items = await store.search(
    namespace,
    query="what does the user like to work on?",
    limit=5,
)

# Both
items = await store.search(
    namespace,
    query="...",
    filter={"category": "preferences"},
    limit=5,
)
```

Returns `list[Item]` ordered by relevance (for semantic) or
recency (for non-semantic). Each `Item` has `key`, `value`,
`namespace`, `created_at`, `updated_at`, `score` (for
semantic).

---

## 9. `store.put` and `store.aput`

```python
# Sync
store.put(namespace, key, value, index=None)

# Async
await store.aput(namespace, key, value, index=None)
```

`index` is a list of field names to embed for vector search.
`put` upserts (overwrites if the key exists).

`aput` is the async variant. Use it from async nodes.

---

## 10. Common pitfalls

1. **Forgetting `index=` on `put`.** The item is stored but
   not searchable semantically. Add `index=["field_name"]`
   for fields the model should match against.
2. **Confusing namespace vs. key.** The namespace is the
   grouping; the key is the unique id within the namespace.
   Forgetting the namespace and using just a key means
   the item lives at the root (probably not what you want).
3. **Using the store for conversation state.** The store is
   for cross-thread data. Use the checkpointer for the
   current conversation.
4. **Not configuring embeddings on `PostgresStore`.** Without
   `index={...}`, semantic search fails (or returns nothing).
5. **Mixing sync and async APIs.** `store.put` vs
   `store.aput`. Use the right one for your node.
6. **Forgetting `await store.setup()`.** Tables don't exist;
   writes fail.
7. **Items in the store are not versioned.** `put` overwrites.
   If you need history, the checkpointer is the right tool.
8. **`filter` keys are exact-match.** For "value > 5," use
   a query that ranks by relevance, or post-filter the
   results in Python.
9. **The store's data is global, not per-graph.** Two graphs
   in the same process share the same store. Use namespaces
   to segregate.
10. **Putting Pydantic models in `value`.** Pydantic models
    are JSON-serializable. Other Python objects (datetime,
    Path, custom classes) are not — convert to dict/str
    first.

---

## 11. What to read next

- [08-checkpoints-and-persistence.md](08-checkpoints-and-persistence.md)
  — the checkpointer (conversational state).
- [10-human-in-the-loop.md](10-human-in-the-loop.md) — the
  HITL flow with stores.
- LangGraph memory: <https://langchain-ai.github.io/langgraph/concepts/memory/>
