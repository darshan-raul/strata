"""Typed state for the LangGraph agent.

Phase 2 keeps this minimal: a single `messages` field managed by the
`add_messages` reducer from langgraph, plus a `thread_id` for correlation
in logs (not used as a checkpointer key in Phase 2 — the graph holds
state in memory for the duration of one HTTP request).
"""
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """State carried between nodes of the graph.

    `messages` is the conversation history. The `add_messages` reducer
    appends new messages rather than overwriting, so AI and Tool messages
    accumulate in the order the LLM sees them.
    """

    messages: Annotated[list, add_messages]
    thread_id: str
