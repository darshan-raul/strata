# RAG — Retrieval-Augmented Generation

The pattern of *retrieving relevant context from an external store
and injecting it into the LLM prompt* before answering. Strata's
co-pilot uses RAG so it can answer questions about Strata itself
(architecture, runbooks, ops), about specific EKS clusters
(status, recent activity), and about ArgoCD/EKS/AWS — without
stuffing all of that into the LLM's system prompt.

RAG lands in **Phase 4**. This doc is the design you need to
understand before that phase.

---

## 1. Why RAG at all

LLMs are trained on snapshots of public data. They do not know:

- The current state of your clusters (rows in Postgres).
- What `docs/strata/agent-architecture.md` says about your control
  plane (your internal architecture doc).
- That your org's runbook for EKS upgrades says "drain via Karpenter
  first, then bump the node group" (a private Google Doc).

Three approaches to give the LLM this knowledge:

1. **Stuff it in the system prompt.** Works until the context
   window fills up. Doesn't scale beyond a few hundred lines.
2. **Fine-tune the model on the data.** Expensive, slow, brittle,
   doesn't help with data that changes daily.
3. **Retrieve at query time, inject into the prompt.** This is RAG.

Strata picks RAG because:

- The data is structured (Postgres rows) and unstructured (markdown
  docs) and changes often.
- A senior k8s/AWS engineer expects fresh answers, not "as of
  training cutoff."
- We want to **show our work** — RAG responses can include
  citations, and the user can verify the source.

---

## 2. Strata's RAG shape

```
                    ┌──────────────┐
   user question ──▶│ agent-service│
                    │  (Python,    │
                    │   LangGraph) │
                    └──────┬───────┘
                           │
                           │  POST /retrieve
                           │  {collection, query, top_k, filter}
                           ▼
                    ┌──────────────┐
                    │ retriever-   │ ──── POST /v1/embeddings ──┐
                    │ service (Go) │                            │
                    └──────┬───────┘                            ▼
                           │                            ┌────────────┐
                           │                            │  LiteLLM   │
                           │ vector search              │ (Titan v2) │
                           ▼                            └────────────┘
                    ┌──────────────┐
                    │   Qdrant     │
                    │ (vector DB)  │
                    └──────────────┘

  ingestion (separate flow, runs every 60s):
  
    Postgres rows ──▶ rag-indexer (Go) ──▶ POST /index ──▶ retriever-service
                                                          └─▶ embed + upsert
```

Three services, all in-cluster, all talking HTTP. No Qdrant client
in the agent-service. No embedding model in the agent-service. The
retriever-service is the only thing that knows about both Qdrant
and the embedding model.

### Why a separate `retriever-service`?

Per AGENTS.md cross-cutting rule #3:

> **All RAG retrieval goes through `retriever-service`.** `agent-service`
> and any other consumer call the retriever HTTP API, never Qdrant
> directly. Centralizes embedding-model choice and makes it swappable.

Reasons:

1. **Embedding model choice lives in one place.** Switching from
   Titan v2 to Cohere embed-v3 means changing one config in the
   retriever, not in every consumer.
2. **Vector store is swappable.** Swap Qdrant for pgvector, Milvus,
   or Pinecone by rewriting one Go service. The agent doesn't care.
3. **Auth, rate-limiting, and observability are centralized.** One
   service to add rate limits to, one set of logs.
4. **The agent stays dumb.** It calls `POST /retrieve` and gets
   back chunks. The retrieval strategy, hybrid search, reranking,
   metadata filters — all server-side.

---

## 3. The retriever-service API

```
POST /retrieve
  body: {
    "collection": "strata_docs",
    "query": "how do I provision a cluster?",
    "top_k": 5,
    "filter": {"section": "onboarding"}  // optional metadata filter
  }
  response: {
    "chunks": [
      {
        "id": "strata_docs/onboarding.md#provisioning",
        "text": "To provision a cluster, the user runs...",
        "score": 0.84,
        "metadata": {"path": "onboarding.md", "section": "provisioning", "sha": "abc123"}
      },
      ...
    ]
  }
```

