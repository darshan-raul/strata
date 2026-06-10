"""LangGraph state machine for the agent.

Phase 2 graph: `call_model` → (conditional) → `tools` or `END`.

    ┌──────────────┐      has tool_calls       ┌──────────────┐
    │  call_model  │ ─────────────────────────▶│    tools     │
    │ (LLM thinks) │                           │ (run a tool) │
    └──────┬───────┘                           └──────┬───────┘
           │ no tool_calls                            │
           ▼                                          │
          END  ◀──────────────────────────────────────┘
                   (loops back to call_model)

The graph holds state in memory for the duration of one HTTP request.
No checkpointer, no confirmation node, no RAG node in Phase 2.

The system prompt is intentionally minimal: it tells the model which
tools exist (via bound tool schemas) and that the data comes from
mocked sources. We do NOT pre-instruct on tone or formatting in Phase 2
because we want to see what the model does by default — that's the
learning.
"""
from __future__ import annotations

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.providers.litellm_provider import get_chat_model
from app.state import AgentState
from app.tools.delete_cluster import delete_cluster
from app.tools.get_cluster_logs import get_cluster_logs
from app.tools.get_cluster_status import get_cluster_status
from app.tools.list_clusters import list_clusters
from app.tools.provision_cluster import provision_cluster

SYSTEM_PROMPT = """You are Strata, an AI co-pilot for a Kubernetes platform.
You can list, inspect, provision, and delete EKS clusters by calling
the available tools. The tool data is mocked for now; treat it as
ground truth for the user's account.

When you answer:
- Prefer tool calls over guessing. If the user asks about a cluster,
  call the right tool first, then summarize the result.
- Be concise. The user is a senior k8s/AWS engineer.
- If a tool returns an error or no rows, say so plainly.
"""


def _build_tools() -> list:
    """Return the full tool list. Order matters for some LLM tool-pickers."""
    return [
        list_clusters,
        get_cluster_status,
        get_cluster_logs,
        provision_cluster,
        delete_cluster,
    ]


def call_model(state: AgentState) -> dict:
    """The single LLM call. Prepends a system message if this is the first turn."""
    tools = _build_tools()
    llm = get_chat_model().bind_tools(tools)

    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

    response = llm.invoke(messages)
    return {"messages": [response]}


def build_graph():
    """Construct and compile the LangGraph StateGraph.

    Returns a CompiledStateGraph. Call .invoke({"messages": [...]}) to
    run it; .stream(...) to get incremental updates.
    """
    tools = _build_tools()

    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", ToolNode(tools))

    graph.add_edge(START, "call_model")
    graph.add_conditional_edges(
        "call_model",
        tools_condition,
        {
            "tools": "tools",
            END: END,
        },
    )
    graph.add_edge("tools", "call_model")

    return graph.compile()
