"""FastAPI app: POST /chat streams NDJSON.

Wire format (one JSON object per line):
    {"type": "token", "text": "..."}
    {"type": "tool_call", "name": "...", "args": {...}}
    {"type": "tool_result", "name": "...", "result": ...}
    {"type": "done"}

Why NDJSON and not SSE: easier to debug from `curl`, easier to test
with `httpx`, no event-id / retry quirks. Phase 5+ switches to SSE
when the web UI's `<CopilotRail />` lands.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.graph import build_graph

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("agent-service")

app = FastAPI(title="strata-agent-service", version="0.1.0")

# Build the graph once at import. LangGraph graphs are stateful per
# invocation but the compiled graph itself is reusable.
_GRAPH = build_graph()


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    graph_built: bool


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", graph_built=_GRAPH is not None)


def _ndjson(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, default=str) + "\n").encode("utf-8")


async def _stream_chat(message: str, thread_id: str) -> AsyncIterator[bytes]:
    """Run the graph on one user message and stream NDJSON events.

    The graph is invoked synchronously (LangGraph's sync invoke is fine
    for Phase 2; we'll move to astream for the SSE migration in Phase 5).
    We yield events as we observe messages appended to the state.
    """
    log.info("thread_id=%s user_message=%r", thread_id, message)

    initial_state: dict[str, Any] = {
        "messages": [HumanMessage(content=message)],
        "thread_id": thread_id,
    }

    result = _GRAPH.invoke(initial_state)
    final_messages = result["messages"]

    for msg in final_messages:
        if isinstance(msg, AIMessage):
            tool_calls = msg.additional_kwargs.get("tool_calls") or []
            for tc in tool_calls:
                fn = tc.get("function", {})
                args_raw = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except json.JSONDecodeError:
                    args = {"_raw": args_raw}
                yield _ndjson(
                    {
                        "type": "tool_call",
                        "name": fn.get("name", "?"),
                        "args": args,
                    }
                )
            if msg.content:
                yield _ndjson({"type": "token", "text": msg.content})
        elif isinstance(msg, ToolMessage):
            yield _ndjson(
                {
                    "type": "tool_result",
                    "name": msg.name or "?",
                    "result": msg.content,
                }
            )

    yield _ndjson({"type": "done"})


@app.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    thread_id = req.thread_id or f"t-{uuid.uuid4().hex[:8]}"
    return StreamingResponse(
        _stream_chat(req.message, thread_id),
        media_type="application/x-ndjson",
    )
