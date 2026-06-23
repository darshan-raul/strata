# RAG — Retrieval-Augmented Generation

> **Stub for Phase 0.** The full doc lands in Phase 6 when RAG
> ships. For now, see `notes/rag.md` for the v1 design (will be
> rewritten for per-user / multi-tenant in Phase 6).

## Planned outline

1. Why RAG at all
2. Strata's RAG shape (per-user)
3. The retriever-service API
4. The Qdrant collections (per-user, per-collection)
5. The agent's `retrieve` node
6. Ingestion: the `rag-indexer` Go service
7. Chunking strategies
8. Metadata filtering
9. Hybrid search and reranking (deferred to v1.1+)
10. Degraded mode
11. What to read next

Key changes from the v1 design (`notes/rag.md`):

- **Per-user Qdrant collections.** Each user gets their own
  collection namespace; the rag-indexer tags every chunk with
  `user_id` and the retriever filters on it.
- **Per-user encryption DEK** for the embedding pipeline's
  metadata (if needed; embeddings themselves are not sensitive
  but cluster status text might be).
- **KMS-backed** retriever-service credentials.
- **Routed through the orchestrator** in addition to being
  callable directly from the agent — the orchestrator can
  enforce user-scoped access even if the agent is compromised.