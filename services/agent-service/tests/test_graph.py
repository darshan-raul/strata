"""Tests for the LangGraph state machine.

These do NOT need a real LiteLLM. We monkeypatch the chat model with
a `FakeListChatModel` that returns canned responses, and assert the
graph routes through `call_model` → `tools` → `call_model` → END
correctly.

The pattern is borrowed from LangGraph's own test suite: a list of
fake responses drives the LLM, and we observe what messages ended up
in the final state.
"""
from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage

from app import graph as graph_module
from app.graph import build_graph


class _FakeChatModelWithTools(FakeMessagesListChatModel):
    """A FakeMessagesListChatModel that supports `bind_tools`.

    `bind_tools` is what `call_model` in `app.graph` calls on the chat
    model. The base fake raises NotImplementedError on it, so we
    override to return self — the canned responses already carry the
    tool_calls we want to exercise.
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> _FakeChatModelWithTools:  # type: ignore[override]
        return self


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> _FakeChatModelWithTools:
    """Return a fake LLM and monkeypatch `get_chat_model` to return it.

    The fake is preloaded with a sequence of responses:
      1. AIMessage with a tool_call to list_clusters
      2. AIMessage with the final natural-language answer
    """
    responses: list[Any] = [
        AIMessage(
            content="",
            tool_calls=[ToolCall(name="list_clusters", args={}, id="call-1")],
        ),
        AIMessage(content="You have 3 clusters: demo (READY), staging (PROVISIONING), scratch (FAILED)."),
    ]
    fake = _FakeChatModelWithTools(responses=responses)

    def _stub() -> Any:
        return fake

    monkeypatch.setattr(graph_module, "get_chat_model", _stub)
    return fake


def test_graph_routes_through_tools_and_emits_final_message(fake_llm: _FakeChatModelWithTools) -> None:
    g = build_graph()
    result = g.invoke({"messages": [HumanMessage(content="list my clusters")], "thread_id": "t-test"})

    msgs = result["messages"]
    # 1: HumanMessage (input)
    # 2: AIMessage (the LLM decides to call list_clusters)
    # 3: ToolMessage (result of list_clusters)
    # 4: AIMessage (final natural-language answer)
    assert len(msgs) == 4
    assert isinstance(msgs[0], HumanMessage)
    assert isinstance(msgs[1], AIMessage)
    assert isinstance(msgs[2], ToolMessage)
    assert isinstance(msgs[3], AIMessage)

    assert msgs[1].tool_calls[0]["name"] == "list_clusters"
    assert msgs[2].name == "list_clusters"
    assert "demo" in msgs[3].content


def test_graph_responds_directly_when_no_tool_call_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the LLM responds without tool_calls, the graph should END after one call_model."""
    responses: list[Any] = [
        AIMessage(content="Hi! I can help you manage EKS clusters. What do you need?"),
    ]
    fake = _FakeChatModelWithTools(responses=responses)
    monkeypatch.setattr(graph_module, "get_chat_model", lambda: fake)

    g = build_graph()
    result = g.invoke({"messages": [HumanMessage(content="hello")], "thread_id": "t-test"})

    msgs = result["messages"]
    # SystemMessage is prepended in call_model, then Human, then final AIMessage.
    # No ToolMessage — graph went straight from call_model to END.
    assert any(isinstance(m, AIMessage) and m.content.startswith("Hi!") for m in msgs)
    assert not any(isinstance(m, ToolMessage) for m in msgs)