```
POST /index
  body: {
    "collection": "strata_docs",
    "id": "strata_docs/onboarding.md#provisioning",
    "text": "To provision a cluster, the user runs...",
    "metadata": {"path": "onboarding.md", "section": "provisioning", "sha": "abc123"}
  }
  response: {"upserted": true}
```

```
DELETE /index/{collection}/{id}
  response: {"deleted": true}

GET /healthz
  response: {"status": "ok", "qdrant": "ok"}
```

The agent-service calls `/retrieve` from a LangChain `BaseRetriever`
wrapper. The `rag-indexer` calls `/index` on a 60s timer.

---

## 4. The Qdrant collections

Qdrant is the vector store. Each "thing we want to retrieve" lives
in a **collection** with a fixed vector dimension (1024 for Titan
v2 at default config).

| Collection | Source | One chunk per | Metadata |
|---|---|---|---|
| `strata_clusters` | `clusters` table | cluster row | `cluster_id`, `user_id`, `status`, `region`, `updated_at` |
| `strata_alerts` | `alerts` table | alert row | `cluster_id`, `severity`, `created_at` |
| `strata_workflow_runs` | `workflow_runs` table | run row | `cluster_id`, `workflow_name`, `status`, `started_at` |
| `strata_docs` | `docs/**.md` | document section | `path`, `section`, `sha` |

Why split by source? Different update cadences, different chunk
strategies, different metadata filters. The user asks "what's the
status of cluster cl-001?" — the agent searches `strata_clusters`
with `filter: {cluster_id: "cl-001"}`. The user asks "how do I
upgrade an EKS cluster?" — the agent searches `strata_docs`.

The collection-to-source mapping is the agent's job to know. The
LLM sees a `retrieve_docs` tool with a `collection` parameter; the
description tells it when to use which.

---

## 5. The agent's `retrieve` node (Phase 4)

In LangGraph, RAG is a node before `call_model`:

```mermaid
flowchart LR
    START([START]) -->|if is_doc_question| retrieve[retrieve]
    START -->|otherwise| call_model
    retrieve -->|"SystemMessage with chunks"| call_model[call_model]
    call_model -->|conditional| tools[ToolNode] or END
```

### The `retrieve` tool

```python
from langchain_core.tools import tool
import httpx

@tool
def retrieve_docs(collection: str, query: str, top_k: int = 5) -> list[dict]:
    """Retrieve relevant chunks from a Strata RAG collection.

    Use this when the user asks:
    - 'How do I ...?' (docs collection)
    - 'What's the status of cluster X?' (clusters collection)
    - 'Any alerts about ...?' (alerts collection)
    - 'What happened during the last provision of ...?' (workflow_runs collection)

    Args:
        collection: One of 'strata_docs', 'strata_clusters', 'strata_alerts',
                    'strata_workflow_runs'.
        query: The question or phrase to search for. Be specific.
        top_k: Number of chunks to return (default 5).

    Returns:
        A list of chunk dicts with 'text', 'score', and 'metadata'.
    """
    r = httpx.post(
        "http://retriever-service:8080/retrieve",
        json={"collection": collection, "query": query, "top_k": top_k},
        headers={"Authorization": f"Bearer {os.environ['RETRIEVER_API_KEY']}"},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()["chunks"]
```

### Routing: when to retrieve?

Two options:

1. **Always retrieve.** Simple. Adds latency and token cost to
   every turn. Doesn't scale if you have many collections.
2. **Conditional retrieve.** A node before `call_model` that
   inspects the last user message and decides whether to call
   `retrieve_docs` first. Faster, cheaper, but you have to write
   the routing logic.

Strata uses option 2. Heuristic: if the user message contains a
"what/how/why/when" question word, or matches a known doc-keyword
regex (e.g. `provision`, `deprovision`, `argocd`, `eks upgrade`,
`secret`, `iam`), route to retrieve. Otherwise, skip.

The routing function lives in `app/graph.py` as a conditional edge:

```python
def should_retrieve(state: AgentState) -> str:
    last = state["messages"][-1]
    if not isinstance(last, HumanMessage):
        return "call_model"
    text = last.content.lower()
    keywords = ["how", "what", "why", "when", "where", "explain", "docs",
                "provision", "deprovision", "delete", "argocd", "eks",
                "secret", "iam", "vpc", "nat", "subnet"]
    if any(k in text.split() for k in ["how", "what", "why", "when", "where", "explain"]) \
       or any(k in text for k in ["provision", "deprovision", "argocd", "eks upgrade"]):
        return "retrieve"
    return "call_model"
```

This is naive. Phase 4 will refine it. The point is the LLM gets
context for questions and skips retrieval for terse commands
("list my clusters" doesn't need RAG).

### Injecting context into the prompt

The retrieve node returns a list of chunks. The standard pattern is
to inject them as a system message before the LLM call:

```python
def retrieve_node(state: AgentState) -> dict:
    last_msg = state["messages"][-1].content
    chunks = retrieve_docs.invoke({
        "collection": "strata_docs",
        "query": last_msg,
        "top_k": 5,
    })
    context = "\n\n---\n\n".join(
        f"[{c['metadata'].get('path', '?')}]\n{c['text']}" for c in chunks
    )
    context_msg = SystemMessage(
        content=f"Use these Strata docs to answer the user's question. "
                f"Cite the path in brackets. If the docs don't answer it, say so.\n\n{context}"
    )
    return {"messages": [context_msg]}
```

The next `call_model` invocation sees this `SystemMessage` in the
message history and uses it. The `add_messages` reducer puts it
right before the last `HumanMessage` (insertion order is preserved).

**Critical:** the context message is appended to the state. On the
NEXT user turn, it's still there. This is usually wrong. You want
context to be transient. Two ways to handle it:

1. **Tag it with a custom `id`** and use a reducer that filters
   out previous context messages on new turns.
2. **Use a separate `context` field in state** with its own
   reducer that always overwrites. The retrieve node writes to
   `context`; the call_model node reads `context` and includes
   it in the LLM call but doesn't add it to `messages`.

Option 2 is cleaner. Strata will do option 2.

---

## 6. Ingestion: the `rag-indexer` Go service

Reads Postgres every 60s, embeds new/updated rows, upserts to
Qdrant via the retriever-service. Two flows:

### Platform data (Postgres)

```go
// pseudo-Go
ticker := time.NewTicker(60 * time.Second)
for range ticker.C {
    rows := db.Query("SELECT * FROM clusters WHERE updated_at > $1", lastSeen)
    for rows.Next() {
        text := formatClusterAsText(row)  // human-readable summary
        retriever.Index("strata_clusters", row.ID, text, row.Metadata)
    }
    // ...same for alerts, workflow_runs
}
```

The `formatClusterAsText` function is the chunking strategy. For
cluster rows, it's something like:

```go
func formatClusterAsText(c Cluster) string {
    return fmt.Sprintf(
        "Cluster %s (id: %s) is in region %s, k8s version %s, status %s, "+
        "last updated %s. %d node groups. Created by user %s.",
        c.Name, c.ID, c.Region, c.K8sVersion, c.Status, c.UpdatedAt,
        c.NodeGroupCount, c.UserID,
    )
}
```

Why human-readable text and not a JSON blob? Embedding models are
trained on natural language. "Cluster demo is READY in us-west-2"
embeds closer to user questions than `{"id":"cl-001","status":"READY"}`.

### Docs (the `docs/` directory)

The indexer also walks `docs/**/*.md`, splits by header, embeds
each section, upserts to `strata_docs`:

```go
filepath.Walk("docs/", func(path string, info fs.FileInfo, err error) error {
    if !strings.HasSuffix(path, ".md") { return nil }
    text, _ := os.ReadFile(path)
    sections := splitByHeader(text)  // <h1>, <h2>, <h3>
    for _, section := range sections {
        id := path + "#" + section.Anchor
        sha := gitSHA(path)  // re-embed only if file changed
        retriever.Index("strata_docs", id, section.Text, {"path": path, "section": section.Anchor, "sha": sha})
    }
    return nil
})
```

The `make reindex-docs` target runs this on demand. In Phase 6, an
Argo Workflow or CronJob replaces it.

---

## 7. Chunking strategies

The most important lever for RAG quality. A chunk is a piece of
text that gets embedded as a single vector. Too small = lost
context. Too large = noise dilutes the embedding.

### Markdown docs (header-based)

Split on `#`, `##`, `###`. Each section is one chunk. A section
under 200 chars is concatenated with the next. A section over
2000 chars is recursively split on `###` or paragraphs.

```python
def chunk_markdown(text: str) -> list[Chunk]:
    sections = re.split(r'\n(?=##\s)', text)
    chunks = []
    for s in sections:
        if len(s) < 200:
            continue
        if len(s) > 2000:
            chunks.extend(_split_long_section(s))
        else:
            chunks.append(Chunk(text=s, section=derive_anchor(s)))
    return chunks
```

### Cluster rows (one row = one chunk)

Trivial. One cluster row → one text string → one embedding.

### Logs (deferred)

Don't put logs in v1. If you do, the chunk strategy is "5-minute
window" — aggregate pod logs into 5-min windows per cluster, embed
the concatenation. Far too noisy otherwise.

### Code blocks (in docs)

Preserve them. LLMs read code well. But code in a chunk makes the
chunk embedding less about the surrounding prose. If a section is
mostly code, embed the prose before and after separately.

---

## 8. Metadata filtering

Qdrant supports filtering on payload fields at query time. This is
the key to "find docs about EKS upgrades" vs "find all docs".

```python
# all docs about a specific section
filter = {"must": [{"key": "section", "match": {"value": "eks-upgrades"}}]}

# all chunks from a specific doc
filter = {"must": [{"key": "path", "match": {"value": "eks-onboarding.md"}}]}

# alerts for a specific cluster
filter = {"must": [{"key": "cluster_id", "match": {"value": "cl-001"}}]}
```

The agent passes the filter as part of the `retrieve_docs` call
arguments. The LLM sees "you can filter by path, section, or
cluster_id" in the tool description and constructs the right filter.

**Why this matters:** without metadata filtering, you rely entirely
on vector similarity, which is fuzzy. With filtering, you can do
"give me all alerts for cl-001, ranked by similarity to this
question." The filter narrows the candidate set; vector search
ranks within it.

---

## 9. Hybrid search and reranking (deferred to v1.1+)

Pure vector search misses exact-match queries. "What's the EKS
version of cluster cl-001?" wants the literal answer, not a
similarity match. Hybrid search combines BM25 (keyword) and vector
similarity scores.

Qdrant supports this natively. We enable it in a later phase if
measured recall is poor:

```python
# Qdrant hybrid search
results = qdrant.search(
    collection_name="strata_clusters",
    query_vector=embed(query),
    query_filter=filter,
    limit=5,
    # hybrid params
    fusion="rrf",  # reciprocal rank fusion
    prefetch=[
        {"query": embed(query), "using": "dense"},
        {"query": bm25_encode(query), "using": "sparse"},
    ],
)
```

Reranking (Cohere Rerank, BGE-reranker) takes the top-50 from
retrieval and re-ranks with a more expensive model. Worth it only
if you're already getting 50+ candidates and need to pick the top 5
precisely. Phase 4 doesn't have this problem yet (we have ~100 docs
total).

---

## 10. Degraded mode

If Qdrant is down, `retriever-service` returns 503. The
`retrieve_docs` tool should catch this and return an empty list
(plus a warning message that ends up in the tool result). The
agent then answers without context.

```python
try:
    r = httpx.post(...)
    r.raise_for_status()
    return r.json()["chunks"]
except httpx.HTTPError as e:
    return [{"text": f"(retrieval unavailable: {e})", "metadata": {"_error": True}}]
```

The model sees the error and either apologizes ("I can't look up
docs right now") or answers from its own knowledge with a
disclaimer. Either is better than the agent loop failing entirely.

The system message in the retrieve node should say: "If the
retrieval result says retrieval is unavailable, answer from your
own knowledge and tell the user you couldn't look it up."

---

## 11. What to read next

- `docs/bedrock.md` — what Titan v2 is and why we picked it.
- `docs/litellm.md` — how embeddings get called.
- `docs/langgraph.md` — the retrieve node in graph topology.
- `docs/strata/agent-architecture.md` — the full picture.
- Qdrant docs: <https://qdrant.tech/documentation/>
- Qdrant hybrid search: <https://qdrant.tech/articles/hybrid-search/>
